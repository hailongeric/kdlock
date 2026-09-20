# 2026-09-20：恢复上游 C 内联换栈，移除额外执行计数

按用户要求，TCLock 的两处换栈实现恢复为上游 C 内联汇编，删除新增的
`tc_delegated/tc_completed/tc_batches`。六场 smoke 和 Linux/TCLock 正式
**50/50 场全部通过负载正确性及排空检查**；正式完成 49000000 次操作。
四线程为 Linux 的 **0.887×**，8/16/20 线程分别为 **1.505× / 1.612× / 1.571×**。

本轮没有运行期执行计数：代理次数和占比为 `null`，状态为 `UNMEASURED`。
不能把本轮的数据正确性通过写成逐场实际代理次数验收通过。

## 实现及上游一致性

- [komb.c](../../../tclock_backend/komb.c) 恢复上游
  `komb_spin_lock_slowpath()` 的 C 内联汇编；helper 恢复为 `get_komb_node()`。
  [combiner.c](../../../tclock_backend/combiner.c) 使用上游
  `komb_context_switch()` 的 C 内联汇编，替代已删除的 `context.S`。
  两个函数块与固定提交 `bbfb9f00a12af51dff6ca291cb9829a82960c2ef` 逐行相同，
  仅忽略空白差异。外部模块的头文件、初始化和类型适配仍存在。
- 删除三个额外 per-CPU 变量的定义、声明、热路径增量和 sysfs 参数；
  完成发布恢复上游 `WRITE_ONCE(lock->locked_completed, 1)`。
  保留原版用于限制批处理的 `counter_val` 等协议字段。
- 计时外仍检查锁字、节点占用和 shadow 上下文是否排空；负载仍验证全部
  迭代、哈希表结构、结果分类、IRQ/preempt 状态。运行器拒绝意外加载仍带
  旧计数参数或符号的后端，不把未知代理量伪装成零。
- 沿用上一轮 IRQ 检查关闭、模块 UBSAN 关闭、批次参数 1024、纯轮询等待及
  锁外 `cond_resched()`/四组乘加；没有调整内核、哈希表正文或 kdlock 准入。

**C 源码对齐不等于整个生成二进制与 GCC 9/原内核相同。** 当前仍使用 GCC 11.4
和 `6.1.159-kdclobber2`。模块 ELF 的慢路径包含两处上游手写 `retq`；
`komb_context_switch()` 的 C 返回仍由当前编译配置生成 `__x86_return_thunk`。
慢路径手写返回之后还可见编译器生成的未执行返回尾部，不能把它算作每次额外
执行的返回。内核配置未修改，现有 objtool 换栈告警和新增 naked-return 告警
保留在构建日志中；没有宣称自定义换栈支持完整内核栈展开。

## 验证 C 内联汇编的续点

原写法有编译器看不到的 CALL/RSP 操作，不能只靠源码相同判定正确。
[加载前审核](../context_audit.py) 检查实际 ELF：

- context switch 的六寄存器保存、两个 RSP 操作和反序恢复必须符合约定；
- 慢路径开头不能插入破坏续点的额外栈序言，两处内联返回均先恢复六寄存器；
- 隐式 CALL 的两个 helper 在当前生成代码中只改变 RAX/flags，保留 RDI 锁参数；
- 模块没有新增统计计数符号，也没有 UBSAN handler 引用。

[续点测试](../../../tests/unit/spin/test_tclock_context.py) 编译实际生产函数块，
验证 128 次换栈、64 次获取返回和 64 次代理 unlock 返回，六寄存器及 RSP 正确。
这证明受测续点机制，不等于覆盖所有嵌套/乱序解锁或证明每场实际代理比例。

初版夹具把整个用户态程序都按内核 8 字节栈约定编译，所有续点断言执行后，
在末尾 libc 输出处段错误；分开编译时又补齐了内联函数立即数约束所需的
非 PIE 设置。最终仅生产函数使用内核栈约定，用户态夹具保留 libc 所需的
16 字节对齐，测试通过。失败诊断保留，期间没有加载内核模块；没有为适应
夹具修改这两个上游函数体。

## 五轮中位数

Mops/s 越大越好。前轮为已关闭 IRQ/模块 UBSAN、仍使用独立汇编和计数的版本。

| 线程 | Linux Mops/s | TCLock Mops/s | 本轮 TCLock/Linux | 前轮 TCLock/Linux |
| --- | --- | --- | --- | --- |
| 1 | 6.787 | 6.757 | 0.996× | 0.957× |
| 4 | 2.796 | 2.480 | 0.887× | 0.842× |
| 8 | 2.964 | 4.459 | 1.505× | 1.422× |
| 16 | 3.103 | 5.002 | 1.612× | 1.567× |
| 20 | 3.261 | 5.125 | 1.571× | 1.583× |

四线程仍比 Linux 低 **11.3%**，Linux 五轮范围为 2.704–2.847，TCLock 为
2.435–2.566 Mops/s。20 线程分别为 3.089–3.281 和 5.055–5.259 Mops/s。

相对倍率变化不能全部归因于 C 内联汇编或计数移除。两项同时改变，没有同期
交替的旧/新二进制控制组；单线程连原生组都从上一轮 14.113 变为本轮
6.787 Mops/s，表明跨轮绝对数值受其他因素影响。四线程 TCLock 本身从
2.502 到 2.480 Mops/s，倍率变大也包含原生组吞吐变化。因此，本次结论是
**代码已进一步对齐、四线程退化仍在**，没有测得两项修改各自的独立加速率。
本轮不再给出平均批次长度，也不沿用旧批次计数作为当前原因证据。

## 配置、验证范围和证据

- 与前轮相同的单全局锁哈希表、CPU 0–19、1/4/8/16/20 线程；每线程
  100000 次、各五轮，交替排列后端。每场单线程 48000 次预热、静置两秒。
- 同一内核 Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，voluntary。
  IRQ 与 UBSAN 范围沿用[前轮设置](20260920-irq-ubsan.md)，内核原生锁内部
  的 UBSAN 仍保留；本轮没有复现论文的原工具链或物理 NUMA 环境。
- 基础两项 C 测试、生产内联汇编续点测试通过；五项直接运行器/验收检查通过，
  包括拒绝仍带计数的旧 provider、拒绝未排空状态和编译器额外序言。
- 六场 smoke 覆盖 Linux/TCLock 的 1/4/20 线程，共 500000 次计时操作；
  正式 50 场单独统计。最终工作线程退出，workload、TCLock、kdlock 模块均未加载。
- 没有重跑 kdlock 的已知动态链表 JIT 拒绝；没有新的 kdlock 性能成绩。
  未运行全量测试，未启用 mutex JIT，未提交 Git。

[正式记录](../../.tmp/tclock_inline/rcuht-inline-20260920-compare01/records.json)、
[正式汇总](../../.tmp/tclock_inline/rcuht-inline-20260920-compare01/summary.csv)、
[离线校验](../../.tmp/tclock_inline/comparison-audit.json)、
[上游函数一致性](../../.tmp/tclock_inline/source-audit.json)、
[实际模块续点审核](../../.tmp/tclock_inline/rcuht-inline-20260920-compare01/tclock-context-audit.json)。

[完整归档](../../.tmp/tclock_inline/rcuht-inline-20260920-all.tar.gz) 包含初始夹具
诊断、最终测试、smoke、正式运行的冻结源码/二进制、编译选项、反汇编和排空状态。
SHA256：`911e2599ec78f28450fa863b03d57df3897c0f0a4269d9c5f5f2b9fc47f78e5a`。
已离线核对 50 场、49000000 次操作、数据结果、全部冻结源码/二进制哈希和
未测量代理量的标记。归档中的失败夹具记录不属于内核场次，最终依据见
`rcuht-inline-20260920-validation/README.txt`。
