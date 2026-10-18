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
Its focused validation is recorded separately in [VALIDATION](VALIDATION.md);
it is not a new performance matrix or a claim of throughput parity.

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
