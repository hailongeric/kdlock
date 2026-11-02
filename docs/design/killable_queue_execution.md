# Stage (c): killable capture and exact request retirement

Branch: `codex/unified-lock-queue-c`.
Parent checkpoint: `28d576ba4bbba8d8539018de36bfbac854dd9996`.
Production baseline remains `7231ddf0963ff2cc730590c09cc81e7f96f93095`.
The independent changes on `master` are not part of this candidate's evidence.
This design precedes code. The [shared queue model](unified_lock_queue.md)
remains authoritative for API behavior, ownership and retirement requirements.

## Implementation order and necessary dependencies

1. Extend the common request with exact tentative-cleanup custody and terminal
   guard transfer. Add one admission driver whose actual-ready callback covers
   the physical mutex plus the lock-specific phase and active-reader predicate.
2. Convert rwsem writer admission on newly initialized/quiescent objects to a
   selected exclusive phase for every writer entry form. Do not mix this with
   positive cohorts. This part of Stage (d) moves forward because Stage (c)
   cannot commit at the embedded mutex acquisition before reader drainage.
3. Add independent general service executors, queued/preemptible root capture,
   selected origin stack transfer, integer continuation entry and exact result
   retirement. A worker has no pending public acquisition of its own.
4. Connect nested lock controls to the same admission driver. A nested LOCAL
   request remains on its submitting executor, uses the root origin's signals
   and resumes the parent JIT at its exact post-CALL result. Its protected body
   continues in the already delegated parent; no suffix moves to origin.
5. Connect the release/downgrade routes required by the newly captured API.
   A prepared killable caller already supports downgrade through its callable
   route; capture must not remove that behavior. Exact writer-to-read credit
   handling therefore moves forward as necessary. The subsequent complete
   writer/read-tail campaign and enabled-MM integration remain later delivery.

No new ordinary acquisition error or local-only capture wrapper constitutes
completion. No enabled path may bypass killable cancellation before commitment.
Implementations and tests are reported separately from this design.

## One readiness and cancellation election

An admission contains a canonical request and acquisition membership, an exact
tentative physical owner, a selected phase lease and a pending-cleanup token.
The object's raw guard serializes selection, actual readiness and origin-signal
arbitration. A successful callback means actual physical ownership, an eligible
phase and a fresh zero-reader observation, not merely queue selection, image
readiness, pin readiness, a reservation or mutex PICKUP alone.

The callback attempts the actual grant first. For a retained reader, PICKUP is
only tentative: `PICKUP + reader1 + fatal` cancels and rolls back; `PICKUP +
reader0 + eligible phase + fatal` succeeds. Nonfatal signals stop optimistic
polling but do not cancel TASK_KILLABLE. TASK_INTERRUPTIBLE uses the same driver
and its own signal predicate. A committed request cannot subsequently return
`-EINTR`, including while image/stack/executor preparation is finishing.

Cancellation removes acquisition and condition links under the object guard.
The pending-cleanup token prevents CANCEL_ACK until the exact tentative owner
has released/acknowledged its gate and only its own phase lease. Cleanup never
waits for unrelated readers or the preceding holder. A queued request has no
executor reference spanning another body's execution and can retire while that
body remains active. A selected request's service loop handles its own
cancellation; it does not run an unrelated body before finishing cleanup.

The origin's task determines signals. The physical submitter and actual owner
determine execution and release. Origin-owned tentative custody uses an exact
owner-service request/ACK when an executor owns request arbitration. Neither
task silently performs another task's physical unlock.

## Selected rwsem phase and public entry forms

All writer forms participate in the same gate/selected-phase protocol on an
object. Queued requests do not increment admission. Admission is open or names
one selected exclusive phase; separate opaque request identity/generation and
physical-owner fields identify its exact lease. Ordinary/callable/signal/try/
cleanup callers never infer phase authority from the counter alone.

Callable and cleanup entries remain conventional C calls and are nondelegable.
They use a stack wait record, transfer successful ownership to the retained
physical/object phase record, and retire the wait record before returning.
Trylock performs a bounded nonblocking equivalent with complete rollback and
no queue, allocation or proxy dispatch. Preparation is quiescent continuation
capability, not a second admission encoding. Existing ordinary read entry and
atomic try/rollback/up_read rules remain.

Writer release consumes the exact acquired record. The origin does not perform
an extra phase decrement after a service executor has already released it.
Typed writer release is a recognized compiler-clobber endpoint; existing
function-pointer/cleanup signatures and evaluation behavior remain unchanged.

## Root execution, storage and the C7 dependency

Serving foreign B before the executor's own uncommitted killable A body can
strand A's cancellation. Calling A acquired first is also invalid if B is then
granted an overlapping same-object exclusive interval. The new service task
has no such public A. It acquires and executes B alone, finishes B's physical
release and result handoff, then considers another request through fresh
admission. It never manufactures a public grant to retain combining authority.

Before selection, a captured caller reserves stable cold request storage and
remains preemptible. The preallocated CPU/slot sidecar is the ordinary case;
private spill storage is obtained before publication when those slots are busy.
Allocation failure is retried before publication rather than returned as a new
public API error or made dependent on an ancestor releasing its slot. This
spill policy needs allocation-pressure validation beyond this stage's focused
checks. Service notification membership is distinct from object
acquisition order: it schedules work and holds no hidden acquisition grant.
Dispatcher preview uses identity/generation only; no queued node or packet
pointer survives across a foreign body. Cancellation removes this notification
membership as part of exact retirement.

The descriptor already resides outside capture-helper frames. The
origin switches to its separately reserved protocol stack before publishing
stack readiness. Capture initializes scalar entry fields and exact
leases/memberships; it does not copy a whole virtual register packet. Before
commitment, cancellation returns through intact native helper frames. After
commitment, completion resumes the captured post-release packet once.

An origin pins only for its selected proxy interval, including in-progress
delegated lock/API service, not while the request is merely published. Other
queued callers remain preemptible. Selection and stack preparation precede the
body; there is no queue-response wait inside a body batch. Service tasks avoid
the selected origin CPU and retain only the CPU context required by an active
JIT activation. Blocking nested admission first suspends/unbinds that activation
so the actual sleeping mutex owner can schedule/migrate without retaining an
unrelated CPU frame slot.

The implementation must state its capacity proof. Existing oversubscription
limits are not expanded by this stage. No root may wait on a slot held by its
own ancestor. LOCAL nested admission needs no additional root capture slot or
service task. Persistent acquisition metadata uses retained storage/spill
lifetimes rather than turning the old eight-entry ledger into a public nesting
limit. Depth nine and out-of-order releases are explicit checks; arbitrary
stack/resource pressure remains unvalidated until a concrete storage/progress
proof and corresponding checks exist. Such limits cannot become new public
`-E2BIG`, `-ENOMEM` or silent origin completion.

## Actor, guard and result lifetime

A transport actor token separates origin arbitration from selected executor
arbitration. An origin must acquire that token before caching the object guard.
Once selected executor custody wins, the origin only polls retained transport
state, reports signals and services authorized physical-owner commands. The
executor checks the logical origin's signal predicate. Token handoff supplies
the old-guard-access retirement proof; changing a guard pointer alone does not.

After all object-guard users, queue links, selection and tentative cleanup have
retired, transfer lifecycle custody to a retained guard before exposing a final
release/cancellation result. Never reacquire an object guard after cancellation
return or the final read-credit decrement can permit object destruction.

Body completion publishes RELEASED plus its exact packet/result. Origin result
consumption supplies RETURN_ACK. Final anchor/stack/source reuse follows that
ACK and all child, acquisition and owner-service retirement. The old legacy
node-free-before-owner-ACK path is not the new retained path.

## Nested calls and downgrade

Each child has an exact parent/root invocation, logical depth, CALL target,
source stack/return word, request generation and acquisition identity. A LOCAL
child publishes on its target lock, blocks only in a Native-legal context and
uses the origin's predicate even when its physical waiter is another task.
Cancellation returns `-EINTR` to that CALL with zero child-body effects; parent
effects/owners remain. Success sets EAX zero, consumes the CALL once and resumes
the parent's immutable image. Source closure cannot veto or replay a committed
continuation. Parent waiting continues to service retained owner ACKs.

Logical release is independent of physical LIFO activation retirement. Released
records stay retained while children or return/services reference their storage.
An earlier lock may release before a later one without losing either identity.
Exclusive same-object recursion and sleeping acquisition under a held spinlock
are not made legal by this mechanism.

At downgrade, publish the request's read credit before exclusive release, finish
the physical writer ACK, reopen phase admission, and keep executing the read
tail on the executor. Matching up_read consumes that credit without modifying
a successor writer's phase. Any subsequent writer freshly obtains its gate,
selected phase and active-reader-zero observation. No writer reacquisition is
hidden in public up_read. Ordinary direct read acquisition starts no proxy
body; a nested LOCAL API runs on the existing submitting execution context.

## Focused VM validation

- Actual admission fixture: busy holder, retained reader, exact rollback,
  origin/executor signal distinction, and the two PICKUP/readiness cases.
- Compiled integer capture: register pressure, native `0/-EINTR`, explicit
  success EAX zero, no body/unlock after failure and no replay after commitment.
- Existing local mutex/rwsem probes once after affected changes, retaining
  their cancellation, rollback, downgrade, publication and drain assertions.
- One generic proxy fixture: canceled head/middle/tail before holder release;
  selected-drain cancellation before reader release; actual other-task success;
  committed-pending-signal success; nested cancellation/success, parent effects
  retained, out-of-order release and depth nine.
- Existing one-point functional JIT smoke for affected lock families. No full
  Python inventory, Nano grid, syscall performance comparison or mmap1 timing
  is part of this focused Stage (c) validation.

Each result binds source, kernel, topology, actual origin/executor, invocation,
grant, returned completion and final retirement. Entry counters are not proxy
completion proof. Any unsupported reached context/helper is enumerated with
source evidence and keeps broader integration unaccepted. No context-sensitive
MM helper, builtin image startup or syscall-specific adapter is concealed by
this lock-protocol implementation; those remain explicit integration work.
