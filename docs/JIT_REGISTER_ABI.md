# kdlock JIT 执行与寄存器 ABI

本文记录当前 x86-64 实现中，临界区状态如何进入 JIT、如何在翻译代码中表示，
以及如何退出、续跑并最终恢复到原 waiter。它描述的是现有代码的实际约定，
不是一个与实现无关的目标设计。

适用范围是高层代理路径 `kd_exe_on_call_hl_entry()`，即当前 mode
0/1/2/6/7/8/9/10 和 `mutex_jit=1` 下的 mode 3/4/5/11。低层 futex 路径
`kd_exe_on_call()` 共用相同的两参数 wrapper ABI，但不支持 mode 2/5
使用的 hostcall。本项目当前只定义 x86-64 内核代码的翻译语义。

本文描述的 mode 2/5 退出和续跑约定已经通过独立运行验证；实际入口、服务地址、
计数器和保留日志见 [`VALIDATION.md`](VALIDATION.md)。

关键实现文件：

- `include/wrapper.S`：JIT 二进制入口、寄存器装载和回写。
- `include/asm_head.h`：`pt_regs` 偏移和 wrapper 私有栈槽。
- `include/kd_segment.h`：获取 waiter 所在 CPU 的 kernel GS base。
- `disassem/conflict.py`：虚拟特殊寄存器到 R12-R15 的动态映射。
- `disassem/normal.py`：GS/current 操作数降级和 segment 拒绝策略。
- `disassem/disassem.py`：读取 per-CPU 符号偏移并在产生代码前预检查 segment 指令。
- `disassem/special_inst.py`：`CALL`、`RET`、`PUSH`、`POP` 等指令的降级。
- `disassem/indirect_jump.py`：间接跳转、call miss 和 hostcall 退出桩。
- `kernel_module/exe.c`：退出原因解释、known-call/hostcall 执行和续跑。
- `kernel_module/kd_exec.c`：嵌套执行帧和 continuation 快照。

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
| `args[1]` | logical waiter 的 `task_struct *` | 预留计数输出，当前固定为 0 |

参数数组始终只有两个元素，没有第三个 task 参数。wrapper 在
返回时会覆盖这两个输入，所以 executor 每次首次进入或 continuation
续跑前，都要从当前 `kd_exec_frame` 重新写入 GS base 和 logical task。
当前代码不得读取返回后的 `args[1]` 作为执行计数：R11 中虽有运行时 block
budget，但 epilogue 不会把它复制到 `Stack_INST_CNT`。

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
flags，但入口 dispatcher 的 `CMP` 以及 branch-block budget 的 `INC`/`TEST` 都会
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
但 `jit_context` 本身仍是 A combiner 栈上的对象；该栈在 B 完成前必须保持有效，
不能将“续点显式化”理解成“不依赖宿主栈的生命周期”。

mutex B 不再创建虚拟 waiter 或子 frame。A combiner 获取原生 B 后，在同一
frame 记录 `KD_EXEC_LOCK_NATIVE`，然后才弹出 lock CALL 的返回地址。等待 B 期间
保留父级 GPR/RIP/RSP/GS/task，获取后在同一 artifact 执行 B 内的指令。

顶层 spin/mutex waiter 在入队的 origin CPU 上记录
`cpu_kernelmode_gs_base(cpu)` 和 `current`。低层 futex 入口则使用目标
task 的 `task_cpu(task)` 查找 kernel GS base，并把该 task 作为 logical
waiter。这两条路径都不使用 artifact 全局的 `exe->gsbase`。低层
futex 入口当前仅作为兼容 API 保留，仓库内没有调度/唤醒代理 waiter 的
frontend。

`task_cpu(task)` 只是读取时的 CPU，不等同于顶层 waiter 入队时捕获并保持的 origin
CPU。这个低层 API 本身不负责持有 task 引用或禁止其迁移，尚无完整调用契约。

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
| `-0x98` | `Stack_INST_CNT` | 预留计数槽；prologue 固定写入 0 |

`Stack_RIP`、`Stack_IJ`、`Stack_INST_CNT` 由一次 `sub rsp, 24` 分配；prologue
显式清零 `Stack_INST_CNT`。正常退出桩必须先定义 R14 和 `Stack_IJ`，再跳到公共
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

运行 translated code 时不会执行 `wrgsbase`，也不会把 combiner CPU 的硬件
GS base 切换为 waiter 的值。翻译器将普通 `%gs:offset` 操作数改写为
`[virtual_GS_base + offset]`；virtual GS 从 `Stack_RGS` 加载，因而 MOV 读、
MOV 写和 INC 等 read-modify-write 都访问 origin CPU 的 per-CPU 区。

`current_task` 是特例。daemon 从 `/proc/kallsyms` 计算其 per-CPU 偏移；遇到
64-bit `MOV reg, %gs:current_task` 时，直接从 virtual `CT` / `Stack_RCT`
返回 logical waiter。这避免远端 combiner 读到它自己或 origin CPU 上后续
调度进程的 `current`。对 `current_task` 的写入或 RMW 不允许。

这里保证的是地址来源和 logical task 的替换，不是任意 per-CPU 操作的并发正确性。
远端 combiner 修改 origin CPU 的 per-CPU 内存时，origin CPU 上的中断或其他任务
仍可能同时操作它；`migrate_disable()` 不能防止这类并发。对依赖本地非 LOCK RMW、
抢占计数、IRQ/RCU 或调度状态的代码，需要单独的策略和测试。原生 handler 执行时
硬件 GS 和真实 `current` 仍属于 combiner，不能自动观察到这里的 logical waiter。

当前 fail-closed 策略为：

- `%fs:` 内存操作数不支持，不传入 FS base。
- `rdfsbase`/`rdgsbase`/`wrfsbase`/`wrgsbase`/`swapgs` 和直接 segment
  寄存器访问不支持。
- 其他 segment-prefixed 内存指令不支持。对齐 NOP 携带的 CS 伪操作数会被丢弃并生成普通 NOP。
- miasm 在 daemon 已抓取翻译范围内不能解码的 basic block 整体拒绝。
  范围外的 CALL 目标坏块只是 miss 占位，仍按 call-miss 策略处理。对
  miasm 0.1.5 会错解的 `SWAPGS` 和 FSGSBASE 编码另行按原始字节拒绝。
- 预检查失败时 daemon 生成最小拒绝 artifact，以
  `KD_EXE_ERROR_INST == 3` 退出；kernel executor 将该 entry 标记为终止错误。
  当前高层路径在进入 wrapper 后遇到这种无续跑协议的退出会 fail-stop，不从入口重做。

以上是 segment/解码检查的范围，不是完整指令白名单。当前 `INT` 被生成为 NOP，
部分未处理 special 指令仅打印 warning，一般特权指令也没有统一的拒绝门槛。
不能据此声称任意危险内核指令都能失败关闭；待办见 [`TODO.md`](TODO.md)。

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
本轮按用户要求暂不扩展 flags ABI，只验收普通 CALL miss，不验收基本块预算退出。

## 8. Sandbox 退出 ABI

公共 epilogue 约定：

```text
pt_regs.ip = physical R14
pt_regs.sp = physical R13
pt_regs.bp = physical R12
args[0]    = Stack_IJ
args[1]    = Stack_INST_CNT   (当前固定为 0)
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
| 不支持的 segment/指令 | 被拒绝的入口或指令 RIP | `3` (`KD_EXE_ERROR_INST`) | 不变；终止失败 |

`KD_EXE_IJ_MISS == 2` 是 `kd_exe_info.status_code` 的 daemon 状态，不是普通 IJ
miss 时 wrapper 返回在 `args[0]` 的值。wrapper 返回源 RIP，kernel executor
验证后才把 translation entry 发布为 `KD_EXE_IJ_MISS`。

`seg_error`/`seg_error2` 现在都明确写入 `KD_EXE_ERROR_INST == 3`。但
`normal.py` 中的一般内存地址检查指令仍未启用；确定性错误码不代表
sandbox 已经成为内存隔离边界。

`KD_EXE_RUN_NATIVE=6`、`KD_EXE_NATIVE_DONE=7` 和 `KD_EXE_KNOWN_NATIVE=8`
是高层 C 执行结果，不是新增的 wrapper `args[0]` 错误码。输入/输出仍各有两个
元素。运行中非普通 CALL 的错误目前 fail-stop，不能套用 CALL 的栈约定。

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

## 10. Nested lock known-call 约定

lock/unlock 与 hostcall 使用相同的“保留虚拟 CALL frame 后退出”机制：

- `regs->ip` 标识 `_raw_spin_lock`、`_raw_spin_unlock`、`mutex_lock` 或
  `mutex_unlock`。
- `regs->di` 是第一个 guest 参数，即原始 lock 地址。
- nested lock/unlock 被 handler 消费后，通常弹出 `[regs->sp]` 并从 post-CALL
  RIP 继续同一 artifact。
- 发生远端 spin B 代理时，B waiter 携带完整 `pt_regs`；B 完成后返回的 RIP/RSP/GPR
  再成为 A 的 continuation 状态。
- 最外层 unlock 是临界区完成边界，不能先弹 CALL frame，因为原 waiter 最终
  需要用该栈顶返回地址直接跳过已经代理执行的 unlock。

`kd_exec_frame` 是 nested/hostcall 边界的持久状态，保存 `regs`、entry RIP、
continuation RIP/RSP、waiter GS base、logical task、父 frame 和 lock ownership。
当前 frame depth 和 lock depth 都限制为 8。
`mutex_backend` 记录该 frame 的锁后端，known-call 不允许混用 spin/mutex 处理器。

## 11. 返回原 waiter

成功代理后使用 `jump_to_saved_regs()`：

1. 从 `pt_regs` 装入 R15、R14、R13、R12、RBP、RBX、R11、R10、R9、R8、
   RAX、RCX、RDX、RSI、RDI。
2. 把真实 RSP 切换为 `regs->sp`。
3. 执行 `retq`，从 virtual CALL frame 栈顶取得 post-unlock RIP。

该函数不会跳到 `regs->ip`；成功退出时该字段通常仍是 outer unlock target。
真正的续点来自 `[regs->sp]`。

spin 和 mutex 的普通 CALL miss 都使用 `jump_to_saved_regs_in_cs()`：切换到
`regs->sp` 后先压入 `regs->ip`，再 `retq`。这里的 IP 是退出时原始 callee 地址，
不是原始 CS entry，也不是 JIT 机器码地址；callee 所需的返回地址仍在虚拟栈顶。

队列返回值 `5` 表示 native 续跑，既不是原生获取锁后从入口返回，也不是已完成
整个 CS。物理 waiter 恢复到 native 代码；虚拟 spin B waiter 则向 A 传递同一份退出
寄存器，不弹栈、不回到 JIT。mutex 在释放节点和恢复 preempt/migrate 状态后跳转。

combiner frame 在 native 执行期间仍存活并保留物理锁；native unlock hook 将
请求交给拥有该锁的 executor 处理。ack 放在 waiter 自己的 native 栈上，避免
frame 清除后 waiter 仍轮询已释放内存。发布 native 唤醒后，combiner 不再读取或
二次完成那个可能已被复用的队列节点。详见 `DESIGN.md` 9.5。

mutex 的原生 owner 一直是 combiner，不会写成 waiter。waiter 仅借用其持锁
保护执行 native 后缀；在途 task 记录保持改名后的 mutex unlock hook 路由，
combiner 完成最后的解锁通知时释放该记录再 ack。这些状态不占用 wrapper args。

仍需定义 nested control-call 失败续跑。mutex 现在仅在获取并记录 B 后消费 CALL，
但容量等 post-entry 失败仍是 fail-stop。新增状态位和交接元数据放在 frame/node，
没有扩展两元素 `args`。

两个恢复函数都不恢复 EFLAGS、硬件 segment base 或 SIMD/FPU 状态。
GS 内存语义由翻译后的显式基址寻址实现，不依赖这两个恢复函数切换
硬件 GS。

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
   task，每次 continuation 都必须重新安装；返回后 `args[1]` 固定为 0，不能当作
   有效计数。
8. 不得依赖硬件 FS/GS 切换。只有文档化的 GS 显式基址降级和 logical
   `current_task` 读取受支持；FS、base-register 指令和 `current_task` 写入必须失败关闭。
9. EFLAGS 和 SIMD/FPU 状态仍不是完整的跨边界 ABI。
10. 修改 `struct pt_regs` 偏移、wrapper push 顺序或 `Stack_*` 宏时必须同步修改
   三者，并反汇编最终 `jit.bin` 验证实际编码。
