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

The [archive manifest](observed-1/archives.json) has SHA-256
`196a8f829a4bcf462352754a82d348ab2decf1cc96e981778fb9472dca93e7b9`.
Its four archives contain measurements, raw host observations, both analysis
format versions and metadata. They remain under the guest run's sibling
`-archives` directory and source-host `raw/bench/mutex-public-20261020-observed-1/`.
The [independent review](observed-1/offline-review.json) performed 886,743 checks:
exactly one failed, the preserved immediate post-run QEMU thread-set comparison.
Archive integrity, original-input binding, all worker/business/retirement
receipts and arithmetic checks reported no other issue. Therefore the review's
overall `consistent` field is false.

The first offline review stopped when its reader requested CSV bytes from a
cache that retains only selected text extensions. Its
[failure receipt](observed-1/offline-review-initial.json) and initial reader are
preserved. The corrected reader hashes the CSV member directly. The first CSV
also used default CRLF formatting; its original bytes and producer remain in
the archive alongside the final LF-formatted version, with all 360 parsed rows
verified identical. Neither issue reran or changed a measurement.

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

`d3806e4` passed [checks-2](../../tests/mutex-observation-20261020/checks-2/result.json):
both basic programs, 13 comparison checks, four observation checks and two
profile-plan checks. All 464 frozen source files remained unchanged and final
idle was confirmed. The checks'
[archive manifest](../../tests/mutex-observation-20261020/checks-2/archives.json)
has SHA-256
`196271be811fb3cebc86a72f6796a8fb29da7a0297b57da84c70a3758e5b920b`;
the inert review passed 6,932 checks with no issues.

`mutex-public-20261020-profiles-1` completed all 40 sessions serially with that driver.
The first preparation-time host receipt had 76 threads, so no session was
started then. A fresh receipt at 13:40:06 UTC had the exact original 67-thread
set after natural retirement; the unchanged preflight admitted that receipt.
Both receipts are retained. This run does not use the host observer; interference
within its intervals remains uncertain even if endpoint placement matches.

All 40 sessions passed functional checks and drained, including exact retirement
for all 20 KD sessions. All 4,424 original/collector input hashes remained
unchanged. The [sample analysis](profiles-1/profile-analysis.json) found zero
reported loss and valid worker PID/TID/CPU cohorts in all 40 profiles. Exact
provider ELF sizes and loaded symbols bound attribution; generated code uses
the exact published image range. The perf tool SHA-256 is
`be41fc3678db80aa92593a72034ebd6ec4c574c2dca2523f294dff5a0667aca3`.
Perf's default timestamps differ from the clients' CLOCK_MONOTONIC timestamps;
their alignment remains unvalidated. The analysis does not filter them as
though they shared one clock.

The samples are not a reproduction of every plain-run ordering. Public/OUTER
ratios in this one diagnostic repetition are c08/3 0.839, c08/4 1.027, c08/5
1.335, pipebytes/3 0.964, pipebytes/5 1.168 and RCUHT/2 0.935. Pipecap/5 is
incomparable: public returned JIT bodies while OUTER had zero JIT entries.
Pipebytes/4 remains incomparable too. Profiling and variance can affect the
physical-to-delegated mix, so these ratios cannot replace the plain comparisons.

The DIRECT lock-entry functions account for 5.76–46.64% of public worker
event-period weight; much of that is busy-owner polling. Exact task-identity
functions account for 0.37–2.22%. Sample weights are not isolated function
timings. The old compiled DIRECT fast path has a public-entry CALL into
`kd_mutex_lock_entry`, followed by two return layers after a successful
physical acquisition. This supports testing an entry-inlining candidate;
it does not establish the cause or recoverable fraction of any loss.

The [profile archive manifest](profiles-1/archives.json) has SHA-256
`608709986aa7cbdcfcfcbc13b3ed6f1e68b80961525da00b5d7f7eab874647ff`.
The [inert review](profiles-1/offline-review.json) performed 105,506 checks,
with exactly one failed check: the immediate post-run thread set had 80 QEMU
threads rather than the original 67. This remains an environment limitation.
Archive integrity, source/tool binding, workers, business results, retirement,
sample sums and loss counts reported no other issue.

## Entry-inlining candidate

Candidate `003d71c` forces the unchanged common lock-entry decision to inline
into each existing ABI entry. It preserves the public DIRECT CALL, captured
IP/SP/BP, sleep-before-acquire ordering, up-to-eight probes and early COMBINER
exit, exact contention counts, nested admission and unlock ACK paths. The
source-extraction test marker follows the declaration; all mutation checks
remain. No lookup or admission condition is removed.

The existing unified-API reviewer found no source-level protocol change and
reported no files touched or VM activity. The VM-built provider confirms that
the extra helper CALL disappears from all three affected entries. Its public
entry preserves the incoming SP/IP/BP in registers and forwards those same
values into contention, with ABI2. Performance improvement remains unmeasured.

The candidate check runner is [check-entry-candidate.py](check-entry-candidate.py):
two basic programs and six affected drivers, with provider/daemon builds and
source verification before and after each step. The serial
[live supervisor](run-entry-tasks.py) retains the original stop-on-failure and
idle/source checks. It also binds the owner/ACK fixture's `sources.json` map
explicitly and verifies each retained source byte and child success/drain
receipt. The completed order is ordinary local mutex, OUTER continuation, public
DIRECT continuation, and the real-owner ACK fixture on CPUs 0, 32 and 33.

`mutex-entry-inline-20261020/checks-1` passed both basic programs and all six
affected drivers, including 11,504 resource checks and 3,438 after-OUTER checks.
Provider `W=1` and daemon `-Werror` builds passed. The provider log retains locale
fallback and `_Q_LOCKED_COMBINER_VAL` redefinition warnings; this is not a
warning-free build claim. Byte-exact compiler/disassembly logs remain in the
raw archive. `live-1` passed all four
probes serially: the ordinary probe completed 160,000 operations across eight
workers and 2,048 32-byte mutexes; OUTER/public cold-delegated phases returned
1,586,349 / 1,591,541 JIT bodies. Each continuation probe recorded exactly one
hot native exit and zero post-ban JIT activity. The real-task fixture passed
both B-A/A-B release orders, four ACKs, and its three-worker, 4,096-iteration
registry stress. That constructed-frame fixture executes zero JIT bodies.

The [health receipt](../../tests/mutex-entry-inline-20261020/health.json) binds
1,612 source/binary hashes, reports no per-probe kernel fault matches and exact
retirement `state=2, modules=writers=frames=0` for all four probes. The
[archive manifest](../../tests/mutex-entry-inline-20261020/archives.json) has
SHA-256 `6fb8361828f44362e0ba16a5796308e267e3df1ca6a82b3f6ba57d9bc3c1b7a9`.
Complete checks/live/metadata archives are retained in the guest's sibling
`mutex-entry-inline-20261020-archives` directory and source-host
`raw/tests/mutex-entry-inline-20261020/archives/`. An
[independent inert review](../../tests/mutex-entry-inline-20261020/offline-review.json)
completed 27,261 checks with zero issues. This validates the selected candidate
scope, not whole-kernel replacement or resolution of the seven throughput losses.
