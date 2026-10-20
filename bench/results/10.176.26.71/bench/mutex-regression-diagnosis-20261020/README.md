# Mutex regression diagnosis after the controlled replay

Status: active. The user reopened all seven mutex points and requested subsequent
rwlock/rwsem, real mmap, page-fault and nano/list work. The completed correctness
checks and [original-input replay](../mutex-public-regressions-20261020/README.md)
retain their exact source and artifact identities. This stage starts at
`226e2a6`; no new performance result or candidate correction is claimed yet.

The source checkout on `380G10` is the only writer. The recovery VM remains
`root@10.176.26.71:2222`, kernel `6.1.159-kdclobber2`, boot
`b65f0205-c8f9-4385-8b13-039cbce243a6`. All tests and timings remain serial in
that VM. Helpers may review read-only; they do not edit or execute VM work.

The immediate dependency is environment observation. The original-input replay
matched the original thread set before measurement but retained an extra QEMU
worker on collector CPU 63 afterward. A bounded host observer will read exact
thread identities, affinities, CPU runtime and available runqueue accounting
through `/proc`. It changes only its own affinity to unused host CPU 62 for
this focused 2–5-worker plan. It changes no QEMU, kernel or frequency setting.
Its sample duration, gaps and CPU cost are retained. Polling may miss tasks
that start and exit between samples; disabled scheduler statistics cannot
establish runqueue delay.

Guest session clock brackets are recorded outside the worker interval. Cross-host
clock alignment requires explicit round-trip bounds; wall clocks are not assumed
synchronized. The original frozen binaries, translation sources and collectors
remain unchanged in the next reproduction, with the new observer/scheduler
identified separately. Placement checks, business oracles and drain requirements
remain mandatory; an observation failure cannot relabel a run as accepted.

Static inspection identifies DIRECT's clobber entry and provider ownership
lookup as hypotheses to profile. It does not establish their share of any loss.
The seven points remain c08 at 3/4/5 workers, pipebytes at 3/5, pipecap at 5 and
RCUHT at 2. The original pipecap loss was 40.23%; the replay loss was 25.18%,
without a demonstrated fix. The two class gaps and unmeasured p95 latency remain
open. Instrumented diagnosis will remain separate from plain throughput.

Subsequent stages retain these dependencies:

1. Evaluate focused mutex changes only after causal evidence, with affected
   correctness checks and matched OUTER/Native/TCLock controls. Define latency
   sampling and overhead before interpreting percentiles.
2. Reconcile and measure supported rwlock/rwsem comparisons. TCLock has no
   established sleeping-rwsem control; this cannot be silently substituted.
3. Audit all users of the real `mm->mmap_lock` object and missing filemap/folio,
   userfault and filesystem callbacks before integration. Initialization,
   helper APIs, task/mm state, cancellation, downgrade and implicit
   unlock/reacquire transitions must follow one ownership protocol.
4. Establish native/local mmap and fault behavior, then validate any supported
   delegation without replaying partial effects. Synthetic probes do not
   establish safe real fault delegation.
5. Compare equivalent 16/128-node plain/prefetch list work across supported lock
   families and worker configurations. Functional success alone is not evidence
   of a throughput advantage; losses and variation remain reportable.
