# Sleeping KD reader/writer semaphore

The waiting implementation selected in `c21345b` is the KD rwsem baseline.
Its acceptance includes the measured tradeoff: large gains at 60 workers and
substantial regressions at two workers with 20% writes. The
[performance status](../PERFORMANCE.md#accepted-rwsem-implementation-c21345b)
retains those results. This acceptance does not replace the selected KD mutex
protocol or establish support for every Linux reader/writer semaphore use.
The subsequent IRQ-safe reader-release correction at `e6fc371` adds timed
writer-drain rechecks and is included in maintained `master`. A source comparison
at `80f3f1e` confirms that the rwsem implementation, public rwsem headers and mmap
overlay are unchanged since that correction. The historical `c21345b`
measurements predate the correction and do not establish its performance.

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
| [kd_rwsem.h](../../include/kd_rwsem.h) | Public concurrent-reader/ordinary-writer operations on `struct kd_rwsem` |
| [kd_rwsem_types.h](../../include/kd_rwsem_types.h) | Object layout, `DEFINE_KD_RWSEM` and `KD_RWSEM_INITIALIZER` |
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
delegation phase and encoded tail without an auxiliary table. Exact waiter
records occupy reserved queue nodes; provider-wide queues and execution stacks
remain additional storage.
Existing rwsem performance records measure the previous containing layout and
do not establish performance for this refactor. There is no
separate rwsem delegation queue or new generated-code ABI.
The [compact mutex DWARF receipt](../../bench/results/10.176.26.71/tests/mutex32-20261019/layout-dwarf.json)
also records this containing layout from the built provider.

## API and scope

`DEFINE_KD_RWSEM()` and `kd_rwsem_init()` initialize static and dynamic objects.
`kd_down_read()` / `kd_up_read()` permit concurrent, sleeping readers.
`kd_down_write()` / `kd_up_write()` provide exclusive, sleeping ordinary writers.
The `kd_mutex_local_*` calls inside the implementation are the internal physical
writer gate, not an alternative public rwsem API: calling them directly would
bypass reader admission and drain. Explicit writer delegation uses the separate
`kd_rwsem_direct.h` interface described below.
Read and write trylocks return 1 on success and 0 on failure. Interruptible and
killable ordinary acquisitions return zero on success and `-EINTR` on
cancellation, without leaving reader, writer-admission or gate ownership behind.
Killable acquisition ignores nonfatal signals. An immediately available
acquisition may succeed despite a pending signal.

Read trylock and its matching read unlock also support IRQ-disabled or
preemption-disabled contexts without changing the caller's state. In those
atomic contexts they do not sleep, allocate or spin on a lock. Ordinary sleeping
acquisitions and writer operations retain their task-context requirements. The
mmap adapter's public facade and caller-task policy are described in the
[integration guide](../../kernel_integration/mmap_lock/README.md#public-readwrite-api-and-atomic-read-trylock).

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

The final reader's ordered decrement precedes a task-context reader-drain wakeup.
Waitqueue enrolment and condition rechecks ensure a waiter either observes the
completed drain or receives a wakeup. Atomic release omits the synchronous wake;
the writer's timed recheck observes completion. Releasing the last outer reservation
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
finish. A final reader in schedulable context wakes only `reader_drain`; an ordinary phase release
or final outer reservation release wakes only `phase_wait`. Reader drainage
cannot open a closed admission phase. A reader-drain waiter retains its
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
immediately. Admission barriers, exact reservations, cancellation, physical
ownership, static initialization and the 320-byte layout are unchanged.
Keep this validated baseline until measurements justify a safer alternative.
An embedded `irq_work` wakeup would require proof of late-enqueue, cancellation
and object-lifetime safety; it is not a validated replacement for the timed wait.

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
Interruptible and killable acquisitions bypass the 16,384-probe polling stage;
their reader-drain waits use the timed recheck and retain their cancellation
rules. In particular, mmap/munmap's `kd_down_write_killable()` path does not run
that polling loop. Changing its budget would not directly tune those syscalls'
killable admission or reader-drain waits. Wakeups prompt readers to retry their own admission-aware
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

The [conditional instruction probe](../../tests/kernel/jit_escape/README.md)
has a rwsem family using the same outer-writer pair, ABI2 and requirement-1
image as the mutex continuation. It requires returned cold-path bodies, a
validated hot instruction marker, exact native suffix effects, competing
accepted-reader exclusion and final reservation/gate drain. It does not add
delegated reader or nested rwsem control support.

The separate [mmap adapter](../../kernel_integration/mmap_lock/README.md) integrates
the ordinary local API into `mm_struct::mmap_lock` for its documented non-RT,
non-lockdep x86_64 SMP configuration. Linux callers keep the `mmap_*` wrappers;
the adapter selects Native or namespaced KD primitives once per mm before
publication. Readers remain concurrent and local. Native mmap, munmap, advice
and fault algorithms stay unchanged and execute on their original task. The
adapter does not use the explicit outer-writer pair.

Minimal API/lifetime wrappers preserve the acquired-share token and mm reference
for asynchronous non-owner read release. The generic rwsem API does not gain a
non-owner release contract. An observed reader count or idle predicate cannot
replace that exact transfer or stopped/joined users at destruction.

The [corrected-image receipt](../../bench/results/10.176.26.71/tests/mmap-irq-trylock-20261025/README.md)
records 137 Native and 161 KD assertions on actual mm objects in `kdmm31`, with
normal drain and unload. Its 352 standalone assertions and two basic programs
are separate validation classes. They establish the tested API/order/lifetime
cases, not full Linux semantics, fairness, bounded starvation, transitive callback
coverage, whole-kernel substitution, RT or lockdep equivalence. Provider loading
alone also does not establish shared-provider workload or returned-JIT coverage.

The [scoped audit](../../bench/results/10.176.26.71/bench/mmap-perf-prep-20261025/README.md#lock-audit)
records acquisition, rollback, cancellation, downgrade, exact writer ownership
and mmap token/destruction ordering. It found no new demonstrated lock correctness
defect within that scope. It distinguishes the validated one-jiffy tradeoff from
unproved fairness and wakeup-amplification hypotheses; it does not establish
full Native equivalence. The already-authorized one-attempt diagnostic loaded
the unchanged provider, retired it and unloaded normally, without a workload or
JIT-body test. The earlier pre-initialization failure to allocate its 7,592-byte
per-CPU section remains unexplained: capacity, fragmentation and allocator hints
were not isolated. Do not repeat that diagnostic as a prerequisite for the
built-in mmap comparison.

The older 24-session plain/sampled campaign
[stopped at initial admission](../../bench/results/10.176.26.71/bench/mmap-kdmm31-paired-20261025/README.md)
with 73 QEMU tasks versus the required 67, before any boot or payload load. All
24 measured sessions remain unrun. Later quiet observations cannot validate
that failed admission or any rejected timing.

The prospective [shared-mm comparison plan](../../bench/mmap_lock/README.md#plain-throughput-plan)
is the separate `plain-scaling-v1` schema: 21 worker counts, Native/KD and three
paired repetitions, or 126 plain sessions. Its
[41 focused mocked test passes](../../bench/results/10.176.26.71/tests/mmap-scaling-plan-20261026/README.md)
and independent review establish tooling behavior only. The 44 unscored checks,
170 payload cycles and six boots are planning maxima, not live approval.
Current window admission needs 385 full captures; the historical transport
estimate was 259. See the [runner budget](../../bench/mmap_lock/README.md#plain-throughput-plan)
for the worker-policy waits and revised storage/runtime. Counts above 32 span
both guest NUMA nodes; this does not isolate a
NUMA effect. Adjacent repetitions share boots. No expanded case has run.

The earlier 12-session `plain-v1`
[authorized attempt](../../bench/results/10.176.26.71/bench/mmap-plain-v1-20261025/README.md)
consumed one capture and stopped at 68 QEMU tasks versus 67, before any boot or
payload check. All twelve measurements and six unscored checks remain unrun;
that attempt qualified no timing. This failure is separate from the older
73-task stop. Review and idle synchronization of runner inputs remain necessary
before a future separately approved campaign. The workload measures completed
writer mmap/munmap cycles, not isolated lock acquisition, concurrent-reader
scaling or page-fault throughput. New latency sampling is deferred. TCLock has
no equivalent killable/downgrade mmap interface and is not a comparison arm.

The [first 60-second diagnostic attempt](../../bench/results/10.176.26.71/bench/mmap-diagnostic-20261026/README.md)
stopped during initial observation at a 504.396027 ms gap, before any stimulus.
The user subsequently clarified the approximate cadence requirement; the
[diagnostic guide](../../bench/mmap_lock/DIAGNOSTIC.md) tracks its separate
correction and latest execution status. Neither a diagnostic nor a later quiet
observation replaces original benchmark admission or validates rejected timing.
The exact 67-task gate remains unchanged.

The [corrected diagnostic](../../bench/results/10.176.26.71/bench/mmap-diagnostic-corrected-20261026/README.md)
then stopped on a new QEMU task during the guest no-op phase; its checksum phase
did not run. Final health at **01:26:28 on October 26 (Asia/Shanghai)** recorded
recovery `6.1.159-kdclobber2`, boot `d32e2e18-c340-4a98-8105-335bccec0b5d`,
the original 73 modules, taint **12288** and no pending boot. This is time-stamped
saved evidence. Recheck recovery and competing jobs with the active owner before
later live work; preserve the
[reconstruction and recovery inputs](../../kernel_integration/mmap_lock/README.md#reusing-the-corrected-build).

Operation-specific MM body delegation and prepared teardown campaigns are
retired. The historical audits below explain native dependencies and preserve
their captured evidence; they do not authorize resuming those mechanisms.
`access_remote_vm()` and other task-dependent bodies remain on the originating
task. Broader substitution still requires coordinated reader/writer, Linux helper
and lockdep contracts, fault/VMA lifetimes, retry and lock-mode transitions, and
kernel configuration validation.

The retained [native mmap audit](../../bench/results/10.176.26.71/tests/proc-mmap-audit-20261015/README.md)
identifies the following dependencies. Paths and line numbers refer to its
captured kernel inputs, not an independently verified current guest tree.

| Native participant | Branch contract that a replacement must preserve |
| --- | --- |
| `include/linux/mm_types.h:597`, `include/linux/mmap_lock.h:11`, `kernel/fork.c:mm_init` | The object is a native rwsem, with static/dynamic initialization, nested/killable/try acquisition, downgrade, non-owner read release, assertions and contention helpers. Maple tree uses its `dep_map` as an external lock only with `CONFIG_LOCKDEP`; the macro is a no-op in the current configuration. Every participant and its object/layout, initialization and supported lockdep contract must be converted together. |
| `arch/x86/mm/fault.c:do_user_addr_fault` | Fault handling uses `current->mm`, saved registers, IRQ state, signal/accounting context and exception fixups. Capturing an `mm` pointer does not preserve these originating-task requirements or establish sleep eligibility. |
| `mm/memory.c:lock_mm_and_find_vma` | Read trylock can fall back to killable acquisition. Stack growth drops read ownership, acquires write killably, refinds the VMA and downgrades on success; failures return unlocked. `mmap_upgrade_trylock()` always returns false in this capture. Old VMA references cannot survive the drop by assumption. |
| `arch/x86/mm/fault.c:1311`, `__bad_area` | Access-error handling releases the read lock. Signal-pending and `VM_FAULT_COMPLETED` exits are already unlocked. `VM_FAULT_RETRY` reacquires and refinds the VMA; ordinary completion explicitly unlocks. Each implicit release needs one exact ownership/ACK transition, and each retry needs a fresh acquisition. |
| `mm/memory.c:fault_dirty_shared_page`, `__do_fault`, `handle_mm_fault` | Filemap/folio retries, filesystem fault callbacks and userfault handling can drop the lock while allocating, waiting or doing I/O. Complete callback, reference and origin-context proofs are needed. Their internal implementations are not fully retained in this capture. |
| `mm/gup.c:faultin_page`, `__get_user_pages_locked` | `COMPLETED` clears `*locked` and returns `-EAGAIN`. `RETRY` returns `-EBUSY` and clears `*locked` except with `RETRY_NOWAIT`. The wrapper can reacquire killably, then release again to report the interrupted critical section. Return flags alone do not identify ownership; page references, partial progress and VMA invalidation must also be preserved. |
| `mm/gup.c:fixup_user_fault` | Internal `COMPLETED`/`RETRY` paths reacquire the read lock and set `*unlocked`; retries refind the VMA. Returning with the lock held does not mean ownership was uninterrupted. |
| `mm/mmap.c:expand_stack`, `mm/memory.c:__access_remote_vm` | Legacy stack expansion drops read, takes write killably, and returns read-held after downgrade or unlocked on failure. Remote access requires an `mm` reference and must preserve both exits and page references. Its GUP call supplies `locked=NULL`; retry-driven unlock cannot be inferred for that call. |
| `mm/mmap.c:do_mas_align_munmap`, `__vm_munmap`, `brk`; `mm/mremap.c` | Unmapping may downgrade and return `1`, selecting read rather than write unlock. Some stack-growth neighbors suppress downgrade. `vm_munmap()` disables downgrade while the munmap syscall enables it. Current delegated outer writers cannot downgrade; these paths require ordinary ownership or a separately established protocol. |
| `mm/util.c:vm_mmap_pgoff`, `mm/mprotect.c:do_mprotect_pkey`, `kernel/fork.c:dup_mmap`, `fs/proc/task_mmu.c` | mmap/mprotect have killable acquisition, mmap population follows unlock, fork nests old/new-mm write ownership, and proc iteration retains task/mm references across callbacks. Smaps rollup can drop and reacquire on contention. Cancellation, cross-object nesting, post-unlock work and iterator invalidation remain required. |

The x86 fault handler never sets `FAULT_FLAG_RETRY_NOWAIT`; its inference that
`VM_FAULT_RETRY` means unlocked is therefore valid for that caller. Applying the
same inference to GUP would lose the documented NOWAIT exception. Userfault
copying in `__mcopy_atomic()` also releases and reacquires internally, while
returning bytes/errno rather than fault flags. In the newly captured
`handle_userfault()` implementation, the blocking drop path returns `RETRY`
without reacquisition; NOWAIT returns `RETRY` while still held. Its architecture
comment alone does not prove a different branch. A lexical acquisition/release
pair or a retry counter cannot represent these transitions.

The audit was captured on 2026-10-15 against `6.1.159-kdclobber2`, with recorded
live/source Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. A read-only
recheck on 2026-10-20 matched all 25 retained source/configuration files to the
unchanged audit hashes and the baseline manifest to SHA-256
`0f44870efd7ff604067a2436edcfd95ac8c4e413b42e3d534a51e3c011d3d013`.
That configuration enables `LOCK_MM_AND_FIND_VMA`, `USERFAULTFD` and
`PREEMPT_DYNAMIC`; `PROVE_LOCKING` and `DEBUG_LOCK_ALLOC` are disabled.
These historical checks and native syscall probes do not establish KD
mmap/fault execution. The subsequent
[current-source capture and review](../../bench/results/10.176.26.71/tests/mmap-fault-followup-20261020/README.md)
rechecked the live identity and all 25 files, adding 21 callback/helper files.
Its 1,470 archive checks passed and 24 hashed source intervals document implicit
release, NOWAIT, file/context pins, nested resources, retry and downgrade.
Those audited inputs still used native mm lock objects and did not establish
delegated rwsem mode/ownership transitions, origin context or transitive
filesystem/DAX/journal lifetimes. The separate earlier opt-in
[module-owned mapping integration](mmap_fault.md)
passed Native/KD/TCLock functional checks for its private backing state and
originating-task fault transactions. Its native `mm->mmap_lock` remains intact;
that bounded integration does not resolve the full-mm blockers. The existing
fail-closed rwsem-call admission stays intact. Generic fault replay remains
unsupported.

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
