# Exact wake-callback correlation design

This is a proposed next observer, not implemented or validated evidence.
The installed `6.1.159-kdmm1` image (Build ID
`687ff5a29315d732f93a618e50ac407c794bbf9b`) and sealed observer revision remain
unchanged. A new observer must have separate source, binary and result identities.
No selective-wake change follows from the existing aggregate retry counts.

## Falsifiable question and bounded scope

Hypothesis: one phase-wait wake operation invokes callbacks for multiple exact
writer wait entries, activates multiple blocked writers, and more than one of
those writers subsequently returns from blocking with a failed admission
predicate. Alternative explanations include non-queue wake sources, an already
runnable waiter, cancellation and unrelated later wake operations. Count each
separately; absence of a matched chain does not establish broadcast causality.

Start with a fixed-work correctness fixture: one held writer and two queued
killable writers on distinct guest CPUs, then release the holder and allow both
writers to finish. Keep the kernel and waitqueue policy unchanged. Add a direct
task-wake negative control, cancellation, and reader-drain/downgrade controls.
This bounded event trace is deliberately separate from the original 16-worker
timing input. Only after exact lifecycle controls pass may one bounded selected
window of the frozen workload be proposed. Do not start a broad matrix.

## Identities and event boundaries

Retain task and mm allocation references before publishing records. Identify an
acquisition by retained task identity plus a monotonically increasing call
sequence and the exact semaphore address. Identify each wait entry by that
acquisition, its stack address, phase/drain kind and initialization generation;
the same stack address is reused across waits and is never sufficient alone.
Capture initialization and queue preparation before publication can expose the
entry to a waker. Finish/cancellation must close that exact generation before
the stack can be reused. Observer retirement never substitutes for worker join.

Capture these distinct events with monotonic timestamps, per-CPU sequence and
exact identities:

- Wake operation entry/exit, queue address, caller/return site and a unique wake
  invocation ID. Repeated internal bookmark passes belong to the same outer
  invocation; interrupt nesting must use a bounded context stack.
- Queue traversal callback invocation, exact entry, callback function, saved
  entry flags, mode and wake flags. Invocation means selection for a callback,
  not successful activation or acquisition.
- Callback return and signed result, paired through a retained invocation
  descriptor. Do not dereference the entry after the callback removes it:
  `finish_wait` may take its empty-list fast path and permit stack reuse before
  the waker finishes returning, even while the waker still holds the queue lock.
  A nonzero default callback result is not by itself proof of a scheduler
  dequeue or an eventual blocked scheduling return.
- Scheduler waking/activation events for the exact retained target. Preserve
  the synchronous caller context and any cross-CPU activation separately; a
  remote scheduler event must not borrow an unrelated CPU's callback context.
- Actual blocked versus runnable switch-out, schedule return, and the next
  predicate outcome. Retain the corrected `prev->on_rq == 0` blocked predicate.
  Multiple switches within one schedule invocation form one episode.

The retained ELF disassembly places the `__wake_up_common` indirect callback
call at `0xffffffff8113b088` (`e8 b3 6c 0c 01`) and its result test at
`0xffffffff8113b08d` (`85 c0`). This static finding is not a live byte check.
Resolve and verify all exact emitted
addresses, instruction bytes, preserved registers and stack offsets from the
captured ELF; refuse changed bytes before registering any probe. The kernel
source alone is not an instruction-site proof.

## Lifetime, concurrency and rejection rules

Preallocate all records and event capacity. Use separate per-CPU append-only
event buffers with explicit completion publication and no wrapping/overwrite.
Cross-CPU callbacks must not write the original task-owned counter record.
An immutable wait-generation descriptor remains valid until queue removal,
waiter-side closure and all in-flight callback observations complete. Capture
the callback context while its entry is still linked and protected; return-side
events use that retained context, not the possibly reused entry. Never dereference an unretained
task or a stack entry after its protected lifetime. If an entry is requeued
before an earlier callback return, preserve both event contexts rather than
overwriting an acquisition or wake ID. No global lock may serialize the lock
protocol merely to simplify observation.

Any missed probe, slot/event/context-stack overflow, incomplete pair, identity
mismatch, ambiguous reuse, untracked selected entry, impossible ordering or
nonzero active context invalidates the entire affected trace. Report all such
failures, including unobserved activations, rather than assigning them to a
convenient wake source. STOP requires independent real task exit/join, then
unregisters probes and tracepoints, synchronizes callbacks and drops exact
references. Cancellation must preserve the removed entry's generation until
callback retirement; test both before and after callback selection.

## Perturbation and interpretation

Breakpoints inside waitqueue and runqueue paths extend lock hold time. Event
stores, clocks and extra scheduler hooks add observer cost; a trace establishes
causal order only for that instrumented execution. Do not compare its rate to
the earlier observer, perf samples or plain timing. Report selected/omitted
acquisitions, overflow/missed counts, full admission and the original immediate
endpoint separately from trace consistency. A rejected endpoint remains a
rejected timing even when the event trace is internally complete.

Before a selective-wake variant, require matched one-to-many callback and
activation chains ending in failed predicates. Then design a separate policy
with competing writers, local readers and delegated cohorts (where supported),
cancellation around selection, rollback-to-successor, downgrade, fairness and
liveness checks before timing. Existing waiters are non-exclusive: changing
`wake_up_all` to `wake_up` alone still wakes all non-exclusive entries and is
not a selective-wake implementation.
