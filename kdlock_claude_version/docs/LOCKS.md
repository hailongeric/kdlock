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
| spinlock | `kd_spin_lock`, `_irq`, `_irqsave`, `_bh` | `kd_raw_spin_lock*`, `kd_spin_trylock{,_bh}` |
| rwlock | `kd_write_lock`, `_irq`, `_irqsave`, `_bh` | `kd_read_lock*`, `kd_read_trylock`, `kd_write_trylock` |
| mutex | `kd_mutex_lock`, `_interruptible`, `_killable` | `kd_mutex_trylock` |
| rwsem | `kd_down_write`, `_killable` | `kd_down_read{,_interruptible,_killable}`, `kd_down_read_trylock`, `kd_down_write_trylock`, `kd_downgrade_write` |

Releases are ordinary C functions (`kd_spin_unlock*`, `kd_write_unlock*`,
`kd_read_unlock*`, `kd_mutex_unlock`, `kd_up_write`, `kd_up_read`). The
translator knows them by symbol: a call to one with `rdi` equal to the session
root ends the section.

**All users of one object must use kdlock.** Queue encodings and layouts are
not interchangeable with the native locks; replacing a lock type means
replacing the object and every caller (see
[KERNEL_INTEGRATION.md](KERNEL_INTEGRATION.md)).

**What may be delegated.** Only a caller in task context, with an image for its
call site, and whose saved interrupt state the executor can honor
(`kd_ctx_compatible`). Everything else queues as a plain waiter. A delegated
section must not sleep on the combiner; every call that can sleep is a
frontier exit and ends the delegation at that call.

## 2. Spinlock

* The queue word **is** the lock (`locked` byte). A free lock with no queue
  is taken by one cmpxchg of the whole word (`kd_q_trylock_fifo`), so a fast
  path can never barge past a queue. There is no pending bit: waiters go
  straight to the MCS queue (FIFO).
* The queue head takes the lock byte (`kd_q_head_lock`), serves followers,
  then hands headship to the successor.
* `kd_raw_spin_lock*` use the same word but **never publish** (used for
  scheduler, timers, lock internals) and never combine.
* `_irq`, `_irqsave` and `_bh` entries are delegable: the section runs with
  the origin's logical IF/BH state (see ARCHITECTURE 6). Their releases apply
  the matching logical effects when they are the session root release
  (`kd_apply_unlock`).

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

## 4. Mutex

* `q.locked` is the lock; everybody acquires by cmpxchg on that byte, so
  parked waiters, the queue head and new callers compete like in the native
  mutex.
* Two kinds of waiter:
  * **Spinning** waiters stay in the MCS queue **while the owner is running**
    (`kd_mutex_can_spin`: no `need_resched()`, owner on a CPU). They publish
    their continuation; the queue head, once it owns the mutex, runs their
    sections before its own. They are non-preemptible.
  * **Parked** waiters sleep on `->waiters` under `wait_lock`.
* A spinning waiter becomes a parked one by **withdrawing first**:
  `WAIT -> ABANDON` by cmpxchg. The combiner claims by `WAIT -> RUN`. One
  cmpxchg decides, so a section is executed by exactly one of them and a task
  is never run by a combiner and by itself.
* **Handoff.** A parked waiter that keeps losing sets `KD_QF_HANDOFF`; the next
  release then passes ownership to the first parked waiter directly (lock byte
  stays set, `owner` changes) and a running session stops early. This bounds
  sleeper starvation.
* Unlock uses `atomic_fetch_andnot_release` to learn atomically whether
  sleepers exist, avoiding a lost wakeup.
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
* **Readers never delegate.** A reader takes `count` by cmpxchg and parks on
  `m` when a writer holds or waits.
* **Downgrade** (`kd_downgrade_write`) is one atomic and, inside a section,
  is always handed back: the origin performs it natively.
* A nested rwsem writer acquire inside a section is queued and spun for like
  any nested lock while its holder runs, and handed back with the call
  pending once it would need to sleep.

## 6. Semantics that differ from the native locks

| Topic | Native | kdlock |
| --- | --- | --- |
| Spin fairness | qspinlock pending bit + MCS | plain FIFO MCS |
| Who runs a contended section | its own task | the queue head's CPU, if an image exists |
| Preempt count / IF during a delegated section | origin's | executor's, with the origin's logical IF and a transferred count |
| Per-CPU data accessed in a section | origin's CPU | executor's CPU (except the three task-identity symbols) |
| Mutex waiting | optimistic spin then sleep | MCS spin while owner runs, then park; handoff flag |
| Spin waiters in IRQ context | normal | never published, plain queue |
| Recursive lock of one object | deadlock | deadlock |
| `ww_mutex`, `rt_mutex`, lockdep, PREEMPT_RT, debug locks | supported | not provided; Kconfig refuses RT, lockdep and lock debugging |

## 7. Tunables

| Name | Default | Meaning |
| --- | --- | --- |
| `kd_batch` (core param, 0644) | 1024 | executions (served + passed over) per wait |
| `kd_numa` (core param, 0644) | 1 | NUMA-ordered sessions |
| `KD_MAX_NODES` | 4 | queue nodes per CPU and class |
| `KD_MAX_ROOTS` / `KD_MAX_DEPTH` | 4 / 3 | nesting bounds |
| `KD_REQ_THRESHOLD` | 64 | contended waits before a site is requested |
| `KD_MISS_BUDGET` | 64 | learning reports per image |
| `KD_SITE_WINDOW` | 256 | executions between usefulness checks |
