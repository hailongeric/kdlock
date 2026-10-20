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

## Observation-tool checks

`bc72912` passed dependency checks, both basic programs, 13 comparison tests
and four observer/clock tests in the VM. The latter cover proc-stat parsing,
exact task identity, affinity refusal and conservative clock projection.
The frozen copy contains 462 source files matched to the committed manifest;
both that copy and the maintained guest source stayed unchanged. Final idle
was confirmed. No live modules or new throughput measurement ran in this step.

[Checks and logs](../../tests/mutex-observation-20261020/checks-1/result.json)
and [complete archive metadata](../../tests/mutex-observation-20261020/checks-1/archives.json)
are retained separately. The archive manifest SHA-256 is
`7992c1243992f81918cf0f877cc8df7b6a1c5477d5d2b17305eaa66688b1b651`;
the inert source/archive review passed 6,410 checks with no issues. The first
archive download failed because the local parent directory was absent; creating
that destination and repeating the copy did not rerun any test.

## Observed original-input reproduction

`mutex-public-20261020-observed-1` completed 120/120 sessions at scheduler
`bc72912`, using the original `d21a1e3` measured collection. All functional
oracles passed and every session drained. The 60 KD retirements have exactly
zero modules, writers and frames; no kernel fault matches were found. Independent
post-run verification matched all 4,088 original files and 336 retained collector
files. This is an instrumented reproduction, not a revised mutex implementation.

The [separate comparisons](observed-1/comparisons.json) and
[360 per-repeat rows](observed-1/per-repeat.csv) keep the original matrix, plain
replay and observed reproduction distinct:

| Original regression | Original public/OUTER | Plain replay | Observed reproduction |
| --- | ---: | ---: | ---: |
| c08, 3 workers | 0.812460 | 0.681982 | 0.863191 |
| c08, 4 workers | 0.706642 | 0.533785 | 0.642315 |
| c08, 5 workers | 0.789000 | 0.764036 | 0.748420 |
| pipebytes, 3 workers | 0.840544 | 0.967176 | 1.010601 |
| pipebytes, 5 workers | 0.874075 | 0.919470 | 0.879555 |
| pipecap, 5 workers | 0.597685 | 0.748197 | 0.635819 |
| RCUHT, 2 workers | 0.919323 | 0.887614 | 0.708436 |

These are ratios of three-repeat medians within comparable execution classes.
The observed c08/4, c08/5, pipecap/5 and RCUHT/2 public maxima remain below 95%
of their OUTER minima. c08/3 and pipebytes/5 retain overlapping ranges. The
pipebytes/3 loss did not reproduce at that provisional screen. The c08/2 and
pipebytes/4 class gaps remain; pipecap/4 is same-class with ratio 0.953764.
None of these observations establishes a causal correction or p95 latency.

The [host observation](observed-1/host-observation-summary.json) completed
17,966 samples over 900 seconds with no placement error or interruption.
QEMU had 67–98 observed threads, including 61 distinct additional task
identities over the window. All service threads remained on CPU 63.
Additional-service observed CPU deltas sum to 0.817 seconds; the maximum
per-session sum in intervals overlapping the projected measurement window is
9.278 ms. These are sampled deltas, not complete interference bounds.
The immediate post-run snapshot had 69 threads; the final snapshot restored
the original 67 naturally. The strict post-run thread-set match therefore
remains a recorded environment difference, not a waived check.

Clock projection retains the entire 1.277-second envelope of endpoint RTT
bounds. Intervening drift is unproven, tasks can escape polling, and other host
processes were not observed. Host scheduler statistics were disabled, leaving
runqueue delay unmeasured. The observer consumed 12.62% of one CPU, pinned to
otherwise unused host CPU 62. This overhead is an additional reason to keep
this collection separate. The samples establish transient QEMU activity; they
do not explain the seven losses.

## Matched causal profiles

The next diagnostic selects repeat zero of all ten original points, retaining
the original four-arm rotation: 40 sessions. Original provider, workload,
client, daemon, translator and collector bytes remain pinned. Flat `cycles:k`
profiles use 199 Hz sampling; API recording attaches to the idle persistent
client and acknowledges enable before its measured workers are created.
Inherited worker sampling is disabled and stopped before module teardown.
Synthetic sampling uses the retained collector's existing profiling path.
The exact perf binary is copied and hashed; all results are explicitly
diagnostic and excluded from throughput acceptance. No task-routing,
admission, publication, business or retirement predicate is changed.
