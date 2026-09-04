# kdlock JIT 执行与寄存器 ABI

本文记录当前 x86-64 实现中，临界区状态如何进入 JIT、如何在翻译代码中表示，
以及如何退出、续跑并最终恢复到原 waiter。它描述的是现有代码的实际约定，
不是一个与实现无关的目标设计。

适用范围是高层代理路径 `kd_exe_on_call_hl_entry()`，即当前 mode 0/1/2 和
`mutex_jit=1` 下的 mode 3/4。低层 futex 路径 `kd_exe_on_call()` 共用 wrapper，
但不支持 mode 2 hostcall。

本文描述的 mode 2 退出和续跑约定已经通过独立运行验证；实际入口、服务地址、
计数器和保留日志见 [`VALIDATION.md`](VALIDATION.md)。

关键实现文件：

- `include/wrapper.S`：JIT 二进制入口、寄存器装载和回写。
- `include/asm_head.h`：`pt_regs` 偏移和 wrapper 私有栈槽。
- `disassem/conflict.py`：虚拟特殊寄存器到 R12-R15 的动态映射。
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
| `args[0]` | 当前传入 `exe->gsbase` | sandbox 退出原因；IJ miss 时为源 RIP |
| `args[1]` | `0` | 对应 `Stack_INST_CNT`，但当前没有初始化/写入，值未定义 |

因此，当前代码不得读取 `args[1]` 作为可靠的执行计数。R11 中虽有运行时
block budget 计数，但 epilogue 没有把它复制到 `Stack_INST_CNT`。

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

嵌套 waiter 不重新解析 native hook 栈，而是通过
`node->regs = *regs` 复制父 JIT 的完整 GPR/RIP/RSP 快照，并复制显式 lock stack。
这使 B 锁的远端 combiner 可以继续代理 A 的执行流，而不依赖 A combiner 的
C 调用栈。

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
| `-0x78` | `Stack_RGS` | 入口 `args[1]` |
| `-0x80` | `Stack_RFS` | 入口 `args[0]` |
| `-0x88` | `Stack_RIP` | 退出 RIP 临时槽 |
| `-0x90` | `Stack_IJ` | 退出原因或 IJ 源地址 |
| `-0x98` | `Stack_INST_CNT` | 预留计数槽；当前未初始化 |

`Stack_RIP`、`Stack_IJ`、`Stack_INST_CNT` 由一次 `sub rsp, 24` 分配，并不会自动
清零。正常退出桩必须先定义 R14 和 `Stack_IJ`，再跳到公共 `exit`。

FS/GS 仍是遗留接口：`asm_head.h` 把 `args[0]` 命名为 `PT_FS`、`args[1]` 命名为
`PT_GS`，但执行器实际把 GS base 放在 `args[0]`，`args[1]` 为零。因此当前
FS/GS 虚拟寄存器的槽位名称和输入不一致，不能视为稳定 ABI。

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
RIP, RSP, RBP, R11, R12, R13, R14, R15, FS, GS, T1, T2
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

## 7. 虚拟栈和函数调用

translated `PUSH`、`POP`、`CALL`、`RET`、`LEAVE` 全部操作 virtual RSP，通常是
physical R13 指向的 waiter 逻辑栈。它们不能使用 native `CALL`/`RET` 操作
wrapper 实栈来模拟 guest 调用。

当前降级规则：

1. `CALL target` 先把原指令的 post-CALL RIP 压入 virtual stack，再 `JMP` 到
   translated target 或对应退出桩。
2. 已翻译 callee 的 `RET` 从 virtual stack 弹出目标，经 IJ table 跳到匹配的
   `loc_<rip>`。
3. 普通 call miss 在退出桩执行 `R13 += 8`，撤销刚才的虚拟 CALL frame；随后
   整个临界区从保存的入口快照进行 native retry/重新翻译。
4. control call 和 hostcall 必须保留这个 CALL frame，kernel handler 才能从
   `[regs->sp]` 取得 post-CALL continuation。

## 8. Sandbox 退出 ABI

公共 epilogue 约定：

```text
pt_regs.ip = physical R14
pt_regs.sp = physical R13
pt_regs.bp = physical R12
args[0]    = Stack_IJ
args[1]    = Stack_INST_CNT   (当前未定义)
```

其余受支持 GPR 也写回 `pt_regs`。退出桩的具体协议如下：

| 原因 | R14 / `regs->ip` | `args[0]` | virtual CALL frame |
| --- | --- | --- | --- |
| `SYSCALL` | syscall 指令 RIP | `0` (`KD_EXE_NORMAL`) | 不适用；高层路径判为错误 |
| 普通 call miss | callee target | `1` (`KD_EXE_CALL_MISS`) | 退出前弹出 |
| lock/unlock control call | callee target | `1` | 保留 |
| allowlisted hostcall | service target | `5` (`KD_EXE_HOSTCALL`) | 保留 |
| IJ miss | jump target | IJ 源 RIP，而不是常量 `2` | 不变 |
| block budget 超限 | 最近记录的 block RIP | `4` (`KD_EXE_INST_LIMIT`) | 不变 |
| dispatcher 无匹配 continuation | 请求的 RIP | `2` | 不变；高层路径最终失败 |

`KD_EXE_IJ_MISS == 2` 是 `kd_exe_info.status_code` 的 daemon 状态，不是普通 IJ
miss 时 wrapper 返回在 `args[0]` 的值。wrapper 返回源 RIP，kernel executor
验证后才把 translation entry 发布为 `KD_EXE_IJ_MISS`。

`seg_error`/`seg_error2` 当前没有建立独立、可靠的 `Stack_IJ` 值；同时
`normal.py` 中实际地址检查指令仍未启用。因此这两个标签不能作为稳定退出 ABI。

## 9. Mode 2 hostcall 的寄存器续跑约定

mode 2 的退出和返回流程为：

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
   通过 wrapper 进入；dispatcher 直接跳到 continuation label。

当前 handler 只显式修改 RAX，其他 guest GPR 保留。新增服务时必须为每个服务
定义参数、返回值和允许 clobber 的寄存器，不能直接按 `regs->ip` 调用任意内核
函数。hostcall 自身上限为 16；hostcall 和 known-call 恢复共同占用每个高层
临界区最多 16 次的 continuation budget。

hostcall continuation 位于函数调用之后，因此不能依赖调用前 EFLAGS。外层锁和
当前 `kd_exec_frame` 在 native service 执行期间保持有效。

## 10. Nested lock known-call 约定

lock/unlock 与 hostcall 使用相同的“保留虚拟 CALL frame 后退出”机制：

- `regs->ip` 标识 `_raw_spin_lock`、`_raw_spin_unlock`、`mutex_lock` 或
  `mutex_unlock`。
- `regs->di` 是第一个 guest 参数，即原始 lock 地址。
- nested lock/unlock 被 handler 消费后，通常弹出 `[regs->sp]` 并从 post-CALL
  RIP 继续同一 artifact。
- 发生远端 B 代理时，B waiter 携带完整 `pt_regs`；B 完成后返回的 RIP/RSP/GPR
  再成为 A 的 continuation 状态。
- 最外层 unlock 是临界区完成边界，不能先弹 CALL frame，因为原 waiter 最终
  需要用该栈顶返回地址直接跳过已经代理执行的 unlock。

`kd_exec_frame` 是 nested/hostcall 边界的持久状态，保存 `regs`、entry RIP、
continuation RIP/RSP、父 frame 和 lock ownership。当前 frame depth 和 lock
depth 都限制为 8。

## 11. 返回原 waiter

成功代理后使用 `jump_to_saved_regs()`：

1. 从 `pt_regs` 装入 R15、R14、R13、R12、RBP、RBX、R11、R10、R9、R8、
   RAX、RCX、RDX、RSI、RDI。
2. 把真实 RSP 切换为 `regs->sp`。
3. 执行 `retq`，从 virtual CALL frame 栈顶取得 post-unlock RIP。

该函数不会跳到 `regs->ip`；成功退出时该字段通常仍是 outer unlock target。
真正的续点来自 `[regs->sp]`。

spin JIT 失败回退使用 `jump_to_saved_regs_in_cs()`：它切换到 `regs->sp` 后，先
压入 `regs->ip`，再 `retq`，因此从原始 CS entry 重新执行。mutex JIT 失败则
保持 waiter 未完成并把锁交还给它，让原 lock 调用按 native 路径返回。

两个恢复函数都不恢复 EFLAGS、segment state 或 SIMD/FPU 状态。

## 12. 修改 JIT 时必须保持的约束

1. physical RSP/RBP 始终属于 wrapper，guest RSP/RBP 必须经过 R13/R12 和
   register map。
2. 普通 translated 指令不得硬编码 guest R11-R15 的物理位置。
3. 跳到公共 `exit` 前，必须完成 special-register spill，并定义 R14 和
   `Stack_IJ`。
4. control call/hostcall 必须保留 virtual CALL frame；普通 call miss 必须撤销。
5. 新增可恢复出口时，必须把 post-call RIP 加入入口 dispatcher 的
   continuation label 集合。
6. native handler 只能通过 `pt_regs` 读取 guest 参数、写回明确声明的结果，
   且必须定义失败、重试和 side-effect 语义。
7. 不得把 `args[1]`、EFLAGS、FS/GS 或 SIMD 状态当成已实现的跨边界 ABI；若要
   使用，应先补齐 wrapper 保存/恢复及对应测试。
8. 修改 `struct pt_regs` 偏移、wrapper push 顺序或 `Stack_*` 宏时必须同步修改
   三者，并反汇编最终 `jit.bin` 验证实际编码。
