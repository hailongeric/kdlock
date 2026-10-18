# Performance status

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

## Rwsem writer delegation, 2026-10-18

The [rwsem report](../bench/results/10.176.26.71/bench/rwsem/20261018/README.md)
contains all 756 correct, drained Native/KD sessions: c01/c08/RCUHT, 1%/20% writes,
the standard 21 worker counts through 60, three repetitions and post4 work.
The new admission phase preserves the accepted mutex source and protocol.
All 233 frozen runtime inputs match the final checkout. The 64-vCPU VM uses
collector 63, unchanged CPU/NUMA placement and the host's `ondemand` governor.

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
slower on median whole throughput; this implementation is not a high-count
performance improvement over Native for these mixes.

Only seven of 378 KD timed sessions completed JIT bodies, all c08/20% writes:
one repetition at 16 workers and all three at 36 and 40. They completed 1,752
delegated writes in total. The other 371 sessions, including all 60-worker cases,
were `NO_JIT`. The unchanged heat policy was retained; publication was not
counted as execution. Four separate writer-heavy functional checks establish
substantial returned delegation, as recorded in [validation](VALIDATION.md).
Those different mixes are not pooled into this performance matrix.

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
