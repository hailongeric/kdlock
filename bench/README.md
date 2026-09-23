# Benchmarks

当前性能入口是[三后端直接API对照](tclock_compare/README.md)：Linux原生、TCLock和当前KD。
KD默认按CPU热值分流获取、统一generic clobber解锁，CPU热度只按实际MCS发布计数。

最新[adaptive 阈值诊断](tclock_compare/results/20260923-adaptive-threshold-sweep.md)
比较单锁计数32/128/1024及恢复32，各配置三轮。两个候选均未满足3/4线程改善且
8/20线程不降的保留条件，默认仍为32；这组KD参数诊断不替代下面的三后端矩阵。

最新[完整三轮矩阵](tclock_compare/results/20260923-spin-default-heat-full3.md)完成168/168场、
12960万次操作并排空，包含现有batch元数据和continuation布局优化。
20线程KD observe中位数c1/c16为5.324/5.051 Mops/s；两模式20线程spread均低于0.8%。
3/4线程仍慢于Linux/TCLock，低线程异常快样本和全部三轮结果均保留。
输入为`39b0e7c`加冻结工作树修改，不能把组合版本收益单独归因于某一改动。

[性能调查与布局对照](tclock_compare/results/20260923-spin-single-hot-balance.md)保留失败候选、
单线程长批次对照及因果限制；[昨日恢复报告](tclock_compare/results/20260922-performance-recovery.md)
保留20线程5.197/4.809的历史参照与PMU版本澄清。

运行器默认每配置3轮、每线程100000次。Linux/TCLock每配置每轮各跑一次，KD observe/adaptive分别保存；
正式比值使用有效最大吞吐及同场ns/op，同时展示min/median/max/spread，不删除快慢样本。
cacheline默认120场，完整1/2/3/4/8/16/20线程为168场；RCUHT默认60场。
功能模式显式使用`--repeats 1`，只记录正确性/JIT/排空，不输出性能比较。

| 入口 | 用途 |
| --- | --- |
| [tclock_compare](tclock_compare/README.md) | 当前运行方法、cacheline/RCUHT、observe/adaptive、结果口径和功能检查 |
| [spin_cacheline](spin_cacheline/README.md) | 共用客户端、provider观察层、生命周期及离线汇总 |
| [近期历史索引](tclock_compare/results/HISTORY.md) | 已移除的中间实验、固定Git原文、失败证据和归档哈希 |
| [早期历史索引](spin_cacheline/results/HISTORY.md) | 9月15日至21日的旧版本报告 |

所有构建和测量在recovery guest执行，环境及排空遵循[AGENTS](../docs/AGENTS.md)。
代码修改后可直接运行性能测试，运行器内置业务、IRQ/preempt、JIT和排空检查；
独立单元、SELFTEST及功能矩阵按改动选择，不作为固定前置步骤。
各报告分别记录实测与未测范围；后续工作见[性能计划](../docs/PERFORMANCE_PLAN.md)。
