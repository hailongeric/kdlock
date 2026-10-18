# Sleeping KD reader/writer semaphore

[`kd_rwsem.h`](../../include/kd_rwsem.h) provides concurrent sleeping readers and
ordinary exclusive writers. The explicit outer-writer interface in
[`kd_rwsem_direct.h`](../../include/kd_rwsem_direct.h) also permits writer
delegation through the selected KD-only mutex. Reader admission closes and
existing readers drain before any writer can publish a pinned delegation
request. No Linux mutex or Linux rwsem backs the object. The KD mutex's physical
ownership, legacy queue and batching, ABI2, immutable images, source leases,
unlock acknowledgements and frame retirement remain unchanged.

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
`struct kd_rwsem_outer_cookie` for one lexical acquisition and a unique named
continuation in a `noipa` function. Prepare that continuation on the embedded KD
mutex with `kd_mutex_prepare()` and `KD_ENTRY_ABI_MUTEX_CLOBBER_V1`. The compiler
owns spills across the clobber boundaries, as for direct KD mutex calls. The
existing two-word wrapper input and packet ABI do not change.

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

## Admission phases

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
speculation rolls back without touching protected data. A slow reader sleeps
and retries the same admission-aware acquisition; it cannot bypass a closed
phase by acquiring the physical gate. Speculative reader counts can briefly
appear during a writer phase, but those callers never access the protected
payload.

An outer writer atomically joins or creates a positive phase, executes the
reader-drain ordering barrier, and sleeps until existing readers drain. Only
then does it call the unchanged KD mutex outer interface, which may acquire
locally, combine other requests or publish a pinned waiter. All admitted
readers have finished before that publication, and the positive phase prevents
new admitted readers. The reader's ordered increment/recheck and the writer's
reservation/barrier/count check prevent both from missing each other.

The final reader's ordered decrement precedes the drain wakeup. Waitqueue
enrolment and condition rechecks ensure a waiter either observes the completed
drain or receives a wakeup. Releasing the last outer reservation reopens
admission and wakes readers and ordinary writers. Reservation release is
outside the translated region, after the existing mutex unlock endpoint;
synthetic completion resumes there on the origin rather than releasing the
reservation from the executor.

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

The [current validation receipt](../../bench/results/10.176.26.71/tests/rwsem-delegation-20261018/README.md)
records the focused checks for this implementation. The
[API probe](../../tests/kernel/rwsem/README.md) covers sleeping readers,
writer/late-reader exclusion, same-CPU scheduling progress, cancellation,
trylocks, downgrade and drain. Its phase-specific checks keep an outer writer
before publication while an ordinary reader or downgraded writer is active.
Separate strict JIT acceptance checks establish returned bodies through matching
outer-unlock completions; a published `NORMAL` image alone is insufficient.
Native, delegated-capable KD and ordinary local KD shells retain distinct source
and instrumentation identities. Functional and JIT acceptance results do not
establish throughput parity; see the [performance status](../PERFORMANCE.md)
for measured comparisons.

The [previous ordinary-only receipt](../../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
and [archived delegated receipt](../../bench/results/10.176.26.71/tests/rwsem-snapshots-20261015/README.md)
describe their captured implementations. Neither establishes validation or
performance of this admission-phase implementation.
