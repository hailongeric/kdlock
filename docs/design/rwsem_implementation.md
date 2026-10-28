# Sleeping KD reader/writer semaphore

This lock supports stage 1 reader/writer microbenchmarks and stage 2 local mmap
locking in the [project roadmap](../ROADMAP.md). Broader kernel replacement is
the stage 3 objective. The two current uses have distinct execution paths:
explicitly prepared benchmark writers may delegate, while native MM bodies stay local.

The waiting policy selected at `c21345b` and later IRQ-safe release correction
remain the protocol foundation. Ordinary read contention now queues optimistic
admission attempts before the existing sleeping fallback. New writer phases
yield while those readers remain queued. Historical acceptance and regressions
do not qualify current performance. The current Linux 7 shared-MM comparison loses
to Native at all measured counts; [performance](../PERFORMANCE.md) owns those
results and [validation](../VALIDATION.md) owns exact source/check scopes.

[`kd_rwsem_api.h`](../../include/kd_rwsem_api.h) provides one ordinary public
reader/writer name family. Writers remain local until explicit quiescent object
preparation enables delegation for ordinary macro calls. A lock holder can then
execute a waiting writer's protected work through the selected KD-only mutex. A reader/writer semaphore, abbreviated **rwsem**,
allows concurrent readers or one exclusive writer, and blocked callers can sleep.
Before a writer publishes a delegation request, it closes **reader admission**
(permission for new readers to enter) and waits for existing readers to finish,
called **reader drain**. A published mutex waiter then polls with preemption
disabled, so the scheduler cannot pause it in the ordinary way to run another
task on that CPU; this is the **pinned waiter** restriction.
Read bodies always execute on the acquiring task. Queuing a reader's admission
attempt does not delegate its read operation.

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
| [kd_rwsem.h](../../include/kd_rwsem.h) | Callable local acquisition declarations and exact routed release on `struct kd_rwsem`; also used by the generated MM backend |
| [kd_rwsem_types.h](../../include/kd_rwsem_types.h) | Object layout, `DEFINE_KD_RWSEM` and `KD_RWSEM_INITIALIZER` |
| [kd_rwsem.c](../../kernel_module/kd_rwsem.c) | Reader acquisition, queued ordinary-read polling, exact writer reservations, sleeping waits, cancellation, downgrade and idle inspection |
| [kd_rwsem_api.h](../../include/kd_rwsem_api.h), [kd_rwsem_api.c](../../kernel_module/kd_rwsem_api.c) | Ordinary public writer capture, quiescent preparation and origin phase release after exact mutex unlock/ACK |
| [kd_rwsem_compat.h](../../include/kd_rwsem_compat.h) | Native source spellings and cleanup guards for exclusively KD objects; no binary layout or lockdep compatibility |
| [KD mutex implementation](mutex_implementation.md) | Physical writer ownership, legacy delegation queue, generated execution and unlock acknowledgements |
| [direct_rwsem.h](../../workload_modules/rwlock_bench/direct_rwsem.h) | Benchmark caller mapping for Linux Native, ordinary KD and delegation-capable KD |

The October 28 Linux 7 emitted layout retains a 320-byte object with 64-byte
overall alignment. The appended `reader_osq` occupies offset 280 in the final
cacheline, preserving all existing field offsets. The previous 512-byte object had 128-byte alignment;
the
[layout receipt](../../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/object-layout.json)
retains that accepted build's size evidence. Shrinking the embedded mutex changes
the containing layout without changing the rwsem waiting protocol. Current fields
are arranged as follows:

| Field | Offset | Purpose |
| --- | ---: | --- |
| `gate` | 0 | Embedded 32-byte KD mutex; serializes writer bodies |
| `prepared_writes` | 32 | Quiescent, monotonic policy in former padding; never ownership authority |
| `readers` | 64 | Exact reader count, including temporary speculative increments |
| `admission` | 128 | Open, local-writer or prepared-writer phase |
| `phase_wait` | 192 | Sleeping callers waiting for an eligible admission phase |
| `reader_drain` | 256 | Reserved writers waiting for existing readers to finish |
| `reader_osq` | 280 | Abortable queue for optimistic ordinary-read admission; no reader payload runs under it |

The reader count, admission word and two waitqueues start on separate 64-byte
lines. The new queue tail follows `reader_drain` within its region. These offsets do not
describe a Linux rwsem-compatible layout. The embedded mutex now holds its own
delegation phase and encoded tail without an auxiliary table. Exact waiter
records occupy reserved queue nodes; provider-wide queues and execution stacks
remain additional storage.
Existing rwsem performance records measure the previous containing layout and
do not establish performance for this refactor. There is no
separate rwsem delegation queue or new generated-code ABI.
The [compact mutex DWARF receipt](../../bench/results/10.176.26.71/tests/mutex32-20261019/layout-dwarf.json)
also records this containing layout from the built provider.

## API and scope

Include `kd_rwsem_api.h` for the ordinary public family:
`kd_down_read/up_read`, `kd_down_write/up_write`, read/write trylock, read
interruptible/killable and write killable operations, and `kd_downgrade_write`.
`kd_down_write_interruptible` is a KD extension: the target Linux header has no
corresponding writer API. `DEFINE_KD_RWSEM`/`DECLARE_KD_RWSEM`,
`KD_RWSEM_INITIALIZER`, `kd_init_rwsem`, `kd_rwsem_init` and `__kd_init_rwsem`
cover static, ordinary dynamic and named initialization. Initialization requires
a quiescent object and clears prepared mode. Named/class arguments supply no
lockdep integration.

Ordinary `kd_down_write` calls are local by default and permit atomic downgrade
with `kd_downgrade_write`, followed by `kd_up_read`. Callable acquisitions
(`(kd_down_write)(sem)` or a function pointer), trylock, signal and cleanup-guard
acquisitions always remain local, even on a prepared object. Both macro and
callable `kd_up_write` route the exact physical acquisition before retiring its
phase. Mixed macro/callable release is supported; accessing the embedded gate
directly bypasses reader admission and is invalid.

`kd_rwsem_prepare(sem, entry, KD_ENTRY_ABI_MUTEX_CLOBBER_V1)` explicitly enables
writer delegation for that object's ordinary macro calls. Stop and join every
participant before preparation. The function returns `-EBUSY` for an observed
live object; the idle observation is not a concurrent lifetime barrier. Only a
successful source-entry preparation sets the flag, which stays set across local,
signal and trylock operations. There is no concurrent mode switch or disable
API. Prepared ordinary writers must be same-task lexical acquire/release pairs,
must not downgrade and must not acquire inside another translated body. These
are explicit eligibility obligations, not automatically proved properties.
Unprepared ordinary writers retain downgrade; callers requiring it on a prepared
object select callable, signal or trylock local acquisition.

The public macro captures the original caller's continuation. Prepared writers
reserve a positive phase and drain readers before the unchanged mutex DIRECT
ABI2 entry can publish a pinned waiter. The public unlock reaches the mutex JIT
endpoint, then only the resumed origin releases its exact reservation after
physical unlock/ACK. No caller cookie or separate OUTER rwsem API is needed.
Preparation does not promise a returned JIT body. Benchmark sources publish a
named continuation in a `noipa` function for registration and auditing; the
continuation ABI and two-word generated wrapper are unchanged.

Read/write trylocks return 1 on success and 0 on failure. Interruptible and
killable acquisitions return zero on success and `-EINTR` on cancellation without
leaving a reader, phase or gate acquisition. Killable ignores nonfatal signals;
an immediately available acquisition may succeed despite a pending signal.
Prepared ordinary writers cannot cancel after publication; cancellation APIs
remain local. Read trylock and matching unlock preserve IRQ/preemption state in
atomic contexts without sleeping, allocating or acquiring a scheduler lock.
Sleeping acquisitions and writer operations require task context.

Nested and nest-lock annotations match the target non-lockdep aliases: they do
not evaluate the annotation or validate lock ordering. Read non-owner forms
allow an explicitly coordinated task to release a transferred read count; the
caller must retain the object until that release. This is not an automatic
lifetime transfer or permission for writer non-owner release. Read/write cleanup
guards acquire locally, with native-shaped try/intr/kill forms.
`kd_rwsem_is_locked`, `kd_rwsem_is_contended` and held assertions are observations
of KD state, not ownership grants. Contention reports KD wait/queue presence;
it does not reproduce Linux's exact wait-list representation. Speculative reader
counts can make a lock observation true before a reader enters its body.
`kd_rwsem_is_idle` is a KD extension for inspection after all users stop/join;
it cannot replace source/frame retirement.

`kd_rwsem_compat.h` maps the corresponding Native names and guards to these KD
operations when included after Linux headers. Rebuild every containing object
and caller, and use KD storage exclusively. The layout, scheduling/fairness,
lockdep annotations and prepared execution context differ from Native. There is
no reader-to-writer upgrade, arbitrary recursive-read guarantee, IRQ/BH writer
API or translated rwsem nesting ledger. RT/debug/lockdep configurations are
explicitly refused by the shared build contract. Native MM uses only the
local declarations and generated backend; the generator removes delegated phase
helpers and replaces routed unlock with local gate release. It never links the
loadable public API wrapper or opts MM into delegation.

## Who may enter: admission phases

An atomic admission word is independent of the embedded KD physical mutex:

| Admission value | Allowed participants |
| --- | --- |
| `0` | Readers may enter; a writer may reserve admission when no optimistic readers are queued |
| Positive | Exact number of live prepared-writer reservations; no new reader or local writer may enter |
| `-1` | One local writer owns admission; no prepared writer or new reader may enter |

The positive count records exact reservations acquired and released by the prepared
acquisition path. It does not identify the physical executor or replace the mutex's owner,
queue, source lease, result acknowledgement or frame records. An prepared
reservation begins before the KD mutex call and ends only after its matching
unlock returns on the originating task. An origin delayed after unlock therefore
keeps admission closed conservatively.

When admission is zero, local writers and new prepared-writer cohorts defer
while `reader_osq` is nonempty. An prepared writer rechecks that hint after a failed
reservation CAS, because the observed phase may have changed from positive to
zero. Existing positive cohorts still accept exact prepared-writer reservations.
The queue hint grants no ownership: an enqueue can race the check, and the
unchanged reservation RMW and reader-drain barriers still enforce exclusion.
This gives queued readers a chance to enter before another writer phase starts;
every reader acquires its own count and executes its own body.

A reader observes admission open, publishes its reader count with a fully
ordered increment, then rechecks admission with acquire ordering. A failed
speculation rolls back without touching protected data. An ordinary slow reader
queues its optimistic retries, then sleeps when needed; every retry uses the
same admission-aware acquisition on its own task. It cannot bypass a
closed phase by acquiring the physical gate. Speculative reader counts can
briefly appear during a writer phase, but those callers never access the
protected payload.

An prepared writer atomically joins or creates a positive phase, executes the
reader-drain ordering barrier, and waits until existing readers drain. Only
then does it call the unchanged KD mutex DIRECT interface, which may acquire
locally, combine other requests or publish a pinned waiter. All admitted
readers have finished before that publication, and the positive phase prevents
new admitted readers. The reader's ordered increment/recheck and the writer's
reservation/barrier/count check prevent both from missing each other.

The final reader's ordered decrement precedes a task-context reader-drain wakeup.
Waitqueue enrolment and condition rechecks ensure a waiter either observes the
completed drain or receives a wakeup. Atomic release omits the synchronous wake;
the writer's timed recheck observes completion. Releasing the last prepared reservation
reopens admission and wakes phase waiters. Reservation release is outside the
translated region, after the existing mutex unlock endpoint; synthetic
completion resumes there on the origin rather than releasing the reservation
from the executor.

## Waiting and wakeups

Reader counts, admission reservations, and the two waitqueue heads occupy
separate 64-byte-aligned regions. In the recorded accepted x86_64 build, this
increased the object from 384 to 512 bytes; both historical layouts had 128-byte
overall alignment through the former embedded mutex. The compact gate reduced
the containing object to 320 bytes while retaining those separate regions;
the appended read-admission tail targets the spare space after `reader_drain`.
`phase_wait` contains readers and writers waiting for eligible admission,
including writers deferred by the optimistic reader queue. `reader_drain`
contains writers that already hold an ordinary or prepared reservation and wait for readers to
finish. A final reader in schedulable context wakes only `reader_drain`; an ordinary phase release
or final prepared reservation release wakes only `phase_wait`. Emptying the
optimistic reader queue can also enable phase waiters without changing admission.
Reader drainage cannot open a closed admission phase. A reader-drain waiter retains its
reservation, so admission cannot reopen while that wait remains live. Fully
ordered count/phase updates precede the lockless `waitqueue_active()` checks
and pair with waitqueue enrolment and predicate rechecks.

Read trylock's speculative rollback uses the same ordered decrement as read
unlock. IRQ-disabled or preemption-disabled callers cannot enter a waitqueue or
scheduler lock there: they might already hold `rq_lock`. They only decrement.
All reader-drain sleeps therefore recheck the acquire-ordered reader count on a
one-jiffy timeout. The timeout does not acquire ownership or expire a reader;
writers continue sleeping until the count is zero or an applicable signal
cancels the wait. Timer/stack wait storage belongs to the schedulable writer and
is retired before returning. No callback retains the semaphore after read release.
This applies before delegation publication, including positive reservations.
Phase waits keep their ordinary wakeups and do not poll on a timer.

On the captured `HZ=250` configuration a jiffy is 4 ms. This introduces periodic
writer wakeups while readers remain and possible additional wake latency after
an atomic final decrement. Scheduling adds its own delay; there is no new latency
guarantee or performance claim. IRQ-enabled, non-atomic final release still wakes
immediately. Admission barriers, exact reservations, cancellation and physical
ownership remain unchanged. Static and dynamic initialization also clear the
ordinary-read OSQ tail.
Keep this validated baseline until measurements justify a safer alternative.
An embedded `irq_work` wakeup would require proof of late-enqueue, cancellation
and object-lifetime safety; it is not a validated replacement for the timed wait.

An ordinary `kd_down_read()` first tries up to eight reader acquisitions without
queuing, stopping early for rescheduling. This short stage avoids a queue round
trip when a brief writer phase ends. On continued failure, it disables
preemption and reserves one of the existing preallocated
mutex CPU/slot records for `reader_osq`. This uses that slot's independent OSQ
links and exact reservation lifetime; it does not acquire the embedded writer
gate, publish a delegation request or allocate new per-call storage. The queue
head alone retries shared admission while queued callers poll their own nodes.
The head tries at most 16,384 conditions and stops early for `need_resched()`.
OSQ acquisition can also abort when rescheduling is needed or the predecessor's
vCPU is preempted. An unavailable slot skips optimistic polling.

Every success, abort or exhausted poll retires OSQ membership and releases the
slot before enabling preemption. After enabling preemption, an empty OSQ tail
triggers a full memory barrier before the lockless `phase_wait` check and wake.
This orders the release-only tail update against writer enrolment/recheck;
otherwise a writer could remain asleep after the queue became empty. The check
also runs on unsuccessful acquisition paths. A replacement queued reader keeps
writers deferred until a later empty transition. The reader then enters its body
or uses the existing `wait_event()` enrolment/recheck fallback. A reader count is
always acquired by the reader's own task; the queue head cannot grant ownership
to another caller. Read trylock and interruptible/killable read APIs bypass this
queue and retain their existing semantics. A speculative rollback while the
ordinary-read poll is pinned omits the synchronous drain wake, as described
above; the writer's timed drain recheck still guarantees an opportunity to
observe completion.

Uninterruptible writer admission and reader-drain waits retain their existing
polling stages before sleeping. Each stage tries at most 16,384 condition checks
and stops early when the scheduler needs the CPU. Those writer polls occur before
delegation publication with preemption enabled; their finite fallback lets
sleeping or colocated holders resume. A successful
predicate may acquire a reader count or writer reservation, so it is consumed
once without another acquisition attempt. The local writer's read-only
phase check is only a hint; its compare/exchange remains authoritative. The
budget is the accepted tuning for the captured benchmark platform, not a
universal optimum. Earlier measurements of the unqueued policy improved some
60-worker cases but substantially reduced throughput in some two-worker cases.
Those observations do not establish performance for queued reader admission.

The polling bound counts predicate invocations, not elapsed time: the existing
prepared-reservation predicate can retry its compare/exchange internally. The
fallback retains `wait_event()` enrolment, condition rechecks and scheduling.
Interruptible and killable acquisitions bypass the 16,384-probe polling stage;
their reader-drain waits use the timed recheck and retain their cancellation
rules. In particular, mmap/munmap's `kd_down_write_killable()` path does not run
that polling loop. Changing its budget would not directly tune those syscalls'
killable admission or reader-drain waits. Wakeups prompt readers to retry their own admission-aware
acquisition. Published mutex waiters, physical ownership, queue batching and
wrapper ABI are unchanged.

## Local writers, cancellation and downgrade

A local writer atomically changes admission from `0` to `-1`, acquires the
KD physical gate locally, and drains readers while it may sleep. An unavailable
admission phase is itself a sleeping wait. Interruptible/killable acquisition
cancels at an applicable wait without retaining the phase or physical gate.
Failure during reader drainage releases both before reporting `-EINTR`.

Local unlock releases the KD physical gate before reopening admission.
Downgrade publishes its reader count while it still owns both `-1` admission
and the physical gate, then releases the gate and reopens admission. A following
prepared writer must reserve admission and drain this reader before publication.
An existing positive phase excludes local ownership, so a local writer
can never introduce a downgraded reader behind already-pinned prepared writers.

Prepared ordinary macro acquisition does not downgrade because other writers in its positive phase
may already have published pinned requests. Introducing a reader at that point
would violate their reader-free admission guarantee and could prevent that
reader from resuming on a pinned CPU. Cancelling a published request would also
require changing the selected mutex's queue and source/frame lifetime protocol.
Keeping those operations on local acquisitions preserves both contracts.

This construction preserves a live prepared-writer cohort: new prepared writers may
join a positive phase while readers or local writers wait. New phases yield
to queued optimistic readers, but this does not port Linux rwsem's reader
batching or fairness policy. Sustained prepared-writer arrivals can still delay
those waiters. It does not guarantee starvation freedom, bounded waiting or
improved throughput. The selected mutex's general oversubscription
limitations remain separate from the rwsem reader-drain solution.

## Mmap and validation boundaries

The [Linux 7 mmap adapter](../../kernel_integration/linux70/MMAP.md) uses ordinary
local KD readers/writers behind Linux's `mmap_*` wrappers. It selects one backend
per mm before publication; native MM algorithms execute on their original task.
It never enables prepared writer delegation. Minimal wrappers retain exact
read-share tokens and mm references for asynchronous read release; an observed
reader count cannot replace that lifetime transfer.

Normal `kdlock1` disables this adapter. The separate enabled `kdmm1` image has
Native/KD schema-2 identities, fresh API/lifetime/mapping/fault prerequisites and
42 completed exploratory shared-MM timings. The
[checkpoint](../../bench/results/10.176.26.71/tests/linux70-kdmm1-20261027/README.md)
retains the initial failed contention witness and later diagnostic separately.
The current queued-reader preference does not qualify those frozen MM results.
Correctness does not establish fairness, full Linux equivalence, performance
parity, whole-kernel support or automatic non-owner lifetime transfer. RT and
lockdep configurations are explicitly excluded.

The [instruction-exit probe](../../tests/kernel/jit_escape/README.md) has a separate
prepared local-writer ABI2 family. Its returned cold bodies, hot native suffix, exclusion
and drain are distinct from the local actual-MM backend. Production source trust
changes no reader-drain, ownership, ACK or reservation-release requirement.

The archived owned-mutex rwsem design is not interchangeable: prepared writers must
reserve admission and drain readers before publication, and retain their exact
reservation through the origin's final release. Do not restore Linux mutex
backing, parked producers or operation-specific MM delegation. Older kernel
line audits, fault proposals and stopped campaign plans remain in the
[fixed pre-cleanup guide](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/rwsem_implementation.md#mmap-and-validation-boundaries)
and [history](../history/README.md).
