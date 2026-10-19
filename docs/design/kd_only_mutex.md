# KD-only mutex with the accepted legacy delegation protocol

The main branch is `master`, retaining the KD-only protocol selected at `d2a2304` with
the accepted `555b8b7` compatibility baseline. Immutable tags
`accepted/kd-only-mutex-20261018` and `accepted/kd-mutex-compat-20261017` retain
those measured versions. `master` is authoritative for current code;
`current/kd-mutex` retains the earlier `af330db` instruction-exit checkpoint at
this review. The owned/adaptive experiment is archived; see
[branch dispositions](../history/main-consolidation-20261018.md).

The replacement assumes every user of an object uses KD. Each `struct kd_mutex`
contains physical exclusion; an auxiliary record indexed by its address holds
legacy delegation scheduling only while that state is needed. The object is
32 bytes with native alignment in the captured configuration. There is no Linux
`struct mutex` backing or Linux mutex fallback in this path.
Cold calls, admission refusals, task-record shortages, same-CPU predecessor
refusals, auxiliary allocation failures, nested calls and source closure all
retain KD physical exclusion.

This guide owns the object-replacement and ordinary-alias contract. The
[mutex implementation](mutex_implementation.md) explains current acquisition,
queue and release paths; the [lock catalog](../LOCKS.md) compares all four KD
families. The revision comparison below records the KD-only replacement boundary.
Its v4/v5 capability numbers are historical checkpoints, not the current provider
version. Later checked instruction exits and spin helper execution have separate
capabilities and preserve this mutex protocol.

## What changes and what stays the same

| Boundary | Accepted baseline `555b8b7` | KD-only change selected at `d2a2304` |
| --- | --- | --- |
| Physical exclusion | Linux owner word, optimistic spinning and sleeping wait list | KD-owned owner word, private optimistic spin queue and sleeping wait list |
| Scheduling storage | 1,024 resident shadow entries indexed by original address | Legacy gate and queue embedded in each KD object |
| Outer entry | Read guard then zero-owner acquire CAS | Up to eight read-guarded probes of the KD owner word before admission |
| Outer cookie unlock | Linux `mutex_unlock` | `kd_mutex_local_unlock` |
| Queue and batches | Four pinned waiter slots per CPU; bounded NUMA selection; 1,024-body cap | Same queue, polling, slot/stack geometry and batching policy |
| Recovery | Exact task references, FULL state and physical-owner unlock ACKs | Same ownership and retirement obligations, using the KD object's address |
| Translation | ABI2, instruction refusal, immutable images, capability v4 | Same packet/wrapper contract; v5 requires exclusive KD objects (feature bit 4) |
| Publication serialization | Linux mutex | KD local physical mutex |

The physical algorithm derives from the captured Linux 6.1.159 ordinary non-RT
mutex and OSQ algorithms. [Source hashes](../../kernel_module/mutex/linux-source.json)
identify the inputs. [kd_mutex_local.c](../../kernel_module/kd_mutex_local.c)
owns the implementation, including WAITERS=1, HANDOFF=2 and PICKUP=4. Cancellation
is serialized with unlock under the wait-list spinlock; a designated handoff is
picked up before checking signals. Wake queues retain a task reference until wake.
The module uses scheduler services, including I/O accounting, without invoking
Linux mutex APIs.

Outer entry uses a fixed, short probe window to resolve transient clashes before
paying queue-admission costs. Only a zero-owner acquire CAS grants ownership;
busy owner reads do not modify that word. The active-combiner hint reads the
address index inside RCU without taking the bucket writer lock or retaining an
auxiliary pointer. The existing active-combiner gate state (3) ends retries
immediately, so a running batch receives new work promptly. A
lone gate owner (state 1) may finish during the bounded retry window. The state
is only a hint; it never authorizes ownership or retirement. Exhausting eight probes
also enters accepted legacy admission. This uses no worker-count threshold and changes
neither queued ownership nor batch selection. The physical implementation inlines
its small acquisition helpers and uses raw-spin functions for its private wait
list, avoiding the captured kernel's public spin-clobber wrappers.

Private OSQ nodes are allocated per CPU during provider initialization and freed
after drain. This keeps their storage outside the captured kernel's small reserved
module per-CPU arena. All lock and execution services initialize before the control
device is published; shutdown removes that device before freeing the private
runtime. Published delegation waiters still poll while pinned; delegation requests
do not enter the physical sleeping wait list.

## Object and API contract

`struct kd_mutex` is 32 bytes, aligned to 8 bytes in the captured configuration,
matching the native `struct mutex` size and alignment:

| Storage | State |
| --- | --- |
| Embedded object | Physical owner at offset 0, private OSQ and wait-list spinlock, sleeping wait list at offset 16 |
| Auxiliary delegation record | 256 bytes aligned to 128 bytes; lock address, exact references, delegation executor, gate state, legacy encoded tail and exact delegation waiter count |
| Per-request node | Existing per-CPU linked queue node, packet, stack identity and completion state |

Ordinary physical operations need only the embedded object. Delegation creates
an auxiliary record lazily using GFP_ATOMIC allocation and an address-indexed
RCU lookup. A successful lookup acquires an exact atomic reference before leaving
RCU; publication rechecks under the bucket writer lock. Allocation failure takes
the existing local KD fallback before queue publication. It neither changes
physical ownership nor introduces a fixed
number of supported mutex objects. Existing records are shared by concurrent
delegation requests for the same address.

Exact invocation and gate-owner references retain the record through queue
publication, physical ownership, native unlock ACKs and frame retirement. A
scheduling node may retire before its owner's critical section returns, so node
retirement alone cannot release the record. The final transition to zero and
unlink serialize with publication under the bucket writer lock; an RCU reader
cannot revive a zero-reference record. Reclamation waits for an RCU grace period.
Once users and their asynchronous obligations drain, caller storage may be freed
or reinitialized at the same address without another cleanup API. A pending
callback touches only its retired auxiliary allocation, so it does not retain the
caller object or require `kd_mutex_destroy()`. Exact idle membership can precede
callback completion; controlled provider teardown calls `rcu_barrier()` before
destroying the auxiliary slab. See the [implementation guide](mutex_implementation.md#current-storage-and-lookup)
for lookup and final-reference ordering.

The selected `d2a2304` object occupied 256 bytes aligned to 128 bytes, separating
physical ownership and producer writes across four cachelines. Its measurements
remain evidence for that layout. The compact layout reduces embedded storage;
auxiliary allocations and lookup costs are additional, and no performance gain
has been established for this change.

The per-request node remains 320 bytes, with its packet at offset 128 and
completion/polling bytes at 304/305. Caller-owned object storage must remain alive
until callers, both queues, physical ownership, ACKs and frames have drained.
`kd_mutex_is_idle()` is a checked teardown observation after callers join, not an
admission or lifetime mechanism. `kd_mutex_destroy()` diagnoses a busy object.

[kd_mutex_compat.h](../../include/kd_mutex_compat.h) provides source aliases for
ordinary init/static-init/destroy, lock/unlock, trylock/is-locked,
interruptible/killable/I/O locking, non-lockdep nested forms and
`atomic_dec_and_mutex_lock`. Ordinary C aliases execute locally. Explicit
[kd_mutex_direct.h](../../include/kd_mutex_direct.h) clobber callers enable JIT
delegation on the same object; the benchmark retains its accepted outer-cookie
caller shell. Return-valued and task-sensitive APIs stay on the original task.
The translator refuses Linux mutex APIs and the old kernel mutex bridge.

Historical `kd_origin_mutex_*` helper and `mutex_origin_*` observation names are
retained for routing/report compatibility; they now refer to KD physical locking.
Likewise, a native continuation means original compiled code on the producer,
using KD exclusion. It does not mean a Linux Native mutex fallback.

Changing from the previous KD layout requires rebuilding containing structures
and every caller. Matching native size and alignment preserves the corresponding
embedding geometry, but does not permit casting an existing Linux object,
mixing old and new callers, or changing only a function pointer. The supported
build is the captured x86-64,
non-RT, non-debug-mutex, non-lockdep configuration. RT mutexes and wound/wait mutexes
are separate integration work. No kernel image is rebuilt or installed in this
experiment.

## Validation and measurement boundary

The [compact-object validation receipt](../../bench/results/10.176.26.71/tests/mutex32-20261019/README.md)
records the basic and affected VM checks, live delegation and native continuation,
the initial failed attempts, and source/ELF/archive identities. It makes no
performance claim for the changed layout.

The live ordinary-API probe is
[tests/kernel/mutex/local](../../tests/kernel/mutex/local/kd_mutex_local_probe.c).
It checks native size/alignment and containing-structure offsets at compile time,
160,000 operations across eight workers, sleeping owners, nested locking,
2,048 initialized objects reused at the same addresses and freed without destroy,
an empty auxiliary index during ordinary ownership and after drain, interruptible
and killable cancellation, I/O state and trylock.
Unit checks retain compiled/JIT caller execution,
queue-resource failures, terminal retirement, FULL recovery, frame capacity,
immutable images and source leases. Provider and KD workload import audits reject
Linux mutex imports. The provider-lifecycle fixture executes production startup
and teardown with observable service boundaries and injected initialization failures;
it checks that device publication follows private-runtime initialization. These
checks do not establish whole-kernel compatibility.

The historical c01 comparison uses the unchanged one-cacheline business payload
and 64 rounds of common post-work. Its 256-byte lock is separate from that payload;
those results do not measure the current compact object and auxiliary allocation.
For pipebytes n16, Native uses the actual pipe mutex; KD and TCLock each protect the
same redirected FIONREAD business body with their own private lock. The pipe is
private to the controlled cohort; no reads, writes, resize or independent consumer
may run while bound. The KD adapter never uses the native pipe mutex. This tests
the exclusive-KD assumption for the selected object, rather than installing a
kernel-wide mutex replacement.

The [paired performance report](../../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
records fresh accepted-baseline/KD-only pairs, Native and TCLock at 1–8 workers by
one and 12–60 by four, three repetitions, with all samples and failed attempts.
