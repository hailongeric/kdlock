# General delegated rwsem protocol

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

### Killable continuation capture and commit

Provide a result-returning continuation capture at the ordinary killable writer
entry, with full compiler/register/flags/stack contract. The current void
kd_down_write macro cannot implement this merely by changing a function name.
Callable/function-pointer entry must preserve the same observable behavior;
unsupported entry forms must not be mislabeled as delegated execution.

A request has these distinct states:

  INITIAL -> QUEUED -> COMMITTED -> EXECUTING_WRITE -> RETURNED -> RETIRED
                  \-> CANCELED -> RETIRED

Only an uncommitted request may cancel. Selection and cancellation must compete
on the same exact request state; a completed grant wins. Publication does not
permit execution before commitment. Every committed request executes its body
exactly once, with one completion and final lifetime retirement. No native
continuation may replay the completed prefix or report cancellation after its
body effects have committed.

### Writer phases that can downgrade

Queued requests must not be treated as already reader-drained writers. The
executor selects one exact request, owns the physical gate, closes writer/read
admission and drains readers for that selected request. Selection of a later
writer requires a new valid drain observation. This replaces the assumption
that a positive prepared cohort may reuse a pre-publication drain forever.

Downgrade adds an explicit transition:

  EXECUTING_WRITE -> EXECUTING_DELEGATED_READ -> RETURNED_READ -> RETIRED

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

Stage 1 is delivered on branch codex/rwsem-delegated-protocol-20261102 from
baseline 7231ddf0963ff2cc730590c09cc81e7f96f93095. Stage 2 must report current
local behavior honestly while adding generic observations; Stage 3 cannot claim
forced replacement until the entry, phase, executor-context and startup
capabilities above are implemented and validated together.
