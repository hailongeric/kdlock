# Spin cacheline 共用组件

当前恢复入口准入及批量时钟，保留顶层 pending 免 ticket 和 continuation 退休协议。同期调查、回退与限制见 [回退报告](../tclock_compare/results/20260921-mcs-recovery.md)。

当前 live 入口为 [tclock_compare/run.py](../tclock_compare/run.py)，说明见
[直接 API 对照](../tclock_compare/README.md)。本目录不再提供旧 hook 扫描、
双 ABI 对照、dispatch-floor 或 live perf 入口。

| 文件 | 当前用途 |
| --- | --- |
| `client.c` | 绑核、统一起跑、一次 ioctl 内批量操作与状态校验 |
| `bench_runtime.py` | 计数、CPU 放置、来源/设备、排空与冻结输入 |
| `bench_session.py` | 直接运行器复用的准备、发布、测量和排空基础类 |
| `provider/prepare.py` | 独立源码副本及只读观察 patch，不修改普通 provider |
| `kernel_identity.py` | 检查指定内核源码、基线、构建和 live Build ID |
| `summarize.py`、`assembly.py`、`profile_summary.py` | 当前/已有记录的离线读取和汇总，不能证明当前实际执行 |
| `test_spin_cacheline.py`、`test_assembly.py` | 客户端、数据 oracle、观察层和离线证据的定向检查 |

`make -C bench/spin_cacheline test` 只在 guest 执行，不加载模块；默认 module
构建显式选择 Linux native。三后端所需模块及符号依赖由直接运行器分别构建。
[执行路径](EXECUTION_PATHS.md)统一记录当前 TCLock/KD 流程、对象大小、分配位置、
跨 CPU 数据流及回收边界；[ticket 阶段优化](../tclock_compare/results/20260921-four-thread-ticket.md)
记录四线程 ticket 前后对照，[此前完整矩阵](../tclock_compare/results/20260920-continuation.md)
对应 `644f231`。[历史结果](results/HISTORY.md)
保留冻结版本，旧运行命令只能在匹配历史 checkout 中使用。
