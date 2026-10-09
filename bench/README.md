# Benchmarks

Use [the three-arm direct runner](tclock_compare/README.md) for KD, TCLock and
Linux Native spin/mutex. [Shared components](spin_cacheline/README.md) provide
the client, all-worker warmup, peak selection, source snapshots and offline readers.
Kernel payloads live under [workload_modules](../workload_modules/README.md).

## Results

| Report | Scope |
| --- | --- |
| [Protocol simplification](tclock_compare/results/20261008-protocol-simplification/README.md) | Fresh 540-session spin/mutex baseline at all 15 thread counts under `nopvspin`; rejected translator/memory candidates and rechecks retained separately |
| [Hash diagnosis](tclock_compare/results/20261008-hash-diagnosis.md) | Matched hash controls, NUMA effects and separate profiles; remaining gap against the stronger comparator |
| [Evidence index](tclock_compare/results/HISTORY.md) | All retained reports, full statistics, rejected candidates and fixed Git links to earlier reports |

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
