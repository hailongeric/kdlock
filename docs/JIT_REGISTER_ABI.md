# kdlock JIT 执行与寄存器 ABI

本文以当前 x86-64 内核 spin/mutex 实现为准，描述入口、wrapper、退出及原 waiter
续跑的寄存器/栈约定。使用与执行流见 [JIT_EXECUTION.md](JIT_EXECUTION.md)，
锁和 frame 生命周期见 [DESIGN.md](DESIGN.md)，结果见
[VALIDATION.md](VALIDATION.md#cross-window-cfg-completion)。

唯一执行入口是 frame-backed `kd_exe_on_call_hl_entry()`。两元素输入保持
`{waiter GS base, logical waiter task}`，不增加 FS base 或第三个 task 元素。
GS lowering helper 保留，但生产准入拒绝保留 JIT 范围中的 GS 内存操作。
普通直接 CALL miss 后原 waiter 原生完成后缀，不返回本次 JIT；它不是入口重试。
本文件只说明已实现的状态契约，不保证 flags、任意指令或任意故障恢复正确。

## 1. 状态边界

一次代理执行经过以下状态转换：

```text
native waiter hook stack
        |
        | build/copy struct pt_regs
        v
kd_exec_frame.regs
        |
        | virt_ptr(regs, args)
        v
wrapper real stack + translated register state
        |
        | exit writes back pt_regs and args[]
        v
kernel executor / known-call / hostcall
        |
        | optionally update RIP/RSP and call the same artifact again
        v
final pt_regs -> original waiter resume
```

这里必须区分三种栈：

| 栈 | 当前表示 | 用途 |
| --- | --- | --- |
| waiter 逻辑栈 | `pt_regs.sp`，JIT 内主要由物理 R13 表示 | 原临界区的局部变量、保存寄存器和虚拟 `CALL` 返回地址 |
| wrapper 实栈 | 物理 RSP | 保存 combiner 的 C ABI 状态和 JIT 私有槽；不能当作 guest RSP 使用 |
| lock shadow stack | spin/mutex 后端保存的真实内核栈 | 运行 queue/combiner C 代码；不等于 JIT 的虚拟调用栈 |

`struct pt_regs` 是 wrapper 调用之间的规范寄存器状态。嵌套锁或 hostcall
退出 sandbox 后，任何需要再次进入 JIT 的状态都必须先落实到这份结构中。

## 2. JIT 函数调用 ABI

生成的代码块从 `wrapper.S:main` 开始，C 侧按以下类型调用：

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
当前代码不得读取返回后的 `args[1]` 作为执行计数：R11 中虽有运行时 block
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

当前 wrapper 的字段语义如下：

| 字段 | 进入 JIT | 退出 JIT |
| --- | --- | --- |
| RAX、RBX、RCX、RDX、RSI、RDI、R8-R10 | 直接装入同名物理寄存器 | 从同名物理寄存器写回 |
| R11-R15 | 先保存到 wrapper 私有槽，按需映射到 R12-R15 | 从私有槽写回 |
| RSP | 装入物理 R13，作为虚拟 RSP | 从物理 R13 写回 |
| RBP | 装入物理 R12，作为虚拟 RBP | 从物理 R12 写回 |
| RIP | 由入口 dispatcher 读取；控制流中作为合成地址处理 | 从协议寄存器 R14 写回 |
| `orig_rax`、CS、EFLAGS、SS | 不装入 translated state | wrapper 不修改 |

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

## 4. 原生 waiter 的入口快照

### 4.1 Spin 和 mutex 公共 hook 栈布局

原生 waiter 不是从异常入口得到完整 `pt_regs`。hook 调用点已经按 C ABI 保存
callee-saved 寄存器，`execute_cs()` 按以下布局重建临界区入口：

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
不能被调用者假定跨 `lock()` 保持：mutex 节点创建时这些字段被清零，spin 节点
重用时可能保留旧值。翻译代码必须遵守正常内核函数调用 ABI，不能依赖这些
未定义的入口值。

### 4.2 嵌套 JIT waiter

嵌套 spin waiter 不重新解析 native hook 栈，而是通过
`node->regs = *regs` 复制父 JIT 的完整 GPR/RIP/RSP 快照，复制显式 lock stack，
并继承父 frame 的 waiter GS base 和 logical task。
这使 B 锁的远端 combiner 可以从显式寄存器状态继续代理 A 的执行流。
`jit_context` 位于初始化分配的 per-CPU 池，按请求节点槽位使用；父 combiner
的 C 栈仍保留暂停的控制流和局部快照，在 B 返回前必须保持有效，不能将
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

`wrapper.S` 先建立真实 RBP frame 并保存宿主 callee-saved 寄存器，随后建立
以下 JIT 私有槽。偏移均相对物理 RBP：

| 偏移 | 宏 | 内容 |
| --- | --- | --- |
| `-0x30` | `Stack_PT_REG` | 原 `struct pt_regs *` |
| `-0x38` | `Stack_ARG_REG` | 原 `args *` |
| `-0x40` | `Stack_RBP` | guest RBP spill |
| `-0x48` | `Stack_RSP` | guest RSP spill |
| `-0x50` | `Stack_R15` | guest R15 spill |
| `-0x58` | `Stack_R14` | guest R14 spill |
| `-0x60` | `Stack_R13` | guest R13 spill |
| `-0x68` | `Stack_R12` | guest R12 spill |
| `-0x70` | `Stack_R11` | guest R11 spill |
| `-0x78` | `Stack_RGS` | 入口 `args[0]`，waiter kernel GS base |
| `-0x80` | `Stack_TASK` / `Stack_RCT` | 入口 `args[1]`，logical waiter task |
| `-0x88` | `Stack_RIP` | 退出 RIP 临时槽 |
| `-0x90` | `Stack_IJ` | 退出原因或 IJ 源地址 |
| `-0x98` | `Stack_JIT_WITNESS` | 复用旧计数槽；prologue 写 0，观测用生成块写 1 |

`Stack_RIP`、`Stack_IJ`、`Stack_JIT_WITNESS` 由一次 `sub rsp, 24` 分配；prologue
显式清零 `Stack_JIT_WITNESS`。正常退出桩必须先定义 R14 和 `Stack_IJ`，再跳到公共
`exit`。

`Stack_TASK` 直接复用旧的第二个 segment 槽；`Stack_RIP` 及其后的物理偏移
没有变化。`Stack_RCT` 是翻译器对同一槽位的别名，不会增加栈槽或
`args` 元素。`Stack_RGS` 和 `Stack_RCT` 是每次 wrapper 调用内只读的输入。

## 6. Translated code 的物理寄存器分工

进入 `jit.S` 后，R14/R15 已不再长期保存输入指针。原指针只保存在
`Stack_PT_REG` 和 `Stack_ARG_REG`，到 epilogue 才重新装回。

| 物理寄存器 | translated code 中的角色 |
| --- | --- |
| RAX、RBX、RCX、RDX、RSI、RDI、R8-R10 | guest 同名寄存器，直接执行 |
| R11 | translated basic-block budget 计数器；guest R11 位于 spill 槽/映射池 |
| R12 | 特殊寄存器映射池；每个 block 初始代表虚拟 RBP |
| R13 | 特殊寄存器映射池；每个 block 初始代表虚拟 RSP |
| R14 | 映射池；在 dispatcher/退出桩中固定表示当前 RIP 或目标 RIP |
| R15 | 映射池；IJ miss 退出时固定表示源 RIP |
| RBP | wrapper 的真实 frame pointer，所有 `Stack_*` 宏的基址 |
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

- dispatcher 先执行 `R11 = 0`，再把 `pt_regs.ip` 读入 R14，并跳到匹配的
  `loc_<rip>` 标签。hostcall/known-call continuation 也通过同一张入口表恢复。
- translated block 需要 RIP-relative 值时，translator 以当前原始指令地址生成
  immediate，而不是让 guest 直接读 wrapper 的真实 RIP。
- 分支 block 入口递增 physical R11，并测试 bit 24；命中后以
  `KD_EXE_INST_LIMIT` 退出。R11 在每次 wrapper 进入时重新清零，因此这是单次
  sandbox 运行的 branch-block budget，不是整个临界区的精确 retired-instruction
  数。


### 6.3 GS 和 logical `current`

生产准入拒绝保留 JIT 范围中的所有 GS 内存操作，包括只读及 current_task
读取；FS/base 操作也不受支持。下述是保留并由单元测试覆盖的 lowering helper，
不是生产代理许可。

翻译器不写硬件 GS base。普通 GS 操作数降为显式
`[Stack_RGS + offset]`；匹配 current_task 偏移的 64-bit MOV 则从
`Stack_RCT` 取得 logical waiter。写入/RMW current_task 不允许。
原 waiter 在入队 origin CPU 上捕获 GS/task，嵌套 spin 继承，mutex 保持同一 frame。

显式地址和 logical task 不切换实际调度、IRQ、RCU 或抢占状态。远端访问 origin
per-CPU 内存仍可能与本地操作冲突；native service 的真实 current/GS 仍属于
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
   `loc_<rip>`。
3. 普通 call miss 保留虚拟 CALL frame，以原始 callee RIP、当前 GPR/RSP 返回
   原 waiter 执行 native callee；其 `RET` 使用保留的返回地址到达 post-CALL RIP。
4. control call 和 hostcall 必须保留这个 CALL frame，kernel handler 才能从
   `[regs->sp]` 取得 post-CALL continuation。

第 3 项保留已执行的共享内存和 waiter 栈写入，不做事务回滚，也不再覆盖为入口
快照。combiner 保留物理锁，通过 native unlock 请求完成交接；B 已完成时不会
重做 B，B 仍持有时不会先释放 B 再续跑。实现和 BCD 对比见 `DESIGN.md` 9.5/9.6。
按用户要求暂不扩展 flags ABI。普通 CALL miss 和尚未开始获取 B 的资源失败
使用完整 CALL 边界；这不涵盖基本块预算退出。

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
[执行指南](JIT_EXECUTION.md#5-入口条件与嵌套续点)。

`KD_EXE_IJ_MISS == 2` 是 `kd_exe_info.status_code` 的 daemon 状态，不是普通 IJ
miss 时 wrapper 返回在 `args[0]` 的值。wrapper 返回源 RIP，kernel executor
验证后才把 translation entry 发布为 `KD_EXE_IJ_MISS`。

`seg_error`/`seg_error2` 现在都明确写入 `KD_EXE_ERROR_INST == 3`。但
`normal.py` 中的一般内存地址检查指令仍未启用；确定性错误码不代表
sandbox 已经成为内存隔离边界。

`KD_EXE_RUN_NATIVE=6`、`KD_EXE_NATIVE_DONE=7` 和 `KD_EXE_KNOWN_NATIVE=8`
是高层 C 执行结果，不是新增的 wrapper `args[0]` 错误码。输入/输出仍各有两个
元素。除已验证的 PENDING 锁获取资源失败外，其他运行错误仍 fail-stop，
不能直接套用 CALL 的栈约定。

## 9. Mode 2/5 hostcall 的寄存器续跑约定

mode 2 和 mode 5 的 sandbox 退出及内部返回流程相同：

1. translated `CALL` 把 post-CALL RIP 压到 virtual stack；调用参数仍位于 guest
   RDI、RSI、RDX、RCX、R8、R9，按 x86-64 调用约定解释。
2. hostcall stub 把 service target 放入 physical R14，设置
   `Stack_IJ = KD_EXE_HOSTCALL`，保留 physical R13 指向的 CALL frame 后退出。
3. wrapper 回写后，`regs->ip` 是 service target，`regs->sp` 指向 post-CALL RIP。
4. `kd_hostcall_dispatch()` 用精确 target 查白名单，并调用固定签名 handler。
   当前 `ktime_get`/`ktime_get_ns` 不读取参数，只把返回值写到 `regs->ax`。
5. `advance_after_known_call()` 读取 `*(unsigned long *)regs->sp` 作为 continuation，
   然后执行 `regs->sp += 8` 和 `regs->ip = continuation`。
6. 更新后的完整 `pt_regs` 保存到当前 `kd_exec_frame`，同一个 JIT artifact 再次
   通过 wrapper 进入；executor 先重新写入该 frame 的 GS base/logical
   task，dispatcher 再直接跳到 continuation label。

当前 handler 只显式修改 RAX，其他 guest GPR 保留。新增服务时必须为每个服务
定义参数、返回值和允许 clobber 的寄存器，不能直接按 `regs->ip` 调用任意内核
函数。每次 `kd_exe_on_call_hl_entry()` 调用内，hostcall 上限为 16，并与普通
known-call 恢复共用 16 次 continuation 检查。嵌套子调用重新计数，提前 outer
unlock 的 OOO 分支还绕过普通 known-call 的上限检查；这不是整个嵌套临界区的
严格全局预算。

hostcall continuation 位于函数调用之后，因此不能依赖调用前 EFLAGS。外层锁和
当前 `kd_exec_frame` 在 native service 执行期间保持有效。mode 5 在到达最外层
`mutex_unlock` 后还有第二层恢复：mutex combiner 发布完成状态，原 waiter 通过
`jump_to_saved_regs()` 从 unlock 后继续；严格测试要求该 `jit_resume` 次数与
hostcall resume 及 `jit_success` 完全相等。

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
[最新寄存器验收](VALIDATION.md#cross-window-cfg-completion)。
当前 mode 0/3 和嵌套 mode 1/4/8 的标记样本通过；mutex learned-depth
仍未通过，不能用普通 CALL 样本代替深层 helper 的 JIT 验收。

## 10. Nested lock known-call 约定

lock/unlock 和 hostcall 都保留虚拟 CALL frame 后退出。
`regs.ip` 为控制目标，`regs.di` 为原始锁地址。nested handler 成功处理后通常
弹出 post-CALL RIP 并继续同一 artifact；**最终完成的 unlock CALL 不弹出**，
留给原 waiter 的返回 trampoline。A-before-B 时最终边界可以是 B unlock。

spin 虚拟 B 复制完整寄存器、显式锁表及 GS/task，使用父 artifact 和 B 续点 RIP。
`frame.entry_ip` 是 artifact 查找键，不必等于实际 `regs.ip`。
mutex B 由 A combiner 真实获取，记录 NATIVE 后才弹 CALL，不创建远端 mutex waiter。
frame/lock depth 都有八项限制；不同后端不得混用。

`control_call` 保存 NONE/PENDING/ENTERED/ACQUIRED/COMPLETE 及原始 callee、
CALL RSP、返回地址。合法 PENDING 资源失败恢复该 CALL 包，保留当前 GPR 和
已完成写入；已经发布/获取的操作不能冒充未开始。native 注册也独立验证 phase。

逻辑 requester/resume_target 链不同于物理 CPU 的 parent frame 栈。远端 child
先清 resume_target，再 release-store DONE，此后不访问 parent；parent 即使
没有本地锁，也必须等 child 完成。native 包可以沿链传播而不再返回 JIT。
零本地锁的合法 COMPLETE relay 不新增借用、ACK 或 unpin。

A 早释放由真实 owner 回调处理，B owner 不变；旧 combiner 在执行自己的原始
临界区前重新获取 A。回调/批次对象依赖 combiner C 栈寿命，不能仅因寄存器显式化
就提前释放宿主栈。native ACK 位于 waiter 原生栈；最后 ACK 后由原 waiter
结束自己的 pin，combiner 不能远端解除固定。

默认实测布局为 frame 656、context 5264、spin JIT context 184、spin node 280
字节，静态 per-CPU 7904 字节。布局不是动态栈峰值或任意深度安全证明。
精确节点预留、OOO、远端发布和 readmission 约束见 DESIGN 第 4/9 节；
相关测试参数与失败记录集中在使用/验收文档，不在 ABI 中复制历史流水。

## 11. 返回原 waiter

spin 队列普通获取返回 0/2 时恢复 `kd_spin_native_input.rsp`，包括未分配节点的
容量回退。非局部返回先恢复 `min(node->rsp, node->regs.sp)`，再在该原生栈上
复制 `pt_regs` 与凭证；这避免覆盖已经长入旧 hook 帧的虚拟 CALL 返回地址。
完成代理的 1/3 路径随后结束自己的 ticket，可能重新调度，因此不得再读取原
per-CPU 节点。返回 5 只标记 native 状态并保留 pin；最后一个 native ack 才
由原 waiter 结束它。返回 4 的旧重试路径不提前消耗仍持有的凭证。

成功代理后使用 `jump_to_saved_regs()`：

1. 从 `pt_regs` 装入 R15、R14、R13、R12、RBP、RBX、R11、R10、R9、R8、
   RAX、RCX、RDX、RSI、RDI。
2. 把真实 RSP 切换为 `regs->sp`。
3. 执行 `retq`，从 virtual CALL frame 栈顶取得 post-unlock RIP。

该函数不会跳到 `regs->ip`；成功退出时该字段通常仍是 outer unlock target，
OOO 完成时也可以是最后一个 B unlock target。真正的续点来自 `[regs->sp]`，
因此 final unlock CALL 不能先被 known-call 弹掉。

spin 和 mutex 的普通 CALL miss 都使用 `jump_to_saved_regs_in_cs()`：切换到
`regs->sp` 后先压入 `regs->ip`，再 `retq`。这里的 IP 是退出时原始 callee 地址，
不是原始 CS entry，也不是 JIT 机器码地址；callee 所需的返回地址仍在虚拟栈顶。

队列返回值 `5` 表示 native 续跑，既不是原生获取锁后从入口返回，也不是已完成
整个 CS。物理 waiter 恢复到 native 代码；虚拟 spin B waiter 则向 A 传递同一份退出
寄存器，不弹栈、不回到 JIT。mutex 在释放节点和恢复 preempt/migrate 状态后跳转。

combiner frame 在 native 执行期间仍存活并保留物理锁；native unlock hook 将
请求交给拥有该锁的 executor 处理。ack 放在 waiter 自己的 native 栈上，避免
frame 清除后 waiter 仍轮询已释放内存。spin 的 ack 同时携带原 waiter 的凭证及
是否为最后一个 native 引用；executor 在发布 done 前完成 `borrow_put()`，waiter
收到最后确认后才 `end()`，不能远端解除固定。发布 native 唤醒后，combiner 不再读取或
二次完成那个可能已被复用的队列节点。详见 `DESIGN.md` 9.5。

已由 combiner 获取的 mutex，其原生 owner 仍是 combiner，不会写成 waiter。waiter 仅借用其持锁
保护执行 native 后缀；在途 task 记录保持改名后的 mutex unlock hook 路由，
combiner 完成最后的解锁通知时释放该记录再 ack。这些状态不占用 wrapper args。

`frame->control_call` 记录 NONE/PENDING/ENTERED/ACQUIRED/COMPLETE 以及原始
callee RIP、CALL RSP、返回地址。仅 PENDING 的 `-ENOMEM`/`-E2BIG` 可续跑：
spin 为构造远端请求而暂存的 post-CALL RIP/RSP 恢复到原始 CALL 位置；mutex
此时还没有消费 CALL。当前 GPR 和已完成内存写入不回退。已入队、已获取 B、
无效状态，或 A 已解锁但当前 frame 已无未释放本地锁的情况，不进入这个恢复分支。
PENDING 诊断追加 `outer_released` 和 waiter `task`，便于关联真实 lock CALL 与
native begin；不将 ENTERED/ACQUIRED/COMPLETE 失败改成可重试。

native 注册入口现在也独立检查 phase，不再只在 A 已释放时检查。仅 NONE、
目标/RSP/返回地址有效的 PENDING，以及已验证的 spin remote-native COMPLETE
relay 可以登记；其他阶段在借用引用、发布 frame 和修改计数前拒绝。A 仍被
持有不代表可恢复已发布/已获取的操作。此检查不改寄存器、flags 或两元素 args，
也不新增后期错误恢复，详见 [phase 检查](VALIDATION.md#native-registration-phase-guard)。

spin 的本地 shadow 持锁表容量检查也放在 CALL 推进和获取 B 之前；满表时保持
PENDING，原始 RIP/RSP 不会被消费。这张 CPU 本地表与 logical frame 的八项
持锁表不同。底层原生排队遇到满表则保留物理锁、原始 `node->rsp` 和父 combiner
状态，只释放一次节点并通知后继等待正常 unlock；不创建新 JIT frame。

pending mutex B 若由 native waiter 首次获取，其 owner 是 waiter；之前由
combiner 获取的 A/B 则仍通过 owner 通知解锁。pending spin B 在 native ticket
状态下走 Linux L，不新发布 JIT B 请求。两者均保留嵌套 helper 的返回链，
不回退先前副作用。

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
8. 不得依赖硬件 FS/GS 切换。GS 内存当前不准入；保留的 GS 显式基址降级和 logical
   `current_task` helper 仅保留代码生成能力和测试，不代表允许生产代理。
9. EFLAGS 和 SIMD/FPU 状态仍不是完整的跨边界 ABI。
10. 修改 `struct pt_regs` 偏移、wrapper push 顺序或 `Stack_*` 宏时必须同步修改
   三者，并反汇编最终 `jit.bin` 验证实际编码。
