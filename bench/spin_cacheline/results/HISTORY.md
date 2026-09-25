# Benchmark 早期历史索引（2026-09-15 至 09-21）

这些阶段报告的实现已经被后续版本替代。重复的操作命令与实现说明从当前目录
删除，保留本页的结果、证据身份及固定 Git 版本入口。当前路径见
[执行路径](../EXECUTION_PATHS.md)，最新三方基线及热度计数对照见 [当前结果](../../tclock_compare/README.md#本次结果)。

下列结果均为历史记录，**本次文档整理没有重跑实验**。旧扫描通常使用
“kdlock 最佳吞吐 / Linux 中位吞吐”，每臂两次；9月21日三方对照用五轮中位数，9月22日不同阶段采用单轮或两轮最大值。
当前默认三轮的口径见[运行指南](../../tclock_compare/README.md)。
不同统计口径、caller ABI、源码冻结和准备方式的成绩不能拼接成同环境比较。
原始 `/tmp` 归档在仓库之外，新 checkout 不自带这些文件；哈希是原报告记录，
本次未重新认证全部旧归档。Git 版本保存完整表格、失败记录和运行命令。

## 近期实验与当前结果

9月21日至23日的中间报告已合并到[近期历史索引](../../tclock_compare/results/HISTORY.md)，
包括热表实验、回退、MCS采样、冷调用壳及三轮运行器变更。每项保留固定Git原文、
测量输入身份和证据哈希；已删除旧命令不作为当前运行入口。
当前完整矩阵见[1/8 cacheline三方峰值复测](../../tclock_compare/results/20260925-c1-c8-warmed-peak.md)，
旧布局优化及限制见[历史性能调查](../../tclock_compare/results/HISTORY.md#20260923-spin-single-hot-balance)。

## 更早阶段

所有旧报告可从提交 `2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24` 查看，例如在仓库根目录执行：

```sh
git show 2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24:bench/spin_cacheline/results/20260917-wwjump.md
```

<a id="20260915-post-work"></a>

## 2026-09-15：锁外乘加基线

120 场；增加四组锁外乘加后的完整扫描，不能与此前无锁外计算的成绩直接比较。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260915-post-work.md)。
归档：`/tmp/spin-cacheline-best-post-work-evidence-20260915.tar.gz`。
SHA256：`39710cebd3a72eb287df3cd9f2ee044bce4ad57ca194fdfaac90c64ce69b9340`。

<a id="20260917-stackless"></a>

## 2026-09-17：查询与栈改动

120 场；多线程最佳吞吐 0.544–0.647 Mops/s，仍低于原生。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-stackless.md)。
归档：`/tmp/kdlock-spin-bench-host-20260917/guest.tar.gz`。
SHA256：`d4817cd14508fe904a39c7f2f19b4e5af4dbf216d6c4ae49ccc4adc033c5f499`。

<a id="20260917-frame-fast"></a>

## 2026-09-17：单锁 frame 精简

16 场；20 线程两点最佳吞吐 0.855/0.850 Mops/s；每臂仅两个样本。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-frame-fast.md)。
归档：`/tmp/kdlock-frame-fast-20260917/evidence.tar.gz`。
SHA256：`30029f2d256562e052d1d48738e0b1fe149cf02e51f2ac9e1b62e3650562fc71`。

<a id="20260917-waiter-packet"></a>

## 2026-09-17：waiter 包与 lease

16 场；20 线程两点最佳吞吐 1.029/0.951 Mops/s，4 线程两点下降 2.4%/1.7%。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-waiter-packet.md)。
归档：`/tmp/kdlock-waiter-packet-20260917/evidence.tar.gz`。
SHA256：`3f297ec5b52a09d61553836dcabbb133ed448b0351fc43a1f0abe74ca8623dc5`。

<a id="20260917-tclock-shared"></a>

## 2026-09-17：共享 request

16 场；20 线程两点均约 0.905 Mops/s，未测得整体提速；冻结在恢复 shadow 等待栈之前，尚无锁侧 WWJUMP。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-tclock-shared.md)。
归档：`/tmp/kdlock-tclock-jit-20260917/evidence.tar.gz`。
SHA256：`c668405de0ea788b12c653dea1a3c735cb7510d4a5ec46db1251bbca9efe1ced`。

<a id="20260917-current-spin"></a>

## 2026-09-17：shadow 等待与嵌套状态

120 场；8–20 线程最佳吞吐 0.880–0.940 Mops/s；单锁负载不能验证嵌套优化收益。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-current-spin.md)。
归档：`/tmp/kdlock-spin-current-20260917.NDIlms/evidence.tar.gz`。
SHA256：`f65bc552d854c1b755dfef83a8c0858e63da9c26738940d06152f526dda9980a`。

<a id="20260917-batch"></a>

## 2026-09-17：per-CPU 统计与批内复用

16 场；20 线程两点最佳吞吐 1.299/1.285 Mops/s；三项改动合并测量，无独立归因。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-batch.md)。
归档：`/tmp/kdlock-spin-batch-20260917/evidence.tar.gz`。
SHA256：`c11cb68aaedd98aee13657617e1059633b3874614f0b5a12086df52e8c2457c8`。

<a id="20260917-wwjump"></a>

## 2026-09-17：旧锁侧 WWJUMP

16 场；20 线程两点最佳吞吐 1.550/1.519 Mops/s，实际 WWJUMP 计数为正；当时的汇编 shell/C step 已被统一 C 循环替代。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-wwjump.md)。
归档：`/tmp/kdlock-wwjump-20260917/evidence.tar.gz`。
SHA256：`d753b9c1c4bd0fd79420438d5c44e8486597073578c49b9b234d950e40c01144`。

## 旧 README 中的阶段记录

这些阶段的运行命令也已从当前指南删除。结果与失败详情固定到整理前提交：

| 记录 | 原文 |
| --- | --- |
| <a id="source-organization"></a>2026-09-15 代码整理回归 | [冻结记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/bench/spin_cacheline/README.md#source-organization) |
| <a id="rerun-100k-no24"></a>十万次扫描与百万次批次故障 | [冻结记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/bench/spin_cacheline/README.md#rerun-100k-no24) |
| <a id="assembly-validation"></a>汇编按临界区去重验证 | [冻结记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/bench/spin_cacheline/README.md#assembly-validation) |

## 2026-09-18 至 09-21 阶段报告归档

以下 29 份旧报告从当前目录删除；完整正文、命令、首次失败、结果表及原始证据
路径保存在整理前 Git 版本。此处链接固定到 `175d73bcc2faaa5ee9f9ab28a20491680d834043`；
本地也可用 `git show <提交>:<路径>` 读取，无需联网或重新运行实验。
后续的完整矩阵、两级候选和直接哈希报告现归入
[近期历史索引](../../tclock_compare/results/HISTORY.md)，这些阶段不再标为当前实现。

| 历史报告 | 冻结版本 |
| --- | --- |
| 2026-09-19：Hotlock 批量采样对照 | [20260919-batched.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/hotlock_record/results/20260919-batched.md) |
| 2026-09-19：10240 次检查与本地热锁发现 | [20260919-local-discovery.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/hotlock_record/results/20260919-local-discovery.md) |
| 2026-09-20：CPU 本地哈希记录开销 | [20260920-local-hash.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/hotlock_record/results/20260920-local-hash.md) |
| 2026-09-18：caller-clobber v1 同内核四组对照 | [20260918-clobber-v1.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/spin_cacheline/results/20260918-clobber-v1.md) |
| 2026-09-18：后继请求预取地址前移 | [20260918-prefetch.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/spin_cacheline/results/20260918-prefetch.md) |
| 2026-09-18：共享 JIT 寄存器 backing 的定向对照 | [20260918-shared-reg-bank.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/spin_cacheline/results/20260918-shared-reg-bank.md) |
| 2026-09-18：spin 获取入口与原生缓存对照 | [20260918-spin-entry.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/spin_cacheline/results/20260918-spin-entry.md) |
| 2026-09-18：减少普通 spin 的状态访问 | [20260918-state-access.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/spin_cacheline/results/20260918-state-access.md) |
| 2026-09-18：统一 combiner 现场后的 spinlock 性能 | [20260918-unified-context.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/spin_cacheline/results/20260918-unified-context.md) |
| 2026-09-19：node 通知分行与 gate 数组隔离 | [20260919-cacheline-isolation.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/spin_cacheline/results/20260919-cacheline-isolation.md) |
| 2026-09-18：完整 TCLock 原生委托与 Linux/kdlock 对照 | [20260918-native-stack.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260918-native-stack.md) |
| 2026-09-19：直接 API 三方性能对比 | [20260919-direct-api.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260919-direct-api.md) |
| 2026-09-19：哈希表临界区对比 | [20260919-rcuht.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260919-rcuht.md) |
| 2026-09-19：状态访问优化后的 spinlock 三方复测 | [20260919-state-access.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260919-state-access.md) |
| 2026-09-19：TCLock 四线程退化分析 | [20260919-tclock-four-threads.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260919-tclock-four-threads.md) |
| 2026-09-19：1/4/8/16/20 线程三方对照与伪共享检查 | [20260919-thread-scaling.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260919-thread-scaling.md) |
| 2026-09-20：当前版本切回 cacheline 的三方性能对比 | [20260920-cacheline-current.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-cacheline-current.md) |
| 2026-09-20：continuation 交接后的三方性能测试 | [20260920-continuation.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-continuation.md) |
| 2026-09-20：恢复上游 C 内联换栈，移除额外执行计数 | [20260920-inline-no-counters.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-inline-no-counters.md) |
| 2026-09-20：对齐 RCUHT 的 IRQ 检查及模块 UBSAN 设置 | [20260920-irq-ubsan.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-irq-ubsan.md) |
| 2026-09-20：修复哈希表 JIT 拒绝并重测三种锁 | [20260920-kd-hash-jit.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-kd-hash-jit.md) |
| 2026-09-20：本地热锁哈希与稳定角色 | [20260920-local-hash.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-local-hash.md) |
| KD 不代理路径：从 CAS 争抢改为共用 MCS | [20260920-native-mcs.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-native-mcs.md) |
| 2026-09-20：删除调度请求检查与锁外调度点 | [20260920-no-resched.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-no-resched.md) |
| 2026-09-20：KD 单锁字阶段 | [20260920-singleword.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-singleword.md) |
| 2026-09-20：TCLock 与上游一致性核对 | [20260920-upstream-audit.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-upstream-audit.md) |
| 2026-09-21：四线程 ticket 路径优化 | [20260921-four-thread-ticket.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-four-thread-ticket.md) |
| 2026-09-21：代理准入移到 MCS 边界 | [20260921-mcs-admission.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-admission.md) |
| 2026-09-21：竞争性能回退调查与恢复 | [20260921-mcs-recovery.md](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-recovery.md) |

需保留的结论：MCS 准入/时间域实验发生高竞争退化，两个优化候选未恢复到旧版
95%，已回退到含 ticket 优化的入口路径；四线程 KD 与 TCLock 的差距仍存在。
旧 RCUHT 的 KD 准入失败后来修复，但不能把早期原生完成记成实际 JIT；
TCLock 换栈、IRQ/preempt 修复前的失败和修改前后配置均留在冻结报告。
历史 hook、双锁字、带额外计数及不同调度/插桩配置的成绩不能拼接比较。
当时的adaptive直接哈希改造没有显示整体性能提升；单锁矩阵未验证
多锁精确地址容量的收益。最新局限以当前结果报告和 [测试入口](../../../tests/README.md)为准。

2026-09-21 清理只移除旧内核可重建中间文件，所有 guest 原始测试/性能证据及
宿主归档均保留；没有因文档合并删除失败日志或更改证据哈希。
