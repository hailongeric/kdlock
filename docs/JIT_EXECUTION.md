# JIT 范围、执行流与测试

适用范围：仅 x86_64 机器上的内核临界区；不包含其他架构的适配或测试任务。
`mutex_jit` 默认开启；mutex 正例按 `mutex_jit=1` 验收，`0` 仅用于显式原生对照。
普通 spin/mutex 的 caller-clobber v1 由独立 `kdclobber2` 内核入口启用：物理请求
最初仅有 RIP/RSP/RBP，正常 outer unlock 返回精简完成；中间出口先物化 FULL
包再进入下述通用处理。旧 ABI 和中途 FULL 续跑保留完整契约。身份、状态表和调用约束
统一见 [寄存器 ABI 1.0](JIT_REGISTER_ABI.md#10-普通-spin-的-caller-clobber-v1)。
2026-09-08 用户确认：只审查本次实际可能执行的 JIT 范围，普通 CALL miss
交回原 waiter 后，从保存的退出状态原生完成剩余临界区，不再返回本次 JIT。
这取代此前“普通 CALL 后的 native 后缀也必须整段准入”的要求。

当前默认接口为 `kdclobber2` 的普通 spin/mutex clobber（ABI 1/2）。本 CPU
累计频率与锁频率先于目标进程筛选，每 10240 次统一读时钟；准备方法见 3.2。
本文件保留增量选择和导航；专门协议的角色、断言及诊断入口分置于
[入口准入](testing/entry_admission.md)、[spin](testing/spin_protocols.md)、
[mutex](testing/mutex_protocols.md) 和 [native](testing/native_protocols.md)。部分旧准备仍为 12000 次，
且依赖旧 CPU 放置，未全部适配/重验本地发现；只能作为协议库存按需诊断。
当前通过范围以 [tests](../tests/README.md#当前验证范围) 的冻结记录为准。

## 1. 准入范围

翻译器先解码，再由 `context_policy.jit_phase_blocks()` 选择 JIT 可达块，
随后做临界区锁深度边界检查和上下文检查。同一份块集合用于生成机器码及
入口分发表，不能只缩小检查范围却继续生成未检查的后缀。

| 边界 | 本次 JIT 后续范围 |
| --- | --- |
| 普通直接 CALL，callee 不在当前解码块中 | 保留 CALL 本身和退出桩，删除该 CALL 的返回边 |
| 同后端 lock/unlock 控制调用 | 保留可恢复的后继，仍检查嵌套临界区 |
| allowlist hostcall | 额度内 callee 由服务适配器执行，返回后继续 JIT；后继仍需检查。额度退出不缩小翻译审查范围 |
| 已解码的普通 callee | 检查 callee 和返回后继，保留 CALL 入参及 RET 效果分析 |
| 间接 CALL | 保守保留后继；不能假设一定 miss，已学习目标也需检查 |
| 条件分支或其他 JIT 路径到达同一后缀 | 后缀仍在范围内，不能因另一条 CALL 边退出而删除 |

初始入口和已学习目标作为范围根；每次重新编译重新计算范围。可达的缺失
分支文本仍走有界补读，不能把未解码的跳转目的地当作安全空块。
普通 CALL 自身的目标和压入返回地址的内存写入也必须通过检查。

文本窗口已经覆盖目标地址，不代表该窗口的 CFG 已解码目标。新热路径可能
指向已有冷窗口中尚未解码的块；翻译器会补充该窗口的解码入口并重新检查。
这不增加独立的准入根，不让冷分支借用新的入口寄存器假设。补读和补充解码
入口共用 32 轮扩展上限；真正不可解码或预算耗尽仍拒绝，不跳过缺失块。

spinlock 和 mutex 默认都支持显式 GS 访存，按 pinned waiter base 翻译；
current_task 读取使用 logical waiter，无需单独启用 GS 开关。
范围内发现 FS/base 操作、已识别的线性 per-CPU/调度/IRQ/RCU 符号或其他既有
拒绝条件时，整个候选拒绝并删除本次汇编/二进制产物，daemon 发布 native-only。
只存在于已排除后缀的不支持的上下文操作不再导致该 JIT 前缀被拒绝，因为它们
由原 waiter 原生执行，不是交给 combiner 的 hostcall。
这不是任意指针、并发内存、所有指令或所有内核上下文的安全证明。

## 2. 执行流

```text
waiter 获取/请求 L，记录原临界区入口
  |
  +-- 无可用 JIT / 准入拒绝 --> waiter 原生执行
  |
  +-- combiner 持有原生 L --> 校验入口/逻辑子请求的执行范围
                              |
                         wrapper 按 entry_abi 导入有效入口状态
                              |
                         必要时检查入口地址区间
                              +-- 条件不满足 --> 尚未开始，走原生路径
                              |
                              v
                         执行翻译后的指令
                              |
                +-------------+------------------+
                |             |                  |
           lock/unlock     hostcall          普通 CALL miss
                |             |                  |
           锁协议处理      allowlist 服务     保存当前 GPR/RIP/RSP
                |             |              保留虚拟 CALL 返回地址
                +-------> 继续 JIT                |
                                                 v
                                         原 waiter 原生进入 callee
                                                 |
                                         原生返回并执行剩余临界区
                                                 |
                                         unlock 请求 / owner ACK
                                                 |
                                            本次代理结束
```

图中控制 CALL 的续跑指中间 lock/unlock：进入 C 前须物化 FULL。
普通 clobber root 的最终 outer unlock 另走 COMPLETE，写回 RIP/RSP/RBP，
回到锁侧循环完成/发布，再由 waiter 恢复；不把精简包交给通用 dispatcher。
局部 mutex 控制另有
[有界栈检查](testing/entry_admission.md#53-mutex-控制-call-的栈检查)：窗口不足时在 CALL 前交回 waiter，
窗口变化时在已完成 CALL 的后继交回 waiter；两者均不返回本次 JIT。

普通 CALL miss 的 `regs.ip` 指向原 callee，`regs.sp` 保留刚压入的源返回地址。
waiter 不是从临界区入口重跑，之前的写入和已完成的 B 不重放，也不做事务回滚。
native 续跑期间，combiner 保留已经获得的物理锁并按既有协议处理 unlock 通知；
等待这次 native 续跑完成，不恢复同批其他代理请求的执行。这是该 combiner
的暂停，不是全局暂停；其他 CPU 上独立锁队列的 combiner 仍可处理自己的请求。
mutex 的原生 owner 不交接给 waiter。不能让其他调用者趁 native 后缀未完成
进入这些仍持有的原锁。嵌套/远端路径的具体状态约束见
[DESIGN](design/frames.md#96-bcd-comparison-and-continuation-scope)。

例如 `A: 写入 -> CALL F -> 后缀 -> unlock(A)`，F 尚未翻译时只执行 JIT 前缀；
F 和后缀都在 waiter 上执行。daemon 可以学习 F 并为未来调用重编译，但不会
把这次已转入 native 的执行重新拉回 JIT。若新版本可能执行 F 内部或返回后缀，
必须重新检查这些代码；之前前缀通过不等于新范围也通过。

两元素输入 ABI 不变：`args[0]=waiter GS base`、`args[1]=logical waiter task`。
spinlock 和 mutex 的被代理 waiter 等待结果时均保持禁止抢占并 PAUSE 轮询，
不会睡眠或调度。spin 的物理 waiter 在关本地 IRQ 后用连续汇编发布和等待，
完成后从寄存器包恢复，不返回可能已被远端 JIT 覆盖的旧 C 帧；详见 2.2 节。
mutex 取得 gate 后的真实锁获取和 native owner/ACK 路径仍保留原调度语义。
mutex 等待仍可能受到 IRQ/NMI 访问；spin 关本地 IRQ 也不排除 NMI。
owner/依赖任务必须能在其他 CPU 推进，同 CPU 的 sleeping owner 与 busy waiter
组合不支持。旧版依赖 waiter
调度的同 CPU 用例证据不适用于本策略。寄存器及输出含义见
[JIT_REGISTER_ABI.md](JIT_REGISTER_ABI.md)。非 CALL 故障续跑、flags 修复和
不可变代码版本仍是已记录的限制，本次不扩展。

### 2.1 Waiter 发布边界

正常 spin JIT 完成时，wrapper 先更新共享 request 的有效结果，combiner 完成
终态检查和解绑，再在 node 上 release 发布 `completed=1/locked=0`；waiter
acquire 观察完成后才消费结果。新 ABI 的 COMPLETE 只含 RIP/RSP/RBP；FULL
中间出口和旧 ABI 遵守各自寄存器规则。node 仅引用 request，不保存另一份整包。
mutex MINIMAL/COMPLETE 借用 node 包，首次 FULL 退出才取得独立 frame 包。
尚未执行的单 waiter、IRQ/native 交接和批次末尾交接也使用 release，先完成
队列链接再唤醒。
这是私有队列的执行通知，不是把原生锁 owner 改为 waiter。

node 完成通知发布后可能立即复用。combiner 必须提前保存后继，不再读写旧 node；native
续跑期间的 owner ACK 是另一个、位于原 waiter 栈上的请求，其最后访问也必须
是 release ACK。两类通知不能混成一个“完成”计数，原生后缀仍遵守上述保留 owner 的流程。

`test_spin_outer_progress.py` 使用生产 combiner，检查五种发布路径、最终寄存器包、
release API 和即时槽复用后的无覆盖，并拒绝普通写入/错误包/发布后覆盖的变异。
`test_spin_shadow.py` 的容量交接计数只统计真实队首分支，不把普通批处理发布误计为
容量拒绝。这些是确定性替代原语测试，不是硬件 memory-order litmus 或任意并发证明。
修改此边界时在 guest 选择这两个程序及受影响的复杂 spin 用例；不要附带 mutex
或被替代的 mode 0/1 基础诊断。本轮的精确命令、两次初始失败和冻结输入见
[发布边界验收](VALIDATION.md#spin-waiter-publication)。

远端 child 完成时，`kd_exec_remote_complete()` 先清空 child 的 `resume_target`，
再 release 发布 parent 的 `remote_result=DONE`，之后不再访问 parent。
无剩余锁的 parent 可能随即退休并复用；这与物理 waiter 的 node 唤醒、原生
unlock 请求的 ACK 是三个不同边界。
既有 `test_remote_outer.py` 检查生产远端协议、native 续跑确认、完整 guest x86-64
`pt_regs` 和 CALL 返回字；普通返回只推进 IP/SP，终态 OOO 保留最后 unlock 的
CALL 包。确定性观察器要求 DONE 前脱链，并立即覆盖可退休 parent 来检测迟到写入。
这些比较包含软件包中的 flags 字段，但不执行硬件 flags 恢复，也不证明任意并发存活期。
只改此 fixture/驱动时在 guest 运行以下一项，不因此重跑 live JIT：

```sh
make -C tests/unit run TESTS= PY_TESTS=test_remote_outer.py
```

十一种临时生产代码变异（含计量缺失、错后端、吞掉错误三项）须触发明确断言，
BUG-only 退出不能充当检测成功。
它们会额外编译运行临时代码，只随本单元被选中时执行，不增加 live case。
验收与冻结输入见
[远端包单元记录](VALIDATION.md#remote-packet-unit)。

### 2.2 Spin 的等待栈与 IRQ 状态

当前实现接受 IRQ-on 和 IRQ-off 的 task 入口。`kd_spin_entry_begin()`、
gate claim 和缓存快路径均不再因 `irqs_disabled()` 拒绝；task/BH、migration、
native-active、owner 与 ticket 代次等适用检查仍保留。自愿抢占的假设没有取消
ticket 生命周期内的 CPU pin，也没有允许 hardirq/softirq 或 IRQ/BH 操作代码进入 JIT。

spin 为每个 possible CPU 预分配一份 8KB shadow 等待栈，准备、队首和 combiner
仍使用 task 内核栈。它采用 TCLock 的等待栈隔离方式，执行后端继续使用 JIT：

```text
进入队列前保存并关闭本地 IRQ -> 在 node 保存原 flags、物理 RSP 和 hook RSP
  -> 物理 waiter：在同一段汇编中切到 shadow 栈，压入一个旧 C RSP
     -> 链接前驱，PAUSE 轮询；不调用 C 或访问旧 C 栈
     -> 尚未代理的队首：弹出旧 RSP，返回完整 C 帧，取得原锁后恢复原 IRQ 状态
     -> 已完成/native 后缀：放弃旧 C 帧，在 min(物理 RSP, 最终虚拟 RSP)
        对齐后的栈下方调用恢复函数，保留 request 指针和 ticket/flags
        -> 完成 ticket 或标记 native -> 直接装载共享寄存器包
        -> 最后一次包读取后归还 request 引用 -> 恢复原 IRQ 状态 -> 跳转续点
```

IRQ 屏蔽覆盖发布、等待和 combiner 执行，恢复时保留入口状态：原来关闭的仍然
关闭，原来开启的才重新开启。native 后缀继续保留 ticket pin 到最终 owner ACK。
虚拟 waiter 使用父执行者的独立 C 栈，仍需轮询并服务远端 owner/ACK；它的
队列区间同样保存、关闭并恢复本地 IRQ。原生快路径不借出任务栈。

`shadow_stack.wait_stack_top` 指向独立分配的等待栈顶，和锁记录、wrapper RSP
暂存分开。模块初始化时分配，失败统一回滚，所有请求排空后释放；热路径没有
分配或整栈清零。切回 task 栈后才释放 CPU pin 或恢复 IRQ，避免栈仍被使用时
被同 CPU 的下一请求复用。mutex 的独立执行栈保留。
返回码与准备期 retry 见 [Spin 协议](design/locking.md#43-combiner-and-native-returns)，
逐步伪代码见 [执行路径](../bench/spin_cacheline/EXECUTION_PATHS.md#42-发布请求等待和恢复入口)，
已运行范围见 [shadow 等待栈验证](../tests/README.md#spin-shadow-wait-validation)。

### 2.3 Frame 复用与单锁完成

spin 的物理 waiter 在发布前从预分配池领取 request，直接准备其中的寄存器包和
frame。node 只引用这份存储；combiner 用 `kd_exec_frame_bind()` 把它接到本 CPU
的 `context.top/parent` 链，depth 保留物理嵌套上限。`kd_exec_frame_pop(frame, NULL)`
只做生命周期检查和解绑，不复制包，也不归还等待者尚在使用的 request。

普通、复杂出口和 native 续跑共用原包；远端 child 的独立 frame 通过 `regs_ref`
引用逻辑 root 包。各 owner 的 CALL/锁事实和锁记录独立保留，避免把正在变化的
寄存器当作旧准入快照。原生回退在发布前增加 owner 引用，ACK/pop 后才归还；
child 另保留 root 引用。物理 waiter 的恢复汇编在最后一次读取后归还自己的引用。
因此 node 复用、原 waiter 返回甚至退出，都不提前回收仍有 owner 使用的 frame。

嵌套 producer 在发布前将父锁记录直接写入 child 的独立 ledger；combiner 验证
原地记录后启用，不再通过 `jit_context` 复制第二遍。虚拟 waiter 每轮仍检查
远端邮箱，只有非空时才调用解锁/ACK 处理函数；物理 waiter 的 shadow 等待不变。
状态与生命周期边界见[嵌套 JIT waiter](JIT_REGISTER_ABI.md#42-嵌套-jit-waiter)。

每 CPU 预分配 12 个按 64 字节对齐的 768 字节 request，共 9216 字节；frame/context 为 672/5400
字节。模块静态 per-CPU 节减少是因为 node 去掉了内嵌寄存器包，不代表总内存减少。
嵌套 `kd_spin_jit_context` 在 x86-64 上从 184 缩为 16 字节，四槽的请求大小从
736 降到 64 字节；两者的 `vzalloc` 仍占一页，不能计作每 CPU 释放一页内存。
准备和解绑不清空整个 frame 或无效锁记录；池满时使用原有原生/队列回退。
mutex 使用 per-CPU frame 分配；最小 root 借用 node 包，FULL 续跑保留独立生命周期。

批次持续持有 L，并在整个 combining 区间持有一次 source/provider lease；每个
spin bind 检查 OPEN，但不再逐 frame 增减全局计数和 module 引用。设备状态里的
`frames` 是租约计数，不能再解释为批次内 spin frame 的个数。
正常单锁完成合并终态验证与物理解绑，仍检查 owner/top/depth、batch lease
和实际出口包，完成发布继续由锁层负责；SELFTEST 保留 complete/观察/pop 顺序。
复杂出口才保存物理 combiner 快照。普通 request 标志移至 frame 前，ABI/包分类
移至寄存器包前，准入元数据集中在请求前两条缓存行；不复制可变状态。
同批次的同 entry/SPIN backend 复用已找到的 `exe` 槽指针，仍逐次 acquire
检查 NORMAL、OPEN、entry/pid 和代码指针；普通路径在最终 batch prepare
集中检查，身份 lookup 本身不授权执行，dispatcher 的 backend/scope 检查
也保留；不缓存代码版本或把 source lease 当成代码不可变保证。
执行当前请求前预取下一已发布请求的实际寄存器包、frame 热字段，以及逻辑
waiter task 栈范围内的虚拟 SP/push 槽。虚拟子请求使用共享 root 包，不再按
CPU 的 node-zero RSP 猜栈范围；提前 outer release 后不访问旧 successor。
SLOWPATH、COMBINER、JIT_SUCCESS 等事件、最大深度、overflow 和 invariant
统计改为初始化时一次性 `alloc_percpu()` 分配，避免挤占模块静态 per-CPU
预留区；排空退出后遍历所有 possible CPU 汇总，日志字段不变。
实时 waiter 数量、JIT 禁用 latch 和 owner/ACK 仍是共享协议/观察状态。
普通请求只初始化 72 字节 frame 热头部及有效寄存器字段；锁数组、remote/native 控制和
快照位于预分配冷区，由 `complex_ready` 在首次复杂出口启用。node 为 128 字节，
首行保留链接、调度栈标记、execution 引用及发布前准备的预取地址提示，
第二行独立放置 completed/locked，避免后继入队干扰 waiter 轮询；各槽均对齐 64 字节。
提示只在排队期间使用，不参与准入或最终恢复。
`kd_spin_batch_run` 在同一个 C 帧中连续处理新、旧及混合 ABI 请求，编译器
按 clobber 约束保护 combiner 活跃值。旧 wrapper 适配只额外保护物理 RBP；
新 wrapper 自己保护 RBP。正常请求不逐次退出/重入循环，也没有外层汇编
成组保存。循环完成/解绑/发布当前 waiter 后选择并准入下一请求。
正常单锁跳过逐请求 `execute_cs`/通用 dispatcher；复杂出口用
`kd_exe_spin_batch_resume` 消费已经执行的出口，禁止重放当前前缀。
新 ABI 正常入口、完成和最终恢复只访问 RIP/RSP/RBP；旧 ABI 最终 unlock
回写 callee-saved 集及 RIP/SP、RDI，保留原入口导入及最终 GPR 恢复。
中途出口仍在进入 C 前物化完整逻辑 GPR。
排空日志 `kd_spin batch: entries=... ww_jumps=...` 证明实际批次入口/连续交接次数。
普通单用户 request 最终 release store 归还；有 native/child 使用者时仍原子递减。
ticket 分配/查询只访问活跃位图中的槽，状态变更 guard 仍保护远端引用和代次。
协议及完整生命周期见 [Frame 协议](design/frames.md#91-frames-and-lock-ledger)，逐步操作见
[执行路径](../bench/spin_cacheline/EXECUTION_PATHS.md)。TCLock 原生切栈与当前 JIT
路径、初始寄存器范围及剩余状态保存的对照统一见
[寄存器 ABI 对比](JIT_REGISTER_ABI.md#11-与-tclock-spinlock-的执行路径和状态保存对比)。

## 3. 环境与操作

第一次手动操作先读 [代码地图与逐步运行](PROJECT_GUIDE.md#3-一步一步运行)：
其中有 VM/guest 检查、完整文件索引、单用例入口和拆开观察 mode 3 的流程。
本节及后续章节维护复杂用例的协议、参数和判定，不要求把所有命令顺序执行。

只在可恢复的 guest 中构建和运行，不能在宿主机加载模块。当前 guest SSH
端口为 2222，默认要求 `6.1.159-kdclobber2` 的 hook/exports。
先确认恢复快照和空闲状态，完整流程见 [AGENTS.md](AGENTS.md)。
normal 模式共享源码无需复制；recovery 模式虽路径相同但使用 ext4，只同步
哈希不同的文件，不移动或整目录复制仓库。

以下首次环境验收命令在 guest 的 `/root/host_fs/kdlock` 执行。
先按 [依赖安装](PROJECT_GUIDE.md#33-检查依赖与空闲状态) 创建/激活 venv，确保
`python3`、测试子进程及 daemon 继承同一 PATH；只设置 `VIRTUAL_ENV` 不够。
开发后的日常增量使用[第 7 节](#7-分层与增量回归)，不重复执行本节全部命令：

```sh
cd /root/host_fs/kdlock
export KDIR=/root/linux-6.1.159-kdclobber2
python3 bench/spin_cacheline/kernel_identity.py
make -C tests/unit run
python3 tests/tools/audit_context_spills.py
```

仅在明确需要历史主模式诊断时，确认恢复快照并核对各脚本的本地频率准备后执行以下命令。
脚本负责编译、加载、检查、停止 daemon 和卸载：

```sh
export KDLOCK_RECOVERY_CONFIRMED=1
bash tests/live/test_09_jit_execution_modes.sh 0 1 2 3 4 5
```

该入口无参数时只列出测试范围，不再默认运行全主模式。显式参数先全部校验，
相同 mode 按首次出现顺序只运行一次；遇到失败立即停止。检查每种模式时可
分别传入一个 mode，不能因为前面通过就假定后面执行过。
mode 3/4/5 脚本显式加载 `mutex_jit=1` 并检查实参。
daemon 的 `--mode flat/per-tgid` (`1/2` / `v1/v2` 为兼容别名) 只选择工作目录布局，不是 benchmark 的 mode。
daemon 必须在 kdlock 加载后启动，并在一次设备会话内完成读取、翻译和发布。
真实文本读取要求有效的设备引用；翻译子进程继承该引用，父进程退出后也可能
继续持有。真实读之前还会 pin 源码所属 LIVE 模块；停止并等待所有翻译者和
执行者退出后，须成功 `retire` 再卸载，不能将 `in use` 当作强卸载理由。
执行流及手工 CLI 的边界只维护在 [daemon 文档](../daemon/README.md#device-session)。
mode 1/4 的入口条件及 mode 8 的跨窗口解码有历史实际 JIT 证据；本地发现改造后未重跑这些专门阶段，这不代表
所有远端或资源耗尽场景也通过，完整结果及未通过项见验证记录。

mode 3 的 `test_07` 在生成物出现后，还通过现有 `wait_ready()` 读取
`/dev/kd_dev`，等待对应 RIP/TGID 的 mutex 条目为 NORMAL，再运行竞争负载。
`jit.bin` 存在可能早于上传，最终 chunk 日志也早于 payload 拷贝，不能只查
一次日志就启动测试或判失败。发布状态写入 daemon 日志同名前缀的
`.published.json`；此准备检查不代替负载后的 body witness/计数验收，也不提供
不可变版本或并发重编译保护。

mode 8 原有阶段需要串行准备六个翻译入口，`test_04` / `test_10` 为此单独等待最多
90 秒并打印实际耗时。只延长产物初始化等待，不改变负载执行超时、必需产物、
返回后 body witness、寄存器或互斥/副作用检查。
`test_04 ... 8` 随后在两个新模块会话运行双根共享 B 的纯 JIT、混合完成阶段，
每个会话另准备三个入口，
执行流见 [6.14](testing/spin_protocols.md#614-两个独立-root-共享-b-combiner)。`test_10` 的退出点变体不追加该阶段。

普通 CALL 的真实寄存器/退出点续跑，以及上下文拒绝测试：

```sh
KD_NATIVE_REGISTERS=1 bash tests/live/test_10_native_resume.sh 0 1
KD_NATIVE_REGISTERS=1 bash tests/live/test_10_native_resume.sh 3 1
KD_NATIVE_REGISTERS=1 bash tests/live/test_10_native_resume.sh 1 2
KD_NATIVE_REGISTERS=1 bash tests/live/test_10_native_resume.sh 4 2
bash tests/live/test_04_spinlock.sh 8
KD_NATIVE_REGISTERS=1 bash tests/live/test_10_native_resume.sh 8 2
KD_NATIVE_REGISTERS=1 bash tests/live/test_10_native_resume.sh 8 3
bash tests/live/test_12_context_native_only.sh 10
bash tests/live/test_12_context_native_only.sh 11
KD_CONTEXT_LOCK_API=percpu-spill bash tests/live/test_12_context_native_only.sh 3
```

普通 CALL 测试检查当前退出状态、waiter 身份、返回栈及副作用恰好一次；不能用
完全原生对照代替。上下文拒绝测试则必须没有 JIT 执行，随后验证原生结果。

学习普通 helper 后的深层 mutex JIT/容量退出，日常使用已升级的两源码模块用例：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case native-mutex-depth
```

该脚本先执行 JIT 前缀并产生真实 helper CALL miss，排空调用者后让 daemon
学习第二个模块中的 helper，再检查新范围的 JIT、锁容量退出和源码 pin 退休。
必须执行 helper 中翻译后的加锁指令，验证真实容量退出、保留锁和 owner ACK；
只有第一段 body witness 不能通过整项验收。完整执行流见 5.1。
直接调用 `test_10_native_resume.sh 4 5` 仍是默认单模块诊断，不作为该复杂用例的
前置或附加步骤；只有单模块构建/路径本身受影响或需要定位时才另行选择。
学习重编译期间先排空旧调用者，并非已实现版本隔离。

### 3.1 纯原生寄存器对照

历史 `control-0/3` 的必要逻辑已并入 `test_10`，不再依赖 guest `/tmp` 中的
外部脚本。它们只在首次校验探针、修改原生对照或显式验收时选择，不属于日常
`registers`、`core`、`baseline` 或 `extended` 的前置步骤：

```sh
# Guest only, after confirming the recovery snapshot.
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite native-controls
# Equivalent explicit diagnosis of the mutex reference only:
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_CONTROL=1 KD_NATIVE_REGISTERS=1 \
  bash tests/live/test_10_native_resume.sh 3 1
```

执行流：确认空闲 -> 共用构建/加载 -> provider 设为 `target_process=kd_unused`
并读回，保持 `mutex_jit=1` -> 启用同一寄存器汇编探针 -> 八名非目标 worker
各完成一次原生临界区 -> 只读确认 registry 为空、source 为 OPEN 且 modules/
frames/writers 均为 0 -> 正常 retire/卸载 -> 校验八条记录、16 个 GPR、CALL
返回栈和保护状态。该分支不启动 daemon、不晋升或翻译；不检查 flags。

`KD_NATIVE_CONTROL=1` 仅接受 registers=1、mode 0/3、stage 1，并继承寄存器
用例的参数互斥检查。未设置时原 JIT/续跑路径不变。`native-state.json`、
`registers.json`、environment、workload 与 dmesg 进入统一证据目录；任何 JIT
entry/body/install、native frame、owner ACK 或非零注册数都会使对照失败。
归档器可能保留先前 daemon 工作区的文件，它们不是本次生成或执行证据。
不能用纯原生对照通过替代 JIT 寄存器续跑正例；历史命令清单也不改写为新命令。

### 3.2 热锁晋升与翻译准备

新 lock 入口按本 CPU 频率、本 CPU 的单锁频率、进程身份依次筛选：

```text
每 CPU 首次建立时间起点，此后每 10240 次普通 lock 访问读一次 TSC
  -> CPU 批次少于 400 亿 TSC：开启/维持本 CPU 准入
  -> CPU 开启后，只更新本地 64 槽中的地址、计数、窗口及晋升缓存
  -> 时间检查点复用同一次 TSC，检查本地候选锁
  -> 单锁本地计数 >= 10000 且不足 25 亿 TSC：CAS 发布全局热锁地址
  -> 本地晋升缓存命中：不查全局表，随后才筛选进程和注册 entry
  -> daemon 翻译 -> NORMAL 发布 -> 实际正文及完整状态验收
```

CPU 窗口按 10240 / 256 比例放大，保持旧的 256 次 / 10 亿 TSC 频率标准，
检测精度则变粗；降温、等于期限或时间倒退在下一个检查点关闭新准入，最多
延迟 10239 次访问，后续可重新达标。已有解锁、续跑、票据和 owner ACK 不受影响。

单锁起点复用上一个 CPU 时间检查点，可能早于真实首个样本，因此判断偏保守。
本地窗口过期会清零重测，不再维护全局 CHECKING/IGNORE。不同 CPU 的计数不
汇总，本地直接映射冲突丢弃旧历史及旧正向缓存，可能推迟识别。只有本地达标
才访问共享集合，表满仍走原生；已缓存的热锁不再读共享地址。全局只保存
131071 个已晋升地址，约 1 MiB；per-CPU 结构约 1.6 KiB。首次起点以外，CPU
和单锁共用每 10240 次一次的时钟读取，没有逐地址读时间或共享原子计数。

普通根入口仅采样 lock，非目标访问也供样，但不注册 JIT。既有嵌套协议可以
只读查询全局热锁身份；新 root 仍须本地达标。SELFTEST 发布全局身份不绕过
本地门槛。详细布局、生命周期和近似边界见[设计](DESIGN.md#hotlock-monitoring)。

准备负载需要覆盖 CPU 和本地单锁两个阶段；当前普通 spin/mutex 验证与 bench
使用连续 48000 次准备，发布仍须等待 NORMAL。每线程只执行一次的协议探针
须另建立该 CPU 的锁历史；相关 live 用例显式启用场景模块的原生空临界区
准备，客户端在共同屏障前完成并固定 CPU，正文和副作用计数保持独立。
该测试选项默认关闭，不用于性能测量。其余专门协议用例未重新验证本地频率
准备，不能沿用旧的全局热锁通过记录。频率判断不测真实竞争，也不保证 99% JIT。

共享采样改动的定向入口如下；编译和运行均在 recovery guest：

```sh
make -C tests/unit run PY_TESTS='infrastructure/test_hotlock_sampling.py'
KDLOCK_RECOVERY_CONFIRMED=1 python3 tests/regression.py \
  --case mode-0 --case mode-3 --output /root/kdlock-evidence/hotlock-live-new
```

单元覆盖批量门槛、独立窗口、碰撞、并发发布、重入、时间倒退与终态；
live 仍要求自然晋升、实际 JIT、完整副作用和排空。直接采样函数的成本与
稳态锁操作测量分开，见[专用对照](../bench/hotlock_record/README.md)。

### 3.3 带观测的负载测量

详细说明见 [README](../bench/lock_scenarios/README.md#33-带观测的负载测量)。

### 3.4 原生锁与 JIT 配对实验

详细说明见 [README](../bench/lock_scenarios/README.md#34-原生锁与-jit-配对实验)。

### 3.5 翻译器剖析

详细说明见 [README](../bench/lock_scenarios/README.md#35-翻译器剖析)。

<a id="cpu-受限的-mutex-测量"></a>
<a id="可选的-jit-边界计时"></a>

## 4. 如何判读

公共脚本强制 `KD_JIT_BODY_WITNESS=1`。实际 JIT 验收同时需要有效 `jit.bin`、
匹配 entry/lock 且 wrapper 返回后的 `JIT body witness: ... body=1`，以及负载
状态/计数检查。只看到翻译命令、安装日志或调用前 `execute_cs` IP 不足以通过。
mode 2/5 还要确认额度内 hostcall 执行和恢复成对出现；mode 5 的超额度 CALL
另由原 waiter 原生完成，按 [6.13](#613-call-次数额度与原生后缀) 单独关联。

`body=1` 证明生成块确实进入且 wrapper 已返回，不证明每条指令/每条路径均执行。
JIT 前缀加 native 后缀不能写成“整个临界区全由 JIT 完成”。`body=0` 也不能
授权入口重放。观测插桩不是性能基线，手工运行 daemon 默认不开启。

失败时先查看 `CONTEXT_NATIVE_ONLY` / `CONTEXT_ADDRESS_WIDENED` 的源 RIP、
指令和原因，再对照 daemon 工作目录里的 `asm/jit.S`、`jit.bin`、miss 表及
脚本输出的 `Evidence:` 目录。分析精度耗尽是保守拒绝，不是发生真实越界的证据；
拒绝后的原生完成不能冒充 JIT 正例通过。

同一次翻译可能先报告无条件分析的 `CONTEXT_ADDRESS_WIDENED`，再通过带条件
分析并报告 `ENTRY_GUARDED_ADMISSION`。前一条不能单独当作最终拒绝。冷分支
补读为 `ENTRY_GUARD_WAIT_TEXT` / `TEXT_RANGE_EXTEND`，补读完成仍须重新检查。
`CFG_ROOT_EXTEND` 则表示为已缓存文本补充可达解码入口，不是额外读取文本或
接受未检查的块。
运行时 `ENTRY_GUARD_REFUSED` 表示当前入口值不满足条件，本次未执行 body；
`ENTRY_SCOPE_MISMATCH` 或 `INVALID_ENTRY_REFUSAL` 则需要核查 frame、CALL
阶段、RIP/RSP 和父请求，不能忽略错误并重试入口。

各批次的时间、源码身份和结果集中记录在 [VALIDATION](VALIDATION.md)；
[9 月 9 日矩阵清单](VALIDATION.md#recorded-matrix-manifest) 是历史执行记录，
不是当前回归的待执行清单。当前选择以第 7 节和 `tests/regression.py` 为准。
完整矩阵必须使用同一源码快照，不借用旧的短回归结果。虚拟请求取消与续跑
见 6.3，原 waiter 的等待/取消见 6.4；6.2 的真实 RCU/owner ACK 探针不执行
JIT，不能计入实际 JIT 正例。主模式、寄存器、held-B、pending-B、学习后 callee
与远端测试分别验证不同路径，不能合称所有资源耗尽或所有生命周期均已完成。

## 5. 入口条件与嵌套续点

详细说明见 [entry_admission](testing/entry_admission.md#5-入口条件与嵌套续点)。

<a id="51-学习后的直接-callee"></a>
<a id="52-运行时续点"></a>
<a id="53-mutex-控制-call-的栈检查"></a>
<a id="同设备能力协商"></a>

## 6. 资源拒绝与测试边界

先判断拒绝发生在哪个阶段，再决定执行流。资源不足不等于可以重跑入口：

```text
模块初始化分配失败 -> 初始化返回错误，尚未安装 hook
新入口没有代码块 -> 不发布半成品条目 -> ready=false
  -> wrapper 尚未调用 -> 队列按未执行请求处理，由 waiter 原生执行
JIT 已执行，新的 lock CALL 仍为合法 PENDING，尚未取得/发布新锁
  -> 仅支持的 ENOMEM/E2BIG -> 保留当前 CALL 包，原 waiter 完成原生后缀
本地 spin 获取后的 EIO，通过 6.11 的完整检查点验证
  -> SPIN_NATIVE -> CALL 后继原生续跑，不再获取 B
其余 ENTERED/ACQUIRED，或其他未经验证的 post-entry 错误
  -> 不授权入口重放，按既有 fail-stop 协议处理
```

以下是当前主要资源路径清单，不把组件测试写成所有生产调度均已验证：

| 资源 | 当前边界与处理 | 覆盖与缺口 |
| --- | --- | --- |
| 代码块池 / 执行表 | 最多 64 个 640 KiB 块、511 个槽；注册失败不发布条目，已有 key 不重复取块；原生拒绝不回收块 | `test_exe_registry.py` 检查真实全量/部分分配、清理与并发注册；6.6 通过真实 CALL 入口填满代码池，并组合两个存活 native frame 与新队列回退；511 槽满仍是合成元数据的探测边界测试 |
| 高层 JIT 入口 | 表不存在、空槽、未就绪、native-only、无 code block 或查无空槽均在 wrapper 前返回 | `test_jit_entry_scope.py` 使用真实 lookup/ready 和高层执行器，检查 spin/mutex 的完整 GPR 包、虚拟栈和锁记录不变；wrapper/锁原语仍是替身 |
| 上传边界 | 单块容量外的 payload 被设备拒绝；未知 key 不创建新条目 | 注册测试检查真实设备读写函数与最后一个合法字节；不证明完整镜像、并发替换或上传互斥锁语义 |
| hotlock 表 | 131071 槽；新地址无法建立采样记录时不晋升，继续原生 | `test_hotlock_sampling.py` 的生产函数容量测试；不是同时访问十万把真实锁的压力测试 |
| spin gate / acquisition ticket | gate 1024 槽、每 CPU 32 个 ticket；普通 hook 预留失败转原生；虚拟 B 必须遵守 CALL 阶段 | gate/entry 组件及 outer production fixture 分层检查；6.3 组合真实 ticket/gate 满表、新锁原生互斥及第二个 JIT 前缀后的 PENDING ENOMEM；均发生在虚拟请求发布前，不支持任意发布后恢复或 EOVERFLOW |
| mutex shadow / task 记录 | shadow 1024 槽；task 记录用 GFP_ATOMIC 分配；hook 中失败在入队前转原生 mutex | `test_mutex_resources.py` 检查生产组件；6.6 将真实 shadow 表满、原生竞争与两个存活 frame 组合；task/RCU/ACK 的独立 probe 见 6.2 |
| spin / mutex node | 每 CPU 各 4 个；普通请求无 node 时用自己的栈等待私有 gate，再取得原锁；虚拟 spin 请求先取消预留再返回 | spin producer/队列与 live observer 有界覆盖；6.3 连接真实 JIT、虚拟 ticket 取消及原生续跑，但资源输入为注入；mutex 生产组合测试取代旧模型，`test_11` 有八 waiter 争用四槽，6.7 将真实四槽占满与存活 JIT/native frame 组合 |
| frame / held-lock / 执行栈 | 8 层 frame、8 个逻辑锁记录与 CPU-local held-lock 容量分别检查；spin 使用 task 栈，mutex 保留独立栈，均不同于 shadow 锁记录容量 | 6.8 区分真实物理链的继承锁记录满与独立 local-shadow 拒绝；另有生产 frame 容量、spin producer、远端拒绝及 mutex learned-depth 有界测试，不能由一项容量通过推导全部耗尽场景 |
| 源码依赖 / 会话退休 | 每会话最多 pin 64 个 LIVE 模块；单次读取不超过 256 KiB；OPEN -> DRAINING -> RETIRED 不可逆 | `test_source_lifetime.py` 执行真实 source/device/registry 决策，模块/IRQ/VFS 为替身；6.6 连接两个真实 frame、busy retire、后缀 ACK、源 pin 阻止卸载及失效后释放；5.1 的深度扩展另行验证两份真实模块源码 pin |

代码池组件测试在真实初始化流程的分配 API 上注入失败，不修改生产容量，也不
执行生成机器码。它用 24 个 pthread 对六个 key 重复注册以竞争真实注册 gate，
所有表读取在 join 后进行；这不是 Linux IRQ、抢占或同时执行 JIT 的证明。
入口拒绝检查不是锁回滚测试，不能用于扩大已执行后的恢复范围。

在 guest 按改动点选择以下单元测试，不要求每次依次执行：

```sh
python3 tests/unit/run.py execution/test_exe_registry.py
python3 tests/unit/run.py execution/test_jit_entry_scope.py
python3 tests/unit/run.py mutex/test_mutex_resources.py
```

注册测试的七个变异负例必须成功编译、再由断言检测；编译错误或超时不算通过。
真实 JIT 与 native 后缀仍用第 3 节命令验收，证据见
[VALIDATION](VALIDATION.md)。队列资源耗尽的下一步以 [TODO](TODO.md) 为准。

### 6.1 Mutex 资源与恢复包

详细说明见 [mutex_protocols](testing/mutex_protocols.md#61-mutex-资源与恢复包)。

<a id="同队列的同-cpu-续跑"></a>

### 6.2 Task 引用、最终 ACK 与 RCU

详细说明见 [mutex_protocols](testing/mutex_protocols.md#62-task-引用最终-ack-与-rcu)。


### 6.3 Spin 虚拟请求取消与续跑

详细说明见 [spin_protocols](testing/spin_protocols.md#63-spin-虚拟请求取消与续跑)。

<a id="native-续跑窗口内的-gate-表压力"></a>
<a id="真实-ticket-耗尽"></a>

### 6.4 原 Waiter 的信号与退出

详细说明见 [native_protocols](testing/native_protocols.md#64-原-waiter-的信号与退出)。


### 6.5 原 Waiter 与 B 释放的竞争

详细说明见 [native_protocols](testing/native_protocols.md#65-原-waiter-与-b-释放的竞争)。


### 6.6 独立队列的并行 Native Frame

详细说明见 [native_protocols](testing/native_protocols.md#66-独立队列的并行-native-frame)。

<a id="mutex-shadow-表耗尽"></a>
<a id="代码池耗尽"></a>
<a id="保留-b-与原生竞争者"></a>
<a id="原-waiter-的信号与退出"></a>
<a id="改名后的原生嵌套与解锁"></a>

### 6.7 同 CPU 的 Mutex JIT 拒绝

详细说明见 [mutex_protocols](testing/mutex_protocols.md#67-同-cpu-的-mutex-jit-拒绝)。

<a id="节点满槽与-task-分配失败"></a>

### 6.8 物理 Frame 链与容量检查

详细说明见 [spin_protocols](testing/spin_protocols.md#68-物理-frame-链与容量检查)。

<a id="frame-回收门禁"></a>

### 6.9 无锁祖先与 Waiter 退出

详细说明见 [spin_protocols](testing/spin_protocols.md#69-无锁祖先与-waiter-退出)。


### 6.10 提前释放 A 的原生依赖

详细说明见 [spin_protocols](testing/spin_protocols.md#610-提前释放-a-的原生依赖)。


### 6.11 Spin 获取后的受检续跑

详细说明见 [spin_protocols](testing/spin_protocols.md#611-spin-获取后的受检续跑)。


### 6.12 同 CPU 的嵌套 Mutex JIT

详细说明见 [mutex_protocols](testing/mutex_protocols.md#612-同-cpu-的嵌套-mutex-jit)。


### 6.13 CALL 次数额度与原生后缀

此功能只处理第 17 次尚未分派的 CALL，不处理基本块指令预算或任意指令异常。
访问时 guard、原指令续跑和局部条件码保护仍明确延期，见
[未实现限制](TODO.md#deferred-access-time-guard)。

```text
同一 entry 发布 NORMAL -> 正常 mode 5 多轮/同 CPU waiter/持续竞争
  -> 每个代理请求：时钟服务 -> JIT -> int_sqrt 服务 -> JIT
  -> 最外层 unlock 后返回原 waiter
  -> 全部调用者退出，再设置测试参数 mode5_call_quota=1
  -> CPU 0 的一个 holder + CPU 1–4 的四个调用者，每人执行一次临界区
  -> JIT 请求的前 16 次时钟服务：adapter 执行并回到同一镜像
  -> 第 17 次：保留 callee RIP / CALL RSP / GPR，检查现有 CALL 包和服务策略
  -> 原 waiter 执行第 17 次时钟、int_sqrt 及剩余原生临界区，不回本次 JIT
  -> mutex unlock 交给保留原生锁的 owner，等待 ACK，调用者退出
  -> 全部 join；恢复 mode5_call_quota=0，确认原注册仍 NORMAL
  -> 停止 daemon、退休/卸载，核对完整状态与协议证据
```

`mode5_call_quota` 只是测试模块的两阶段开关，默认零；不是关闭 JIT 的 debug
选项，也不改变生产额度。mode 5 始终启用 `mutex_jit=1`。只在调用者已经排空
时切换；每次临界区固定调用 1 或 17 次 `ktime_get_ns()`，当前编译结果可能
实际调用 `ktime_get`。复杂状态更新仍在循环前仅执行一次，`mode5_api_calls`
统计每次时钟返回，`mode5_api_observations` 每个临界区一次，分别识别入口重跑、
漏执行或重复执行待处理服务。task/IRQ/preempt 日志在 unlock 后的原始任务采集，
不把 current/GS 探针插入翻译正文。

mode 2 和 mode 5 还在整个时钟循环后调用 `int_sqrt(unsigned long)`。输入为
`root*root+low`，其中 `low=observations & 0xffff`、`root=0x80000000+low`；
该值不溢出 64 位且整数平方根恰为 root。参数使用高 32 位，结果的 bit 31 为一，
用于发现参数截断、错误寄存器和符号扩展；结果必须被后续代码比较，而非丢弃。
每个临界区只调用一次标量服务，卸载记录
`kd_scalar service: mode=<2|5> calls=<完整临界区数> failures=0`。
这项数值检查与原有完整复杂状态 oracle、时钟统计各自保留；mode 5 第 17 次
时钟后的标量操作只在 native 后缀执行。服务 ABI 和支持范围见
[DESIGN 8.4](DESIGN.md#84-native-hostcalls)。

令 N 为原有正常阶段的 JIT 完成数，M 为额度阶段的 native frame 数，须 N>=2、M>0：

| 证据 | 期望 |
| --- | --- |
| `jit_success` / `jit_resume` | N / N；不把 native suffix 当作 JIT 完成 |
| entry/lock 匹配的返回后 body witness | N+M；额度阶段前恰为 N |
| hostcall exits / executed / resumed / limit | 2N+17M / 2N+16M / 2N+16M / M |
| hostcall rejected / failed | 0 / 0 |
| native started / completed / unlocks | M / M / M；逐 task/lock 关联，不能只比总数 |
| 完整临界区计数 | 正常阶段总数 + 5，复杂状态无失败 |
| API observations / calls | 临界区总数 / 临界区总数 + 16*5 |
| scalar calls / failures | 临界区总数 / 0；包含正常和额度 native 后缀 |

`mutex_signal_protocol.py quota` 将 `CALL_LIMIT_NATIVE` 与真实 `kd_native begin`
的 entry、callee RIP、RSP、task、原锁匹配，检查服务目标/返回标签属于当前
生成物，并将 complete、owner ACK 与原 waiter unlock 后的返回记录关联。
生成物必须同时有独立的时钟及 `int_sqrt` 服务目标。mode 2 不触发额度退出，
其 hostcall exits/executed/resumed 均须为 `2*jit_success`，limit/rejected/failed 为零。
五个调用者全部成功且 IRQ/preempt 干净；超额度请求不调用 adapter、不请求学习。
前后同一注册的 entry/TGID/code/status 必须一致，daemon 翻译/安装次数不增加。
这些观测不是不可变版本保证或完整硬件 GPR/flags 采样，C3/C4 仍延期。

`Evidence:` 目录保留 normal 阶段日志、两个客户端日志/退出码、开关读回、
前后发布 JSON、final.log 和 protocol.json；统一 runner 收入归档。没有额度
JIT、警告被限流导致记录不完整或任一调用者失败，都不能记 PASS。

```sh
# Guest only; existing entries, not another daily test case.
make -C tests/unit run TESTS= \
  PY_TESTS='test_hostcall_codegen.py test_jit_entry_scope.py test_exe_registry.py test_mutex_signal_protocol.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite hostcall
```

修改共享 executor 时，再选双后端 progress 单元和 mode 2/4、两后端寄存器续跑、
learned mutex-depth；只改观察器则不重复所有 JIT。普通控制 CALL 的混合额度、
`test_exe_registry.py` 同样提取真实服务表及 adapter：修改服务 manifest/adapter
必须运行它，不能只运行导入其 helper 的 consumer 测试。注册替身不执行服务，
但仍须提供真实参数字段和 typed primitive 的编译契约。
坏包/目标/服务属性拒绝由生产 consumer 单元覆盖，不把 mode 5 的 hostcall
实测泛化成普通 CALL 额度、远端额度或任意故障恢复都已实测。

### 6.14 两个独立 Root 共享 B Combiner

详细说明见 [spin_protocols](testing/spin_protocols.md#614-两个独立-root-共享-b-combiner)。

<a id="混合完成waiter-退出与-b-后继"></a>

### 6.15 两个 A Combiner 共享原生 Mutex B

详细说明见 [mutex_protocols](testing/mutex_protocols.md#615-两个-a-combiner-共享原生-mutex-b)。


## 7. 分层与增量回归

按 2026-09-14 的[交付范围](TODO.md#delivery-scope)，极少出现的情况可以不补实现、
不专项测试。极端资源组合、特殊取消/退出顺序和任意别名扩展不再自动成为下一项
任务；已有用例保留供相关改动或显式诊断选择，不要求每轮覆盖所有边界。
常见路径已复现的错误仍须处理，未测场景仍是限制而不是 PASS。

按 2026-09-16 的约定，每次只验证基础简单功能与修改直接影响的功能。
`make -C tests/unit run` 默认只跑两个基础 C 程序；用 `PY_TESTS` 增加相关单元
测试。下面的复杂套件保留为按需选项，不是每轮必跑项；全量仅在明确要求时
使用 `run-all`。旧 PASS 仍只属于其冻结输入。
翻译准备中的 warmup、promotion、发布检查仍必须保留，否则无法保证实际 JIT。
41 个单元入口和 22 个 shell 驱动的逐项用途、重叠分析及精简进展见
[测试用例分析](TEST_EXAMPLES.md)。节点、mutex 交接、frame、CALL 和 tail 模型已由生产测试承接；
live 选择器的套件内容不变，本节说明何时选用；保留入口不等于要求例行运行。

替代依据是执行路径和断言，而不是代码长度或循环次数。复杂用例必须覆盖同一
后端/配置下原用例的关键结果和实际 JIT 执行证据，才可替代对应正例；不同退出
边界、失败分支和协议观测仍独立保留。开发新功能时可先用基础用例定位，复杂
验收通过后，把覆盖较小的用例移出日常范围；完全重复的脚本合并或删除，并更新
本节的替代说明和选择器检查，不让基础用例重新成为每轮默认前置步骤。

`tests/run_all.sh` 无参数只列出范围，不执行内核测试。命令定义集中在
`tests/regression.py`，`--suite` 可重复，`--case` 可点选，两者按用例名称取并集。
所有日常范围都排除基础验收和被更复杂用例覆盖的普通诊断项；`extended` 也排除
已经登记替代关系的十一项诊断。这些关系集中在选择器的 `COVERED_DIAGNOSTICS`，
无参数或 `--list` 会列出，`test_regression.py` 检查它们不会重新进入套件。
去重只针对同一个用例身份，不静默删除用户显式点选的简单诊断，也不因为历史
通过而跳过本次选中的用例；点选诊断不会自动附带它的替代用例。
`--list` / `--dry-run` 不构建、不加载；真正执行只允许 root 在规定 guest 路径，
并要求已经确认 recovery。以下例子按需要选择，不是顺序执行清单：

```sh
# Preview on either host or guest; mode 5 appears only once.
bash tests/run_all.sh --suite mutex --suite hostcall --case mode-5 --dry-run

# Guest only, after confirming recovery: ordinary mutex changes, modes 4/5.
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite mutex

# Dual-frame code/shadow pools, peers and retirement, plus combined node pressure.
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite mutex-parallel

# Focused unit programs only; TESTS= avoids unrelated C unit builds/runs.
make -C tests/unit run TESTS= PY_TESTS='test_regression.py test_mutex_parallel_protocol.py'
```

### 选择范围

| 范围 | 用途与覆盖 |
| --- | --- |
| `baseline` | 首次验收/故障定位：设备加载卸载、无 JIT 执行的翻译链路、mutex_jit=0 原生对照；不随日常回归运行 |
| `native-controls` | 显式纯原生寄存器对照 control-0/3；非目标线程、无翻译/JIT，不加入其他范围，流程见 3.1 |
| `spin` | mode 2/7/8：hostcall、非 LIFO 解锁、多队列嵌套 |
| `mutex` | mode 4/5：竞争嵌套、重复 hostcall/同 CPU waiter/持续竞争，均 mutex_jit=1 |
| `core` | `spin` 与 `mutex` 的五个复杂代表用例；不是全部功能验收 |
| `hostcall` | mode 2/5，不能用普通深层嵌套替代 native service 返回 JIT 的检查 |
| `registers` | 八个退出边界的 GPR/返回栈检查，不被普通业务状态正确所替代 |
| `admission` | GS JIT 正例与上下文/别名拒绝负例；修改分析器还须运行独立 admission audit |
| `spin-native` / `mutex-native` | 对应后端的退出点续跑、提前 A 释放/原生依赖、资源拒绝/容量、后续 native-only 策略；spin 另含受检获取后续跑；mutex 还含真实栈变化、同队列同 CPU 续跑、两项并行 frame 与跨队列同 CPU 满槽/拒绝组合 |
| `spin-remote` | 八层物理 frame 的同/跨 NUMA、多请求远端和三种 late-exit，日常不先重复一层/两层 |
| `mutex-signals` | 原 waiter 的两种不可中断信号、两种 API 的取消/获得/无偏置竞争、独立 native peer |
| `protocol` | 原生参与者互斥和两种 RCU/owner ACK 探针；JIT=0 的探针不能计为 JIT 正例 |
| `mutex-parallel` | 两个真实 JIT/native frame 的两种顺序，合并代码池与 mutex shadow 表满/新队列回退、原生 B 竞争者取消后重排、退休与重载；另含同 CPU 满槽/上下文拒绝/task 分配失败组合 |
| `extended` | 64 项独立/复杂代表用例，排除 baseline、native-controls 及十一项已覆盖诊断；保留 mode 6 的同一 frame 三锁检查，仅在明确要求完整 live 范围时运行 |

以上是按行为划分的起点，不是必跑列表或自动影响分析。不要仅因低概率扩展尚未
覆盖而选择 `extended`、完整信号/资源矩阵。已显式选中的用例仍完整执行原有
断言，不能静默跳过失败项或裁掉阶段后沿用其 PASS 名称。wrapper/ABI、共享 executor、锁入口
或生命周期的改动可能影响多个范围，须取相关范围并集；内核基线变化先重新做
基础验收。只改文档不运行 JIT；只改某个 oracle/测试驱动，验证该驱动及对应 live
用例即可。不能因为复杂业务正例通过而删除尚未覆盖的错误分支或独立协议。
如果只修改测试选择规则，运行
`make -C tests/unit run TESTS= PY_TESTS=test_regression.py` 与 `--dry-run` 即可，
不加载模块或重复 live 验收；单元测试清单仍保留 `run-all` 入口供显式全量检查。
纯原生对照入口的改动选择 `test_regression.py`、`test_native_registers.py`，
两项 `native-controls` 和受影响的嵌套寄存器 JIT 正例。只是修改选择规则时仍
只做单元/预览，不把原生对照变成每轮必跑的基础检查。

设备会话改动选择已有的 `test_daemon_policy`、`test_text_regions.py` 和
`test_jit_diagnostics.py`，分别检查真实 fork/exec、分块传输、设备身份/关闭和
翻译错误分类；不新增重复的基础脚本。对应 live 选择 mode 2/4/5、
`native-mutex-depth` 和 `context-mixed`，覆盖两后端执行、hostcall、学习后的
再次翻译和 native-only 发布。独立的真实 cdev 引用探针及其边界见
[设备会话验收](VALIDATION.md#device-session-binding)，不能计为一次 JIT 执行。

只修改 5.3 的能力协商时，选择 `test_source_lifetime.py`、`test_text_regions.py`
和 `test_native_after_outer.py`，分别检查真实 ioctl/退休边界、同设备缓存/错误包、
共享窗口常量与运行时续点。live 用 `native-mutex-stack-change` 替代普通 mode 4，
保留 mode 2/5、`native-mutex-depth`、`context-mixed`，再取 `mutex-parallel` 并集。
这覆盖实际能力查询、两种孤儿 writer 排空及共用清理，不新增基础前置检查；
没有修改分析规则时不附带完整 admission audit。

源码生命周期改动再选择 `test_source_lifetime.py` 及实际受影响的 registry、
frame、入口和路由测试。该专属程序提取生产 source/device/retire 逻辑，检查
容量、去重、LIVE/init 范围、关闭后的准入、忙状态和失效先于 module_put，
不以用户态替身声称内核 reader 已排空。其 live 验证并入现有两个
`parallel-drain-*`，原来的 JIT/逐锁 ACK/精确记录断言不减少。同 CPU 资源压力
分支不提前退休，避免阻止待测的新请求；所有分支结束时都经公共 retire 清理。
仅测试驱动修正时重跑失败项及对应复杂用例，不自动附带已通过的基础检查。
6.6 的 writer/重载、代码池、shadow 表和 B peers 共用三个 `mutex-parallel`
复杂用例，不另保留旧简单版本或附带 baseline。相关驱动修改选择
`test_mutex_parallel_protocol.py`，再按实际资源改动补注册表/入口或
`test_mutex_resources.py`，不运行全量单元测试。shared-CPU 压力分支检查共用
脚本的默认路径。只改观察器时只选其单元与受影响 live；只改文档时不运行 JIT。
额外锁的晋升准备是资源实验前提，不是重复的基础验收；失败结果与不同冻结
版本仍须分开保留。
两源码扩展升级现有 `native-mutex-depth`，与 `native-4-4` 一起检查可选模块路径及
共享脚本的 PENDING 路径（现含 6.1 的同 CPU 续跑）；不附带单模块 depth 或基础 smoke。新增观测用
`test_source_depth_protocol.py` 检查错误状态、pin/loader 混淆、错误目标和提前释放；
选择器另检查残留 `kd_depth_source` 必须阻止下一项。修改观测后只重跑该程序；
生产 source/寄存器/分析器未变时，不把已接受的独立测试全部重新运行。
当前该用例已升级为两次真实 CALL 学习，不再附带旧的 inline 适配器版本。
若同时修改 5.3 的分析规则，先运行相关分析/生成单元程序和 audit，再取 `core`、
`native-mutex-depth`、真实栈变化、mutex 两个寄存器退出边界及 `context-mixed`
的并集；相同观察器或默认驱动已被其中用例覆盖时不再重复选择。

例如修改两后端共用的返回表生成器，先选择 5.2 的五个分析/生成程序和 audit，
再运行 `core` 加已学习深度路径，不附带 baseline、单锁 mode 0/3 或全量单元测试：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite core --case native-mutex-depth
```

### 合并与保留

以下是普通成功路径的替代关系，不是对所有故障、指令或调度的等价证明。
基础诊断仍可用 `--case` 点选；其余独立负例、寄存器和生命周期探针不因此删除。

| 仅点选的诊断 | 回归中的替代用例 | 保留的检查 |
| --- | --- | --- |
| `mode-0` | `mode-2` | 单 spin 锁的 JIT body、完整状态、排空，并增加 hostcall 返回 |
| `mode-1` | `mode-8` | A/B 嵌套锁/解锁、实际 JIT、完整状态，并增加内层队列竞争 |
| `mode-3` | `mode-5` | mutex_jit=1 的单锁代理、实际 JIT、原锁互斥与状态，并增加重复 hostcall/持续竞争 |
| `node-physical-1-0` / `node-physical-2-0` | `node-physical-8-0` | 相同 NUMA 配置的真实物理 frame/node 生命周期与队列观测 |
| `node-physical-1-1` / `node-physical-2-1` | `node-physical-8-1` | NUMA-aware 配置下相同断言，增加链深度 |
| `parallel-shared-cpu` | `parallel-node-pressure` | 同 CPU pre-body 拒绝、存活 frame/owner ACK，并增加真实满槽和 task 分配失败 |
| `native-1-4` | `virtual-ticket-refusal` | 相同 PENDING B 续跑、实际 JIT、原 waiter 排队和最终 ACK，增加真实 32-ticket/gate 表满及新锁原生互斥 |
| `native-1-3` / `native-4-3` | `registers-1-3` / `registers-4-3` | 同后端普通 held-B CALL miss、业务记录/native probe、B->A 后缀，增加原始寄存器和 CALL 栈检查；不覆盖 6.10 的提前 A 释放 |

mode 6 不属于上述替代关系：同一 frame 中保留 A/B/C 与多层物理 frame 不同。
日常核心范围无需先跑它，但 `extended` 仍检查该独立深度路径。
`shadow-capacity` 同样不是八层物理链的重复项；二者到达不同的容量检查，见
[6.8](testing/spin_protocols.md#68-物理-frame-链与容量检查)。保持 `spin-native` / `extended` 中的独立入口。

- 删除 `test_03_hotlock.sh`、`test_06_daemon.sh`，合并到 `test_02_jit_engine.sh`：
  一次准备检查 promotion、entry、内核文本读取、生成物、确切入口发布和排空后清理。
  `pipeline` 不执行生成代码，仅用于首次验收/定位。
- 删除 `test_07a_mutex_jit_smoke.sh`；mode 3 的 `test_07` 验证同类单锁成功路径、
  总计数和更多竞争场景，且有返回后 body witness；不再为“恰好一次 JIT”单设
  调度烟测。需要单锁定位时用 `--case mode-3`。
- mode 0/1/3/6、一层/两层 frame 等诊断入口仍可点选，但不附带在复杂用例前执行。
  `test_09` 保留为主模式兼容入口，无参数只显示统一清单；显式模式去重且不会
  自动附带其替代用例。需要完整主模式验收时须明确传入模式，见第 3 节。
  不删除 benchmark 的 mode 定义。
- 同 CPU 用例复用 `test_23` 的参数分支；日常用 `parallel-node-pressure` 同时验证
  context refusal、真实满槽和另一请求的注入 task 分配失败，不再运行覆盖较小的
  `parallel-shared-cpu`，也不为每种资源增设重复的基础脚本。
- 源码退休 busy/排空检查扩展已有双 frame 用例，不另设“加载一次、卸载一次”的
  smoke；同设备能力协商也复用该用例中的实际 writer。状态机边界与错误变异
  测试仍独立保留，不能由复杂正例通过替代。
- 栈变化续跑扩展 `test_10` 的七角色竞争驱动，不另加简单 smoke。它检查已完成
  控制 CALL 的后继，不能替代 PENDING 未开始获取或普通 CALL miss 的独立检查。
- `waiter-interruptible` / `waiter-killable` 检查取消后 A 的最终 ACK 已完成、
  原生 B owner 仍持锁。释放竞争用例允许 B 更早解锁，即使也返回 `-EINTR`，
  仍不覆盖这个持锁进度断言。因此前两项保留在 `extended` 并可单独点选，
  不自动加入日常 `mutex-signals`；同一命令的不同环境参数不能直接当作重复项。
  具体执行流和 oracle 见 6.4/6.5，选择器测试检查两类用例不会被相互替代。
- 单元测试中刻意构造的边界、失败变体和 JIT=0 协议探针并非重复正例，继续保留。

### 执行与证据

执行流为：选择/去重 -> 确认 guest/recovery 与空闲状态 -> 冻结源码及起始环境 ->
按项运行现有脚本和 oracle -> 检查退出码、dmesg、排空、源码未变 -> 归档证据 ->
全部满足后创建 `accepted` 并运行下一项。任何失败停止后续，不自动重试、强制
卸载或放宽判定。
runner 清除继承的 `KD_*` / `KDLOCK_*` 注入变量，只使用选中命令的明确设置和
recovery 确认；特殊参数实验应直接调用相应脚本，不冒充命名用例。

输出目录默认 `/tmp/kdlock-regression.*`，或 `--output` 指定一个仓库外的新目录。
不用再从多个临时目录手工拼接常规用例证据：

| 文件 | 用途与边界 |
| --- | --- |
| `selection.json` | 精确脚本、参数与本次选定的注入环境，不包含未运行项目的通过结果 |
| `source.json` / `source.tar.gz` / `source-archive.json` | 冻结运行/测试输入及逐文件、整包 SHA256；含 `requirements.txt`、`guest.config` 和 guest 补丁，排除任意生成文本及 Kbuild 生成文件 |
| `environment.json` / `kernel.notes` | 用例开始前的 boot notes、uname、启动参数、CPU/NUMA、挂载/抢占/sysctl、工具和 Python 依赖查询；不是完整构建环境或执行中配置证明 |
| 每项的 `output.log` / `exit-status` / `dmesg.log` | 脚本输出、原始退出码和结束时内核日志；日志读取失败也使验收失败 |
| `artifacts.tar.gz` / `protocol.tar.gz` | 生成工作区，以及脚本明确宣告的协议/角色/daemon 文件，不扫描无关临时文件 |
| `post-case-builds.tar.gz` | 用例结束时存在的模块、daemon 和 benchmark 文件；可能包含恢复的默认构建或先前的可选模块，不等于实际加载镜像的身份 |
| `evidence.json` | 三个证据包及各成员的 SHA256、原目录/文件路径和符号链接文本 |
| `result.json` / `accepted` | 独立记录 script_exit、kernel_fault、drained、source_unchanged、evidence_complete、错误与起止时间；全部通过后才创建标记 |

环境采集使用与脚本相同的基础环境，固定 `LC_ALL=C`；命名用例的 `KD_*` 设置
仍在 `selection.json` 中。只保存代码内明确列出的 PATH、编译/Python 等继承
变量，不转储整个环境；未设置的变量为 JSON `null`，不等于工具的默认值。
只读查询常用 gcc/cc、make、binutils、bash，记录选择路径、解析目标、SHA256、
版本输出和状态；不执行任意 `CC`/`MAKEFLAGS` 字符串来猜测完整构建命令。
Python 依赖通过 PATH 中的 `python3` 查询，不假定它与 runner 解释器相同。
记录 miasm、pyelftools、future、pyparsing 的安装版本、位置与声明依赖，不导入
翻译器或访问 JIT 设备。启动保留原工具/虚拟环境链接路径，哈希读取解析目标；
这不改变协议归档禁止跟随链接的规则。

每个命令查询限时 10 秒；缺失工具/包、非零退出、超时、损坏 JSON 或无法读取
运行设置会在 `environment.json` 中保留错误并停止，尚未启动任何用例。
`stage=before_cases` 是起始观察，不是整个测试期间配置/依赖未变化的证明。
脚本随后可能设置 sysctl 或重建 SELFTEST 镜像，仍以脚本和逐项协议证据为准。
版本元数据和工具二进制哈希不覆盖全部导入代码、动态库、编译参数或加载镜像；
不得据此自动跳过测试、把未运行项记 PASS，或宣称字节锁定/完整可重复构建。
运行包版本另由 `disassem/requirements.txt` 固定，安装步骤只维护在手动指南；
元数据采集本身不会强制版本、安装包或选择 venv，也不会打包其内容。

`results.tsv` 的 0 只代表脚本退出码，不能替代 `accepted`。脚本通过也可能因
缺少已宣告文件或归档失败而被拒绝；归档完整也不证明执行了 JIT，仍须保留本
文规定的返回后 body witness 和逐用例 oracle。上下文负例允许没有 `jit.bin`。

现有 `Evidence: /tmp/kdlock-*` 声明整棵协议目录，公共 daemon 启动函数另输出
`Evidence file:`。重复声明或已经在协议目录内的 daemon 日志只收集一次。
协议树中的符号链接仅保存目标文本，既不读取目标，也不在 tar 中创建活动链接；
writer 探针指向的 helper 本身已在冻结源码包中。源码、生成工作区和独立声明
的文件仍不允许通过链接越界。设备、FIFO、递归包含输出目录以及文件变化都
使归档失败；失败的 `.partial` 不是完整证据包。

失败且调用者/模块已排空时也保留镜像和协议，以便后续清理临时目录后查验。
未确认排空时只保留已经取得的源码、命令、输出和状态，标记
`evidence_complete=false` 并停止；不把仍在变化的文件伪装成冻结证据，也不强制
卸载或重跑来补齐 PASS。原始临时目录不自动删除；主输出目录可直接整体 tar
归档，SHA256 清单用于核对内容，不是签名或不可变 JIT 版本证明。

已有输出目录可用仓库内的只读工具校验，`RUN_DIR` 指向该目录：

```sh
python3 tests/verify_evidence.py "$RUN_DIR"
```

执行流：读取冻结源码、起始环境与选择清单 -> 核对 boot notes/源码包 -> 按
选择顺序核对 journal、退出码、日志、result 和 accepted -> 核对三个证据包的
精确成员及哈希 -> 再查读取期间文件未变 -> 输出 JSON。工具不执行记录中的
命令、不解包载荷、不跟随 tar 链接，也不访问当前 guest/JIT 设备或修改结果。
不要求 root/recovery；离线归档复核可在宿主机或 guest 完成，工具单测仍在 guest。

- 退出 0：所选项目都有一致且通过的历史记录。
- 退出 1：记录完整但含失败，或部分选中项目尚无记录。
- 退出 2：记录矛盾、缺少必需文件、未完整归档、文件变化或格式/大小不支持。

`unrecorded_cases` 只表示缺少结果，不证明进程从未运行或已经退出，不能据此
重启 VM。工具限制单文件元数据 16 MiB、压缩包 256 MiB、单包完整解压流 1 GiB
和清单/包成员 100000 项；超限不静默忽略。只认当前采集格式，不自动补造旧记录。
这些检查不认证记录来源，也不重新执行逐用例 oracle；若内容与全部清单一起被
改写，一致性本身不能识别伪造。仍需可信的外层包 SHA256、原执行证据和
case-specific JIT/协议检查。不得把离线校验记为新 JIT、当前源码通过或加载镜像证明。
只改该只读工具时运行 `test_regression.py`，再检查已有成功/失败归档即可，
不重跑无关负载。当前工具验证见 [离线校验](VALIDATION.md#offline-evidence-verifier)。

只修改用例开始前的只读环境采集时，运行 `test_regression.py` 即可；它同时
实际读取 guest 环境、核对工具字节和检查缺失/超时/坏输出的停止边界，不加载
模块或重复 JIT。当前结果见 [环境证据](VALIDATION.md#environment-evidence)。
修改逐项归档流程时运行该单元程序，再选一个带协议目录的复杂正例、
独立 daemon 日志的 hostcall 正例和已有上下文负例。归档修正后只重跑失败项及
尚未运行的受影响项，不重复已经覆盖且实现未变的路径。本轮冻结版本与失败
记录见 [归档验收](VALIDATION.md#scoped-evidence-capture)。源码包不包含系统依赖的
完整字节、guest 磁盘或整个内核构建目录。原生对照已改用 3.1 的仓库内驱动，
起始工具/依赖元数据也已采集，Python 运行包有版本配方；但完整系统依赖字节、
内核构建环境及历史镜像身份仍独立保留，不能宣称任意 fresh checkout 已能重现
全部历史结果。

每项默认外层超时 600 秒，可显式调整；不要因此取消 SSH 的外层超时。
在输出目录创建 `STOP`，会等当前项结束并检查排空后于下项之前退出 93；
不改写运行中的脚本，不在 native waiter 仍持有 frame 时中断它。

当前 `extended` 包含已登记脚本的代表组合，不穷举所有参数，也不等于历史
67 项矩阵：它不自动包含显式 `native-controls` 和上述已覆盖诊断，另含 shadow-capacity、
两项 native-peer 和同 CPU context refusal/真实满槽扩展。历史矩阵的命令和结果
仍按当时冻结版本记录，不改写为新的选择范围。
结果入口见 [tests/README.md](../tests/README.md)，历史冻结索引保留在
[VALIDATION](VALIDATION.md)。每次只报告实际选择的项目；未选择项是
未重跑，不把旧结果合成当前版本的“全量通过”。
