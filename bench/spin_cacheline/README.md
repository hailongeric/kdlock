# Spin cacheline 共用组件

当前采用精确地址哈希热度统计，保留入口准入、顶层 pending 免 ticket 和 continuation 退休协议。
准入只保留adaptive；每1024次MCS发布用`(entries >> 10) < spin_entry_ratio_limit`比较并清零两个计数。
默认上界2；`spin_entry_ratio_limit=0`仅关闭竞争比例过滤，原生队头资格及CPU/单锁热度仍生效。
单锁热度独立保持每512次记录检查，不随CPU采样间隔变化。

当前 live 入口为 [tclock_compare/run.py](../tclock_compare/run.py)，说明见
[直接 API 对照](../tclock_compare/README.md)。本目录不再提供旧 hook 扫描、
双 ABI 对照、dispatch-floor 或 live perf 入口。

| 文件 | 当前用途 |
| --- | --- |
| `client.c` | 全worker预热、绑核、统一起跑、固定/连续计时及状态校验 |
| `peak.py`、`test_peak.py` | 全worker活跃窗口选择、进度校验及对应检查 |
| `bench_runtime.py` | 计数、CPU 放置、来源/设备、排空与冻结输入 |
| `bench_session.py` | 直接运行器复用的准备、发布、测量和排空基础类 |
| `provider/prepare.py` | 独立源码副本及只读观察 patch，不修改普通 provider |
| `kernel_identity.py` | 检查指定内核源码、基线、构建和 live Build ID |
| `summarize.py`、`assembly.py`、`profile_summary.py` | 当前/已有记录的离线读取和汇总，不能证明当前实际执行 |
| `test_spin_cacheline.py`、`test_assembly.py` | 客户端、数据 oracle、观察层和离线证据的定向检查 |

`make -C bench/spin_cacheline test` 只在 guest 执行，不加载模块；默认 module
构建显式选择 Linux native。三后端所需模块及符号依赖由直接运行器分别构建。
直接运行器默认使用`--kd-provider-ubsan off`，向重新创建的私有provider构建传入
`UBSAN_SANITIZE=n`；显式`kernel`继承内核配置，普通provider构建保持原设置。
所选政策、ELF核验及分组口径见[直接API说明](../tclock_compare/README.md#准备与运行)。
[spin 实现](../../docs/design/spin_implementation.md)统一记录当前 TCLock/KD 流程、对象大小、分配位置、
跨 CPU 数据流及回收边界。[历史索引](results/HISTORY.md)保留阶段成绩与失败记录，
旧运行命令只能在匹配历史 checkout 中使用。

客户端和峰值选择共用于cacheline及`--workload rcuht`。固定/计时测量复用同一payload校验：
hash要求搬移、冲突、未命中总和等于完整操作数，并验证结构完整性；每256次发布的worker进度只用于选窗口。
最近hash计时支持及135场验证见[结果报告](../tclock_compare/results/20260927-hash-peak.md)。
