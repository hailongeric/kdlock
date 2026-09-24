# Benchmarks

当前性能入口是[三后端直接API对照](tclock_compare/README.md)：Linux原生、TCLock和当前KD。
KD按CPU热值分流获取、统一generic clobber解锁。按用户要求，当前工作候选把采样与比例判断统一到
512次MCS边界，复用原MCS计数，只保存16字节的两个前次计数；接受近似统计，不修正IRQ交错。
adaptive默认比较100% MCS/获取比例，移除两低确认、原生冷却和近期热度保留。
spin单锁达到512次时检查12.5亿TSC窗口；mutex保持第1025次/25亿，CPU窗口仍为400亿。
动态热表布局和busy保护保持，小型pinned封装内联。
诊断槽采用128字节区域隔离，新增4KiB共享存储，局部修复已独立提交。
简化候选的42场`simple512-fixed`正确排空，但性能保护失败，作为EXPERIMENTAL检查点保留；`b83f551`及两个补充后继实验均保留为失败历史，
队列等待改动已撤回。当前不能宣称1/2/8/16/20线程性能保护完成；
进度和失败证据见[本轮报告](tclock_compare/results/20260924-contention-ratio.md)。
完整策略见[执行流](../docs/JIT_EXECUTION.md#21-热度与角色)，运行参数见[直接API入口](tclock_compare/README.md)。

历史[MCS8/CPU400万完整三轮](tclock_compare/results/20260923-mcs8-cpu4m.md)完成168/168场、
12960万次操作并排空；基础/定向单元3组和23项错误变体通过。adaptive在c1/c16的
8线程中位数为4.072/3.978，20线程为5.450/5.179 Mops/s；相比上一批默认历史中位数
分别提升7.89%/5.84%和2.98%/2.04%。该批3/4线程仍落后，单线程未一致改善；完整波动见报告。
这些是旧参数组合的成绩，不代表当前比例准入配置。

此前[adaptive 窗口与采样间隔诊断](tclock_compare/results/20260923-adaptive-windows.md)
覆盖单锁窗口、CPU窗口、MCS间隔的6个独立候选及1个组合，各完整配置三轮。
间隔调整改善了部分8线程成绩，过紧窗口损害20线程；该轮结束时恢复当时默认。
用户随后指定当时的MCS8/CPU400万组合，不能用此前两个单参数候选推定组合收益。
此前[单锁计数32/128/1024诊断](tclock_compare/results/20260923-adaptive-threshold-sweep.md)也未保留候选。
这些KD参数诊断不替代下面的三后端矩阵。

此前MCS1/CPU400亿的[完整三轮矩阵](tclock_compare/results/20260923-spin-default-heat-full3.md)完成168/168场、
12960万次操作并排空，包含现有batch元数据和continuation布局优化。
20线程KD observe中位数c1/c16为5.324/5.051 Mops/s；两模式20线程spread均低于0.8%。
3/4线程仍慢于Linux/TCLock，低线程异常快样本和全部三轮结果均保留。
输入为`39b0e7c`加冻结工作树修改，不能把组合版本收益单独归因于某一改动。

[性能调查与布局对照](tclock_compare/results/20260923-spin-single-hot-balance.md)保留失败候选、
单线程长批次对照及因果限制；[昨日恢复报告](tclock_compare/results/20260922-performance-recovery.md)
保留20线程5.197/4.809的历史参照与PMU版本澄清。

运行器默认每配置3轮、每线程100000次。Linux/TCLock每配置每轮各跑一次，KD observe/adaptive分别保存；
正式比值使用有效最大吞吐及同场ns/op，同时展示min/median/max/spread，不删除快慢样本。
`--spin-contention-pct`默认100，0仅关闭比例；汇总同时区分
`cpu_heat_policy=mcs_entry_ratio512_simple`和门槛值；旧`mcs_entry_ratio512_batch128`、
`mcs_entry_ratio512_confirm2`、`mcs_entry_ratio512`等候选单独保留，不能合并取优。
可按直接API入口说明用`taskset -c 0-19`固定准备阶段的CPU集合；worker仍按配置绑核，
所有选定worker CPU必须包含在允许集合中。`environment.json`保存`runner_affinity`。
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
