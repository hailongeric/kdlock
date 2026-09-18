# TCLock 原生委托后端

这个独立实验使用完整 TCLock spinlock 执行路径，经现有 `kdclobber1` 普通 spin
hook 接入同一个 `spin_cacheline` 工作负载。锁字、队列、pending、shadow 栈、
六个 callee-saved 寄存器保存、物理 RSP 切换及 WWJUMP 均来自上游 TCLocks。
不使用 kdlock 的 shadow lock、JIT、翻译注册表、寄存器包或 daemon。

来源固定为 [TCLocks](https://github.com/rs3lab/TCLocks) 的提交
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`。`upstream/` 保留四个未修改文件，
`UPSTREAM.json` 记录哈希；`port.patch` 记录移植差异。保留原 GPL-2.0 及作者声明。
四个文件均来自该提交的 `src/kernel/rcuht/` 子树；差异文件用于审查，不是直接
应用到另一内核的安装补丁。

## 移植边界

- 采用上游内核版的纯轮询路径；不启用 rcuht 的 `KERNEL_SYNCSTRESS` 分支，
  该分支会在 per-CPU shadow 栈上调用 schedule。普通入口由接口层管理 preemption。
- 保留 WWJUMP、NUMA 队列选择和六条 cacheline 预取。批次上限为上游内核默认
  1024，与当前 kdlock 一致；上游 rcuht 自定义的 262144 不用于本轮。
- 将 C 内联切栈汇编移至 `context.S`，保持六寄存器顺序和原生 CALL 续点。
  普通 C 调用可能破坏参数，故入口在 R12 保存锁地址。保留当前内核的 frame
  pointer/缓解配置及 return thunk；自定义切栈不承诺完整栈展开。
  本轮 `W=1` 构建成功但仍有 objtool 栈/帧指针告警，原始构建日志保留。
- 增加分配失败回收和 Linux 6.1 类型适配；完成通知明确使用 release store。
  两个只读 per-CPU 计数分别记录抵达代理 unlock 与离开借用栈后的完成发布，
  排空后两者须相等。`quiescent` 核对锁字及所有 CPU 的队列/上下文状态。

`provider.c` 只接管 `target_lock` 指定的普通 spinlock，其他锁调用原生实现。
这是可恢复 benchmark 的独立后端，不是任意临界区的通用透明替换：本轮负载只
访问全局计数器，没有 task/per-CPU 数据、嵌套锁、服务调用或中途调度。
原版 TCLock 的完整慢路径保留在 `komb.c`，不据本轮单锁结果声称其他场景已验证。

所有构建和运行遵循 [操作手册](../docs/AGENTS.md)，只在 recovery guest。
模块互斥安装现有 spin hook，不改内核；必须保留 source workload，直到客户端
全部退出、`quiescent=1`、delegated/completed 相等，再卸载后端，最后卸载 workload。
该已知调用者边界不是通用 hook 热卸载保证。不得强制卸载。

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
[context.S](context.S) 保存续点、切栈，离开借用栈后才能 release 发布完成；
直接替换为原生 unlock 会绕过这套协议。所谓“其他 CPU 抢锁”只允许按协议
竞争并在条件满足后获取，不表示可以强行夺走仍由执行者持有的锁。

因此保留 API 的前提是同一目标锁的所有访问入口都统一到兼容协议。当前
[provider.c](provider.c) 只接管目标普通 spin 入口；它没有给这把目标锁提供
未修改原生调用者、绕过 hook 的调用、IRQ/BH/irqsave 或 trylock 的混用保证。
三方 benchmark 在不同会话中切换后端，不是这些调用者同时竞争同一把锁的测试。
切换原生栈也不会自动切换 Linux `current`、GS 或 per-CPU 身份；前述全局计数器
负载的通过结果不扩大为任意临界区的透明替换保证。

kdlock 的选择不同：原生参与者只访问 Linux 锁 **L**，代理队列使用私有字 **S**，
实际执行者必须获取 L 才能访问正文。普通代理批次可以一直持有 L，而不逐请求
重新获取它。L/S 带来的部分成本用于原生互操作；若要改成 TCLock 的单锁字，
必须统一该锁所有参与者的协议，或另行实现并验证互操作层，不能只删掉 L。
所有权与生命周期规则统一见 [DESIGN 4.1](../docs/DESIGN.md#41-native-lock-and-private-queue)，
性能收益及抵消因素见[执行路径对照](../bench/spin_cacheline/EXECUTION_PATHS.md#tclock-cost-comparison)。
本节是源码协议审查，没有新增混用测试，也不宣称不支持的混用方式已经验证。

## 文件与验证入口

| 文件 | 用途 |
| --- | --- |
| `komb.c` | 上游排队、combiner、WWJUMP、unlock 和 shadow 栈管理 |
| `context.S` | 六寄存器保存/恢复和物理栈切换 |
| `provider.c` / `compat.h` | 实验 hook、目标锁身份、preemption 与只读计数 |
| `upstream/` / `UPSTREAM.json` / `port.patch` | 不变来源及可审核移植差异 |

真实汇编的基础验证为
[`tests/unit/spin/test_tclock_context.py`](../tests/unit/spin/test_tclock_context.py)。
三方运行方法、实际执行结果和性能解释维护在
[`bench/tclock_compare/`](../bench/tclock_compare/README.md)。
已完成的[三方实测](../bench/tclock_compare/results/20260918-native-stack.md)覆盖
180 场稳态会话；保存/恢复对照、实际代理比例、独立采样及 kdlock 并发冷晋升
失败均在该页记录。真实汇编单元验证六个寄存器、RSP 和 lock/unlock 续点，
不能据此宣称任意内核栈展开或复杂临界区已通过。
与 kdlock 的入口、L/S 协议、逐请求处理及收益抵消见
[执行路径对照](../bench/spin_cacheline/EXECUTION_PATHS.md#tclock-cost-comparison)。
