# Resident-list measurements after correctness validation

Status: `timing-1` stopped at a strict rwlock `NO_JIT` failure after 147 attempts:
146 successful sessions and one failed session. Its immediate host endpoint
also failed, with 83 QEMU threads against the original 67. Evidence preservation
and independent verification are complete; acceptance remains open. Shared-lock
collection and the mmap/fault source review are complete, with their documented
limits. The original recovery VM remains the only test environment.

The [task plan](task-plan.json) preserves all ten timing argument lists from
the previously retained resident-list plan. That plan selected eight and 60
workers, three repetitions, two-second measurements, collector CPU 63 and CPU
prefixes. This is a focused 264-session comparison, not the full 21-count grid.
Its geometry is unchanged; source identity is now validated `f48b90e`, whose
497 manifest files equal restored `a768361`. The original plan and all earlier
functional failures remain separate evidence.
The prepared [preflight](preflight.py) requires the original host configuration,
actual recovery snapshot, unchanged manifest and exact historical arguments,
then checks all ten dry-run plans before allowing the serial supervisor.
The [post-run verifier](verify.py) normally requires all 264 results, frozen
sources/binaries, 44 compiled-function audits, 96 KD loaded-image receipts and
exact retirements. It retains both strict environment endpoints; a failed
post-run check remains a failure. Its explicit stopped-run mode checks the exact
147 attempted cases and preserves the failed and missing verdicts.
The [independent archive review](offline-review.py) recomputes worker
effects, timing windows, execution classes and three-round ranges from raw
records. It reconstructs provider sources and checks compiled/generated ELF
extents, loaded bytes and every retained prefetch instruction. It imports only
hash-pinned inert readers and ran on `380G10` after archival.
Static review reconciled the verifier with the unchanged TCLock record schema:
exclusive TCLock has no KD completion counter. Its absence is checked explicitly;
TCLock quiescence and returned native-mutex delegation use their own receipts.
Missing KD counters still fail verification. These source-host checker changes
were synchronized after the stopped run passed the extended idle checks.
The ELF/image reader separately passed a
[70,425-check inert review](preparation/historical-code-review.json) of the
retained `list-functional-4` archive: 14 compiled audits and 14 loaded images,
with zero issues. The first review command selected nonexistent timing
`records.json` files in that functional archive; its
[error](preparation/initial-selector-error.log) is retained. Selecting the
actual frozen plan and per-session receipts allowed the unchanged code-image
reader to complete. No workload ran, and this historical review does not
validate the later timing results.

| Family | Variants | Controls | Mix | Sessions |
| --- | --- | --- | --- | ---: |
| Spin | plain/prefetch × 16/128 nodes | Native, TCLock, KD | exclusive | 72 |
| Public mutex | same | Native, TCLock, KD | exclusive | 72 |
| Rwlock | same | Native, TCLock, KD | 20% writes | 72 |
| Sleeping rwsem | same | Native, KD | 20% writes | 48 |

These are the bounded, resident-memory
[list payloads](../../../../../docs/BENCHMARK_WORKLOADS.md#resident-linked-list-traversal).
They perform no allocation or page-fault workload inside the critical section.
Exclusive post-work remains 64 rounds; shared-family post-work remains four.
NUMA, batch 1024, queue prefetch 2, entry ratio 2 and UBSAN-off settings remain
explicit. Payload prefetch is a separate variant from queue prefetch.

The [16 functional cases](../../tests/native-continuation-20261020/README.md)
already passed with returned JIT bodies, list integrity, loaded-image checks and
exact retirement. Timing retains the original JIT requirements and stops on a
failure. It will keep every repetition, worker result, source/binary identity,
prefetch audit and retirement record. Three-round groups require a single
execution class; missing or partial JIT evidence cannot be scored as a returned
body. Any within-backend hint comparison also requires matching family, size,
worker count, mix, source and instrumentation. Ranges and spreads will be
reported; p95 latency remains unmeasured.

## Admission and stopped collection

The first strict admission, `preflight-1`, **failed before any timing session**.
Its host capture at 2026-10-20 17:02:04.263592 UTC had 70 QEMU threads against
the required original 67. The additional TIDs 421142, 421144 and 421145 were
named `worker`, each pinned to CPU 63; every original thread identity and
affinity remained unchanged. No host setting or admission check was changed.
[Failed health](preflight-1/health.json) confirms an idle guest, all 497 source
hashes unchanged, zero measured sessions and no timing output directory.

The [independent preservation review](preflight-1/offline-review.json) passed
633 checks; the preflight itself remains failed. The
[archive manifest](preflight-1/archives.json) SHA-256 is
`130790ae1ce9092a103e764906049608b8738e6d936b8fbae01034cda18e06a7`.
Raw archives are under
`bench/results/10.176.26.71/raw/bench/nano-list-followup-20261020/preflight-1/archives/`.
The first later [thread inspection](preflight-1/thread-review-1.json) saw those
three TIDs absent but 68 total threads; a separately retained
[full receipt](preflight-1/later-host-receipt.json) at 17:04:49 still had 70,
with different worker TIDs. The [17:05:44 inspection](preflight-1/thread-review-2.json)
observed 67 and no worker-named threads. These are observations of natural
thread turnover; the source of that work and within-run interference are
unmeasured. Later receipts do not repair the failed admission.

The new full host receipt at **17:06:19.825167 UTC** matched the original
67-thread configuration, pins, frequency and memory policies, boot, dependencies
and actual recovery snapshot. `preflight-2` passed all 497 source hashes and
the exact ten dry-run plans, totaling 264 sessions. The unchanged supervisor
started the first task at **17:07:03.292316 UTC** under:

`/root/kdlock-evidence/10.176.26.71/bench/nano-list-followup-20261020/timing-1/`

The source snapshot at collection admission is `6c124de`; measured inputs remain
the fixed `f48b90e` manifest. Only documentation and evidence helpers changed
during the preceding idle synchronization. A source-host launcher invokes the
same VM supervisor once and captures the host endpoint after its SSH command
returns. It adds no observer during timing; SHA-256 is
`215d64e540040a69bb647e2f2afc446be5a4ee30937a8b8b2f27a14215ce1213`.
Its exit code does not establish drain; the supervisor and per-session exact
retirement checks still do that.

The first eight tasks completed all 144 spin/mutex sessions. The ninth task
completed the Native and TCLock controls, then failed
`rwlock-w20/list-n16-kdlock-w020-t08-r00` because no complete JIT body executed.
The remaining 69 rwlock cases and all 48 rwsem cases were not run.
The supervisor returned at 17:22:16.808190 UTC; its `FAILED` state and
`final_idle=false` remain unchanged. The immediate host capture began at
17:22:17.146443 UTC and reported 83 threads. A later idle observation does not
repair either verdict. A separate stopped-run verification mode retains the
strict failure, checks all measured business effects and retirements, and
explicitly accounts for the 117 missing cases. It never labels this run complete
or includes the failed KD sample in performance comparisons.

## Archived verification and diagnosis

[VM health](timing-1/health.json) confirms 147 drained attempts, 146 strict
successes and one strict failure. All 147 business oracles pass. It verifies
4,254 source hashes, 80 binary hashes, 36 compiled-function audits and 49 loaded
KD images with exact `{state:2, modules:0, writers:0, frames:0}` retirements.
No retained per-session kernel fault matches were found. The 48 successful
KD spin/mutex cases all returned JIT bodies; their combined counters report
438,339,643 matching entries/completions. Total measured work, including the
failed rwlock sample, is 940,407,808 operations.

The [independent review](timing-1/offline-review.json) completes 250,374 checks
over 10,505 files and 98 symlinks. Evidence integrity passes; the retained host
placement failure is its sole remaining check issue. The strict `NO_JIT`
failure is separately recorded, excluded from scoring, and never converted to
a pass. The [endpoint receipt](timing-1/endpoint-timing.json) establishes a
0.338253-second gap between the failed child's exit and the original host
capture. The supervisor's `final_idle=false` is preserved separately from the
verifier's later successful idle check.

The first inert review had 25 checker-schema issues: shared workers record
successful calls as JSON `null`, while the exclusive reader expects numeric
zero; a failed sample also requires a null accepted-throughput field.
The correction checks the exact shared schema before adapting a copy for
timing arithmetic, and retains the failed status. Initial outputs and reader
bytes remain under raw `review-initial/`, with their
[hash receipt](timing-1/initial-review-receipt.json). No workload, measurement or
archive changed. An earlier archive metadata wrapper used `threads` instead of
the host receipt's `tasks` key and stopped before archiving; its
[error](timing-1/initial-archive-wrapper-error.log) is retained.

The [rwlock failure review](timing-1/no-jit-review.json) binds the
[session](timing-1/failed-session.json), [kernel log](timing-1/failed-session-kernel.log)
and current source hashes. That sample completed 18,146,048 operations:
14,516,840 reads and 3,629,208 writes. The ABI3 NORMAL image matched its loaded
bytes; measured entries, completions, address guards and helper waves were all
zero. Teardown recorded zero combiners and cold CPU/per-lock heat on CPUs 0–7.

Source inspection explains why publication alone cannot satisfy this test.
Ungated successful writers execute locally. Gated writers additionally require
CPU and per-lock heat before requesting delegation. CPU heat samples every
1,024 MCS publications, retains entry-ratio limit 2 and a time bound; native
queue heads can veto heat unless six linked successors exist before the
captured tail. Lock heat has its own 512-record/time gate.
These paths are consistent with the absence of delegated execution in this
mixed eight-worker case. They do **not** establish which gate rejected each
timed acquisition: the final `unfinished_batch` counters are residuals, not
lifetime totals or phase-local history. No claim is made that no earlier
1,024-publication boundary occurred. The exact cause remains unresolved.
All gates, requirements, warmups and repetition counts remain unchanged.

[Archive manifest](timing-1/archives.json):
`7bdb750e72fc791c2a0dc57ac7e5bb669f93fffb77e471b01c92e27a2047e805`.
Raw archives are under
`bench/results/10.176.26.71/raw/bench/nano-list-followup-20261020/timing-1/archives/`.
The 40,836,946-byte matrix archive is
`a52e436e781d83c3718992856e7e1efd77efd8d21b4dee9beaba7212d1322386`;
the 144,303-byte metadata archive is
`a0ca37880041e870aec48e101959bba2935376a3efb5cd1265579be8960d315d`.

## Descriptive timing and variance

These observations retain the failed host endpoint and do not establish
acceptance or resolve the seven earlier mutex regressions. Three-repeat groups
are separate by family, size, worker count, variant and execution class.
The [groups](timing-1/groups.csv), [control comparisons](timing-1/comparisons.csv)
and [prefetch comparisons](timing-1/prefetch.csv) retain every range and sample
standard deviation/CV.

Spin meets the observed median-whole/best-peak parity rule at all eight points
against each control. Mutex meets it at four of eight points against Native
and seven of eight against TCLock. The five misses are:

| Mutex case | Control | Median whole ratio | Best peak ratio |
| --- | --- | ---: | ---: |
| 16 nodes, plain, 8 workers | Native | 0.7553 | 0.7403 |
| 16 nodes, prefetch, 8 workers | Native | 0.8263 | 0.8036 |
| 128 nodes, plain, 8 workers | Native | 0.7605 | 0.6726 |
| 128 nodes, plain, 8 workers | TCLock | 0.8627 | 0.7815 |
| 128 nodes, prefetch, 8 workers | Native | 1.0894 | 0.7371 |

The plain 128-node/eight-worker mutex case is the one observed separated
5% loss against Native. Host interference remains unmeasured, so this is
descriptive evidence rather than causal attribution.

Maximum three-run whole-rate spreads `(max/min−1)×100`, with sample CV:

| Family/backend | Largest spread | CV | Whole-rate range, Mops/s |
| --- | ---: | ---: | ---: |
| KD spin | 5.56% | 2.87% | 6.322–6.674 |
| Native spin | 12.86% | 6.52% | 0.276–0.312 |
| TCLock spin | 4.09% | 2.15% | 4.084–4.251 |
| KD mutex | 4.79% | 2.56% | 5.596–5.864 |
| Native mutex | 1326.48% | 77.77% | 0.121–1.726 |
| TCLock mutex | 35.90% | 16.43% | 2.461–3.344 |

Payload prefetch meets the same two-rate rule in one of four KD spin groups
and three of four KD mutex groups. Across all three backends it meets six of
12 spin and five of 12 mutex comparisons. These are separate variants; no
blanket benefit is established. Rwlock lacks matched repetitions and rwsem
has no timing in this run. P95 latency and runtime host interference remain
unmeasured; the 117 missing cases and strict failure remain explicit gaps.

## Separate rwsem continuation

The [rwsem selection](rwsem-task-plan.json) contains only the original tenth
task, with all arguments unchanged: 48 sessions, two sizes, plain/prefetch,
eight/60 workers, three repetitions and strict returned-JIT enforcement.
The same supervisor and 497-file measured source manifest apply. This new
`rwsem-1` run requires its own fresh strict preflight and immediate host endpoint.
It repeats none of the 147 attempted sessions and does not resume or relabel
`timing-1`. The 69 unrun rwlock cases remain unresolved. Preparation and exact
selection checks are ready; collection has not started.
