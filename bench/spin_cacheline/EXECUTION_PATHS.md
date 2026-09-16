# spin_cacheline：首次执行、代理 JIT 与开销路径

本文从 `SC_RUN` 展开到原 waiter 恢复，供对照源码和汇编查找性能问题。
描述的是当前实现，不是优化后的设计；本次只整理文档，没有重跑或修改性能代码。
负载、测量口径和操作入口见 [README](README.md#临界区与测试伪代码)。

阅读条件：x86_64，普通任务上下文，单层 `sc_body_N`，同一把 spinlock，
`KDLOCK_SELFTEST=0 KDLOCK_NUMA=0`，`bench_quiet=1 jit_timing=0`。
内核入口按最近运行的 `6.1.159-kdstatic2` 合并 static-call 接口展开；旧接口的差异
在第 2 节注明。伪代码合并错误处理，但保留影响主路径成本的查表、原子操作、
复制、校验和等待；辅助函数名不等于最终机器码一定存在一次 CALL，须对照反汇编。

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
3. [已发布的原生快路径](#native-fast)：单线程 NO_JIT 通常走这里。
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
    result = kd_spin_fast_acquire(L, RIP)       // 首次该 CPU 的缓存尚未建立
    if result == OWNED: return                 // 第 3 节
    if result == MISS_PINNED: preempt_enable() // 归还失败尝试的 CPU pin
    selected = (source.OPEN and comm 两个机器字掩码匹配 sc_worker)
               or 当前任务仍有未结束的原生 fast/ticket
    if !selected: origin_raw_spin_lock(L); return
    kd_raw_spin_lock_slow(L, saved_RSP, RIP)
```

R2 在快路径失败时才做 target/retained-owner 选择。旧指针 hook 接口先调用独立
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
    kd_spin_fast_remember(L, RIP)               // NORMAL 且已有 gate 才能填缓存
    kd_spin_lock(L, saved_RSP)                  // 第 4 节；仍不保证 JIT

kd_hotlock_is_promoted(L):
    raw_spin_lock_irqsave(global_hotlock_table_lock)
    对 L 做哈希/线性探测；读取是否 DELEGATE
    raw_spin_unlock_irqrestore(...)

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
`kd_spin_entry_native_active()` 还包含 per-CPU 32 个 ticket 的扫描；其在本路径和
下文 `kd_spin_lock()` 的检查均保留，并非仅初始化时执行。

### 2.3 注册不是编译；已有条目也经过全局锁

对应 [registry_publish.inc](../../kernel_module/execution/registry_publish.inc)、
[registry_lifecycle.inc](../../kernel_module/execution/registry_lifecycle.inc)、
[exe.c](../../kernel_module/exe.c)、[kd_source.c](../../kernel_module/kd_source.c)。

```text
kd_exe_add(0, RIP, SPIN):
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

kd_spin_fast_remember(L, RIP):
    检查普通可抢占上下文
    再 kd_get_exe(0, RIP)；检查身份、SPIN、NORMAL、source.OPEN
    gate = kd_spin_gate_find(L)                 // 全局 map irqsave 查找
    if gate 存在:
        preempt_disable()
        更新 per_cpu.fast 的 origin=L、rip=RIP、gate 字段
        preempt_enable()
```

条目尚未 NORMAL 或 gate 尚未创建时不填缓存；后续慢入口再尝试。
`vmalloc/set_memory_x` 在 provider 初始化时预分配代码池，不在每次抢锁内分配。
但 `kd_exe_add` 的全局 gate、source 地址检查及查表在**每次已晋升的慢入口**重复，
不是仅首次执行；这是应优先检查的固定成本。

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

## 3. 已发布但不代理：单线程常见路径

对应 [kd_spin_fast.h](../../include/kd_spin_fast.h)。

```text
kd_spin_fast_acquire(L, RIP):
    if preempt_count != 0 or IRQ disabled or migration disabled: return CONTEXT
    preempt_disable()
    fast = 当前 CPU 的缓存
    if fast.origin == L and fast.rip == RIP
       and atomic_read(fast.gate.S) == 0 and source.OPEN:
        spin_acquire(lockdep)                  // 是否生成实质代码取决于内核配置
        if do_raw_spin_trylock(L):             // 真正的 Linux 原锁原子获取
            fast.owner = current; WRITE_ONCE(fast.held, L)
            return OWNED                      // pin 一直持有到 unlock
        spin_release(lockdep)
    return MISS_PINNED

sc_body_N 原生展开正文

kd_spin_dispatch_unlock(L):
    if 普通任务且有 preemption pin
       and fast.held == L and fast.owner == current:
        spin_release(lockdep)
        do_raw_spin_unlock(L)
        WRITE_ONCE(fast.held, NULL); fast.owner = NULL
        preempt_enable()
        return
    进入第 5.5 节的 slow unlock
```

命中后没有热锁表、注册 gate、ticket、node、frame、wrapper 和 JIT 正文计数。
仍有 hook 栈布局、static-call、上下文/缓存/S/来源状态判断、per-CPU 记录及原锁操作。
测量刚开始时若某 CPU 缓存尚未建立，仍需先走慢入口；“单线程 NO_JIT”不等于
每一次获取都命中快路径。S 非零时优先进入现有排队协议；S 为零也只是提示，
原生 fast 与 combiner 最终都必须获取 L。

<a id="queue"></a>

## 4. 快路径失败后的竞争、原锁所有权和队列

### 4.1 准入与 S 的获取

对应 [kd_spinlock.c](../../kernel_module/kd_spinlock.c)、
[kd_spin_entry.c](../../kernel_module/kd_spin_entry.c)、
[kd_spin_gate.c](../../kernel_module/kd_spin_gate.c)、
[state.inc](../../kernel_module/spin/state.inc) 和 [queue.inc](../../kernel_module/spin/queue.inc)。

```text
kd_spin_lock(L, saved_RSP):
    检查 task/IRQ/softirq/migration/native-active；不适用则走原生 L
    kd_spin_entry_begin(L, HOOK):
        preempt_disable()
        扫描当前 CPU 的 32 个 ticket：找空槽、拒绝同任务重复获取 L
        gate = kd_spin_gate_get(L)              // 全局 map irqsave 查找/首次创建
        raw_spin_lock_irqsave(ticket.guard)
        写 task/L/gate/sequence/cpu/state=WAITING，清 hold/native_refs
        raw_spin_unlock_irqrestore(...)
    检查本 CPU 无当前 JIT frame/其他任务占用的执行上下文；否则结束 ticket 再原生
    S = kd_spin_word(L)                         // 再次全局 map irqsave 查找
    old = cmpxchg_acquire(S, 0, LOCKED)
    if old == 0: goto acquired
    if old 只有 PENDING: 有界轮询 S
    if old 含 tail/pending 等非 locked 位: goto queue
    old = fetch_or_acquire(S, PENDING)          // helper 内再次 kd_spin_word(L)
    if old 出现其他等待者:
        必要时清本次设置的 pending 位；goto queue
    等待原 locked 清除；clear_pending_set_locked(L)
    goto acquired
queue:
    kd_spin_lock_slowpath(L, saved_RSP)         // 见 4.2；代理完成者不从这里普通返回
acquired:
    kd_spin_claim_origin(L)
    return                                    // 自己执行原生 sc_body_N 正文

kd_spin_claim_origin(L):
    kd_spin_entry_find(L)                      // 本 CPU ticket 扫描、临时 preempt pin
    guard irqsave：检查 ticket 代次/任务/CPU/状态
    if 已 OWNED: 解开 guard，直接成功           // queue 已 claim 时仍重复做这次检查
    WAITING → CLAIMING；解开 guard
    cmpxchg(gate.owner, NULL, current)
    kd_preempt_disable_raw_spin_lock(L)        // 真正获取 Linux L；不再增加一次 pin
    增加 gate.generation；写 held/owner_cpu/hold
    guard irqsave：CLAIMING → OWNED；解开 guard
```

只有 S 成功还不能访问负载。`kd_spin_gate_claim` 必须取得 L，以排斥没有使用 S
的原生线程。map 查找即使 `create=false` 也拿同一把全局 irqsave 锁；ticket 的
guard 则是每个 ticket 独立的锁，二者不能混为同一个全局瓶颈。

### 4.2 发布请求、等待和恢复入口

对应 [slowpath.inc](../../kernel_module/spin/slowpath.inc) 与 `kd_spin_lock_slowpath`。

```text
kd_spin_lock_slowpath(L, saved_RSP):
    保存调用者 C 栈 RSP、原 hook 寄存器栈 RSP
    切换到当前 CPU 的 8KB shadow C 栈
    记录 SLOWPATH 诊断：查找诊断槽 + atomic64_inc(event)
    idx = per_cpu.node_count++                 // 每 CPU 最多 4 个 node
    若耗尽：还原 count；轮询 trylock(S) 后返回 acquired（本负载不嵌套）
    初始化 node 的 locked/completed/next/tail、CPU/NUMA、RSP、L、current、GS base
    清 exec_frame/jit_waiter/jit_retry/native_resume/native_regs_decoded/jit_context
    记录 pinned_context；kd_spin_entry_find(L) 保存 origin ticket 引用
    __kd_spin_lock_longjmp(L, node):
        S = kd_spin_word(L)
        node.queued_at = timing_start()        // jit_timing=0 时返回 0，不读时钟
        old_tail = xchg_tail(L, node.tail)     // helper 也查 gate，再原子交换 S.tail
        诊断槽 atomic_inc(waiter_count)
        if old_tail 有前驱:
            previous = decode_tail(old_tail)  // CPU/index → 对应 per-CPU node
            previous.next = node              // 链接完成后前驱可观察此请求
            while load_acquire(node.locked):
                if node.jit_waiter: remote_poll // 普通 bench waiter 此条件为 false
                cpu_relax()                   // x86 PAUSE，保留 CPU 执行上下文
            smp_rmb()
            if node.native_resume: 转原 waiter native 后缀路径（非本负载正常路径）
            if node.completed:                // 别的 CPU 已执行完本请求
                扫描 shadow 锁栈，检查嵌套/OOO 返回分支
                node_count--；prefetchw 原栈的 6 条 cacheline
                诊断槽 atomic_dec_return(waiter_count)
                保存 resume_node；返回“代理完成” → 第 5.4 节
        等待 acquire(S.locked | S.pending) == 0 // 到队首后仍可能等待
        if 自己是唯一队尾 and CAS(S, tail, LOCKED) 成功:
            claim_origin(L)；结束 queue timing；node_count--；退出 waiter 诊断
            恢复原 C 栈，返回 acquired
        设置 S.locked=COMBINER；claim_origin(L)
        结束本队首的 queue timing
        while node.next == NULL: cpu_relax()
        检查 shadow 锁栈容量；保存 combiner 状态、RSP
        node_count--；临时置自己 node.rsp=0；将 L 压入 shadow 锁栈并校验
        run_combiner(L, node.next)             // 服务跟在自己后面的请求
        弹出 L、校验并恢复 shadow 状态/RSP；还原 S 的持锁状态
        退出 waiter 诊断；恢复原 C 栈，返回 acquired
```

源码宏 `smp_cond_load_relaxed_sched` 名字带 `sched`，但这里的定义只有
`READ_ONCE` 和 `cpu_relax()`，没有主动调度。`preempt_enable()` 在释放对应 pin
时仍可能允许调度，不能据此宣称完全不会被切走。
上面展开正常获取与代理完成。桥接函数还识别：未执行正文的 `jit_retry` 返回 4，
在已取得 L 后恢复到保存的正文入口；`native_resume` 返回 5，转原 waiter 后缀及
owner ACK 协议。它们与完成返回 1/3、普通获取返回 0/2 不能混用。

### 4.3 combiner 的批次不是每个 waiter 一次物理解锁

对应 [combiner.inc](../../kernel_module/spin/combiner.inc)。

```text
run_combiner(L, first_follower):                // 进入时 combiner 已持有 L
    curr = first_follower; next = curr.next
    if next == NULL or curr/next 是 IRQ 特殊节点:
        S.locked = LOCKED
        store_release(curr.locked, false)；smp_mb()
        return                                // follower 留作下一任 owner，没有 JIT
    记录 COMBINER 诊断 atomic64_inc
    counter = 0
    while curr:
        counter++
        next = curr.next                       // NUMA_AWARE=0，直接取后继
        batch.next = next；batch.outer.released = false
        result = execute_cs(L, curr, batch)    // 第 5 节
        if result == NO_RUN or 未执行正文的 RUN_ERROR:
            next = curr；break                 // 留待原生，不标 completed
        if result != NATIVE_DONE:
            store_release(curr.locked_completed, 1) // 同时 completed=1、locked=0
        // 此后不能再访问已完成 node；它的 waiter 可马上复用 node
        if 复杂嵌套路径已提前释放 outer: reclaim_outer(L); return
        if next == NULL or next.next == NULL or counter >= 1024: break
        curr = next
    S.locked = LOCKED
    store_release(next.locked, false)          // 留下一个后继负责后续 owner 工作
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

### 5.1 execute_cs 的准备

对应 [combiner.inc](../../kernel_module/spin/combiner.inc)、
[kd_exec.c](../../kernel_module/kd_exec.c)、
[lock_ledger.inc](../../kernel_module/execution/lock_ledger.inc) 和
[shadow.inc](../../kernel_module/spin/shadow.inc)。

```text
execute_cs(L, node, batch):
    S = kd_spin_word(L)                         // 全局 map irqsave 查找
    per_cpu.shadow.curr_cs_cpu = node.cpuid
    检查 node 非额外 pinned 的普通 waiter
    查诊断槽的 jit_disabled latch；禁用则 NO_RUN
    if !node.native_regs_decoded:
        从 waiter 原 hook 栈取 r15/r14/r13/r12/rbx/rbp/RIP
        node.regs.sp = saved_hook_RSP + 64
        node.native_regs_decoded = true        // 预执行拒绝后不可重复消费同一栈包
    if !kd_exe_is_ready(0, node.regs.ip):
        记录 NOT_READY 原子诊断；kd_exe_add(...); return NO_RUN

    frame = kd_exec_frame_push(node.regs, RIP, L, node, shadow, depth, GS, task):
        检查 CPU context owner/depth；validate_context 扫描 8 个 frame 槽
        kd_source_frame_get():
            global_source_lock irqsave；检查 OPEN/frames 上限
            try_module_get(provider)；frames++；unlock_irqrestore
        memset(frame, 0, sizeof(frame))
        frame.regs = node.regs                 // 整个 pt_regs 复制
        设置 entry/L/GS/logical_task/parent/depth/state=RUNNING 等字段
        初始化 native_link；context.depth++；再次 validate_context
    node.exec_frame = frame；frame.spin_origin = node.spin_origin
    kd_exec_frame_set_lock_stack(frame, shadow.lock_addr, depth=1):
        检查输入锁、重复项、outer 的位置
        清空 4 个完整锁向量数组，各容量 8；填入 L；validate_frame
    capture_combiner_state：复制 8 项锁地址及 CPU/栈/IRQ 等状态
    frame.outer_unlock_hook = batch.outer
    queue_end = timing_start()                 // 关闭时不读时钟
    result = kd_exe_on_call_hl_entry(frame.regs, RIP, L)
    if frame.executed: queue_timing_end(...)   // 关闭时直接返回
    完成处理见 5.4
```

每个被代理请求都有自己的 frame push/pop，并不是整个批次只创建一次。
frame 来自固定 per-CPU 数组，仍会逐请求清零、复制和校验；“没有动态分配”
不意味着这些内存操作免费。`kd_source_frame_get/put` 还逐请求更新全局生命周期状态。

### 5.2 C dispatcher 的常见一次 wrapper 路径

对应 [exe.c](../../kernel_module/exe.c)、
[control_calls.inc](../../kernel_module/execution/control_calls.inc)、
[timing.inc](../../kernel_module/execution/timing.inc)、
[observation.patch](provider/observation.patch) 和 [kd_bench.h](provider/kd_bench.h)。

```text
kd_exe_on_call_hl_entry(regs, RIP, L):
    frame = kd_exec_current_frame()
    validate_frame；检查 GS/logical_task
    exe = kd_get_exe(0, RIP)
    kd_exe_is_ready(0, RIP)                     // 内部再次 kd_get_exe
    检查 SPIN 类型、RUNNING/未执行/未 outer unlock、原始入口和栈有效
    dispatch_start = timing_start()
    body_reported = false
    args[2] = {frame.gsbase, frame.logical_task}
    frame.executed = true                     // 保守标记，不等同于正文证据
    boundary_start = timing_start()
    exe.code_block(regs, args)                 // 间接调用生成的 wrapper；见 5.3
    timing_end(WRAPPER, boundary_start)
    检查 ENTRY_REFUSED 等返回分类
    if !body_reported and args[1] == 1:
        if bench_lock_addr != 0 and L == bench_lock_addr:
            this_cpu_inc(bench_bodies)         // wrapper 返回后，按逻辑调用计一次
        if !bench_quiet: 打印正文日志
        body_reported = true

    // 当前 sc_body_N 正常返回 args[0]=CALL_MISS
    if regs.ip == 原 _raw_spin_unlock 地址 and regs.di == L:
        timing_start()
        handle_known_call：
            清 control_call.phase；检查无混合 spin/mutex 后端
            判断为 outer unlock 且没有未释放的 nested lock
            return KNOWN_OUTER_UNLOCK         // 不调用 Linux unlock，不再次进入 wrapper
        timing_end(CONTROL)
        result = RUN_TO_UNLOCK
    mb()                                      // dispatcher 退出公共全屏障
    timing_end(DISPATCH, dispatch_start)
    return result
```

这段对应无 nested lock/hostcall 的一次正常返回。通用 dispatcher 还处理已知 nested
CALL、hostcall、多次 continuation、native suffix 和异常；这些分支的判定仍可能
经过，但服务本身不在本负载执行。`jit_timing=0` 不调用 `ktime_get_ns()`，仍有
开关判断和部分跨文件 helper 调用；quiet 也不关闭 frame/ticket/诊断检查。

### 5.3 wrapper 和生成正文：真正的计数更新只占一小段

对应 [wrapper.S](../../include/wrapper.S)。输入仍是两个元素的 args 数组，输出复用为
`{exit_kind, body_witness}`。CPU 的真实 RSP 属于 combiner；R13/R12 表示 waiter
的虚拟 SP/BP，不能把它理解为 CPU 切换到 waiter task。

```text
wrapper(regs, args):
    ENDBR64；保存 combiner 的 rbp/rbx/r12/r13/r14/r15
    将 regs/args 指针保存到真实栈
    从 pt_regs 加载 rbx/r11/r10/r9/r8/rax/rcx/rdx/rsi/rdi
    将虚拟 rbp/rsp/r15/r14/r13/r12/r11、GS/task 压入 wrapper spill 区
    预留 RIP/退出原因/正文标记槽；body_witness = 0
    R13 = virtual_SP；R12 = virtual_BP
    执行生成的 jit.S
exit:
    保存虚拟 IP/SP/BP
    写回 args 的退出原因和正文标记
    将 spill 区与工作寄存器写回 pt_regs
    丢弃临时槽；恢复 combiner 的 callee-saved 寄存器；RET 到 C dispatcher
```

下面是当前 N=1 生成物的等价伪汇编，具体地址用名称替换；N=2/4/8/16 增加
展开的读改写。没有把多次实际访存简写成“调用 JIT”：

```text
R11 = 0；R14 = PT_RIP
比较 R14 与已知入口/后继；跳转对应 label；未知入口返回 IJ_MISS
entry_after_spin_lock:
    Stack_JIT_WITNESS = 1
    R15 = 原 load 指令的 next_RIP              // MOVABS，用于重写 RIP-relative
    RAX = *(R15 + 原位移)                      // load slot[0].value
    RDI = L 的绝对地址
    RAX += 1
    R15 = 原 store 指令的 next_RIP             // 再一个 MOVABS
    *(R15 + 原位移) = RAX                      // store slot[0].value
    R15 = 原 unlock 调用后的地址
    R13 -= 8；*(u64 *)R13 = R15                // 在 waiter 虚拟栈模拟 CALL 返回地址
    jump translated_unlock_stub
translated_unlock_stub:
    R14 = 原 _raw_spin_unlock 地址
    Stack_IJ = CALL_MISS
    Stack_RSP = R13
    jump wrapper.exit
```

原正文可以直接用 RIP-relative load/store；JIT 重定位后这里增加 MOVABS、虚拟
CALL 栈写入和退出分派。具体三份代码见 [汇编查看目录](README.md#assembly-inspection)：
`native.S` 是原始 `sc_body_N`，`JIT.S` 是生成正文，**`bin.txt` 是包含 wrapper 的
JIT 机器码反汇编**。只数 `JIT.S` 的计数更新会漏掉 wrapper 和所有 C 管理成本。

### 5.4 完成一个 waiter：先退休 frame，再发布完成

对应 `execute_cs` 后半段、[kd_exec.c](../../kernel_module/kd_exec.c)、
[spin_calls.inc](../../kernel_module/lock/spin_calls.inc)、
[remote.inc](../../kernel_module/execution/remote.inc) 和 `kd_spin_resume_waiter`。

```text
execute_cs 收到 RUN_TO_UNLOCK：
    record_event(OUTER_UNLOCK):
        validate_frame；检查 L/状态/regs.di
        outer_unlock_seen = true
        lock_mark_released(L)：再次 validate_frame；查向量，标记逻辑释放
        没有 nested/remote 依赖 → 不执行 batch.outer.release，不释放物理 L
    kd_spin_jit_nested_cleanup(frame):
        检查 can_complete：逻辑锁已释放且无 remote pending
        当前 depth=1，没有 nested 项需要实际清理
    combiner_state_matches：检查深度/CPU/栈/IRQ，比较 8 项锁地址
    frame_complete：validate_frame；can_complete；completion_seen=true
                    发布 COMPLETE；再次 validate_frame
    node.regs = frame.regs                     // 一次完整复制
    node.jit_retry = false；node.exec_frame = NULL
    remote_complete(frame)：无 parent，立即返回
    frame_pop(frame, &node.regs):
        检查当前 owner、LIFO、terminal 状态、remote/native 请求与链表
        validate_context
        node.regs = frame.regs                 // 当前源码在 pop 中又复制一次
        context.depth--；memset(frame, 0, sizeof(frame))；清 context.owner
        source_frame_put：全局 source irqsave 下 frames--；module_put(provider)
        再次 validate_context
    查诊断槽；atomic64_inc(JIT_SUCCESS)，检查 max_depth
    if !bench_quiet: 打印成功日志
    返回 run_combiner；由它 release-store node.completed/locked

原 waiter 在第 4.2 节的等待循环醒来：
    消费 completed 和最终 regs；node_count--；prefetch；退出 waiter 诊断
    将真实 RSP 切回 min(node.rsp, node.regs.sp) 下方的原任务栈空间
    kd_spin_resume_waiter(0):
        在原栈复制 node.regs、origin ref 到局部变量
        kd_spin_entry_end(ref):
            ticket.guard irqsave；核对代次/任务/CPU、无 hold/native_refs
            清 ticket 成员；state=FREE；清 ref；unlock_irqrestore
            preempt_enable()                  // 之后不再读可复用的 per-CPU node/ticket
        jump_to_saved_regs：恢复 GPR 和虚拟 SP，RET 消费模拟 CALL 的返回地址
    从原 sc_body_N 的 unlock 后继继续，函数返回
    执行自己的 sc_post_work；completed++；提交下一次 lock
```

已代理的 waiter 不重新执行原正文，也不调用一次物理 `spin_unlock(L)`；其工作
已经在 combiner CPU 完成。异常只在确认未执行正文时允许回退；正文已执行但
没有可继续的出口时 fail-stop，不能把“少一次检查”优化成重复计数更新。

### 5.5 combiner 或未代理线程的 slow unlock

对应 `kd_raw_spin_unlock_slow`、`kd_spin_release_origin` 及 gate/entry release。

```text
内核 _raw_spin_unlock → kd_spin_dispatch_unlock：
    fast_unlock 未命中 → target/retained-owner 选择
    kd_raw_spin_unlock_slow(L):
        kd_exec_native_unlock(L, false)        // 本负载 native_frames 为空，立即 false
        if kd_spin_entry_find(L):              // 扫描本 CPU ticket
            kd_spin_unlock(L):
                S = kd_spin_word(L)           // 全局 map irqsave 查找
                常见 S.locked=LOCKED：
                    kd_spin_release_origin(L):
                        再 kd_spin_word(L)；再 kd_spin_entry_find(L)
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
| 重复注册/来源确认 | 每个已晋升慢入口都 `kd_exe_add`：全局 CAS gate → source irqsave → 模块查询 → registry；已有 NORMAL 也如此 | 检查能否为已注册且仍有效的条目提供读取路径，保留关闭准入和 source 生命周期约束 |
| 重复 gate map 查询 | `remember/begin/kd_spin_word`，以及 pending/tail/claim 邻近 helper、`execute_cs`、unlock 多次查询；只读 find 也拿全局 irqsave 锁 | 将已有稳定 gate/S 沿一次请求传递，避免同一 L 的重复查找；不能只把读者锁删除而不处理发布可见性 |
| ticket 查找/状态迁移 | native-active 检查、32 槽准入扫描、多次 find；claim/release/end 的独立 guard 操作 | 复用已验证 ref、减少同一次调用中重复扫描；保留代次、owner、ACK 和 pin 的终点 |
| 执行注册表查找 | 每次成功 `execute_cs` 中 ready 查一次；dispatcher 的 get + ready 又查两次，共 3 次 `kd_get_exe`，不含请求入口 | 传递已校验的 exe，核对发布/退休同步后再决定哪些检查可合并 |
| frame/context 校验 | 常见成功路径 8 次完整 `validate_frame`；push/pop 合计 4 次 `validate_context`，每次遍历 8 个 frame 槽 | 区分状态转换必须验证的字段与同一阶段重复验证；不能据低耗时猜测移除正确性条件 |
| frame 清零/复制 | 每次 push/pop 各清零整个 frame；设置锁栈再清 4 个容量 8 的数组；node→frame 复制一次，frame→node 在完成处及 pop 各一次 | 优先核查重复复制、重复清零；若使用单层专用路径，必须保持初始化/未使用项不变量 |
| source frame lease | 每代理一次，get/put 各一次全局 source irqsave；provider module 引用增减 | 评估按仍存活的 batch 保留 lease 的可能性及退休语义；不可凭没有 translator 就取消 frame 生命周期保护 |
| 常规诊断计数 | SLOWPATH、COMBINER、JIT_SUCCESS、waiter_count 在同锁共享诊断槽上做全局原子 RMW；quiet 不关闭 | 区分统计量与协议状态；可评估纯统计转 per-CPU，不能删除拒绝 latch 或排空检查 |
| wrapper 和生成代码 | 每次 JIT 保存/恢复寄存器、spill、写虚拟 CALL 栈、间接调用和返回；正文存在地址重写指令 | 依据已证明的寄存器活跃性/出口契约减少搬运；保持两元素 ABI 和实际正文标记 |
| 屏障、pin 与原锁 | dispatcher `mb()`、队列 acquire/release、ticket pin、原 L 原子获取/释放 | 按具体先后关系证明是否冗余；不能将真实排斥和完成发布删掉作为提速 |

8 次 `validate_frame` 的来源：push 后 context 校验 1 次、设置锁栈 1 次、dispatcher
入口 1 次、outer event 与 lock-mark 各 1 次、complete 前后各 1 次、pop 前 context
校验 1 次。它每次检查全部 8 个锁槽，包括应为空的尾部，不是只检查实际的一个 L。
`context` 在空栈时不调用 frame 校验，但仍遍历 8 个槽的 UNUSED 状态。

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

建议先检查重复注册、gate 传递和 frame 重复搬运，再用相同源码/内核/参数的
独立 [profile.py](profile.py) 核对改变后的开销位置与 JIT 差值。队列等待占比、
实际 batch 大小和服务速度需要一起解释；本文没有新采样，以上候选项没有给出
未经测量的提速比例，也不能把最近扫描的 best/median 当作这些修改的收益。
