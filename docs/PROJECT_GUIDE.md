# 项目执行指南

## 1. 当前进展

spin通过显式`kd_spinlock_t`和caller-clobber v1 API接入，32位KD字承载获取、pending、
MCS tail及combiner仲裁；Linux、TCLock、KD对象不能混用协议。mutex协议保留，
全局hook未安装，加载provider不自动代理普通Linux锁。

当前只保留adaptive：复用per-CPU MCS/获取计数，MCS达到512时用右移判断比例并清零，再采时，
原生队头在同一近似边界检查捕获队尾以内的六个后继。冷获取内联首次CAS，
热获取走pinned clobber入口；解锁统一走generic clobber协议。
热度只影响未来准入，owner/ACK/frame退休保持独立；完整规则见
[执行流](JIT_EXECUTION.md#21-热度与角色)。spin waiter诊断改为per-CPU事件总数，
live观察近似，独立排空后检查最终余额，见[锁协议](design/locking.md#spin-diagnostic-identity-lifetime)。

当前锁实现的[c1三方矩阵及nested/early](../bench/tclock_compare/results/20260924-warmed-peak.md)
和[1/8 cacheline复测](../bench/tclock_compare/results/20260925-c1-c8-warmed-peak.md)已完成。
成绩、样本分布及源码身份只在匹配报告中维护，不拼接为全量功能验收。
并发冷准备、pinned mutex和访问时guard等边界见[TODO](TODO.md)，
后续性能任务只维护在[PERFORMANCE_PLAN](PERFORMANCE_PLAN.md)。

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
默认每配置三轮，报告min/median/max及波动；运行器负责构建、业务、IRQ/preempt、JIT和排空检查。
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
运行器要求实际JIT的配置缺正文即失败；允许的 NO_JIT 性能样本不算 JIT PASS。
旧 hook live 脚本及其操作专题已删除；历史证据见 [VALIDATION](VALIDATION.md)。

### 3.6 2026-09-21 存储清理记录

历史维护只清理 `linux-6.1.159`、`-kdstatic1`、`-kdstatic2`、`-kdclobber1` 的可重建
编译中间文件，释放约43.03 GiB；旧源码、配置、vmlinux、启动镜像、已安装模块及
恢复基线保留。当前kdclobber2构建树、测试证据和恢复快照未清理，旧树重建须重新
生成中间文件。782个受保护文件清理前后SHA256一致；这不代表重新运行功能或性能。
逐文件清单、脚本与核验见[维护归档](../bench/.tmp/maintenance_20260921/maintenance-20260921.tar.gz)，
guest目录为 `/root/kdlock-evidence/maintenance-20260921/`。
