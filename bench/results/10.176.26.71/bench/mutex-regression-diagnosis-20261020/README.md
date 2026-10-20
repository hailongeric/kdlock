# Mutex regression diagnosis after the controlled replay

Status: validation and investigation evidence recorded; performance acceptance
remains open. The user reopened all seven mutex points and requested subsequent
rwlock/rwsem, real mmap, page-fault and nano/list work. The completed correctness
checks and [original-input replay](../mutex-public-regressions-20261020/README.md)
retain their exact source and artifact identities. This stage starts at
`226e2a6`. The observed reproduction, matched profiles and isolated entry-inlining
comparison are complete. The inlining experiment is not accepted as a regression
fix; all seven causes and remaining environment/class gaps remain open.
The later [operation-latency stage](../mutex-latency-20261021/README.md) completed
252 serial sessions and measured sampled complete-operation p95. Its exact
scope, observer effects, variance and failed host endpoint remain separate from
the historical measurements below.

The source checkout on `380G10` is the only writer. The recovery VM remains
`root@10.176.26.71:2222`, kernel `6.1.159-kdclobber2`, boot
`b65f0205-c8f9-4385-8b13-039cbce243a6`. All tests and timings remain serial in
that VM. Helpers may review read-only; they do not edit or execute VM work.

The initial dependency was environment observation. The original-input replay
matched the original thread set before measurement but retained an extra QEMU
worker on collector CPU 63 afterward. A bounded host observer recorded exact
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

## Isolated provider comparison

The completed bounded experiment used the original `r2` d21 inputs plus only the
entry-inlining change selected from `003d71c`; it is not a full `003d71c` build.
The four selected public groups share an identical 99-file raw provider and
observation recipe. [entry_candidate.py](../../../../mutex_api_compare/entry_candidate.py)
builds a new private observed provider with NUMA=1, batch=1024, SELFTEST=0 and
UBSAN off. Each public group keeps its original workload, client, daemon,
translator and plan. Synthetic source identities include the refreshed
prepared entry and prepared manifest as well as the raw entry; API identities
retain their original source scope. The new provider has its own binary hash.

Dedicated public-only views preserve the original OUTER, Native and TCLock
bundles and identities. The existing host, boot, topology, dependency, import,
admission, business and retirement checks remain. Both original and candidate
bytes were verified. Preparation and focused runner checks preceded a new host
receipt and the same 120-session, ten-point, three-repeat schedule.

This schedule has no simultaneous original-public fifth arm. Candidate/OUTER
comparisons are freshly matched, while changes from earlier public results
remain observational. Execution classes and repetitions stay separate; p95,
within-run host interference and unresolved losses remain explicit gaps.

Driver `d1a976a` passed two basic programs, 13 comparison checks and four
candidate-boundary checks in
[`mutex-candidate-runner-20261020/checks-1`](../../tests/mutex-candidate-runner-20261020/checks-1/result.json).
Its archive manifest SHA-256 is
`6921689425fb7dd8824c4019dd303491882e58407bf76b79ee327dc6a9ca4572`;
the offline review passed 6,943 checks.

Prepared inputs are `mutex-public-20261020-inline-inputs-1`, manifest
`d8b5b56daa3110cf3e276ca8c2198c2b05eda1bd79630210142163f57bc8f9ac`,
provider `7ed3022ae9c631f22c26aa9c54293f949a2e36ac53790b162782f72b47e0eefc`.
The [preparation archives](inline-inputs-1/archives.json) have manifest SHA-256
`e84308527775fac8a26c2eaf0e524868431b0a6eb5179a9419f5e81e8e6b7035`.
The [independent review](inline-inputs-1/offline-review.json) passed 22,223 checks.
Its first reader stopped because extensionless Makefiles beneath
`provider-inputs/` were hashed but omitted from its text cache. The initial
reader and [failure log](inline-inputs-1/offline-review-initial.log) are retained;
the corrected reader fetches and rehashes those archive members. No input or
measurement was changed.

`mutex-public-20261020-inline-1` completed 120/120 functionally valid, drained
sessions, including 60 exact KD retirements and zero kernel fault matches.
Classes are 60 controls, 22 NO_JIT, 24 WITNESSED_JIT and 14 RETURNED_JIT. The
original 67-thread host configuration matched before admission. The immediate
post-run receipt at 14:47:45.714152 UTC had 99 QEMU threads; that strict check
failed. All thread affinities still matched the placement policy. Runtime
interference remains unmeasured.

The [four-collection analysis](inline-1/comparisons.json) keeps all 480 samples
and source versions separate. Candidate ranges below are observed whole-run
throughput in millions of operations/second, not confidence intervals.

| Original regression point | Candidate / OUTER median | Candidate range | OUTER range |
| --- | ---: | ---: | ---: |
| c08 / 3 | 0.7824 | 5.125–5.697 | 6.321–8.607 |
| c08 / 4 | 0.7125 | 4.698–6.134 | 6.384–7.258 |
| c08 / 5 | 0.7064 | 4.061–4.288 | 5.776–9.200 |
| pipebytes / 3 | 0.9769 | 11.287–11.610 | 11.421–12.041 |
| pipebytes / 5 | 0.9598 | 4.641–5.049 | 4.563–5.464 |
| pipecap / 5 | Incomplete class match | 5.541–6.027, three returned-JIT samples | Two returned-JIT samples, one NO_JIT |
| RCUHT / 2 | Incomplete class match | Two witnessed-JIT samples, one NO_JIT | 5.382–5.670, three witnessed-JIT samples |

All three c08 losses remain. The c08/3 and c08/5 losses exceed the provisional
5% observed-range margin; c08/4 does not meet that margin despite its median
loss. Public/OUTER spreads reach 29.1%/56.6% among those points. Both pipebytes
points meet the provisional median screen in this run, without establishing
repeatable correction. Pipecap/5 and RCUHT/2 cannot satisfy the unchanged
three-repeat class gate. Existing c08/2 and pipebytes/4 class gaps also persist;
pipecap/4 is comparable at 0.9281. P95 remains unmeasured. All seven original
points therefore remain unresolved for acceptance.

The [run archives](inline-1/archives.json) have manifest SHA-256
`5fd2c1c0f9f5819e3f62671ca79272d86a5c72a3dc729ea5ee6e31d532964c58`.
The [independent run audit](inline-1/offline-review.json) performed 124,584
checks with exactly one failed check, the retained post-run thread-set mismatch.
All archive/input binding, worker, business, retirement and summary-arithmetic
checks reported no other issue. Archives remain in the corresponding guest
`-archives` directories and source-host `raw/bench/` directories.

The candidate is rejected as a solution to the seven regressions. Its
implementation and evidence are preserved at
`archive/mutex-entry-inline-20261020` (`7062887`). Only
`kernel_module/lock/mutex_calls.inc` and
`tests/unit/mutex/test_mutex_resources.py` are restored to their `27df765` bytes;
the unified API, nested locking and ownership/ACK protocol remain in place.
The restored entry has SHA-256
`0d201fc6fbb0514e1cefdea2237e35ff2b9dc67432db53592224552fd269ace3`.

The restoration validation stage is `mutex-entry-restored-20261020`. It reuses
the same two basic programs, six affected drivers and four serial live probes
(local, OUTER, public DIRECT and owner/ACK) in the original recovery VM.
At restored commit `a768361`, dependencies, provider/daemon builds and all eight
selected unit programs/drivers passed in `checks-1`. Provider warnings include
locale fallback, `_Q_LOCKED_COMBINER_VAL` redefinition and assembly/objtool
diagnostics; this is not a warning-free build.

`live-1` stopped at the first provider load: reserved per-CPU allocation of
7,592 bytes at alignment 128 returned ENOMEM before provider initialization.
The local workload was never loaded; OUTER, public and owner/ACK never started.
The original `PREPARATION_FAILED` result remains unchanged. A later observation
confirmed no project modules/tasks and an idle VM. The failed attempt, checks,
kernel trace and input hashes were archived before retry.

This matches the previously documented reserved-per-CPU preparation failure in
the [unified API validation](../../tests/mutex-api-20261020/validation.json).
The unchanged `tc_allocator_guard` performed its normal page-sized allocation
and free, then unloaded. Its private source/build/command receipts are retained
in `allocator-refresh`; neither the kernel nor allocator metadata was patched.
The same four-task plan completed in `live-2`, with identical source and
arguments and a fresh snapshot/placement receipt. All four probes passed:

| Probe | Restored-source result |
| --- | --- |
| Local API | 160,000 operations, eight workers, 2,048 objects, 32-byte/8-byte layout; nested sleeping, cancellation, ring handoff, I/O and API helper checks passed |
| OUTER | 1,539,422 warmup and 1,590,301 cold-delegated returned bodies; exactly one hot native exit, zero hot completions and zero post-ban activity |
| Public DIRECT | 1,546,751 warmup and 1,589,757 cold-delegated returned bodies; exactly one hot native exit, zero hot completions and zero post-ban activity |
| Owner/ACK | Both B-A/A-B orders, four ACKs, two deferred frees; three registry workers completed 4,096 iterations each with three deferred frees; constructed frames, zero JIT bodies |

The [final health receipt](../../tests/mutex-entry-restored-20261020/health.json)
binds 1,616 source/binary hashes, all 246 files from the failed first attempt,
and the allocator preparation. All four successful probes retired exactly
`state=2, modules=writers=frames=0`; no matched runtime kernel faults were found.
The [ELF section comparison](../../tests/mutex-entry-restored-20261020/percpu-section-comparison.json)
shows identical per-CPU size, alignment and contents between the earlier
successful inline candidate and the initially rejected restored provider.
Successful retry after normal allocator preparation supports the known
allocator-hint diagnosis; it does not erase the original failure.

The [complete archives](../../tests/mutex-entry-restored-20261020/archives.json)
have manifest SHA-256
`3aabb6b7408ce69a392c7587d2001636382eba12057b0857eb84dc78b689439a`.
Their [inert source/receipt review](../../tests/mutex-entry-restored-20261020/offline-review.json)
passed 31,957 checks with zero inconsistencies. The separate pre-retry
[failure archive](../../tests/mutex-entry-restored-20261020/failed-live1-archives.json)
has manifest SHA-256
`26a592b9766758e8a92db8f621c276d9c8379a80e7c446985807a0d84e045b70`;
its review passed 11,468 preservation checks while explicitly retaining
`PREPARATION_FAILED`, zero live probe passes and no claimed source retirement.
Both complete archive sets remain in the corresponding guest sibling
directories and source-host `raw/tests/mutex-entry-restored-20261020/`.

The maintained entry is restored and its affected correctness scope is
validated. No performance measurement was rerun in this restoration stage.
All seven mutex regressions, execution-class gaps, p95 latency and the strict
post-measurement host thread-set mismatch remain explicitly unresolved.
Subsequent rwlock/rwsem, real mmap/fault and list work must retain those limits
and cannot imply acceptance of the mutex comparison.

## Follow-up stage evidence and unresolved scope

The [shared-lock comparison](../shared-lock-followup-20261020/README.md)
completed 756 rwsem and 270 rwlock sessions on the same recovery VM, using
restored, validated inputs. Functional checks and exact retirement pass.
The rwsem post-run host thread set fails; rwlock's matching after receipt is
117.556 seconds late. Their ranges, misses and execution classes remain separate
from this mutex investigation.

The [current mmap/fault review](../../tests/mmap-fault-followup-20261020/README.md)
captures 46 kernel files, verifies unchanged kernel identity and documents
four concrete blockers: full-object/API migration, ownership/mode transitions,
origin-context/resource lifetime, and unvalidated transitive callbacks.
Its 1,470-check source review passes; real KD mmap/fault integration remains
explicitly unresolved, with no guest kernel changes.

The [resident-list stage](../nano-list-followup-20261020/README.md) preserves
`timing-1` (146 strict successes, one strict rwlock `NO_JIT` failure) and the
separate `rwsem-1` (48 strict successes). Both have complete archives and
independent evidence-integrity checks, and both retain immediate host-thread
mismatches. The first run's remaining 69 rwlock cases subsequently completed
in the [strict continuation](../nano-rwlock-diagnosis-20261021/README.md):
59 successes, ten NO_JIT failures, 23 exact retirements and a failed 76-thread
endpoint. Missing-case coverage is closed. The second gate diagnostic records
10,441 first-follower non-combinable refusals at eight workers; it preserves
all strict failures and does not relax admission.
The 48 rwsem cases were the untouched original task, not repetitions of
failed attempts. Reports retain every range, CV, miss and prefetch comparison.

All seven original mutex points remain unresolved: c08 at 3/4/5 workers,
pipebytes at 3/5, pipecap at 5 and RCUHT at 2. The inline-entry experiment
remains rejected, and the maintained implementation is the restored entry.
The later [latency diagnostic](../mutex-latency-20261021/README.md) completed
252 sessions, 126 exact KD retirements and 4,073,421 observations. Its independent
5,218,772-check audit passes integrity, while its host endpoint fails at
125 versus 67 threads. Plain DIRECT/OUTER throughput ratios span 0.3219–1.0593
across six comparable points; plain RCUHT splits execution classes. Sampled
p95 ratios span 1.0733–3.2231 with substantial observer effects and variance.
All seven causes and the earlier execution-class gaps remain unresolved.
Acquisition-only latency and isolated instrumentation cost remain unmeasured.
Whole-kernel replacement, RT/ww_mutex, lockdep and
oversubscription remain separately unvalidated.

All stages used a sole source writer and serial VM execution. The three
helpers (`native_api_inventory`, `rw_and_mm_audit`, `unified_api_review`) finished
read-only reviews and each reported **no files touched**. No run is active.
Acceptance remains open; no probe, admission threshold, ownership record or
ACK/retirement check was removed or weakened.
