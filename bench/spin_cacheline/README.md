# Spin cacheline 共用组件

当前采用精确地址哈希热度统计，保留入口准入、顶层 pending 免 ticket 和 continuation 退休协议。
准入只保留adaptive；`spin_contention_pct=0`仅关闭竞争比例过滤，原生队头资格及CPU/单锁热度仍生效。

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
[执行路径](EXECUTION_PATHS.md)统一记录当前 TCLock/KD 流程、对象大小、分配位置、
跨 CPU 数据流及回收边界。[历史索引](results/HISTORY.md)保留阶段成绩与失败记录，
旧运行命令只能在匹配历史 checkout 中使用。
