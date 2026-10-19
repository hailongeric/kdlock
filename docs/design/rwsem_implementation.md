# Sleeping KD reader/writer semaphore

The waiting implementation in `c21345b` is the **accepted current KD rwsem**.
Acceptance includes the measured tradeoff: large gains at 60 workers and
substantial regressions at two workers with 20% writes. The
[performance status](../PERFORMANCE.md#accepted-rwsem-implementation-c21345b)
retains those results. This acceptance does not replace the selected KD mutex
protocol or establish support for every Linux reader/writer semaphore use.

[`kd_rwsem.h`](../../include/kd_rwsem.h) provides concurrent sleeping readers and
ordinary exclusive writers. The explicit outer-writer interface in
[`kd_rwsem_direct.h`](../../include/kd_rwsem_direct.h) also permits writer
delegation: a lock holder can execute a waiting writer's protected work through
the selected KD-only mutex. A reader/writer semaphore, abbreviated **rwsem**,
allows concurrent readers or one exclusive writer, and blocked callers can sleep.
Before a writer publishes a delegation request, it closes **reader admission**
(permission for new readers to enter) and waits for existing readers to finish,
called **reader drain**. A published mutex waiter then polls with preemption
disabled, so the scheduler cannot pause it in the ordinary way to run another
task on that CPU; this is the **pinned waiter** restriction.

No Linux mutex or Linux rwsem backs the object. The KD mutex keeps the same
physical ownership records, queue, and batching of several waiting operations.
Its machine-level calling agreement remains ABI2; just-in-time compiled (JIT)
code remains
immutable after publication. References keep the source module loaded until it
is no longer needed, unlock acknowledgements confirm release, and execution
records are retired only after their final user finishes. These ownership and
lifetime rules are unchanged. The [terminology guide](../TERMINOLOGY.md) explains
other code and evidence terms used below.
The [lock catalog](../LOCKS.md) compares this sleeping API with the spinning
rwlock and the two exclusive lock families.

## Source and object layout

| Source | Responsibility |
| --- | --- |
| [kd_rwsem.h](../../include/kd_rwsem.h) | Object layout, static initializer and ordinary public operations |
| [kd_rwsem.c](../../kernel_module/kd_rwsem.c) | Reader acquisition, exact writer reservations, bounded polling, sleeping waits, cancellation, downgrade and idle inspection |
| [kd_rwsem_direct.h](../../include/kd_rwsem_direct.h) | Outer-writer pair: reserve/drain before the mutex call, release the reservation on the origin after mutex unlock completes |
| [KD mutex implementation](mutex_implementation.md) | Physical writer ownership, legacy delegation queue, generated execution and unlock acknowledgements |
| [direct_rwsem.h](../../workload_modules/rwlock_bench/direct_rwsem.h) | Benchmark caller mapping for Linux Native, ordinary KD and delegation-capable KD |

The current header gives a 320-byte object with 64-byte overall alignment in
the captured configuration. The previous 512-byte object had 128-byte alignment;
the
[layout receipt](../../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/object-layout.json)
retains that accepted build's size evidence. Shrinking the embedded mutex changes
the containing layout without changing the rwsem waiting protocol. Current fields
are arranged as follows:

| Field | Offset | Purpose |
| --- | ---: | --- |
| `gate` | 0 | Embedded 32-byte KD mutex; serializes writer bodies |
| `readers` | 64 | Exact reader count, including temporary speculative increments |
| `admission` | 128 | Open, ordinary-writer or outer-writer phase |
| `phase_wait` | 192 | Sleeping callers waiting for an eligible admission phase |
| `reader_drain` | 256 | Reserved writers waiting for existing readers to finish |

The last four fields start on separate 64-byte lines. These offsets do not
describe a Linux rwsem-compatible layout. The embedded mutex now holds its own
delegation phase/count and encoded tail without an auxiliary table. Provider-wide
queues and execution stacks remain additional storage.
Existing rwsem performance records measure the previous containing layout and
do not establish performance for this refactor. There is no
separate rwsem delegation queue or new generated-code ABI.
The [compact mutex DWARF receipt](../../bench/results/10.176.26.71/tests/mutex32-20261019/layout-dwarf.json)
also records this containing layout from the built provider.

## API and scope

`DEFINE_KD_RWSEM()` and `kd_rwsem_init()` initialize static and dynamic objects.
`kd_down_read()` / `kd_up_read()` permit concurrent, sleeping readers.
`kd_down_write()` / `kd_up_write()` provide exclusive, sleeping ordinary writers.
Read and write trylocks return 1 on success and 0 on failure. Interruptible and
killable ordinary acquisitions return zero on success and `-EINTR` on
cancellation, without leaving reader, writer-admission or gate ownership behind.
Killable acquisition ignores nonfatal signals. An immediately available
acquisition may succeed despite a pending signal.

`kd_downgrade_write()` converts an ordinary writer to a reader without admitting
an intervening writer; finish with `kd_up_read()`. `kd_rwsem_is_idle()` is an
inspection helper after all callers stop and join. Its admission, reader and
gate checks cannot replace provider source/frame drain.

`KD_RWSEM_OUTER_WRITE_LOCK()` / `KD_RWSEM_OUTER_WRITE_UNLOCK()` are a separate
matched pair for delegation-capable outer writers. The caller supplies an opaque
`struct kd_rwsem_outer_cookie` to record one matching lock/unlock operation and a
unique named continuation (the point where execution resumes) in a `noipa`
function, which disables interprocedural compiler optimization. Prepare that
continuation on the embedded KD mutex with `kd_mutex_prepare()` and
`KD_ENTRY_ABI_MUTEX_CLOBBER_V1`. The compiler
knows which registers the call may overwrite and saves the values needed later,
as for direct KD mutex calls. The existing two-word wrapper input and packet
ABI do not change.

The outer pair cannot downgrade or cancel after publication. Its admission and
drain waits are uninterruptible; callers needing cancellation use an ordinary
acquisition. It must finish with its matching outer unlock, even when a
particular invocation executes locally. Ordinary trylock,
interruptible/killable acquisition and downgrade
retain their local contracts. Do not mix an ordinary acquisition with an outer
unlock, reuse or transfer a live cookie, or access the embedded gate directly.

All participants must adopt this API for the same object. This is not a
binary/layout-compatible replacement for Linux `struct rw_semaphore`. There is
no reader-to-writer upgrade, recursive locking guarantee, non-owner release API,
IRQ/BH variant, lockdep integration or RT support. The translator continues to
refuse ordinary rwsem APIs and admission helpers inside an enclosing delegated
body, including calls discovered while learning a helper. There is no nested
rwsem ledger mode or remote cancellation/downgrade contract.

## Who may enter: admission phases

An atomic admission word is independent of the embedded KD physical mutex:

| Admission value | Allowed participants |
| --- | --- |
| `0` | Readers may enter; an ordinary or outer writer may reserve admission |
| Positive | Exact number of live outer-writer reservations; no new reader or ordinary writer may enter |
| `-1` | One ordinary writer owns admission; no outer writer or new reader may enter |

The positive count records exact reservations acquired and released by the outer
API. It does not identify the physical executor or replace the mutex's owner,
queue, source lease, result acknowledgement or frame records. An outer
reservation begins before the KD mutex call and ends only after its matching
unlock returns on the originating task. An origin delayed after unlock therefore
keeps admission closed conservatively.

A reader observes admission open, publishes its reader count with a fully
ordered increment, then rechecks admission with acquire ordering. A failed
speculation rolls back without touching protected data. A slow reader retries
the same admission-aware acquisition, sleeping when needed; it cannot bypass a
closed phase by acquiring the physical gate. Speculative reader counts can
briefly appear during a writer phase, but those callers never access the
protected payload.

An outer writer atomically joins or creates a positive phase, executes the
reader-drain ordering barrier, and waits until existing readers drain. Only
then does it call the unchanged KD mutex outer interface, which may acquire
locally, combine other requests or publish a pinned waiter. All admitted
readers have finished before that publication, and the positive phase prevents
new admitted readers. The reader's ordered increment/recheck and the writer's
reservation/barrier/count check prevent both from missing each other.

The final reader's ordered decrement precedes the reader-drain wakeup.
Waitqueue enrolment and condition rechecks ensure a waiter either observes the
completed drain or receives a wakeup. Releasing the last outer reservation
reopens admission and wakes phase waiters. Reservation release is outside the
translated region, after the existing mutex unlock endpoint; synthetic
completion resumes there on the origin rather than releasing the reservation
from the executor.

## Waiting and wakeups

Reader counts, admission reservations, and the two waitqueue heads occupy
separate 64-byte-aligned regions. In the recorded accepted x86_64 build, this
increased the object from 384 to 512 bytes; both historical layouts had 128-byte
overall alignment through the former embedded mutex. The current compact gate
reduces the containing object to 320 bytes while retaining those separate regions.
`phase_wait` contains readers and writers
waiting for an eligible admission phase. `reader_drain` contains writers that
already hold an ordinary or outer reservation and are waiting for readers to
finish. The final reader wakes only `reader_drain`; an ordinary phase release
or final outer reservation release wakes only `phase_wait`. Reader drainage
cannot open a closed admission phase. A reader-drain waiter retains its
reservation, so admission cannot reopen while that wait remains live. Fully
ordered count/phase updates precede the lockless `waitqueue_active()` checks
and pair with waitqueue enrolment and predicate rechecks.

Uninterruptible acquisitions poll, meaning they repeatedly check whether they
can proceed before entering a sleeping wait. Each polling stage tries at most
16,384 condition checks and stops early when the scheduler needs the CPU.
Polling occurs before delegation publication, with preemption enabled;
its finite fallback lets sleeping or colocated holders resume. A successful
predicate may acquire a reader count or writer reservation, so it is consumed
once without another acquisition attempt. The ordinary writer's read-only
phase check is only a hint; its compare/exchange remains authoritative. The
budget is the accepted tuning for the captured benchmark platform, not a
universal optimum. It improves the measured 60-worker cases but substantially
reduces throughput in some two-worker cases; acceptance retains that limitation.

The polling bound counts predicate invocations, not elapsed time: the existing
outer-reservation predicate can retry its compare/exchange internally. The
fallback retains `wait_event()` enrolment, condition rechecks and scheduling.
Interruptible and killable acquisitions keep their existing sleeping waits and
cancellation rules. Wakeups prompt readers to retry their own admission-aware
acquisition. Published mutex waiters, physical ownership, queue batching and
wrapper ABI are unchanged.

## Ordinary writers, cancellation and downgrade

An ordinary writer atomically changes admission from `0` to `-1`, acquires the
KD physical gate locally, and drains readers while it may sleep. An unavailable
admission phase is itself a sleeping wait. Interruptible/killable acquisition
cancels at an applicable wait without retaining the phase or physical gate.
Failure during reader drainage releases both before reporting `-EINTR`.

Ordinary unlock releases the KD physical gate before reopening admission.
Downgrade publishes its reader count while it still owns both `-1` admission
and the physical gate, then releases the gate and reopens admission. A following
outer writer must reserve admission and drain this reader before publication.
An existing positive phase excludes ordinary ownership, so an ordinary writer
can never introduce a downgraded reader behind already-pinned outer writers.

The outer API does not downgrade because other writers in its positive phase
may already have published pinned requests. Introducing a reader at that point
would violate their reader-free admission guarantee and could prevent that
reader from resuming on a pinned CPU. Cancelling a published request would also
require changing the selected mutex's queue and source/frame lifetime protocol.
Keeping those operations on ordinary acquisitions preserves both contracts.

This construction prefers a live outer-writer cohort: new outer writers may
join a positive phase while readers or ordinary writers wait. It does not port
Linux rwsem's reader batching or fairness policy, and sustained outer-writer
arrivals can delay those waiters. It supplies no bounded-wait guarantee or
implied throughput advantage. The selected mutex's general oversubscription
limitations remain separate from the rwsem reader-drain solution.

## Why the archived delegation cannot be copied unchanged

The archived implementation remains reachable at
`archive/task/sleep-rwsem-snapshots` (`82f92db`). Its writer integration depended
on the rejected owned-mutex protocol:

1. It combined during unlock, after the physical writer had drained readers.
   The selected mutex may combine during acquisition. Reader drainage after
   its outer lock macro is therefore too late. The new positive phase drains
   readers before entering that macro.
2. `cookie.owner == 0` includes routed physical acquisitions and native
   fallbacks; it does not identify only synthetic delegated entries. The new
   phase protocol applies before every outer acquisition without making this
   assumption.
3. Published waiters poll with preemption disabled. Waiting for a sleeping
   reader only after publication can prevent that reader from resuming on a
   pinned CPU. The new drain wait happens before publication while the caller
   remains schedulable.
4. A pre-publication reader drain alone cannot account for a later ordinary
   downgrade. Exclusive ordinary admission prevents that transition from
   overlapping a positive outer-writer phase.

These admission rules resolve the rwsem-specific ordering hazards without
restoring the owned/adaptive protocol, Linux mutex backing or parked published
producers.

## Mmap and validation boundaries

The API does not integrate this object into `mm_struct::mmap_lock`. That requires
coordinated replacement of every reader/writer, Linux helper and lockdep
contracts, fault/VMA lifetimes, retry and lock-mode transitions, and kernel
configuration validation. Safe admission does not establish that
`access_remote_vm()` or another task-dependent body can be delegated; existing
instruction and context admission still apply.

The [API probe](../../tests/kernel/rwsem/README.md) covers sleeping readers,
writer/late-reader exclusion, same-CPU scheduling progress, cancellation,
trylocks, downgrade and drain. Its phase-specific checks distinguish the two
waitqueues and keep an outer writer before publication while an ordinary reader
or downgraded writer is active. Separate strict JIT acceptance checks require
returned bodies through matching outer-unlock completions; a published `NORMAL`
image alone is insufficient. Native, delegated-capable KD and ordinary local KD
shells retain distinct source and instrumentation identities.

See the [optimization validation receipt](../../bench/results/10.176.26.71/tests/rwsem-optimization-20261018/README.md)
for recorded checks and source identities. Functional and JIT acceptance do not
establish throughput parity; measured comparisons belong in the
[optimization report](../../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
and [performance status](../PERFORMANCE.md).

The [initial writer-delegation receipt](../../bench/results/10.176.26.71/tests/rwsem-delegation-20261018/README.md)
records the earlier shared-queue implementation without bounded polling. The
[previous ordinary-only receipt](../../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
and [archived delegated receipt](../../bench/results/10.176.26.71/tests/rwsem-snapshots-20261015/README.md)
describe their captured implementations. Those earlier receipts do not establish
validation or performance of the current waiting implementation.
