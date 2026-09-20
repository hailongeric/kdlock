# Benchmarks

所有构建与测量只在 recovery guest，环境及排空遵循 [AGENTS](../docs/AGENTS.md)。
当前入口按直接 API 使用独立 Linux、TCLock、KD 对象；旧透明 hook 和双 ABI
性能运行器已删除。冻结历史报告保留原版本与归档索引，不作为当前验收。

| 入口 | 用途 |
| --- | --- |
| [tclock_compare](tclock_compare/README.md) | 当前三后端直接调用、cacheline/RCUHT、observe/adaptive 和本地嵌套检查 |
| [hotlock_record](hotlock_record/README.md) | 旧/新采样器的独立组件对照 |
| [spin_cacheline](spin_cacheline/README.md) | 当前运行器共用的客户端、provider 观察层、生命周期和离线汇总/汇编读取 |

最新 [单锁字结果](tclock_compare/results/20260920-singleword.md)和
[本地哈希/策略结果](tclock_compare/results/20260920-local-hash.md)分阶段报告。
[历史索引](spin_cacheline/results/HISTORY.md)保留旧成绩；后续工作统一见
[PERFORMANCE_PLAN](../docs/PERFORMANCE_PLAN.md)。
