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
