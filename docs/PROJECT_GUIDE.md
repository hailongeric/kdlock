# 项目执行指南

## 1. 当前进展

当前模块通过显式 `kd_spinlock_t` 与 caller-clobber v1 API 接入 spin 调用者。
32 位 KD 字直接承载获取、pending、KD MCS tail 和 combiner 仲裁；gate/S、
Linux L 二次获取及旧 spin 统一分发均已删除。Linux、TCLock、KD 对象不能混用协议。
mutex 协议和嵌套控制调用保留，但 `kd_main.c` 未安装全局 mutex hook。
加载 provider 不会让普通 Linux spin/mutex 自动进入代理。

spin/mutex 分别有每 CPU 16 桶、6 候选的热锁表。默认 `hotlock_mode=adaptive`，
要求本地 `score-error >= 10000`；`observe` 固定准入并记录相同统计。
CPU/候选窗口为 400 亿/25 亿 TSC，合并 `record_*` 首次初始化时间，之后每
10240 样本刷新窗口；`query_*` 只读缓存。普通 spin 在入口做热度/上下文判断，
关闭代理时跳过记录；普通根 fast/pending 免 ticket，队列分支才占用并检查翻译。
owner/ticket/frame 独立存活，解锁不查热表。

当前沿用 `644f231` 的每 CPU 20 KiB continuation/等待栈区；普通完成先 pop
再通知，native 的最终解锁等待根 ticket 借用全部退休。对象大小、分配位置及
TCLock/KD 数据流集中在 [EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。
最新定向功能结果见 [tests](../tests/README.md#mcs-recovery-validation)，
性能调查及恢复结果见 [回退报告](../bench/tclock_compare/results/20260921-mcs-recovery.md)，
此前完整矩阵见 [三方报告](../bench/tclock_compare/results/20260920-continuation.md)。此前 adaptive
和记录器回退保留在 [历史报告](../bench/tclock_compare/results/20260920-local-hash.md)；
新 observe 成绩不验证 adaptive 收益。更广远端 native/无锁 relay 的强制 live 时序
及访问时 guard 等边界见 [TODO](TODO.md)，历史成绩不能作为当前验收。

## 2. 阅读顺序

- [DESIGN](DESIGN.md)：模块边界与实现契约；[锁协议](design/locking.md)定义所有权。
- [JIT_EXECUTION](JIT_EXECUTION.md)：准备、等待、执行、续跑和退出。
- [JIT_REGISTER_ABI](JIT_REGISTER_ABI.md)：寄存器包、wrapper 和控制 CALL。
- [EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)：TCLock/KD 分阶段流程、
  对象尺寸、创建位置和跨 CPU 数据流。
- [CODE_MAP](CODE_MAP.md)：文件入口；[tests](../tests/README.md)和
  [bench](../bench/README.md)维护验证和测量命令。
- [AGENTS](AGENTS.md)：环境与操作边界；[PERFORMANCE_PLAN](PERFORMANCE_PLAN.md)
  维护后续性能任务。

## 3. 一步一步运行

### 3.1 同步源码

宿主目录 `/home/eric/vm/vm-shared/kdlock`；guest SSH 为 `root@127.0.0.1:2222`，
项目目录 `/root/host_fs/kdlock`。normal 模式为 9p 共享，recovery 为独立 ext4 副本。
先确认 guest 空闲，再比较 SHA256，只同步变化文件；对本次明确删除的文件同步删除。
不能移动、递归覆盖或清空 `/root/host_fs`。运行器冻结输入后不可再改 guest 文件。

### 3.2 进入 guest 并检查基线

```sh
cd /root/host_fs/kdlock
python3 bench/spin_cacheline/kernel_identity.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
```

当前 release 为 `6.1.159-kdclobber2`，捕获 Build ID 为
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。核验源码、配置、构建及运行身份，
不能只看 uname。保留 `nokaslr`、voluntary 抢占和既定 CPU 放置；不要自动改内核。
旧内核仅用于匹配历史源码的重现，见 [kernel_baseline](../kernel_baseline/README.md)。

### 3.3 检查依赖与空闲状态

使用 guest 的 CPython 3.10 和 [固定依赖](../disassem/requirements.txt)，
需要 gcc/make/binutils、Python 开发头文件。已有环境可直接使用：

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C
python3 -m pip check
python3 - <<'CHECK'
import sys
sys.path.insert(0, 'bench/spin_cacheline')
import bench_runtime
bench_runtime.idle()
CHECK
```

新环境在仓库外创建 venv，按 requirements 安装固定版本；不要升级系统 Python
或全局 pip 包。构建及测试只在 guest，宿主只做源码/Git/静态检查。

### 3.4 构建和选择检查

```sh
make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 W=1
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
make -C tests/unit run
```

默认单元入口仅运行两个基础 C 程序。按修改添加 `PY_TESTS`，不要自动跑全量。
provider/device 生命周期用 `tests/run_all.sh --case module`；实际 JIT 使用
[直接运行器](../bench/tclock_compare/README.md)，支持 `plain`、`nested`、`early`。
所有 live 检查先按 [AGENTS](AGENTS.md)从 monitor 确认真实可恢复快照，再设置
`KDLOCK_RECOVERY_CONFIRMED=1`，命令带外层 timeout，结果放仓库外新目录。

### 3.5 排空及证据

停止新调用，等待已知 workload 和翻译者退出，retire 成功后先卸载 workload，
再卸载 provider。EBUSY 不能强制卸载；继续保存现场并排查未完成请求。
不要把 source lease 误当成锁对象任意释放或通用 hook reader 的屏障。

运行器保留源码/ELF 哈希、内核身份、正文计数、负载结果及排空状态。
NORMAL 只代表发布，实际 JIT 需要 wrapper 返回后的正文计数。
observe 竞争正例缺正文即失败；adaptive 的 NO_JIT 性能样本不算 JIT PASS。
旧 hook live 脚本及其操作专题已删除；历史证据见 [VALIDATION](VALIDATION.md)。
