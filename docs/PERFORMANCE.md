# Performance status

The reader/writer semaphore (rwsem) implementation measured in `c21345b` is
**accepted as the current version**, including the two-worker regressions below.
Acceptance identifies the maintained implementation; it does not turn every
measured configuration into a performance pass.

Throughput is reported in **Mops/s**, millions of completed operations per second.
The **whole-run median** is the middle of three repetition rates, each measured
over its full timed interval. A ratio of 2× means twice the reference rate;
0.286× means 28.6% of that rate, or 71.4% slower. A **JIT** (just-in-time compiled)
body counts as returned only after delegated execution reaches its matching
unlock and completes the return protocol. `NO_JIT` means no such bodies were
returned in that measurement. **Drained** means all requests and their required
references and acknowledgements finished. The
[terminology guide](TERMINOLOGY.md) defines the remaining lock and evidence terms.

The later [instruction-exit change](design/admission.md#checked-instruction-exits)
has focused correctness validation, including ordinary rwsem delegation controls.
It does not have a new timed comparison. The throughput values below belong to
their recorded source versions; acceptance of those results does not measure the
additional flag-preservation cost in images that contain instruction markers.

The accepted current mutex is KD-only `d2a2304`: KD physical exclusion with the
legacy delegation queue. The [2026-10-17 paired report](../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
contains 504 complete, drained sessions: two workloads, 21 worker counts, three
repetitions and four arms (accepted compatibility baseline, KD-only, Native,
TCLock). It uses the regular 64-vCPU VM and collector 63.

## Current mutex result

At 60 workers, median whole-run throughput in Mops/s is:

| Workload | Linux Native | TCLock | Compatibility baseline | Current KD-only | Change vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01, post64 | 4.276 | 3.107 | 4.856 | 4.838 | −0.39% |
| api-pipebytes-query-n16 | 1.821 | 2.447 | 5.371 | 5.130 | −4.48% |

The main matrix has 41 of 42 points within 5% of baseline or faster. Pipebytes
at 44 workers was 7% slower. Nine additional fresh pairs at that point have
medians 5.175/5.193 Mops/s (baseline/current, +0.35%), but the median paired change
is −2.50% and six of nine pairs are slower. Keep this follow-up separate from
the original matrix; it does not erase the original regression or its variability.

The 252 KD measurements comprise 225 JIT-positive sessions and 27 NO_JIT controls.
The report retains every sample, whole-run and warmed-peak statistics, spread,
source identities, failed intermediate trials and independent archive replay.
The initial consolidation preserved the accepted runtime bytes. The subsequent
[feature reintegration](history/feature-reintegration-20261018.md) adds ordinary
rwsem and restores snapshots/tooling while retaining the accepted mutex source.
Its focused validation is recorded separately in [VALIDATION](VALIDATION.md).
The later rwsem comparison below measures the new writer interface separately;
it does not rerun or replace the accepted mutex comparison.

## Accepted rwsem implementation, c21345b

The [optimization report](../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
records all **756 correct, drained Native/KD sessions**: c01/c08/RCUHT, 1%/20%
writes, the standard 21 worker counts through 60, three repetitions and post4
work (four dependent arithmetic rounds after each unlock). At 60 workers,
accepted KD median whole-run throughput is **5.10–7.42×**
the initial KD rwsem and **1.546–2.352×** contemporary Native. Low-count
regressions remain; this is not an improvement at every configuration.

Separate waiting queues now serve callers waiting for permission to enter and
writers waiting for existing readers to finish. Frequently written fields occupy
different cachelines, reducing interference between CPU caches. Before sleeping,
callers poll: they repeatedly check whether they can proceed, for up to 16,384
checks, stopping earlier if the scheduler needs the CPU. Ordinary writers also
read the admission state before the authoritative atomic compare-and-exchange
that reserves it. The budget is accepted tuning for this captured platform, not
a universal optimum or a fixed time bound. Existing readers still finish before
a writer publishes a pinned delegation request. The
[design](design/rwsem_implementation.md) explains
the ordering and the object-size tradeoff (384 to 512 bytes). The accepted KD
mutex protocol, heat policy and wrapper ABI remain unchanged.

The before/final full grids have source-content IDs `03e379fc02be5ab7` and
`96940efc0a925d7f` respectively (canonical manifest hash prefixes, not Git IDs).
They share the captured `6.1.159-kdclobber2` kernel, 64-vCPU topology, worker
placement and collector 63. The initial `485729f` grid, fresh baseline screen,
later baseline-repeat screen and candidate screens remain separate runs.

At 60 workers, median whole-run throughput in Mops/s is:

| Workload | Writes | Linux Native | Accepted KD rwsem | KD / Native | KD / initial KD |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01 | 1% | 3.561 | 7.900 | 2.219× | 7.416× |
| c01 | 20% | 1.421 | 2.197 | 1.546× | 5.458× |
| c08 | 1% | 3.299 | 7.758 | 2.352× | 7.250× |
| c08 | 20% | 1.412 | 2.183 | 1.546× | 5.495× |
| RCUHT | 1% | 3.262 | 7.312 | 2.242× | 6.927× |
| RCUHT | 20% | 0.873 | 2.047 | 2.344× | 5.100× |

For each comparison, both the median whole-run rate and the best eligible
post-warmup window must be at least the reference rates to count as a pass.
Across 126 points, KD meets both observed median-whole and best-peak criteria
at **110 points versus the initial KD**, with 12 failures and four split-status
comparisons. Against contemporary Native there are **117 passes, six failures
and three split-status comparisons**. At 20% writes/two workers, c01 and c08
retain substantial whole-run regressions versus the initial KD: **0.286× and
0.276×** respectively, approximately **71–72% slower**. These regressions remain
part of the accepted implementation's documented performance. The six Native
misses are all three 20%/one-worker points, c08/1%/two workers, and c01/c08 at
20%/36 workers. The report retains
all remaining differences and repetition ranges; these descriptive thresholds
are not significance tests.

The 378 KD timed sessions include **155 with returned JIT bodies and 223
NO_JIT controls**, with **7,275,620 matching entries and completions**. Final
c01/20% at five, six and seven workers splits execution statuses; the initial
c08/20%/16-worker point also splits. All planned sessions completed correctly.
A split point lacks one homogeneous three-repetition group; it was not skipped.
All six 60-worker points are homogeneous: 1% writes has zero JIT, while 20%
writes has returned JIT in every repetition. The high-count improvement therefore
cannot be attributed solely to delegation.

The separate **270-session spinning-rwlock reference** completed correctly and
drained: Native/TCLock/KD, the same three payloads and two mixes, and
1/8/32/36/60 workers with three repetitions. KD meets both observed criteria at
29/30 points against Native and 28/30 against TCLock. Its misses are c08/20%/one
worker against both and RCUHT/1%/60 workers against TCLock. TCLock's stack-based
delegation share is unmeasured. This port has no sleeping TCLock rwsem; these
spinning measurements are not rwsem parity or evidence of sleeping/cancellation/
downgrade support. The KD rwlock algorithm was not changed.

Focused screens preserve an unresolved first-repetition Native reduction in
both baseline and selected runs. Governor-policy equality, sampled frequencies
and inactive tracing do not isolate its cause; no samples were normalized away.
Separate baseline/final diagnostic profiles each completed six sessions with
tracing restored. For c01/20%/60 workers, KD median hits/op changed from
2.0460 to 0.000819 for `prepare_to_wait_event`, 2.0314 to 0.000810 for
`autoremove_wake_function`, 1.1602 to 0.001123 for `schedule`, and 9.6844 to
0.014329 for `_raw_spin_lock_irqsave`. Baseline profile sessions had no returned
JIT and final sessions did, so these observations do not isolate each change.
Profiles include background activity, are excluded from throughput scoring, and
overlapping function counts/times are not exclusive CPU costs.

Independent offline arithmetic replay passed for all **2,118 timed sessions**:
the initial/final grids (756 each), seven separate 48-session screens (336)
and the 270-session spinning reference. It recomputed protected effects, JIT
deltas, whole-run rates, eligible peaks and comparison groups from retained
plans, records and samples. This was an evidence check, not a new kernel test.
Six captured archives passed integrity verification. Both final-grid and
final-reference manifests match all 233 reviewed runtime inputs. The
[validation receipt](../bench/results/10.176.26.71/tests/rwsem-optimization-20261018/README.md)
records focused API/JIT checks and byte-equivalence scopes: 16 selected mutex
files within 112 preserved runtime files against `d2a2304`, and 115 unchanged
provider/header/translator/daemon files against `485729f`. These scopes overlap.

## Historical rwsem writer-delegation baseline, 2026-10-18

The [initial rwsem report](../bench/results/10.176.26.71/bench/rwsem/20261018/README.md)
contains all 756 correct, drained Native/KD sessions: c01/c08/RCUHT, 1%/20% writes,
the standard 21 worker counts through 60, three repetitions and post4 work.
This is the `485729f` shared-queue implementation before bounded polling and
queue separation. Its admission phase preserves the accepted mutex protocol.
All 233 frozen runtime inputs matched its recorded checkout when measured.
The 64-vCPU VM used collector 63, recorded CPU/NUMA placement and the host's
`ondemand` governor; those receipts do not describe the later provider bytes.

At 60 workers, median whole-run throughput in Mops/s is:

| Workload | Writes | Linux Native | KD rwsem | KD / Native |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1% | 3.576 | 1.065 | 0.298× |
| c01 | 20% | 1.424 | 0.403 | 0.283× |
| c08 | 1% | 3.259 | 1.070 | 0.328× |
| c08 | 20% | 1.415 | 0.397 | 0.281× |
| RCUHT | 1% | 3.270 | 1.056 | 0.323× |
| RCUHT | 20% | 0.868 | 0.401 | 0.463× |

KD meets both observed peak and median-whole criteria at 26 of 126 points and
is slower on at least one metric at 99. The remaining c08/20%/16-worker point
has all six valid measurements but split KD execution statuses, so its groups
are reported separately. No benchmark was skipped. At 60 workers KD is 54–72%
slower on median whole throughput; that captured implementation was not a high-count
performance improvement over Native for these mixes.

Only seven of 378 KD timed sessions completed JIT bodies, all c08/20% writes:
one repetition at 16 workers and all three at 36 and 40. They completed 1,752
delegated writes in total. The other 371 sessions, including all 60-worker cases,
were `NO_JIT`. The unchanged heat policy was retained; publication was not
counted as execution. Four separate writer-heavy functional checks establish
substantial returned delegation, as recorded in the
[initial validation receipt](../bench/results/10.176.26.71/tests/rwsem-delegation-20261018/README.md).
Those different mixes are not pooled into this historical performance matrix.

The report retains every repetition, spread, peak and whole-run statistics,
JIT groups, all regressions, plots, verified raw archives and source identities.
Real mmap integration and Linux rwsem fairness remain outside this comparison.

## Other lock families and earlier versions

The [2026-10-15 c01 rwlock report](../bench/results/10.176.26.71/bench/rwlock/20261015-c01/README.md)
contains 378 accepted sessions at 1%/20% writes and the same 21-count grid.
It meets its strict best-peak and median-whole criterion at 39/42 points, with
mixed JIT statuses kept separate. These are measurements of its captured source,
not a rerun of the consolidated provider.

The [all-workload report](../bench/results/10.176.26.71/bench/comparison/workloads-20261015T180603Z/README.md)
and [expanded mutex report](../bench/results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md)
preserve spin/rwlock/API coverage and the superseded owned-mutex implementation.
Their KD mutex numbers do not describe the selected main version. The
[legacy compatibility report](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md)
and [recovery report](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-recovery-20261016T113518Z/README.md)
explain the path to the accepted implementation.

Use the [workload catalog](BENCHMARK_WORKLOADS.md) and [runner guide](../bench/README.md)
for future comparisons. Keep machines, topologies, post-work, source versions,
instrumentation and JIT/NO_JIT groups distinct. No lock wins every supported
configuration. Historical matrices and rejected candidates remain in the
[results index](../bench/results/README.md) and [history](history/README.md).
