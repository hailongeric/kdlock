# KD-only mutex with the accepted legacy delegation protocol

The main branch is `master`, selecting KD-only implementation `d2a2304` with
the accepted `555b8b7` compatibility baseline. Immutable tags
`accepted/kd-only-mutex-20261018` and `accepted/kd-mutex-compat-20261017` retain
those measured versions; `current/kd-mutex` follows main. The earlier
owned/adaptive experiment is archived; see [branch dispositions](../history/main-consolidation-20261018.md).

The replacement assumes every user of an object uses KD. Each `struct kd_mutex`
contains physical exclusion and legacy delegation scheduling. There is no Linux
`struct mutex`, address-to-shadow map, or Linux mutex fallback in this path.
Cold calls, admission refusals, task-record shortages, same-CPU predecessor
refusals, nested calls and source closure all retain KD physical exclusion.

## What changes and what stays the same

| Boundary | Accepted baseline `555b8b7` | KD-only implementation |
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
busy reads do not issue locked RMWs. The existing active-combiner gate state (3)
ends retries immediately, so a running batch receives new work promptly. A
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

`struct kd_mutex` is 256 bytes, aligned to 128 bytes in the captured configuration:

| Cacheline | State |
| --- | --- |
| 0 | Physical owner at offset 0, private OSQ, wait-list spinlock and wait list |
| 1 | Delegation executor at offset 64 and gate state at offset 72 |
| 2 | Legacy encoded delegation tail at offset 128 |
| 3 | Exact delegation waiter count at offset 192 |

The first aligned 128-byte region groups physical ownership; the second groups
producer-written tail and waiter counts. This separates those writes from the
physical owner even for adjacent-cacheline prefetch.

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

This changes object layout and requires rebuilding containing structures and every
caller. Casting an existing Linux object, mixing old and new callers, or changing
only a function pointer is invalid. The supported build is the captured x86-64,
non-RT, non-debug-mutex, non-lockdep configuration. RT mutexes and wound/wait mutexes
are separate integration work. No kernel image is rebuilt or installed in this
experiment.

## Validation and measurement boundary

The live ordinary-API probe is
[tests/kernel/mutex/local](../../tests/kernel/mutex/local/kd_mutex_local_probe.c).
It checks 160,000 operations across eight workers, sleeping owners, nested locking,
2,048 initialized objects, interruptible and killable cancellation, I/O state,
trylock and final drain. Unit checks retain compiled/JIT caller execution,
queue-resource failures, terminal retirement, FULL recovery, frame capacity,
immutable images and source leases. Provider and KD workload import audits reject
Linux mutex imports. The provider-lifecycle fixture executes production startup
and teardown with observable service boundaries and injected initialization failures;
it checks that device publication follows private-runtime initialization. These
checks do not establish whole-kernel compatibility.

The c01 comparison uses the unchanged one-cacheline business payload and 64 rounds
of common post-work. The lock's four cachelines are separate from that payload.
For pipebytes n16, Native uses the actual pipe mutex; KD and TCLock each protect the
same redirected FIONREAD business body with their own private lock. The pipe is
private to the controlled cohort; no reads, writes, resize or independent consumer
may run while bound. The KD adapter never uses the native pipe mutex. This tests
the exclusive-KD assumption for the selected object, rather than installing a
kernel-wide mutex replacement.

The [paired performance report](../../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
records fresh accepted-baseline/KD-only pairs, Native and TCLock at 1–8 workers by
one and 12–60 by four, three repetitions, with all samples and failed attempts.
