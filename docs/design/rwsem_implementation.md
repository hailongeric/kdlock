# Sleeping KD reader/writer semaphore

KD rwsem provides concurrent local readers and one selected writer around a
KD-owned physical gate. Ordinary objects and callable APIs execute locally.
Explicit quiescent preparation enables retained continuation capture for the
public writer macros, including interruptible and killable forms. The selected
request must acquire its real gate and freshly drain readers before its body
can run; publication alone grants neither ownership nor reader-free execution.

The ordinary read APIs remain local. A read tail reached by a proxied writer's
downgrade has a separate retained-writer contract described below. This is
current implementation behavior, not the proposed general lock redesign.
[Performance](../PERFORMANCE.md) and [validation](../VALIDATION.md) separate
source-specific results from correctness and broader replacement claims.

## Source and object layout

| Source | Responsibility |
| --- | --- |
| [kd_rwsem.h](../../include/kd_rwsem.h) | Callable APIs, exact routed releases and inspection |
| [kd_rwsem_types.h](../../include/kd_rwsem_types.h) | Object layout and static initialization |
| [kd_rwsem.c](../../kernel_module/kd_rwsem.c) | Local readers/writers, condition channels, trylock, real downgrade and final read decrement |
| [kd_rwsem_api.h](../../include/kd_rwsem_api.h), [kd_rwsem_api.c](../../kernel_module/kd_rwsem_api.c) | Public macro capture, quiescent preparation and typed release entry |
| [kd_admission.h](../../include/kd_admission.h), [kd_admission.c](../../kernel_module/kd_admission.c) | Canonical writer selection, actual readiness, cancellation, phase and read-tail custody |
| [kd_wait_queue.h](../../include/kd_wait_queue.h), [kd_wait_queue.c](../../kernel_module/kd_wait_queue.c) | Shared request states, memberships, selection, cleanup and acknowledgement ordering |
| [kd_service.c](../../kernel_module/kd_service.c) | Retained execution, typed controls and exact native release routing |
| [kd_rwsem_provider.c](../../kernel_module/kd_rwsem_provider.c) | Explicit per-object provider preparation, binding and activation |
| [kd_rwsem_compat.h](../../include/kd_rwsem_compat.h) | Native source spellings and cleanup guards for exclusively KD objects |

Source assertions retain a 320-byte object with the following offsets. This is
KD storage, not a Linux rwsem-compatible layout:

| Field | Offset | Purpose |
| --- | ---: | --- |
| `gate` | 0 | Embedded 32-byte KD mutex and shared acquisition guard/queue |
| `prepared_writes` | 32 | Quiescent capture policy; never ownership authority |
| `selected_kind` | 36 | No phase, retained admission or local owner |
| `selected_owner` | 40 | Exact selected physical task |
| `selected_identity` | 48 | Exact acquisition identity |
| `phase_generation` | 56 | Distinguishes successive selected phases |
| `readers` | 64 | Real reader credits, including speculative increments |
| `admission` | 128 | Open `0` or selected writer `-1` |
| `phase_wait` | 192 | Admission-condition memberships and queued local-reader count |
| `reader_drain` | 256 | Selected writer waiting for real readers to finish |
| `reader_osq` | 280 | Abortable optimistic reader admission; never reader-body delegation |

The condition heads use `gate.wait_lock`; they are not independent physical
owners. The separately aligned counters/conditions and preallocated reader OSQ
slots remain. Exact request, source, image and execution storage is additional.
The earlier [layout receipt](../../bench/results/10.176.26.71/tests/mutex32-20261019/layout-dwarf.json)
and [older object comparison](../../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/object-layout.json)
retain their own build identities; their measurements do not qualify later
protocols or the merged runtime.

## API and scope

Include `kd_rwsem_api.h` for the ordinary public family. Initialization requires
a quiescent object and clears preparation, selected metadata, counters and queue
heads. Static, dynamic and named initialization remain available; name/class
arguments add no lockdep integration.

| Acquisition form | Route |
| --- | --- |
| `kd_down_read`, read signal/try/non-owner forms | Local reader admission and a real reader credit |
| Unprepared `kd_down_write`, `_interruptible`, `_killable` macros | Local selected-writer admission |
| Explicitly prepared writer macros above | Retained capture through `kd_service_capture`, subject to eligibility and resource/context checks |
| Callable writer functions, function pointers and cleanup constructors | Conventional local C acquisition, including on prepared objects |
| Write trylock | Bounded local attempt; no publication, allocation or sleeping |

`kd_down_write_interruptible` remains a KD extension: the target Linux rwsem
writer API has a killable form but no corresponding interruptible form.
Read/write trylocks return 1 on success and 0 on failure. Signalable calls return
0 after actual acquisition or `-EINTR` after applicable cancellation and exact
cleanup. Killable waits ignore nonfatal signals. Nested/nest-lock annotations
preserve the supported non-lockdep aliases without evaluating annotations.

`kd_rwsem_prepare(sem, entry, KD_ENTRY_ABI_MUTEX_CLOBBER_V1)` registers the source
entry before enabling capture. Stop and join all participants first. Invalid
arguments/ABI return `-EINVAL`; an observed live object returns `-EBUSY`.
The idle check is not a concurrent lifetime barrier. Preparation is monotonic
until quiescent reinitialization and does not guarantee that any request will
be delegated or return through JIT. Callable/try/cleanup uses still participate
in the same object's admission protocol.

Prepared signalable macros use the retained integer-result entry; they are not
blanket local fallbacks. Their original task supplies the signal predicate.
Actual readiness wins the grant-versus-signal election; selection, mutex PICKUP,
an image or a zero-reader observation from an earlier phase is insufficient.
Before commitment, cancellation must unlink the request and finish its exact
tentative physical/phase cleanup before CANCEL_ACK. After commitment, later
preparation or execution work cannot turn the acquisition into `-EINTR`.

Both macro and callable releases route the exact successful acquisition. Never
operate on `sem->gate` independently or infer owner authority from `admission`
alone. Ordinary non-owner read release permits an explicitly transferred real
credit with retained object lifetime; it does not transfer a proxy writer or
permit writer non-owner release. Cleanup guards acquire locally. Inspection
and held assertions report state/hints, not acquisition or caller ownership.
`kd_rwsem_is_idle` is for inspection after users stop/join, not retirement.

All participants must use one object protocol. Rebuild containing objects and
callers for the KD source aliases. No binary-layout, lockdep, reader-to-writer
upgrade, arbitrary recursive-read or general IRQ/BH writer support is implied.
RT/debug/lockdep exclusions remain those of the shared build contract.

## Who may enter: admission phases

There is no positive prepared-writer cohort. The atomic admission word has only
two valid states:

| Value | Meaning |
| --- | --- |
| `0` | Local readers may acquire; no selected writer phase is closed |
| `-1` | One exact selected writer phase closes new reader admission |

Every blocking writer uses the canonical acquisition queue. Its selected
physical task obtains the real gate, then waits for already linked local-reader
condition memberships to acquire or cancel while admission remains open.
Only then does it establish a fresh `0 -> -1` phase with exact kind, owner,
acquisition identity and generation, and drain real reader credits with the
required ordering. Only actual gate ownership,
matching phase and a fresh zero-reader check commit the acquisition. A queued
writer carries no phase reservation or reusable reader-drain result.
Trylock uses bounded request/gate/phase checks without publishing a queue node.

Local calls transfer successful custody from their temporary stack admission
to the object's LOCAL owner record before retiring that descriptor. Retained
capture keeps the canonical admission through physical release and its ACK.
These are distinct lifetime routes through the same readiness protocol.

A reader checks open admission, publishes its credit with a fully ordered
increment and rechecks admission with acquire ordering. A failed speculation
rolls back before accessing the critical-section body. Temporary speculative
counts can overlap a closed phase without granting a reader entry. A queued
reader still acquires its own credit and runs its own body.

Release retains `-1` until exact physical release has completed. Metadata and
wake references are prepared under the object guard; reopening admission is
the final object RMW. A subsequent writer performs its own selection and reader
drain. Request generations and owner records, not a counter or queue hint,
determine which acquisition may release.

## Waiting and wakeups

Ordinary `kd_down_read` first makes up to eight success-first attempts, stopping
for rescheduling. Continued contention uses the existing preallocated mutex
CPU/slot storage for an abortable reader OSQ membership. Only its head retries
shared admission, for at most 16,384 conditions or until rescheduling is needed.
The temporary CPU pin and slot end before the read body or sleeping fallback.
No reader payload is published or delegated through this queue.

Reader condition fallback uses a short-lived stack request protected by
`gate.wait_lock`. Its membership and `phase_wait.readers_waiting` count retire
before returning. Condition wake collection retains task references, not stale
stack-node pointers. Emptying the optimistic reader queue performs the ordering
barrier and condition notification after dropping its slot/pin.

Local writers use `kd_admission_wait`: success-first readiness and the original
task's signal predicate, bounded 16,384-probe polling, scheduler checks and
one-jiffy rechecks. Signalable writers use this common election too; a pending
signal stops optimistic polling, while only the call's signal class cancels.
Retained transport has its own service/wait coordination around the same exact
admission decision. The budgets are implementation bounds, not latency or
fairness guarantees.

An ordinary public `kd_up_read` finishes with the ordered reader decrement and
performs no later object access or deferred notification. This applies even in
ordinary task context: the final credit can permit immediate object retirement.
The proxy route is checked first and consumes no anonymous reader count.
Internal speculative rollback remains separate. Writer reader-drain waits use
timed rechecks, so an atomic/IRQ-disabled final decrement needs no scheduler or
queue lock. Reader phase-condition fallback also rechecks on a one-jiffy timer
for the interval between wake collection and the final phase-opening RMW.

A timer only prompts another real predicate check; it neither grants ownership
nor expires a reader. At recorded `HZ=250`, a jiffy is 4 ms, with additional
scheduler delay possible. No starvation freedom, bounded wait or Native fairness
identity is established. A deferred wake mechanism would need its own exact
object-lifetime and cancellation proof.

## Local writers, cancellation and downgrade

Ordinary local downgrade publishes a real reader credit while the caller still
owns its physical writer and `-1` phase, then releases the gate and reopens
admission. A following writer freshly selects and drains that read credit.
Local read release keeps the allocation/guard/scheduling-free final decrement.

A typed downgrade actually consumed by a JIT proxy is different. It changes the
logical acquisition to read mode while retaining the same physical writer gate
and selected `-1` phase. It creates no real reader credit and does not admit
unrelated readers or another writer. The same bound image can continue at the
real post-CALL source position; surrounding MM operations are not skipped.
Its matching typed read release consumes that retained writer exactly once,
with physical/phase ACKs before completion.

If an uncompiled instruction hands back after proxy downgrade, the executor
retains that writer while the original logical task runs the exact unfinished
suffix. Its typed `UP_READ` waits for the executor's physical release and ACK.
This proxy final-release route supports the same logical task in ordinary task
context, not IRQ-off, preemption-disabled, borrowed spin/preempt/RCU intervals
or cross-task non-owner release. Genuine real-credit read APIs keep their own
ordinary atomic-context contract.

If handback occurs before downgrade, the later native downgrade keeps its real
reader-credit route: publish the credit, release writer/phase and transfer that
credit to native custody. Never substitute a reader decrement for proxy writer
release or consume a real credit twice. The [execution flow](../JIT_EXECUTION.md#batch-execution-and-return)
owns the compiler release-boundary exception and exact CALL/RET/handback rules;
[frames](frames.md) and [lifetimes](lifetimes.md) own final-user retention.

## Mmap and validation boundaries

The [Linux 7 adapter](../../kernel_integration/linux70/MMAP.md) keeps native MM
source bodies and algorithms unchanged and selects one backend per mm before
publication. Its generated local backend does not link the loadable
`kd_rwsem_api.c` macro wrapper. Explicit generic provider preparation/binding
and activation are a separate opt-in route; loading a provider alone does not
enable delegation. Read acquisition remains local. Minimal MM wrappers retain
exact tokens/mm references for asynchronous real-reader release.

Normal `kdlock1` disables MM replacement. Enabled kernel/profile identities,
source, provider activation and actual API path must all be recorded. Historical
[local-MM checks and timings](../../bench/results/10.176.26.71/tests/linux70-kdmm1-20261027/README.md)
are distinct from later generic retained execution. The
[proxy-read campaign](../../bench/results/10.176.26.71/bench/mmap1-proxy-read-7e3c90b4-v3/README.md)
records a stable counter-enabled mmap1 point and complete whole-application
returns for both selected roots. It does not identify a particular consumed
downgrade branch, establish quiet/Native performance gain or validate the later
merged runtime combination. Original failed campaigns and exact cleanup remain
separate receipts. This documentation edit supplies no new execution evidence.

Preserve source/image leases, exact owners, cancellation, acquisition results,
release ACKs and final-user retirement. Do not restore Linux lock backing,
positive prepared cohorts or operation-specific MM body delegation. Historical
protocols and promotion decisions remain in their fixed source/result records
and the [history index](../history/README.md).
