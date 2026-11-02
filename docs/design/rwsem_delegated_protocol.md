# General delegated rwsem protocol

## MM continuation implementation, November 3

Branch `codex/unified-lock-queue-mm` starts at
`11eb4250661c092e62f6bf9168e87b938041b274`; its tested Stage (c) implementation
is `9370ae4e635bef487d16be475e37a5a1f9e27d7b`. This continuation is authorized
to build/install a distinct Linux 7 image and run actual unchanged mmap1 through
system calls. The older local-only MM policy below and in the captured branch
instructions does not prohibit this explicitly requested general protocol work.
Native MM bodies remain unchanged. This section precedes implementation; none
of the following capabilities is established by the earlier generic fixture.

The target sequence is delegated write, actual downgrade, delegated read tail,
exact read release and then fresh admission for subsequent writer work. A
downgrade is a continuing ownership interval, not completion or a scheduling
request. A following same-object writer cannot run while its executor retains
the prior read credit. Final release still ends that caller's captured root;
worker reuse for another request is separate from lock ownership.

### Returning primitive CALL service

Translate the original MM/VMA/maple instructions and ordinary callees. Calls to
primitive APIs whose allocator, task or CPU context belongs to origin O need a
returning transaction. Never designate `do_mmap`, `mmap_region`, munmap teardown
or another MM body as such a primitive to conceal the entire critical section.
The service resumes the same executor E and immutable image at the exact CALL
successor; it is not an original-task suffix or another public acquisition.

An immutable descriptor names the exact target, up to six word arguments,
scalar/void result and a balanced-origin context contract. Six arguments are
an initial service ABI limit, not a new lock-API error. A reached unsupported
signature remains explicit integration work; it cannot be guessed or silently
passed different arguments. Stack-argument and pair-spanning IRQ/preempt/RCU or
Native-lock operations require additional exact contracts. A merely matching
function name cannot establish those contracts.

Each retained root owns a preallocated transaction: root identity/generation,
monotonic service sequence, exact target, source SP/CALL return word, context
baseline and REQUESTED/RUNNING/DONE/CONSUMED phase. E suspends/unbinds and drops
only engine-owned pins before transferring packet custody. O services only its
own matching request. The source CALL word stays untouched on the source stack.

Potentially sleeping Native calls cannot execute on O's independent shadow
stack: it is not `task->stack`. A general assembly bridge saves the shadow
activation and switches below the current source SP on O's retained Native
task stack while E is suspended. Only there may it remove O's engine preempt
pin and invoke the actual helper. It captures volatile return registers/flags
before restoring that pin, then leaves the Native helper frames before
publishing DONE. E validates transaction identity and context, regains packet
custody, consumes the CALL once and resumes its exact immutable continuation.
The first fixture must witness a sleeping primitive on O's own task stack and
post-service body effects on the same E, with no root completion at the helper.

Keep acquisition priority and killable cancellation unchanged. Before actual
grant O's signal and real gate/phase/reader readiness arbitrate together. After
grant a helper cannot turn committed body effects into failed acquisition.
Nested general lock calls from a Native service must preserve their usual local
task semantics and must not recursively capture the service infrastructure.

The source-checked balanced roster additionally covers the ordinary per-CPU
counter update, per-VMA writer exclusion and detach wait, perf mapping event,
conditional reschedule entries and RCU callback enqueue. These are existing
primitive APIs, not replacement MM bodies. Their Native invocation must finish
with its entry IRQ/preemption context restored before E resumes; in particular,
`__vma_start_write` finishes its temporary `rcuwait` task publication even when
the wait condition was already true. The public RCU enqueue APIs do not retain
an RCU read-side interval on return. Neither `__rcu_read_lock/unlock` nor Native
spin acquire/release is designated balanced: their state spans later source
instructions and requires a separate retained context record. The exact roster
and argument/result contracts are maintained in `include/kd_service_calls.def`.

The next bounded continuation adds exact Native preemption-reschedule entries.
The captured `perf_trace_mmap_lock_acquire_returned` DEC branch calls
`__SCT__preempt_schedule_notrace`; this is conditional on both tracing and a
pending reschedule, rather than a mandatory call in every mmap1 pair. The
ordinary and notrace functions, their assembly thunks, static-call entries and
dynamic-key functions are zero-argument, void APIs. Their actual selected
Native implementation must run on O; a descriptor must not replace the source
branch with an invented reschedule. Context 10, SCHEDULE_ORIGIN, requires zero
retained NativeSpin/PREEMPT pins and permits retained RCU only with
CONFIG_PREEMPT_RCU. Unlike a general balanced helper, involuntary preemption
may validly occur inside a preemptible RCU read interval. The Native task-stack
bridge removes only the runtime pin, and the return validates the same IRQ,
pin and RCU baselines before resuming E. E remains preemptible while O services
this scheduling transaction. The helper and its source CALL return normally;
there is no suffix or additional public lock acquisition.

Two existing public admission primitives also receive ordinary balanced O
descriptors: `security_vm_enough_memory_mm(struct mm_struct *, long)` returns
int, and `security_mmap_addr(unsigned long)` returns int. The former is reached
for successful private writable, accounted mappings, the latter after a valid
address is selected. Their callback dispatch and the associated accounting use
O's actual task context. They do not create/remove VMAs or replace an enclosing
MM body. The captured definitions are at `security/security.c:739` and
`security/security.c:2623`; their lock-held call sites are `mm/vma.c:2433` and
`mm/mmap.c:862`. This source extension requires separate focused validation;
the version-16 read checkpoint does not establish these new paths.

### General per-object execution provider

The current builtin MM pool and adapter have no capture/image entry. Add a
versioned ordinary rwsem provider interface, with immutable per-object binding
before publication. A provider-bound object routes every acquisition, release,
try, downgrade, assertion and read operation to that provider's general core.
Old/early objects continue on their builtin core; never exchange pools or owner
records merely because two layouts have the same size. `kd_mmap=off` keeps its
Native route. The MM layer contains only ordinary lock APIs and minimal binding,
control-entry and lifetime glue, with no workload-specific selection or body.

The provider reference belongs to the object until destruction. Registration
controls new binding only; unregister cannot change live objects or discard
their module references. A copied mm initializer must overwrite a copied
provider pointer without dropping the source mm's reference, then take its own
new binding reference. Verify the existing union, `use_kd` and new pointer
offsets and overall layout at compile time. Setup serialization is not a new
acquisition lock.

Inline lock frontends expose the general SP/IP/BP clobber contract at the actual
caller's frame. Integer success explicitly defines EAX zero; callable forms
retain conventional C results. Register exact typed facade control identities
so the runtime and translator agree on acquire/release/downgrade endpoints.
Ownership assertions use exact retained object/request/phase identity: E may
prove its physical ownership, and O may prove its logical ownership only while
authorized to service that exact continuation. A locked/count hint is not an
owner query.
Ordinary facade queries/assertions are also explicit returning primitive
bindings. Their metadata distinguishes them from acquisition/release controls,
and declares one object argument plus a scalar or void result. This prevents
the translator from following an opaque provider function pointer. An origin
assertion runs only during the exact authorized helper transaction, where the
existing retained logical-owner query proves its object/request/phase ticket.
No assertion is weakened to an aggregate locked hint or omitted from execution.
The three ordinary/nested/killable MM acquisition API wrappers must remain
`__always_inline`: an outlined wrapper would capture its own returning frame
before the protected caller's body. Only these API declarations change;
source preservation normalizes those declarations explicitly and compares
their original instructions and all Native MM bodies separately.

Provider activation and each immutable object binding also own a source
residency lease. Acquire the object's lease inside the builtin registration
critical section before exposing its provider pointer; release it exactly once
with that binding at destruction. Source retirement must test these leases
under its own admission guard and return busy without closing admission while
any lease remains. Closing first would strand still-live bound objects on a
provider that can no longer admit their next ordinary acquisition. Deactivation
stops new binding before releasing activation's lease. Lease counts describe
exact matched factory/destructor references; they never authorize lock
acquisition, ownership or approximate request retirement.

Object retirement and continuation retirement are separate. The module core's
`kd_mutex_waiters_idle` checks the exact `counted_lock` waiter marker; it does
not treat a retained node's `lock` packet metadata as active object use. The
captured service path sets `node->lock` but does not publish `counted_lock`.
Therefore a released outer object's stale packet key cannot by itself veto its
provider destructor while a different nested owner keeps the continuation
alive. Keep the legacy counted-marker checks unchanged, and retain source,
task-stack, packet and frame references through the root's actual return ACK.
An object may retire only after its physical gate, phase, queues and final read
credit have completed their existing exact final-access ordering.

Bootstrap is a separate gate. Prepare immutable core lock-site images before
enabling new provider bindings; keep translator/controller infrastructure on
its existing object backends. No published delegated MM request may revert to
local body execution for a cold image. A cold entry, translator dependency or
unsupported reached operation must be identified and resolved explicitly before
claiming default delegated mmap/munmap. Initial local eligibility is not proxy
proof. Missing GS/per-CPU/context handling cannot be excused by trusted source.

### Retained Native inner-lock intervals

An untouched anonymous mapping can share page-table ancestry with a neighbouring
mapping. Consequently, munmap can reach a Native PTE lock and RCU read interval
even though mmap1 never touches its own pages. This branch cannot be excluded
from the protocol merely because an empty-page-table fast path exists.

The captured Linux 7 objects retain callable `_raw_spin_unlock` and
`__rcu_read_unlock` boundaries in the relevant PTE loop. This permits a general
Native API extension: O acquires the exact inner lock/RCU authority, a retained
record names its object, kind and acquisition/service generation, and E
continues the translated body only with compatible IRQ/preemption state. O
executes the matching Native release once; its record and any CPU-context
authority survive until the actual release acknowledgment. Conditional failed
acquisition creates no owner record. Counters can describe context depth but
cannot replace individual Native lock records.
An ordinary trylock of an already held object is still invoked on O and may
return false; it is not treated as recursive blocking acquisition. Its unused
candidate record cannot alter the earlier acquisition's exact authority.

A paired Native API is distinct from the balanced primitive contract. The
runtime must retain E's immediate execution capacity across acquisition and a
held Native spin interval; unpinning E after O obtains a spinlock can strand its
unlock behind another spinning executor. No instruction-budget scheduling or
sleeping is allowed while the source's Native atomic context forbids it.
Balanced helper calls inside that interval must observe O's actual retained
Native context after removing only the engine-owned pin. Preserve actual
Native signals, conditional results and all enclosing KD ownership records.

The module descriptor context values distinguish balanced task calls (1),
balanced nonblocking calls (2), conditional PTE spin-plus-RCU grant (3), ordinary
spin acquire/try/release (4/5/6), RCU acquire/release (7/8), and conditional PTE
RCU-only grant (9). The sysfs row shape is unchanged. Eight cold records per
root are a storage fast path, not an API limit: a further acquisition retains
one executor C-stack spill record before invoking the Native API, and released
records are reused. Kernel-stack pressure is an explicit unvalidated boundary.
The frontend accepts only those nine declared context values. A source
indirect CALL keeps its exact successor in the immutable image when returning
services are available; the runtime must still match the evaluated target to
an exact registered descriptor before authorizing that continuation. Merely
having a successor does not authorize an unknown callback. Images without a
reached direct or indirect service call retain their ordinary publication
requirements. Arithmetic flags at the actual source CALL boundary are saved
before dispatch metadata changes them, for helper interfaces that preserve
flags as well as ordinary C-volatile values.
Every successful grant names O, root UID/generation, acquisition service
sequence, kind and exact lock object; observed preemption/RCU depths only check
those live records. With the supported preemptible-RCU configuration, each
ordinary Native spin record contributes one Native preempt disable, while each
RCU record contributes one task read-side nesting reference. The engine pin is
accounted separately and is the only pin temporarily removed by the bridge.
Balanced potentially sleeping calls are refused while either Native kind is
live. A nonblocking context call may preserve that surrounding interval.

Releasing the outer KD owner does not complete a root that still holds Native
records. The final Native release can instead be its completion endpoint. That
API has already executed on O, so completion leaves its original source CALL
word unconsumed for the existing final RET restoration. An intermediate Native
result consumes that word once and resumes E; final completion must never both
pop it in the runtime and let the restoration RET pop another source word.
Every registered direct CALL and admitted indirect CALL exports its source
arithmetic flags. Immediately before the Native CALL, the bridge merges those
bits with O's physical control flags without changing its IRQ state or source
volatile inputs. It captures the callee's output flags before restoring the
engine context. This also preserves a declared callback that leaves arithmetic
flags and non-result registers unchanged. A special Native ABI still needs an
exact argument/result and context declaration; a matching name is insufficient.

Any source instruction that mutates CPU-local state outside those API calls
needs its own faithful lowering or returning instruction service. In particular
remote unlocked preempt-count RMWs and their zero-test flags cannot be justified
by pointer substitution. Identify the compiled release form and remaining GS
operands for the exact image/configuration before enabling its pair contract.
Likewise, the lazy-MMU interval and indirect PV/TLB operations require explicit
physical-context handling. If consistent execution cannot be established,
service that precise interval on its required actor with a resumable boundary;
never silently route the entire mmap/munmap body to O or declare it a success.

### Focused delivery and acceptance

The first GS candidate's module build also exposed that Linux 7 hides
`preempt_enable_no_resched` from modules. The instruction bridge must use the
same ordered `barrier(); preempt_count_dec();` operations to remove its own
engine pin on the Native task stack. It must not schedule before the source
instruction computes its flags. The subsequent source reschedule branch remains
an ordinary, separately executed source operation.

The indirect returning-CALL check found a production scope error: the old
Native-suffix reachability rule discarded the successor before the returning
dispatcher could include it. A returning-service image explicitly retains that
edge; the runtime still requires an exact declared target and CALL word.
Registered tail jumps use the caller's actual retained return word and resume
its source CALL successor. They do not manufacture another CALL word. Other
images retain the earlier scope rule.

Retained images also need the ordinary direct-callee closure before execution.
The legacy decoder deliberately does not follow CALLs, and learning a missing
callee after handing the rest of a body to O cannot implement this protocol.
For trusted ABI2 returning-service images, seed and fetch ordinary direct CALL
targets through the existing complete-source lease/window expansion. Exact
declared primitives and lock controls stay resumable boundaries. A decoded
callee's tail jump to a declared primitive inherits the source caller's real
return word. Existing source-size/expansion limits remain explicit resource
limits; this does not assert that every MM callback or source graph is ready.
Compiler sibling calls may also use a direct conditional branch to that
primitive. Such a branch needs the same target stub and caller-return
continuation as an unconditional tail jump; its untaken branch stays in the
translated image. This does not authorize indirect jumps to arbitrary helpers.

The final ownership release can itself be an instruction, for example the
last inline preemption decrement after an earlier outer unlock. Unlike a CALL,
it has no source return word to consume. Completion must preserve the unchanged
source SP, resume IP immediately after the completed instruction and its
arithmetic flags. The existing validated post-instruction packet tag identifies
that mode. Both module-local restoration and the builtin provider trampoline
must implement it; this is general continuation glue, not a change to any MM
body. Provider version 2 explicitly requires that completion mode. Version 1
must refuse the new provider rather than misinterpret a post-instruction
packet as a returning CALL. Final cleanup and the transferred module reference
are retired before builtin code restores the packet. Ordinary CALL completion
still consumes its original source return word exactly once.

1. Implement the returning primitive transaction and its task-stack bridge;
   build and run the affected generic killable/read-tail plus returning-helper
   fixture in the VM. Preserve all failed attempts and transaction witnesses.
2. Connect the versioned ordinary rwsem provider, typed entry metadata and
   exact ownership query. Inventory reached mandatory GS/current/IRQ/preempt
   operations and primitive CALLs from the actual compiled MM entries. Add
   explicit returning services or faithful lowering, not a whole-body suffix.
3. Prepare a distinct source/output-separated Linux 7 kernel and schema-2
   identity. Preserve old builds, frozen source and recovery disks. Verify
   unchanged Native MM body hashes and the Native `kd_mmap=off` API path.
4. Run focused actual-MM correctness and unchanged `mmap1_threads` and
   `mmap1_processes` with `kd_mmap=on`. Require origin/executor/request/object
   binding, other-task write entry, downgrade/read-tail execution, returning
   helper sequences, exact read release and returned completion. A returned
   syscall alone cannot establish this. Keep observations separate from timing.
5. Measure one round per selected point against a fresh matching Native arm
   only after functional proof. No claimed gain or master promotion follows
   from design, compilation, local execution or a partial returned prefix.

The November 3 preflight independently confirms the ordinary kernel boot,
idle guest, actual `kdlock-builddisk-clean-20261031` recovery snapshot, CPU
placement/frequency and about 50.7 GiB free on the second build filesystem.
Recheck the required 50 GiB preparation reserve before creating another build.
These observations authorize proceeding; they are not MM delegation evidence.

The current staged redesign is owned by
[Unified lock queue: Stage (a)](unified_lock_queue.md). Its shared queue model,
killable/nesting obligations and delivery gates supersede the earlier
implementation-pass ordering below. This document retains the rwsem
write/read-tail and executor-context requirements; neither document is evidence
that those capabilities are implemented. Stop after the Stage (a) design commit
and report before starting queue implementation.

## Objective and current stage

The user requests general delegated execution for the unchanged public kdlock
API. This supersedes the earlier local-only MM execution policy for this
candidate. There must be no workload-name selection, mmap1-only helper, special
syscall adapter, disabled cancellation check or silent original-task suffix.
The ordinary Native backend selected by kd_mmap=off retains its existing route.

Source baseline: 7231ddf0963ff2cc730590c09cc81e7f96f93095. Work is isolated
from master. This document is a design, not evidence of an implemented protocol,
a built kernel, proxy execution or measured performance.

The user's latest decision permits a delegated writer's downgraded read tail
to continue on the executor. This deliberately changes the general rwsem rule
that every read body executes locally. It applies to every equivalent caller,
not to a selected syscall or workload. Ordinary direct read acquisitions still
execute on their calling task. A delegated writer does not return to its origin
at downgrade; the origin remains suspended through the matching read unlock and
returned completion. Unsupported reached operations must be reported explicitly
and must not silently complete the remaining body on the original task.

## Public behavior to preserve

- The public acquire/release, killable, trylock and downgrade semantics remain
  unchanged for all callers. Successful acquisition has priority over a pending
  signal. A failed killable acquire does not execute the caller's body and does
  not retain a reader share, phase reservation, physical gate or queue node.
- Readers remain concurrent, including an executor-held downgraded share. Trylock remains nonblocking. No request can use an
  object initialized for a different protocol or change its protocol while live.
- Existing exact acquisition, physical owner, source/frame lifetime and final
  unlock acknowledgment obligations remain. A count is not an ownership token.
- Callers keep their native bodies. General API capture and lock routing may
  change; a benchmark or syscall-specific reimplementation is not acceptable.

## Required general changes

### Implementation pass: executor returns to pending writer work

Implementation restarts on codex/rwsem-killable-continuation from
69fca435cb41135a3676f66e54f413b3ee5c714e. The earlier design/observation
checkpoint is bd7e198b1933a01d639723ceb621fbcc45b6a29c. The
production source baseline remains 7231ddf0963ff2cc730590c09cc81e7f96f93095.
The rejected noncancellable foundation is retained at
64d4c3c049b82409d4765144e8422e31d20a4734 and
codex/archive-rwsem-noncancellable-foundation. It was never built or run.
The requested next transition is a sequence of distinct ownership intervals:

```text
origin B: selected writer -> delegated downgrade -> delegated read tail
          -> exact read release -> returned completion/retirement
executor E: select its pending A (or another queued request C)
            -> physical gate -> selected exclusive phase
            -> fresh active-reader drain -> that request's writer body
```

The same physical executor may perform both intervals. It does not inherit B's
write ownership after read release. The pending A may be E's original public
acquisition that has not reached its body; fulfilling it does not insert another
public API call. B may acquire again only when B's unchanged code calls an
acquisition API. Never hide a blocking writer acquisition inside public up_read.

The required implementation order is:

1. Complete the result-returning killable continuation capture together with
   cancellable publication and commitment. Cancellation has an exact failure
   continuation returning -EINTR; committed proxy entry explicitly defines
   success EAX as zero. A canceled request must be unlinked and acknowledged
   before its packet/stack can retire, without waiting for the holder to release.
   A selected/draining request is not yet acquired. Successful gate/phase/drain
   readiness takes priority over a pending signal; cancellation after commitment
   cannot report failure or replay body effects. Use the origin's killable
   predicate, never the executor's pending signals. Preserve the two-word wrapper
   ABI and callable/cleanup contracts. Do not add a capture-only local wrapper
   or publish a killable request through the current uncancellable mutex queue.
2. Separate queued writer/request accounting from selected writer admission.
   Use exact request-owned writer/read records and a phase generation. No
   queued request has a reusable reader-drain result. Apply the selected-phase
   rules to ordinary, signalable, trylock and delegated writers; preserve the
   existing cancellation, rollback and success-before-signal ordering.
3. Add general runtime controls for delegated downgrade and final read release.
   Publish the read credit before releasing the physical gate, reopen admission
   only after its unlock acknowledgment, and continue the read tail on E.
   The physical gate ACK must not complete the read acquisition or pop its
   frame. Keep exact source, packet, stack, object and execution records live.
   Finish B's read release and returned completion before reusing its storage
   or blocking E on A/C. Route reacquisition through the full rwsem writer
   protocol, not the existing mutex-only early-release recovery helper.
   Preserve each request's own commitment state: an already committed A cannot
   become canceled merely because physical reacquisition is necessary. An
   uncommitted killable request retains its ordinary cancellation contract.
   Connect only complete general capabilities to the kernel's ordinary lock
   facade. The builtin executor/image startup dependency and reached helper
   context services remain mandatory; a module-only or local-only run cannot
   certify forced delegated MM execution. No workload-specific adapter or
   suppressed reached-operation check is an intermediate solution.
4. Validate the killable path, selected admission and writer/read-tail protocol
   together. An unbuilt or local-only foundation does not complete any delegated
   mmap acceptance criterion.

Directly affected VM checks must witness other-task write entry, downgrade,
read-tail effects, exact read release/completion, and the same executor's fresh
writer acquisition. Include an intervening live ordinary reader so reacquiring
only the gate cannot pass. Check cancellation with a queued successor, rollback,
trylock nonblocking behavior, ordinary local downgrade and atomic read release.
After coherent changes, build and run unchanged mmap1_threads and
mmap1_processes in the enabled-MM VM, keeping proxy evidence separate from
application completion. A failed/unsupported point is retained, diagnosed and
reported; local execution is never counted as the requested delegated result.

This section authorizes an implementation sequence, not a claim that the
capabilities are already present. Keep every build/test attempt and exact
source/image identity. No source edits or synchronization occur while frozen
inputs are executing, and no promotion follows from an incomplete candidate.

The first required killable proof cancels a published uncommitted request and
returns failure while the holder still owns the lock. Its body prefix stays
zero, its successor survives and no packet/frame reference remains after exact
retirement. A second controlled case commits acquisition against a pending
fatal signal and executes exactly once with success. Cancellation while waiting
for readers must undo only that request's phase/gate custody. The existing local
cancellation probes do not establish any of these published-request cases.

The capture ABI can be constructed independently, but a working delegated
killable acquisition cannot use the current mutex queue unchanged. The baseline
queue only polls locked (kernel_module/mutex/queue.inc:84); its waiter outcomes
are native continuation, completed body or next head (mutex/waiter.inc:61).
There is no cancel-versus-commit election or canceled-node unlink/retirement
acknowledgment. Integer capture alone does not add those operations. Full MM
execution separately needs executor-side resumable services: the ordinary CALL
path at kernel_module/exe.c:704 currently runs the origin's remaining suffix,
and the builtin generator at kernel_integration/mmap_lock/prepare.py:61 removes
delegation machinery. These distinct gaps must not be concealed by local routing.

### Killable continuation capture and commit

Provide a result-returning continuation capture at the ordinary killable writer
entry, with full compiler/register/flags/stack contract. The current void
kd_down_write macro cannot implement this merely by changing a function name.
Callable/function-pointer entry must preserve the same observable behavior;
unsupported entry forms must not be mislabeled as delegated execution.

The result is also an execution-entry input. The existing ABI2 pristine packet
imports SP/IP/BP, not an arbitrary incoming EAX. A future integer-returning
source wrapper must therefore distinguish native return from committed proxy
entry: the native return preserves zero or -EINTR, while the captured proxy
success entry explicitly defines EAX as zero before the caller tests it. One
possible assembly layout captures a label containing `xor %eax,%eax` and jumps
over that label on the helper's ordinary return. This is a proposed ABI2
construction requiring compiler/JIT validation, not implemented support. The
two-word generated wrapper argument array remains unchanged. Cleanup
constructors must not capture inside a helper that returns before its user's
body. A capture-only helper that still acquires locally does not satisfy the
delegation requirement and must not be presented as a completed protocol step.

A request has these distinct states:

```text
INITIAL -> QUEUED -> SELECTED_DRAINING -> COMMITTED -> EXECUTING_WRITE
                                                        |
                                                        v
                                                     RETURNED -> RETIRED
QUEUED or SELECTED_DRAINING -> cancellation cleanup -> CANCELED -> RETIRED
```

Only an uncommitted request may cancel; selection for reader drainage is not
yet a successful public acquisition. Commitment follows physical gate ownership
and a valid zero-reader observation. Selection and cancellation must compete
on the same exact request state; a completed grant wins. Test the successful
grant predicate before acting on a signal. A killable request may stop optimistic
polling for any pending signal, but only the origin's killable cancellation
predicate authorizes failure; a nonfatal signal alone must not cancel it.
The executor cannot substitute its own pending-signal state for the origin's.
Cancellation of selected work retires its gate/phase custody before returning
failure, without publishing body execution or releasing somebody else's credit.
Publication does not permit execution before commitment. Every committed
request executes its body exactly once, with one completion and final lifetime
retirement. No native continuation may replay the completed prefix or report
cancellation after its body effects have committed.

### Writer phases that can downgrade

Queued requests must not be treated as already reader-drained writers. The
executor selects one exact request, owns the physical gate, closes writer/read
admission and drains readers for that selected request. Selection of a later
writer requires a new valid drain observation. This replaces the assumption
that a positive prepared cohort may reuse a pre-publication drain forever.

Downgrade adds an explicit transition:

```text
  EXECUTING_WRITE -> EXECUTING_DELEGATED_READ -> RETURNED_READ -> RETIRED
```

The read acquisition created by downgrade belongs logically to the same
successful caller acquisition, while its body and final release execute on the
executor. Its exact record binds the lock, request, origin, executor, generation
and one live read credit. This is a transfer of the request's execution/ownership
class; it is not an ordinary down_read call and must not release/reacquire the
lock with an unprotected gap.

The transition must, in this order:

1. Validate exact selected writer ownership and complete the native caller's
   pre-downgrade ordering (including per-VMA release ordering in MM callers).
2. Publish one exact read credit for the request before opening shared admission.
3. Change the request's ownership ledger from exclusive to delegated-read and
   end its exclusive phase. An object transition must not expose an unlocked
   interval between the writer state and that reader credit.
4. Continue the same captured continuation on the executor. Retain origin task,
   stack, frame, source and object lifetimes; no completion notification permits
   the origin to reuse its live stack while the read tail is still executing.
5. At the matching up_read, consume that exact credit once, close the captured
   continuation, acknowledge completion and retire the remaining state. A later
   origin-side release must not consume the share a second time.

Queued writers have reservations, not already valid reader-drain results. A
writer may enter only after its own selected phase observes all live read
credits drained, including every delegated downgrade credit. Any downgrade
invalidates earlier phase/drain observations through a generation transition.
A queued writer cannot bypass that recheck merely because it was published or
reader-drained before the downgrade. The queue may close admission to new
readers according to the general writer policy, but it cannot revoke an existing
read credit or serialize ordinary readers as exclusive bodies.

Physical gate custody, public exclusive ownership and shared ownership must be
represented separately. A temporary retained gate must not make the delegated
reader pass an exclusive-owner assertion. Releasing the gate must not let a
successor use a stale drain result. The implementation must choose and validate
one explicit ordering for this custody transfer rather than infer ownership from
aggregate counters. Readers on other tasks may still execute concurrently.

The first candidate design releases physical gate custody at downgrade, while
retaining the exact delegated read acquisition. Queued request count is separate
from reader admission. The selected executor owns the gate, closes admission,
and drains active read credits for that request. At downgrade it first publishes
its read credit and changes its ledger class, then releases the gate while the
old writer admission is still closed. Only after physical unlock/ACK does it
reopen shared admission. This retains the ordering of current local downgrade,
without returning the read tail to origin. Ordinary readers can enter concurrently.

A successor may acquire the physical gate before the prior phase reopens, but
must wait for that phase, close admission for its own selection, and freshly
drain active read credits. The delegated tail's outstanding credit prevents
writer entry. No published request is already reader-drained. Every writer
entry form, including local/signal and trylock, must follow the new ordering;
trylock must fail and roll back rather than wait for a drain. A canceled
reservation cannot decrement the delegated reader's credit. Aggregate admission
and gate.owner cannot replace the exact selected-writer record for ownership
queries or assertions.

Gate unlock/ACK at downgrade is not logical body completion. The frame retains
an unreleased delegated-read ledger entry, its source/stack/request state and
the origin's suspension until final read release and returned completion. The
matching up_read consumes the exact credit without unlocking a mutex. This is
needed because current kd_up_read explicitly allows IRQ-disabled/atomic callers
and avoids scheduler locks; attaching kd_mutex_local_unlock there could reach
wake_up_q. No frame or source may retire merely because all physical gates are
released while a delegated read credit remains live.

Final delegated up_read may run while admission is closed by the next selected
writer waiting for that credit. It must not require admission zero or retire the
previous writer phase again. The selected writer's drain must remain schedulable:
pinning it indefinitely on a CPU needed by the delegated read tail can prevent
that tail from releasing. Bounded polling and its scheduling path retain exact
request/frame custody; scheduling is not cancellation or proof of drainage.

After closing admission, drain only already admitted read credits. Never wait
for the reader-admission OSQ to become empty at that point: queued readers need
admission to reopen, so that wait can deadlock. A pre-close reader preference is
a policy decision, not a drain obligation. An authorized non-owner read release
also needs exact credit/completion routing; merely decrementing an aggregate
count would lose the request/frame obligation. No object pointer may be
dereferenced after public release without a separately retained lifetime.
These are implementation and fixture obligations, not validated behavior. All
queued writers must use the new selected-phase protocol before delegated
downgrade can be enabled.

An original-task read unlock and an executor-side read unlock follow the same
public up_read semantics; internal routing uses the exact acquisition record.
Nested read shares, non-owner read transfers, trylocks and asynchronous release
must retain their declared semantics. Supporting the new downgraded execution
class does not authorize treating arbitrary read acquisitions as delegated.

### General executor and context handling

Default other-task execution at an uncontended lock cannot be provided by
opportunistic combining alone. One worker and process-per-mm workloads need a
general executor distinct from the original task, available without caller-name
or object-class selection. Executor queues for different locks are not one
physical-lock delegation batch.

Logical task operands and physical execution context are separate. The existing
translator can substitute a saved logical current for recognized scalar loads;
this does not install the origin's scheduler state, CPU-local exclusion, active
mm, allocator policy or nested-lock ownership. Each executor-side helper must
state the logical task data it consumes and the physical CPU/task state it needs.
Temporarily overwriting the CPU's current_task is not a valid implementation.

Reached scheduler, allocation, nested-lock and MM-context operations need
executor-side services with exact ownership and return state. Current ordinary
CALL continuation runs the original task and its remaining suffix; it cannot
serve as this protocol's generic helper path. An unsupported reached point must
retain exact state for diagnosis rather than being counted as a successful proxy.
Failing an unsupported attempt is evidence of incomplete support, not a passing
replacement or permission to change the public API's failure behavior.

### Startup dependency

The existing MM builtin is local-only and runs before the loadable provider and
userspace translator are available. General forced execution cannot wait for a
userspace translator while the same lock protocol is needed to start userspace.
This dependency must be resolved before changing the builtin default: either a
builtin executor/translation service or source-bound images available during
startup. Caller-specific selection and unreported local execution before
provider readiness are excluded. No implementation option is claimed validated
by this design.

### Lifetime and reentrancy

Retain the original task, stack continuation and object lifetime through execution
and acknowledgment. An mm_struct allocation reference alone does not retain its
address space; an existing synchronous reference or an appropriate mm_users
reference must remain valid. VMA/table pointers require their own lock/reference
proof. Reentrant requests, executor waits, nested owners and module/source
retirement must all identify the exact request and execution generation.

## Staged instrumentation and validation

Stage 1 is this design. Stage 2 adds general protocol observations, compiled out
or disabled for ordinary scoring unless explicitly selected. Stage 3 integrates
the complete candidate and builds/runs it in the VM. Instrumentation does not
by itself enable delegation or establish support.

Record request/lock identity, generation, origin/executor task identity, state
transitions, cancellation/commit result, proxy entry/returned completion,
executor-side downgrade transfer, final delegated read release and retirement. Distinguish local,
proxy, canceled and unsupported outcomes explicitly. Proxy evidence requires
executor_tid != origin_tid; executing JIT on the originating task is not enough.

Define episode length as completed other-task write bodies under one physical
lock ownership interval. Also retain per-request queue wait and execution time,
plus the explicit write-to-read transition; do not combine independent locks into a
batch. Reconcile all published requests after drain and report unresolved ones.

All source edits, Git and static inspection run on 380G10. Builds, unit/kernel
checks and timing run only in VM 10.176.26.71. Verify idle, disk reserve and an
actual recovery snapshot before live work. Preserve each failed attempt before
repair. A changed production kernel needs a new frozen source/image identity;
prior scope4 bundles cannot certify it.

After each coherent code change: build, retain logs, run affected general API
checks and unchanged mmap1_threads/mmap1_processes with kd_mmap=on, including
one and two workers as unscored functional cases. Require completed proxy
write evidence and executor-side downgrade/read-tail release where reached. Keep kd_mmap=off checks and
all existing cancellation, rollback, downgrade, ownership and drain oracles.
No local-only fixture or NORMAL image substitutes for returned proxy evidence.

Final throughput uses fresh Native/KD arms with the same application binary,
configuration, worker placement and one scored round per selected point. Report
every gain/loss, exact source/image identities, episode distributions, explicit
unsupported sites and remaining correctness limits. No promotion follows merely
from compilation or a favorable score.


## Required capability evidence before a candidate can be accepted

The current source establishes missing capabilities, not a proof that all MM
instructions are inherently impossible to delegate:

| General point | Source evidence | Required candidate behavior |
| --- | --- | --- |
| Killable entry has no capture ABI | include/kd_rwsem.h and include/kd_rwsem_api.h; kernel_module/kd_rwsem_api.c | Preserve result/cancellation semantics with a complete continuation contract. |
| Prepared cohorts pre-drain before publication | kernel_module/kd_rwsem.c, kd_rwsem_reserve_delegate and kd_rwsem_delegate_enter | Select/drain by current phase generation; no stale admission across downgrade. |
| Ordinary downgrade requires local exclusive phase | kernel_module/kd_rwsem.c, kd_downgrade_write | Add the exact general delegated-read ownership class and final-release route. |
| Native CALL continuation currently runs origin suffix | kernel_module/exe.c, ordinary CALL path | Executor-side service or explicit unsupported receipt; no successful origin suffix. |
| Native wait/IRQ/RCU/MM terminals have physical context requirements | include/kd_native_terminals.def | Keep checks until equivalent executor-side context/service is implemented. |
| Current image production requires userspace | kernel_module/kd_main.c and the translation daemon | Break the early-boot dependency without per-caller selection or silent local work. |

No genuinely impossible instruction is established by merely finding an
unsupported current helper. Allocation, sleeping, current->mm reads and
conditional TLB work are not blanket rejection reasons. A precise unsupported
receipt must identify the reached source address/instruction/helper, saved
context and missing semantic service. Such receipts fail candidate support;
they are never counted as completed delegated execution.

The current explicit helper boundaries include the following. Their existence
in source is verified; the baseline API observer does not establish which helper
branches mmap1 reached. These are implementation gaps to resolve or report at
the exact reached site, not reasons to reject every branch of an enclosing body.

| Current reached boundary | Evidence / missing executor behavior |
| --- | --- |
| schedule, schedule_timeout, io_schedule and __cond_resched | include/kd_native_terminals.def marks scheduler-context terminals; kernel_module/exe.c:667 routes a terminal CALL to the origin suffix. Need executor-side wait/resume using the physical executor's scheduler state while retaining logical request ownership. |
| _raw_spin_lock and its IRQ/BH variants, Native mutex/rwsem helpers | The same terminal definition file marks Native-lock calls. Need exact nested ownership and saved/physical IRQ/preemption compatibility; numerical IF equality alone does not establish CPU-local context equivalence. |
| __rcu_read_lock, __rcu_read_unlock, synchronize_rcu and migration/BH helpers | CPU-context terminals in the same file. Need explicit executor-side context nesting and matched release; substituting logical current does not preserve CPU-local exclusion. |
| flush_tlb_mm_range, flush_tlb_kernel_range, switch_mm_irqs_off | Task/MM terminals in the same file. Require actual active-mm, CPU/TLB and ordering handling; translating a saved task pointer does not install those physical states. |
| user-copy/fault helpers, kthread_use_mm and mmput | Task/MM terminals in the same file. Require address-space/fault/lifetime services; their mere presence does not prove they occur inside each anonymous mmap1 body. |

The killable-entry, downgrade and final read-release gaps are unconditional
protocol gaps where those APIs occur. The remaining named CALL boundaries are
conditional until instruction/helper tracing establishes a reached site. No
new local suffix or API failure has been installed to make these gaps appear to
pass. An unsupported reached point remains a failed candidate, never a silent
origin continuation or successful direct-replacement claim.

Stage 1 is delivered on branch codex/rwsem-delegated-protocol-20261102 from
baseline 7231ddf0963ff2cc730590c09cc81e7f96f93095. Stage 2 must report current
local behavior honestly while adding generic observations; Stage 3 cannot claim
forced replacement until the entry, phase, executor-context and startup
capabilities above are implemented and validated together.

## Returning GS memory instruction transactions

Unlocked GS-relative INC and DEC must execute as one instruction on the
original task's CPU. Replacing GS by a saved remote address preserves the
address but loses the CPU-local read/modify/write contract. The retained
protocol therefore adds a separate instruction transaction for 32-bit and
64-bit memory operands. Immutable image metadata records the exact source
bytes, instruction length, operation and JIT successor. The runtime decodes the
same bytes, computes the effective offset from the existing FULL virtual GPR
packet, and validates the retained image and original task before publication.
The executor suspends before the original task touches the packet. The original
task executes one unlocked INC or DEC, preserves input CF, records all resulting
arithmetic flags, and acknowledges completion. Only then may the executor
resume the exact successor. Virtual GPRs and SP do not change, and no CALL return
word is constructed or consumed. Source bytes and the successor remain pinned
through image retirement; neither a quota nor an unsupported reached operation
permits an implicit original-task suffix.

The original task performs the transaction on its ordinary task stack. Its
runtime preemption pin is separate from source context. Exact accesses to
__preempt_count require 32-bit INC/DEC handling which removes only that runtime
pin while computing Native flags, retains each source preemption transition,
and restores the runtime pin before acknowledgment. Subsequent Native calls and
root completion must validate both the retained Native-spin records and these
source transitions. In particular, DEC's zero test includes x86's inverted
need-reschedule bit; a count biased by the runtime pin cannot supply its result.
Each source INC reserves one exact `KD_NATIVE_OWNER_PREEMPT` record before the
instruction; its matching DEC retires the latest token for O's exact count
address after actual execution. Expected Native preempt depth is the sum of
live spin and source-pin records. E retains its CPU capacity while either kind
is held, and a 64-bit or partial overlapping access to this 32-bit field is
refused before execution. Ordinary per-CPU accounting updates create no pin
record. The last matched DEC can complete a previously unlocked root through a
flags-aware IP/SP restore; it cannot use the source-CALL RET completion mode.
Other widths, LOCK/REP or address-size prefixes, non-GS segments and instructions
without a decoded emitted successor remain explicit unsupported reached points.
They must not execute through the remote ordinary RMW lowering.

The same before-effects marker covers other explicit GS destination mutations:
MOV and other stores, ADD/ADC/SUB/SBB, logical operations, NEG/NOT, shifts and
rotates, modifying bit operations, SETcc, POP, XCHG/XADD and CMPXCHG families.
Only the exact INC/DEC32/64 decoder authorizes execution. Other rows contain the
exact source bytes with operation, width and successor offset zero; publication
can retain those branches, while reaching one reports EOPNOTSUPP before effects.
GS loads, compares, read-only bit tests, prefetches and memory input operands
remain ordinary translations; this does not establish that every such read is
equivalent for arbitrary CPU-local scheduler state.

Focused validation will decode exact positive and negative byte forms, inspect
generated FULL exit and arithmetic-flags reentry, then exercise source GPRs,
unchanged SP/CF, increment/decrement results, exact acknowledgment/generation,
interrupt-visible local updates and matched preemption transitions in a VM
fixture. This source checkpoint supplies no measurement or execution receipt.

The focused VM attempt at `a4b64cabde4d96cd5c33417ecbbbda61c6d75300`
passed the production byte decoder and its three negative controls, the helper
parser, generated MM dependency checks and MM benchmark runner units. It did
not start live modules. Generated GS code checks stopped at their incomplete
fake ABI2 symbol table; the source-lifetime C fixture failed because its newly
included instruction metadata required scalar typedefs before that include.
These are retained failed fixture attempts, not execution passes. The focused
correction supplies the established fake lock symbols and fixes only typedef
ordering; it adds no read-normalization protocol or new runtime claim.

### Normalized source preemption reads

Source GS reads of __preempt_count cannot simply read the original CPU's word
and subtract one. While E runs, O may be handling an interrupt, so the sampled
word can also contain physical interrupt nesting that the source instruction
would not observe while executing on O. Partial-width tests of higher bytes are
subject to the same issue. A following isolated slice therefore guards every
explicit GS memory read by its decoded effective address. The predicate uses
the canonical __preempt_count symbol and the operand's actual width, including
overlap aliases; it does not depend on a caller name or a static address guess.
The exact symbol is carried by a versioned immutable directory and compared
with the provider's own symbol at publication. Nonoverlapping reads keep their
ordinary lowering. A matching read transfers the one instruction to O's Native
task stack, where only the runtime pin is removed and the actual source context
is present. There is no raw partial-read normalization claim.

The initial returning read operations are MOV memory-to-GPR32/64 and TEST
memory16/32 with an immediate. MOV writes only its decoded destination and
zero-extends a 32-bit result; TEST supplies the actual arithmetic flags. Neither
operation changes source SP or creates/consumes a PREEMPT record. MOV to SP and
other overlapping read forms remain exact before-effects refusal rows. Every
guard preserves source GPRs and flags before either the ordinary read or the
instruction transaction. This adds capability version 16 and a distinct read
feature/requirement; version-15 mutation directories remain supported. Focused
checks must cover dynamic aliases, operand boundaries, nonoverlap behavior,
zero extension, TEST zero/carry flags and exact same-executor reentry before
this slice supplies any execution or MM claim.

## Instrumentation checkpoint, November 2

The generic [API observer](../../tests/kernel/rwsem/observe/README.md) was built
and checked in the VM at bbb79781e85305cf3881f21108d11d4bf063af7e. Its fourteen
decoder fixtures passed. Fresh actual-MM API checks and unchanged mmap1
thread/process identity checks passed on the existing local-only kdscope4
image with kd_mmap=on. Four diagnostic observations at one and two workers
captured 88,204 events with complete API pairs, including downgrade/read release,
without probe misses or overflow. The [retained record](../../bench/results/10.176.26.71/tests/rwsem-protocol-observe-20261102/README.md)
includes the two failed setup attempts, fixes, exact identities and archives.

This completes baseline API observation only. It does not observe request
publication, commitment, a logical origin or executor, delegated ownership or
frame retirement. Protocol-transition instrumentation must accompany those
new implementation states. Every current capture states proxy_proof=false;
delegation length, critical-section ratio and performance acceptance remain
unestablished. Production lock and MM integration sources are unchanged from
the stated baseline. No delegated candidate kernel has been built or run.
