# spin_cacheline：首次执行、代理 JIT 与开销路径

本文从 `SC_RUN` 展开到原 waiter 恢复，供对照源码和汇编查找性能问题。
伪代码随当前实现更新；历史采样与性能结果仍只属于各自冻结版本。
负载、测量口径和操作入口见 [README](README.md#临界区与测试伪代码)。

阅读条件：x86_64，普通任务上下文，单层 `sc_body_N`，同一把 spinlock，
`KDLOCK_SELFTEST=0 KDLOCK_NUMA=0`，`bench_quiet=1 jit_timing=0`。
后续详细伪代码按 `6.1.159-kdstatic2` 的旧调用者 ABI 展开；接口的差异
在第 2 节注明。伪代码合并错误处理，但保留影响主路径成本的查表、原子操作、
复制、校验和等待；辅助函数名不等于最终机器码一定存在一次 CALL，须对照反汇编。

`kdclobber1` 的普通调用者先由编译器保存跨 lock/unlock 活跃值，asm 传递
RDI=锁、RSI=SP、RDX=续点、RCX=BP，经独立 static-call bridge 进入同一锁层。
排队请求只记录三个续点字段；锁侧统一循环通过内联 asm 调用偏移 32 的 wrapper，
正常完成只回写并恢复三个字段。hostcall/nested/native 中间退出仍完整保存并走
下文通用处理。新、旧及混合 ABI 均在同一个 C 栈帧内连续处理；旧偏移 16
入口的内联适配只额外保护 RBP，原汇编外壳已退出生产构建。
两种调用者都保留 L/S、ticket、source、owner/ACK 及 IRQ 协议；完整定义见
[寄存器 ABI](../../docs/JIT_REGISTER_ABI.md#10-普通-spin-的-caller-clobber-v1)。

| 符号/状态 | 含义 |
| --- | --- |
| `L` | workload 的 `sc_lock`，真正排斥原生参与者的 Linux 锁 |
| `S` | `gate->word`，kdlock 私有队列调度字；包含 locked、pending、tail，不能替代 L |
| `RIP` | `sc_body_N` 内 `_raw_spin_lock` 调用后的原始入口地址；不是函数起始地址 |
| waiter | 提交请求的线程，保留自己的内核栈、寄存器包和 origin ticket |
| combiner | 获得 S 并实际持有 L、在自己的 CPU 上替 waiter 执行正文的线程 |
| `NORMAL` | JIT 已发布；单凭此状态不能证明本次测量执行过 JIT |
| `NO_JIT` | 测量前后实际正文计数差为零；仍可能走过 kdlock 管理或等待路径 |

建议按以下顺序阅读：

1. [批次边界](#batch)：哪些操作每次 ioctl 一次，哪些每次抢锁一次。
2. [首次执行与注册](#cold)：热锁发现、准备翻译以及重复注册检查。
3. [先 CAS 的无竞争路径](#native-fast)：单线程 NO_JIT 通常走这里。
4. [竞争与队列](#queue)：ticket、原锁、waiter 等待和 combiner 批次。
5. [一次实际 JIT](#jit)：frame、dispatcher、wrapper、生成正文和恢复。
6. [开销核对表](#costs)：常见成功路径的重复操作和优化优先级。

<a id="batch"></a>

## 1. 一次 ioctl 的测量边界

对应 [client.c](client.c)、[module.c](../../workload_modules/spin_cacheline/module.c)、
[payload.h](../../workload_modules/spin_cacheline/payload.h) 和
[post_work.h](../../workload_modules/spin_cacheline/post_work.h)。

```text
用户态主线程：
    读取初始数据；创建 T 个线程
    等待所有线程完成绑核、设置 sc_worker 名称并发布 atomic ready
    wall_start = now(CLOCK_MONOTONIC)
    store_release(go, true)

每个 worker：
    load_acquire(go) 放行后：
        cpu_start = now(CLOCK_THREAD_CPUTIME_ID)
        ioctl(SC_RUN, N, I)                     // 每线程一次，不是每个 op 一次
        finished = now(CLOCK_MONOTONIC)
        cpu_time = now(CLOCK_THREAD_CPUTIME_ID) - cpu_start

内核 SC_RUN：
    copy_from_user；检查参数；选择固定展开的 sc_body_N
    atomic_add_unless(sc_control, +1, -1)        // 整批准入；-1 表示快照独占
    post_state = 1
    for completed = 0 .. I-1:
        sc_body_N():
            spin_lock(L)                       // 后续章节展开此调用
            EXPAND_N(READ_ONCE(slot[i]) + 1 → WRITE_ONCE(slot[i]))
            spin_unlock(L)                     // 或代理完成后直接恢复到它的后继
        post_state = sc_post_work(post_state)  // 4 组依赖乘加，8 条寄存器指令
    atomic_dec_return_release(sc_control)
    copy_to_user(completed)；返回

用户态主线程：
    join；读取最终数据并检查所有 16 个槽
    wall = max(worker.finished) - wall_start
    throughput = sum(completed) * 1e9 / wall    // wall 单位 ns，吞吐单位 op/s
```

`EXPAND_N` 是编译时展开的 N 次读改写，不是锁内循环。全部线程访问同一数组，
每个槽间距 64B；锁内没有时钟、syscall、日志、mutex 或服务调用。
原子起跑等待只在 ioctl 前；热循环没有 `cond_resched()`、sleep/yield 或强制交接。
时钟在批次边界调用，开销按 I 摊销；`ns/op` 包括正文、锁协议和锁外计算，
不是单次锁获取延迟。

<a id="cold"></a>

## 2. 首次执行：原生、发现热锁、注册和翻译

### 2.1 每次 spin_lock 的内核入口

对应 [guest-kernel.patch](../../kernel_experiments/spin_static/guest-kernel.patch)、
[kd_lock.c](../../kernel_module/kd_lock.c) 和
[kd_spin_select.h](../../include/kd_spin_select.h)。

```text
_raw_spin_lock(L):
    保留现有 hook 所要求的 callee-saved 寄存器栈布局
    if selector 指针存在 and (combined static key 开启 or select() == 2)
       and lock callback 指针存在:
        保存原始 RSP；取得调用后的 RIP
        static_call(kd_spin_lock_call)(L, saved_RSP, RIP)
        return
    __raw_spin_lock(L)                          // Linux 原生获取

kd_spin_dispatch_lock(L, saved_RSP, RIP):
    尝试可选的原生站点缓存：命中且成功获取 L 则返回
    失败若临时 pin 则先归还；关闭 spin_native_cache 不尝试缓存
    selected = (source.OPEN and comm 两个机器字掩码匹配 sc_worker)
               or 当前任务仍有未结束的原生 fast/ticket
    if !selected: origin_raw_spin_lock(L); return
    kd_raw_spin_lock_slow(L, saved_RSP, RIP)
```

当前 R2 在可选缓存未完成获取后做 target/retained-owner 选择。旧指针 hook 接口先调用独立
selector，再间接调用 `__kd_raw_spin_lock`；不能把旧接口的额外 selector 成本
直接计到 R2 上。原生对照不加载 kdlock，但仍使用带既有 hook 的同一实验内核。

### 2.2 冷锁：只执行原生正文，累计访问频率

对应 [kd_hotlock.c](../../kernel_module/kd_hotlock.c)。

```text
kd_raw_spin_lock_slow(L, saved_RSP, RIP):
    if kd_spin_entry_native_active() or !kd_hotlock_is_promoted(L):
        kd_hotlock_record(L)
        origin_raw_spin_lock(L)
        return                                 // 调用者执行原生正文及 unlock
    kd_exe_add(0, RIP, SPIN)                     // 见 2.3；已注册也调用！
    kd_spin_lock(L, saved_RSP, RIP)                  // 第 4 节；仍不保证 JIT

kd_hotlock_is_promoted(L):
    对只追加的表做哈希/线性探测；acquire 读取已发布的地址
    命中 L 后 READ_ONCE(status) == DELEGATE；遇到空槽/探测完毕则 false
    查询不加锁、不关闭中断、不做原子 RMW

kd_hotlock_record(L):
    now = rdtsc_ordered()
    首次用 atomic cmpxchg 建立模块级起始 TSC
    if 模块预热不足 1,000,000,000 cycles: return
    raw_spin_lock_irqsave(global_hotlock_table_lock)
    查找/创建 L 的记录；已 DELEGATE 则直接退出
    now = rdtsc_ordered()                       // 按持锁更新顺序重新取时间
    samples++
    INIT → CHECKING，记录起点及 2,500,000,000 cycles 的窗口
    后续采样：窗口到期 → IGNORE；到期前累计 10,000 个样本 → DELEGATE
    IGNORE 保留该状态；退出时 unlock_irqrestore
```

未晋升的 lock/unlock 都可能采样；**样本不是失败的 trylock 次数，也不是等待次数**。
因此单线程也能晋升、注册并生成 JIT，却没有其他 waiter 可供代理。
`rdtsc_ordered()` 属于发现过程，不能解释已发布单线程快路径的每次耗时。
表项地址由写侧 release 发布，状态转换使用 WRITE_ONCE；查询与新建/晋升并发时
允许返回 false，调用者继续经过采样器和原生锁。采样器仍使用全局写锁，
尤其 IGNORE 锁仍会采样；无锁查询不等于整个冷锁路径无锁。表项在模块存活期间
不删除、不复用，释放整张表前仍要求调用者排空。
`kd_spin_entry_native_active()` 在没有已有 preempt pin 时直接返回 false，不扫描
ticket；已有 pin 的调用者只扫描 per-CPU 活跃位图中的槽。查询复用已有 pin，
不再临时 disable/enable 抢占；其在本路径和下文 `kd_spin_lock()` 的调用均保留。

### 2.3 注册不是编译；已发布条目只读确认

对应 [registry_publish.inc](../../kernel_module/execution/registry_publish.inc)、
[registry_lifecycle.inc](../../kernel_module/execution/registry_lifecycle.inc)、
[exe.c](../../kernel_module/exe.c)、[kd_source.c](../../kernel_module/kd_source.c)。

```text
kd_exe_add(0, RIP, SPIN):
    exe = kd_get_exe(0, RIP)                    // acquire 读取发布状态后比较 key
    if exe 已发布（不是 UNUSED）and pid/RIP/SPIN/代码指针匹配 and source.OPEN:
        return                                 // 已注册，不代表 NORMAL 或允许执行
    while cmpxchg_acquire(global_code_block_gate, 0, 1) != 0: cpu_relax()
    kd_source_pin_root(RIP):
        raw_spin_lock_irqsave(global_source_lock)
        检查 OPEN、地址属于有效 text；查找 module 及已有 source pin
        首次依赖该 module 才 try_module_get 并加入来源表
        raw_spin_unlock_irqrestore(...)
    exe = kd_get_exe(0, RIP)                    // 哈希/线性探测
    if 已有同一 pid/RIP:
        检查 lock_kind 一致；不重复生成或分配代码
        store_release(global_code_block_gate, 0); return
    从装载时预分配的 64 个 executable block 中取一个
    设置 pid=0、RIP、tgid、SPIN、code_block
    store_release(exe.status, UNINIT)
    store_release(global_code_block_gate, 0)

```

`kd_spin_fast_remember` 只在 root 且缓存启用时处理。L/RIP/gate 键完全相同
则立即返回，删除旧代码在每次竞争 miss 后仍进行的重复 NORMAL 查询；新键
才查询注册表并检查 NORMAL/source.OPEN。缓存本身不授权 JIT 执行。
`vmalloc/set_memory_x` 在 provider 初始化时预分配代码池，不在每次抢锁内分配。
每次已晋升慢入口仍调用 `kd_exe_add`，但同身份/后端且 source OPEN 的已发布
条目现在只做读取，不再进入全局 gate、source irqsave 或模块地址查询。
UNINIT、miss 和 native-only 也可确认已注册；是否执行仍由 NORMAL 与 frame
准入决定。首次注册、冲突或关闭准入时保留原串行化检查。并发发布后的身份
须重新核对，不能把 lookup 返回的空槽误当作已有条目；退休同步见
[source 生命周期](../../docs/DESIGN.md#31-source-lock-and-hook-lifetimes)。

### 2.4 daemon 的首次翻译与测量前准备

对应 [daemon.c](../../daemon/daemon.c)、[disassem.py](../../disassem/disassem.py)、
[sys.c](../../kernel_module/sys.c) 和 [Session.prepare](bench_session.py)。

```text
daemon（用户态，持有设备会话）：
    read /dev/kd_dev，发现 UNINIT 的 pid=0、RIP、SPIN 条目
    fork/exec Python translator；保留设备 lease
    读取原始内核字节与符号，解码控制流、检查上下文及支持的指令
    寄存器/栈映射；生成入口分派、正文标记、已知 unlock 的退出代码
    输出 asm/jit.S
    gcc 汇编 wrapper.S（包含 jit.S）→ jit.o
    objcopy → jit.bin；objdump → bin.txt
    等待 translator 成功退出，分块 write /dev/kd_dev 上传 jit.bin

内核上传：
    mutex_lock_interruptible(kd_publish_lock)    // 上传控制面，不在 worker 抢锁路径
    检查设备 lease、条目和写入范围；copy_from_user 到 code_block
    最后一块完整写入后，用 kd_exe_publish_status 的 cmpxchg 发布 NORMAL
    mutex_unlock(kd_publish_lock)

bench 准备一个新会话：
    加载新 workload/provider；启动 daemon
    同样 T 个绑核 worker：每线程 1 次 → sleep(1s) → 每线程 12,000 次
    等待唯一匹配 RIP 的条目 NORMAL、生成物有效、translator 成功退出
    检查 worker/frame 排空；停止 daemon；确认 writers=0
    两组均 sleep(2s)
    读取 jit_before，再开始第 1 节的测量批次
```

翻译、上传以及这里的 sleep 都在准备阶段。worker 不在某次 lock 内同步等待
Python 编译：若 combiner 发现 JIT 未就绪，返回 `NO_RUN`，让请求获取原锁后
执行原生正文。正式测量时 daemon 已停止，不能把编译时间或上传 mutex 当作
测量期每次 JIT 的开销；生成物按临界区去重的导出也发生在测量与排空之后。

<a id="native-fast"></a>

## 3. 无竞争 root：缓存原生获取与先 CAS 的入口

对应 [kd_spin_fast.h](../../include/kd_spin_fast.h) 和
[kd_spinlock.c](../../kernel_module/kd_spinlock.c)。`spin_native_cache=1` 默认保留
原生站点缓存；装载 provider 时设为 `0` 可关闭，参数在会话中只读。缓存键与
本次物理 hold 分开：前者可跨获取复用，后者必须在本次 unlock 清除。

缓存命中要求 root、source.OPEN 和整个 S 空闲，再实际 trylock Linux L；成功
不建立 ticket/S owner。解锁只释放 L 和 pin，嵌套调用沿用原生路径。关闭缓存
或未完成获取时，进入以下与 TCLock 相同的“先 CAS、再准备竞争请求”顺序：

```text
kd_spin_lock_abi(L, SP, IP, BP, abi):
    已完成目标选择、热锁晋升检查和 entry 注册
    检查 task/softirq/migration/native-active；不适用则原生
    preempt_disable()
    检查当前 frame/执行上下文；不适用则归还 pin 后原生
    gate = kd_spin_gate_get(L)
    if 无 gate: 归还 pin 后原生
    缓存启用时尝试记住新键；已有相同键不再查翻译表
    if 是 root 且 cmpxchg_acquire(gate.S, 0, LOCKED) == 0:
        kd_spin_gate_claim(gate, fast.hold)   // 复用 pin，获取 L；保留 owner/代次
        fast.held = L                        // claim 失败则释放 S、归还 pin 后原生
        return                               // 自己执行原生正文
    否则进入第 4 节，以同一 gate/pin 建立 ticket

kd_spin_dispatch_unlock(L):
    if 本任务/CPU 的 fast.held == L 且持有 S/L:
        gate = fast.hold.gate
        kd_spin_gate_release(fast.hold)       // 检查 owner/代次，释放 L
        store_release(gate.S.locked, 0)  // 保留并发 pending/tail 位
        fast.held = NULL                     // hold 已清零，缓存键保留
        preempt_enable()
        return
    缓存原生 L-only 持有者释放 L/pin；其他进入第 5.5 节的 slow unlock
```

无竞争获取不创建 ticket、node、frame，也不捕获寄存器。成功后同时持有 S/L，
以 L 排斥原生 peer；先释放 L 再打开 S。线程改名、关闭准入及嵌套调用不丢失外层持有记录。
内层仍正常发现/注册条目并建立独立 ticket；轻量 root 不是 native suffix，
不能据此禁止内层准入，否则无竞争预热会漏掉内层 JIT。与 TCLock 相同的是先尝试锁字、竞争后准备请求；仍存在
目标/热锁/翻译条目/gate 查询和双锁字成本，不能据此宣称已等同 TCLock。

<a id="queue"></a>

## 4. 竞争后的 ticket、原锁所有权和队列

### 4.1 准入与 S 的获取

对应 [kd_spinlock.c](../../kernel_module/kd_spinlock.c)、
[kd_spin_entry.c](../../kernel_module/kd_spin_entry.c)、
[kd_spin_gate.c](../../kernel_module/kd_spin_gate.c)、
[state.inc](../../kernel_module/spin/state.inc) 和 [queue.inc](../../kernel_module/spin/queue.inc)。

```text
kd_spin_lock_abi(L, saved_RSP, RIP, BP, abi):
    执行第 3 节的准入、pin 和 gate 查询
    root 已尝试 S 的 CAS；成功已返回，失败保留 old
    kd_spin_entry_begin_pinned(L, gate, ref):
        检查 task、已有 pin、参数及 gate 对应 L
        扫描 occupied 活跃 ticket，拒绝同任务重复获取 L
        对 ~occupied 找首个空位，检查 32 槽容量与 sequence 溢出
        raw_spin_lock_irqsave(ticket.guard)
        写 task/L/gate/sequence/cpu/state=WAITING，清 hold/native_refs
        置 occupied；raw_spin_unlock_irqrestore(...)
        成功将已有 pin 的结束责任交给 ticket；失败不消耗 pin
    准入失败：归还 pin 后原生获取 L，不发布请求
    request = {ref=本次 ticket, S=gate.word}   // 不再次查询 gate
    非 root 先建立 ticket，再 CAS S；成功 goto acquired
    if old 只有 PENDING: 有界轮询 S
    if old 含 tail/pending 等非 locked 位: goto queue
    old = fetch_or_acquire(S, PENDING)          // 直接传 S，不查 map
    if old 出现其他等待者:
        必要时清本次设置的 pending 位；goto queue
    等待原 locked 清除；clear_pending_set_locked(S)
    goto acquired
queue:
    kd_spin_lock_slowpath(L, saved_RSP, request)         // 见 4.2；代理完成者不从这里普通返回
acquired:
    kd_spin_claim_origin(request)
    return                                    // 自己执行原生 sc_body_N 正文

kd_spin_claim_origin(request):
    使用 request.ref                          // 不重新扫描 ticket/map
    guard irqsave：检查 ticket 代次/任务/CPU/状态
    if 已 OWNED: 解开 guard，直接成功           // queue 已 claim 时仍重复做这次检查
    WAITING → CLAIMING；解开 guard
    cmpxchg(gate.owner, NULL, current)
    kd_preempt_disable_raw_spin_lock(L)        // 真正获取 Linux L；不再增加一次 pin
    增加 gate.generation；写 held/owner_cpu/hold
    guard irqsave：CLAIMING → OWNED；解开 guard
```

只有 S 成功还不能访问负载。`kd_spin_gate_claim` 必须取得 L，以排斥没有使用 S
的原生线程。gate 创建在全局 irqsave 锁内复查碰撞链，初始化后用
`store_release(origin, L)` 发布；读取用 `load_acquire(origin)`，已有条目无须
map 锁。表在会话内不删除或换键，受控排空后才卸载。ticket 的 guard 仍独立
保护代次、owner 和状态；稳定 gate 指针不代表已获取 L 或通过 source 准入。
`entry_gate` 在已有 pin 下检查 CPU/task/代次后直接读取本地 gate；只有原任务
改变槽的归属，远端仅在 guard 下修改 native_refs，因此这个读取不再 irqsave。
当前默认自愿抢占内核；覆盖整个请求生命周期的 pin 仍保留到最终结束/ACK。

### 4.2 发布请求、等待和恢复入口

对应 [slowpath.inc](../../kernel_module/spin/slowpath.inc)、
[wait.inc](../../kernel_module/spin/wait.inc) 与
[kd_spin_lock_slowpath](../../kernel_module/kd_spinlock.c)。

```text
kd_spin_lock_slowpath(L, saved_RSP, request):
    保存并关闭本 CPU 的 IRQ；继续使用 task 内核栈
    准备期局部 input 保存调用者 C 栈 RSP、原 hook 寄存器栈 RSP、原 IRQ flags
    记录 SLOWPATH 诊断：查找诊断槽 + this_cpu_inc(event)
    idx = per_cpu.node_count++                 // 每 CPU 最多 4 个 node
    若耗尽：还原 count；轮询 trylock(S) 后返回 acquired（本负载不嵌套）
    execution = 从当前 CPU 的 12 槽预分配池领取 users=0 的 request
    acquire 读零后设 users=1；池满则回到原生/队列路径，不分配内存
    node.execution = execution；node 只保留执行对象引用和队列/调度字段
    初始化 node 的 locked/completed/next/tail、CPU/NUMA、RSP
    将 IRQ flags、jit_waiter/retry/native/pinned 等请求标志放入 execution
    frame_prepare(execution.frame)：只初始化前 72 字节热状态，不访问冷区
    保存 entry/L/GS/task、origin；regs_ref 指向 frame 内唯一寄存器包
    kd_spin_prepare_regs(node)：在本 CPU 解码 hook 保存的 callee 寄存器、RIP/SP
    execution.native_regs_decoded = true       // 在任何队列发布之前完成
    __kd_spin_lock_longjmp(L, node, request):
        S = request.S
        node.execution.queued_at_ns = timing_start()        // jit_timing=0 时返回 0，不读时钟
        old_tail = xchg_tail(S, node.tail)     // 直接原子交换 S.tail
        诊断槽 atomic_inc(waiter_count)
        if old_tail 有前驱:
            previous = decode_tail(old_tail)  // CPU/index → 对应 per-CPU node
            普通物理 waiter：在一段连续汇编内切到本 CPU 的 8KB shadow 等待栈
                在 shadow 栈压入一个旧 C RSP，再发布 previous.next
                不调用 C、不读写旧 C 栈；PAUSE 轮询 locked 等待 release 唤醒
                若 completed/native_resume：放弃旧帧，直接进入安全栈上的恢复函数
                node_count--；退出 waiter 诊断；保存 request 指针、ticket/IRQ flags
                完成 ticket 或标记 native；直接装载共享包
                最后一次读取后归还 request（单锁 release store；共享/复杂原子递减）
                恢复原 IRQ 状态；跳到续点
                只有未执行正文的队头唤醒才弹出旧 RSP 并返回 C
            虚拟 waiter：原有 C 等待及 remote_poll，保留 owner/ACK 协议
        等待 acquire(S.locked | S.pending) == 0 // 到队首后仍可能等待
        if 自己是唯一队尾 and CAS(S, tail, LOCKED) 成功:
            claim_origin(request)；结束 queue timing；node_count--；退出 waiter 诊断
            恢复原 IRQ 状态，正常返回 acquired
        设置 S.locked=COMBINER；claim_origin(request)
        结束本队首的 queue timing
        while node.next == NULL: cpu_relax()
        检查 shadow 锁栈容量；保存 combiner 状态、RSP
        node_count--；临时置自己 node.rsp=0；将 L 压入 shadow 锁栈并校验
        run_combiner(L, node.next, request)             // 服务跟在自己后面的请求
        弹出 L、校验并恢复 shadow 状态/RSP；还原 S 的持锁状态
        退出 waiter 诊断；恢复原 IRQ 状态，正常返回 acquired
```

源码宏 `smp_cond_load_relaxed_sched` 名字带 `sched`，但这里的定义只有
`READ_ONCE` 和 `cpu_relax()`，没有主动调度。`preempt_enable()` 在释放对应 pin
时仍可能允许调度，不能据此宣称完全不会被切走。
普通物理 waiter 完成/native 唤醒不再经过旧 C 返回链。桥接函数仍处理
普通获取返回 0/2，以及未执行正文的 `jit_retry` 返回 4；虚拟 waiter 保留
返回 1/3/5 以通知现有父 frame。所有恢复都保留原 IRQ 状态。

### 4.3 combiner 的批次不是每个 waiter 一次物理解锁

对应 [combiner.inc](../../kernel_module/spin/combiner.inc)。

```text
run_combiner(L, first_follower, request):                // 进入时 combiner 已持有 L
    batch.request = request；S = request.S
    curr = first_follower; next = load_acquire(curr.next)
    if next == NULL and S.tail 非零且 decode_tail(S.tail) != curr:
        等待 producer 发布 curr.next，再 acquire 读取
        // 首次进入且仍持有 S/L，尚无 NUMA 拼接；真正队尾不等待
    if next == NULL or curr/next 是 IRQ 特殊节点 or source_frame_get() 失败:
        S.locked = LOCKED
        store_release(curr.locked, false)；smp_mb()
        return                                // follower 留作下一任 owner，没有 JIT
    // 本批次已取得一次 source/provider lease，覆盖每个请求及其 ACK/pop
    记录 COMBINER 诊断 this_cpu_inc
    进入 kd_spin_batch_run：编译器管理整批 combiner 的活跃 C 值
    counter = 0
    同一个 C 栈帧内循环 while curr:
        counter++
        next = curr.next                       // NUMA_AWARE=0，直接取后继
        batch.next = next；batch.outer.released = false
        预取 next 的实际寄存器包、frame 热字段和栈内 SP/push 槽
        if 普通单锁准入成功:
            内联 clobber 调用 alternate wrapper；JIT 只执行当前请求
            if 正常最终 unlock:
                按入口 ABI 回写；循环完成/pop 当前 frame
            else:
                完整包回写；execute_cs 消费现有出口，不重跑已执行前缀
        else:
            result = execute_cs(L, curr, batch)  // 原通用处理；第 5 节
        if result == NO_RUN or 未执行正文的 RUN_ERROR:
            next = curr；break                 // 留待原生，不标 completed
        if result != NATIVE_DONE:
            store_release(curr.locked_completed, 1) // 同时 completed=1、locked=0
        // 此后不能再访问已完成 node；它的 waiter 可马上复用 node
        if 复杂嵌套路径已提前释放 outer:
            reclaim_outer(request); source_frame_put(); return
        if next == NULL or next.next == NULL or counter >= 1024: break
        curr = next；继续专用准入，正常连续请求形成 WWJUMP
    批次结束返回，编译器恢复 enclosing C 调用所需状态
    S.locked = LOCKED
    store_release(next.locked, false)          // 留下一个后继负责后续 owner 工作
    source_frame_put()                         // 归还整批租约
    return                                    // 仍持有 Linux L

combiner 自己：恢复原 C 栈 → 原生执行自己的 N 次读改写 → 原生 unlock L
```

`NATIVE_DONE` 由原 waiter 后缀和 owner ACK 路径处理，不再访问/完成旧 node。
本负载正常的 `RUN_TO_UNLOCK` 不走这条分支。
普通入口开始代理需要观察到至少两个 follower：一个待代理，一个后继 owner；
两线程即使发生争抢也未必有可代理批次。之后 follower 可以完成、再次提交，
批次实际长度取决于当时队列，1024 只是上限，不能当作每批大小。

**当前 combiner 对多个 waiter 的 JIT 正文连续执行时一直持有 L。** 每个 waiter
的“逻辑 unlock”不会物理释放 L。`sc_post_work()` 由被唤醒的原 waiter 在
`sc_body_N()` 返回后执行，combiner 的上述循环不会在相邻 JIT 正文间插入它。
因此锁外乘加只间隔各请求线程的再次提交，不保证逐正文发生原锁或 CPU 交接。

<a id="jit"></a>

## 5. 一次实际 JIT：frame → wrapper → 正文 → 完成

### 5.1 锁侧驻留批次与单锁准入

对应 [combiner.inc](../../kernel_module/spin/combiner.inc)、
[kd_jit_batch.h](../../include/kd_jit_batch.h)、[kd_exec.c](../../kernel_module/kd_exec.c)。

```text
run_combiner(L, node, request):
    获得整个批次的 source/provider lease
    保存外层队列与真实 L 的既有所有权
    kd_spin_batch_run(batch):
        编译器序言/尾声管理 combiner 现场
        在同一个 C 帧中循环执行以下请求逻辑
    执行末节点交接，或提前释放后的 outer reclaim
    归还 source/provider lease

kd_spin_batch_run 的循环体:
    若已有 wrapper 返回：
        if 本次入口 ABI 对应的精确最终 unlock 分类通过:
            观察真实正文标记；完成/解绑 frame；发布当前 waiter 完成
        else:
            按分支启用 cold ledger/snapshot
            execute_cs 消费已经返回的出口；不再次执行当前前缀
            使用原有 nested/native/拒绝/outer-release 处理
    检查批次上限、末节点和 outer-release
    保存 NUMA 暂存队列边界；选择下一请求；预取其后继
    if 非普通单锁 root、额外 pinned 或禁用:
        进入 execute_cs 通用处理
    exe = 批内同 entry/SPIN backend 缓存，未命中才查表
    复查 OPEN/NORMAL/entry/backend/code、未执行 root、有效 SP、KDWB001 签名
    frame_bind(node.execution.frame, depth=1, batch_lease=true)
    准备 args[2]、原始 entry SP 和当前 L/unlock 地址
    标记 executed，以对应内联 clobber 边界调用 wrapper，回到本循环
```

正常单锁不再逐请求经过 `execute_cs → kd_exe_on_call_hl_entry`。队列选择、
完成发布和 WWJUMP 都在锁层；wrapper 不持有队列或调度回调，不在生成 JIT 内
切换 waiter。原有 NUMA 拒绝回滚、最后一名 waiter、batch-size 和提前释放规则保留。
旧代码没有 `KDWB001` 签名时走普通 wrapper。

9/17 冻结版本曾在每个请求间返回 C step 和汇编 shell；当前统一循环已消除
这次退出/重入及外层成组保护。新旧混合队列也不会退到普通 C ABI wrapper。
旧入口只额外保护 RBP，两个入口均向编译器声明其他 GPR clobber。编译器仍
可能产生函数级保存及活跃局部值 spill，不能宣称所有现场成本为零。
TCLock 从当前 unlock 续点切到下一 lock 续点；kdlock 保留物理 combiner 栈
供 JIT 暂存槽使用，只更新逻辑 waiter 栈。两者都运行锁侧 C 交接逻辑。
完整状态对照见 [寄存器 ABI](../../docs/JIT_REGISTER_ABI.md#11-与-tclock-spinlock-的执行路径和状态保存对比)。

frame 的常用头部为 72 字节；其后是寄存器包和预分配冷区。普通 prepare/bind/
complete/pop 不初始化、检查八层数组、remote/native 控制或快照。复杂出口先
原地建立单锁 ledger，再调用通用处理；SELFTEST 观察器需要 ledger 时提前启用。
frame/context/request 保持预分配，node 为 64 字节，包含两个排队期间有效的预取地址。
12 个 request 槽独立于四个可复用 node；这是减少热路径访问，不是缩小整个对象。

### 5.2 已执行出口如何进入通用处理

对应 [exe.c](../../kernel_module/exe.c) 和
[observation.patch](provider/observation.patch)。

`kd_exe_spin_batch_resume()` 接收已返回的寄存器包、exit/witness 和原 entry SP。
通用 dispatcher 先消费该出口，再决定处理 CALL/hostcall、续跑或原生后缀。
它不能先调用一次 wrapper；否则会重放已经执行过的前缀。
入口拒绝仍必须同时满足原 entry/SP、零 witness 和专用拒绝标记，才能撤销
`executed` 并走未开始的原生路径。正文运行后的异常不能按原入口重试。

通用入口仍执行原有 frame、backend、scope 和就绪检查。批次入口在执行前用
仅适用于 pristine root 的检查完成准入；不能把一个 continuation 当作新 root。
slot 缓存不保存 readiness 或代码版本，source/provider lease 也不是代码不可变保证。

普通与批次路径都在真实 wrapper 返回后调用同一正文观察点；bench 的
`bench_jit_bodies` 只统计匹配 L 且 witness=1 的逻辑调用，续跑不会重复计数。
`jit_timing=0` 不读时钟；启用时批次路径仍记录 wrapper/dispatch 区间。

### 5.3 wrapper 的两种边界

[wrapper.S](../../include/wrapper.S) 的偏移 0 保留普通 C ABI，偏移 16 是带版本
签名的旧 ABI 专用入口。普通入口保存/恢复原 callee-saved 寄存器；专用入口
只预留同样的栈空间，编译器管理 combiner 活跃值，内联适配保护 RBP。`args[2]` 和控制槽偏移不变。
新增 `Stack_BATCH` 位于 `RBP-160`，保存专用描述指针；先分配栈再写，避免 red zone。

| 出口 | 写回 |
| --- | --- |
| 专用入口，第一次精确到达当前 L 的 spin unlock | RBX/RBP/R12–R15、虚拟 RIP/SP、分类用 RDI、exit/witness |
| hostcall、其他 CALL miss、嵌套/native、错误、入口拒绝 | 完整受支持 GPR、虚拟 RIP/SP、exit/witness |
| 普通入口及续跑 | 完整受支持 GPR、虚拟 RIP/SP、exit/witness |

精简保存集合只应用于已知最终 lock/unlock ABI；中间出口仍保留有效寄存器。
R11–R15、SP/BP 的 `Stack_*` backing 直接使用请求的对应 `pt_regs` 字段，
入口不复制到 wrapper 栈，出口不再复制回来。物理 R11 固定作包基址；原 block
计数改用 `Stack_BUDGET` 内存槽。CPU 中的脏逻辑寄存器仍需 spill/完整物化。
这减少边界搬运，但可能增加循环计数访问和请求包的缓存流量，不能按删除的
指令数直接推算吞吐收益。布局与有效性规则见 [寄存器 ABI](../../docs/JIT_REGISTER_ABI.md#3-pt_regs-输入输出约定)。
生成正文继续按虚拟寄存器和地址重写执行；`bin.txt` 包含 wrapper，不能只数
`JIT.S` 中计数更新的指令来估计执行成本。

### 5.4 完成发布与 request 退休

```text
单锁正常返回：
    检查执行状态、当前锁及完成状态，标记 frame COMPLETE
    frame_pop(frame, NULL)：检查物理 owner/LIFO 和终态，解绑
        不读取未启用的冷状态；不复制寄存器；不归还 waiter 的 request
    per-CPU JIT_SUCCESS 计数
    release-store node.completed/locked           // 发布前结果已就绪
    之后不再访问这个可立即复用的 node
    取得下一请求继续，或结束批次

原 waiter 醒来：
    放弃旧 C 帧，RSP = min(node.rsp, request.regs.sp) 向下对齐
    从 request 读取 origin ticket、IRQ flags 和最终寄存器
    ticket_end：检查代次/owner/native 引用，清活跃位并归还 pin
    直接恢复 request 中的 CPU 寄存器
    在最后一次包读取后归还 request：
        pristine 单锁只有一个用户：release store users=0
        复杂/native/remote：原子递减，保留尚未结束的 owner
    恢复 IRQ flags，返回 unlock 后继，执行自己的锁外计算
```

普通请求的完成不释放物理 L，L 由整个批次持有。原 waiter 不再次执行正文或
物理 unlock。复杂分支继续遵循原 owner/ACK、cleanup、remote 与终态约束。
退出日志 `kd_spin batch: entries=... ww_jumps=...` 按所有 possible CPU 汇总：
`entries` 是专用入口调用数，`ww_jumps` 是上一专用请求正常完成后继续进入下一
专用请求的次数；二者不同于总 JIT 正文数，也不替代负载正确性检查。

### 5.5 combiner 或未代理线程的 slow unlock

对应 `kd_raw_spin_unlock_slow`、`kd_spin_release_origin` 及 gate/entry release。

```text
内核 _raw_spin_unlock → kd_spin_dispatch_unlock：
    fast_unlock 未命中 → target/retained-owner 选择
    kd_raw_spin_unlock_slow(L):
        kd_exec_native_unlock(L, false)        // 本负载 native_frames 为空，立即 false
        if kd_spin_entry_find(L, ref):         // 扫描本 CPU ticket
            kd_spin_unlock_ref(L, ref):
                request = {ref, S=entry_gate(ref).word}
                常见 S.locked=LOCKED：
                    kd_spin_release_origin(request):
                        使用 request.ref 和 S，不再查 map/ticket
                        guard irqsave：OWNED → RELEASING；解开 guard
                        gate_release：检查 owner/task/CPU/generation
                        do_raw_spin_unlock(L)；清 gate.held/owner/hold
                        guard irqsave：RELEASING → RELEASED；解开 guard
                        store_release(S.locked, 0)
                        entry_end：清 ticket；preempt_enable()
            return
        if !kd_hotlock_is_promoted(L): kd_hotlock_record(L)
        origin_raw_spin_unlock(L)
```

物理顺序是先释放 L，再打开 S，再结束 ticket/pin。第 4.3 节提前放行的下一任
owner 仍需等到 S/L 允许获取；不能删掉 S 的等待就让它并行修改正文。

<a id="costs"></a>

## 6. 哪些代码最值得检查

### 6.1 当前源码的重复工作清单

以下按单层、首次 wrapper 即成功到达 outer unlock 的请求计算，是源码执行次数，
不是精确耗时或汇编指令数；拒绝、嵌套、native continuation 的次数不同。

| 工作 | 当前路径与频率 | 应检查的改进方向 |
| --- | --- | --- |
| 重复注册/来源确认 | 每个已晋升慢入口仍调用 `kd_exe_add`；已发布且同身份/后端、source OPEN 时只读返回，新注册及冲突才走原串行化路径，关闭准入仍拒绝 | 已去除命中路径的全局 CAS gate、source irqsave 和模块查询；保留发布、关闭准入和 source 生命周期约束，实际耗时收益尚未测量 |
| 重复 gate map 查询 | 入口查一次 gate；root 先 CAS S，失败后 ticket 复用 gate/pin；pending/tail、execute_cs 和普通 unlock 不再查 map | 已实现 origin release/acquire 发布与无锁读取；创建仍在锁内复查，诊断/无本地 ticket 的 OOO 查询保留；实际耗时收益尚未测量 |
| ticket 查找/状态迁移 | 无 pin 的 native-active 查询不扫描；begin 从空闲位直接分配，只扫描活跃槽检查重复；find 复用已有 pin，entry_gate 无 guard；状态修改仍使用 guard | 已移除临时 pin/unpin 和本地 gate 读取锁，合并重复准入检查；保留代次、owner、ACK 和 pin 的终点 |
| 执行注册表查找 | spin 在同批次同 entry/SPIN backend 上复用 exe 指针；缓存命中的 `find_ready` 和后续 `batch_prepare` 仍各检查一次 readiness，prepare 每次还检查 wrapper 签名；mutex 仍逐请求查表 | 合并重复校验，保留最终准入的 OPEN/NORMAL、身份及代码检查；批次 lease 保证槽存活，不等于 readiness 或代码版本不可变 |
| frame/context 校验 | 普通路径只访问 frame 热状态及寄存器包，不启用冷区；仍逐请求调用完成判定、complete/pop、prepare/bind 和计时辅助函数；完整 context 扫描仅 SELFTEST 保留 | 专门化普通完成与下一请求绑定，减少函数往返和重复检查；保留源租约、owner、容量、ACK 和终态约束 |
| frame 清零/复制 | 无逐请求整块清零；spin 直接使用 waiter 准备的 request/frame，无 node→frame→node 或最终软件快照 | 复杂/native/remote 共用逻辑包，独立 owner 控制状态仍保留，mutex 未改用该池 |
| source frame lease | 每批次一次 CAS 获取、原子递减和 provider module 引用增减；逐 bind 检查 OPEN | 关闭标志和计数在同一原子字中协调退休，仍有共享计数缓存行与模块引用成本，不是零同步 |
| 常规诊断计数 | 纯事件、最大深度及 overflow/invariant 已 per-CPU；每个排队 waiter 仍有共享 `atomic_inc`/`atomic_dec_return`，计数紧邻 JIT 禁用 latch；多个诊断入口重复查槽 | 复用诊断槽，评估实时计数按需观测或其他低开销表示；该计数用于测试/workload 阶段协调，不能直接删除或只在退出后汇总 |
| 下一请求预取 | 当前正文执行前预取下一已发布请求的寄存器包、frame 热字段及逻辑 task 栈内的虚拟 SP/push 槽 | 虚拟子请求跟随共享 root 包；不猜 node-zero RSP，不改变 owner/ACK，不在提前 outer release 后访问旧 successor |
| wrapper 和生成代码 | 同一个 C 帧跨新旧及混合批次；旧入口适配仅保护 RBP；新 ABI 仅捕获/最终恢复三字段；新生成物直接复用请求 GPR backing，旧 ABI 仍装载 CPU 状态及最终恢复 | 编译器仍产生函数级保存和活跃值 spill；JIT 仍有入口分派、地址重写及虚拟栈操作；R11 包基址把 block 计数移至内存；完整中间出口和正文标记保留，历史成绩不能代表此次改动 |
| 屏障、pin 与原锁 | 复杂 dispatcher `mb()`、队列 acquire/release、ticket guard/pin、原 L 获取/释放；普通批次持续持有 L，不逐代理正文重获 | S/L 双层所有权用于兼容原生 peer，不能直接套用 TCLock 单锁字而删除排斥或 owner/ACK 协议 |

普通单锁不读取未启用的冷区，也不进入通用 dispatcher；复杂出口先物化
owner/control 状态再处理。ticket guard、实时 waiter 计数、共享 request 引用和
批次 source 原子操作仍有成本；并发协议与实时观察字段不能当作纯统计删除。

### 6.2 已有采样支持什么结论

已有 R2 四线程 N=1 的 `cycles:k`、499Hz、period 加权 IP 采样中，
`__kd_spin_lock_longjmp` 占 **52.80%**；其中 node.locked/PAUSE 范围占总权重
**46.06%**，S locked/pending 等待范围占 **4.26%**。`kd_spin_gate_lookup` 为
**2.44%**，`kd_exec_frame_validate` 为 **1.92%**；生成映像只有 **0.092%**
（20 个样本）。这些是增加锁外乘加前的历史诊断；测量期 JIT 占比 58.76%，
完整来源和限制见 [历史采样记录](../../docs/VALIDATION.md#spin-static-dispatch-profiling)。

这支持先查请求等待、全局元数据锁和逐请求管理成本。等待样本高表示 CPU 在等待
服务或所有权，并不能单独证明 PAUSE 指令本身是瓶颈；删掉 PAUSE 或加入 yield
不等于缩短 combiner 服务时间。现有 flat IP 采样也不能把所有
`_raw_spin_lock_irqsave` 样本归到某一个内部锁，更不能直接给出锁交接率。

单线程历史 `kd_spin_dispatch_lock` 的 38.59% 包含真正的 locked CMPXCHG，
不能全部称为无效调度代码。优化单线程应重点检查第 3 节及 kernel hook；
第 6.1 节多数 frame/queue 开销只会影响慢入口或真实代理，不能改善已命中的
单线程 native fast 路径。

重复注册、gate 传递、执行条目复用与单锁 frame 精简已实现；开销归因需要对应版本的
独立 [profile.py](profile.py) 核对改变后的开销位置与 JIT 差值。队列等待占比、
实际 batch 大小和服务速度需要一起解释，不能把历史扫描的 best/median 当作
单项修改的收益。

后续 [2026-09-18 三方采样](../tclock_compare/results/20260918-native-stack.md#为什么当前-kdlock-仍慢)
已经覆盖同环境 TCLock、Linux 与 kdlock。新版本的明确热点包括共享诊断槽、
waiter 计数更新及后继请求的依赖读取；不是仍按旧版本的全局锁/整包搬运解释。
生成镜像的采样权重很小，但分母包括所有等待 worker，不能据此直接给出
wrapper 的串行服务成本上限。采样权重不是删除某段代码后可获得的提速比例。

<a id="tclock-cost-comparison"></a>

### 6.3 TCLock 与 kdlock 的实现差异及收益抵消

以下比较独立 [TCLock 后端](../../tclock_backend/README.md)与当前普通
caller-clobber v1。原生互操作、source 生命周期和中途续跑等职责不同，
完整后端的吞吐差距不能全部归因于保存几组寄存器。性能数值、失败记录及
冻结身份只维护在[三方结果页](../tclock_compare/results/20260918-native-stack.md)。

TCLock 与 Linux 可以保留相同调用接口，但不能直接混用同一目标锁的竞争协议：
tail 对应不同的 per-CPU 节点，代理 unlock 也需要自己的续点/完成处理。
[兼容边界](../../tclock_backend/README.md#与-linux-原生-spinlock-的协议兼容边界)
说明为何 kdlock 的 L/S 成本部分用于原生互操作。当前对照分会话加载后端，
不证明 TCLock 能与未修改原生调用者共同竞争目标锁。

| 环节 | TCLock 原生后端 | 当前 kdlock | 成本差别 |
| --- | --- | --- | --- |
| 获取入口 | 目标锁身份判断后直接进入原锁字的 CAS/pending/队列 | 可选原生站点缓存；miss 后目标选择、晋升、条目确认和 gate 查询，先尝试 S，竞争后建立 ticket | kdlock 进入队列前有更多工作；命中注册/已有 gate 并不每次获取全局创建锁 |
| 锁协议 | 被测目标锁完全由 TCLock 协议管理 | 私有调度字 S 加真实 Linux 锁 L | L 用于排斥原生 peer；普通批次持续持有 L，不能按每个代理正文重获 L 计价 |
| 入口现场 | 六个 callee-saved 和 CALL 续点留在原栈，node 记 RSP | 请求仅捕获 RIP/RSP/RBP，其余活跃值由 caller 保存 | 减少显式搬运，但保存责任部分转移到编译器 |
| 连续交接 | unlock 保存原生续点，物理切到下一 waiter 栈；离栈后发布完成 | wrapper 返回、完成分类、普通 root 合并终态验证/解绑、发布、下一请求 prepare/bind | 同一个 C 循环已去除旧 callback shell，逐请求管理仍存在 |
| 状态访问 | node、原生栈及 per-CPU combiner 状态 | node → execution，内嵌 frame/regs 或借用 regs_ref，加 ticket、翻译条目等 | 热元数据集中到请求前两条缓存行；frame/regs 内嵌不是额外指针跳转，仍有真实间接读取 |
| 诊断 | 三个直接 per-CPU 计数 | 事件 per-CPU，批次/请求复用 slot，waiter_count 独立缓存行 | 重复查找和读写混用已减少；共享原子计数成本仍在 |
| 正文 | 原生指令 | wrapper、虚拟寄存器/地址重写与出口判定 | 本负载的自增不因 JIT 减少业务读写；两者都能从批次中的数据局部性获益 |
| 批次结束 | 队列/IRQ 条件、上限 1024、need_resched | 队列、上限 1024、准入/执行结果等；普通循环没有相同的 need_resched 条件 | 相同 batch 上限不等于相同实际批长、覆盖率或调度行为 |

四处需要特别区分“删除了重复工作”与“总成本消失”：

1. **手写保存减少，函数级保存仍在。** 冻结的 `sc_body_1/16` 反汇编显示，
   caller-clobber 使函数保存/恢复 RBX、R12–R15，即使正文没有跨边界活跃局部值，
   也须履行函数对外的普通 C ABI。combiner 的活跃 C 值同样要跨 wrapper 保存。
   同一 ABI 的 TCLock arm 也承担 caller 这部分成本。长批次原生 ABI 差值包含
   桥接和代码布局，不能全部记作 spill，也不能仅凭 push/pop 数量预测吞吐。
2. **事件计数本地化，共享行仍可能迁移。** [slot](../../kernel_module/spin/state.inc)
   此前将 addr、waiter_count 和 jit_disabled 放在同一 16B 对象。当前 slot
   扩为对齐的 128B，计数单独占一行；batch 解析一次身份，waiter 退出复用
   入队记录。禁用状态仍逐次 acquire 读取，计数仍实时原子更新。
   [递进对照](results/20260918-state-access.md)区分引用复用与缓存行分离；
   两者都没有删除全局计数本身的写入成本。
3. **批次摊销所有权成本，逐请求成本不随批长消失。**
   [lookup](../../kernel_module/spin/combiner.inc) 仅解析身份，普通 root 在
   [batch_prepare](../../kernel_module/exe.c) 集中检查 readiness、ABI、镜像标识
   和 frame；复杂路径保留原检查。source lease 按批次持有，不能据此认定可变状态或
   代码版本不可变。高 JIT 比例只证明代理覆盖，不能证明单次服务便宜。
4. **预取地址准备也有成本。** TCLock 主要预取下一 waiter 的原生栈；历史采样
   中 kdlock 先读 execution、regs_ref、task 与 SP，再触发预取。当前
   [预取路径](../../kernel_module/spin/prefetch.inc)默认把地址准备移到发布前：
   combiner 只从 node 取得实际包指针、受检 SP 和 full/complex 标记，先预热
   request 的两条热元数据行，再预热寄存器和栈。普通请求直接提供内嵌包，虚拟请求沿用共享父包。
   装载参数 `spin_prefetch=0/1/2` 支持关闭、旧查询、生产者提示；只控制后继
   请求预取。准备工作和新增字段仍有成本，不能用 combiner 读取减少代替总吞吐。
   [四路对照](results/20260918-prefetch.md)已完成：20 线程相对旧版本提高约
   7.3%/9.3%，JIT 均约 99.8%；4 线程基本持平，不能推为普遍收益。

本轮的[入口/缓存独立对照](results/20260918-spin-entry.md)进一步验证了另一种
抵消：把 S/L 释放直接内联进公共解锁，会使缓存命中路径也保存 RBX/R12。
现将该调用移到独立函数，保留 owner 校验与释放顺序；guest 汇编确认这组
额外函数级保存已消失。获取入口另将注册/调度移入冷函数，并用标准 `bint`
保存装载开关，避免 UBSAN bool 读取冷调用迫使命中路径提前保存参数；内核
检查配置未关闭。省下 ticket 准备不保证完整操作自动提速。

### 6.4 当前落地与后续测量

诊断 slot 引用复用、计数行分离、请求热字段布局及普通 root 准入/完成处理已实现。
frame、寄存器包和可变分类仍各保留一份权威状态；672 字节 frame 未缩小，
request 由本轮实际基线的 720 字节增至按行对齐的 768 字节。增加少量预分配空间
用于减少分散访问及相邻 request 共行，不能解释为内存占用下降。
十项基础/受影响 unit 和六项 live 验证见[测试记录](../../tests/README.md#spin-state-access)，
五个递进版本的性能证据统一见[状态访问对照](results/20260918-state-access.md)。

随后 [9/19 当前版本三方复测](../tclock_compare/results/20260919-state-access.md)
重新测量 Linux、TCLock 与 kdlock：90 场对照和 30 场长批次全部正确排空。
20 线程的 kdlock 超过 TCLock，4 线程仍落后；TCLock 的实际委托比例波动明显。
这是完整后端比较，不能将全部差距归因于现场保存或单个状态访问机制。

后续仍可测实际批长、等待权重、共享 waiter_count 更新，以及 wrapper/正文重写
成本。诊断表未覆盖的复杂入口仍会按锁地址查询；ticket、source、native/remote
ACK 的生命周期不同，不能因 node 可复用就删掉它们。性能判断继续同时报告
完整操作吞吐和实际 JIT 比例。

并发冷晋升停滞仍是独立未修复问题，稳态单 CPU 准备不关闭该缺口。
现有性能矩阵也不验证任意嵌套或 task/per-CPU 正文。
