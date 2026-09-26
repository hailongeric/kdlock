# Benchmarks

当前入口是[三后端直接API对照](tclock_compare/README.md)：Linux原生、TCLock和KD adaptive。
KD使用per-CPU近似竞争统计和原生队头的有界前缀检查；完整策略统一见
[执行流](../docs/JIT_EXECUTION.md#21-热度与角色)，不在测量文档重复参数历史。

## 当前结果与口径

- [最新c1预取/诊断/CPU热值优化](tclock_compare/results/20260926-prefetch-unlock.md)：
  77eb9a2、十四线程点三方126场及32线程功能；保留三轮分布、性能缺口和候选回退。
- [前版c1 NUMA-on优化](tclock_compare/results/20260926-numa-followup.md)：
  d439df8、十四线程点三后端各三轮126场；六后继准入、链接/计时精简与匹配32线程功能验证。
- [首轮c1 NUMA与有界批次](tclock_compare/results/20260926-numa.md)：
  1–8/12/16/20/24/28/32线程、三后端各三轮126场；含预取候选、冗余状态清理和性能缺口。
- [前版1/8 cacheline复测](tclock_compare/results/20260925-c1-c8-warmed-peak.md)：
  1/2/3/4/8/16/20线程、三后端各三轮，126场有效并排空。
- [优化与c1完整线程矩阵](tclock_compare/results/20260924-warmed-peak.md)：
  包含1–8/16/20线程90场、匹配功能验证、保留改动和撤回候选。
- [历史索引](tclock_compare/results/HISTORY.md)：旧频率、observe模式、采样策略及固定迭代报告，
  按固定Git版本追溯，不能混为当前结果。

当前比较使用固定2.5GHz、全部worker各48000次预热，连续测量2秒，
取最高300ms全worker活跃窗口，同时保留整段吞吐。每配置三轮，报告min/median/max/spread；
后端比值使用最高有效峰值及同场ns/op，不删除快慢样本。
运行前后核对频率及CPU放置，保留固定设置。CLI无计时参数时仍是固定迭代模式，
正式峰值运行须显式传入`--duration-ms 2000 --peak-window-ms 300`。

## 入口

| 入口 | 用途 |
| --- | --- |
| [tclock_compare](tclock_compare/README.md) | 准备、CLI、cacheline/RCUHT、功能检查及结果解释 |
| [spin_cacheline](spin_cacheline/README.md) | 共用客户端、观察层、峰值计算与离线汇总 |
| [执行路径](spin_cacheline/EXECUTION_PATHS.md) | TCLock/KD对象、跨CPU数据流及生命周期 |
| [早期历史](spin_cacheline/results/HISTORY.md) | 9月15日至21日的冻结版本 |

所有构建和测量在recovery guest执行，环境及排空遵循[AGENTS](../docs/AGENTS.md)。
运行器内置业务、IRQ/preempt、实际JIT和排空检查；单元与独立功能检查按改动选择，
不作为性能测试的固定前置。性能通过不代表全量功能通过，后续任务见
[性能计划](../docs/PERFORMANCE_PLAN.md)。
