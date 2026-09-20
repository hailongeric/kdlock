# TCLock 与 KDLock 当前执行路径、对象和数据流

本文以 `e25c551` 及随后入口抢占配对修改的源码为准，描述直接调用 benchmark 的 **spin** 路径。
TCLock 指仓库中的外部模块适配版 `tclock_backend/`；KD 指显式 `kd_spinlock_t`
API，不是整个内核锁的替换。mutex 只涉及下述共享执行设施及独立热表，其互斥
协议见 [locking](../../docs/design/locking.md)，不能套用这里的 spin 流程。

三臂使用同一负载源码、分别编译为不同 ELF。完整操作包括获取、正文、释放、
锁外计算和循环，`ns/op` 不是单独获取锁的延迟。Linux 臂调用
`__raw_spin_lock/unlock`，使用独立 Linux 锁对象。

## 1. 阅读口径与构建差异

大小单位均为字节，指 x86_64 的 `sizeof` 或明确请求的分配长度，不含分配器
填充、vmalloc 页表/管理开销。“占用对象”通常是借用预分配槽，不代表临界区内
分配内存。内嵌对象已经计入外层大小，不能重复相加；64 字节地址对齐也不等于
对象大小为 64。C 局部对象可能被优化进寄存器或复用栈槽，不能把其 `sizeof`
之和当作函数最大栈深。

| 构建 | 当前启用项与边界 |
| --- | --- |
| TCLock backend | `NUMA_AWARE=1`、`WWJUMP=1`；`ENABLE_IRQS_CHECK` 关闭。当前对照限 task context、IRQ 开启的单锁调用者，不作为通用 IRQ/嵌套锁替代 |
| KD normal | `KDLOCK_SELFTEST`、`KDLOCK_NUMA` 默认关闭；NUMA 队列选择及探针是显式构建选项 |
| KD 策略 | `spin_delegate=0` 走原生自执行并跳过新请求的热度记录，默认 `1`。`hotlock_mode=adaptive` 默认按热度准入；`observe` 固定热度准入，仍受上下文/JIT 就绪/安全检查约束 |

对象尺寸于 2026-09-20 在 guest `6.1.159-kdclobber2` 用现有模块的 `pahole -s`
核对，未重新构建、加载模块或运行负载。两侧关键布局源码哈希一致；该次 KD ELF
为 normal 构建，NUMA/SELFTEST 的源码布局增量另列。

| 已读取的 ELF | SHA256 |
| --- | --- |
| `kernel_module/kdlock_km.ko` | `a351dbcca80ce8c53a6800df49dd417628c15c19bfd18e1dad585b5a59f0e8f1` |
| `tclock_backend/tclock_backend_km.ko` | `ad5f4baca2868ec13dddc17bab06203201bbe4a92ce1169ed3824cc50faf2393` |

## 2. 锁对象和公共负载

| 对象 | 大小与位置 | 创建与使用 |
| --- | --- | --- |
| KD `kd_spinlock_t` | 4；workload 模块静态 `sc_lock`，地址按 64 对齐 | 模块初始化清零；同一锁字承载 locked、pending、tail 及 combiner 仲裁 |
| TCLock `qspinlock` | 4；当前 workload 静态 `spinlock_t sc_lock` 的锁字，地址按 64 对齐 | backend 直接使用该对象，调用端管理抢占；当前内核无额外 debug lock 布局，不能推广到任意 `spinlock_t` 配置 |
| `sc_slot` | 64，含 8 字节计数器及填充；静态 `sc_data[16]` 共 1024 | workload 模块载入时存在；各路径更新所选 N 个槽的计数器，不是读写每条 cacheline 的全部 64 字节 |

锁对象不内嵌节点、request、frame 或热表。节点属于 CPU，执行记录属于请求，
翻译条目属于代码入口；同一代码入口可以服务不同锁地址。KD 没有 gate 映射、
独立 S、Linux L 二次获取或旧 spin 统一分发。
来源：[payload.h](../../workload_modules/spin_cacheline/payload.h)、
[调用壳](../../workload_modules/spin_cacheline/direct.h)。

## 3. TCLock：对象、栈切换和完成交接

### 3.1 对象在哪里创建

| 对象 | 大小/数量 | 存储与生命周期 |
| --- | --- | --- |
| `komb_node` | 120 × 4 = 480 / possible CPU | `komb.c` 静态 per-CPU 数组，模块存活期间保留。数组基址对齐，元素步长仍为 120，不是每个节点独占两个对齐 cacheline |
| `shadow_stack` 元数据 | 128 / possible CPU | 静态 per-CPU；含 `lock_addr[8]`、栈顶、当前/前一 waiter CPU、WWJUMP 计数及 NUMA 暂存链表 |
| shadow 栈内存 | 8192 / possible CPU | `komb_init()` 逐 CPU `vzalloc`；`ptr` 指向末端，初始 `local_shadow_stack_ptr=末端-8`；排空后 `komb_free()` 释放 |
| 保存的机器上下文 | 每次显式保存 6 个寄存器，共 48；另有 CALL 返回地址及 C 栈帧 | 写入已有任务栈或 shadow 栈；`rsp` 指向保存点。不分配 `pt_regs`、稳定 request 或 JIT frame |
| combiner 检查点 | 若干 C 局部变量，非独立堆对象 | `__komb_spin_lock_longjmp()` 执行栈保存旧 `rsp`、CPU、计数、next 及 NUMA 链表；实际栈帧大小由编译决定 |

节点的 `next/tail` 组织队列，`count` 管理占用，`socket_id/cpuid` 定位与选队，
`rsp` 保存真实栈续点，`lock/task_struct_ptr` 关联锁和逻辑调用者，
`completed/locked` 通知原 waiter。`irqs_disabled` 字段保留，但不会使已关闭的
IRQ 检查代码自动启用。
来源：[节点定义](../../tclock_backend/include/spinlock/komb.h)、
[队列与初始化](../../tclock_backend/komb.c)、
[上下文切换](../../tclock_backend/combiner.c)。

### 3.2 当前默认路径

1. 调用壳 `preempt_disable()` → `komb_spin_lock()`。先 CAS 获取锁字，失败后
   尝试 pending。成功均返回自己的正文，不占用排队节点、不换栈。
2. 排队进入 `komb_spin_lock_slowpath()`：RBP/RBX/R12–R15 压入原任务栈，
   保存 RSP 到本 CPU 节点，切到预分配 shadow 栈。当前普通可代理路径使用
   `komb_nodes[0]`，不能把“预留 4 个节点”理解为普通路径支持四槽任意嵌套。
3. 初始化节点、交换锁字 tail、向前驱 `next` 发布自己，在本地 `locked` 轮询。
   队首才等待共享锁字的 locked/pending 清除。
4. 队首独占时获取锁、归还节点占用，回原任务栈自行执行。有可代理后继时，
   队首保存检查点进入 combiner；节点计数可先归还，被暂停的栈和续点仍须保活。
5. `execute_cs()` 通过 `komb_context_switch()` 切到 waiter 的 `rsp`，从其
   lock 返回位置执行原始正文。原 waiter CPU 留在自己的 shadow 栈轮询；
   逻辑调用者与当前物理执行者不同。
6. 代理正文的 `komb_spin_unlock()` 将 unlock 续点保存回当前 waiter 的 `rsp`。
   WWJUMP 切到下一 waiter 的栈，或回 combiner 的 shadow 栈；NUMA 选择可暂存
   其他 socket 节点。批次由后继、可代理边界及预算决定，`komb_batch_size`
   默认 1024；没有恢复已删除的调度检查。
7. 离开借用栈后用 `completed/locked` 通知原 waiter。它恢复更新后的 `rsp`，
   从 unlock 续点返回，不再次执行正文。批次结束交接后继，combiner 自身仍回到
   自己的 lock 调用流程。普通持锁者 unlock release 清除 locked，调用壳最终
   `preempt_enable()`。

```text
waiter CPU                         combiner CPU
任务栈：保存 6 寄存器、RSP
切 CPU shadow 栈 → 发布 node ─────→ 读取 node->rsp
本地轮询 locked                    切入 waiter 任务栈，执行原正文
                                   unlock：保存新 rsp，离开该栈
恢复 node->rsp ← completed/locked ← 通知完成
从 unlock 后继续
```

源码保留 `ENABLE_IRQS_CHECK` 下的不可代理 MCS 分支：为嵌套/IRQ 等上下文选择
节点，不借出栈，队首获取后通知后继并自行执行，真正四槽耗尽才轮询锁字。
**当前 backend 没有编入该分支**。`lock_addr[8]` 和 OOO 标记也不等于当前单锁
对照已验证任意嵌套与乱序解锁。

## 4. KDLock：对象分层与创建位置

### 4.1 模块启动时预留的对象

| 对象 | 大小/数量 | 分配点、用途和回收 |
| --- | --- | --- |
| `kd_spin_node` | 128 × 4 = 512 / CPU | `spin/state.inc` 静态 per-CPU 数组；每节点按 64 对齐，`completed/locked` 偏移 64/65；原生与代理共用四槽 |
| `kd_spin_cpu_state` | normal 80 / CPU；NUMA 增加 16 | 静态 per-CPU；`lock_addr[8]`、当前代理 CPU、`node_count`、等待栈顶；NUMA 再有暂存链表头尾 |
| continuation/等待栈共享预留区 | 20480 / CPU | `kd_spinlock_init()` 每 CPU 一次 `vzalloc`；低端 12 KiB 放 continuation，高端 8 KiB 为物理等待栈，两区不重叠 |
| `kd_spin_continuation_stack` | 9280 / CPU，包含 768 × 12 条记录 | 位于低端预留区；只按 top 分配，退休标记后收缩连续已退休栈顶；记录按 64 字节对齐，活动记录不搬移 |
| `kd_exec_frame` | 648，已包含在 request 中 | 生产者准备，combiner 原地 bind/pop，不为同一 spin 请求另分配第二个 frame |
| `pt_regs` | 168，已包含在 frame 中 | 根请求拥有寄存器包；虚拟子请求 `regs_ref` 可指向根包，不按层复制整包 |
| `kd_spin_jit_context` | 16，已包含在 request 中 | 虚拟请求的 `requester` 与锁深度；跟随 request 存活，不绑定可复用 node 槽 |
| `kd_exec_context` | 5208 / CPU | `kd_exec.c` 静态 per-CPU，含 8 × 648 的旧 frame 数组及 top/owner/depth。spin 外部 request frame 绑定到 top；数组仍服务 mutex/其他 push 路径，不是每个 spin 请求新增一份 |
| `kd_spin_fast_cpu` | 24 / CPU | 静态 per-CPU；单一 task 持锁的 held/owner，以及原生嵌套/IRQ 排空计数 nondelegated |
| `kd_spin_entry` / pool | 48 × 32 + 16 = 1552 / CPU | `kd_spin_entries_init()` 一次 `alloc_percpu`；ticket 记录 task/CPU/代际/物理所有权及 native 引用，最后 ACK 和 end 后归还槽。尺寸依赖当前内核 raw lock 布局 |
| 热表 candidate/table/cpu | 40 / 288 / 576 | `kd_hotlock_init()` 一次 `alloc_percpu`；每 CPU spin、mutex 各 16 桶、6 候选，共 576；不是 owner 存储 |
| `kd_spin_diag_slot` | 128 × 32 = 4096，全局 | 静态数组；锁地址、禁用标志和 waiter 数，槽身份在模块会话内稳定；它是诊断表，不是已删除的全局热锁晋升集合 |
| `kd_spin_diag_cpu` | 2592 / CPU | spin 初始化时 `alloc_percpu`；事件/批次计数，排空汇总后释放；SELFTEST 额外探针存储不计入 normal 表 |

这些是对象请求长度，不是模块总 RSS。例如 20 KiB 预留区由 vmalloc 按页支撑，
实际占用还有页取整和管理开销；静态 per-CPU 符号间也可能有填充。
来源：[spin 布局](../../include/kd_spinlock.h)、
[CPU 状态](../../kernel_module/spin/state.inc)、
[初始化/销毁](../../kernel_module/spin/lifecycle.inc)、
[frame 布局](../../include/kd_exec.h)、
[ticket](../../kernel_module/kd_spin_entry.c)、
[热表](../../kernel_module/kd_hotlock.c)。

### 4.2 调用栈对象与全局翻译对象

| 对象 | 大小 | 创建位置与数据流 |
| --- | --- | --- |
| `kd_spin_ref` | 16 | ticket 指针 + sequence；内嵌于请求/frame/ACK，用于代际检查，不另分配 |
| `kd_spin_request` | 24 | `kd_spin_lock_abi()` 等调用栈局部；ref + KD word 指针，传给队列/batch，早释放后仍用原 ticket 重新获取 |
| `kd_spin_native_input` | 48 | `kd_spin_lock_slowpath()` 栈局部；物理 RSP、逻辑 SP/IP/BP、ABI、IRQ flags，发布前写入稳定 request |
| `kd_spin_batch` | normal 184；NUMA 或 SELFTEST 单开 192，两者开 200 | `run_combiner()` 栈局部，含外层释放 hook、后继、request、翻译及进度；覆盖整批和同步 ACK 等待 |
| `kd_jit_batch_call` | 96，已包含在 batch 中 | wrapper 描述，含寄存器指针、两元素 args、代码/入口/完成信息，不是另一份寄存器包 |
| `kd_combiner_state` | 88，已包含在 frame 中 | 首次进入复杂路径时保存 combiner 锁账本与队列检查点；简单路径避免完整检查点保存 |
| `kd_exec_outer_unlock` | 16，已包含在 batch 中 | frame 通过指针调用 release hook，released 防止重复物理释放 |
| `kd_remote_request` | 24 | 子执行者 `kd_exec_remote_unlock()` 栈局部；指针发给父 frame mailbox，等待 done ACK 后才可退出作用域 |
| `kd_native_request` | 32 | 原 waiter `kd_exec_native_unlock()` 栈局部；发给仍持物理锁的执行者，最后 ACK 后返回 |
| `kd_exe_info` 注册表 | 64 × 511 = 32704，全局 | `kd_exe_init()` 一次 `vzalloc`；按代码入口登记，不按锁或每次获取创建 |
| JIT code block 池 | 每块 655360（640 KiB），最多 64 块 = 40 MiB | provider 初始化逐块 `vmalloc` 并设置执行权限，至少一块成功才可启动；入口登记取预留块，实际块数看启动日志 |

caller-clobber 调用壳由编译器保存活跃值，保存量取决于调用点，不是每次固定
保存 168 字节。wrapper/生成代码还使用已有执行栈，详见
[寄存器 ABI](../../docs/JIT_REGISTER_ABI.md)。翻译分配见
[registry_lifecycle.inc](../../kernel_module/execution/registry_lifecycle.inc)。

### 4.3 continuation 状态与回收

| 字段 | 当前用途与写入方 |
| --- | --- |
| `kind` | ROOT 或 VIRTUAL，明确区分物理入口与嵌套虚拟请求 |
| `result` | QUEUED、RETRY、NATIVE_READY；RETRY 只允许未执行正文的入口恢复 |
| `storage` / `retired` | 指向所属 CPU 的存储栈及退休标记；仅所属 CPU 更新 top，远端 native 子执行者在 pop 后发布标记 |
| `native_regs_decoded` | 物理入口寄存器包已准备完成 |

`users`、`packet_owner`、`jit_waiter`、`jit_retry`、`native_resume`、
`pinned_context` 已移除。额外抢占嵌套的检查前移到代理发布前，拒绝走 KD 原生
MCS。原生 MCS 节点仍为 `execution=NULL`，不申请 continuation。

## 5. KDLock 按阶段执行

### 5.1 准备、热度与快速获取

1. 计时前 `kd_spin_prepare(lock, post_call_ip, ABI)` 登记入口。provider 使用
   既有注册表/代码池；daemon 经 `/dev/kd_dev` 取得代码与元数据，翻译、组装、
   上传并发布。NORMAL 只表示可尝试执行，不能当作正文执行证据。
2. `KD_SPIN_DIRECT_CALL` 传 lock、pre-CALL SP、post-CALL IP、BP 给 clobber v1
   入口，编译器按调用壳的 clobber 声明保存活跃值。
3. `kd_spin_lock_abi()` 在任何热度/上下文判断前执行一次 `preempt_disable()`；
   直接原生 bridge 入口同样先关闭抢占。开启代理时记录本 CPU spin 热表，统计
   复用入口 pin，不额外 disable/enable；独立统计调用或可睡眠 mutex 调用才
   在尚未关闭抢占时临时 pin。每 10240 个记录样本
   检查时钟，CPU 窗口为 40000000000 TSC ticks，候选窗口为 2500000000 ticks。
   CPU 速率满足条件后统计候选，adaptive 要求 `score-error >= 10000`。
   桶链用槽位索引并比较完整地址，满表 miss 才扫描六个 score 淘汰。重入失败
   丢弃样本；observe 的固定准入仍保留。
4. 上下文/冷热策略拒绝或关闭代理时走已 pinned 的原生 helper；其他路径继续
   检查执行上下文。所有分支保留同一次入口 pin，不先 enable 再 disable。
   普通无嵌套 fast CAS 成功只登记 per-CPU fast owner，不 reserve ticket/node/
   request；竞争或嵌套时再占 ticket。pending 成功也不需要 node/request。
5. 到 queue 分支才检查 JIT ready；未 ready 时尝试登记并走原生 MCS，保留已经
   建立的 ticket，取得物理锁后 claim。

热表仅给准入建议；解锁不查询它。窗口重置、候选淘汰、CPU 迁移不能改变已有
owner、frame 或 ACK 归属。统计与锁协议是独立数据流。

每次实际嵌套 lock 获取仍有自己的一次 pin，与对应 unlock 配对。普通自执行在
物理释放及 owner/ticket 清理后 `preempt_enable()`；被完整代理的原调用者在
完成恢复路径结束其 ticket/pin；native 续跑等待最后 owner ACK 才结束原 ticket。
远端执行者不能替另一个 CPU 恢复抢占。批次提前释放再重新获取仍保留原入口 pin。

### 5.2 无 JIT / 无代理：原生 MCS

`kd_spin_lock_nondelegated()` → `kd_spin_acquire_nondelegated()`：

1. 同一 KD 字 fast CAS → pending → MCS。只有需要排队才占一个预分配节点；
   设置 `socket_id=IRQ_NUMA_NODE` 表示不可代理，`execution=NULL`。该标记也
   用于普通 task，不表示调用一定来自 IRQ。
2. 交换 tail、向前驱发布 next，在自己的 locked 轮询；队首才等共享锁字。
3. 队首取得物理锁后，把队首资格交给后继并归还 node_count。后继仍等物理锁
   释放；**唤醒后继不等于释放自己的临界区锁**。
4. 原线程执行正文；普通根请求转入 fast owner，嵌套/IRQ 保留独立排空计数。
   已有 ticket 的回退保留 ticket。unlock release 清除 locked、保留 pending/
   tail，并结束对应 owner/ticket/pin。

此路径不 reserve request、不绑定 frame、不准备寄存器包、不换等待栈、不建立
代理 source lease，也不调用 Linux 锁协议。发布前 continuation 容量不足仍走此 MCS 路径。
真正四节点全占用才轮询 KD 字：原生 helper 使用 read-before-CAS；代理 slowpath
自身的节点耗尽分支目前仍是 trylock/CAS 循环，不能写成所有极端分支已经统一。
来源：[nondelegated.inc](../../kernel_module/spin/nondelegated.inc)。

### 5.3 可代理请求发布与执行

1. `kd_spin_lock_slowpath()` 保存 IRQ flags、屏蔽 IRQ、准备 input，reserve
   node/request。根请求令 `regs_ref=&frame.regs`；clobber v1 只初始化 IP/SP/BP
   的 MINIMAL 包，复杂出口才物化 FULL GPR 包。
2. 初始化逻辑 task、GS、ABI、ticket 等。物理 waiter 有前驱时，**先切到 8 KiB
   等待栈，再发布前驱 next**，随后汇编 PAUSE 轮询。JIT 会使用原 waiter 的
   逻辑栈地址，原 CPU 不能继续在借出的栈上压入 C 帧。
3. 队首独占时自行获取并归还排队资源；有可代理后继时保存状态、创建栈上 batch，
   取得 source lease 后执行。不可代理节点既是批次入口边界，也是批内边界，
   不能解引用其空 execution。
4. combiner 使用 `node->execution` 的现成 frame/包。简单路径走批量 wrapper，
   复杂路径 bind 到本 CPU exec context。`batch.call.regs` 指向同一逻辑包，
   不复制 waiter frame 给 combiner。wrapper 入参 `args[0/1]` 分别传逻辑 GS 和
   task，返回时承载出口结果；寄存器包提供逻辑 IP/SP。与 TCLock 不同，KD
   wrapper 的物理 RSP 保持在执行者栈上，生成代码通过逻辑 SP 访问 waiter 栈。
5. wrapper 执行生成代码，业务内存直接读写 workload 原始共享地址。普通完成
   回写 post-unlock IP/SP/BP；中间出口保存 FULL 包与续点，按锁账本/控制 CALL
   状态决定嵌套、完成或受检原生续跑。
6. 正常完成先退休相应 frame，再通知 waiter。物理 waiter 丢弃可能被覆盖的旧
   hook/queue C 帧，从稳定 request 恢复；最后一次寄存器读取后才标记退休并收缩栈顶，
   恢复 IRQ flags 并跳到续点。未执行正文的队首交接才可返回旧 C 调用链。

```text
物理 waiter CPU                    combiner CPU
input → reserve request
request.frame.regs ← IP/SP/BP
node.execution → request
切等待栈 → 发布 next ─────────────→ node → 同一 request/frame
PAUSE 轮询                          batch.call.regs → 根寄存器包
                                   wrapper/JIT → 原业务内存、逻辑栈
                                   完成包/续点 → 同一寄存器包
恢复 request ← 完成/原生通知 ←───── frame 退休或保留 owner 等 ACK
最后一次包读取后标记退休并收缩 top（native 有剩余锁时保留至最终解锁）
```

来源：[入口](../../kernel_module/kd_spinlock.c)、
[发布等待](../../kernel_module/spin/wait.inc)、
[队列](../../kernel_module/spin/slowpath.inc)、
[批次](../../kernel_module/spin/combiner.inc)、
[复杂执行](../../kernel_module/spin/execute.inc)。

### 5.4 嵌套代理、提前释放和 ACK

| 场景 | 对象与数据流 | 结束条件 |
| --- | --- | --- |
| JIT A 遇到 B | 嵌套入口先占独立 ticket；快速获取更新锁账本，需虚拟排队再占 node/request。子 frame 有独立锁账本，regs_ref 共享根包，requester 指向直接父 frame | 子 frame pop 后才允许父请求继续；无需整包复制或根包引用计数 |
| B 由另一 CPU 代理 | A 执行者保留自己的 C 栈等待并轮询 remote mailbox，不切物理 waiter 专用等待栈 | 子执行者发布完成/原生结果，父执行者处理恢复；B 是 A 已准入代码的续点，不是独立词法深度 1 入口 |
| 持 B 提前释放 A / OOO | jit_lock 数组记录 kind、node、released；需远端 owner 释放时发送 24 字节栈上 remote request | owner 完成唯一物理释放并更新账本，最后 release-store done；发送者收到 ACK 才销毁栈对象 |
| batch 外层锁提前释放 | frame 调用 batch 内嵌 outer hook，released 记录释放；批次收尾经原生 MCS 重新取得同一 KD 字，原 ticket reclaim | 重新取得后再回调用者，不新增另一份外层 frame/ticket，不重复释放已放开的字 |
| JIT 受检续点转原生 | 每个执行者（含无锁 relay）登记根 ticket 借用，再发布 NATIVE_READY | 原 waiter 经栈上 request 请求 owner 解锁；物理 ACK 与退休分开，清理/pop 后解除借用；最终解锁等待全部退休再释放根现场与入口抢占保护 |
| 未执行正文就拒绝 JIT | 可退回 KD 获取/原入口恢复，result=RETRY 区分恢复方式；虚拟请求取消本次远端绑定后继续父执行 | 不允许把已执行正文的失败当作从头 retry，只支持已有受检续跑边界 |

**node 复用、NATIVE_READY、物理解锁 ACK、frame pop、存储回收及 source lease
释放是不同事件。** 无剩余锁的 native 续跑在恢复前等待全部退休；普通恢复汇编
完成全部现场读取后才回收根记录。OWNER/WAITER/COMBINER/DONE 仍保存在稳定
owner/ticket/frame 中，不依赖热表。

TCLock 通过真实栈续点及节点完成交接表达执行进度；KD 还需要显式包、frame 和
受检恢复状态。不能因为 TCLock 无同名字段就删掉生命周期，也不能让这些代理
状态成为原生 MCS 路径的每次调用成本。

## 6. 验证与结果解释

本轮功能检查与未覆盖边界见 [continuation 验证记录](../../tests/README.md#continuation-validation)。未运行性能测量，
只确认省去空闲引用扫描、request users/packet_owner 更新及第二次预分配。真实 JIT
须有 wrapper 返回后的正文证据；NORMAL、原生完成、排空均不能单独代替。
当前 TCLock 对照验证业务数据与排空，没有实际委托计数，不能把剩余调用数
当作委托比例。

已有验证和限制见 [原生 MCS 报告](../tclock_compare/results/20260920-native-mcs.md)、
[本地热表报告](../tclock_compare/results/20260920-local-hash.md)。运行入口见
[benchmark README](README.md)；准入/续跑边界见
[JIT 执行流](../../docs/JIT_EXECUTION.md)、[frame 协议](../../docs/design/frames.md)。
