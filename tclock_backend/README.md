# TCLock 原生委托后端

当前实验使用 TCLock spinlock 的 Linux 6.1 移植版，`spin_cacheline` 直接调用导出的
`komb_spin_lock/unlock`，调用者配对管理抢占。统一 hook 安装/撤销已经暂时注释。锁字、队列、pending、shadow 栈、
六个 callee-saved 寄存器保存、物理 RSP 切换及 WWJUMP 机制来自上游 TCLocks。
编译分支、换栈汇编、计数和测试环境存在差异，不等同于上游 RCUHT 原样构建。
不使用 kdlock 的 shadow lock、JIT、翻译注册表、寄存器包或 daemon。

来源固定为 [TCLocks](https://github.com/rs3lab/TCLocks) 的提交
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`。`upstream/` 保留四个未修改文件，
`UPSTREAM.json` 记录哈希；`port.patch` 记录移植差异。保留原 GPL-2.0 及作者声明。
四个文件均来自该提交的 `src/kernel/rcuht/` 子树；差异文件用于审查，不是直接
应用到另一内核的安装补丁。

## 移植边界

- 等待节点采用纯轮询，已删除旧 `KERNEL_SYNCSTRESS` 等待宏中的调度分支。
  普通入口由接口层管理 preemption。
- 2026-09-20 按用户选择对齐 RCUHT 的检查设置：不定义 `ENABLE_IRQS_CHECK`，
  并以 `UBSAN_SANITIZE := n` 构建本模块。仅用于 IRQ 开启的 task 上下文单锁
  样例，不提供 IRQ/嵌套锁入口保证。三种 direct workload 同样关闭 UBSAN；
  运行内核和 Linux 原生锁内部仍保持原配置。
- 保留 WWJUMP、NUMA 队列选择和六条 cacheline 预取。批次上限为上游内核默认
  1024，与当前 kdlock 一致；上游 rcuht 自定义的 262144 不用于本轮。
- 随后按用户要求删除 `need_resched()` 批次截断条件，并删除公共哈希表循环的
  `cond_resched()` 调度点和开关。代理批次仍按后继可用性、IRQ 节点及额度结束。
  这是实验策略变更，与上游原有批次退出条件存在差异。
- 2026-09-20 后续按用户要求恢复上游 C 内联汇编：`komb.c` 内的慢路径与
  `combiner.c` 内的 context switch 保持原六寄存器顺序、RSP 交接和 CALL 续点。
  不再构建独立 `context.S`。加载前检查实际机器码没有破坏续点的额外栈序言，
  隐式调用的两个 helper 只改写 RAX/flags，保留锁参数。
  慢路径恢复上游手写 `retq`；context switch 的 C 返回仍由当前内核编译选项
  生成 return thunk。未修改内核配置；objtool 的换栈及 naked-return 告警保留。
- 增加分配失败回收和 Linux 6.1 类型适配；完成发布恢复上游 `WRITE_ONCE`。
  删除额外的 `tc_delegated/tc_completed/tc_batches` 存储、更新及 sysfs 参数。
  上游批次控制字段仍保留。`quiescent` 在计时外核对锁字及所有 CPU 的队列/
  上下文状态；本轮只验证负载正确性与排空，不测量实际代理次数或比例。

`provider.c` 只初始化/释放 TCLock 上下文和提供排空状态。`target_lock` 在依赖
后端的样例加载后、worker 启动前绑定，只供诊断读取；不在 lock/unlock 路径筛选。
这是可恢复 benchmark 的独立后端，不是任意临界区的通用透明替换：已测正文为
全局 cacheline 更新及哈希表操作/调用者栈统计，没有 task/per-CPU 身份访问、
嵌套锁、服务调用或临界区内调度。`komb.c` 保留上游主委托流程，但选择了不同于
RCUHT 的编译分支；不据单锁结果声称其他场景已验证。源码、冻结 ELF 和配置的
逐项核对见 [2026-09-20 上游一致性审查](../bench/tclock_compare/results/20260920-upstream-audit.md)。

所有构建和运行遵循 [操作手册](../docs/AGENTS.md)，只在 recovery guest。
不安装 spin hook、不改内核；先加载后端，再加载直接依赖它的 workload。客户端
全部退出、`quiescent=1` 后，清除 `target_lock`，先卸载
workload 再卸载后端。不得强制卸载。

## 与 Linux 原生 spinlock 的协议兼容边界

这里比较当前 x86 实验中的 Linux qspinlock 与本目录固定版本的 TCLock。
**调用接口可以保持 `spin_lock()/spin_unlock()`，但同一把锁不能混用未修改的
Linux qspinlock 与 TCLock 两套后端。** 当前目标锁必须在整个会话内由 TCLock
独占管理，其他独立锁仍可使用 Linux 实现。

| 环节 | Linux qspinlock | TCLock |
| --- | --- | --- |
| 无竞争/轻竞争 | CAS 获取，或走 pending 路径 | 保留类似 CAS/pending 路径，成功后自己执行正文 |
| 排队与执行 | MCS 类队列组织获取顺序，每个调用者在自己的 CPU 上执行正文 | 队列节点另带 RSP、完成状态；combiner 可切到等待者栈代执行正文 |
| unlock 与交接 | 释放物理锁后，后继才可获取；队首资格交接本身不授权正文执行 | 代理 unlock 保存续点，可直接切向下一 waiter，批内保持物理互斥 |
| 等待结束 | 获取锁后执行自己的正文 | 被代理者在完成发布后，从自己的 unlock 返回链继续，不能重放正文 |
| 现场 | 锁协议不另建可供其他 CPU 恢复的现场 | 保存六个 callee-saved、RSP，复用原生栈上的 CALL 返回地址，无完整 `pt_regs` 包 |

锁字布局相似不等于队列兼容。两者都把 CPU/节点编号编码进 tail，但
[Linux `decode_tail()`](https://github.com/torvalds/linux/blob/v6.1/kernel/locking/qspinlock.c)
访问该 CPU 的 `qnodes[idx].mcs`，本目录 [komb.c](komb.c) 的同名函数访问
`komb_nodes[idx]`。若 TCLock 等待者已经发布 tail，原生调用者排队时会将它
解码到另一套节点，并把后继链接到错误位置；反向混入同样不成立。
无竞争 CAS 或个别 pending 交接可能表面正常，不能据此证明慢路径互操作。

TCLock 还使用 combiner、IRQ 和乱序解锁状态。代理 unlock 必须配合
[combiner.c](combiner.c) 保存续点、切栈，离开借用栈后才能发布完成；
直接替换为原生 unlock 会绕过这套协议。所谓“其他 CPU 抢锁”只允许按协议
竞争并在条件满足后获取，不表示可以强行夺走仍由执行者持有的锁。

因此保留 API 的前提是同一目标锁的所有访问入口都统一到兼容协议。当前
[provider.c](provider.c) 的旧 hook 路径已暂停，当前样例统一直接调用 TCLock；它没有给这把目标锁提供
未修改原生调用者、绕过 hook 的调用、IRQ/BH/irqsave 或 trylock 的混用保证。
三方 benchmark 在不同会话中切换后端，不是这些调用者同时竞争同一把锁的测试。
切换原生栈也不会自动切换 Linux `current`、GS 或 per-CPU 身份；前述单锁
负载的通过结果不扩大为任意临界区的透明替换保证。

kdlock 的选择不同：原生参与者只访问 Linux 锁 **L**，代理队列使用私有字 **S**，
实际执行者必须获取 L 才能访问正文。普通代理批次可以一直持有 L，而不逐请求
重新获取它。L/S 带来的部分成本用于原生互操作；若要改成 TCLock 的单锁字，
必须统一该锁所有参与者的协议，或另行实现并验证互操作层，不能只删掉 L。
所有权与生命周期规则统一见 [DESIGN 4.1](../docs/design/locking.md#41-native-lock-and-private-queue)，
性能收益及抵消因素见[执行路径对照](../bench/spin_cacheline/EXECUTION_PATHS.md#tclock-cost-comparison)。
本节是源码协议审查，没有新增混用测试，也不宣称不支持的混用方式已经验证。

## 文件与验证入口

| 文件 | 用途 |
| --- | --- |
| `komb.c` | 上游排队、combiner、WWJUMP、unlock 和 shadow 栈管理 |
| `combiner.c` | 上游 C 内联汇编的六寄存器保存/恢复和物理栈切换 |
| `provider.c` / `compat.h` | 直接 API 后端生命周期、计时外目标绑定与排空状态 |
| `upstream/` / `UPSTREAM.json` / `port.patch` | 不变来源及可审核移植差异 |

真实汇编的基础验证为
[`tests/unit/spin/test_tclock_context.py`](../tests/unit/spin/test_tclock_context.py)。
三方运行方法、实际执行结果和性能解释维护在
[`bench/tclock_compare/`](../bench/tclock_compare/README.md)。
当前 cacheline 成绩见 [9/20 三方重测](../bench/tclock_compare/results/20260920-cacheline-current.md)：
150/150 场通过，TCLock 二十线程 1/16 cacheline 吞吐为 4.992/3.341 Mops/s；
沿用 C 内联换栈、无显式调度点及无额外计数设置，代理量仍未测。
哈希表成绩见 [9/20 哈希表 JIT 修复与三方重测](../bench/tclock_compare/results/20260920-kd-hash-jit.md)：
三个后端统一调整摘链/计数顺序后，九场样例及正式 75/75 场通过正确性和排空
检查；TCLock 四/二十线程吞吐为 2.516/5.129 Mops/s，代理量仍未测。
此前 [删除调度检查和调度点](../bench/tclock_compare/results/20260920-no-resched.md)：
六场 smoke、四线程各五轮全部通过正确性及排空检查；四线程为 Linux 的 0.898×。
此前仍保留调度检查的 [C 内联汇编、无额外计数](../bench/tclock_compare/results/20260920-inline-no-counters.md)：
Linux/TCLock 正式 50/50 场通过数据及排空检查，代理量未测；没有新的 kdlock 性能成绩。
此前仍带执行计数的对照见 [IRQ/模块 UBSAN 对齐](../bench/tclock_compare/results/20260920-irq-ubsan.md)。
最近完整三方基线见 [9/19 五档线程复测](../bench/tclock_compare/results/20260919-thread-scaling.md)。
随后 kdlock 的 [node/gate 隔离修复](../bench/spin_cacheline/results/20260919-cacheline-isolation.md)
只重测旧/新 kdlock，没有重测 TCLock/Linux；此前长单线程成本仍见
[同日独立对照](../bench/tclock_compare/results/20260919-state-access.md#单线程长批次)。
[首次三方实测](../bench/tclock_compare/results/20260918-native-stack.md)保留两种 ABI
的 180 场稳态、独立采样和 kdlock 并发冷晋升失败；旧采样占比不是当前热点占比。真实汇编单元验证六个寄存器、RSP 和 lock/unlock 续点，
不能据此宣称任意内核栈展开或复杂临界区已通过。
与 kdlock 的入口、L/S 协议、逐请求处理及收益抵消见
[执行路径对照](../bench/spin_cacheline/EXECUTION_PATHS.md#tclock-cost-comparison)。
