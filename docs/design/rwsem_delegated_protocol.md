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

The user explicitly selected original-task execution after an explicit
write-to-read downgrade. Ordinary read acquisitions and that read tail remain
local. Returning at downgrade is a specified ownership transition; other
unsupported reached operations must be reported explicitly and must not silently
complete the remaining write body on the original task.

## Public behavior to preserve

- The public acquire/release, killable, trylock and downgrade semantics remain
  unchanged for all callers. Successful acquisition has priority over a pending
  signal. A failed killable acquire does not execute the caller's body and does
  not retain a reader share, phase reservation, physical gate or queue node.
- Readers remain concurrent. Trylock remains nonblocking. No request can use an
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

  EXECUTING_WRITE -> DOWNGRADED_READ -> RETURNED_READ -> RETIRED

Before returning to the origin, publish its exact read share and retire or
suspend the exclusive phase so that no queued writer can enter using an earlier
drain observation. Preserve all per-object release ordering. The origin resumes
at the original downgrade continuation and eventually releases its own read
share. The combiner must not execute that read tail. The request's execution,
read ownership and frame/source retirement have separate completion points.

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
downgrade transfer, final read release and retirement. Distinguish local,
proxy, canceled and unsupported outcomes explicitly. Proxy evidence requires
executor_tid != origin_tid; executing JIT on the originating task is not enough.

Define episode length as completed other-task write bodies under one physical
lock ownership interval. Also retain per-request queue wait and execution time,
plus the explicit downgrade endpoint; do not combine independent locks into a
batch. Reconcile all published requests after drain and report unresolved ones.

All source edits, Git and static inspection run on 380G10. Builds, unit/kernel
checks and timing run only in VM 10.176.26.71. Verify idle, disk reserve and an
actual recovery snapshot before live work. Preserve each failed attempt before
repair. A changed production kernel needs a new frozen source/image identity;
prior scope4 bundles cannot certify it.

After each coherent code change: build, retain logs, run affected general API
checks and unchanged mmap1_threads/mmap1_processes with kd_mmap=on, including
one and two workers as unscored functional cases. Keep kd_mmap=off checks and
all existing cancellation, rollback, downgrade, ownership and drain oracles.
No local-only fixture or NORMAL image substitutes for returned proxy evidence.

Final throughput uses fresh Native/KD arms with the same application binary,
configuration, worker placement and one scored round per selected point. Report
every gain/loss, exact source/image identities, episode distributions, explicit
unsupported sites and remaining correctness limits. No promotion follows merely
from compilation or a favorable score.
