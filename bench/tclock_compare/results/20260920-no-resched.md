# 2026-09-20：删除调度请求检查与锁外调度点

按用户要求删除 TCLock 的 `need_resched()` 批次截断和公共哈希表循环的
`cond_resched()`。Linux/TCLock 六场 smoke、四线程各五轮对比均通过正确性
及排空检查。四线程 TCLock 中位吞吐为 Linux 的 **0.898×**，仍低约 **10.2%**。

## 改动范围

- [komb.c](../../../tclock_backend/komb.c) 删除解锁时的 `need_resched()` 条件、
  旧 `KERNEL_SYNCSTRESS` 等待宏中的 `schedule()` 分支和相关未使用宏。
  等待保持纯轮询；代理批次按后继可用性、IRQ 节点和 1024 额度结束。
- [module.c](../../../workload_modules/spin_cacheline/module.c) 删除每轮锁外的
  `need_resched()`/`cond_resched()`；[hash_payload.h](../../../workload_modules/spin_cacheline/hash_payload.h)
  删除 `hash_resched` 参数。公共源码对三个后端一致，锁外四组乘加仍保留。
- 保留 layout ABI v2 的字段位置，`resched` 固定为 0；运行器拒绝仍报告
  `resched=1` 的旧模块，并增加该拒绝路径的验证。
- 沿用 C 内联汇编、无额外 per-CPU 执行计数、IRQ 检查关闭及模块 UBSAN 关闭。
  内核和正常的 preempt 配对未改；实际 workload 仍有 `preempt_schedule`
  静态调用接口，删除显式调度点不表示关闭内核调度。

固定提交的四份 `upstream/` 文件未修改，`port.patch` 已更新。
此次批次退出策略有意偏离上游，不能记为进一步恢复原版算法。

## 四线程五轮结果

相同哈希表参数，每线程 100000 次，CPU 0–3，交替后端顺序。每场单线程
48000 次预热、静置两秒；表中为五轮中位数。

| 设置 | Linux Mops/s | TCLock Mops/s | TCLock/Linux |
| --- | --- | --- | --- |
| 前轮：保留调度检查与调度点 | 2.796 | 2.480 | 0.887× |
| 本轮：删除两处代码 | 2.751 | 2.469 | 0.898× |

本轮 Linux 为 363.46 ns/op，TCLock 为 404.96 ns/op；五轮吞吐范围分别为
2.729–3.238 和 2.442–2.602 Mops/s。正式 10/10 场完成 4000000 次操作。

前轮数据来自[同日 C 内联、无额外计数实验](20260920-inline-no-counters.md)，
本次没有同期交替的旧/新二进制控制组。倍率的小幅变化不能当作确定加速：
TCLock 绝对吞吐基本持平，四线程退化仍在。也没有批长或实际代理比例数据，
不能据此断言批次没有变长，或将剩余差距归于某个已测出的单一原因。

## 验证与证据

- 所有构建和运行均在 recovery guest，内核 `6.1.159-kdclobber2`，Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，动态抢占为 voluntary。
- 基础两项 C 测试和实际内联汇编续点测试通过；直接运行器六项检查通过。
- Linux/TCLock 的 1/4/20 线程 smoke 共六场、500000 次计时操作通过。
  这些短样例仅作功能验证，不代替正式五轮性能测量。
- 实际 ELF 没有 `cond_resched`、显式 `schedule` 或 UBSAN handler 引用，
  workload 没有 `hash_resched` 参数符号；TCLock 六寄存器/续点审核通过。
  构建保留原有 objtool 换栈告警，未宣称完整栈展开支持。
- 全部场次验证操作分类、哈希表结构、IRQ/preempt 状态及排空；内核日志
  未出现故障。最终 worker 退出、测试模块卸载。代理量继续标为 `UNMEASURED`。
- 未重跑 kdlock 已知的动态链表 JIT 拒绝，没有新的 kdlock 性能成绩；
  未跑全量测试，未启用 mutex JIT，未提交 Git。工作树基于
  `b4b16ca09d4b2833196b265e93bac934583fa3ef`，具体输入以冻结哈希为准。

[正式汇总](../../.tmp/tclock_no_resched/rcuht-no-resched-20260920-four01/summary.csv)、
[逐场记录](../../.tmp/tclock_no_resched/rcuht-no-resched-20260920-four01/records.json)、
[离线核对](../../.tmp/tclock_no_resched/comparison-audit.json)、
[完整归档](../../.tmp/tclock_no_resched/rcuht-no-resched-20260920-all.tar.gz)。
已核对全部冻结源码和二进制哈希。归档 SHA256：
`fe593b09e3ba6e2bc0bb0ec3051287eac426d626f5d133739a26540b987ddb28`。
