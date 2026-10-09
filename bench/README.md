# Benchmarks

Use [the three-arm direct runner](tclock_compare/README.md) for KD, TCLock and
Linux Native spin/mutex. [Shared components](spin_cacheline/README.md) provide
the client, all-worker warmup, peak selection, source snapshots and offline readers.
Kernel payloads live under [workload_modules](../workload_modules/README.md).

Use the [rwlock comparison](rwlock_compare/README.md) for native, TCLock and KD
read-write locks: the default RCUHT cases use 1% and 20% writes across
all 15 thread counts, with returned-writer JIT evidence and validated warmed peaks.

## Results

The optimization phase closed on 2026-10-09. The final report retains all samples
and remaining gaps; superseded reports are retrieved from fixed Git records.

| Report | Scope |
| --- | --- |
| [RCUHT rwlocks](rwlock_compare/results/20261010-rcuht/README.md) | 1%/20% writes on the hash payload; all 15 thread counts, ABI3 JIT writers and strict Native/TCLock parity checks |
| [Rwlock scaling](rwlock_compare/results/20261009-scaling/README.md) | 1%/20% writes on one cacheline; all 15 thread counts, 270 sessions, throughput curves and NUMA progress |
| [Initial rwlock mixes](rwlock_compare/results/20261009/README.md) | Native/TCLock/KD, 180 cacheline sessions at 1/16 workers, 12 KD controls, and the hash-writer JIT admission limit |
| [Protocol simplification](tclock_compare/results/20261008-protocol-simplification/README.md) | Fresh 540-session spin/mutex baseline at all 15 thread counts under `nopvspin`; rejected translator/memory candidates and rechecks retained separately |
| [Historical hash diagnosis](tclock_compare/results/HISTORY.md#hash-diagnosis) | Matched hash controls, NUMA effects and separate profiles in a fixed Git snapshot |
| [Evidence index](tclock_compare/results/HISTORY.md) | All retained reports, full statistics, rejected candidates and fixed Git links to earlier reports |

These are recorded measurements, not reruns of subsequent cleanup commits.
Raw ignored/local/guest archives remain intact. A fresh checkout supplies reports,
not those large original run directories.

## Measurement rules

The intended comparison uses fixed 2.5 GHz, NUMA-on, UBSAN-off KD benchmark provider,
48000 operations of warmup per worker, three rounds, two-second measurement and the
highest valid 300 ms window after settling. For spin/mutex, explicitly select the
full 15-point thread set; their shorter defaults are not the complete matrix.
The rwlock runner defaults to that full thread set.

Keep peak min/median/max/spread and whole throughput, actual JIT/delegation status,
worker/node shares, frozen source/ELF/kernel identity and drain. Amortized ns/op is
inverse aggregate throughput, not measured acquisition latency. Failed/NO_JIT
samples stay in records and do not become valid JIT positives.

The runner guide owns commands, result fields and acceptance rules;
[performance status](../docs/PERFORMANCE.md) records the closed phase and deferred
designs. [Tests](../tests/README.md) owns correctness
check selection; [operations](../docs/AGENTS.md) owns guest/recovery/drain rules.
