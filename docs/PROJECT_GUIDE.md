# 项目执行指南

## 1. 当前进展

当前实现包含 `39b0e7c` 的continuation错位布局、`1eaaf99` 的简单batch元数据单次
初始化及 `6064c6e` 的通用clobber解锁；CPU热值C `if` 分流和MCS-entry机制来自 `ccefa62`，
采样批次及窗口使用下述当前参数。
模块通过显式 `kd_spinlock_t` 与caller-clobber v1 API接入spin，32位KD字承载
获取、pending、MCS tail及combiner仲裁。Linux、TCLock、KD对象不能混用协议。
mutex实现与嵌套控制保留，全局mutex hook仍未安装；加载provider不自动代理普通Linux锁。

获取宏pin后只按CPU热值执行C `if`：冷分支为完整原生CAS/pending/MCS，热分支
为pinned clobber入口。宽clobber只属于获取热分支，寄存器保存由编译器安排；
解锁无条件走通用clobber入口，冷/热均传lock/SP/IP/BP，provider依据低字节5或
普通状态完成对应释放，不读取CPU热值。没有on/off编译壳选择或手工push/pop。

spin CPU每次实际MCS发布计数，每8次读取一次时钟，整批耗时严格小于400万TSC ticks才判热，
不检查队列深度；2/3线程真实入队也可升温。mutex CPU仍每1024次入口检查400亿窗口；
两类单锁均第33次检查25亿窗口。热表为每CPU/type
256桶、256条完整地址记录，无候选、淘汰或busy字段；满表不覆盖。owner/ticket/frame
独立存活。完整规则及准入边界见 [执行流](JIT_EXECUTION.md)。

每CPU仍预分配20 KiB：continuation在低12 KiB内按CPU错位，高8 KiB等待栈不变。
普通完成先pop再通知，native最终解锁等待根ticket借用退休。布局及TCLock差异见
[EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。

当前MCS8/CPU400万组合已完成[168场三轮矩阵](../bench/tclock_compare/results/20260923-mcs8-cpu4m.md)，
8/20线程adaptive本批未观察到历史对照退化，3/4线程仍慢、单线程未一致改善。此前MCS1/CPU400亿版本覆盖见
[完整三轮矩阵](../bench/tclock_compare/results/20260923-spin-default-heat-full3.md)，
优化隔离、失败候选及短/长批次限制见[性能调查](../bench/tclock_compare/results/20260923-spin-single-hot-balance.md)。
历史结果不能拼接成当前全量验收。并发冷准备、pinned mutex以及访问时guard等
已知边界见 [TODO](TODO.md)；后续性能任务只维护在 [PERFORMANCE_PLAN](PERFORMANCE_PLAN.md)。

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
