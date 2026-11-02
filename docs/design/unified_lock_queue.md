# Unified lock queue: Stage (a) design

The authorized Stage (c) implementation is specified in
[killable capture and exact request retirement](killable_queue_execution.md).
It brings the necessary object-wide selected-writer admission forward rather
than enabling capture on top of the old positive cohort. The Stage (b) receipts
remain fixed evidence; they do not validate the new implementation.

## Artifact, scope and evidence status

Stage (a) was committed and reported as a source-backed design at
81e2c674764eea877241021946062d53398f01f3. Implementation now proceeds in
separate queue, cancellation and delegated-transition commits. Following the
subsequent instruction, validation is incremental after the functional paths
are connected; this does not turn an unrun stage into validated support.

- Branch: codex/unified-lock-queue.
- Design parent: f1a179b8f2e369f571b927ceb6443f51a0415b7f.
- Production source baseline: 7231ddf0963ff2cc730590c09cc81e7f96f93095.
- Rejected, unbuilt noncancellable attempt:
  64d4c3c049b82409d4765144e8422e31d20a4734, retained by
  codex/archive-rwsem-noncancellable-foundation. Do not use it as a candidate.

The scope is a reusable internal queue for mutex, rwsem and rwlock. Native
application bodies, public signatures/results and lock-specific context rules
remain unchanged. No mmap1 names, branches, helpers or special modes enter the
production protocol. General delegated MM execution additionally depends on the
executor/context/image work identified in the
[rwsem protocol design](rwsem_delegated_protocol.md).

The decision is **one reusable topology and lifecycle implementation, with one
mutex acquisition queue for both local and delegation-capable requests**.
Different condition channels and CPU-local physical primitives are not collapsed
into one FIFO. Shared queue code does not imply shared ownership, one global
queue, one waiting predicate, or permission to sleep in every lock class.

## Public behavior and its preservation mechanism

These are requirements on every supported caller, not special benchmark rules.
Runtime scheduling and throughput may change; public acquisition results,
protected intervals, required ordering and release/context behavior may not.

| Behavior to preserve | Mechanism in the new protocol |
| --- | --- |
| Ordinary mutex/rwsem acquisition returns void; body runs once after acquisition | Exact request grant plus one execution owner. No queue/resource error becomes a new public error or replays a committed prefix. |
| Killable mutex/rwsem acquisition returns 0 or -EINTR | Origin signal predicate and actual acquisition readiness arbitrate under the object's queue guard. A committed grant cannot become cancellation. |
| Interruptible acquisition returns 0 or -EINTR | Same arbitration, using TASK_INTERRUPTIBLE rather than TASK_KILLABLE. Preserve the existing KD interruptible-writer extension; do not present it as a Native rwsem API. |
| Nonfatal signals do not cancel killable acquisition | A pending signal may end optimistic spinning; only signal_pending_state(TASK_KILLABLE, logical_origin) authorizes cancellation. |
| Successful acquisition takes priority over a pending signal | Both initial fast attempt and guarded decision attempt a ready grant before accepting cancellation. Selection or gate reservation alone is not success. |
| Mutex/rwsem/rwlock trylock remains boolean and nonblocking | Existing atomic acquisition/rollback policy, no queue publication, allocation, sleeping or proxy selection. No failed trylock leaves a credit, pin, phase or gate. |
| Concurrent ordinary readers remain local | Reader-count admission stays separate from writer execution. Queued reader nodes grant an admission attempt/credit, not another task's reader body. |
| Downgrade has continuous write-to-read protection | Publish one exact read credit before ending exclusive admission. A delegated downgraded tail stays on its executor through matching read release. |
| Matching unlock consumes exactly the successful acquisition | Acquisition identity and actual physical owner/ticket route release. Queue position, task names, heat and aggregate counts are not authority. |
| Authorized non-owner read release | Preserve the explicit transferred acquisition/object lifetime. Cross-task release consumes that credit once; it does not imply mutex owner transfer. |
| Atomic-compatible read try/rollback/up_read | Keep ordered counter operations without sleeping, queue-guard/scheduler locking or deferred unretained object pointers on the atomic path. Timed writer-drain rechecks remain. |
| IRQ/BH/preemption variants and spin-context use | Lock-class adapters preserve the declared entry/restore order, flags and actual owner CPU. No sleeping mutex acquisition is made legal under a held spinlock by temporarily enabling preemption. |
| Callable, function-pointer and cleanup forms | Preserve conventional C results and constructor lifetime. An entry lacking a complete continuation contract explicitly sets delegation false; never capture inside a returning guard constructor as though it were the user's body. |
| Mutex I/O and atomic_dec_and_mutex_lock | Preserve I/O accounting and the original atomic reference predicate; queue refactoring changes only the lock wait after that predicate permits it. |
| Nested annotations and object initialization/preparation | Preserve ignored non-lockdep annotations, static initialization and existing preparation errors (-EINVAL/-ESHUTDOWN/-EOPNOTSUPP and rwsem -EBUSY where applicable). No new -E2BIG/-ENOMEM/-EDEADLK leaks from the queue into ordinary APIs. |
| Query/assertion interfaces | Preserve their lock-state/hint contracts; an implementation-specific contention hint is never an ownership proof. Exact selected/acquired records drive owner-sensitive checks. |

Verified baseline sources: [local mutex entries](../../kernel_module/kd_mutex_local.c#L317),
[grant before signal](../../kernel_module/kd_mutex_local.c#L249),
[rwsem entries](../../kernel_module/kd_rwsem.c#L175),
[rwlock context/try APIs](../../include/kd_rwlock.h#L163), and
[preparation](../../kernel_module/lock/mutex_calls.inc#L173).
Unsupported configurations remain CONFIG_PREEMPT_RT, CONFIG_DEBUG_MUTEXES,
CONFIG_DEBUG_LOCK_ALLOC and lockdep. This design neither enables those
configurations nor claims arbitrary whole-kernel replacement.

## Migration map: old queue to new queue

All rows refer to the source baseline above. Stage (b) first substitutes reusable
operations without changing admission order or enabling a new execution mode.

| Existing mechanism and source evidence | Destination | Separation retained |
| --- | --- | --- |
| Sleeping mutex ring, stack waiter, wait_lock: [kd_mutex_local.c:66](../../kernel_module/kd_mutex_local.c#L66), [249](../../kernel_module/kd_mutex_local.c#L249) | Common per-object mutex request queue; local-only nodes carry the same grant/signal/wake policy | Stack waiter may retire only after its own queue/read references finish. Real owner HANDOFF/PICKUP semantics remain. |
| Delegation tail/chain and private NUMA lists: [waiter.inc:50](../../kernel_module/mutex/waiter.inc#L50), [combiner.inc:36](../../kernel_module/mutex/combiner.inc#L36) | Same mutex request queue, with delegation-capable nodes and explicit selection records | Continuation, image, source, stack, physical acquisition and final ACK lifetimes survive dequeue. No private linked batch invisible to cancellation. |
| Mutex physical OSQ: [kd_mutex_osq.c:147](../../kernel_module/kd_mutex_osq.c#L147), [231](../../kernel_module/kd_mutex_osq.c#L231) | Target: bounded optimistic spinning as a wait policy on that same queued request, then park when legal | Until old OSQ is removed as a whole, its links and IDLE/grant/abort retirement stay independent. Never alias active legacy OSQ links with the new queue. |
| Rwsem reader admission OSQ: [kd_rwsem.c:139](../../kernel_module/kd_rwsem.c#L139) | Common queue instance for reader-admission retries, eventually sharing the phase-condition channel | Retry-turn ownership is not reader ownership. Ordinary reader bodies stay local. Migration must retain abort/unlink-before-schedule and reader concurrency. |
| Rwsem phase_wait: [kd_rwsem.c:79](../../kernel_module/kd_rwsem.c#L79) | Separate common condition-channel instance for admission predicates | Enqueue/recheck/wake ordering and phase-wait cancellation remain distinct from reader drainage. |
| Rwsem reader_drain: [kd_rwsem.c:100](../../kernel_module/kd_rwsem.c#L100) | Separate common condition-channel instance for selected writers waiting on active reader credits | Atomic final up_read can omit notification; timed predicate rechecks remain. Never drain queued admission waiters as though they were active readers. |
| Rwlock writer/slow-reader gate: [kd_rwlock.h:56](../../include/kd_rwlock.h#L56), [128](../../include/kd_rwlock.h#L128) | Common lifecycle/selection code with a non-sleeping rwlock adapter; physical backend migration is separately gated | Keep packed reader/writer state and the interrupt/BH reader exception. Such a reader cannot join a writer gate that is draining its interrupted reader. |
| Standalone four-byte spin primitive/MCS storage: [spin/nondelegated.inc](../../kernel_module/spin/nondelegated.inc) | Retain as a physical backend where an inline common header cannot fit | Reusable records/services do not authorize enlarging a Native-sized gate or replacing IRQ-context waits by sleeping. Standalone spin redesign is not required by this stage. |
| Owner-service/return ACK mailboxes, source/image retirement lists | Retain separate channels, optionally reusing notification helpers | These carry execution/ownership dependencies, not acquisition order. Making an owner wait behind its own acquisition FIFO can deadlock. |

Thus the target removes the separate sleeping-ring/delegation-chain topology
and, after validation, the mutex's separate OSQ membership. It shares code for
rwsem conditions and rwlock requests while retaining necessary queue instances
and physical state. Stage (b) is not complete if it merely renames all the old
queues or adds a wrapper around unchanged independent request lists.

### Current rwsem condition integration and retained rwlock backend

The Stage (b) source changes replace rwsem phase_wait and reader_drain topology
with distinct common condition heads sharing gate.wait_lock. Short condition
descriptors never run an independent acquisition election. Grant/rollback and
prepared positive-cohort admission remain unchanged until the canonical killable
driver and selected-phase protocol are connected together. The reader admission
OSQ remains an independent physical membership at this point; its count is an
optimistic-reader hint, not every parked reader. A future single-membership
spin-to-park adapter must retain that distinction so a writer does not wait for
parked readers that need its phase to reopen. These changes are unbuilt and
unrun, and do not establish delegated killable support.

Rwlock still uses the existing packed count and four-byte KD spin gate at
offset 64. Task slow readers withdraw their speculative count before acquiring
that gate; interrupt/BH readers bypass the queued-writer gate to avoid waiting
for their interrupted reader: [kd_rwlock.h:56](../../include/kd_rwlock.h#L56).
Writers own the gate and drain active readers before body entry:
[kd_rwlock.h:128](../../include/kd_rwlock.h#L128). ABI3 dispatch still enters the
spin backend at [spin/direct.inc:46](../../kernel_module/spin/direct.inc#L46)
and performs executor admission at
[spin/combiner.inc:137](../../kernel_module/spin/combiner.inc#L137). Moving only
local callers to a new common head would leave two acquisition topologies.
The pending join must migrate those ABI3 provider/combiner routes and the local
slow-reader/writer adapter together, preserving the gate's size, count-byte
release, exact pins/tickets and interrupt-reader exception. No partial rwlock
header or alternative local queue is enabled by the condition-channel change.

### Why the earlier retirement warning still matters

The explicit warning is about independently live OSQ and delegation memberships:
[mutex_implementation.md:125](mutex_implementation.md#L125),
[571](mutex_implementation.md#L571),
[include/kd_mutex.h:56](../../include/kd_mutex.h#L56), and
[lifetimes.md:16](lifetimes.md#L16). No literal blanket prohibition against a new
sleeping/delegation queue was found in this source. The sleeping ring's stack
lifetime and the chain's frame/ACK lifetime nevertheless make a link-only merge
incorrect.

The redesign replaces topology publication for both, rather than aliasing their
current links. Publication and unlink are fully serialized. A queue node retains
a stable request reference while linked or selected. Dequeue never retires a
live packet/frame. A local stack node gets no remote borrower after unlink ACK;
a delegating request retains its continuation anchor after queue membership
ends. Removing the legacy OSQ eliminates its membership; while it still exists,
its existing separate links and full retirement proof remain mandatory.

## Queue, request, acquisition and activation model

### Stage (b) storage and migration choices

The common queue is a nonowning view of an existing raw guard and one head
pointer. The mutex keeps its 32-byte layout: owner at 0, raw wait guard at 8,
legacy OSQ word at 12 during migration, common head at 16, delegation gate at
24, and a reserved compatibility word at 28. The last word no longer publishes
an independently linked delegation chain. A circular node supplies the tail.
Local waiters use stack-owned request/membership storage. Captured requests
use cold sidecars paired with the existing preallocated CPU/slot storage, so
the 320-byte packet, packet offsets and two-word wrapper ABI do not change.
Slot lookup uses its immutable encoded CPU/slot identity. A sidecar remains
reserved until queue, selection, execution and return obligations have ended.
This stage does not claim to remove the existing finite capture capacity.

The first VM compilation completed, but module loading rejected the enlarged
static per-CPU section (8560 bytes). Cold sidecars therefore use a dynamic
per-CPU pool allocated once during provider initialization and freed only after
exact provider drain. This is still preallocation, not lock-path allocation;
hot packet storage remains in its existing static per-CPU area. The failed
attempt is retained separately from subsequent checks.

Publication and removal of both local and captured mutex requests use the
same head and guard. A captured head supplies its existing membership to the
physical acquisition helper; the helper must not enqueue a second waiter for
that acquisition. A gate reservation that cannot immediately acquire physical
ownership is released before entering the common queue, preventing a later
queue head from waiting behind its own reserved gate. Optimistic OSQ membership
remains separate until its complete replacement, as required above.

NUMA selection inspects and reorders pending members under the same guard;
it cannot create a private deferred chain. A local-only member is a service
boundary and never a body-dispatch candidate. Current captured waiters are
uncancellable until the new killable capture and exact cleanup are connected;
the presence of shared queue code alone does not enable killable delegation.
The common request's readiness election is separate from condition membership:
phase/drain wakeup is a retry opportunity and never a public acquisition grant.

The runtime first adds request-owned continuation anchors and exact activation
bindings. It keeps legacy activations unchanged until a caller uses those
bindings. Replacing fixed logical-depth/resource limits and enabling nested
proxy requests require the retained-storage extension; an unused anchor type
does not establish either capability.

Four identities have different lifetimes:

1. A queue membership orders one pending condition/acquisition attempt.
2. A stable request owns capture, result, logical nesting and continuation state.
3. An acquisition owns one physical primitive/ticket or exact reader credit.
4. An executor activation temporarily runs a request on one physical stack/CPU.

Their storage can be colocated only with a proved common lifetime. The topology
node's removal, acquisition grant, body completion, return acknowledgment and
storage reuse are separate events.

### Required fields and authorities

These are design fields, not a new exported ABI or implemented struct layout.

| Record | Required information |
| --- | --- |
| Queue header | Per-object raw guard, head, publication/notification epoch, channel/policy identity and bound object incarnation. No global queue guard. |
| Membership node | Prev/next, queue/channel identity, request pointer plus invocation generation, membership state, wait reason, wake mode, and explicit queue/selector-reference ownership. Every simultaneous membership has its own links. |
| Stable request | Unique invocation generation, object incarnation, API family/mode/wait state, immutable may_delegate and reason, logical task, physical submitting task, selected executor, capture/result continuations, canonical packet pointer, source/image/stack/object leases, cancellation/grant state, return status and retirement acknowledgments. |
| Nesting part of request | Logical parent identity/generation, root identity, logical depth, exact acquisition references, child identities/outstanding-return obligations and owner-service mailbox. Parent lineage is independent of physical activation depth. |
| Acquisition record | Unique acquisition generation, object/mode, logical owner, actual physical owner/CPU/ticket, live read-credit identity if shared, release state and exact physical unlock ACK. Multiple requests reference one authority; they do not copy competing ownership ledgers. |
| Activation | Current executor/CPU, physical frame parent, request identity, packet execution-owner token, saved IRQ/BH/preemption/GS context and resume disposition. Physical LIFO rules apply only to active physical stacks. |

Context records separate the logical Native entry baseline, actual submitter/
executor state, and KD-owned pin/IRQ/BH obligations. A nested spin acquisition
adds its own protection to protocol pins already held for a delegated mutex.
Raw preemption-count equality is neither a compatibility proof nor a restore
recipe. Each acquisition consumes only its own recorded adjustments; matching
IF values do not transfer CPU-local ownership.

Queue topology/state changes use the object's raw guard with appropriate IRQ
preservation. Bodies, drainage loops, scheduling, allocation, callbacks and wake
delivery do not execute while that guard is held. An operation touching another
object drops the first guard before acquiring the next; no new cross-object
guard order may manufacture a lock cycle.

The existing mutex has a raw wait_lock, OSQ word and one ring-head pointer in
its 32-byte object: [kd_mutex_types.h:15](../../include/kd_mutex_types.h#L15).
The proposed budget reuses that guard, word and head storage; an intrusive
circular list obtains its tail through head.prev. Preserve the 32-byte
native-aligned mutex and two-word wrapper ABI. The budget is owner 8 bytes,
guard/queue-state word 8, head 8 and existing physical-gate/state words 8.
Wide object incarnation, policy and lifecycle metadata cannot all be added to
that inline budget. Stage (b) must supply an exact offset/storage map using
retained preallocated request/object anchors for cold metadata and prove its
lookup/lifetime contract, including static initialization and atomic entry.
Inline fit is not established by this abstract field table. No new global
hot-path lock or enlarged physical owner word is a substitute for that proof.
Rwsem channel headers can reuse their current wait-head regions. The rwlock's
existing cacheline padding may hold a header, but a four-byte embedded spin gate
cannot simply grow one: layout checks and a deliberate backend adaptation are
required before that migration is claimed.

### Publication, selection and delegation flag

The entry adapter sets may_delegate before publication, after capturing the
actual API/context and obtaining required continuation resources. Zero means
the selector may grant/wake the requesting execution context but may never
dispatch this node's body to another executor. One means permission, not proof
of image readiness, acquisition or execution.
Each queued node obtains this flag through its exact stable request; all of
that request's memberships share one immutable decision and invocation identity,
rather than independently mutable delegation flags on each link.

Pre-publication resource waits are also part of the API contract: killable and
interruptible requests must retain their signal handling there. Do not insert
an uninterruptible pool wait ahead of an otherwise ready acquisition. Reserve
necessary storage before entering the acquisition path where required; preserve
ready-grant priority if a resource/activation delay occurs after real acquisition.
A storage policy that cannot meet both rules is an explicit support blocker,
not permission for a new ordinary-API failure or hidden origin completion.

The adapter may revise the flag while the request is PRIVATE with no published
observer. The flag and its reason are immutable while the invocation is published,
selected or acquired. Heating, task renaming, new images and slot reuse cannot
turn an old false node into a proxy request. A different invocation can set a
different value only after complete retirement and a new generation. Any future
pre-grant reclassification requires explicit withdrawal/retirement and fresh
publication. ACQUIRED work cannot withdraw, reclassify or replay; changing a
byte in a live node is not permitted by this design.

Selection requires both may_delegate and exact current source/image, executor
and IRQ/preemption compatibility. Local-only, callable and unsupported-context
requests use an explicit LOCAL disposition with a recorded reason. A false
child of an already delegated parent stays on its submitting executor; that is
no new child delegation and never an implicit jump to the original task.
That executor obtains the child's exact acquisition through the common queue,
then resumes the captured parent at the post-acquisition CALL result. It does
not manufacture a second captured body for this local child. Even this false
child uses the logical origin's cancellation predicate; calling the old callable
killable helper unchanged would inspect the wrong task's signals when logical
origin and submitter differ.
If an operation genuinely requires the original task/CPU, parent delegation is
unsupported until the general context service can preserve that requirement.

Delegated mmap acceptance cannot be satisfied by marking all killable requests
false. A required-proxy candidate must enumerate an unsupported capability and
remain unaccepted; it cannot quietly complete on origin, invent an API error or
replay a prefix. Source closure cannot revoke an already admitted request's
leases. Acquire the needed leases before publication and retain them through
all descendant execution and return obligations.

All links are inserted completely under the queue guard. No predecessor write
is deferred until after a tail exchange. Selectors either inspect under the
guard or retain an exact selection reference obtained there. No unlocked raw
node-pointer prefetch/dereference is allowed after dropping that reference.
Selected-but-uncommitted nodes remain findable by their cancellation operation;
there is no privately detached, unobservable list of pending requests. A bounded
cohort can preview full request identities, not retain raw node pointers or
origin/packet references across execution of another body. Re-resolve each
identity under the object guard and recheck its generation/state before touching
the node. A withdrawn preview is simply absent. Short selection references
cannot span an unrelated body, sleep or origin pin-response wait. Canceling C
must not await an executor still running B. A selected draining request with
actual tentative gate/phase custody follows the explicit cleanup/ACK path below.

An already published request enters physical acquisition with its canonical
membership token; it must not enqueue a second waiter for the same acquisition.
Today the delegation head calls kd_mutex_local_lock_node, whose slowpath creates
a separate stack waiter ([queue.inc:92](../../kernel_module/mutex/queue.inc#L92),
[kd_mutex_local.c:238](../../kernel_module/kd_mutex_local.c#L238)). Naively putting
both on one FIFO can place that head's second waiter behind itself. The new
adapter performs physical grant and spin-to-park changes on the existing
request. Distinct condition-channel memberships retain separate links, but are
not a second place in the same object's acquisition order.

Preserve admission/handoff policy in Stage (b), including finite NUMA bypass
bounds. The shared mechanism adds no unconditional FIFO guarantee or unbounded
NUMA preference. A local-only node cannot be converted or indefinitely skipped
to sustain a proxy batch. CPU-local retry/OSQ eligibility is not a body grant.

## Killable capture, arbitration and retirement

The acquisition state machine is:

```text
PRIVATE -> QUEUED -> SELECTED_DRAINING -> ACQUIRED -> EXECUTING
            |              |                         |
            +--------------+                         v
                   |                              RELEASED
               CANCELING                             |
                   |                              RETURN_ACK
             CANCEL_ACK                              |
                   +----------------------------> RETIRED
```

SELECTED_DRAINING is tentative ownership of admission work, not successful
public acquisition. For rwsem, actual grant requires the selected exclusive
phase, physical exclusion and a fresh zero-active-reader observation. For
mutex and rwlock, the adapter supplies their corresponding actual primitive
grant predicates. Selection and cancellation use the same guarded decision.

### Decision location and success priority

The logical origin's waiter, a selector, or the acquisition executor can invoke
the decision, always under the exact object's queue guard. The operation:

1. Validates object/request generation and current lifecycle state.
2. Checks/consumes a ready grant or already committed PICKUP first.
3. Only if no successful grant exists, examines the logical origin's API-specific
   signal predicate and can commit CANCELING for an unacquired request.
4. Otherwise leaves the request pending and records its next wake/recheck cause.

This is one arbitration operation, not an unlocked signal test followed later
by independent selection. Readiness includes queue-policy eligibility and real
primitive/phase conditions. Image preparation, executor notification or a pin
handshake must not be misrepresented as successful acquisition or manufacture
an artificial cancellation after a real grant. Separate committed logical
ownership from subsequent execution activation. If proxy activation is not yet
ready after an actual grant, retain the committed acquisition and result; do
not turn it into -EINTR. Physical ownership transfer to its executor remains
exact and exposes no unlocked interval.

The current local example already grants/PICKUPs before checking signals:
[kd_mutex_local.c:258](../../kernel_module/kd_mutex_local.c#L258). Its delegation
counterpart has no such cancellation protocol:
[queue.inc:84](../../kernel_module/mutex/queue.inc#L84),
[waiter.inc:50](../../kernel_module/mutex/waiter.inc#L50). Stage (c) must implement
it, not put a signal test in the old polling loop.

### Returning cancellation while the holder remains locked

For a QUEUED request, remove its membership under the guard, undo only its own
uncommitted reservation, invalidate selection, and release queue/selector node
references before CANCEL_ACK. The preceding owner does not hold the queue guard
through its critical section, so cancellation does not require that owner to
unlock or reach the canceled node. A scheduler notification retains a task
reference, not a stale pointer to the removed stack node.

For SELECTED_DRAINING, CANCELING prevents grant. Wake the selected executor's
cleanup service, which relinquishes its tentative gate/phase and acknowledges
each exact owner operation. Its wait condition includes cancellation and owner
service; it must not keep waiting for the active reader to release. CANCEL_ACK
may wait for this cleanup to execute, but never for the unrelated holder/read
share or the next combiner round. For a nested child, cleanup preserves every
parent acquisition and returns -EINTR only to the child's captured CALL.

Observe the logical origin's signals even when another task physically waits
for a nested request. Origin signal/owner-service notifications wake that
physical waiter through the request's retained service channel. A bounded timed
origin-predicate recheck supplies progress if no direct signal relay exists;
an uninterruptible executor wait without either mechanism is invalid. The
root wait state/relay must continue servicing child cancellation even after
the root itself has committed and can no longer cancel. No mmap-specific
signal hook is permitted.

An executor must not run a potentially blocking foreign body while it is the
sole cancellation/return service for its own uncommitted killable acquisition.
The old combiner habit of serving B before entering A's own body cannot simply
be reused for such A. Use an independent service executor or a proved captured
continuation/ownership transfer that lets A cancel and return while B remains
active. An already committed A cannot cancel, but do not label a tentative
queue/gate selection ACQUIRED merely to suppress its signal. Any foreign work
must also respect actual acquisition ordering; this rule does not authorize
overlapping two same-object exclusive grants.

CANCEL_ACK means all access rights belonging to the canceled invocation have
retired: no publisher, selector, executor, physical owner or callback can still
use its removed node or canceled capture. A root keeps only its return/result
reference, consumes -EINTR, restores native context and returns without a body
or unlock. A child instead transfers its exact failure result and packet token
back to its submitting parent at the post-CALL continuation. That parent retains
its own stack/packet/source references and acquisitions; the root origin may
remain suspended. The canceled request's protected-body prefix effects must be
zero; its nested parent's already committed effects are preserved. After
ACQUIRED, pending signals cannot cancel or report failure for that acquisition;
exactly-once completion is obligatory.

### Reuse and stale references

Each pool/stack invocation has a nonreset generation plus object incarnation.
References and ACKs match the full identity, not just address/CPU/slot. A node
has explicit queue, selector, execution, parent/child, physical-owner and return
obligations. Counters can check their balance but cannot replace named records.
Storage is reusable only after all those obligations and every simultaneous
membership retire. An old cancellation, unlock, source closure or completion
must fail to match a new generation without changing its state.

Separate membership removal from continuation lifetime: a local stack node
cannot outlive its native wait frame; a selected proxy request must retain an
independent anchor before that membership frame can return. Reuse between true
and false delegation roles fully reinitializes discriminators before publishing
the new generation, without blanket packet clears or whole-packet copies.
The current nonreset count_seq is a precedent, not complete new-queue proof:
[kd_mutex_state.h:33](../../include/kd_mutex_state.h#L33).

## Rwsem admission and downgraded read tail

Preserve these current orders during infrastructure migration:

| Current path | Required Stage (b) order |
| --- | --- |
| Unprepared callable/local writer | Physical gate -> local -1 phase -> reader drain |
| Prepared callable/local/signal writer | Local -1 phase -> physical gate -> reader drain |
| Prepared delegated ordinary writer | Positive reservation -> reader drain -> publication |

These are verified in [kd_rwsem.c:253](../../kernel_module/kd_rwsem.c#L253)
and [392](../../kernel_module/kd_rwsem.c#L392). Making just prepared local writers
gate-first while keeping positive cohorts can deadlock: one path holds the gate
waiting for admission, the other admission waiting for the gate.

The explicit, justified change in Stage (d) is an object-wide selected-writer
protocol. Queue reservations move to separate exact request records/counts;
admission represents only an actually selected exclusive phase or open shared
admission. Every writer in that object then selects the gate/phase and freshly
drains readers. Preparation remains quiescent continuation/image capability,
not a separate positive exclusive phase. This change is necessary because
pre-publication drainage cannot remain valid after a delegated downgrade admits
new readers. It changes internal order, not public acquire/release semantics.

Initialize the new protocol before publication, or migrate only after all users,
reservations, owners, credits, frames and ACKs have drained. Do not overwrite
a live positive count with -1, mix old and new adapters on an object, or expose
new cancellation behavior only for selected callers. Stage (c) cannot advertise
killable acquisition through a legacy cohort unless it also rolls back exact
pre-acquisition reservations and preserves its existing ordering.

At delegated downgrade, publish one request-owned read credit; release/ACK the
physical writer gate; end the old exclusive phase; continue the read tail on
the same executor. The retained read record is not the next writer's selected
slot. Next writers freshly drain it, regardless of earlier queue publication.
Final up_read consumes only that credit, even if another writer already owns
the admission phase while draining it. No mutex unlock or admission decrement
is appended to that atomic-compatible operation. Gate ACK at downgrade is not
request completion.

After the tail returns and its exact read release/completion retires, the
executor may freshly acquire for its own pending writer or another request.
The completed origin need not wait for that next acquisition. No implicit
writer acquisition is inserted into the completed caller's code.

Phase admission and reader drainage remain distinct queue instances/reasons.
Do not close admission and wait for queued readers to leave an admission queue;
they need that admission to open. Drain only active credits. Keep the current
atomic read release plus timed drain recheck contract:
[kd_rwsem.c:88](../../kernel_module/kd_rwsem.c#L88).

## Nesting: logical dependencies and physical execution

### Supported intent and Native limits

The target includes distinct-object mutex->mutex, rwsem->mutex,
mutex->rwsem, rwsem->rwsem, mutex->spin/rwlock and spin/rwlock->spin/rwlock
where their Native contexts permit them. Same type is not same object. Same
object exclusive recursion or an atomic read-to-write upgrade is not newly
supported. Repeated shared acquisition requires distinct credit identities
where the Native API/context permits it; no blanket recursion guarantee is
inferred from a read count. The current rwlock explicitly excludes task-context
recursive reads/upgrades/NMI: [kd_rwlock.h:20](../../include/kd_rwlock.h#L20).

Parent nodes carry logical depth and exact acquisition references, not one
anonymous lock count. A nested request has parent identity/generation and the
exact pending source CALL/return token; an outer request has no logical parent.
The logical origin, physical submitter and child executor may be three distinct
tasks. Signals belong to the logical origin. Required CPU-bound owner operations
belong to the actual physical owner.

### Nested request and reader-drain ordering

Before publishing child Q, parent R transfers an exclusive execution token for
the canonical packet to Q and enters WAIT_CHILD. Q references R's source/stack
anchor and required acquisition records, rather than copying them. Only the
current execution-token owner may mutate the canonical registers, virtual source
stack or source-body execution. Separately authorized owner services can update
their exact acquisition/mailbox/ACK records and perform a physical release while
Q owns that token. They cannot mutate Q's packet or resume R's body. Source CALL
words and post-CALL results are consumed once.

For a writer child on semaphore B, retain outer A's actual acquisition and
apply B's full admission protocol independently. A child is not reader-drained
because its parent was selected. If the request still owns a read share of B
and would wait for itself, the queue cannot invent a Native upgrade; preserve
the API limitation. Canceling B before grant leaves A and its read credits
unchanged, and the original caller's error branch performs any subsequent
cleanup.

### Blocking while the parent is pending

The physical submitter can block only if the original API/context permits it.
Sleepable waits are woken for child completion, cancellation and owner-service
requests. The wait loop services observed owner/ACK work before sleeping again.
Spin/IRQ/BH contexts spin with their native context and service only operations
legal in that context. Do not re-enable interrupts/preemption to make an invalid
sleeping acquisition appear valid.

An ancestor acquisition may need release by the parent's physical executor
while the child executes elsewhere. The parent therefore remains serviceable;
a parked executor that only waits for child DONE can create a new deadlock.
The current spin remote wait services such requests:
[spin/slowpath.inc:72](../../kernel_module/spin/slowpath.inc#L72). Extending this
to mutex/rwsem is required; current [remote.inc:25](../../kernel_module/execution/remote.inc#L25)
explicitly excludes mutex frames.

If IRQ/BH/preemption/CPU-local requirements bind a child to its submitter, that
child has may_delegate=false and acquires/continues on that executor, preserving
the parent's delegation. If even executor-local service cannot preserve the
required original context, the reached point is explicitly unsupported. Neither
case authorizes quietly running the parent's suffix on origin.

### Out-of-LIFO completion and release

Acquisition records are released by exact identity, not stack position. In
lock(A), lock(B), unlock(A), unlock(B), A's physical release/ACK can complete
while B remains held. Keep the request, packet, stack/source anchor and B's
record live. Independent requests/owner-service ACKs can finish in either order;
the parent's continuation advances only after its own exact child/result
obligations finish.
Here independent completion means separate requests/owner-service ACKs, or a
Native asynchronous operation with its own packet and lifetime. An ordinary
synchronous nested call chain has one canonical packet and one execution token;
its sibling bodies cannot run concurrently or mutate that packet out of order.
A cancel/ACK for one child cannot retire a sibling or an ancestor.

Physical C stacks still unwind LIFO. Logical parent is not physical frame
parent. Suspend only at a clean dispatcher return that transfers all packet,
source/image and ownership custody into the stable request. Then its temporary
activation can unwind normally. Reactivation binds a new physical frame without
replaying capture or obtaining a fresh permission to execute committed effects.
If an activation still has a live native service stack/ACK pointer, retain that
activation; do not detach it by pretending a field copy retained its stack.

Current physical frames cannot be popped out of order:
[frame_lifecycle.inc:395](../../kernel_module/execution/frame_lifecycle.inc#L395).
Current child retirement also precedes parent DONE:
[remote.inc:122](../../kernel_module/execution/remote.inc#L122). Preserve those
obligations while permitting stable request/acquisition records to retire in
dependency order. Transfer the source lease to the retained request/anchor
before releasing a frame or batch lease.

### Capacity and progress are an explicit implementation gate

Current four CPU mutex slots and eight frame/lock entries cannot simply be the
new logical nesting bound: [kd_mutex.h:35](../../include/kd_mutex.h#L35),
[kd_exec.h:26](../../include/kd_exec.h#L26),
[lock_ledger.inc:79](../../kernel_module/execution/lock_ledger.inc#L79).
Returning -E2BIG or waiting for storage held by one's own ancestor would change
ordinary API behavior. Queue membership storage, retained requests and acquired
owner records therefore have separate resource accounting.

Use preallocation and explicit storage transfer. A local-only synchronous waiter
can use its live physical wait frame; a published proxy must reserve stable
request/packet/service storage before it can be selected. Acquisition records
may be rooted in the bound object's retained metadata, so a long list of held
locks does not require an eight-entry copied ledger. Resumable activations must
not retain an entire CPU frame slot merely because a request is pending.

The allocator/reservation proof for all supported nesting depths is not supplied
by existing code. Stage (b) must specify exact pool/stack sizes and a progress
path that neither waits on ancestor-owned slots nor exposes a new API failure.
Atomic/IRQ paths cannot allocate or sleep for storage. If that proof is absent,
retain the existing physical backend for that context and enumerate the missing
proxy capability; do not claim generalized nesting or silently return to origin.
Depth-nine and exhaustion fixtures are mandatory. This is a declared support
gate, not a claim that changing a constant resolves the problem.

## Explicit execution gaps beyond the queue

| Source-backed current gap | Required support / limitation |
| --- | --- |
| Ordinary capture is void: [kd_rwsem_api.c:30](../../kernel_module/kd_rwsem_api.c#L30) | Integer killable capture with separate success/failure continuations; published cancellation protocol before it is enabled. A local-only wrapper does not count. |
| Current frames are tied to one physical owner/LIFO: [kd_exec.h:169](../../include/kd_exec.h#L169) | Stable logical requests, explicit activation suspension and owner services. Current generalized nested delegation is absent. |
| Native CALL handling runs the origin suffix: [exe.c:704](../../kernel_module/exe.c#L704) | General executor-side resumable CALL/context services. Do not use this route as a successful required-proxy outcome. |
| Scheduler/CPU/MM/TLB boundaries: [kd_native_terminals.def](../../include/kd_native_terminals.def) | Exact reached helper/instruction/context evidence and equivalent executor service. Equal saved IF values alone do not establish CPU/TLB/RCU equivalence. |
| Existing scalar hostcalls require task-independent, atomic behavior: [hostcalls.inc:122](../../kernel_module/execution/hostcalls.inc#L122) | Cannot label allocation/nested sleeping helpers as those services without a new contract. |
| MM builtin strips delegation: [prepare.py:61](../../kernel_integration/mmap_lock/prepare.py#L61), [pool.c:6](../../kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/pool.c#L6) | General provider/image availability before activating the builtin. No syscall-specific adapter or startup-local route counted as delegation. |

These are absent capabilities, not proofs that every containing critical
section is inherently impossible to delegate. Retain useful translated prefixes
and service only the reached point where an equivalent executor service exists.
A mandatory instruction such as PAUSE/fence must execute faithfully at every
occurrence; a runtime exit every spin iteration is not an acceptable substitute.
Where equivalence cannot be established, report the precise point/context and
leave the required-proxy candidate unaccepted. Public APIs do not gain a new
unsupported-operation return code.

## Validation matrix and staged delivery

The matrix remains the complete target, rather than a list of completed checks.
The [Stage (b) infrastructure record](../../bench/results/10.176.26.71/tests/unified-queue-20261102/README.md)
reports the focused queue/local checks and four returned-JIT smoke points now
run, with each source version and failed attempt retained. Existing local
receipts do not satisfy the new delegated killable, nested-executor, read-tail,
capacity or MM rows. Those support/acceptance gates remain open.

| ID | Case | Required oracle | First required stage |
| --- | --- | --- | --- |
| Q1 | Empty/single/multiple-node publish, dequeue and handoff | Complete guarded links; no delayed publisher after unlink; exact owner flags and generations | (b) |
| Q2 | Mixed delegable/non-delegable head/middle/tail; false->true and true->false slot reuse | False nodes never selected for other-executor body execution; local children resume the parent on the submitting executor; new role only in a retired/new generation; explicit disposition/reason | (b) |
| Q3 | Optimistic spin -> legal park, abort and wake/recheck races | One request/membership authority, exact native context, no lost wake or abandoned link | (b) |
| Q4 | Phase channel vs drain channel, legacy OSQ coexistence | Distinct predicates/links; OSQ IDLE is not body grant; no phase wake replaces drain proof | (b) |
| Q5 | Prepared/unprepared ordinary/callable/signal/try/cleanup/API aliases | Baseline ordering/results preserved before selected-protocol migration; no new exported errors | (b) |
| Q6 | Published head contends physically and changes from spinning to parking | One canonical acquisition membership, no recursive self-enqueue behind its own node | (b) |
| C0 | Signal while reserving capture/continuation storage before publication | Correct killable/interruptible result and ready-acquisition priority; no uninterruptible pool wait, partial publication or new API error | (c) |
| C1 | Fatal cancellation of published head/middle/tail while holder stays locked | -EINTR before holder release; zero prefix; successor survives; exact CANCEL_ACK/retirement | (c) |
| C2 | Nonfatal killable signal; interruptible signal; signal initially pending | Correct API predicate; ready success first; no killable cancellation for nonfatal signal | (c) |
| C3 | Selection/drain vs cancellation with holder/readers deliberately retained | Tentative selection cancels and rolls back without waiting for those releases | (c) |
| C4 | Ready grant/PICKUP racing fatal signal, including delayed image/pin/activation readiness, and fatal signal after commitment | 0 for an actual ready grant, exactly one body and no later cancellation; activation delay cannot manufacture -EINTR | (c) |
| C5 | Capture return/register pressure and failure continuation | Explicit JIT EAX0; exact -EINTR; no replay/body/unlock after failure; two-word ABI unchanged | (c) |
| C6 | Delayed selector/wake/ACK against node reuse; executor busy in another body while a previewed request cancels | Cancellation returns while that holder/body remains active; immediate slot reuse; full identity rejects old generation; no stale node/packet/stack access or false completion | (c) |
| C7 | Executor has its own uncommitted killable A while foreign B can remain blocked | Either B is not assigned to that sole service, or A can cancel/return independently while B stays active; no phantom committed grant or requirement that B finish | (c) |
| N1 | Distinct-object mutex->mutex, rwsem->mutex, mutex->rwsem, rwsem->rwsem; uncontended/contended | Correct parent/depth/owner records; actual child proxy where enabled; local-only child never dispatched to another executor | (b) infrastructure, (c)/(d) execution |
| N2 | Mutex->spin/rwlock and spin/rwlock->spin/rwlock; IRQ/BH match/mismatch | Correct physical owner CPU/ticket, Native baseline and protocol/nested pin restoration; no sleeping in an invalid context or origin suffix substitution | (b)/(d) |
| N3 | Killable/interruptible nested child queued and draining, with both delegation-flag values and a committed parent | Child-only failure/rollback; parent effects/acquisitions preserved; origin-only fatal cancels, executor-only fatal does not cancel that child's logical acquisition | (c) |
| N4 | Nested committed child against pending fatal signal | Child succeeds once; parent resumes at exact post-CALL packet; no entry replay | (c) |
| N5 | Writer child while unrelated readers remain; child downgrade | Fresh target-object drain; no parent drain reused; exact child read credit blocks later writers | (d) |
| N6 | Outer-first release, independent request/service ACKs reversed, delayed physical unlock ACK | Acquisition release independent of request/physical LIFO retirement; one shared-packet execution token; no premature parent/source/packet reuse | (b)/(d) |
| N7 | Owner-service publication racing executor sleep/child return | Ancestor unlock/ACK progresses without mutating the child's canonical packet; no wait solely for child DONE or artificial dependency cycle | (b)/(c) |
| N8 | Three levels, depth nine, pool pressure and ancestor-held capacity | No hard public depth error, own-ancestor slot wait, blanket packet copy or new ordinary-API failure | (b) support gate |
| N9 | Same-object recursion/upgrade and permitted repeated shared acquisition | No invented exclusive recursion/atomic upgrade; distinct identities for each legally acquired read share | (b)/(d) |
| D1 | Delegated killable writer -> downgrade -> executor read tail | Other-task write/read witnesses, continuous read credit, exact returned completion | (d) |
| D2 | Same executor resumes pending writer with another reader still held | Must freshly acquire gate/phase and drain that reader; no gate-only reacquisition or stale phase decrement | (d) |
| D3 | Atomic final read release and non-owner transferred release | No sleeping/queue guard/scheduler lock on atomic path; exact credit and lifetime; timed drain progress | (d) |
| L1 | Source closure, origin exit attempt, nested live owners, object reuse | Retained exact leases/ACKs; no generation confusion or retirement while any dependency remains | (b)-(e) |
| E1 | Unchanged mmap1_threads and mmap1_processes, kd_mmap=on | Actual syscall/backend identity; killable path; other-task read-tail return and fresh writer acquisition; final drain | (e) |
| E2 | kd_mmap=off and matched nano comparison | Native route unchanged; one measurement round per point; every gain/loss retained without pooling versions/topologies | (e) |

Stage (b): implement the common queue/storage/adapter infrastructure with existing
behavior preserved, retaining legacy protocol adapters until their replacements
are complete. Stage (c): implement result-returning killable capture and the
actual cancellation/grant/retirement path; no uncancellable published writer is
accepted as this stage. Stage (d): complete selected-phase encoding and general
executor writer/read-tail/nested transitions. Stage (e): build and validate the
combined kernel/module candidate, then unchanged mmap1 on the VM with proxy
proof and matched performance evidence. Earlier stages may run focused VM builds
and tests for their own artifacts; they do not count as Stage (e).

All source/Git/static review runs on 380G10. All compilation, unit/kernel tests,
modules, daemons and timing run only on VM 10.176.26.71 after the maintained
idle/snapshot/headroom/identity gates. Freeze inputs while running. Preserve
every failed attempt. Stop and report after each stage; do not promote an
unaccepted candidate or use a local-only mmap1 completion as proxy proof.

Stage (a) acceptance is the committed model, field/lifecycle decisions,
migration mapping, explicit current limitations and this validation matrix.
It establishes no build, performance, cancellation or nesting implementation
claim. The capacity, context-service and builtin-availability gates above remain
visible prerequisites rather than silently weakened behavior.

## Stage (b) retained continuation infrastructure

The implementation in [kd_exec_cont.h](../../include/kd_exec_cont.h) and
[continuation.inc](../../kernel_module/execution/continuation.inc) adds retained
execution storage backed by a pointer to the common kd_wait_request. That common
record remains the only acquisition/cancellation authority. The continuation
does not repeat the signal election or change its state through an object guard
after public release. Queue adapters own those transitions and the old-guard
access retirement required before rebinding to retained lifecycle storage.

The internal interfaces are:

- kd_exec_cont_init: bind a private common request to its canonical packet;
  retain the root's source/module, task and task-stack references. Child anchors
  share those references through explicit parent/root identities and child links.
- kd_exec_cont_bind, kd_exec_cont_suspend and kd_exec_cont_resume: use the
  anchor's stable frame as a temporary physical activation. Suspend requires the
  current top frame and no live native/remote stack service. It unbinds without
  copying the packet, completing the request or dropping the source lease.
- kd_exec_cont_child_begin and kd_exec_cont_child_acquired: transfer the one
  packet execution token and consume the exact successful acquisition CALL once.
- kd_exec_cont_child_return: return a canceled child's -EINTR or a LOCAL child's
  acquisition result to its physical submitter's parent continuation; a proxied
  child returns only after its own completed body endpoint. These are different
  dispositions, and neither moves the parent's suffix to origin.
- kd_exec_cont_owner_get, kd_exec_cont_owner_borrow and kd_exec_cont_owner_put:
  retain references to independently authoritative acquisition records, with
  generation validation and physical-release ACK callbacks. A reference moved
  to a continuing parent keeps its creator anchor live until that exact
  reference is released. A reference is not a physical acquisition.
- kd_exec_cont_return and kd_exec_cont_retire: separate unbinding/body return
  from final reuse. Children, owned references, transferred-reference storage,
  memberships, selections and return state must permit retirement before source
  or stack references are dropped.

The matching put_task_stack helper is resolved once from core text. Its absence
disables new retained capture initialization explicitly; it does not prevent
legacy provider initialization or add a public lock error. The resolved release
pointer is retained by the root that acquired the stack reference. New retained
frames use FULL packet returns. Legacy frames initialize their optional anchor
pointer to NULL and retain their existing ABI2 minimal completion route.

These helpers are bounded infrastructure. Public killable capture, owner handoff,
old-guard handover ACK, resumable MM CALL services and new proxy-child dispatch
are not enabled by this addition. The existing lock ledger and its consumers
remain unchanged; the new reference lists do not claim that every consumer has
migrated. Existing four-slot storage and eight-entry physical-frame/lock limits
remain relevant until the separate resource and consumer migration is complete.
No generalized depth, cancellation, read-tail execution or performance claim
follows from the presence of these helper interfaces. Static review is distinct
from the required VM compilation and runtime checks.

### Retained-pointer storage correction

The first infrastructure checkpoint, 6277cb9d, appended an eight-byte anchor
pointer to kd_exec_frame. On the supported x86-64 layout this changes the frame
from 656 to 664 bytes and the 64-byte-aligned kd_spin_continuation from 704 to
768 bytes. The pointer is unused by current capture, so that extra stride has
no functional purpose. The source correction below preserves the original
frame and spin-record sizes. The final VM build passed the exact size/offset
assertions and all four returned-JIT functional points; performance remains
unmeasured.

The exact storage budget is:

| Field | x86-64 byte offsets | Meaning |
| --- | --- | --- |
| Existing hot discriminator byte | 39 | spin_kind, spin_regs_decoded and rwlock_admitted keep their existing bits; has_continuation uses the next spare bit. regs still begins at 40. |
| saved_combiner / mutex_mixed union | 280–367 | Existing 88-byte union; its following jit_lock_addr still begins at 368. |
| mutex_mixed.spin_sequence | 280–343 | Existing eight exact spin sequences, unchanged. |
| transfer_requested / transferred / picked_up | 344 / 345 / 346 | Existing mutex transfer flags, unchanged. |
| Mutex-only retained pointer | 352–359 | Aligned pointer after the flags/padding; mutex_mixed grows from 72 to 80 bytes and remains smaller than saved_combiner. |
| Remaining union tail | 360–367 | Still available to the existing saved_combiner layout. |
| Frame end | 656 | Remove the appended pointer; image remains at 648. |
| Spin continuation end | 704 | diag 656, storage 664, result 672, retired 676, jit_context 680 and queued_at_ns 696. |

The new pointer overlaps saved_combiner.local_queue_head. Legacy spin frames
must therefore never interpret it. kd_exec_frame_continuation first tests the
hot discriminator and returns NULL without reading the union pointer when the
bit is clear. Its pointer read uses READ_ONCE inside the selected branch.
kd_exec_frame_set_continuation publishes the pointer before setting the bit;
clearing the bit does not write any spin combiner bytes. All legacy frame
constructors clear the bit. Only a retained mutex frame sets it. No packet,
wrapper word, capture behavior or ownership protocol changes in this correction.
Compile-time offset/size checks accompany the source for the next VM build.

The first returned-JIT smoke preparation stopped because the benchmark's
observation patch still expected kd_exec.h immediately followed by
kd_source.h. The retained-frame header now sits between those includes.
Update that exact patch context while retaining all observations and the
zero-fuzz application requirement. No workload or JIT body ran in that failed
preparation; it is retained independently of subsequent attempts.
The initial edit left four leading context lines and three trailing lines;
the exact patch still refused that hunk. Regenerating the hunk with three
lines on each side passes a full zero-fuzz static dry run. Neither preparation
failure is a workload result.
