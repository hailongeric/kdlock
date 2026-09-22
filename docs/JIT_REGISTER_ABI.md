# kdlock JIT 执行与寄存器 ABI

本文以当前 x86-64 内核 spin/mutex 实现为准，描述入口、wrapper、退出及原 waiter
续跑的寄存器/栈约定。使用与执行流见 [JIT_EXECUTION.md](JIT_EXECUTION.md)，
锁和 frame 生命周期见 [DESIGN.md](DESIGN.md)，结果见
[VALIDATION.md](VALIDATION.md)。

通用执行入口是 frame-backed `kd_exe_on_call_hl_entry()`；普通 spin 批次可使用
锁侧 `kd_spin_batch_run()` 和第 2.3 节的专用 wrapper 入口。两元素输入保持
`{waiter GS base, logical waiter task}`，不增加 FS base 或第三个 task 元素。
GS 内存按 origin GS base 翻译；等待代理结果的线程保持禁止抢占并用 PAUSE 轮询。
普通直接 CALL miss 后原 waiter 原生完成后缀，不返回本次 JIT；它不是入口重试。
未来调用若采用学习后的直接 callee，准入传播实际 CALL 包及 RET 效果，并校验
返回目标表；这不增加 wrapper 参数，也不假定普通 callee 保留哪些寄存器。
除明确标为待实现的 3.1 节外，本文件说明已实现的状态契约；不保证 flags、
任意指令或任意故障恢复正确。

## 1. 状态边界

spin 代理执行使用一份预分配的共享寄存器包。`entry_abi` 由实际内核入口确定，
沿 registry、daemon、生成物目录、frame 和 wrapper 逐层核对，不能由调用点
形状猜测。下图描述旧 ABI；新普通 spin 路径见 1.0 节，普通 mutex 见其后的 mutex 小节。
mutex 的最小入口借用 node 包，中途 FULL 出口才取得独立状态，见第 4 节：

```text
native waiter hook stack
        |
        | decode saved callee registers + RIP/RSP before publication
        v
continuation.frame.regs <--- node->execution->frame.regs_ref
        |
        | bind the same continuation.frame; virt_ptr(regs, args)
        v
wrapper control stack + CPU registers + shared packet spill slots
        |
        | exit writes back the same register packet and args[]
        v
kernel executor / known-call / hostcall
        |
        | optionally update RIP/RSP and call the same artifact again
        v
shared packet -> final CPU loads -> retire continuation -> original waiter resume
```

这里必须区分四种栈：

| 栈 | 当前表示 | 用途 |
| --- | --- | --- |
| waiter 逻辑栈 | `pt_regs.sp`，JIT 内主要由物理 R13 表示 | 原临界区的局部变量、保存寄存器和虚拟 `CALL` 返回地址 |
| wrapper 实栈 | 物理 RSP | 保存 combiner 的 C ABI 状态和 JIT 私有槽；不能当作 guest RSP 使用 |
| 后端 C 栈 | spin 使用执行者自己的 task 内核栈；mutex 使用其独立 waiter 栈 | 运行 queue/combiner C 代码；不等于 JIT 的虚拟调用栈 |
| spin shadow 等待栈 | 每 CPU 20 KiB 区域的高端 8 KiB，`kd_spin_cpu_state.wait_stack_top` | 物理 waiter 发布前切入，保存一个旧 C RSP 并 PAUSE 轮询；不承载 JIT 或 frame |

spin 的普通物理 waiter 保持本 CPU 的 IRQ 状态，同一段汇编先切到
shadow 等待栈，再发布和轮询，不访问旧 C 栈。尚未执行的队首交接恢复旧 RSP；
代理完成后直接在 task 栈的安全位置重建恢复帧，不逐层返回旧 slowpath。
离开等待栈且读完/退休 continuation 后才释放 pin 并转到续点，IRQ 状态不变。锁地址账本和 wrapper
暂存不属于这份等待栈。虚拟 waiter 的 owner/ACK 轮询仍使用执行者独立的 C 栈。

`struct pt_regs` 的有效字段由 `packet_state` 决定。嵌套锁或 hostcall
退出 sandbox 后，任何需要再次进入 JIT 的状态都必须先落实到这份结构中。

### 1.0 普通 spin 的 caller-clobber v1

当前 workload 通过显式 `KD_SPIN_DIRECT_CALL(kd_spin_lock_clobber_v1, ...)`
接入，使用同一寄存器约定；provider 不安装全局 spin hook。下述内核桥说明 ABI
来源，不表示加载 provider 会代理普通 Linux 锁。

显式配对壳 `KD_SPIN_DIRECT_LOCK(lock, cookie, continuation)` / `KD_SPIN_DIRECT_UNLOCK(lock, cookie)`
使用普通 C caller-saved 约束，cookie统一传`kd_spin_direct_cookie`，它是已有per-CPU
`rate_hot`的视图。一个CPU一份，所有锁共享；不另存路径、嵌套深度或调用点cookie。
cookie只在C selector取得pin后读取，不在JIT正文中改写，也不能与保留壳混配。
`spin_cold_fastpath=1` 时，selector 获取一个 pin 后按 CPU 热度决定本次路径。
冷态不会计算 SP/IP/BP，也不强制保存五个 callee-saved 寄存器；编译器仍可保存普通 C 活跃值。
热态在 asm 内依次 push RBX/R12/R13/R14/R15，然后向 pinned clobber-v1 入口传递同一四参数。
continuation 位于 CALL 后、五个 POP 前，因此 MINIMAL 输入仍只有 IP/SP/BP，其他入口值来自栈。
continuation不依赖未捕获的CALL返回值。冷获取使用低字节状态5，冷解锁据此直接释放，
不查询热度、ticket、context或fast owner；热解锁重新保存当前活跃值。
COMPLETE 指向解锁 CALL 后的 POP，FULL 仍恢复完整包，拒绝沿本次原生获取完成。
调用端需重编译，wrapper 参数、包布局、32 位锁字均未改变；当前 workload 仅迁移外层；nested/early 的旧内层入口另用栈保存/重载五个值，
防止外层新壳把内层 clobber 后的未捕获值再次压栈。内层 ABI 和续跑协议不变。

共享核心内联到普通 clobber/pinned 入口和两种热解锁包装；前者自行 pin，后者复用 selector
的 pin，不重复查询 pin 状态。JIT 分发表只包含实际生成的指令续点；已裁剪的原生后缀
由物理完成恢复，不生成悬空的解锁后标签，也不扩大可执行范围。

默认 `kdclobber2` 内核的 `raw_spin_lock/unlock`（包括其 `spin_lock/unlock` 调用者）
用内联 asm 调用 `kd_raw_spin_{lock,unlock}_clobber_v1`。RDI 为锁，RSI 为
CALL 前 RSP，RDX 为同一 asm 内的 CALL 后标签，RCX 为调用者 RBP。
RDI 使用读写约束，元数据寄存器为输出，其余 GPR、`cc`、`memory` 明确破坏；
`ASM_CALL_CONSTRAINT` 保留，RSP/RBP 必须满足调用边界。跨边界活跃值由
调用者编译器保存。函数级 callee-saved 序言仍可能存在，不承诺消除所有 push/pop。
IRQ/BH/irqsave/trylock 和显式 nested 入口保持原契约；普通 mutex 使用独立 ABI=2。
provider 构建要求 `KD_SPIN_CLOBBER_V1`；旧内核安装分支已删除，缺失接口时报错。
这不删除同一内核上的旧调用者支持：`KD_SPIN_LEGACY_CALLER` 对照、显式 nested
入口和 FULL 续跑仍有实际消费者，不能把它们当成废代码。

| `packet_state` | 有效状态及消费者 |
| --- | --- |
| MINIMAL | 仅 RIP/RSP/RBP；GS/task、锁和生命周期在 frame 中。发布前不解码旧序言、不初始化整包；入口拒绝后沿原生获取流程返回 lock 后续点 |
| COMPLETE | wrapper 验证普通 root 的 outer unlock 目标、锁、RSI=虚拟 SP+8、RDX=返回槽、RCX=逻辑 BP，写入 unlock 后续 RIP/RSP/RBP，返回独立分类 7 |
| FULL | 中间退出在进入 C 之前保存当前完整逻辑 GPR。沿已有 hostcall、nested、native 或续跑处理，不重放前缀 |

正常新路径为 `MINIMAL → COMPLETE → waiter`。`kd_spin_restore_request()`
在全部现场读取完成后标记 continuation 退休并收缩本 CPU 栈顶，完成后通过保留 GPR 的 helper 解除原入口 pin；IRQ 状态不变；
只恢复三个续点字段，调用者后续
指令重新装载活跃值。FULL 继续使用原完整恢复。两种状态不能混入通用 dispatcher。

新 wrapper 位于偏移 32，目录偏移 25 为 `KDWC001`、41 为 `KDAB`、45 为
生成物的 `entry_abi` 字节。RDX 传递独立元数据描述符；原两元素 `args` 不变。
`kd_jit_clobber_call_v1()` 为 combiner 提供编译器可见的 clobber 调用边界，
wrapper 只保护物理 RBP，不导入线程 GPR、不手写保护 RBX/R12–R15。
JIT 的虚拟 GPR 暂存直接复用预分配 `pt_regs` 字段，不另建入口副本。
MINIMAL/COMPLETE 中未捕获字段可以在正文执行后成为 JIT spill，但不能因此
当作有效的初始或完整恢复状态；只有 FULL 出口补齐 CPU 中的当前逻辑值后
才允许 C 消费完整包。准入证明禁止正文观察
未捕获的初始 GPR，包括部分寄存器、内存地址、存储值和分支条件。
入口 guard 仅允许 SP/BP 寄存器依赖；新 ABI 可引用未被正文先前写入影响的
初始 64-bit 栈槽。guard 在读取任何槽前先检查所有源槽完整位于入口 SP/BP
范围内，再对加载的指针检查别名条件。常量左移形成的数组索引使用相同的
64-bit 回绕运算检查实际地址，不假定索引范围。未知写入、opaque callee 或
被覆盖的槽不能重新获得入口身份；未知写入失效位随 CFG 分支合并传播。
越界、别名或证明预算耗尽均在正文前拒绝。此精度重试的内存分析预算为四百万步
和 512 个字节事实（旧 ABI 仍为一百万步、256 字节），用于新增 spill 的
逐字节别名证明。guard 收集和输出均合并重叠区间，保留原容量限制。
新控制边界丢弃旧 callee-saved 事实，
SP/BP 和内存状态保留；虚拟 CALL 的返回槽及控制处理器的 32-bit 锁字写入
仍经过原有别名/guard 分析，与锁可能重叠的 spill 必须失效。此摘要只适用于
新普通 spin 控制入口。新 ABI 对现有 typed `ktime_get`、`ktime_get_ns` 和
`int_sqrt` handler 使用顺序效果摘要：服务不写 waiter 内存，虚拟 CALL 的
返回槽仍参与别名分析；返回寄存器未知，保留正常 C ABI 的 callee-saved 事实。
未来或未知服务不继承此摘要；旧 ABI 的控制/hostcall 失效规则保持不变。
敏感地址准入和并发内存新鲜度的原有限制继续适用。

偏移 0 的普通 C ABI 和偏移 16 的旧批次入口继续可用。旧生成物仅能进入旧
ABI；新图像的 ABI 必须匹配 registry/frame。嵌套混合边界使用 FULL 包。
所有批次在同一个锁侧 C 循环中调用 wrapper，包括新旧 ABI 混合队列。
旧偏移 16 入口通过 `kd_jit_legacy_batch_call()` 只额外保护物理 RBP；
新偏移 32 入口自己保护 RBP。编译器管理跨 wrapper 活跃的 combiner C 值，
不再进入成组保存寄存器的汇编外壳，也不因旧入口返回外层循环。下一 waiter
选择、完成发布、原生 peer 排斥、source pin 和 owner/ACK 仍由锁层负责。
实验补丁、构建与基线操作见 [spin_clobber](../kernel_experiments/spin_clobber/README.md)。

<a id="mutex-clobber-assessment"></a>

#### 普通 mutex 的 caller-clobber v1

`kdclobber2` 的普通 `mutex_lock/unlock` 宏调用独立
`kd_mutex_{lock,unlock}_clobber_v1`；寄存器参数与 spin 相同，`entry_abi=2`。
spin 为 1、旧 ABI 为 0，registry、daemon、translator 和 wrapper 必须匹配
后端及身份。内核桥接通过 static call 选择 provider，原生回退直接调用
原 mutex fast/slowpath，避免宏递归。interruptible/killable/trylock、IO、
显式 nested 和取函数地址的调用者保留旧契约。

node 发布前只写 IP/SP/BP。`kd_mutex_clobber_wait()` 先进入该预约的 8 KiB
shadow 栈，再运行排队代码；只有未执行的队首可以返回旧 C 帧。已完成请求
在两个栈位置以下重建恢复帧，清理 slot、恢复抢占/迁移及 task 引用后直接
回到续点，不再经过可能被 JIT 覆盖的 hook 帧。

首个物理 root frame 通过 `kd_exec_frame_push_borrowed()` 借用 node 的同一包。
只有单一 A 账本、没有嵌套/remote/提前释放的首轮调用允许 COMPLETE；wrapper
还检查精确的新 unlock 目标、锁和续点元数据。正常路径无整包初始化、导入、
node/frame 复制或最终完整恢复。JIT 暂存字段不等于有效入口 GPR。

中间出口先物化 FULL，再在任何 C 控制服务前复制到 frame 自有包。这个副本
有独立生命周期：原生 waiter 释放 node 后，combiner 仍必须等待 owner ACK。
FULL 正常或 native 返回在释放 node 前另存恢复包；不能从已复用的 node 恢复。
原生 owner 不转交给 waiter，真实 mutex 获取可以睡眠，A/B 解锁仍由实际 owner
执行并 ACK。正文已经执行时不允许回到入口重放。

翻译器在新 mutex 边界丢弃 callee-saved 事实，但保留原有 opaque-memory 和
256 字节受检栈协议；不能套用 spin 的 32-bit 锁字写入摘要。
RBP spill 与 RSP 检查窗口的覆盖关系可由入口谓词证明；每个字的全部字节
必须位于所有先前控制调用的窗口内，CFG 合并取这些约束的交集。原生处理器
仍比较完整窗口。未知写入/普通 callee 不允许重新取得入口槽身份。
旧 ABI 仍解码原内核保存栈并完整恢复；重复六寄存器副本已删除。node 为
256B/64B 对齐，next 与 64/65 偏移的通知字节分行，CPU 从 tail 解码。
补丁及基线操作见 [mutex_clobber](../kernel_experiments/mutex_clobber/README.md)。
已知 pinned mode-4 调度缺口仍见 [TODO](TODO.md#current-checkpoint)。

### 1.1 与 TCLock spinlock 的执行路径和状态保存对比

对照仓库内 [TCLock 上游快照](../tclock_backend/upstream/)；其固定提交为
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`，来源与哈希见
[UPSTREAM.json](../tclock_backend/UPSTREAM.json)。对应上游内核代码：
`src/kernel/rcuht/locks/komb.c`、`src/kernel/rcuht/lib/combiner.c` 和
`src/kernel/rcuht/include/lib/combiner.h`。该头文件启用 `WWJUMP`。
这里比较实现，不把 Linux qspinlock benchmark 当成 TCLock 性能对照。
独立 [tclock_backend](../tclock_backend/README.md) 已保留该来源的完整普通 spin
执行路径，通过同一内核 hook 物理切换 waiter 栈；同负载的
[当前三方实测](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260919-state-access.md)另行报告。
该后端的现场恢复没有经过 kdlock wrapper，不能拿它替代 JIT 中途完整物化。

TCLock 的 `komb_spin_lock_slowpath()` 先把六个 callee-saved 寄存器压到
waiter 原栈，node 仅记 RSP；CALL 返回地址也在该栈上。caller-saved 活跃值由
调用者编译器保存。随后 waiter 在 shadow 栈排队等待，原栈借给 combiner。
`komb_context_switch()` 保存六个 callee-saved，交换物理 RSP，再恢复入栈方的
六个寄存器。它没有保存所有 GPR，也没有保存 RFLAGS。

combiner 的 `execute_cs()` 首次切入 waiter 后，自己的栈帧一直保留。
`komb_spin_unlock()` 在末节点、IRQ 节点、批次上限或 `need_resched()` 时返回
combiner；否则直接切入下一 waiter 的 lock 续点。旧 waiter 的完成通知在离开
其栈后发布。该交接仍运行两端的锁侧 C 代码，六组 push/pop 不是总成本。

kdlock 采用相同的现场寿命原则：等待者先离开原栈再发布，整批保留一个
combiner 续点，完成发布后不再访问旧请求。`kd_spin_batch_run()` 让新、旧及
混合 ABI 都在同一个 C 栈帧中连续执行；正常请求无需逐次退出/重入批次函数。
编译器负责保存跨 wrapper 活跃的 C 值；旧偏移 16 wrapper 会破坏物理 RBP，
其调用适配只保存/恢复这一个寄存器，并保持 RSP 与 CALL 对齐。
没有额外的 RBX/R12–R15 成组汇编保护，也不解析编译器序言。
这不保证机器码不再保存这些寄存器：caller 所在函数仍须满足对外 C ABI，
combiner 的活跃 C 值也需要跨 clobber 保存。显式状态搬运减少与端到端成本
下降是不同结论；函数级保存、逐请求校验等抵消点见
[当前执行路径与对象对照](../bench/spin_cacheline/EXECUTION_PATHS.md)。

```text
TCLock:
  waiter: 六个 callee-saved 留在原栈 -> shadow 栈等待
  combiner: 保存一次自身续点 -> 切物理 RSP -> 原生 CS
    -> unlock 保存续点 -> 下一 waiter，或回到原 combiner
  waiter: 加载 node.RSP -> 恢复 callee-saved -> 沿 unlock 返回

kdlock caller-clobber v1:
  waiter: 编译器保存活跃值 -> 记录 RIP/RSP/RBP -> shadow 栈 -> 发布
  combiner: 同一个 C 帧 -> 准入/绑定 -> 精简 wrapper -> JIT CS
    -> 三字段 COMPLETE -> 完成/解绑/发布 -> 同循环下一请求
  waiter: 退休 ticket 元数据 -> 恢复 RIP/RSP/RBP -> 退休 continuation -> unpin -> caller 续点
  中途出口: 完整逻辑 GPR 物化一次 -> 既有 hostcall/nested/native 协议
```

| 现场 | TCLock | 当前 kdlock |
| --- | --- | --- |
| 入口保存 | 原栈六个 callee-saved，node.RSP，栈上返回地址 | 新 ABI 仅 RIP/RSP/RBP；其他活跃值由 caller 编译器保存。旧 ABI 继续原捕获 |
| combiner | 批次期间保留原栈帧，WWJUMP 不逐次返回它 | 单个 C 循环覆盖新旧及混合请求，编译器保存自身活跃值；每次调用仅有必要 RBP 保护 |
| 正常最终出口 | 保存 unlock 的原生栈续点，物理 waiter 恢复六个寄存器 | 新 ABI 验证 outer unlock 身份及元数据，只写回/恢复 RIP/RSP/RBP；旧 ABI 保持原规则 |
| 中途现场 | 原生 C ABI 与真实栈续点 | JIT 当前完整逻辑 GPR，在进入 C 前写入唯一共享包；续跑禁止重放前缀 |
| task/GS | node.task 和 `komb_get_current()`，不切硬件 GS/task | 显式 logical task/origin GS，同样不切硬件 GS/task |
| 等待与回收 | 离开被代理原栈后通知完成 | shadow 发布、frame pop、release wake；最后读取后回收 continuation，native 另等全部 ticket 借用退休 |

kdlock 的物理 RSP 必须留在 combiner 栈：wrapper 的控制槽、地址
重写和逻辑 SP/BP 映射依赖这个帧。虚拟 GPR backing 已改为直接使用共享包，
没有 `pt_regs → wrapper spill → pt_regs` 的复制链。它只切换 JIT 的逻辑 waiter 栈，不能直接
套用 TCLock 的物理 RSP 切换汇编；那样会破坏现有 JIT 寄存器映射。
中途退出也不能只保存六个 callee-saved，因为已执行的逻辑 caller-saved 值
可能仍被后缀使用。只有明确的 caller-clobber 最终边界允许丢弃这些值。

锁侧准入/绑定、KD 单锁字对同协议 peer 的排斥、source 生命周期、嵌套 owner/ACK 和
提前解锁仍需保留。二者均没有完整条件码上下文恢复：kdlock 普通 spin 最终不执行 `popfq`，
IRQ 状态保持不变，也不恢复 JIT 退出点的条件码。详细限制见第 3 节。
本次验证与未重跑范围见 [历史：测试记录](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/tests/README.md#tclock-context-loop)。

核对入口：[等待栈切换](../kernel_module/spin/wait.inc)、
[统一批次](../kernel_module/spin/combiner.inc)、
[编译器调用边界](../include/kd_jit_batch.h)、[wrapper](../include/wrapper.S)、
[最终恢复](../kernel_module/kd_spinlock.c)。

## 2. JIT 函数调用 ABI

生成物的偏移 0 为 `wrapper.S:main`，本节描述这个普通 C ABI 入口。
普通 spin 批次实际使用偏移 16/32 的 clobber 调用边界（第 1.0、2.3 节），
不能把它们转换成下列普通函数指针调用。偏移 0 的类型为：

```c
void (*virt_ptr)(struct pt_regs *regs, unsigned long args[2]);
```

按照 x86-64 SysV ABI，进入 wrapper 时：

| 物理寄存器 | 输入 |
| --- | --- |
| RDI | `regs` 指针 |
| RSI | `args` 指针 |

wrapper 保存宿主 RBX、RBP、R12-R15，因此对调用它的 C 代码遵守 callee-saved
约定。RAX、RCX、RDX、RSI、RDI、R8-R11 是 caller-saved，wrapper 返回时可被
破坏；C 侧不从 RAX 接收状态，所有结果都通过 `regs` 和 `args` 返回。

`args` 是复用的输入/输出通道：

| 元素 | 调用前 | wrapper 返回后 |
| --- | --- | --- |
| `args[0]` | 被代理 waiter 的 kernel GS base | sandbox 退出原因；IJ miss 时为源 RIP |
| `args[1]` | logical waiter 的 `task_struct *` | body witness：开启观测且进入生成块为 1，否则为 0 |

参数数组始终只有两个元素，没有第三个 task 参数。wrapper 在
返回时会覆盖这两个输入，所以 executor 每次首次进入或 continuation
续跑前，都要从当前 `kd_exec_frame` 重新写入 GS base 和 logical task。
当前代码不得读取返回后的 `args[1]` 作为执行计数：`Stack_BUDGET` 中虽有运行时 block
budget，但 epilogue 不会把它复制到 `Stack_JIT_WITNESS`。此布尔标记不是指令
数量、完整路径覆盖率或代码 generation 身份。

翻译诊断开关 `KD_JIT_BODY_WITNESS` 默认是 `0`。设为 `1` 时，生成的基本块
和可恢复续点在标签后用 `MOV Stack_JIT_WITNESS, 1` 写入标记，不改变 GPR
或 flags；dispatcher、callee/IJ 退出表不写入它。每次 wrapper 调用先清零，
避免上次执行的 1 被误用。公共测试启动 daemon 时强制开启，并要求匹配
entry/lock 的返回后 `JIT body witness` 日志；原先的调用前 IP 日志不再足够。
执行器每次高层调用只记录第一个正标记，不承诺每次内部续跑都有单独日志。
此值不独立授权失败恢复、锁交接或重放；未开启观测的代码即使执行也返回 0。
专用入口拒绝协议将零值作为必要的包校验之一，还必须满足第 8 节的其他条件。

### 2.3 批次入口与退出保存集合

旧 ABI wrapper 在偏移 9 放置 `KDWB001` 签名，偏移 16 是专用批次入口；偏移 0
仍是普通 C ABI 入口。锁侧准入每次校验 OPEN、NORMAL、entry/backend、未执行
单锁 root、有效 SP 和签名。旧生成物没有该签名时走通用路径。
普通入口保存/恢复物理 combiner 的六个 callee-saved 寄存器；批次入口只
预留相同栈布局，由内联 asm 的 clobber 约束交给编译器保存活跃 C 值。
旧批次入口不恢复物理 RBP，调用适配用独立栈槽保护它。
`args[2]` 仍输入 GS/task、输出 exit/witness。专用入口额外从 RDX 接收
`kd_jit_batch_call` 指针，包含当前 L 和解锁入口；该指针不包含 node/队列或
调度回调，不能用于在 JIT 内切换 waiter。

原有 wrapper 控制槽偏移保持不变；`Stack_BATCH` 在 `RBP-160`，先分配栈空间
再写入，不使用内核 red zone。wrapper 返回同一个锁侧循环，完成当前请求后
继续下一请求，整批结束才退出这个 C 帧。旧 ABI 的普通入口与批次入口共用
`load_packet`，只装载实际驻留 CPU 的逻辑 GPR；R11–R15 的 backing 已在共享包中，
不再先复制到实栈。物理 waiter 保持原最终恢复规则。
下表描述旧 ABI；新 caller-clobber 的 MINIMAL/COMPLETE 规则见第 1.0 节。

| 返回边界 | 写回集合 |
| --- | --- |
| 专用批次的首次 CALL_MISS，目标恰为 spin unlock 且 RDI=L | RBX/RBP/R12–R15、虚拟 RIP/SP、用于完成分类的 RDI，以及 exit/witness |
| hostcall、其他 CALL miss、nested/native、错误或入口拒绝 | 原完整 GPR 包、虚拟 RIP/SP、exit/witness |
| 普通 C ABI wrapper 入口，包括旧 mutex 和 FULL 后续续跑 | 原完整 GPR 包、虚拟 RIP/SP、exit/witness |

缩小集合只适用于最终 lock/unlock ABI 边界，不适用于 JIT 中途出口。
复杂出口进入 `kd_exe_spin_batch_resume` 时已经执行过正文；通用 dispatcher 先
消费这次返回，再决定服务或续跑，不能再次调用原入口。下表描述完整保存路径。

## 3. `pt_regs` 输入输出约定

`asm_head.h` 对 Linux x86-64 `struct pt_regs` 使用硬编码偏移：

```text
0x00 r15      0x08 r14      0x10 r13      0x18 r12
0x20 rbp      0x28 rbx      0x30 r11      0x38 r10
0x40 r9       0x48 r8       0x50 rax      0x58 rcx
0x60 rdx      0x68 rsi      0x70 rdi      0x78 orig_rax
0x80 rip      0x88 cs       0x90 eflags   0x98 rsp
0xa0 ss
```

普通 spin 保持 IRQ 开启时，wrapper 的私有元数据必须一直位于已分配栈区内。
FULL 出口先写回 GPR，并读完 witness、exit kind、RIP、clobber/batch 描述，
最后才抬高物理 RSP。不能先释放栈再读负偏移槽，否则中断现场可能覆盖它们；
固定栈大小和已有偏移不变。

当前 wrapper 的字段语义如下：

| 字段 | 进入 JIT | 退出 JIT |
| --- | --- | --- |
| RAX、RBX、RCX、RDX、RSI、RDI、R8-R10 | 直接装入同名物理寄存器 | 从同名物理寄存器写回 |
| R11-R15 | 留在 `pt_regs`，按需映射到物理 R12-R15 | 翻译器 spill 直接写同一字段，无 epilogue 整组复制 |
| RSP | 装入物理 R13，作为虚拟 RSP | 从物理 R13 写回 |
| RBP | 装入物理 R12，作为虚拟 RBP | 从物理 R12 写回 |
| RIP | 由入口 dispatcher 读取；控制流中作为合成地址处理 | 从协议寄存器 R14 写回 |
| `orig_rax`、CS、EFLAGS、SS | 不装入 translated state | wrapper 不修改 |

上述表格描述 FULL/旧 ABI。物理 R11 固定指向本次 `regs`，`Stack_R11`–
`Stack_R15`、`Stack_RSP`、`Stack_RBP` 使用该基址，与对应 `PT_*` 指向同一字节。
物理 R12/R13 仍缓存逻辑 BP/SP，映射池中的脏值仍须按既有 block/控制出口规则
spill，直接执行的其他 GPR 仍须在完整出口写回。共享 backing 不意味着 CPU
寄存器和内存自动同步，也不能删除这些必要写回。

入口 guard 暂借 R11 做地址比较，所有通过、拒绝和 continuation 路径在跳入
正文或出口前恢复包基址。guard 只在执行前读取入口事实；执行后 `regs` 表示
当前状态，不再是不可变入口快照。使用权仍由原有 frame/request 与 owner/ACK
协议交接，父级不能在子级执行时读取同一包当作旧快照。

本次只变更生成物内部寄存器分工；C ABI、两元素 args、入口目录与 `entry_abi`
不变。旧完整 `jit.bin` 保留自身保存/恢复代码，仍可使用原入口；新翻译体必须
配套当前 `wrapper.S` 和 `asm_head.h` 重建，不能把旧的 R11 计数代码拼入新 wrapper。

EFLAGS 不是跨 wrapper 边界的持久状态。相邻 translated 指令会自然使用 CPU
flags，但入口条件的地址比较、dispatcher 的 `CMP` 以及 branch-block budget 的 `INC`/`TEST` 都会
改写 flags，epilogue 也不把 flags 写回 `pt_regs.flags`。所以当前正确性要求原始
代码没有跨这些插桩点存活的 flags；continuation 只能放在函数调用边界等不要求
旧 flags 保持的位置，不能在任意依赖旧 flags 的指令之间退出和恢复。

这只是当前实现的使用限制，翻译器尚未检查 flags 活跃性，也没有自动拒绝违反该限制的
临界区。风险不仅存在于退出/续跑边界：原始代码跨基本块使用 CF/ZF 等状态时，也可能被
block budget 插桩破坏。需要用跨块 `CMP/JMP/Jcc`、`ADC/SBB` 等差分用例验收，
不能由现有复杂状态测试通过推断所有 flags 语义正确。

同理，wrapper 不保存或恢复 XMM/YMM、x87、PKRU、debug/control registers。
当前可翻译临界区不能依赖这些状态跨 sandbox 退出保持。

### 3.1 访问时续跑的前置契约（待实现）

用户于 **2026-09-13 明确继续延期**访问时 guard、原指令处的 waiter 续跑，以及
所需的局部 CF/PF/AF/ZF/SF/OF 保存/恢复。本节仅保留将来重新开展该功能时的
前置契约，**不是当前已有的恢复能力，也不是待确认任务**；通用 flags 修复仍延期。
已有入口条件只能在正文开始前拒绝；普通 CALL miss 的虚拟栈已经压入返回地址，
也不能冒充内存指令前的状态。

| 边界 | RIP / 虚拟栈 | 可否从入口重跑 |
| --- | --- | --- |
| 已有入口拒绝 | 原 entry / 原 SP，未执行正文 | 仅满足完整入口拒绝校验时可走未开始的 native 路径 |
| 已有普通 CALL miss | callee / 已压入源返回地址 | 否，callee 开始原生后缀 |
| 拟新增访问时拒绝 | 尚未执行的源内存指令 / 该指令前的 SP | 否，该指令开始原生后缀 |

未来重新开展实现前必须满足以下条件：

1. 先定义可强制执行的地址/对象范围与生命周期；静态 per-CPU denylist 不足以
   证明未知指针安全。计算一次有效地址，检查宽度、边界及溢出，通过后用同一地址
   执行访问，不能重新读取可被并发改写的指针。
2. 在检查破坏条件码之前保存执行点状态。通过路径恢复原指令需要的条件码；拒绝
   路径还须保存当前 GPR、虚拟 SP 和源 RIP，目的寄存器/内存保持该指令执行前的值。
   不能使用入口的旧 `pt_regs.flags`，也不能在检查完成后才采样条件码。
3. 为这个受检出口定义独立标记和校验，不能复用 `ENTRY_REFUSED`、普通 CALL miss
   或通用 fault。两元素 `args` 不变；条件码是否有效必须有显式状态，不能仅凭
   `pt_regs.flags` 非零判定。完整包校验成功后才发布 native frame。
4. 原 waiter 在恢复当前 GPR/SP 后、第一条续跑指令前恢复所需条件码。拟评估的
   局部范围是 CF/PF/AF/ZF/SF/OF（mask `0x8d5`），不是直接将 combiner 的整个
   RFLAGS 交给 waiter；IF/TF/DF、IRQ、抢占及其他上下文不因此获得切换保证。
   依赖范围外状态的访问必须另行处理，不能据此开放任意隐式指令。
5. 保留此前内存写入与真实 owner，通过原 owner 的 unlock/ACK 完成，不返回本次
   JIT、不重放前缀。验收同时检查通过路径的条件码消费者、拒绝后的第一条指令、
   恰好一次副作用与所有 owner ACK；body witness 单独不足以通过。

现有恢复桩的用户态实测及其非内核测试边界见
[动态指针调查](VALIDATION.md#dynamic-pointer-screening-gap)。完成上述局部契约也
不会修复 dispatcher/budget 的既有 flags 问题，或补齐所有危险指令语义。

## 4. 原生 waiter 的入口快照

### 4.1 Spin 和 mutex 公共 hook 栈布局

本节仅描述 **legacy spin 与 mutex** 的 hook 保存栈。caller-clobber v1
直接接收显式 IP/SP/BP，不解析本节布局，入口捕获见第 1.0 节。

旧入口的原生 waiter 不是从异常入口得到完整 `pt_regs`。hook 调用点已按 C ABI 保存
callee-saved 寄存器。spin 由 origin CPU 的 `kd_spin_prepare_regs()` 在发布前
直接解码到共享 request；旧 ABI mutex 由 `execute_cs()` 重建。二者的 legacy 路径使用以下布局：

```text
[ret_rsp + 0x00] padding / lock 临时槽
[ret_rsp + 0x08] RBX
[ret_rsp + 0x10] R12
[ret_rsp + 0x18] R13
[ret_rsp + 0x20] R14
[ret_rsp + 0x28] R15
[ret_rsp + 0x30] RBP
[ret_rsp + 0x38] RIP，亦即 lock 调用后的 CS 入口
ret_rsp + 0x40   waiter 在 lock 返回后的 RSP
```

因此原生 waiter 明确定义的初始状态只有 RBX、RBP、R12-R15、RIP 和 RSP。
RAX、RCX、RDX、RSI、RDI、R8-R11 作为 lock 函数的 caller-saved 状态，本来就
不能被调用者假定跨 `lock()` 保持：mutex 节点创建时这些字段被清零，spin request
重用时可能保留旧值。翻译代码必须遵守正常内核函数调用 ABI，不能依赖这些
未定义的入口值。

旧 ABI mutex waiter 收到已完成或 native 续跑结果后，`_kd_mutex_lock_abi()` 先将
`resume_node->regs` 复制到自己的局部 `resume_regs`，再清除发布指针、释放
node、恢复抢占/迁移状态，最后使用该副本跳转。node 可能在恢复抢占后立即被
另一请求复用，不能继续从旧 node 读取恢复状态。
生产资源测试在此处主动复用 node 并比较整个 168 字节软件包；它不执行汇编
跳转、不验证硬件 flags 恢复。测试边界见
[历史：mutex 资源与恢复包](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/mutex_protocols.md#61-mutex-资源与恢复包)。

clobber mutex 的 COMPLETE 在 `kd_mutex_resume_completed()` 中只保留三个续点字段；
FULL/native 仍须在释放 node 前保留完整包。新路径直接放弃旧 hook C 帧。

### 4.2 嵌套 JIT waiter

嵌套 spin waiter 不重新解析 native hook 栈。`node->execution` 指向独立 child continuation；
child frame 的 `regs_ref` 引用同一逻辑 root 寄存器包，不复制父 JIT 的 GPR/RIP/RSP。
父请求等待 child frame pop 后的 DONE 才继续；native 链通过根 ticket 借用保活，
不再使用 request `users` 或 `packet_owner`。
它另行保存 owner/control 状态，在发布前把父 lock stack 的有效前缀直接复制到
child frame 并追加 B。combiner 绑定后保留深度、锁类型、重复锁和 outer membership
检查，输入即 child 自身四列时跳过复制，再设置有效深度和 outer index。
child 继承父 frame 的 waiter GS base 和 logical task。B 锁的远端 combiner 更新
同一逻辑包；父级暂停期间使用独立 CALL/锁事实，不把包内变化的值当作旧快照。
`jit_context` 只保留 requester 和预备深度，内嵌于 704 字节 continuation，
与节点槽位的复用独立。虚拟 waiter 缓存 requester，每轮 acquire 检查其远端邮箱；
空邮箱跳过处理函数，有通知则执行原有 owner 检查、解锁和 ACK，不能只等 completed。
父 combiner 的 C 栈仍保留暂停的控制流和局部快照，在 B 返回前必须保持有效，不能将
“续点显式化”理解成“不依赖宿主栈的生命周期”。

mutex B 不再创建虚拟 waiter 或子 frame。A combiner 获取原生 B 后，在同一
frame 记录 `KD_EXEC_LOCK_NATIVE`，然后才弹出 lock CALL 的返回地址。等待 B 期间
保留父级 GPR/RIP/RSP/GS/task，获取后在同一 artifact 执行 B 内的指令。

顶层 spin/mutex waiter 在入队的 origin CPU 上记录
`cpu_kernelmode_gs_base(cpu)` 和 `current`，不使用 artifact 全局的
`exe->gsbase`。nested spin 继承父请求捕获的上下文，mutex B 保持同一 frame。
旧 futex 入口及其 `task_cpu(task)` 查询辅助函数已移除，不能再将任意 task
的即时 CPU 采样当作已固定的 origin 上下文。此清理没有切换硬件 GS，也没有
补全一般 per-CPU 并发语义。

## 5. Wrapper 私有栈布局

三个入口保留相同的 JIT 私有槽偏移，但序言保存不同：偏移 0 的普通 C ABI
入口保存 RBP、RBX、R12–R15；偏移 16 的旧批次入口只预留这六个字的位置，
物理 RBP 由调用适配器保护；偏移 32 的新入口只压入 RBP，预留其余五个字。
批次调用者编译器按 clobber 管理其他活跃值。以下偏移均相对物理 RBP：

| 偏移 | 宏 | 内容 |
| --- | --- | --- |
| `-0x30` | `Stack_PT_REG` | 原 `struct pt_regs *` |
| `-0x38` | `Stack_ARG_REG` | 原 `args *` |
| `-0x40` | `Stack_BUDGET` | 本次调用的 block 额度计数，复用空出的槽 |
| `-0x48` 至 `-0x70` | 保留空间 | 不初始化、不用作 GPR 副本，保持控制槽偏移 |
| `-0x78` | `Stack_RGS` | 入口 `args[0]`，waiter kernel GS base |
| `-0x80` | `Stack_TASK` / `Stack_RCT` | 入口 `args[1]`，logical waiter task |
| `-0x88` | `Stack_RIP` | 退出 RIP 临时槽 |
| `-0x90` | `Stack_IJ` | 退出原因或 IJ 源地址 |
| `-0x98` | `Stack_JIT_WITNESS` | 复用旧计数槽；prologue 写 0，观测用生成块写 1 |
| `-0xa0` | `Stack_BATCH` | 旧批次描述指针 |
| `-0xa8` | `Stack_CLOBBER` | 新 ABI 描述指针 |

两个输入指针入栈后，一次 `sub rsp, 14*8` 分配保留空间与控制槽；prologue
显式清零 `Stack_JIT_WITNESS`，dispatcher 清零 `Stack_BUDGET`。
正常退出桩必须先定义 R14 和 `Stack_IJ`，再跳到公共
`exit`。

`Stack_TASK` 直接复用旧的第二个 segment 槽；`Stack_RIP` 及其后的物理偏移
没有变化。`Stack_RCT` 是翻译器对同一槽位的别名，不会增加栈槽或
`args` 元素。`Stack_RGS` 和 `Stack_RCT` 是每次 wrapper 调用内只读的输入。

## 6. Translated code 的物理寄存器分工

进入 `jit.S` 后，R14/R15 已不再长期保存输入指针。`regs` 在物理 R11 和
`Stack_PT_REG` 中保持，`args` 指针保存在 `Stack_ARG_REG`，供 epilogue 使用。

| 物理寄存器 | translated code 中的角色 |
| --- | --- |
| RAX、RBX、RCX、RDX、RSI、RDI、R8-R10 | guest 同名寄存器，直接执行 |
| R11 | 固定 `REG_BANK` 指针；guest R11 位于共享 `pt_regs.r11` / 映射池 |
| R12 | 特殊寄存器映射池；每个 block 初始代表虚拟 RBP |
| R13 | 特殊寄存器映射池；每个 block 初始代表虚拟 RSP |
| R14 | 映射池；在 dispatcher/退出桩中固定表示当前 RIP 或目标 RIP |
| R15 | 映射池；IJ miss 退出时固定表示源 RIP |
| RBP | wrapper 的真实 frame pointer，独立控制/上下文槽基址 |
| RSP | wrapper 的真实 stack pointer，不是 guest RSP |

### 6.1 R11-R15、RSP、RBP 的动态映射

`conflict.py` 把以下 guest 状态定义为 special registers：

```text
RIP, RSP, RBP, R11, R12, R13, R14, R15, GS, CT, T1, T2
```

每个 translated basic block 的初始映射只有：

```text
physical R13 -> virtual RSP
physical R12 -> virtual RBP
physical R14 -> free
physical R15 -> free
```

当原指令访问 guest R11-R15 或 RIP 时，translator 从物理 R12-R15 中选择可用
寄存器；被驱逐的 guest 值先写入对应 `Stack_R*`。若临时借用 R12/R13，指令后
`recover_stable()` 会恢复虚拟 RBP/RSP。block 结束时 `release_conflict()` 把仍在
映射池中的 guest R11-R15 写回 spill 槽。

所以不能假定“guest R14 永远在 physical R14”或“guest R15 永远在 physical
R15”。只有 dispatcher 和退出协议对 physical R14/R15 的含义是固定的；生成
普通指令必须经过 register map。

### 6.2 RIP 和计数器

- dispatcher 先执行 `Stack_BUDGET = 0`，再把 `pt_regs.ip` 读入 R14，并跳到匹配的
  `loc_<rip>` 标签。hostcall/known-call continuation 也通过同一张入口表恢复。
- translated block 需要 RIP-relative 值时，translator 以当前原始指令地址生成
  immediate，而不是让 guest 直接读 wrapper 的真实 RIP。
- 分支 block 入口递增 `Stack_BUDGET`，并测试 bit 24；命中后以
  `KD_EXE_INST_LIMIT` 退出。该槽在每次 wrapper 进入时重新清零，因此这是单次
  sandbox 运行的 branch-block budget，不是整个临界区的精确 retired-instruction
  数。


### 6.3 GS 和 logical `current`

spinlock 和 mutex 的生产准入默认均允许显式 GS 内存读、写和 RMW，
以及受支持的 current_task 读取；两种被代理 waiter 都在禁止抢占状态下轮询等待。
FS、直接 segment/base 操作和尚未实现 lowering 的隐式 GS string/XLAT 仍拒绝。

翻译器不写硬件 GS base。普通 GS 操作数降为显式
`[Stack_RGS + offset]`；匹配 current_task 偏移的 64-bit MOV 则从
`Stack_RCT` 取得 logical waiter。写入/RMW current_task 不允许。
原 waiter 在入队 origin CPU 上捕获 GS/task，嵌套 spin 继承，mutex 保持同一 frame。

原 waiter 从发布请求前到 acquire 观察到完成或 native handoff 一直禁止抢占，
等待循环只有 cpu_relax（x86 PAUSE），不调用 schedule/cond_resched，不睡眠。
这防止 origin CPU 上其他任务替换该 waiter，但不能排除 IRQ/NMI 对同一 per-CPU
数据的访问，也不切换 IRQ/RCU 上下文；native service 的真实 current/GS 仍属于
combiner。已排除的普通 CALL native 后缀在 waiter 上运行，但这也不消除
borrowed mutex 的 owner-sensitive 限制。

准入范围、IR 内存/别名分析与边界只维护在 DESIGN 第 7 节。
原 waiter pin、稳定 origin 引用、物理 owner 和 ACK 放在锁/frame 元数据，
不占 wrapper args 或保存寄存器槽。

## 7. 虚拟栈和函数调用

translated `PUSH`、`POP`、`CALL`、`RET`、`LEAVE` 全部操作 virtual RSP，通常是
physical R13 指向的 waiter 逻辑栈。它们不能使用 native `CALL`/`RET` 操作
wrapper 实栈来模拟 guest 调用。

当前降级规则：

1. `CALL target` 先把原指令的 post-CALL RIP 压入 virtual stack，再 `JMP` 到
   translated target 或对应退出桩。
2. 已翻译 callee 的 `RET` 从 virtual stack 弹出目标，经 IJ table 跳到匹配的
   `loc_<rip>`。这里匹配的是该 RET 的白名单目标，不保证与原 CALL 一一对应；
   多调用点或共享尾部保留全部后继，改写返回槽可能跳到另一个调用点的后继。
   分析器可按已证明的 RSP 事实分区，并用确切返回槽数值收窄效果传播；未知或
   部分改写仍保留全部可能目标。这不改变运行时白名单、虚拟栈或 wrapper ABI。
   scoped 分析因此检查全部生成返回边，而非假设虚拟调用栈平衡。
3. 普通 call miss 保留虚拟 CALL frame，以原始 callee RIP、当前 GPR/RSP 返回
   原 waiter 执行 native callee；其 `RET` 使用保留的返回地址到达 post-CALL RIP。
4. control call 和 hostcall 必须保留这个 CALL frame，kernel handler 才能从
   `[regs->sp]` 取得 post-CALL continuation。

第 3 项保留已执行的共享内存和 waiter 栈写入，不做事务回滚，也不再覆盖为入口
快照。combiner 保留物理锁，通过 native unlock 请求完成交接；B 已完成时不会
重做 B，B 仍持有时不会先释放 B 再续跑。实现和 BCD 对比见 `DESIGN.md` 9.5/9.6。
按用户要求暂不扩展 flags ABI。普通 CALL miss 和尚未开始获取 B 的资源失败
使用完整 CALL 边界；这不涵盖基本块预算退出。

spin 的 ticket 满表 `E2BIG` 可发生在 CALL 已暂时推进之后。恢复依据是仍为
PENDING 的 `control_call.target/stack/return_ip`，不是入口寄存器快照。
旧 gate 已删除，不存在 gate 容量 ENOMEM 或对 KD 对象使用 Linux 锁回退。
生产单元比较完整 168 字节软件包，不代表硬件 flags 采样或任意指令续跑能力。

## 8. Sandbox 退出 ABI

公共 epilogue 约定：

```text
pt_regs.ip = physical R14
pt_regs.sp = physical R13
pt_regs.bp = physical R12
args[0]    = Stack_IJ
args[1]    = Stack_JIT_WITNESS   (0/1，只供观测)
```

其余受支持 GPR 也写回 `pt_regs`。退出桩的具体协议如下：

| 原因 | R14 / `regs->ip` | `args[0]` | virtual CALL frame |
| --- | --- | --- | --- |
| `SYSCALL` | syscall 指令 RIP | `0` (`KD_EXE_NORMAL`) | 不适用；高层路径判为错误 |
| 普通 call miss | callee target | `1` (`KD_EXE_CALL_MISS`) | 保留，供 native callee 返回 |
| lock/unlock control call | callee target | `1` | 保留 |
| allowlisted hostcall | service target | `5` (`KD_EXE_HOSTCALL`) | 保留 |
| IJ miss | jump target | IJ 源 RIP，而不是常量 `2` | 不变 |
| block budget 超限 | 最近记录的 block RIP | `4` (`KD_EXE_INST_LIMIT`) | 不变 |
| dispatcher 无匹配 continuation | 请求的 RIP | `2` | 不变；高层路径最终失败 |
| 运行期不支持的指令退出 | 保存的指令 RIP | `3` (`KD_EXE_ERROR_INST`) | 不变；终止失败 |
| 入口不重叠条件不满足 | 原入口 RIP | `6` (`KD_EXE_ENTRY_REFUSED`) | 未执行 body；原 GPR/RSP/内存不变，witness 为 0 |

`KD_EXE_NATIVE_ONLY == -3` 仅是翻译准入状态，不是 wrapper 的退出原因，
不能写入 `args[0]` 来模拟拒绝。静态拒绝的入口不调用 wrapper。

`ENTRY_REFUSED=6` 是生产条件检查的运行期退出，不是 daemon 的 entry status，
也不要与 C 执行函数返回的 `KD_EXE_RUN_NATIVE=6` 混淆。kernel 仅在首次 root、
尚无 continuation/hostcall、RIP/RSP 保持入口且 witness 为零时接受它，清除
保守的 executed 标记并返回 `KD_EXE_NO_RUN`；条件未通过不废弃其他输入可用的
已发布代码。其他时机或错误包返回 `KD_EXE_RUN_ERROR`，不允许入口重放。
非 root 续点的逻辑父子校验及版本限制见
[历史：执行指南](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/entry_admission.md#5-入口条件与嵌套续点)。

`KD_EXE_IJ_MISS == 2` 是 `kd_exe_info.status_code` 的 daemon 状态，不是普通 IJ
miss 时 wrapper 返回在 `args[0]` 的值。wrapper 返回源 RIP，kernel executor
验证后才把 translation entry 发布为 `KD_EXE_IJ_MISS`。

`seg_error`/`seg_error2` 现在都明确写入 `KD_EXE_ERROR_INST == 3`。但
`normal.py` 中的一般内存地址检查指令仍未启用；确定性错误码不代表
sandbox 已经成为内存隔离边界。

`KD_EXE_RUN_NATIVE=6`、`KD_EXE_NATIVE_DONE=7` 和 `KD_EXE_KNOWN_NATIVE=8`
是高层 C 执行结果，不是新增的 wrapper `args[0]` 错误码。输入/输出仍各有两个
元素。只有已验证的 CALL/锁控制边界可以续跑；新的 CALL 次数额度路径见第 9 节。
其他运行错误仍 fail-stop，不能直接套用 CALL 的栈约定。

## 9. Mode 2/5 hostcall 的寄存器续跑约定

mode 2 和 mode 5 的 sandbox 退出及内部返回流程相同：

1. translated `CALL` 把 post-CALL RIP 压到 virtual stack；调用参数仍位于 guest
   RDI、RSI、RDX、RCX、R8、R9，按 x86-64 调用约定解释。
2. hostcall stub 把 service target 放入 physical R14，设置
   `Stack_IJ = KD_EXE_HOSTCALL`，保留 physical R13 指向的 CALL frame 后退出。
3. wrapper 回写后，`regs->ip` 是 service target，`regs->sp` 指向 post-CALL RIP。
4. 未达到调用额度时，`kd_hostcall_dispatch()` 用精确 target 查白名单，并调用固定签名 handler。
   当前 `ktime_get`/`ktime_get_ns` 不读取参数，只把返回值写到 `regs->ax`。
   `int_sqrt`（ID 3）从 `regs->di` 读取完整 64 位无符号参数，将整数平方根写入
   `regs->ax`，不截断参数、不对返回值做有符号 32 位扩展。
5. `advance_after_known_call()` 读取 `*(unsigned long *)regs->sp` 作为 continuation，
   然后执行 `regs->sp += 8` 和 `regs->ip = continuation`。
6. 更新后的完整 `pt_regs` 保存到当前 `kd_exec_frame`，同一个 JIT artifact 再次
   通过 wrapper 进入；executor 先重新写入该 frame 的 GS base/logical
   task，dispatcher 再直接跳到 continuation label。

当前 handler 只显式修改 RAX，其他 guest GPR 保留。新增服务时必须为每个服务
定义参数、返回值和允许 clobber 的寄存器，不能直接按 `regs->ip` 调用任意内核
函数。服务在 combiner 的原生 C 栈执行；这不切换 waiter 上下文，也不扩展
两元素 `args`。完整服务清单和上下文约束见 [DESIGN 8.4](DESIGN.md#84-native-hostcalls)。
每次 `kd_exe_on_call_hl_entry()` 调用内，hostcall 上限为 16，并与普通
known-call 恢复共用 16 次 continuation 检查。嵌套子调用重新计数，提前 outer
unlock 的 OOO 分支还绕过普通 known-call 的上限检查；这不是整个嵌套临界区的
严格全局预算。

第 17 次待处理 CALL 尚未执行时，`kd_jit_call_limit_native()` 检查 frame/锁记录、
无在途 native/remote 请求、原 waiter 栈内的非零返回字以及 callee/return 的源码
驻留；hostcall 另复用 manifest 校验，但不调用服务。成功后保留完整 `pt_regs`、
callee RIP 和 CALL RSP，不弹出 `[RSP]`；清除前一条已完成控制调用的 phase，保存
当前 continuation，返回已有的 `KD_EXE_RUN_NATIVE`。原 waiter 从 callee 入口开始
执行，按正常 CALL ABI 返回后完成原生后缀，unlock 仍等待真实 owner ACK。
本次不回 JIT，也不将注册状态改成 CALL_MISS 请求重新翻译。校验失败或服务已经
执行后才出错，仍不能使用这条路径。它不校验每次访存，不保证并发栈私有性，
也不扩展两元素 args；`KD_EXE_INST_LIMIT` 和已延期的 flags 问题保持原状。

hostcall continuation 位于函数调用之后，因此不能依赖调用前 EFLAGS。外层锁和
当前 `kd_exec_frame` 在 native service 执行期间保持有效。mode 5 在到达最外层
`mutex_unlock` 后还有第二层恢复：mutex combiner 发布完成状态，原 waiter 通过
`jump_to_saved_regs()` 从 unlock 后继续。当前正常阶段有时钟和标量两个服务，
`jit_resume == jit_success == N`，hostcall executed/resumed 各为 `2N`。
加入超额度阶段后，另有不返回 JIT 的
native suffix，必须按 [历史：使用指南 6.13](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/JIT_EXECUTION.md#613-call-次数额度与原生后缀)
核对两类计数，不能沿用历史单时钟服务阶段的等式。

### 9.1 普通 CALL miss 的寄存器观察

`KD_NATIVE_REGISTERS=1` 为 `test_10_native_resume.sh` 增加默认关闭的测试探针，
不修改 wrapper 或生产 `pt_regs` 布局。捕获函数 `kd_resume_register_capture`
是独立汇编 callee，在任何 C prologue 前存储 16 个 GPR，随后按内核
`ASM_RET` 返回。caller 保存并恢复被写入标记的 callee-saved 寄存器；RBP
从未改写，额外使用 64 字节原 waiter 的虚拟/原生栈，CALL 再压入八字节返回地址。

| 检查对象 | 期望值 |
| --- | --- |
| RAX/RBX/RCX/RDX/RSI/R8..R15 | 各自固定标记 XOR `record_id + 1` |
| RDI | 独立请求的捕获缓冲地址 |
| RBP | caller 记录的有效 frame pointer |
| RSP | caller 记录的 callee-entry 栈顶 |
| `[RSP]` | 原始 CALL 后继地址，与 caller 的 RIP-relative LEA 结果一致 |
| `[RSP+8]`、`[RSP+16]` | 两个固定栈标记 XOR 同一请求 seed |
| 返回 RAX、capture 次数 | 指定返回标记 XOR seed，且仅调用一次 |

每条请求都由卸载时的检查器验证；只输出 daemon 停止后启用 `native_regs_armed`
的样本，最多 128 条，遗漏会使测试失败。独立 Python 校验器读取原始小端 GPR
字节，而非只相信内核的 `mask=0`，并将样本与真实 `kd_native begin` 的
task/目标 RIP/RSP 对应。远端祖先可以转递同一个包，但 callee 只能执行一次。
一次原生 CALL miss 之外的握手必须继续满足现有精确副作用、owner 和 ACK 检查。

RBP/RSP/后继 RIP 的期望地址由 caller 生成，并非独立证明所有地址计算。
此探针不检查 RFLAGS、向量寄存器、非 CALL 出口、任意栈对齐或 IRQ/NMI；
纯原生及 guest 用户态对照不能记为 JIT 通过。证据见
[最新寄存器验收](VALIDATION.md)。
当前 mode 0/3 和嵌套 mode 1/4/8 的标记样本通过。mutex learned-depth 另行
通过真实 JIT/容量续跑与保留锁检查，不等于它也运行了这套专用 GPR 标记探针。
其两源码模块扩展使用两层真实 learned CALL，仍沿用同一虚拟 CALL/RET 栈和
两元素 wrapper 输入。跨模块 RET 后到达容量出口的证据不替代本节的全 GPR
标记检查；本地 helper 的后缀及 RET 在容量退出后原生完成。共享 RET 的合流
使用有界分区，控制 CALL 后的栈事实仅在第 10 节受检窗口内保留，不能假定
任意内存与保存 GPR 具有同样的保持约定。

## 10. Nested lock known-call 约定

lock/unlock 和 hostcall 都保留虚拟 CALL frame 后退出。
`regs.ip` 为控制目标，`regs.di` 为原始锁地址。nested handler 成功处理后通常
弹出 post-CALL RIP 并继续同一 artifact；**最终完成的 unlock CALL 不弹出**，
留给原 waiter 的返回 trampoline。A-before-B 时最终边界可以是 B unlock。

spin 虚拟 B 引用同一逻辑寄存器包，保留独立 owner 锁表及 GS/task，使用父 artifact 和 B 续点 RIP。
`frame.entry_ip` 是 artifact 查找键，不必等于实际 `regs.ip`。
mutex B 由 A combiner 真实获取，记录 NATIVE 后才弹 CALL，不创建远端 mutex waiter。
frame/lock depth 都有八项限制；不同后端不得混用。

`control_call` 保存 NONE/PENDING/ENTERED/ACQUIRED/COMPLETE 及原始 callee、
CALL RSP、返回地址。合法 PENDING 资源失败恢复该 CALL 包，保留当前 GPR 和
已完成写入；已经发布/获取的操作不能冒充未开始。native 注册也独立验证 phase。

mutex 控制操作后的有界栈检查增加内部 `STACK_CHANGED` 状态，不改变结构大小或
wrapper ABI。该状态要求 `regs.ip == control_call.return_ip`，
`regs.sp == control_call.stack + 8` 且加法不回绕；检查器还核对原控制目标、CALL
返回地址字和原 waiter 栈范围。它表示锁操作已经完成，原 waiter 从其后继继续，
不能再次执行该 lock/unlock。当前内存和 GPR 不回滚，原 owner 继续持有未释放锁。
窗口不足只在操作前使用 PENDING；普通 COMPLETE、spin 本地操作和损坏包不能
冒用此状态。详细执行流与分析器的受检事实保留见
[历史：栈检查](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/entry_admission.md#53-mutex-控制-call-的栈检查)。

本地 spin 获取后另有内部 `SPIN_NATIVE` tag，不改变结构大小或 ABI。
只有经核对 owner/锁记录、原 waiter 栈中的 CALL token 和相同 post-CALL
RIP/RSP 的 EIO 检查点才可设置；它不恢复原 CALL、不改变 GPR，也不再次获取 B。
native 注册只接受匹配后继的 spin 包，不能借此恢复通用 ACQUIRED 错误。
具体执行流、单元与 live 观测边界见 [历史：受检 spin 续跑](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/spin_protocols.md#611-spin-获取后的受检续跑)。

`KD_JIT_CAPS` 在同一有效设备 lease 上查询这一固定运行时约定。它是独立的
16 字节 ioctl 输出，不占用 `pt_regs`、两元素 args、64 字节 entry 或 24 字节
上传头；也不新增 flags 保存或代码版本保证。字段、兼容处理及使用命令集中在
上述栈检查指南。版本 2 复用原保留字段报告模块 per-CPU 预留区大小，不新增
wrapper 参数；该范围能力与可选的 mutex 栈检查是不同约定。
分析器先应用 CALL 压栈写入，只保留所有可能 RSP 的受检窗口
共同覆盖的事实；窗口外、未知别名和其他控制调用仍保留原有 clobber。

逻辑 requester/resume_target 链不同于物理 CPU 的 parent frame 栈。远端 child
先清 resume_target、pop 子 frame，再 release-store DONE，此后不访问已交接的现场；
parent 即使没有本地锁，也必须等 child 退休。native 包可以沿链传播而不再返回 JIT。
零本地锁的合法 native COMPLETE relay 也登记根 ticket 借用，清理/pop 后解除；
它不生成不存在的物理解锁 ACK，也不替原线程 unpin。

A 早释放由真实 owner 回调处理，B owner 不变；旧 combiner 在执行自己的原始
临界区前重新获取 A。回调/批次对象依赖 combiner C 栈寿命，不能仅因寄存器显式化
就提前释放宿主栈。native ACK 位于 waiter 原生栈；spin 最后 ACK 后还须等待所有
执行者解除借用，再由原 waiter 结束自己的 pin，combiner 不能远端解除固定。mutex 则在进入 native 后缀前已
恢复迁移/抢占状态，不把 spin 的 pin 生命周期套用到 mutex。

当前 frame/context/continuation 为 648/5208/704 字节，spin node 为 128 字节、
64 字节对齐。continuation 按 64 字节对齐，frame 起于偏移 32，寄存器包起于 104；
等待和恢复汇编从 `offsetof` 取得偏移，两种 wrapper 的 `pt_regs` 内部布局与输入 ABI 不变。
每 possible CPU 一次预分配 20 KiB，低端 12 KiB 存放 12 条 continuation，
高端 8 KiB 为物理 waiter 等待栈。栈头和记录合计 8512 字节；只由本 CPU 按 top
分配/收缩，远端执行者仅能在 pop 后发布 retired，不扫描空闲引用或搬移活动记录。
node 首行保留链接、execution 与预取地址，通知字段位于第二行偏移 64/65；
数组步长为 128 字节。节点复用不回收 continuation，预取提示不参与恢复。
完整分配、wrapper 栈区与数据流见 [执行路径](../bench/spin_cacheline/EXECUTION_PATHS.md)，
不是动态栈峰值或任意深度安全证明。生产 spin 的 node、combiner 与恢复路径引用
同一份包；frame 的物理链与包引用见 [Frame 协议](design/frames.md#91-frames-and-lock-ledger)。
`pt_regs` 和两元素 args ABI 未改变；mutex 的最小状态与独立 FULL 生命周期见 1.0 节。
精确节点预留、OOO、远端发布和 readmission 约束见 DESIGN 第 4/9 节；
相关测试参数与失败记录集中在使用/验收文档，不在 ABI 中复制历史流水。

## 11. 返回原 waiter

spin 队列普通获取返回 0/2 时直接沿原 C 调用链返回并保持原 IRQ 状态，包括
未分配节点的容量回退。物理 waiter 在连续汇编中先切到 shadow 栈，再发布和轮询；完成或
native 唤醒直接放弃旧调用链，在对齐后的 `min(node->rsp, node->execution->frame.regs_ref->sp)` 下方
建立恢复帧，只保留 continuation 指针和 ticket。普通完成用 `kd_spin_entry_end_pinned()`
退休 ticket 元数据，保留入口 pin 直到最后一次现场读取；native 标记状态并将根记录留在 `kd_spin_native_root`，保留 pin 到所有
执行者退休。`kd_spin_restore_request()` 直接读取共享包；普通完成/重试在全部
读取之后标记记录 retired 并收缩本 CPU top，完成时由保留 GPR 的 `kd_spin_restore_unpin()` 解除 pin 后跳转；重试继续持有 pin，不做软件包快照。
native 有剩余锁时恢复不回收记录，最终解锁经 ACK 和 borrow 等待后回收；无剩余锁
则先等待全部退休，以 mode=3 恢复受检 IP，最后一次现场读取后回收记录。
未执行正文的 retry 返回 4 仍保留已持有的 ticket；虚拟 waiter 保留 1/3/5 返回
分类以通知父 frame。它们不再是物理 waiter 的旧 C 栈返回链。

spin 成功代理使用 `kd_spin_restore_request(..., mode=0)`；mutex COMPLETE 使用
`kd_mutex_resume_completed()` 的三字段恢复，FULL/旧 ABI 使用
`jump_to_saved_regs()`。以下只描述 FULL/旧 ABI 的寄存器与续点语义：

1. 从 `pt_regs` 装入 R15、R14、R13、R12、RBP、RBX、R11、R10、R9、R8、
   RAX、RCX、RDX、RSI、RDI。
2. 把真实 RSP 切换为 `regs->sp`。
3. 执行 `retq`，从 virtual CALL frame 栈顶取得 post-unlock RIP。

该函数不会跳到 `regs->ip`；成功退出时该字段通常仍是 outer unlock target，
OOO 完成时也可以是最后一个 B unlock target。真正的续点来自 `[regs->sp]`，
因此 final unlock CALL 不能先被 known-call 弹掉。

spin 的普通 CALL miss 使用 `kd_spin_restore_request(..., mode=2)`，mutex 使用
`jump_to_saved_regs_in_cs()`：切换到 `regs->sp` 后先压入 `regs->ip`，再 `retq`。这里的 IP 是退出时原始 callee 地址，
不是原始 CS entry，也不是 JIT 机器码地址；callee 所需的返回地址仍在虚拟栈顶。
普通目标在转交前取得源码 residency pin；失败属于不可续跑出口，不重跑入口。
spin 的批次 lease 覆盖所有请求的 native/remote 后缀与实际 pop；mutex 的 push
仍逐 frame 持有会话执行引用。spin 根 ticket 的 native 借用保证所有执行者退休前
根记录仍然有效，普通父子完成则依赖 pop 后的 DONE 顺序。
即使 frame 已标为 ERROR/COMPLETE，只要 native 请求尚未清空或解锁路由仍挂接，
pop 就返回 `-EBUSY`，不复制输出寄存器、不清除存储、不释放会话引用。正常退出
native 正常退出仍由 owner 完成请求并发布物理 ACK 后调用 pop；spin 最后一个
ACK 的 waiter 日志在退休等待结束后输出，不能将日志顺序等同于物理 ACK 发布顺序。
这不增加寄存器字段或 native 出口。普通 spin 不保存或恢复 IRQ flags，
也不从 JIT 虚拟执行重建 live condition codes；既有 flags 语义限制仍在。
当前 SELFTEST 改为验证 pop 前逻辑 task 仍存活、寄存器包/上下文未损坏，
pop 后 `kd_exec_frame_validate()` 拒绝访问；最终 native 返回前必须完成退休。
旧的“waiter TID 先退出、frame 后 pop”时序仅是历史记录，不能作为新协议验收。
这仍是软件包与协议观测，不是实时 GPR/flags 恢复测试。覆盖边界见
[continuation 验证](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#continuation-validation)。
这些引用及独立 source ioctl 不增加 wrapper 参数，也不改变保存的寄存器包；
退休顺序和 hook reader 边界见 [DESIGN 3.1](design/lifetimes.md#31-source-lock-and-hook-lifetimes)。

队列返回值 `5` 表示 native 续跑，既不是原生获取锁后从入口返回，也不是已完成
整个 CS。物理 waiter 恢复到 native 代码；虚拟 spin B waiter 则向 A 传递同一份退出
寄存器，不弹栈、不回到 JIT。mutex 在释放节点和恢复 preempt/migrate 状态后跳转。

combiner frame 在 native 执行期间仍存活并保留物理锁；native unlock hook 将
请求交给拥有该锁的 executor 处理。ack 放在 waiter 自己的 native 栈上，避免
frame 清除后 waiter 仍轮询已释放内存。spin 的 ACK 携带原 waiter 的凭证，
物理 ACK 不解除 executor 借用：executor 清理/pop 后才 `borrow_put()`。
waiter 确认已无剩余解锁路由后等待全部借用（包括无锁 relay）归零，回收根记录
并 `end()`；不能远端解除固定。发布 native 唤醒后，combiner 不再读取或
二次完成那个可能已被复用的队列节点。详见 `DESIGN.md` 9.5。

该固定按 waiter 的 origin 请求计数，不按继承的锁数计数：一个 root 请求借用
远端 A/B 两个 frame 时，两个 `borrow_get()` 共用 root 的一次抢占固定；此例
native 期间 `preempt_count=1`，最后一个 ACK 且所有借用者退休后恢复为 0。不能用源码的两层
`spin_lock()` 推断 waiter 计数为 2，也不能据此声称所有原生上下文数值都被重建。

已由 combiner 获取的 mutex，其原生 owner 仍是 combiner，不会写成 waiter。waiter 仅借用其持锁
保护执行 native 后缀；在途 task 记录保持改名后的 mutex unlock hook 路由，
combiner 完成最后的解锁通知时减少 acquisition 引用再 ack。最后一个引用将
记录从查找表移除，内存与真实 task 引用在 RCU 读者退出后的回调中释放。
这些状态不占用 wrapper args；真实协议探针与构造寄存器包的边界见
[历史：生命周期测试](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/mutex_protocols.md#62-task-引用最终-ack-与-rcu)。

独立任务的 native frame 可以同时存活；通知按 logical task、backend 和锁地址
匹配，每个 waiter 使用自己原生栈上的 ACK 包，不共享一个全局返回包。
[历史：双队列测试](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/native_protocols.md#66-独立队列的并行-native-frame) 使用真实 JIT 续点
和两种排空顺序检查身份及 ACK 隔离，但不新增寄存器或 wrapper 参数，也不代替
完整 GPR/返回栈测试或带存活读者的 RCU 测试。

若同一 CPU 的 context 属于另一 combiner，`execute_cs()` 在 wrapper/frame push
之前返回 NO_RUN。该未执行 waiter 走原生获取和原始 CS；不能复用另一 task 的
寄存器包，也不能把这个入口路径用于已经执行的 JIT。
[历史：同 CPU 用例](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/mutex_protocols.md#67-同-cpu-的-mutex-jit-拒绝) 验证拒绝身份和另一个
frame 的续跑/ACK 不受干扰，但仍不替代完整 GPR 采样。
其满槽扩展还检查未预留 node 的请求使用自己的原生栈等待并取得原锁；该请求
没有 JIT 寄存器包或 owner ACK，不修改另一任务的续跑状态，也不扩展 wrapper ABI。

控制 CALL 的阶段和原始 callee/栈包见第 10 节。原有资源恢复只允许
PENDING 的 `-ENOMEM`/`-E2BIG` 续跑：
spin 为构造远端请求而暂存的 post-CALL RIP/RSP 恢复到原始 CALL 位置；mutex
此时还没有消费 CALL。当前 GPR 和已完成内存写入不回退。已入队、已获取 B、
无效状态，或 A 已解锁但当前 frame 已无未释放本地锁的情况，不进入这个恢复分支。
PENDING 诊断追加 `outer_released` 和 waiter `task`，便于关联真实 lock CALL 与
native begin；不将 ENTERED/ACQUIRED/COMPLETE 失败改成可重试。

native 注册入口现在也独立检查 phase，不再只在 A 已释放时检查。仅 NONE、
目标/RSP/返回地址有效的 PENDING，以及已验证的 spin remote-native COMPLETE
relay 和第 10 节独立的 mutex STACK_CHANGED、spin SPIN_NATIVE 可以登记；其他阶段在借用引用、
发布 frame 和修改计数前拒绝。这两种受检 tag 必须匹配已完成 CALL 的后继 RIP/RSP，
不能再次执行该控制操作。A 仍被持有不代表任意已发布/已获取阶段都可恢复。
此检查不改变 flags 或两元素 args，也不授权任意后期错误恢复。
首次收紧 phase 的历史验收见 [phase 检查](VALIDATION.md#native-registration-phase-guard)，
栈检查的逐字节/坏包证据见 [运行时验收](VALIDATION.md#mutex-control-stack-check)，
真实持 B 者写入 waiter 栈槽、post-CALL 包和两次 ACK 的证据见
[并发栈变化验收](VALIDATION.md#real-mutex-stack-mutation)。

spin 的本地 shadow 持锁表容量检查也放在 CALL 推进和获取 B 之前；满表时保持
PENDING，原始 RIP/RSP 不会被消费。这张 CPU 本地表与 logical frame 的八项
持锁表不同。底层原生排队遇到满表则保留物理锁、原始 `node->rsp` 和父 combiner
状态，只释放一次节点并通知后继等待正常 unlock；不创建新 JIT frame。

pending mutex B 若由 native waiter 首次获取，其 owner 是 waiter；之前由
combiner 获取的 A/B 则仍通过 owner 通知解锁。pending spin B 在 native ticket
状态下获取 KD 单锁字，不使用 Linux 锁协议，也不新发布 JIT B 请求。两者均保留嵌套 helper 的返回链，
不回退先前副作用。

普通 `mutex_lock(B)` 原生等待期间收到 SIGUSR1/SIGKILL，不改变当前 CALL 包、
寄存器续点或 owner ACK 义务。waiter 完成不可中断的 B 获取及后缀，最终 ACK
返回后才能到达用户态信号处理/退出边界；不得因信号改用入口快照或丢弃 frame。
直接调用 `mutex_lock_interruptible/killable(B)` 的普通 CALL miss 则保留实际
API 的 callee RIP 和返回栈。Linux 在原 waiter 上返回 `-EINTR` 时，原生错误
分支不进入或解锁 B；若信号/释放竞争返回 0，则 waiter 真正取得 B 并自行解锁。
两条分支均完成之前借用 A 的 unlock/ACK。该返回值由原生 callee 按正常 C ABI
返回，不由 combiner 伪造，也不重新进入本次 wrapper。获取后的最终 ACK 可早于
信号；测试客户端只在用户态等待该信号，不修改寄存器包或生产 frame 生命周期。
这两类路径的实际 JIT 测试及其限制见
[历史：原 waiter 信号测试](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/native_protocols.md#64-原-waiter-的信号与退出)，不新增 wrapper 状态。

两个恢复函数都不恢复 EFLAGS、硬件 segment base 或 SIMD/FPU。
这些限制不能由寄存器观察测试通过推断为已解决。

## 12. 修改 JIT 时必须保持的约束

1. physical RSP/RBP 始终属于 wrapper，guest RSP/RBP 必须经过 R13/R12 和
   register map。
2. 普通 translated 指令不得硬编码 guest R11-R15 的物理位置。
3. 跳到公共 `exit` 前，必须完成 special-register spill，并定义 R14 和
   `Stack_IJ`。
4. control call、hostcall 和普通 call miss 都必须保留 virtual CALL frame；
   普通 miss 的 native callee 需要其中的返回地址，不能提前弹出。
5. 新增返回 JIT 的可恢复出口时，必须把 post-call RIP 加入入口 dispatcher 的
   continuation label 集合；普通 CALL miss 续跑原生代码，不重新进入 dispatcher。
6. native handler 只能通过 `pt_regs` 读取 guest 参数、写回明确声明的结果，
   且必须定义失败、重试和 side-effect 语义。
7. `args[0]`/`args[1]` 在入口时必须分别为 waiter kernel GS base 和 logical
   task，每次 continuation 都必须重新安装；返回后 `args[1]` 是 0/1 body witness，
   不能当作指令计数或未执行任何副作用的证明，也不能据此决定回退重跑。
8. 不得依赖硬件 FS/GS 切换。GS 使用固定 origin base，`current_task` 使用 logical
   waiter；等待结果时不得解抢占，IRQ/NMI 和 native service 的上下文仍有边界。
9. EFLAGS 和 SIMD/FPU 状态仍不是完整的跨边界 ABI。
10. 修改 `struct pt_regs` 偏移、wrapper push 顺序或 `Stack_*` 宏时必须同步修改
   三者，并反汇编最终 `jit.bin` 验证实际编码。
