# Benchmarks

[当前无候选哈希计数的同期对照](tclock_compare/results/20260921-hotlock-direct.md)：
120/120 场通过，1 亿次操作全部排空。默认 adaptive 四线程/二十线程近似持平；
单线程 c1 +4.86%、c16 −2.10%，未显示整体提升。此前
[两级候选版对照](tclock_compare/results/20260921-hotlock-twolevel.md)保留原版本限定。

[修改前提交完整三方重测](tclock_compare/results/20260921-current-benchmark.md)：
`175d73b`，150/150 场通过，保留全部样本及实际 JIT/排空检查。

此前 [竞争回退调查](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-recovery.md) 包含同期复现、采样、两个候选及回退验收；当前恢复入口准入和批量时钟，保留 ticket 优化。

所有构建与测量只在 recovery guest，环境及排空遵循 [AGENTS](../docs/AGENTS.md)。
当前入口按直接 API 使用独立 Linux、TCLock、KD 对象；旧透明 hook 和双 ABI
性能运行器已删除。冻结历史报告保留原版本与归档索引，不作为当前验收。

| 入口 | 用途 |
| --- | --- |
| [tclock_compare](tclock_compare/README.md) | 当前三后端直接调用、cacheline/RCUHT、observe/adaptive 和本地嵌套检查 |
| [hotlock_record](hotlock_record/README.md) | 旧/新采样器的独立组件对照 |
| [spin_cacheline](spin_cacheline/README.md) | 当前运行器共用的客户端、provider 观察层、生命周期和离线汇总/汇编读取 |

[历史索引](spin_cacheline/results/HISTORY.md)汇总旧阶段报告、回退及冻结证据入口，
详细说明从固定 Git 版本读取，避免旧命令与当前运行路径混用。
后续工作统一见 [PERFORMANCE_PLAN](../docs/PERFORMANCE_PLAN.md)。
