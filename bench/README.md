# Benchmarks

当前性能入口是[三后端直接API对照](tclock_compare/README.md)：Linux原生、TCLock和当前KD。
KD按CPU热值分流获取、统一generic clobber解锁。spin每次MCS发布以内联per-CPU计数累计，
每128次才进入受busy guard保护的采样器；adaptive以512次策略发布窗口检查MCS/获取尝试比例，默认100%。
初始乐观状态也须连续两个低窗口才关闭，随后8窗口保持原生；比例关闭保留近期单锁状态，重开时检查年龄。
当前候选将spin单锁改为第513次/12.5亿TSC窗口；mutex保持第1025次/25亿，CPU窗口仍为400亿。
GS INC/XADD计数及48字节静态per-CPU比例状态已恢复，字节相位候选被拒绝；动态热表布局和busy保护保持。
诊断槽采用128字节区域隔离，新增4KiB共享存储，局部修复已独立提交。
当前缩短spin批次的候选通过相关检查，42场KD adaptive全部正确排空，但高线程性能保护仍失败；
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
`--spin-contention-pct`默认100，0仅关闭比例及其冷却门槛；汇总同时区分
`cpu_heat_policy=mcs_entry_ratio512_batch128`和门槛值；旧MCS32的
`mcs_entry_ratio512_confirm2`及更早候选单独保留，不能合并取优。
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
