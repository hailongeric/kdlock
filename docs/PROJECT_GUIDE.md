# 项目执行指南

## 1. 当前进展

当前模块通过显式 `kd_spinlock_t` 与 caller-clobber v1 API 接入 spin 调用者。
32 位 KD 字直接承载获取、pending、KD MCS tail 和 combiner 仲裁；gate/S、
Linux L 二次获取及旧 spin 统一分发均已删除。Linux、TCLock、KD 对象不能混用协议。
mutex 协议和嵌套控制调用保留，但 `kd_main.c` 未安装全局 mutex hook。
加载 provider 不会让普通 Linux spin/mutex 自动进入代理。

spin/mutex 分别有每 CPU 256 桶、256 条精确锁地址记录；模块初始化预分配并采时。
spin CPU 每次合格 MCS 事件、mutex CPU 每 1024 次入口检查 400 亿 TSC 窗口，
冷捷径开启且队列门槛大于0时冷CPU计合格队头获取，其余情况计入队；
fast/pending 不增加 spin CPU 计数。CPU 热才查表；命中直接增加该锁 count，
大于 32（第 33 次）时检查 25 亿 TSC 窗口、刷新 hot、更新时间戳并清零计数。
没有候选排名或淘汰；满表不覆盖，未收录的新锁在默认 adaptive 下走原生。
observe 固定准入并记录统计。CPU 持续热不重置单锁批次，query 只读缓存。
普通 spin 在入口做热度/上下文判断，
关闭代理时跳过记录；普通根 fast/pending 免 ticket，队列分支才占用并检查翻译。
owner/ticket/frame 独立存活，解锁不查热表。

当前沿用 `644f231` 的每 CPU 20 KiB continuation/等待栈区；普通完成先 pop
再通知，native 的最终解锁等待根 ticket 借用全部退休。对象大小、分配位置及
TCLock/KD 数据流集中在 [EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。
当前热表已按[性能回归处理](../bench/tclock_compare/results/20260922-performance-recovery.md)
恢复到此前最佳已测实现。早期直接哈希计数验证见 [tests](../tests/README.md#hotlock-direct-validation)，
同期性能见 [直接哈希对照](../bench/tclock_compare/results/20260921-hotlock-direct.md)：
adaptive 四线程/二十线程近似持平，没有整体提升。
此前两级候选版对照见 [历史采样报告](../bench/tclock_compare/results/20260921-hotlock-twolevel.md)，
不作为当前无候选实现的性能结果。
此前性能调查及恢复结果见 [回退报告](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-recovery.md)，
此前完整矩阵见 [三方报告](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-continuation.md)。此前 adaptive
和记录器回退保留在 [历史报告](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-local-hash.md)；
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

代码修改后可直接运行[三方性能命令](../bench/tclock_compare/README.md#准备与运行)，
默认每配置一轮；运行器负责构建及业务、IRQ/preempt、JIT 和排空检查。
以下独立构建与单元入口按需使用，不要求先跑完再测性能：

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

### 3.6 2026-09-21 存储清理记录

guest 根盘原占用 98%，可用 2.17 GiB；清理后占用 55%，可用 45.18 GiB。
只删除四套旧树 `linux-6.1.159`、`-kdstatic1`、`-kdstatic2`、`-kdclobber1` 内
94280 个 `.o`、`.a` 和 `.tmp_vmlinux.btf` 文件，按文件分配块合计约 43.03 GiB。
排除 `tools/`、`scripts/`、符号链接和全部基线清单文件，没有运行 `make clean`。
旧源码、配置、vmlinux、启动镜像、已安装模块及恢复基线保留；旧树后续重建需要
重新生成这些中间文件。当前 `kdclobber2` 辅助盘构建树未清理。

清理前后 782 个受保护文件 SHA256 一致，当前 kernel identity 和 venv 的
`pip check` 通过，workload/daemon/provider 保持空闲。所有测试和 benchmark
原始证据（包括失败记录）均保留；没有重新运行功能或性能矩阵。
这只释放 guest 文件系统空间，没有压缩宿主虚拟磁盘镜像或删除恢复快照。

逐文件清单、清理脚本、磁盘统计、保护文件哈希和核验输出在 guest
`/root/kdlock-evidence/maintenance-20260921/`，并取回宿主
[维护归档](../bench/.tmp/maintenance_20260921/maintenance-20260921.tar.gz)。
