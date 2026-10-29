# KD-only mutex replacement contract

This is the per-object replacement contract used by stage 1 benchmarks and the
foundation for stage 3 in the [project roadmap](../ROADMAP.md). It does not mean
all Linux mutex objects or call sites have already been replaced. The scoped MM
stage uses local rwsem operations and retains its separate semantic obligations.

The main branch is `master`, retaining the KD physical-ownership foundation
selected at `d2a2304` with the accepted `555b8b7` compatibility baseline. The tags
`accepted/kd-only-mutex-20261018` and `accepted/kd-mutex-compat-20261017` retain
those measured versions. Current code shares preallocated OSQ/delegation node
storage. The total cap and NUMA locality boundary both default to 1024 bodies,
retaining terminal/deferred handoff without an earlier count-based local cutoff. `master` is authoritative;
`current/kd-mutex` retains the earlier `af330db` instruction-exit checkpoint at
this review. The owned/adaptive experiment is archived; see
[branch dispositions](../history/main-consolidation-20261018.md).

The replacement assumes every user of an object uses KD. Each `struct kd_mutex`
contains physical exclusion and the embedded delegation root. The object is
32 bytes with native alignment in the captured configuration. There is no Linux
`struct mutex` backing or Linux mutex fallback in this path.
Cold calls, admission refusals, task-record shortages, same-CPU predecessor
refusals, nested calls and source
closure all retain KD physical exclusion.

This guide owns the object-replacement and ordinary-alias contract. The
[mutex implementation](mutex_implementation.md) explains current acquisition,
queue and release paths; the [lock catalog](../LOCKS.md) compares all four KD
families. The revision comparison below records the KD-only replacement boundary.
Its v4/v5 capability numbers are historical checkpoints, not the current provider
version. Later checked instruction exits and spin helper execution have separate
capabilities and preserve its ownership and retirement obligations. The table
records the original replacement boundary; later storage and batching changes
are described below and in the implementation guide.

## Historical KD-only replacement boundary

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
embedded delegation phase, without a lookup or reference operation. The existing active-combiner
gate state (3) ends retries immediately, so a running batch receives new work promptly. A
lone gate owner (state 1) may finish during the bounded retry window. The state
is only a hint; it never authorizes ownership or retirement. Exhausting eight probes
also enters accepted legacy admission. This uses no worker-count threshold and changes
neither queued ownership nor batch selection. The physical implementation inlines
its small acquisition helpers and uses raw-spin functions for its private wait
list, avoiding the captured kernel's public spin-clobber wrappers.

OSQ and delegation now use the same four preallocated 320-byte node slots per
possible CPU. Each slot contains separate links and notification state for its
two MCS memberships; the physical OSQ and delegation tails remain independent.
An ordinary spinner reserves a temporary slot or uses the existing sleeping
path when none is available. An initial delegation head explicitly lends its
already reserved slot to OSQ during physical acquisition. OSQ cancellation or
unlock completes its unlink or handoff accesses before marking that membership IDLE and
releasing a temporary slot. Borrowed slots keep their delegation reservation.
There is no separate OSQ allocation or new per-object allocation.

All lock and execution services initialize before the control device is
published; shutdown removes that device before releasing runtime storage.
Ordinary OSQ reservations retire before scheduling. Published delegation
waiters still poll while pinned, and their packets and links cannot be removed
by OSQ cancellation. Their physical executor may sleep while acquiring the
mutex, retaining its original reserved node and exact waiter record.

NUMA selection can defer at most 64 fully linked remote requests. The locality
boundary and total cap both default to 1024, removing the earlier count-based
local cutoff. At earlier terminal-link exhaustion, a deferred cohort of eight or
more requests receives handoff with its prefix rejoined first. A smaller prefix
is rejoined and serviced by the current owner, followed by FIFO selection within
the remaining total cap. Refusal, native continuation, early outer release and
source/frame/ACK retirement retain their separate boundaries. This scheduling
change does not expand instruction admission or park published producers.
The user selected 1024/1024 on October 28; the
[implementation guide](mutex_implementation.md#queue-batch-execution-and-recovery)
records that decision and its limits. Earlier measurements at boundaries 256
and 768 remain separate historical evidence; they do not validate the new default.

## Object and API contract

`struct kd_mutex` is 32 bytes, aligned to 8 bytes in the captured configuration,
matching the native `struct mutex` size and alignment:

| Field | Offset | Size |
| --- | ---: | ---: |
| Physical owner (`atomic_long_t`) | 0 | 8 |
| Physical wait lock (`raw_spinlock_t`) | 8 | 4 |
| OSQ (`optimistic_spin_queue`) | 12 | 4 |
| Sleeping ring head (`kd_local_waiter *`) | 16 | 8 |
| Delegation phase (`atomic_t`) | 24 | 4 |
| Encoded delegation tail (`u32`) | 28 | 4 |

The ring head replaces Linux's list sentinel while preserving O(1) append,
removal and cancellation. Internal list representation differs from Linux.
The embedded phase and tail remove the auxiliary hash and shared reference
count entirely. There is no per-object allocation or retirement callback and no
new caller cleanup. The existing task routing and frame/source/ACK lifetimes
remain. See the [implementation guide](mutex_implementation.md#current-storage-and-lookup)
for phase ordering, exact ownership and versioned per-node waiter records.

The selected `d2a2304` object occupied 256 bytes aligned to 128 bytes. The later
hash-based compact layout at `6341999` also required a 16 MiB auxiliary table.
Measurements for both remain specific to those layouts and source identities.

The per-request node remains 320 bytes, with its exact waiter sequence/key at
offsets 88/96, independent OSQ subrecord at 104, packet at offset 128 and
completion/polling bytes at 304/305. OSQ occupies 24 bytes of existing padding;
its CPU/slot identity stays immutable across reuse. The reservation bitmap
and exact per-CPU balances cover both temporary OSQ users and published
delegation nodes. No shared lock reference count, auxiliary hash, registry lock
or RCU mechanism is added.
The diagnostic count verifies a consistent snapshot or returns an explicit
`-EAGAIN`/`-ENOMEM`; hot-path counting needs no shared atomic updates.
Caller-owned object storage must remain alive
until callers, both queues, physical ownership, ACKs and frames have drained.
`kd_mutex_is_idle()` is a checked teardown observation after callers join, not an
admission or lifetime mechanism. `kd_mutex_destroy()` diagnoses a busy object.

[kd_mutex_compat.h](../../include/kd_mutex_compat.h) provides source aliases for
ordinary init/static-init/destroy, lock/unlock, trylock/is-locked,
interruptible/killable/I/O locking, non-lockdep nested forms and
`atomic_dec_and_mutex_lock`. Direct blocking calls use the unified
[`kd_mutex_lock/unlock`](../../include/kd_mutex_api.h) ABI2 macros, backed by
`KD_MUTEX_DIRECT_LOCK/UNLOCK`. The caller supplies one lock argument, with no
cookie or named continuation. Nested translated calls use the same exact lock
ledger as the direct interface. Signal/try/I/O and last-reference acquisitions
stay on the original task; every successful public acquisition can pair with
`kd_mutex_unlock`, which retains native-owner ACK and gate-owner retirement.

The addressable `kd_mutex_lock` C function has the ordinary C ABI and acquires
locally. Taking its address, calling it indirectly, or writing
`(kd_mutex_lock)(lock)` does not establish the caller-clobber contract needed
for delegation. The addressable `kd_mutex_unlock` still performs exact provider
routing. Their declarations use the assembler/export names `kd_mutex_api_lock`
and `kd_mutex_api_unlock`, avoiding the captured kernel's legacy
`kd_mutex_lock/unlock` exports. The source-level API names stay unchanged.
Compatibility aliases map bare function names to these KD functions as
well as mapping direct calls to the macros. Explicit
`kd_mutex_local_lock/unlock` remains available for internal and intentionally
local pairs. The conventional public C entry points are native-only admission
boundaries: the translator does not learn their implementations as critical
section bodies. Supported translated nesting uses the ABI2 direct control
endpoints emitted by the public macros.

The captured non-lockdep initialization spellings also map to KD:
`__mutex_init` uses `__kd_mutex_init`, and `devm_mutex_init` /
`__devm_mutex_init` use their KD counterparts. Name and class-key parameters do
not create lockdep state. `kd_devm_mutex_init` initializes the object before
calling `__kd_devm_mutex_init`, which returns zero without adding a device
cleanup action in the captured non-debug configuration. Neither supplies a new
object-lifetime guarantee.

`guard(kd_mutex)` and `CLASS(kd_mutex, ...)` acquire through the conventional
local lock function. Guard cleanup and `__free(kd_mutex)` use routed public
unlock. The compatibility header explicitly
maps the captured `class_mutex_t`, constructor/destructor and `__free_mutex`
helpers so `guard(mutex)`, `CLASS(mutex, ...)` and `__free(mutex)` remain KD-only.
These cleanup helpers do not establish an ABI2 delegation boundary. They must
not be used to mix existing Linux objects with converted KD objects.

The existing `KD_MUTEX_OUTER_LOCK/UNLOCK` pair remains a separate optimization
with its inline bounded probes and exact acquisition cookie; existing benchmark
shells retain that pair. The unified direct interface uses the provider's
physical fast acquisition and does not claim the outer cookie's routing cost
or its measured performance. Return-valued and task-sensitive controls remain
ineligible for translated execution.
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
non-RT, non-debug-mutex, non-lockdep configuration. The shared public-header
contract refuses RT, debug mutexes, debug lock allocation and lockdep. Wound/wait
mutexes remain separate unvalidated integration work. No kernel image is rebuilt or installed in this
experiment.

## Semantic differences and replacement limits

KD preserves physical mutual exclusion for its own objects, but the public
delegating API is not a universal replacement for Linux `mutex_lock`. The Linux
comparison here is the captured ordinary non-RT mutex implementation. Choosing
local KD execution and authorizing translated execution are separate decisions.

| Property | Linux Native `mutex_lock` | Direct public `kd_mutex_lock` |
| --- | --- | --- |
| Object protocol | Linux `struct mutex` and Linux users | KD `struct kd_mutex`; every user must use KD |
| Body execution | The acquiring task executes its original code | An eligible body may execute on a combiner; the origin resumes after logical unlock on completion |
| Contended waiting | Optimistic spinning followed by sleeping when needed | Local physical acquisition can sleep; published delegation followers poll pinned |
| Ownership and unlock | The acquiring task is the physical owner | The executor can retain physical ownership while an origin resumes a native suffix; public unlock uses exact routing and owner ACKs |
| Caller boundary | Ordinary C ABI | ABI2 continuation capture and compiler-declared clobbers through the public macro |
| Integration | Native kernel configuration and instrumentation | Captured x86-64, non-RT, non-debug-mutex, non-lockdep configuration |

Both APIs require a context in which mutex acquisition may sleep. Neither
permits recursive acquisition of the same object or makes mutex locking valid
in interrupt or atomic context. Physical exclusion and acquire/release ordering
remain required even when a body delegates. The scheduling gate does not grant
physical ownership, and a logical native continuation must not bypass public
unlock routing to release an executor-owned mutex.

### Cases that require retaining native locking

- An existing Linux mutex shared with unconverted callers must retain Linux
  operations. Conversion requires rebuilding and converting the object and all
  its users; equal geometry does not authorize a cast or partial conversion.
- Interfaces that require `struct mutex` or inspect its internal representation
  require explicit porting before they can use a KD object.
- Code relying on lockdep classes or debug-mutex integration cannot assume the
  corresponding behavior from KD. Its non-lockdep nested aliases do not create
  lockdep state.
- RT and wound/wait requirements must retain the appropriate native primitives
  until separately integrated and validated. Ordinary KD mutex is not an
  implementation of those protocols. Whole-kernel replacement remains unvalidated.

### Bodies that must execute locally

Production trusts kernel/module source and does not prove its context, memory,
loop or entry-input safety. That assumption does not switch hardware `current`,
GS, IRQ/RCU, accounting or address-space state to the origin, supply missing
backend support, or permit arbitrary nested lock protocols. See
[translation policy](admission.md) and the [register ABI](../JIT_REGISTER_ABI.md).

When the body's semantics require its original task, use local acquisition on
the fully converted KD object:

```c
kd_mutex_local_lock(&lock);
/* Original code executes on the acquiring task. */
kd_mutex_local_unlock(&lock);
```

Callable `(kd_mutex_lock)(&lock)` also acquires locally and pairs with routed
public unlock. Signal, trylock and I/O forms remain local. This does not make a
Linux object compatible with KD or add unsupported nested/cancellation protocols.
Generic JIT faults are errors; a progressed body cannot restart from entry.

The maintained baseline pins published delegation waiters even though physical
owners and supported service paths may sleep. This branch separately tests the
[bounded selected-group candidate](mutex_implementation.md#bounded-selected-group-candidate-october-29);
its validation is pending. Broad oversubscription and scheduler-independent
starvation freedom remain unvalidated. Bounded NUMA grouping changes service
order without changing exact physical ownership.

## Validation and measurement boundary

The [Linux 7 normal basic checkpoint](../../bench/results/10.176.26.71/tests/linux70-normal-basic-20261028/README.md)
checks the public mutex c01 preset with correct data, matched returned-JIT
counters and final drain. [Current performance](../PERFORMANCE.md) links the
separately frozen nano/API curves and their adverse/local points.

The ordinary API probe in [tests/kernel/mutex/local](../../tests/kernel/mutex/local/README.md)
and affected fixtures cover their declared layout, cancellation, handoff,
queue/storage, ownership, ACK and retirement obligations. Evidence applies to
its recorded source; it does not establish whole-kernel compatibility.

Historical auxiliary registries, object layouts, queue/prefetch trials and
comparisons against the former 256-byte object remain in the
[fixed pre-cleanup contract](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/kd_only_mutex.md#validation-and-measurement-boundary)
and [history index](../history/README.md). Those rates are not current-layout or
Linux 7 measurements.
