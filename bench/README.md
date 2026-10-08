# Benchmarks

Use [the three-arm direct runner](tclock_compare/README.md) for KD, TCLock and
Linux Native spin/mutex. [Shared components](spin_cacheline/README.md) provide
the client, all-worker warmup, peak selection, source snapshots and offline readers.
Kernel payloads live under [workload_modules](../workload_modules/README.md).

## Results

| Report | Scope |
| --- | --- |
| [Final mutex matrix](tclock_compare/results/20261003-mutex-followup.md) |15 thread points, cacheline/hash; broader performance acceptance still fails |
| [Full statistics](tclock_compare/results/20261003-mutex-followup-statistics.md) | All valid rounds, whole throughput, spread and rechecks |
| [Spin36 analysis](tclock_compare/results/20260928-spin36-analysis.md) | Hash gap, cacheline control, NUMA and PMU attribution limits |
| [Packed continuation](tclock_compare/results/20260928-packed-continuation.md) | Current spin layout geometry and matched regression checks |
| [Evidence index](tclock_compare/results/HISTORY.md) | Fixed Git records for superseded reports, failed candidates and earlier charts |

These are recorded measurements, not reruns of subsequent cleanup commits.
Raw ignored/local/guest archives remain intact. A fresh checkout supplies reports,
not those large original run directories.

## Measurement rules

The intended comparison uses fixed 2.5 GHz, NUMA-on, UBSAN-off KD benchmark provider,
48000 operations of warmup per worker, three rounds, two-second measurement and the
highest valid 300 ms window after settling. Explicitly select the full 15-point
thread set; the runner's shorter default is not the complete matrix.

Keep peak min/median/max/spread and whole throughput, actual JIT/delegation status,
worker/node shares, frozen source/ELF/kernel identity and drain. Amortized ns/op is
inverse aggregate throughput, not measured acquisition latency. Failed/NO_JIT
samples stay in records and do not become valid JIT positives.

The runner guide owns commands and result fields; [performance plan](../docs/PERFORMANCE_PLAN.md)
owns acceptance and next experiments. [Tests](../tests/README.md) owns correctness
check selection; [operations](../docs/AGENTS.md) owns guest/recovery/drain rules.
