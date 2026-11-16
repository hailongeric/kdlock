# Lock families and API

Per-family protocol, public API and semantics. The shared machinery (queue,
session, executor, handback) is in [ARCHITECTURE.md](ARCHITECTURE.md); this
page only states what differs per family. Prototypes are in
`include/kdlock/kd_api.h`, object layouts in `include/kdlock/kd_types.h`.

## 1. API overview

Every lock operation is an **out-of-line call**. That is a protocol
requirement: generated code recognises lock operations by call target, so an
inlined release would let a delegated section run past its end. With
`CONFIG_KDLOCK`, the `CONFIG_INLINE_*` variants and
`CONFIG_UNINLINE_SPIN_UNLOCK` must be configured so no unlock is inlined.

| Family | Delegable acquire (assembly stubs) | Local-only |
| --- | --- | --- |
| spinlock | `kd_spin_lock`, `_irq`, `_irqsave`, `_bh` | `kd_raw_spin_lock{,_irq,_irqsave,_bh}`, `kd_spin_trylock{,_bh,_irq,_irqsave}`, `kd_arch_spin_{lock,trylock,unlock}` |
| rwlock | `kd_write_lock`, `_irq`, `_irqsave`, `_bh` | `kd_read_lock{,_irq,_irqsave,_bh}`, `kd_read_trylock`, `kd_write_trylock{,_irqsave}`, `kd_arch_{read,write}_{lock,trylock,unlock}` |
| mutex | `kd_mutex_lock`, `_interruptible`, `_killable`, `_io` | `kd_mutex_trylock` |
| ww_mutex | none | `kd_ww_mutex_lock{,_interruptible}`, `kd_ww_mutex_lock_slow{,_interruptible}`, `kd_ww_mutex_trylock` |
| rwsem | `kd_down_write`, `_killable` | `kd_down_read{,_interruptible,_killable}`, `kd_down_read_trylock`, `kd_down_write_trylock`, `kd_downgrade_write` |

Releases are ordinary C functions (`kd_spin_unlock*`, `kd_write_unlock*`,
`kd_read_unlock*`, `kd_mutex_unlock`, `kd_ww_mutex_unlock`, `kd_up_write`,
`kd_up_read`). The translator knows them by symbol: a call to one with `rdi`
equal to the session root ends the section.

**Coverage.** These are all operations the Linux 7.0 headers declare for
`spinlock_t`, `raw_spinlock_t`, `rwlock_t`, `struct mutex`, `struct ww_mutex`
and `struct rw_semaphore`; `integration/kd_linux_map.h` maps each native name.
The lockdep-only variants (`_nested`, `_nest_lock`) are the plain operations
without lockdep, and the reader `_non_owner` forms are the plain reader
operations because no reader owner is recorded. Helpers: `kd_spin_is_locked`,
`kd_spin_is_contended`, `kd_rwlock_is_contended`, `kd_mutex_is_locked`,
`kd_mutex_get_owner`, `kd_ww_mutex_is_locked`, `kd_rwsem_is_locked`,
`kd_rwsem_is_write_locked`, `kd_rwsem_is_contended`. `bench/kd_bench.c`
(`KDB_IOC_APITEST`) calls every variant once and checks lock state, interrupt
flag and preempt count against what the native variant leaves.

**What "delegable" means for the sleeping and signal variants.** A caller
of `kd_mutex_lock_interruptible/_killable/_io` or `kd_down_write_killable`
whose section is delegated gets 0, like an uncontended caller. Signals are
looked at only once the caller parks, where the native rules apply
(`-EINTR`); `_io` accounts the parked wait as I/O wait. Readers, trylocks and
ww mutexes never publish a continuation: a reader runs concurrently with
other readers, a trylock does not wait, and a ww acquisition may have to
back off.

**All users of one object must use kdlock.** Queue encodings and layouts are
not interchangeable with the native locks; replacing a lock type means
replacing the object and every caller (see
[KERNEL_INTEGRATION.md](KERNEL_INTEGRATION.md)).

**What may be delegated.** Only a caller in task context, with an image for its
call site, whose lock is in delegation mode (ARCHITECTURE 7a), and whose saved
interrupt state the executor can honor (`kd_ctx_compatible`). Everything else
queues as a plain waiter. A delegated section must not sleep on the combiner;
every call that can sleep is a frontier exit and ends the delegation at that
call.

## 2. Spinlock

* The queue word **is** the lock, with the layout of the native queued
  spinlock. In plain mode it also behaves like it: a free lock with no
  waiter is taken by one cmpxchg of the whole word, the first contender
  becomes the *pending* waiter and spins on the lock byte, later ones join
  an MCS queue whose head waits for holder and pending waiter to leave and
  then takes the lock with a plain store. Nobody can barge past a queue.
* In delegation mode a contended caller of a delegable entry publishes its
  continuation and queues the same way; the queue head, once it holds the
  lock, serves the waiters behind it and then hands the head role on.
* `kd_raw_spin_lock*` and the `kd_arch_spin_*` level use the same word but
  **never publish** (scheduler, timers, lock internals) and never combine.
* `_irq`, `_irqsave` and `_bh` entries are delegable: the section runs with
  the origin's logical IF/BH state (see ARCHITECTURE 6). Their releases apply
  the matching logical effects when they are the session root release
  (`kd_apply_unlock`).
* Release is a byte store. A holder that has a role-exchange offer to
  answer finds out from its own CPU's state (`kd_cpu.xcount`), not from the
  lock word.

## 3. Rwlock (writer-preference queued, qrwlock-like)

* `cnts`: writer byte (`0xff` = locked), writer-waiting bit (`0x100`), reader
  count from bit 9. `wait` orders slow-path readers and writers.
* **Writers are delegable.** A queued writer at the head takes `wait`, sets the
  waiting bit, waits for readers to drain (`kd_rw_post`) and takes the writer
  byte. As combiner it keeps **both** `wait` and the writer byte while serving
  the writers behind it; release only clears the writer byte, so after a
  handback the origin releases with the ordinary call while the combiner still
  holds `wait` and reacquires the byte as the next writer (`keeps_q`).
* **Readers are never delegated** and run on their own task. A session stops
  at the first queued reader, which preserves FIFO between readers and writers.
  Interrupt-context readers do not queue behind waiting writers (as in
  qrwlock), so an interrupted reader cannot deadlock.
* Cost note: delegation only helps writers. Reader-heavy mixes are
  determined by the reader path and the writer-wait bit.
* **Across NUMA nodes** a session's own order cannot help while readers are
  present, because each queued reader ends the session (round 10: 1.4-1.8
  sections per session with 20% writes). Under pressure the lock therefore
  serves one node at a time (an *era*, ARCHITECTURE 7b): a reader that met
  a writer, and a writer whose fast path failed, wait for their node's era
  before they queue, polling the era word and not the lock. The wait is
  bounded by twice `kd_rw_era_ns` and ends at `need_resched()`; a caller
  with interrupts or bottom halves off, or outside task context, does not
  wait at all. A reader that finds no writer is never held back.

## 4. Mutex

* `q.locked` is the lock; everybody acquires by cmpxchg on that byte, so
  parked waiters, the queue head and new callers compete like in the native
  mutex.
* Two kinds of waiter:
  * **Spinning** waiters stay in the MCS queue **while the owner is running**
    (`kd_mutex_can_spin`: no `need_resched()`, owner on a CPU), the role the
    optimistic-spin queue has in the native mutex. They are non-preemptible.
    In plain mode they wait on their own stack and each takes the lock
    itself at the queue head. In delegation mode they publish their
    continuation; the queue head, once it owns the mutex, runs their
    sections before its own.
  * **Parked** waiters sleep on `->waiters` under `wait_lock`.
* A spinning waiter becomes a parked one by **withdrawing first**, and a
  section is executed by exactly one of the waiter and the combiner
  (`kd_node_abandon()` in `kd_internal.h`):
  * The combiner announces a waiter with a plain store (`claim = true`)
    and reads its `state` after a full barrier. It announces the waiter
    after next while it executes the current one, so nothing waits for the
    store.
  * The waiter withdraws with `WAIT -> ABANDON` by cmpxchg and then reads
    `claim`. If it is clear, the waiter has left and the head unlinks the
    node (`ABANDON -> DROP -> FREE`). If it is set, the waiter takes the
    withdrawal back (`ABANDON -> WAIT`) unless the head already moved the
    node to `DROP`.
  * A head that does not execute an announced waiter clears `claim` while
    it still is the head.
  * Before build #57 the combiner claimed with a cmpxchg `WAIT -> RUN` per
    section. The waiter polls that line, so the locked instruction waited
    for an exclusive copy each time: 72% of `kd_session`'s samples for
    rwsem writers at 64 workers (#56). Without it, rwsem writers only went
    from 2.04 to 2.60 Mops/s at 64 workers and from 2.14 to 2.70 at 32
    (#57 against round 7; TCLock 2.58 and 2.70 in the same boot).
* **Handoff.** A parked waiter that keeps losing sets `KD_QF_HANDOFF`; a
  running session then stops early, and the next release takes the lock
  again for the first parked waiter (`owner` changes, the waiter is woken)
  unless somebody was faster in between, in which case the flag stays for
  the release after that. This bounds sleeper starvation in practice; it is
  not the strict handoff of the native mutex.
* **A handoff is granted only to a waiter that is running**
  (`kd_handoff_running`, default 1). If the requester went back to sleep,
  the release only wakes it and the request stays for the release that
  finds it running. A grant to a sleeping task left the mutex with an
  owner off the CPU until the wakeup arrived; the queue head and every new
  caller then parked as well and asked for a handoff in turn. Measured
  (#58, in-boot alternation, 3 rounds, mutex c01, Mops/s): 64 workers
  2.15-2.31 -> 2.62-2.67 with parked waits per second from 7900-13100 to
  390-770; 40 workers 2.44-2.64 -> 2.69-2.70; 32 workers 2.74-2.75 ->
  2.79-2.80; c16 at 64 workers 2.27-2.35 -> 2.50-2.52.
* Release is one atomic operation whether or not spinners are queued: a
  locked subtraction clears the lock byte and returns the flags as they
  were, so there is no lost wakeup. The lock word is not read before the
  release and nothing is read after it (either costs a cache transfer on
  the handover path); what a flag asks for (`SLEEPERS`, `HANDOFF`, `XHEAD`)
  is done after the release, with the lock taken again where needed.
* `owner` is the **logical** owner (the origin, also for delegated sections).
  `kd_mutex_nested` takes it for `r->task`.
* Signals: while a waiter spins in the queue it does not observe signals
  (bounded by the owner running). Once it parks, `interruptible`/`killable`
  behave like the native mutex (`-EINTR`). A section delegated for a
  `killable` caller is not cancelled by a signal.
* A mutex section that blocks (calls anything that can sleep) is handed back
  to its origin at that call; the origin continues as the ordinary owner.

## 5. Rwsem

* `count`: writer bit, waiting-writer bit, need-wake bit, reader bias. A
  `kd_mutex m` is the queue and the single point where writers wait; **only the
  holder of `m` sleeps on `count`**, so `m.owner` is always the right wake
  target.
* **Writers are delegable** (`kd_down_write`, `_killable`), through the mutex
  queue. The head takes `m`, sets the writer bit and waits for readers to
  drain (`post()`); if draining would need sleep it returns
  `KD_WAIT_SLEEP_HELD` and the stub sleeps for `count` while holding `m`.
* **Readers never delegate, and normally do not queue on `m`**
  (`kd_down_read_admit()`). The fast path reads `count` first and adds the
  reader bias only when no writer bit is set.
  * **A writer is in (`WLOCKED`):** the reader registers (adds its bias)
    and waits for the writer bit to clear. That is the end of the
    writer's session, since the combiner keeps the bit for all the writers
    it serves. The readers registered behind one writer phase enter
    together, and the next writer waits for exactly that batch.
  * **A writer is only waiting (`WWAIT`):** the reader stays out until
    that writer is in, then registers behind it. Registering earlier would
    keep the waiting writer out indefinitely.
  * **The wait is bounded** by `kd_rwsem_rspin_ns` (50 us) and by
    `need_resched()`. After that the reader deregisters and parks on `m`,
    where it can sleep and is not passed by later writers.
  * **Waiting readers do not poll `count`.** They poll a phase counter in
    a cache line of its own (`kd_rwsem_phase()`, 256 counters shared by
    hash of the semaphore address). It changes when a writer leaves with
    readers registered behind it, on a downgrade, and when a queued writer
    gets in; a change only means "look at `count` again". `count` is
    written by every reader that enters or leaves, and each poller held a
    shared copy that those writes first had to take away. A reader also
    looks at `count` every 64 iterations without a change.
* **Reader phase** (`kd_rwsem_rphase_ns`, default 1000). A queue head that
  finds readers in waits that long per reader it found, at most 50 us,
  before it sets `WWAIT`. Otherwise each reader got one section per writer
  phase and then waited through the next session.
  * Fixed lengths (#59, in-boot alternation, 2 rounds, 20% writes, Mops/s):
    8 workers 4.64 -> 5.80 at 5 us; 32 workers 4.42 -> 5.82 at 20 us; 64
    workers 2.92 -> 4.00 at 30 us; lower again for longer phases; 4 workers
    7.29 -> 7.00 at 5 us.
  * Per reader, 1000 ns (#60, same method): 8 workers 4.68 -> 5.71, 16
    workers 4.69 -> 5.88, 32 workers 4.32 -> 5.63, 64 workers 2.77 -> 3.98,
    4 workers 7.47 -> 7.41; 1% writes at 64 workers 5.53 -> 6.54; c16 with
    20% writes at 8 workers 3.91 -> 4.31, at 64 workers 2.48 -> 2.57.
  * A single reader gets no phase (from #66): in mmap1 it is the tail of
    the previous munmap after its downgrade, and a phase per operation
    cost 12% at 4-32 threads (`bench/results/kdclaude/mmap1-20261115-64cpu/`).
  * It delays a writer by a bounded time per phase. This is a fairness
    change in the area AGENTS.md lists as deferred, made at the user's
    request.
  * Counters: `rd_behind` counts readers admitted behind a writer phase,
    `rd_queue` counts readers that fell back to `m`.
* **NUMA deferral starts late** (`kd_family.numa_after = 32`): a rwsem
  writer session serves the first 32 waiters in queue order and defers
  remote-node waiters only after that (ARCHITECTURE 7).
* **Eras** (ARCHITECTURE 7b, `kernel/kd_era.c`): readers are admitted
  outside the queue, so no order inside a session reaches them. Under
  pressure the rwsem serves one node at a time.
  * Who waits for its node's era: a reader that meets a writer, and a
    writer whose fast path failed. They wait before touching `count`
    again, polling the era word only, for at most twice `kd_rw_era_ns`,
    and the wait ends at `need_resched()`.
  * A reader that finds no writer is never held back, and its fast path
    does not look at the era. A check there (whenever two readers were in)
    cost every reader 3-12% on one node and gained nothing across nodes
    (build #81).
  * Not every reader is admitted when a writer session ends: only those of
    the era's node have registered behind it. The readers of the other node
    are still outside, and enter when the era is theirs.
  * `kd_rwsem_post()` supplies what decides whether there is an era: the
    readers the queue head found in, how long they took to leave, and how
    many callers were queued behind it.
  * `kd_down_read_trylock()` and `kd_down_write_trylock()` ignore the era.
* **Downgrade** (`kd_downgrade_write`) is one atomic when called natively.
  Inside a delegated section (`kd_vdown`, default 1) it does not end the
  session:
  * The combiner keeps the write side and goes on executing the read part
    of the section; the write side covers everything the read side
    allows. `kd_up_read()` of the session's rwsem then ends the section as
    a write release would, and the combiner serves the next waiter.
  * If the read part has to be handed back (a frontier such as a TLB
    shootdown or a call that can sleep, or code the translator has not
    learned yet), the downgrade is done for real at that point and the
    origin continues as a reader. The combiner makes no role-exchange
    offer then and takes the write side again as queue head.
  * With `kd_vdown=0` the section is handed back at the downgrade, as
    before build #67, and the session ends there. munmap downgrades on
    every call, so in mmap1 every session then served one waiter.
  * **Measured** (will-it-scale mmap1, threads, 2.7 GHz, #69, in-boot
    alternation, 3 runs; iterations per second, `kd_vdown` 0 -> 1 after
    the translator had learned the read part): 4 threads 271000-294000 ->
    374000-383000, 16 threads 253000-290000 -> 359000-373000, 32 threads
    239000-257000 -> 366000-374000, 64 threads 147000-152000 ->
    304000-325000. Sessions at 32 and 64 threads then run to the batch
    limit, with handbacks near zero. Native in the same boot: 319000-329000,
    285000, 278000-280000 and 150000-152000. Build #71 gives the same
    (`bench/results/kdclaude/tune-20261115-2700MHz/`): kd/Native 1.11-1.26
    at 4 threads, 1.28-1.38 at 8-32, 2.02-2.08 at 64; with `kd_vdown=0`
    0.77-0.83, 0.90-0.96 and 1.00-1.03.
  * **Cost:** other readers of that rwsem wait through the read parts
    instead of sharing them. The counters `vdown` and `vdown_hb` count the
    kept downgrades and those whose read part was handed back.
  * The first seconds after the daemon starts are slower: until the read
    part is learned it is handed back (248000-270000 in the first run).
* **Write release** (`kd_up_write`) is one locked subtraction, as for the
  mutex.
* **Every holder of `m` spins before it sleeps on `count`**, bounded by
  time (`kd_rwsem_wspin_ns`, 50 us): the writer at the queue head, a parked
  writer that got `m`, and a reader that queued. A holder of `m` that sleeps
  makes every later waiter see an owner off the CPU and park as well, and
  they are then woken one by one. mmap1 hit this behind munmap, whose
  unmap runs as a reader after a downgrade: 0.33 of Native at 4 threads
  before, 0.98 after. Nano rwsem: unchanged at 4-16 workers, 20% writers at
  32 workers +74-87%.
* Writers publish whenever they can; there is no plain mode for the writer
  queue (ARCHITECTURE 7a).
* A nested rwsem writer acquire inside a section is queued and spun for like
  any nested lock while its holder runs, and handed back with the call
  pending once it would need to sleep.

## 6. Semantics that differ from the native locks

| Topic | Native | kdlock |
| --- | --- | --- |
| Spin fairness | qspinlock pending bit + MCS | the same |
| Who runs a contended section | its own task | its own task in plain mode; the queue head's CPU in delegation mode, if an image exists |
| Who serves the queue after a section is handed back (mutex, rwsem writer) | n/a | the task it was handed back to, when it releases (role exchange) |
| RCU read-side depth during a delegated section | origin's | executor's, carried over to the origin |
| Mutex handoff to a parked waiter | lock never free in between | released, then taken again for the waiter if nobody was faster |
| Preempt count / IF during a delegated section | origin's | executor's, with the origin's logical IF and a transferred count |
| Per-CPU data accessed in a section | origin's CPU | executor's CPU (except the three task-identity symbols) |
| Mutex waiting | optimistic spin then sleep | MCS spin while owner runs, then park; handoff flag |
| Spin waiters in IRQ context | normal | never published, plain queue |
| Recursive lock of one object | deadlock | deadlock |
| `ww_mutex` deadlock avoidance | wound-wait or wait-die per class | wait-die for every class; callers see the same `-EDEADLK` / `-EALREADY` contract |
| `rt_mutex`, lockdep, PREEMPT_RT, debug locks | supported | `rt_mutex` is untouched (it does not use the replaced types); Kconfig refuses RT, lockdep and lock debugging |

## 6a. What the role exchange costs and gains

A/B in one boot (`kd_xchg` 0 against every family offering; build #37, three
rounds, medians, Mops; bodies in which every sixteenth write section is
handed back). `bench/results/kdclaude/probes-20261112/ab37xchg.jsonl`.

| Workers | mutex | rwsem writer | rwlock writer | spinlock |
| ---: | --- | --- | --- | --- |
| 4 | 3.118 → 3.116 | 2.646 → 2.618 | 3.249 → 3.235 | 4.436 → 4.435 |
| 8 | 3.066 → 2.934 (−4%) | 3.258 → 3.111 (−5%, ranges overlap) | 4.177 → 4.070 (−3%) | 4.601 → 4.512 (−2%) |
| 16 | 2.980 → 2.843 (−5%) | 2.552 → 3.049 (+19%) | 4.460 → 4.247 (−5%) | 4.591 → 4.391 (−4%) |
| 32 | 1.476 → 1.627 (+10%) | 1.037 → 1.028 | 2.560 → 2.686 (+5%) | 2.470 → 2.417 (−2%) |

The default (`kd_xchg=1`) therefore offers only for mutex and rwsem writer:
that is where a section can block, and where the alternative is a combiner
that ends up sleeping with the queue in its hands. The spinlock only lost.
These bodies hand back 6% of their sections; a site that hands back rarely
sees neither effect.

## 7. Tunables

| Name | Default | Meaning |
| --- | --- | --- |
| `kd_batch` (core param, 0644) | 4096 | executions (served + passed over) per wait; 1024 until build #68 (ARCHITECTURE 7) |
| `kd_vdown` (core param, 0644) | 1 | a downgrade in a delegated rwsem section keeps the write side and the session goes on (section 5); 0: handed back |
| `kd_cldemote` (core param, 0644) | 3 | bits: a queued spin-class waiter demotes 1 its packet, 2 its stack top (CLDEMOTE); 16 and 32 the same for the sleepable class (ARCHITECTURE 4.2) |
| `kd_numa` (core param, 0644) | 1 | NUMA-ordered sessions |
| `kd_numa_after` (core param, 0644) | 32 | rwsem: waiters a session serves in queue order before it defers other nodes' (ARCHITECTURE 7) |
| `kd_rw_era_ns` (core param, 0644) | 200000 | rwsem and rwlock: the era bound (a waiter waits at most twice this); 0: no eras, and the queue heads measure nothing (ARCHITECTURE 7b) |
| `kd_rw_era_press` (core param, 0644) | 225 | hundredths of a caller: average company a queue-head writer must find (readers in + up to 2 queued behind) for an era to start or be renewed |
| `kd_rw_era_drain_ns` (core param, 0644) | 5000 | no era while the readers a queue head finds take longer than this to leave, on average |
| `kd_rw_era_dbg_drain`, `kd_rw_era_dbg_press` (0444) | - | the last averages a queue head computed (ns; sixteenths of a caller) |
| `kd_rwsem_rspin_ns` (core param, 0644) | 50000 | how long a rwsem reader waits outside `m` before it queues there |
| `kd_rwsem_rphase_ns` (core param, 0644) | 1000 | time per reader found in that a rwsem queue head leaves the readers before it closes the read side (at most 50 us); 0: none |
| `kd_handoff_running` (core param, 0644) | 1 | mutex handoff only to a parked waiter that is running; 0: also to a sleeping one |
| `kd_adapt` (core param, 0644) | 1 | plain mode below the queue depths that follow; 0: always delegation mode |
| `kd_deleg_enter` (core param, 0644) | 5 | spinlock: waiters behind a queue head that switch the lock to delegation mode |
| `kd_deleg_enter_sleep` (core param, 0644) | 3 | the same for a mutex |
| `kd_deleg_exit` (core param, 0644) | 2 | a session leaves delegation mode with fewer waiters queued behind it |
| `kd_xchg` (core param, 0644) | 1 | role exchange after a handback: 0 never, 1 mutex and rwsem writer, 2 every family |
| `KD_PROBE_PERIOD` / `KD_VOTE_PERIOD` | 128 / 32 | contended acquisitions per depth sample in plain mode / sections per sample in a session |
| `KD_MAX_NODES` | 4 | queue nodes per CPU and class |
| `KD_MAX_ROOTS` / `KD_MAX_DEPTH` | 4 / 3 | nesting bounds |
| `KD_REQ_THRESHOLD` | 64 | contended waits before a site is requested |
| `KD_MISS_BUDGET` | 64 | learning reports per image |
| `KD_SITE_WINDOW` | 256 | executions between usefulness checks |
