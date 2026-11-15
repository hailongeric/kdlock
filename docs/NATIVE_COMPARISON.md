# kdlock against the native Linux locks, path by path

What each side actually executes for one contended acquisition, with the
register and cache-line accounting. The native side is Linux 7.0.0-38 as built
in the development VM (`kernel/locking/{qspinlock.c,qrwlock.c,mutex.c,rwsem.c}`,
`arch/x86/entry/entry_64.S`); the kdlock side is `kernel/kd_entry.S`,
`kernel/kd_core.c` and the four family files. Mechanism background:
[ARCHITECTURE.md](ARCHITECTURE.md); per-family protocol: [LOCKS.md](LOCKS.md).

Terms: **origin** W is the task whose critical section is delegated,
**executor** C the CPU that runs it, **packet** (`struct kd_regs`) the
continuation of an origin, **session** one combiner's run over the queue.

## 1. The one structural difference

Both sides have the same fast path and, under contention, the same idea of a
queue. They differ in **what travels** when a waiter cannot have the lock:

| | native | kdlock |
| --- | --- | --- |
| What moves to the lock holder's CPU | the lock's data, one cache line at a time, pulled by each waiter in turn | one continuation per waiter; the lock's data stays in the combiner's cache |
| What the waiter publishes | nothing; its state stays in its own registers and stack frame | 10 words: 6 callee-saved registers, `rax`, `rsp`, `rip`, `rflags` |
| Who executes the critical section | its own task, always | the combiner, from a relocated copy of the code, unless anything in it cannot be executed there |
| Cost per critical section under contention | the protected data crosses to the next waiter | the section's code is already hot on the combiner; the continuation and the node cross instead |

Everything below is the consequence of that one row.

## 2. Object and per-waiter storage

| | native | kdlock |
| --- | --- | --- |
| spinlock | `struct qspinlock`, 4 bytes: locked byte, pending byte, 16-bit MCS tail | `struct kd_spinlock`, 4 bytes: the same word; the holder-owned bit `KD_Q_DELEG` lives in the locked byte |
| rwlock | `struct qrwlock`, 8 bytes: `cnts` + `wait_lock` (a nested qspinlock) | `struct kd_rwlock`, 8 bytes: `cnts` + queue word `wait` |
| mutex | `struct mutex`, 32 bytes: `owner` (the lock itself), `wait_lock`, `wait_list`, OSQ pointer | `struct kd_mutex`, 32 bytes: queue word (locked byte + flags), `wait_lock`, `owner`, `waiters` |
| rwsem | `struct rw_semaphore`, 40 bytes: `count`, `owner`, OSQ pointer, `wait_lock`, `wait_list` | `struct kd_rwsem`, 40 bytes: `count` + a `kd_mutex m` used as the writer queue |
| Queue node | `struct mcs_spinlock` = `{next, locked, count}`, 16 bytes, from `qnodes[4]` per CPU (`_Q_MAX_NODES` = 4); mutex/rwsem spinners use `struct optimistic_spin_node` = `{next, prev, locked, cpu}` | `struct kd_node`, one cache line: `{next, state, tail, nid, regs, entry, claim}` plus, in `nodes[0]`, the per-CPU counters the plain path needs; `nodes[4]` and `mnodes[4]` per CPU (`KD_MAX_NODES` = 4) |
| Sleeping waiter record | `struct mutex_waiter` / `struct rwsem_waiter` **on the waiter's own stack**, linked into `wait_list` | `struct kd_mutex_waiter` on the waiter's own stack, linked into `waiters` (same idea) |
| Continuation record | none | `struct kd_regs`, 256 bytes (4 cache lines), one per CPU, in `kd_cpu.regs` |
| Extra per-CPU memory | `qnodes[4]`, `osq_node` | `kd_cpu`: packet, `nodes[4]`, `mnodes[4]`, a 16 KiB wait stack, counters |

The lock objects have the native sizes on purpose, so containers that embed
them (`struct page`, `lockref`, ...) keep their layout.

## 3. Register and state accounting

This is the table the rest of the document explains. "Words" are 8-byte stores
or loads of architectural state, not counting the lock word itself.

### 3.1 Native

| Path | Registers saved / restored | Where | Notes |
| --- | --- | --- | --- |
| `spin_lock` fast path | **0** | — | inlined `preempt_disable()` + one `cmpxchg` |
| `spin_lock` contended, pending | 0 architectural; the compiler's frame for `queued_spin_lock_slowpath` | callee's stack frame | spins on the locked byte |
| `spin_lock` contended, queued | as above + an MCS node initialised (2 stores: `locked`, `next`) and `count++` | per-CPU `qnodes[idx]` | spins on `node->locked`, then on the lock word |
| `mutex_lock` fast path | **0** | — | one `cmpxchg` on `owner` |
| `mutex_lock`, optimistic spin | compiler frame + an OSQ node (`next`, `prev`, `locked`, `cpu`: 4 stores) | per-CPU `osq_node` | spins on `owner` and `node->locked` |
| `mutex_lock`, parked | as above + `struct mutex_waiter` (3 stores) on the waiter's stack | its own stack | then `schedule()` |
| `down_write` fast path | **0** | — | one `cmpxchg` on `count` + one store of `owner` |
| `down_write`, parked | compiler frame + OSQ node + `struct rwsem_waiter` (5 stores) | its own stack | then `schedule()` |
| `write_lock` contended | compiler frame + **a full nested `qspinlock` acquisition** of `wait_lock` (with its own MCS node) | per-CPU `qnodes` | then `_QW_WAITING` and wait for readers |
| **any blocking wait**: `schedule()` → `__switch_to_asm` | **6 pushed + 6 popped** (`rbp`, `rbx`, `r12`-`r15`), `rsp` moved to `task->thread.sp`, stack canary reloaded, `FILL_RETURN_BUFFER` (RSB overwrite) | both tasks' kernel stacks | plus `__switch_to`: TLS, FS/GS bases, FPU, `cr3` when the mm differs, and the new task's cache working set |

The native waiter never captures a continuation because it never needs one: it
is the only thing that will ever run its critical section. Its state is wherever
the compiler left it.

### 3.2 kdlock

| Path | Registers saved / restored | Where | Notes |
| --- | --- | --- | --- |
| `kd_spin_lock` fast path | **0** | — | `incl __preempt_count` + one `cmpxchg`; identical shape to native |
| `kd_mutex_lock` fast path | **0** | — | one `cmpxchgb` on the locked byte + one store of `owner` |
| `kd_down_write` fast path | **0** | — | one `cmpxchgq` on `count`; no owner store (the wake target is `m.owner`) |
| plain mode, contended | the `*_slow` C function's frame + a `kd_node` initialised (`next`, `tail`, `claim`, `state`) | per-CPU `nodes[idx]` | the native algorithm, pending bit included; **nothing is published** |
| **offer path** (`KD_OFFER`, the waiter publishes) | **10 words stored**: `rbx`, `rbp`, `r12`, `r13`, `r14`, `r15` (6 callee-saved), `rax` (the value the lock call must return), `rsp` (computed as `rsp+8`, past the return address), `rip` (read from `[rsp]`), `rflags` (`pushfq`) | per-CPU packet `kd_cpu.regs` | caller-saved registers (`rcx`, `rdx`, `rsi`, `rdi`, `r8`-`r11`) are dead across a call, so they are not state; `rdi` (the lock) is kept in `rbx` across the C call |
| offer path, return without delegation | **5 loads** (`rbx`, `rsp`, `rax`; `busy` cleared) | — | the return address was never popped, so the stub just returns |
| **`kd_resume`** (origin continues after its section ran elsewhere) | **16 GPRs + `rsp` + `rip` + `rflags` = 19 words loaded** | from the packet | `rip` and `rflags` are staged just below the origin's `rsp`; `popfq` installs the origin's logical interrupt flag; `ret` continues after the release call |
| **`kd_jit_enter`** (executor enters a section) | **6 pushed** (executor's `rbp`, `rbx`, `r12`-`r15`), `rsp` saved to `kd_cpu.host_rsp`, then `rsp` switched to the origin's stack, **16 GPRs loaded** from the packet + `popfq` | executor stack, then origin stack | `push`/`ret` instead of an indirect jump, so resume points in generated code need no ENDBR and no retpoline |
| **`kd_jit_exit`** (section ends or hands back) | **16 GPRs + `rsp` + `rflags` = 18 words stored**, then `rsp` restored from `host_rsp` and **6 popped** | packet, then executor stack | exit stubs use only `mov`, so the flags stored are the section's own |
| **`kd_nested_exit`** (contended inner lock inside a section) | **8 GPRs stored** (`rax`, `rbx`, `rbp`, `rdi`, `r12`-`r15`) + `rsp` + `rflags` + the resume address = **11 words** | the same packet, no copy | again only callee-saved plus `rdi`/`rax`, because the inner lock call has already returned-in-effect |
| combiner per served section | the 18 + 16 words above, plus one `claim` store one section ahead and one `smp_mb()` | — | no atomic per waiter since build #57 (LOCKS 4) |
| blocking wait (`kd_mutex_sleep`, rwsem sleep) | exactly the native cost: `__switch_to_asm` 6 + 6, `__switch_to` | — | kdlock does not change how a task blocks; it tries not to get there |

So a delegated acquisition costs the origin **10 words out, 19 words back**, and
no task switch. A native blocking acquisition costs two task switches of 6
callee-saved registers each plus everything `__switch_to` does, and the critical
section still runs on the waiter's own cold cache.

## 4. Spinlock, side by side

### 4.1 Native

```
spin_lock(l):                                 # inlined
    preempt_disable()
    if cmpxchg(l->val, 0, _Q_LOCKED_VAL):     # 1 atomic, 0 registers saved
        return
    queued_spin_lock_slowpath(l, val)

queued_spin_lock_slowpath(l, val):
    # (a) pending: one waiter waits without a queue node
    if val == _Q_PENDING_VAL:                 # a pending waiter is already there
        spin until val changes, bounded by _Q_PENDING_LOOPS
    if val & ~_Q_LOCKED_MASK: goto queue
    val = fetch_or(l->val, _Q_PENDING)        # 1 atomic
    if not contended further:
        smp_cond_load_acquire(&l->locked, !VAL)   # spin on the holder's byte
        clear_pending_set_locked(l)           # 1 store
        return                                # lock held

    # (b) MCS queue
queue:
    node  = this_cpu(qnodes[0]); idx = node->count++
    node  = &qnodes[idx]; node->locked = 0; node->next = NULL
    tail  = encode_tail(cpu, idx)
    if queued_spin_trylock(l): goto release
    old = xchg_tail(l, tail)                  # 1 atomic: join the queue
    if old has a predecessor:
        prev->next = node
        spin on node->locked                  # until promoted
    val = atomic_cond_read_acquire(&l->val,   # queue head: wait for the holder
                                   !(VAL & _Q_LOCKED_PENDING_MASK))
    # become the owner, pass the tail on
    ...
release:
    this_cpu(qnodes[0]).count--
    # caller now runs ITS OWN critical section, on a cold cache
```

Per contended acquisition the protected data moves to this CPU, and the lock
word moves at least twice (join the queue, take the lock).

### 4.2 kdlock

```
kd_spin_lock(l):                              # assembly stub, kd_entry.S
    preempt_disable()                         # incl __preempt_count
    if cmpxchg(l->val, 0, KD_Q_LOCKED):       # 1 atomic, 0 registers saved
        return                                # identical to native

    # contended: ask the family's C slow path on OUR OWN stack.
    # A C call preserves callee-saved registers and rsp, so if the answer is
    # "publish", the continuation is still exactly as the call left it.
    if kd_q_lock_slow(l, site = [rsp]):       # true = acquired here
        return                                # plain mode: native algorithm,
                                              # pending bit included
    # delegation mode and this site has generated code
    if bts(kd_cpu.busy, 0) was already set:   # nested / interrupt: cannot publish
        jmp kd_spin_lock_plain(l)

    # ---- offer path: 10 words out ----
    packet.rbx/rbp/r12/r13/r14/r15 = those registers      # 6
    packet.rax = return value of the lock call            # 1
    packet.rsp = rsp + 8                                  # 1 (past the ret addr)
    packet.rip = [rsp]                                    # 1 (the return addr)
    packet.rflags = pushfq                                # 1
    rbx = l                                               # survives the C call
    rsp = kd_cpu.wait_stack        # from here nothing writes below packet.rsp,
                                   # so a combiner may run on our stack
    r = kd_spin_wait(l)            # queue a delegable node, then wait

    if r == KD_WAIT_RESUMED:       # our section already ran on another CPU
        jmp kd_resume              # 19 words back, returns past the unlock
    # KD_WAIT_LOCAL: we are the queue head and hold the lock
    restore rbx, rsp, rax from the packet; kd_cpu.busy = 0
    return                         # run our own section, then possibly combine
```

```
kd_spin_wait(l):                              # kd_core.c, on the wait stack
    me = &kd_cpu.nodes[idx]; kd_node_init(me)
    me->nid   = numa_node_id()
    me->entry = site->entry                   # generated code, else NULL
    me->regs  = &kd_cpu.regs                  # the packet
    if queued behind somebody:
        cldemote(packet, stack top)           # kd_cldemote: hand the lines to
                                              # the shared level for the combiner
        st = smp_cond_load_acquire(&me->state, VAL != KD_N_WAIT)
        if st == KD_N_RESUME: return KD_WAIT_RESUMED
    # promoted to head (KD_N_HEAD / KD_N_HEAD_D)
    take the lock; run family post() hook
    if delegation mode and we published:
        kd_session(...)                       # section 6
    return KD_WAIT_LOCAL
```

## 5. rwlock writer, mutex, rwsem writer: the same comparison in short

### 5.1 rwlock writer

```
native write_lock(l):
    preempt_disable()
    if cmpxchg(l->cnts, 0, _QW_LOCKED): return         # 1 atomic
    queued_write_lock_slowpath(l):
        arch_spin_lock(&l->wait_lock)                  # a WHOLE nested qspinlock
                                                       # acquisition, own MCS node
        if cnts == 0 and cmpxchg(cnts, 0, _QW_LOCKED): goto unlock
        atomic_or(_QW_WAITING, &l->cnts)               # 1 atomic
        do  cnts = cond_read(l->cnts, VAL == _QW_WAITING)   # wait for readers
        while not cmpxchg(cnts, _QW_WAITING, _QW_LOCKED)
    unlock: arch_spin_unlock(&l->wait_lock)

kdlock kd_write_lock(l):
    preempt_disable(); if cmpxchg(l->cnts, 0, KD_RW_WLOCKED): return
    # the queue word `wait` is the writers' queue, not a nested spinlock;
    # writers always publish (kd_family.always_deleg), because one session
    # shares ONE wait for the readers to drain among all the writers it serves
    offer path (10 words) -> kd_write_wait -> head: post() waits for readers,
                                              then kd_session() runs every
                                              queued writer's section
```

The structural win is in `post()`: native pays "wait for the readers to leave"
once per writer; a kdlock session pays it once per **session**.

### 5.2 mutex

```
native mutex_lock(l):
    if cmpxchg(l->owner, 0, current): return              # 1 atomic
    __mutex_lock_common(l, state):
        preempt_disable()
        if __mutex_trylock(l) or mutex_optimistic_spin(l, ...):
            # osq_lock(): OSQ node (4 stores), spin while owner is on a CPU
            return 0
        raw_spin_lock(&l->wait_lock)
        waiter = {list, task = current, ww_ctx}           # on OUR stack
        list_add_tail(&waiter.list, &l->wait_list)
        for (;;):
            if __mutex_trylock(l): break
            if signal_pending(): goto err
            set_current_state(state)
            raw_spin_unlock(&l->wait_lock)
            schedule_preempt_disabled()                   # __switch_to_asm: 6+6
            raw_spin_lock(&l->wait_lock)
            if first waiter: mutex_optimistic_spin(...)
        list_del(&waiter.list); raw_spin_unlock(&l->wait_lock)
        # then run OUR OWN critical section

kdlock kd_mutex_lock(l):
    if cmpxchgb(l->locked, 0, 1): l->owner = current; return   # 1 atomic + 1 store
    r = kd_mutex_lock_slow(l, site)
    if r != KD_SLOW_OFFER: return r        # plain mode: MCS spin while the owner
                                           # runs, then park on ->waiters
    offer path (10 words); kd_mutex_wait(l):
        me = kd_mnode_alloc()              # from mnodes[4], FREE-state pool
        queue; spin on me->state
        # giving up requires a withdrawal the combiner can lose a race against:
        #   waiter: cmpxchg(state, WAIT, ABANDON), then read me->claim
        #   head:   me->claim = true (plain store, one section ahead), smp_mb(),
        #           read me->state
        if resumed: kd_resume (19 words)   # section ran on the combiner
        else: head -> take the lock -> kd_session() -> own section
```

Both sides park a waiter on its own stack and both have a handoff flag that
bounds sleeper starvation; kdlock additionally requires the handoff target to be
**running** (`kd_handoff_running`), because granting to a sleeping task made
every spinner see an off-CPU owner and park in turn.

### 5.3 rwsem

```
native down_write(sem):
    if cmpxchg(sem->count, 0, RWSEM_WRITER_LOCKED):          # 1 atomic
        sem->owner = current; return                          # 1 store
    rwsem_down_write_slowpath(sem):
        if rwsem_can_spin_on_owner(sem) and rwsem_optimistic_spin(sem):
            return                                            # OSQ as for mutex
        waiter = {list, task, type = WRITE, timeout, handoff_set}  # OUR stack
        raw_spin_lock_irq(&sem->wait_lock); list_add_tail(...)
        set RWSEM_FLAG_WAITERS
        for (;;):
            if rwsem_try_write_lock(sem, &waiter): break
            raw_spin_unlock_irq(&sem->wait_lock)
            schedule()                                        # 6+6 + __switch_to
            raw_spin_lock_irq(&sem->wait_lock)
        ...

native down_read(sem):
    if (count += RWSEM_READER_BIAS) has no writer: return     # 1 atomic
    rwsem_down_read_slowpath(): queue, maybe schedule()

kdlock kd_down_write(sem):
    if cmpxchgq(sem->count, 0, KD_RWSEM_WLOCKED): return      # 1 atomic, no owner store
    offer path (10 words); kd_down_write_wait(sem):
        wait in sem->m (a kd_mutex used as the writers' queue)
        head: take ->m, set the writer bit, post() = wait for readers to drain
              (bounded by kd_rwsem_wspin_ns, then sleep holding ->m)
              reader phase first if readers are in (kd_rwsem_rphase_ns)
              kd_session(): every queued writer's section, ONE reader wait
        release: one locked subtraction of the writer bit; ->m untouched

kdlock kd_down_read(sem):
    c = count                                   # look before adding: while a
    if c has writer bit or waiting writer:      # writer is in, the add+undo are
        return kd_down_read_slow(sem, c, false) # two more atomics on the line
                                                # the leaving readers need
    if (count += RBIAS) has no writer: return   # 1 atomic
    kd_down_read_slow(): register behind the active writer and poll a hashed
        phase counter in its own line (NOT count, which every entering and
        leaving reader writes); bounded by kd_rwsem_rspin_ns, then queue on ->m
```

Readers never delegate on either side. The kdlock differences are all about
which cache line a waiting reader polls and how long a writer phase lasts.

## 6. The delegation cycle in full

This is what has no native counterpart at all.

```
# ---------- origin W, after the offer path ----------
W: packet  = {6 callee-saved, rax, rsp, rip, rflags}       # 10 words
   node    = {next, state = WAIT, tail, nid, regs = &packet, entry = image}
   cldemote(packet, stack top)                              # spin class
   spin on node.state                                       # its own line

# ---------- combiner C (queue head, holds the lock) ----------
C: kd_session(q, me, root, f):
     for (;;):
       n = me->next
       if !n or budget exhausted or !n->entry or need_resched(): break
       if sleepable and HANDOFF flag set (checked every 16 sections): break
       if numa and n->nid != me->nid and served >= numa_after:
            detach n onto a session-private list; continue   # other node later
       if !kd_ctx_compatible(n->regs): break                 # IF mismatch
       if sleepable:
            n->claim = true (already stored one section ago); smp_mb()
            if n->state != WAIT and kd_node_drop(n): free it; continue
       nn = n->next
       if sleepable: nn->claim = true          # announce the next one
       else:         prefetch(nn); prefetchw(packet of nn, 4 lines)

       done = kd_exec_one(root, n, f)          # <<< run W's section, below
       if nn: prefetchw(nn->regs, 4 lines)
       unlink n from the queue
       if handed back:
            splice the deferred list back in front
            offer ourselves to W (role exchange) unless the grant did not move
       smp_store_release(&n->state, RESUME)    # last touch of n and its packet
       kd_irq_release(&hold)                   # interrupts stay off until here
                                               # if the section was handed back
                                               # with interrupts off
       if handed back: break
       every 32 sections: leave delegation mode if the queue got short
     # then: release() hook, pass the head role on, run C's own section last

# ---------- executing one section ----------
kd_exec_one(root, n, f, hold):
   local_save_flags(flags)
   if origin had softirqs off and we do not: local_bh_disable()
   preempt_count += KD_EXEC_PIN (32)           # a section may release locks the
                                               # origin took earlier
   rcu_sync(our depth -> origin's rcu_depth)
   kd_cpu.task       = origin task             # what `current` reads in the copy
   kd_cpu.canary     = origin's stack canary
   kd_cpu.stack_top  = origin's cpu_current_top_of_stack
   kd_cpu.root       = root                    # which release ends the section
   kd_cpu.cur        = packet;  kd_cpu.anc = nroots
   kd_jit_enter(packet, code):                 # 6 pushed, 16 loaded, popfq, ret
       <<< real machine code, on the ORIGIN'S stack, with the ORIGIN'S flags >>>
   # the image leaves through an exit stub: mov exit_ip/resume/exit_code/aux
   # into kd_cpu, then jmp kd_jit_exit (18 words stored, 6 popped)
   switch (exit kind):
     UNLOCK of the session root      -> record its effects on the origin
                                        (preempt count, IF, BH) in the packet;
                                        DO NOT release; section complete
     UNLOCK = downgrade (rwsem)      -> kd_vdown: keep the write side, mark the
                                        packet and go on executing the read part
     UNLOCK_ANC                      -> an outer root: mark `released`;
                                        otherwise perform it natively
     NESTED (inner spin-class lock)  -> queue the same packet for the inner lock
     ACQUIRE (mutex/rwsem inside)    -> try as the origin without sleeping,
                                        else hand back
     MISS_* / FRONTIER / BUDGET      -> hand back; report to the translator
   d = preempt_count() - pc0; subtract d here, add it to packet.pc_delta
   restore IF/BH (or keep interrupts off until the resume is published)

# ---------- origin W resumes ----------
W: sees node.state == RESUME
   kd_finish_resume(pin): cli; apply packet.pc_delta; rcu_sync
   kd_resume: 19 words loaded, rsp back to its own stack,
              rip/rflags staged below rsp, popfq, ret
   # continues at the instruction AFTER the release call. It never executed the
   # section and never executed the release.
```

## 7. Cost per contended critical section

| | native | kdlock, delegated |
| --- | --- | --- |
| Atomics on the lock word | at least 2 per waiter (join the queue, take the lock) + the release | 1 per session for the grant + the release; the queue tail `xchg` per waiter |
| Protected data | moves to every waiter in turn | stays in the combiner's cache |
| Code and its data | each waiter's own i-cache / d-cache, cold | hot on the combiner after the first section |
| Per-waiter state crossing CPUs | the lock's lines | node (1 line, shared) + packet (4 lines, exclusive) + the origin's stack top |
| Atomic per served waiter | — | none since build #57: a plain `claim` store one section ahead plus a barrier |
| Blocking | two task switches per park/wake, 6+6 callee-saved plus `__switch_to` | the same, but a section that would block is handed back first, so the combiner never sleeps holding the queue |
| Reader wait (rwsem) | polls `count`, which every entering and leaving reader writes | polls a phase counter in a line of its own |

What kdlock adds and native does not pay: the offer (10 words), the resume (19
words), `kd_jit_enter`/`kd_jit_exit` (6 + 16 and 18 + 6 words) per section, a
`popfq` and a `pushfq`, and the translator's images in memory. Those are the
reason for plain mode: below a queue depth of 5 (spinlock) or 3 (mutex) the
combiner outruns its waiters and the native algorithm is used instead
(ARCHITECTURE 7a).

## 8. Semantic differences that follow from the mechanism

| Topic | native | kdlock |
| --- | --- | --- |
| Who runs the critical section | always the owning task | the combiner, from a copy, unless it hands back |
| `current` inside the section | the running task | the origin, through `kd_cpu.task`; all other per-CPU data is the **executor's** (DIFFERENCES D3) |
| Preempt count | balanced on one task | measured on the executor, undone there, added to the origin on resume |
| RCU read-side depth | counted on the task | held by the executor while it runs the section, brought in line on the origin at resume (`kd_rcu_sync`) |
| Interrupt flag | the task's own | the origin's logical flag is installed with `popfq`; an executor with interrupts off never runs a section that expects them on |
| Stack traces | ordinary | no ORC data for images, the wait stack or the stack switch; traces through them stop early |
| Lock ordering / fairness | FIFO per queue (MCS) | FIFO within a NUMA node, batched across nodes (`kd_batch` executions); rwsem readers get a bounded phase |
| What a release does | hands the lock to the next waiter | a combiner keeps it for the whole session; a handback transfers it to the origin, which releases normally |

## 9. Measured result of the difference

Round 9 (`../bench/results/kdclaude/grid-20261115-r9-64cpu/`), 64 vCPUs on two
NUMA nodes, 2.7 GHz, one-line critical sections, Mops/s at 8 and 64 workers:

| Profile | native 8 / 64 | kdlock 8 / 64 | TCLocks 8 / 64 |
| --- | --- | --- | --- |
| spin c01 | 5.18 / 3.73 | 5.88 / 6.35 | 4.39 / 4.30 |
| mutex c01 | 3.58 / 1.61 | 3.76 / 3.66 | 3.23 / 3.09 |
| mutex c16 | 2.68 / 1.55 | 3.50 / 3.54 | 1.85 / 1.81 |
| rwlock writers only | 3.64 / 2.21 | 5.16 / 6.37 | 3.43 / 3.49 |
| rwsem writers only | 3.24 / 1.53 | 3.78 / 3.71 | 3.26 / 3.29 |
| rwsem 20% writes | 2.49 / 1.27 | 6.95 / 4.59 | 5.84 / 5.89 |
| rwsem 1% writes | 5.76 / 2.96 | 15.21 / 7.67 | 15.79 / 12.42 |

The pattern the mechanism predicts: where the critical section is delegable and
the queue is deep, native falls with the worker count and kdlock does not;
where readers dominate across two nodes, kdlock is still behind TCLocks
(PERF_PLAN, open items).
