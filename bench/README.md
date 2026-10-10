# Benchmarks

Use [the three-arm direct runner](tclock_compare/README.md) for KD, TCLock and
Linux Native spin/mutex. [Shared components](spin_cacheline/README.md) provide
the client, all-worker warmup, peak selection, source snapshots and offline readers.
Kernel payloads live under [workload_modules](../workload_modules/README.md).

Use the [rwlock comparison](rwlock_compare/README.md) for native, TCLock and KD
read-write locks: the default RCUHT cases use 1% and 20% writes across
all 15 thread counts, with returned-writer JIT evidence and validated warmed peaks.

## Results

The RCUHT rwlock comparison passed correctness and drain in all 270 sessions;
KD met strict throughput parity at 21 of 30 configurations. The separate
spin/mutex optimization phase closed on 2026-10-09. Reports retain the remaining
gaps; superseded reports are retrieved from fixed Git records.

| Report | Scope |
| --- | --- |
| [RCUHT rwlocks](rwlock_compare/results/20261010-rcuht/README.md) | 1%/20% writes on the hash payload; all 15 thread counts, ABI3 JIT writers and strict Native/TCLock parity checks |
| [Rwlock scaling](rwlock_compare/results/20261009-scaling/README.md) | Historical ABI1, 1%/20% writes on one cacheline; all 15 thread counts, 270 sessions, throughput curves and NUMA progress |
| [Initial rwlock mixes](rwlock_compare/results/20261009/README.md) | Native/TCLock/KD, 180 cacheline sessions at 1/16 workers, 12 KD controls, and the historical ABI1 hash-writer refusal resolved by ABI3 |
| [Protocol simplification](tclock_compare/results/20261008-protocol-simplification/README.md) | Fresh 540-session spin/mutex baseline at all 15 thread counts under `nopvspin`; rejected translator/memory candidates and rechecks retained separately |
| [Historical hash diagnosis](tclock_compare/results/HISTORY.md#hash-diagnosis) | Matched hash controls, NUMA effects and separate profiles in a fixed Git snapshot |
| [Evidence index](tclock_compare/results/HISTORY.md) | All retained reports, full statistics, rejected candidates and fixed Git links to earlier reports |

These are recorded measurements, not reruns of subsequent cleanup commits.
Raw ignored/local/guest archives remain intact. A fresh checkout supplies reports,
not those large original run directories.
The historical measured environment had 40 vCPUs. Follow
[guest setup](../docs/PROJECT_GUIDE.md#guest-workflow) and explicitly choose a
collector outside the actual worker cohorts before new runs.

## VM migration validation

The 2026-10-10 migration to Ubuntu host `eric@10.176.26.71` was verified with
60 pinned guest CPUs, 24 GiB RAM, the captured `6.1.159-kdclobber2` kernel,
`nopvspin`, voluntary preemption and a fresh recovery snapshot. The host uses
an `ondemand` governor; these measurements remain separate from the historical
40-CPU, fixed-2.5-GHz reports.

One 16-worker KD spin functional check completed 1,600,000 operations and
455,538 JIT bodies. The RCUHT comparison completed all 72 sessions correctly
and drained: Native/TCLock/KD, 1%/20% writes, 1/16/32/56 workers, three rounds,
collector CPU 58. KD had 15 JIT-positive and nine `NO_JIT` sessions. Seven of
eight configurations met throughput parity. At 1% writes/56 workers, KD was
below TCLock by 1.66% on best peak and 4.52% on median whole-run throughput.

Run on the physical host:

```sh
cd /home/eric/vm/qemu-scripts
./vm_ssh.sh                # or ssh kdlock-vm
./bench.sh                 # new snapshot, smoke and comparison, host archive
```

Guest evidence is `/root/kdlock-evidence/migration-20261010T070707Z`.
The host archive is `/home/eric/vm/migration/bench-20261010T070707Z.tar.gz`, with
SHA256 `bcf6dc00c9d298d8c90780f28b4e2a8d3f191af7ffeede3c731751cde2193801`.
`/home/eric/vm/migration/validation.json` records the acceptance and
`host-environment.json` records the physical CPU mappings and governor.

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

The [spin/mutex](tclock_compare/README.md) and [rwlock](rwlock_compare/README.md)
runner guides own commands, result fields and acceptance rules;
[performance status](../docs/PERFORMANCE.md) records measured outcomes and deferred
designs. [Tests](../tests/README.md) owns correctness
check selection; [operations](../docs/AGENTS.md) owns guest/recovery/drain rules.
