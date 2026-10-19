# Mutex implementation: KD, TCLock and Linux Native

`master` retains the accepted KD-only legacy lock protocol. New delegation
callers use ABI2; ABI0 remains an internal legacy compatibility interface.
The [compatibility backport](../history/legacy_mutex_compatibility.md) adds fail-closed
processor-state admission, immutable mutex images and generation-bound frames.
The [KD-only extension](kd_only_mutex.md) embeds physical exclusion in a native-sized
KD object and claims separate delegation scheduling state only when needed, while
retaining the queue and pinned producer.

Read [lock protocols](lock_protocols.md) for the algorithm/ownership comparison
and [KD locking](locking.md#mutex-delegation-protocol) for nested owner/ACK
details. This page maps the current ordinary mutex paths to their data and
source. [Register ABI](../JIT_REGISTER_ABI.md) defines the shared wrapper, and
[lifetimes](lifetimes.md) owns executable-image storage. The spin continuation
pool and mutex waiter stacks have separate layouts; shared execution machinery
does not imply copying a spin continuation into every mutex request.
The [lock catalog](../LOCKS.md) locates the other lock families;
[terminology](../TERMINOLOGY.md) defines the queue and machine-state terms.

## Source and call paths

| Arm | Workload entry | Backend implementation |
| --- | --- | --- |
| Native | `(mutex_lock)` / `(mutex_unlock)` | Captured kernel `kernel/locking/mutex.c`, `include/linux/mutex.h` |
| TCLock | `komb_mutex_lock` / `komb_mutex_unlock` | [komb_mutex.c](../../tclock_backend/komb_mutex.c), [combiner.c](../../tclock_backend/combiner.c), [mutex_provider.c](../../tclock_backend/mutex_provider.c) |
| KD ordinary/local | `kd_mutex_local_lock/unlock` and ordinary API variants | [kd_mutex_local.c](../../kernel_module/kd_mutex_local.c), [kd_mutex_osq.c](../../kernel_module/kd_mutex_osq.c) |
| KD outer | `KD_MUTEX_OUTER_LOCK/UNLOCK` | [kd_mutex_direct.h](../../include/kd_mutex_direct.h), [mutex_calls.inc](../../kernel_module/lock/mutex_calls.inc) |
| KD general/nested | `KD_MUTEX_DIRECT_LOCK/UNLOCK` and internal ABI0/2 entries | Same routing file, [kd_mutex.c](../../kernel_module/kd_mutex.c), [native.inc](../../kernel_module/execution/native.inc) |

The Native, TCLock and KD benchmark arms use distinct compiled functions in
[mutex_cacheline/module.c](../../workload_modules/mutex_cacheline/module.c).
The mutex translation unit reuses payload, ioctl runner and timing sources;
there is no per-operation runtime `is_mutex` branch. Measurement runs through
[run_mutex.py](../../bench/tclock_compare/run_mutex.py), sharing reporting with
the spin runner. Registration and final context drain are outside measurement.

The existing kernel build is `/root/linux-6.1.159-kdclobber2` in the guest. Its
release, configuration, source/interface hashes and live Build ID are checked
by the [kernel identity verifier](../../bench/spin_cacheline/kernel_identity.py)
against the [captured baseline](../../kernel_baseline/README.md). Native source
paths above refer to that build. The KD physical core is a separately namespaced
port of its ordinary mutex/OSQ algorithms; it owns KD objects and makes no Linux
mutex API calls.

## Public KD API

[`kd_mutex.h`](../../include/kd_mutex.h) defines ordinary operations;
[`kd_mutex_direct.h`](../../include/kd_mutex_direct.h) defines delegation-capable
calls. These share physical exclusion when used with their matching unlocks.

| Operation | Interface and result |
| --- | --- |
| Initialization and teardown | `DEFINE_KD_MUTEX`, `KD_MUTEX_INITIALIZER`, `kd_mutex_init`; `kd_mutex_destroy` diagnoses a busy object and does not drain users |
| Ordinary blocking acquisition | `kd_mutex_local_lock` / `kd_mutex_local_unlock`; executes the caller's body locally |
| Cancellable acquisition | `kd_mutex_lock_interruptible` or `kd_mutex_lock_killable`; zero on success, `-EINTR` on cancellation; successful calls pair with local unlock |
| Trylock | `kd_mutex_trylock`; 1 on success, 0 otherwise; success pairs with local unlock |
| I/O wait accounting | `kd_mutex_lock_io`; local acquisition with scheduler I/O accounting, paired with local unlock |
| Last-reference acquisition | `kd_atomic_dec_and_mutex_lock`; returns 1 with the local mutex held only when the count reaches zero; otherwise returns 0 without ownership |
| Ownership observations | `kd_mutex_is_locked` observes a physical owner; `kd_mutex_is_idle` additionally checks local/delegation state after all users join; neither acquires the lock |
| Outer delegation | `KD_MUTEX_OUTER_LOCK/UNLOCK`; opaque same-task cookie for one lexical acquisition |
| General direct delegation | `KD_MUTEX_DIRECT_LOCK/UNLOCK`; explicit clobber interface also recognized for supported nested translated controls |

Prepare named direct continuations with `kd_mutex_prepare` and
`KD_ENTRY_ABI_MUTEX_CLOBBER_V1` after the source module is live. The containing
function uses `noipa` to prevent duplicate continuation labels. Ordinary aliases
in [`kd_mutex_compat.h`](../../include/kd_mutex_compat.h) select local operations;
they do not turn arbitrary ordinary C calls into delegation. Interruptible and
killable forms retain their original-task result and cancellation semantics.

The [replacement contract](kd_only_mutex.md) owns alias coverage and rebuild
requirements. There is no Linux mutex fallback. The outer cookie's nonzero value
records exact local ownership; zero means provider-routed unlock and can also
occur after a local fallback. It is not a delegation-success flag.

## KD implementation

### Physical exclusion for ordinary and delegated callers

The `owner` word stores the actual owning task plus three low flag bits:
`WAITERS=1` records a sleeping wait list, `HANDOFF=2` requests ownership transfer,
and `PICKUP=4` reserves that transfer for the selected task. A successful
zero-owner acquire compare-and-exchange grants the fast path. A busy caller
may optimistically spin while the owner is running, using a private optimistic
spin queue (OSQ) to order competing spinners.

When spinning cannot acquire, `kd_local_lock_slow` links a stack waiter under
`wait_lock`, publishes its sleep state and rechecks acquisition before sleeping.
Signal cancellation removes that waiter under the same lock. A designated
handoff must be picked up before checking signals, so cancellation cannot abandon
ownership already assigned to that task. Release clears the owner with release
ordering or wakes/transfers to the first sleeper; the wake queue retains a task
reference until wakeup. The local physical path allocates no delegation node or
JIT frame. Callers entering through the delegation engine retain that engine's
separate request records while using this same physical primitive.

The delegation gate is separate from this owner word. A queue head first takes
the gate, then acquires the same physical mutex through `kd_mutex_claim_origin`.
The auxiliary record's `physical_owner` records the delegation executor; it is
not the ordinary `owner` word and is not set for every local acquisition. Gate
values 1 and 3
identify ordinary gate ownership and an active combiner respectively. Neither
value alone grants permission to execute protected data. Physical unlock must
precede opening the gate.

| Stage | Source to follow |
| --- | --- |
| Local acquire, cancellation, unlock and idle | [kd_mutex_local.c](../../kernel_module/kd_mutex_local.c); private [OSQ](../../kernel_module/kd_mutex_osq.c) |
| Direct entry policy and exact unlock routing | [lock/mutex_calls.inc](../../kernel_module/lock/mutex_calls.inc); [kd_mutex_tasks.c](../../kernel_module/kd_mutex_tasks.c) retains task/acquisition references |
| Auxiliary delegation lookup and retirement | [kd_mutex_aux.c](../../kernel_module/kd_mutex_aux.c); [kd_mutex_aux.h](../../include/kd_mutex_aux.h) defines the shared record |
| Node reservation and physical-owner acquisition | [mutex/queue.inc](../../kernel_module/mutex/queue.inc), coordinated by [kd_mutex.c](../../kernel_module/kd_mutex.c) |
| Batch selection, execution and node retirement | [mutex/combiner.inc](../../kernel_module/mutex/combiner.inc) |
| Waiter execution stacks and continuation restore | [mutex/clobber.inc](../../kernel_module/mutex/clobber.inc), [mutex/waiter.inc](../../kernel_module/mutex/waiter.inc) |
| Object/per-CPU initialization and drain | [mutex/lifecycle.inc](../../kernel_module/mutex/lifecycle.inc) |

### Entry and native routing

The outer pair probes the KD `owner` word at most eight times, attempting an
acquire CAS only when the entire owner/flags word is zero. Each failed probe
pauses before the next attempt; a busy owner read does not modify that word, and a
racing owner still defeats the CAS. The active-combiner hint reads the address's
direct-index slot and validates its lifecycle sequence, without taking a lock,
changing a reference count or retaining an auxiliary pointer. The existing
active-combiner gate state (3) ends retries; a lone gate owner (state 1) may finish
during the bounded window.
The observed state is a hint and never grants ownership or retirement. This window
has no worker-count threshold. Success increments the CPU-local entry observation
and stores the exact native result in the lexical cookie. Unlock uses the
KD local function, preserving its owner/flag slowpath. Cookie zero routes to
KD, including native fallbacks after joining KD ownership routing.

After the bounded probes are exhausted,
`kd_mutex_outer_contended_clobber_v1()` does not repeat that probe window.
`kd_mutex_contended_acquire()` records that contention once and checks heat,
source OPEN, target comm, active-task routing and JIT policy before task/queue
work. A native-only result is returned only when this acquisition obtained no
KD routing reference. The general direct and internal entry APIs keep their void
contract; their unlock uses task membership, native requests and exact KD
physical ownership rather than a fresh admission decision.

`kd_mutex_prepare()` registers the named post-lock continuation with
`KD_ENTRY_ABI_MUTEX_CLOBBER_V1`. Translation/admission/control tables recognize
KD direct and local physical symbols. The direct admitted unlock can use
terminal COMPLETE; complex recovery uses checked generic FULL dispatch. The
outer returning entry has a separate physical C return and JIT continuation
which defines route zero, so a nested translated call never consumes an
unmodelled native result.

### Current storage and lookup

| Object | Current storage/lifetime |
| --- | --- |
| KD mutex object | 32 bytes, aligned to 8 bytes in the captured configuration, owned by the caller; physical owner, OSQ, wait-list spinlock and sleeping wait list |
| Delegation auxiliary slot | 256 bytes, aligned to 128 bytes; 65,536 direct-index slots occupy 16 MiB allocated once during provider initialization; each claimed slot retains an exact lock address, lifecycle sequence, delegation tail, executor/gate, waiter count and atomic references |
| Physical waiting | Private per-CPU OSQ nodes and stack-resident sleeping waiters; ordinary Linux mutex APIs never participate |
| Task routing record | RCU hash with 256 cacheline-aligned buckets in [kd_mutex_tasks.c](../../kernel_module/kd_mutex_tasks.c); cached identities retain an atomic acquisition count and a `task_struct` ref; insertion/eviction use the bucket writer lock |
| `kd_mutex_node` | Four independently bitmap-reserved slots per possible CPU; 320 bytes each, 64-byte aligned |
| Waiter stacks | Four 8 KiB stacks per possible CPU, allocated by [lifecycle.inc](../../kernel_module/mutex/lifecycle.inc) with `vzalloc_node(..., cpu_to_node(cpu))` |
| Execution frames | Shared per-CPU context, up to eight frames; physical owner remains fixed through sleep/ACK; root borrows node packet until FULL detachment |
| Batch state | Physical combiner's stack; retains current retirement flag, exact successor, bounded NUMA deferred chain, outer-release callback and image-slot identity |

Physical operations, including uncontended outer acquisition, use the embedded
fields without an auxiliary lookup. Delegation hashes the object address to one
of 65,536 slots; object identity remains the exact KD pointer. There is no
collision chain, registry lock or auxiliary RCU lifetime. A collision or a slot
being initialized or retired immediately takes the existing local KD fallback
before queue publication. This bounds simultaneous delegation state without
limiting the number of ordinary mutex objects. The [KD-only guide](kd_only_mutex.md)
records field offsets, ordinary API aliases, initialization, drain and full-rebuild
requirements.

The table is zeroed by `vzalloc()` during provider initialization; allocation
failure aborts provider startup with `-ENOMEM`. No allocation occurs on a slot
lookup or claim. The reference word distinguishes free (`-1`), an exclusive
lifecycle reservation (`0`) and live exact references (positive). Creation claims
a free slot, publishes its address and sequence, then release-publishes the first
reference. Lookup increments only a positive count and rechecks the address after
that successful increment: an earlier address read alone cannot identify the
generation acquired by the CAS. A mismatched lookup releases its reference.

Invocation references protect the published queue and its borrowed packet/frame
storage. A separate gate-owner reference survives scheduling-node retirement and
follows physical-owner release, including native ACK and early-release processing.
There is one narrower transfer before node reservation: an immediate successful
gate CAS in `_kd_mutex_lock_abi()` transfers its invocation reference to the
owner through `kd_mutex_claim_origin_take_ref()`. No node, frame or ACK exists
on that path, and the transferred reference protects physical acquisition even
if it sleeps. Waiting, queued, node-overflow and early-reacquisition paths retain
their invocation reference and acquire a separate owner reference.

Synchronous checked unlock uses `kd_mutex_aux_borrow_owned()` to borrow the
current task's established owner reference. The helper validates sequence,
exact address and `physical_owner == current`; it neither increments a reference
nor lends another task's lifetime. Successful unlock clears the recorded owner,
releases physical exclusion, opens the scheduling gate and puts that one owner
reference, with no subsequent access to the slot. A rejected unlock leaves the
owner reference intact. Queue/frame/ACK retention and early outer-release
ordering are unchanged.

Each put atomically decrements the reference count. A resulting zero gives that
caller exclusive retirement: it verifies that executor, gate, tail and waiter
state have drained, clears the address, then release-publishes the free state.
A lookup racing the final put cannot increment the zero reservation. It may
instead acquire a later generation, which still requires the post-acquisition
address check. A held reference prevents reuse through every protocol obligation;
empty queue fields cannot replace it.

Read-only ownership, combiner and waiter-count observations validate the address
and observed fields between two lifecycle-sequence reads. Creation and retirement
publish an odd sequence before changing the address and an even sequence after
the change. Observers reject odd or changing sequences and retain no pointer.
The sequence never wraps: exhausting it permanently disables that slot, with
future delegation attempts falling back locally. The combiner value remains a
hint, while an actual delegation owner also holds its exact reference.
An unstable waiter-count observation returns `-EAGAIN`; idle checks treat a
reserved slot or changing sequence conservatively. A permanently exhausted slot
with free references is idle. The final `kd_mutex aux:` counters distinguish
collision, busy, generation-race, exhausted and injected refusals; they are
diagnostics and never authorize ownership or retirement.

Neither ordinary nor delegation callers need a destruction call to release their
auxiliary slot. They must still stop and join users and drain all uses before
freeing or reinitializing the lock object. Exact idle diagnostics count both live
references and lifecycle reservations as active. Table storage remains allocated
until controlled provider teardown has stopped and joined callers, including
read-only observers, and verified every slot free. Only then is the table freed;
there are no per-slot deferred callbacks. Empty references alone do not establish
that a caller cannot start another observation.

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

Before the current body, `kd_mutex_prefetch_successor()` reads the known-live
successor header and gives write hints for its aligned hot packet line and stack
addresses SP and SP-8. It avoids duplicate hints for SP/BP on the same line and
does not fetch the entire FULL packet on every minimal request. The pointer is queue-owned until wake; no successor or
current-node read is allowed after its completion/native publication. Prefetch
grants no ownership, admission or lifetime.

The auxiliary gate also uses a read before its acquire CAS. Together with the
physical-owner guard, this keeps failed producer RMWs from invalidating ownership
lines held across a batch. Tail exchanges and exact waiter-count updates retain
their original atomic operations on separate lines within the auxiliary record.
Atomic lifetime references share the waiter-count line at offset 196, keeping
reference writes away from the immutable lookup key and the executor/gate line.
They remain independent of queue observations and exact ownership records.

### Queue, batch execution and recovery

[queue.inc](../../kernel_module/mutex/queue.inc) encodes `(CPU+1, slot)` into
the tail, reserves nodes, and acquires KD physical exclusion only after
the scheduling gate. A same-CPU reserved predecessor on that queue refuses
before publication so a pinned follower cannot prevent a sleeping head from
resuming. [clobber.inc](../../kernel_module/mutex/clobber.inc) switches to the
reserved waiter stack before publication and restores the post-completion
boundary without returning through potentially overwritten hook frames.

[combiner.inc](../../kernel_module/mutex/combiner.inc) selects local requests
when built with NUMA enabled. It can defer at most 64 fully linked remote nodes;
an unlinked global tail is never detached. At 128 completed bodies, or when the
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
own operation after B finishes. [The detailed protocol](locking.md#nested-ab-and-native-continuation)
defines that ownership ordering.

Exact per-CPU active-waiter/reserved-node balances and slot bitmaps are
checked separately at drain; opposite imbalances on two CPUs cannot cancel.
The shared physical-owner ledger, task refs, nested waiters and ACKs keep
their own exact state. Pure observations are per-CPU totals read after drain.
KD physical mutex release precedes gate release. The batch source lease outlives
all native/ACK/frame processing.

Every returning combiner holds KD physical exclusion and normal gate value 1.
Refusal and ordinary completion publish that value before waking a successor;
early outer release reacquires it before returning. Terminal and outer-progress
fixtures check this contract independently of the caller's repeated restoration.

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
[upstream](../../tclock_backend/upstream) with hashes in
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

## Scope and evidence

KD keeps pinned published waiters and bounded NUMA queue grouping. Stack
allocation, request selection and KD physical ownership have separate roles.
TCLock supports parking, but this port's fixed-affinity context contract does
not validate arbitrary oversubscription. Both stack/context protocols require
independently runnable dependencies and controlled drain.

Reviewed special instructions can use the [checked instruction-exit contract](admission.md#checked-instruction-exits)
instead of rejecting an entire body because an untaken branch contains one.
If execution reaches the marker, the original waiter resumes before that
instruction and future delegation of the entry is disabled for the source
session. Other unsupported instructions remain refused. This translation policy
does not change the mutex queue, physical ownership or pinned-waiter protocol.
The direct string-helper optimization is restricted to spin ABI1 and is not a
new mutex execution path.

The benchmark KD provider defaults to UBSAN off; a standalone provider build
inherits the existing kernel configuration. Backend/workload ELF identity
and instrumentation policy are recorded separately. The captured kernel is
unchanged. Build/use instructions belong in the
[workload README](../../workload_modules/mutex_cacheline/README.md) and
[runner README](../../bench/tclock_compare/README.md).

The selected `d2a2304` c01/post64 and pipebytes n16 comparison, returned-body
evidence and regression limits are in the
[KD-only report](../../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md).
That report measures the prior 256-byte, 128-byte-aligned object. The separate
[compact comparison](../../bench/results/10.176.26.71/bench/mutex32-index-20261019/README.md)
measures the RCU registry, direct-index table and reference transfer against a
fresh inline baseline. The final compact version improves pipe medians over
RCU but retains c01, seek and pipe gaps against the inline object. Its basic
plus affected checks, profiles, variation and sequential-run limits remain
with that report; the historical full-grid results are not compact measurements.
Earlier grouping/cache candidates remain in
[fixed benchmark records](../../bench/results/380G10/bench/tclock_compare/HISTORY.md#mutex-followup).
The earlier [mandatory-JIT trials](../../bench/results/380G10/bench/tclock_compare/20261008-mutex-priority-trials.md)
retain their original-host behavior after rejecting those versions of task
retention and smaller entry/execution changes under `nopvspin`.
Source review and synthetic unit fixtures do not substitute for those live
results or prove starvation freedom.
