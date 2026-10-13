# Mutex implementation: KD, TCLock and Linux Native

Read [lock protocols](lock_protocols.md) for the algorithm/ownership comparison
and [KD locking](locking.md#5-mutex-delegation-protocol) for nested owner/ACK
details. This page maps the current ordinary mutex paths to their data and
source. [Spin implementation](spin_implementation.md) owns the shared wrapper,
code-pool and spin-continuation geometry; those allocations are not duplicated
per mutex request.

## Source and call paths

| Arm | Workload entry | Backend implementation |
| --- | --- | --- |
| Native | `(mutex_lock)` / `(mutex_unlock)` | Captured kernel `kernel/locking/mutex.c`, `include/linux/mutex.h` |
| TCLock | `komb_mutex_lock` / `komb_mutex_unlock` | [komb_mutex.c](../../tclock_backend/komb_mutex.c), [combiner.c](../../tclock_backend/combiner.c), [mutex_provider.c](../../tclock_backend/mutex_provider.c) |
| KD outer | `KD_MUTEX_OUTER_LOCK/UNLOCK` | [kd_mutex_direct.h](../../include/kd_mutex_direct.h), [mutex_calls.inc](../../kernel_module/lock/mutex_calls.inc) |
| KD general/nested | `KD_MUTEX_DIRECT_LOCK/UNLOCK` and retained bridge endpoints | Same routing file, [kd_mutex.c](../../kernel_module/kd_mutex.c), [native.inc](../../kernel_module/execution/native.inc) |
| KD owned outer | `KD_OWNED_MUTEX_OUTER_LOCK/UNLOCK` | [kd_owned_mutex_direct.h](../../include/kd_owned_mutex_direct.h), [owned core](../../kernel_module/owned_mutex/core.c), [delegation](../../kernel_module/owned_mutex/delegation.c) |
| KD owned ordinary/nested | `kd_mutex_lock/unlock`, `KD_OWNED_MUTEX_DIRECT_LOCK/UNLOCK` | Owned SELF core; translated nested calls use [owned_mutex_calls.inc](../../kernel_module/lock/owned_mutex_calls.inc) |

The benchmark arms use distinct compiled functions in
[mutex_cacheline/module.c](../../workload_modules/mutex_cacheline/module.c).
The mutex translation unit reuses payload, ioctl runner and timing sources;
there is no per-operation runtime `is_mutex` branch. Measurement runs through
[run_mutex.py](../../bench/tclock_compare/run_mutex.py), sharing reporting with
the spin runner. Registration and final context drain are outside measurement.

The existing kernel build is `/root/linux-6.1.159-kdclobber2` in the guest. Its
release, configuration, source/interface hashes and live Build ID are checked
by the [kernel identity verifier](../../bench/spin_cacheline/kernel_identity.py)
against the [captured baseline](../../kernel_baseline/README.md). Native source
paths above refer to that build, not to a second Linux implementation in this
repository.

## Linux Native implementation

`struct mutex` contains `owner`, `wait_lock`, an optimistic spin queue when
configured, and `wait_list`. With the captured configuration it is 32 bytes;
debug/RT configurations change the layout and implementation. Owner low bits
are WAITERS=1, HANDOFF=2, PICKUP=4; pointer comparisons mask all three.

The original lock function's successful owner CAS returns directly. Its
slowpath first retries acquisition and optimistic spinning, then installs a
stack `mutex_waiter` under `wait_lock`. Sleep state publication, rechecking
ownership and wait-list insertion prevent a missing unlock wake. A first
waiter can request handoff instead of repeatedly losing to a fresh contender.
The unlock slowpath preserves flagged state, prepares a wake queue and
performs handoff when requested; the receiving task consumes PICKUP with
acquire ordering.

The Native arm deliberately parenthesizes function names to bypass the
experimental caller-clobber macros. No KD selector is installed, so it reaches
the original Linux algorithm. It does not allocate a KD task record/shadow,
use a JIT frame, or move to a TCLock shadow stack.

## TCLock implementation

The fixed upstream source is commit
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`, retained byte-for-byte in
[upstream](../../tclock_backend/upstream/) with hashes in
[UPSTREAM.json](../../tclock_backend/UPSTREAM.json). The external module
replaces custom `task_struct` fields with
[tc_mutex_context](../../tclock_backend/mutex_compat.h). It retains ordinary
mutex parking, wakeup, NUMA selection and real stack switching. The provenance
and build boundary are in the [backend README](../../tclock_backend/README.md).

| Storage | Location and purpose |
| --- | --- |
| `komb_mutex` | 24 bytes; workload-owned pointer tail, state/locked byte and combiner task; no original Linux mutex owner |
| `tc_mutex_context` | 336 bytes, preallocated per possible CPU on its preferred NUMA node; registered task, stack pointer, waiter links, lock-address stack, batch counter, observations and embedded node |
| `komb_mutex_node` | 160 bytes embedded in that context; next/task/lock, CPU/socket, real RSP and completion/locked notification |
| Shadow stack | 8 KiB per possible CPU, NUMA-local allocation with allocator fallback; retained until controlled backend unload |
| Native context | Six callee-saved GPRs plus CALL return address on existing task/shadow stacks; no KD register packet or software frame |

These sizes are verified from the cleanup's guest-built DWARF. The node starts
at context offset 176; its completion/locked bytes are at node offsets 136/137.
The type has no KD-style 64-byte alignment/whole-line stride requirement.
Allocator overhead, alignment and existing task stacks are separate from
`sizeof`, and object geometry does not measure cache misses.

`tc_mutex_worker_register()` requires single-CPU affinity and an unused
context, takes a task reference, and binds the context before workers report
ready. `tc_mutex_task(task)` looks up by `task_cpu(task)`; registration and
fixed affinity are part of its correctness contract, not approximate
profiling information. Only ordinary operations on registered workers are
supported. Interruptible/killable/IO, rwsem and general unregistered kernel
callers are not ported APIs.

`komb_mutex_lock()` CASes the locked byte. On failure it disables preemption,
sets node CPU/socket/task identity, and enters `__komb_mutex_lock()`. The
assembly saves six GPRs, records RSP through the original implicit helper
CALLs, switches to the context shadow stack and calls the queue slowpath.
That slowpath exchanges `lock->tail`, links behind the predecessor and waits
on the node. Parking/scheduling follows the state machine in
[the protocol](lock_protocols.md#tclock-mutex); it is not a Linux mutex wait-list
implementation.

A queue head obtains the gate. A terminal follower with no successor is
handed physical control; otherwise the combiner records `combiner_task` and
calls `execute_cs()`. `komb_context_switch()` moves physical RSP to the
waiter's native acquisition return. On delegated unlock, WWJUMP records the
waiter's post-unlock RSP and either switches directly to the next eligible
waiter or returns to the combiner. Previous waiter completion is published
only after its stack is no longer executing. Out-of-order state/lock-address
handling remains in the port but does not expand the comparator's single-lock
validation scope.

NUMA selection walks linked successors, defers remote nodes in the context
list and rejoins that list before physical handoff. The default WWJUMP value
1024 is checked against a counter starting at zero, allowing 1025 bodies.
There is no separate KD-style scan limit. Selected waiter stacks receive six
`prefetchw` hints at saved RSP through RSP+320, plus a successor-node hint.
Switching stacks does not switch hardware task/GS identity.

`parks` counts actual successful parking transitions. `batches` and
`delegated` update once after a returned batch, using `counter_val + 1`.
Whole-session deltas prove delegation but do not identify the selected
300 ms peak's delegation share. They are observational values; context
lifetime is checked independently.

`tc_mutex_workers_drain()` requires all workers to have exited and the lock,
queue, saved waiter links, lock-address stack and shadow stack pointer to be
idle. A still-live exiting task yields EBUSY for a bounded retry outside
measurement. Only after cohort drain are task references released. Backend
unload frees preallocated contexts/stacks; no forced context release is used.

## KD-owned implementation (experimental)

`owned-v1` is a separate object protocol. It ports ordinary non-RT Linux
6.1.159 owner spinning, OSQ, sleeping and owner flags into KD, with exact captured
source hashes and port boundaries in [linux-source.json](../../kernel_module/owned_mutex/linux-source.json).
The owned target never enters `mutex_lock`, `mutex_unlock`, their slowpaths or
the legacy shadow gate. Linux mutexes used elsewhere by provider control code
remain unrelated objects. Existing kernel-owned objects continue using the
explicit legacy interface; an owned object cannot mix callers from either API.

[kd_mutex.h](../../include/kd_mutex.h) statically checks size, alignment and
every field offset against the captured Linux type: 32 bytes, alignment 8,
owner at 0, wait lock at 8, OSQ at 12 and wait list at 16. This matches object
geometry, not measured cache behavior. Unsupported RT/debug layouts fail the
build. The old internal shadow-gate type is now `kd_mutex_legacy_gate` in
[kd_mutex_legacy.h](../../include/kd_mutex_legacy.h).

The whole owner word is the sole ownership authority. WAITERS=1, HANDOFF=2 and
PICKUP=4 retain acquire/release ordering. One FIFO under `wait_lock` contains
tagged SELF and DELEGATE waiters; each starts with the same 40-byte private
header. This header is outside the public 32-byte mutex object. Cold, ineligible
and resource-refused outer acquisitions use KD's
optimistic SELF core. The OSQ head competes for a running owner; a waiter
sleeps if spinning cannot make progress. Ordinary SELF release permits barging
until handoff is requested. A delegated head receives directed PICKUP when it
cannot execute. Publication retries acquisition after setting WAITERS, covering
a fast owner release between the first retry and waiter insertion.

A single outcome word reports QUEUED, GRANTED, COMPLETE or FULL. SELF waiters
use their stack header's inline state; delegation packets point to their result
cacheline, away from the FIFO links. A directed delegated grant captures the
wake task reference and unlinks the packet under `wait_lock`, publishes the
exact task owner with PICKUP, then release-publishes GRANTED as its last packet
access. The producer consumes only its own PICKUP with an acquire CAS, without
retaking `wait_lock`. Concurrent WAITERS updates are preserved by the CAS retry.
Stack SELF waiters retain removal under `wait_lock`. Completion and FULL also
retire their packet ownership before publishing the same outcome word.

The outer cookie is an explicit outermost acquisition interface. Its successful
inline CAS records an approximate entry observation and a nonzero physical-owner
cookie. A failed attempt records one contention under a short pin, then uses
independent CPU and exact-address heat. `owned_mutex_entry_ratio_limit` is a
read-only power of two from 2 through 256, default 256; cadence remains 1,024
contentions, strict `(entries >> 10) < limit`, then 1,025 exact-address records.
Cold CPUs avoid table work between comparisons. No policy uses worker count.
`owned_mutex_self_route` is a diagnostic control, not a Linux fallback.

By default, a failed inline probe enters the original ABI2 capture endpoint,
which records the failed attempt exactly once before delegation admission.
`KD_OWNED_MUTEX_PREFLIGHT=1` is an optional caller build choice. It instead calls
an ordinary C-ABI gate to make that observation before capture. A cold caller
acquires through the owned SELF core there. The default caller emits no gate
call and reads no runtime preflight policy. Both entry symbols coexist in the
provider: the opt-in capture calls `kd_owned_mutex_outer_prepared_clobber_v1`,
which does not sample again; the original contended endpoint retains sampling. An admitted caller may first retry with
`owned_mutex_preflight_spins` (0, 64, 256, 1,024 or 4,096; default 0). The
optimistic candidate competes only as OSQ head, checks the running owner and
rescheduling state, and releases OSQ before returning. The separate opt-in
`owned_mutex_preflight_queue` joins an occupied OSQ and shares the budget between
queue observations and owner polling. On expiry it completes the existing OSQ
cancellation protocol; a racing grant must still be unlocked. Existing SELF
spinners retain their unbounded OSQ entry. The budget limits deliberate polling,
not required cancellation, successor publication or elapsed time. An admitted
BUSY result permits capture, but conveys no eligibility lease. Source, command
and active-task eligibility are checked once at prepared entry, before task
references, registration, packet reservation or publication. A refusal acquires
SELF and returns the physical-owner cookie; sampling is not repeated. No task
reference, packet or OSQ lease crosses the C preflight boundary. The compiler
may still spill callee-saved registers for the function's clobber branch.
The gate and both return-valued capture endpoints are outer-only controls and
are rejected inside translated bodies. Compiled caller identity distinguishes
capture-first from C-gate budget zero; neither is inferred from worker count.
The intermediate experimental caller that paired a gate with the old endpoint
must not be reused with this provider; replace the complete caller/provider/JIT
session, retaining archived binaries with their matching frozen sources.

Ordinary and direct clobber calls are nestable SELF controls on their caller.
When translated, the dispatcher acquires/releases them through the exact frame
ledger. Their native acquisitions retain a task-local held count and one cached
task reference until the count drains. This prevents an early A unlock from
combining while its own native continuation still holds B: executing another
A body that takes B at that point would deadlock. Tracking exhaustion keeps
SELF acquisition available and disables new owned batches until unload;
existing tracked depths and published requests still drain. The outer cookie
does not pay for this ordinary/nested acquisition record.

Ordinary unlock never starts a batch, including when its tracked depth reaches
zero: an explicit outer acquisition may still be held outside that record.
It releases or hands off through the SELF core and retains borrower ACK routing.
Only explicit outer unlock can combine. This also prevents B's unlock from
executing a B waiter that needs the caller's still-held outer A.

Combining starts on explicit outer unlock, after the physical owner's own body. A combiner
reserves its independent executor stack and source/task references, then detaches
one finite FIFO snapshot while retaining owner and WAITERS. It executes only
the leading delegates, stops at SELF, handoff, reschedule, refusal, FULL/native
continuation, early release or the 1,024-body cap, and does not refill or reorder
by NUMA node. Unstarted requests rejoin ahead of newer arrivals. Atomic/IRQ-off
unlock and an occupied executor use the owned release/handoff path.

The opt-in `owned_mutex_refill=1` experiment amortizes executor setup over further
FIFO snapshots. Only an exhausted private prefix can refill; deferred wakes are
flushed first. The public head is checked under `wait_lock`, with ownership,
HANDOFF and reschedule conditions rechecked before detachment. A SELF head ends
the batch. One cumulative body count bounds all snapshots, and refusal, FULL or
early release keeps the same stop/rejoin behavior. This changes no object fields
and introduces no NUMA reordering. Its measured results remain separate from the
default finite-snapshot protocol.

Four producer packets and four 8 KiB waiter stacks are reserved per CPU, with
one separate 8 KiB executor stack. Packet size is 320 bytes, registers start at
128, and the completion result starts at 304. Large per-CPU identities use a
dynamic allocation at provider initialization; placing the pool in the static
module arena exceeded this kernel's 8 KiB reserve. Reusable `rcuwait` identities
outlive packets. Final result publication is the last packet access; deferred
wakes retain only those stable identities.

Registry kind 3 and ABI2 distinguish owned images from legacy mutex images.
The two-word wrapper, minimal COMPLETE return, FULL detachment and logical-task
continuation remain shared. A FULL borrower never releases another task's owner
word: the physical executor performs each unlock and acknowledges it. Early
outer release rejoins pending requests and releases A once; the batch neither
reacquires A nor accesses its queue afterward while B finishes. Source retirement
requires producer slots, parked waits, executors, task references and frames to
drain independently of heat.

The benchmark selects this backend with `--mutex-implementation owned-v1` and
reports KD_SELF separately from JIT and Linux Native. It currently covers plain
c01 performance and separate nested/early functional probes. It does not expand
the existing translator's context/flags limits or provide RT/WW/interruptible
mutex APIs. The legacy benchmark default remains until performance acceptance.

## Legacy KD implementation

### Entry and native routing

The outer pair first reads the original `mutex.owner`, attempting an acquire
CAS only when the entire owner/flags word is zero. A busy read declines without
an exclusive cacheline request; a racing owner still defeats the CAS. Success
increments only the approximate CPU-local entry observation
and stores the exact native result in the lexical cookie. Unlock uses the
original function, preserving its owner/flag slowpath. Cookie zero routes to
KD, including native fallbacks after joining KD ownership routing.

`kd_mutex_outer_contended_clobber_v1()` does not retry the declined fastpath.
`kd_mutex_contended_acquire()` records that contention once and checks heat,
source OPEN, target comm, active-task routing and JIT policy before shadow/task
work. A native-only result is returned only when this acquisition obtained no
KD routing reference. The general direct and bridge APIs keep their void
contract; their unlock uses task membership, native requests and exact shadow
physical ownership rather than a fresh admission decision.

The contended hook owns a short preemption pin and calls the specialized
`kd_hotlock_record_mutex_pinned()` sampler. It records one entry and one failed
attempt. While the CPU is cold, samples below the 1,024-contention boundary
return before touching the exact-address table guard. The next boundary still
checks the strict `(entries >> 10) < mutex_entry_ratio_limit` ratio and CPU-local
contention frequency; the read-only limit defaults to 256 and accepts powers of two from
2 through 256. Per-address heat still needs 1,025 records, and a busy table
retains observations for retry. No task reference, shadow allocation or queue
publication occurs before native fallback. The load-time `mutex_native_route`
diagnostic forces that fallback after sampling; unlock never consults it.
Cooling changes new admission only. Existing waiters, task references and
owner acknowledgments remain live until their normal completion and retirement.

`kd_mutex_prepare()` registers the named post-lock continuation with
`KD_ENTRY_ABI_MUTEX_CLOBBER_V1`. Translation/admission/control tables recognize
direct symbols and kernel bridge aliases. The direct admitted unlock can use
terminal COMPLETE; bridge aliases use checked generic FULL dispatch. The
outer returning entry has a separate physical C return and JIT continuation
which defines route zero, so a nested translated call never consumes an
unmodelled native result.

### Current storage and lookup

| Object | Current storage/lifetime |
| --- | --- |
| Original Linux mutex | Workload's `struct mutex`; authoritative native-peer exclusion and physical ownership |
| Shadow table | 1024 resident `kd_mutex_shadow_entry` objects in [kd_lock.c](../../kernel_module/kd_lock.c); each 192-byte gate separates tail, physical ownership/state and waiter identity/gate wait list onto three cachelines |
| Mapped waiter counts | Dynamically allocated 1024 exact integers per possible CPU (256 KiB for 64 CPUs); immutable shadow slot, initialized before map publication and retained until provider unload |
| Task routing record | RCU hash with 256 cacheline-aligned buckets in [kd_mutex_tasks.c](../../kernel_module/kd_mutex_tasks.c); cached identities retain an atomic acquisition count and a `task_struct` ref; insertion/eviction use the bucket writer lock |
| `kd_mutex_node` | Four independently bitmap-reserved slots per possible CPU; 320 bytes each, 64-byte aligned |
| Waiter stacks | Four 8 KiB stacks per possible CPU, allocated by [lifecycle.inc](../../kernel_module/mutex/lifecycle.inc) with `vzalloc_node(..., cpu_to_node(cpu))` |
| Blocking notifications | Four `rcuwait` slots per CPU, resident for the provider lifetime; each node retains its immutable slot pointer, independent of packet reuse |
| Execution frames | Shared per-CPU context, up to eight frames; physical owner remains fixed through sleep/ACK; root borrows node packet until FULL detachment |
| Batch state | Physical combiner's stack; retains current retirement flag, exact successor, bounded NUMA deferred chain, outer-release callback and image-slot identity |

Shadow hits acquire-load the immutable exact address without a lock. The
current collision policy is `address % 1024` plus linear probing; misses take
`kd_mutex_shadow_lock`, recheck, initialize and release-publish the address.
Entries are cacheline-aligned and are not removed/reused while callers are live.
Exhaustion falls back to the original mutex. The shadow hash policy is unchanged.

`kd_mutex_task_get()` first attempts an RCU lookup and atomic acquisition-reference
increment. Cache hits require neither allocation nor the bucket writer lock.
Misses allocate with GFP_ATOMIC, lock the bucket and recheck before publication.
The last put changes the exact count to zero, immediately disabling routing;
the inactive identity can remain cached. A bucket retains up to eight identities
unless live acquisitions require more. A zero-reference eviction CAS claims
the record with -1, arbitrating against concurrent reactivation, before unlinking
it. RCU then protects old readers until the callback drops the task ref and frees
storage. Inactive records also disappear during controlled provider unload.

Controlled drain counts records with positive references after callers stop.
Cached task lifetime does not extend routing membership or excuse an outstanding
owner ACK. Active overflow is pruned on the final put. Approximate heat/counter
values never replace these references. The allocation-fault switch remains
checked before cache lookup, using a read before its one-shot CAS.

Mutex heat has separate entry/contention counters from spin. Every 1024
contentions the accepted policy checks `(entries >> 10) < 256`, resets both
counters, then samples the clock. The earlier proposed limit 2 is not the
current mutex setting. CPU and exact-address heat windows remain separate;
see [heat and roles](../JIT_EXECUTION.md#heat-and-roles) for the full policy.

### Packet/cacheline and prefetch layout

The node's first line contains next, GS base, saved physical RSP, stack
base/top, lock, task and saved entry identity. ABI/packet/tail/slot state and
immutable NUMA identity occupy the second line; `regs` begins at offset 128.
IP/SP/BP and five virtual GPR slots share its first aligned line.
`completed/locked/native_resume` occupy offsets 304/305/306, after the 168-byte
packet in the node's existing fifth line. Minimal packet and metadata writes
therefore do not invalidate the polling line. FULL recovery can touch the
packet's last line; the node remains 320 bytes. Linux `pt_regs` is unchanged.

The root frame's own hot header contains entry/lock identity and frame state.
For spin its inline IP/SP/BP share that first aligned line. A mutex simple
frame instead borrows `node->regs`; the frame header and node packet are
distinct objects. Caller stack memory keeps its original addresses/aliases
and is not relocated into either header. These are layout facts, not measured
cache misses or a claim that all request state occupies one line.

Before the current body, `kd_mutex_prefetch_successor()` hints the known-live
successor header, ABI and aligned hot packet line. After that body,
`kd_mutex_prefetch_successor_stack()` reads the saved SP and hints SP and SP-8.
Separating these stages lets the current body overlap the packet fetch instead
of immediately waiting for a cold SP load. The stack stage is skipped after
early outer release or native continuation. The pointer is queue-owned until
wake; no successor or current-node read is allowed after its completion/native
publication. Prefetch grants no ownership, admission or lifetime.

The private gate also uses a read before its acquire CAS. Together with the
original-owner guard, this keeps failed producer RMWs from invalidating ownership
lines held across a batch. Tail exchanges retain their atomic operations.
Mapped waiter counts use a component per origin CPU and immutable shadow slot;
entry/exit run with preemption disabled on the migration-pinned CPU. Private
unmapped gates retain their atomic count. The live mapped sum spans different
CPU instants and grants no ownership or retirement authority. Controlled drain
checks every component, including opposite nonzero balances; active-waiter,
reservation and underflow checks remain. Storage is allocated once at module
initialization with rollback, avoiding the reserved module-percpu size limit.

### Queue, batch execution and recovery

[queue.inc](../../kernel_module/mutex/queue.inc) encodes `(CPU+1, slot)` into
the tail, reserves nodes, and acquires the original Linux mutex only after
the scheduling gate. A same-CPU reserved predecessor on that queue refuses
before publication. This preserves the spin policy's progress rule and prevents
two tasks from sharing one CPU's executor context in either waiting mode.
[clobber.inc](../../kernel_module/mutex/clobber.inc) switches to the
reserved waiter stack before publication and restores the post-completion
boundary without returning through potentially overwritten hook frames.

[combiner.inc](../../kernel_module/mutex/combiner.inc) selects local requests
when built with NUMA enabled. It can defer at most 64 fully linked remote nodes;
an unlinked global tail is never detached. Selection happens at loop entry;
the current body retains the original successor chain through refusal and early
release. The next iteration uses the saved batch pointer, never a completed
node. This avoids an eager second NUMA selection before the current body.
At 128 completed bodies, or when the
retained successor has no link, deferred requests take priority. Eight or more
deferred requests receive physical handoff; a smaller remote cohort is rejoined
and serviced on the current owner, with FIFO selection for the rest of that
batch. This avoids moving the owner and frame stack for only a few requests.
All refusal, ordinary handoff and early-release exits rejoin deferred requests
before publishing a wake. These bounds constrain bypass within a batch; they
do not prove scheduler-independent starvation freedom.

The default total cap is exactly 1024 bodies. `--kd-batch-size` configures that
compile-time cap, verified through the provider's `mutex_batch` ELF metadata.
The combiner takes one enclosing source lease and uses
`kd_exec_frame_push_mutex_batch()` plus `kd_exe_mutex_batch_prepare()` for
eligible simple ABI2 roots. Each request still checks source OPEN and current
image readiness/publication/ABI; caching slot identity is not caching readiness.
The physical QUEUE_OWNER ledger is initialized before body entry. Cold
complex routing is materialized only when needed.

The first wrapper invocation either returns terminal COMPLETE and retires
through the dedicated mutex helper, or its returned FULL/refusal enters
`kd_exe_mutex_batch_resume()` once. It never reruns the first body. Packet
state and lock-ledger state are distinct: MINIMAL/COMPLETE only authorize the
documented clobber fields; FULL authorizes generic recovery GPRs. Retirement
reads ABI and packet state separately with field-width `READ_ONCE` loads. This
preserves every check while preventing a compiler-merged 64-bit comparison
from overlapping the wrapper's 32-bit packet-state store.

Committed terminal nodes retire before any wake: retain a linked successor,
or remove the exact tail by CAS; losing that CAS waits for the owed link.
The saved `current_retired` flag prevents repeated node reads after native
wake/reuse. Normal results retire/pop before release publication. FULL native
resume first detaches frame-owned state, copies the resume packet, retires the
queue node and publishes native readiness. The combiner then services the
exact physical-owner unlock/final ACK and pops the retained frame. Early A
release uses the same saved batch state and reacquires A for the combiner's
own operation after B finishes. [The detailed protocol](locking.md#53-nested-ab-and-native-continuation)
defines that ownership ordering.

Exact per-CPU active-waiter/reserved-node balances and slot bitmaps are
checked separately at drain; opposite imbalances on two CPUs cannot cancel.
The shared original-owner ledger, task refs, nested waiters and ACKs keep
their own exact state. Pure observations are per-CPU totals read after drain.
Native mutex release precedes gate release. The batch source lease outlives
all native/ACK/frame processing.

Every returning combiner holds the original mutex and normal gate value 1.
Refusal and ordinary completion publish that value before waking a successor;
early outer release reacquires it before returning. Terminal and outer-progress
fixtures check this contract independently of the caller's repeated restoration.

## Scope and evidence

### Blocking waits

KD mutexes always support ordinary uninterruptible sleep after at most
`mutex_spin_limit` PAUSE iterations (default 4096, permitted range 0–1048576).
Zero requests immediate parking. Scheduler pressure is checked every 64
iterations. The polling budget is read-only after load. The spin-only policy
and `mutex_blocking` selector have been removed; the public lock/unlock ABI
is unchanged.

[parking.inc](../../kernel_module/mutex/parking.inc) separates result waiters
from gate waiters. Result waiters register in a persistent `rcuwait` slot, set
`TASK_UNINTERRUPTIBLE`, recheck the result and call `schedule_timeout(1)` with
preemption enabled. The one-jiffy timeout rechecks completion even when a later
translated body depends on the completed caller and cannot flush its buffered
wake. An ordinary wake ends the sleep sooner. A timer tick is not a wall-clock
latency guarantee; scheduler delays still apply.
They retain migration pinning and their independently reserved stack. Completion
publishes the aligned two-byte result and orders its wake check against the
sleep-state barrier. Registration is cleared before node release. Late wakes use
only the resident wake object, never a recycled packet. A wake of a later user of
that slot is spurious; its condition loop checks its own result. The exact task
acquisition reference and RCU-delayed task-cache eviction protect wake readers.

The combiner buffers up to 16 persistent wake-slot pointers so short COMPLETE
bodies share a store-to-wake barrier. It flushes before FULL/generic dispatch,
before a native/ACK service can sleep, before early-release reacquisition and
before batch exit. Native continuation and physical handoff wake immediately.
Queue retirement and frame retirement still precede result publication; a wake
does not transfer Linux ownership or release an acquisition reference. This
bounded batching can add completion-to-wake delay; it is not a latency bound.

Queue heads use bounded polling plus `wait_event` on the gate's private wait
queue. Original-mutex release still precedes gate release. Its wake check has
the matching barrier, preventing a head from sleeping through gate opening.
The 24-byte wait queue fits the existing 192-byte shadow gate. Node size remains
320 bytes; `completed/locked/native_resume` keep offsets 304/305/306.

Mutex translation rejects final images that import the origin CPU's GS base,
including generated guards and learned callees, because another task may use
that CPU while the caller sleeps. Such bodies take the native path. Logical
`current` remains a separately supplied task identity. Existing
[admission and alias limits](admission.md) still apply. The mutex does not
add new interruptible/killable interfaces or a general rwsem/mmap implementation.

The [mutex runner](../../bench/tclock_compare/README.md) records the blocking
policy and scheduler observations. Historical spin/blocking comparisons remain
in the [archive guide](../../bench/mutex_wait_compare/README.md). The
[scheduler probe](../../tests/kernel/mutex/run_wait_selftest.py) checks actual
sleep, progress with a deliberately withheld completion wake, same-CPU progress
and exact drain; its constructed packets are separate
from benchmark JIT evidence.

KD retains migration pins, finite per-CPU reservations and bounded NUMA queue
grouping. Stack allocation, request selection and physical ownership have separate roles.
TCLock supports parking, but this port's fixed-affinity context contract does
not validate arbitrary oversubscription. Both stack/context protocols require
independently runnable dependencies and controlled drain.

The benchmark KD provider defaults to UBSAN off; a standalone provider build
inherits the existing kernel configuration. Backend/workload ELF identity
and instrumentation policy are recorded separately. The captured kernel is
unchanged. Build/use instructions belong in the
[workload README](../../workload_modules/mutex_cacheline/README.md) and
[runner README](../../bench/tclock_compare/README.md).

The [blocking-only verification](../../bench/results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json)
records affected fixtures, actual scheduler/owner probes and returned JIT bodies.
[Performance status](../PERFORMANCE.md) summarizes the latest frozen comparison;
[validation](../VALIDATION.md) indexes older checks and rejected candidates.
These selected checks do not establish arbitrary oversubscription or starvation freedom.
