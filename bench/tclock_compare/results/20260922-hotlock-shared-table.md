# 2026-09-22：spin/mutex 共用 per-CPU 热表

> 历史实验：本方案已回退。当前实现与后续性能验收见[回归处理](20260922-performance-recovery.md)；下文保留当时源码、口径与结果。

热表核心和通用外层的 kind 参数已删除。每个 CPU 只保留一张按完整锁地址匹配
的哈希表，spin/mutex API 名称保留，但不再区分统计类型。锁的实际互斥协议、
owner、ticket、continuation 和 ACK 生命周期不变。

## 共享范围

| 项目 | 合并前 | 合并后 |
| --- | --- | --- |
| 每 CPU 热表 | spin/mutex 各一张 | 共用一张 |
| 哈希桶 / 地址记录 | 每类256 / 256 | 两类合计256 / 256 |
| CPU 计数与时间窗口 | 两类分别累计 | 两类观测合计每1024次检查 |
| 同地址 count/hot | 分类型 | 两个接口共用同一记录 |
| 不同地址 | 完整地址匹配 | 完整地址匹配，碰撞不混淆 |
| entry/table 大小 | 24/6680 B | 24/6680 B |
| 每 CPU 对象大小 | 13376 B | 6720 B，64 B对齐 |

CPU 窗口仍为400亿TSC ticks；CPU热后才记录锁，单锁 count 大于1024时按25亿
TSC窗口刷新hot/时间。query只读。同地址的窗口/计数共享，不允许用热表推断
锁类型或混用互斥协议。两类共同消耗256条容量，满表未知地址保持原有原生回退。

保留上一阶段的无busy、无核心抢占检查：spin主入口复用已有pin，通用外层按需
保护CPU固定；中断下允许统计误差。新地址插入的有界槽预留/链接发布继续保留。
初始化只建立一个CPU时钟，排空日志删除type字段，按CPU和地址输出。

## 本轮验证

在现有未提交工作树上修改，保留此前改动；基准Git提交仍为1b2c320。
仅在recovery guest 6.1.159-kdclobber2构建和执行，确认恢复快照及内核基线，
没有重建guest内核或修改TCLock。普通与SELFTEST的W=1构建通过，保留原有
手写换栈objtool告警及UBSAN/栈保护/缓解配置。

基础两个C检查和hotlock sampling、spin preempt、direct unlock三个驱动5/5通过，
12种错误变异均被检测。新增/调整的生产采样测试验证：混合观测触发同一CPU批次，
同地址跨API共享count/hot，不同地址混合碰撞与共同容量，CPU之间仍隔离。
原有阈值、时间边界、满表保护、query、核心无抢占检查以及19条获取路由检查保留。

三个实际JIT功能会话使用 `--functional --backends kdlock --cachelines 1`
`--threads 4 --repeats 1 --iterations 100000`：

| 场景 | 完成数 | 实际 JIT 正文 | 排空 |
| --- | ---: | ---: | --- |
| nested-observe-on | 400000 | 389642 | 通过 |
| plain-adaptive-on | 400000 | 212509 | 通过 |
| plain-observe-on | 400000 | 198824 | 通过 |

共120万次操作，业务、IRQ/preempt恢复和排空通过，三个会话均有实际JIT正文。
另以独立SELFTEST ELF加载 `hotlock_lifetime_selftest=1 hotlock_mode=observe`
`hotlock_stats=1 mutex_jit=0`：混合spin/mutex观测填满同一表，真实持锁owner保留，
解锁后word=0；原生mutex等待从CPU1迁移到CPU2，balanced=1、ret=0，正常卸载。
排空时输出256条无type字段的热度记录。此探针不是mutex JIT正例。

普通和SELFTEST ELF/pahole均确认table=6680、cpu=6720、对齐64。每CPU对象的
分配请求比合并前少6656 B（约49.8%），不据此推算分配器实际驻留页数。
反汇编确认spin专用核心及clock/insert没有抢占引用，已有地址计数无busy CAS。

三个功能运行器、探针及最终审计均退出0；内核日志无BUG/Oops/WARNING/stall，
源码与冻结ELF哈希一致，最终guest空闲。未运行性能benchmark、PMU、全量unit、
mutex JIT、跨NUMA或强制native续跑矩阵；不声明吞吐提升。

## 证据

Guest：`/root/kdlock-evidence/hotshared-20260922/`，保存修改前文件、host.patch、
源码清单、单元/构建日志、普通和SELFTEST ELF/布局、三个功能会话、探针日志、
内核身份、恢复快照、反汇编和audit.json。

[完整归档](../../.tmp/hotshared_20260922/hotshared-20260922.tar.gz)，SHA256：
`54fd38c7f43f6cc107fce0ab169938767203765ae6acbe147fb5c74d6676a3ff`。
[宿主离线复核](../../.tmp/hotshared_20260922/offline-audit.json)。旧阶段结果见
[无busy核心](20260922-hotlock-core.md)，不能将其数据记作本次共享表测量。
