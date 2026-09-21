# Benchmarks

最新 [竞争回退调查](tclock_compare/results/20260921-mcs-recovery.md) 包含同期复现、采样、两个候选及回退验收；当前恢复入口准入和批量时钟，保留 ticket 优化。

所有构建与测量只在 recovery guest，环境及排空遵循 [AGENTS](../docs/AGENTS.md)。
当前入口按直接 API 使用独立 Linux、TCLock、KD 对象；旧透明 hook 和双 ABI
性能运行器已删除。冻结历史报告保留原版本与归档索引，不作为当前验收。

| 入口 | 用途 |
| --- | --- |
| [tclock_compare](tclock_compare/README.md) | 当前三后端直接调用、cacheline/RCUHT、observe/adaptive 和本地嵌套检查 |
| [hotlock_record](hotlock_record/README.md) | 旧/新采样器的独立组件对照 |
| [spin_cacheline](spin_cacheline/README.md) | 当前运行器共用的客户端、provider 观察层、生命周期和离线汇总/汇编读取 |

此前 [四线程 ticket 优化](tclock_compare/results/20260921-four-thread-ticket.md)
记录同期前后各 60 场对照，四线程 c1/c16 提升 9.4%/14.0%，仍低于 TCLock。
此前 [continuation 三方性能结果](tclock_compare/results/20260920-continuation.md)
记录提交 `644f231` 的完整矩阵；此前
[单锁字结果](tclock_compare/results/20260920-singleword.md)和
[本地哈希/策略结果](tclock_compare/results/20260920-local-hash.md)保留为历史阶段报告。
[历史索引](spin_cacheline/results/HISTORY.md)保留旧成绩；后续工作统一见
[PERFORMANCE_PLAN](../docs/PERFORMANCE_PLAN.md)。
