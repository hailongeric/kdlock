# Benchmarks

Choose the runner for the lock you want to compare. Both runners test KD, TCLock
and Linux Native with matching workloads:

- [Spin/mutex comparison](tclock_compare/README.md): spinlocks and ordinary mutexes.
- [Rwlock comparison](rwlock_compare/README.md): read-write locks, with RCUHT at
  1% and 20% writes across the historical 15-point thread set by default.
- [Complete comparison](../tools/vm/README.md#complete-164-worker-comparison):
  all three lock families and maintained performance payloads at 22 worker counts.

[Shared components](spin_cacheline/README.md) handle warmup, peak selection,
source snapshots and offline reports. The kernel code being measured lives under
[workload_modules](../workload_modules/README.md).

## Results

Reports and raw archives are separated by the physical host that ran them;
see [the results index](results/README.md). All new tests and benchmarks run
in the VM on `10.176.26.71`, after source edits on `380G10` are synchronized using
`python3 tools/vm/sync_to_vm.py`. The regular boot has 64 vCPUs with 32 cores per
NUMA node; use collector CPU 63 and exclude it from worker cohorts. The complete
64-worker comparison uses a temporary 66-vCPU boot, described below.

Live benchmark output goes outside the guest checkout to
`/root/kdlock-evidence/10.176.26.71/bench/<run>`. Host archives belong in
`bench/results/10.176.26.71/raw/bench/<run>/`, and compact published reports in
`bench/results/10.176.26.71/bench/<runner>/<run>/`.

The [complete 22-point comparison](results/10.176.26.71/bench/comparison/full-matrix-20261010T094831Z/README.md)
covers **1–8 workers in steps of one, then 12–64 in steps of four**, under KDLock,
TCLock and Linux Native. It includes spin/mutex cacheline sizes 1/8/16 and RCUHT,
plus rwlock sizes 1/2/4/8/16 and RCUHT at 1%/20% writes: **3,960 timed sessions**,
three rounds per backend and configuration. All final-matrix sessions passed
data checks and drained. Reports retain all samples, round
variation, JIT/NO_JIT evidence, CSV/JSON and scaling plots. Workers use guest
CPUs 0–31,33–64 on distinct host cores, with collector vCPU 65. At 64 workers,
the collector and QEMU services share physical host core 63 with the last worker;
the report records this limitation. The host governor is `ondemand`.

The [earlier bounded 64-vCPU comparison](results/10.176.26.71/bench/comparison/performance-20261010T081816Z/README.md)
contains 72 rwlock, 36 spin and 36 mutex sessions, with three rounds per backend
and configuration. All 144 passed correctness and drained; KD met the strict
target for peak and whole-run throughput at 10 of 16 selected configurations.
The report provides tables, scaling charts, round variation and separate
JIT/NO_JIT evidence. It uses current working-tree source and `ondemand` host
frequency policy; it is a bounded comparison, not the full matrix or a measured
gain over the original host.

On the original 40-vCPU host, all 270 RCUHT rwlock runs produced correct results
and shut down cleanly. KD matched or exceeded both comparators on peak and whole-run throughput at 21 of
the 30 combinations of write percentage and thread count. The separate
spin/mutex optimization phase closed on 2026-10-09. Reports retain the remaining
gaps; superseded reports are retrieved from fixed Git records.

| Report | Scope |
| --- | --- |
| [Complete 22-point comparison](results/10.176.26.71/bench/comparison/full-matrix-20261010T094831Z/README.md) | `10.176.26.71`: all maintained spin/mutex/rwlock payloads, 1–8 and 12–64 workers, 3,960 sessions; temporary 66-vCPU VM, collector 65 shares a physical core at 64 workers |
| [Earlier bounded 64-vCPU comparison](results/10.176.26.71/bench/comparison/performance-20261010T081816Z/README.md) | `10.176.26.71`: RCUHT rwlocks at 1/16/32/56 workers and spin/mutex cacheline at 1/16/32/36 workers; 144 timed sessions, collector CPU 63 |
| [RCUHT rwlocks](results/380G10/bench/rwlock_compare/20261010-rcuht/README.md) | 1%/20% writes on the hash payload; all 15 thread counts, ABI3 JIT writers and strict Native/TCLock parity checks |
| [Rwlock scaling](results/380G10/bench/rwlock_compare/20261009-scaling/README.md) | Historical ABI1, 1%/20% writes on one cacheline; all 15 thread counts, 270 sessions, throughput curves and NUMA progress |
| [Initial rwlock mixes](results/380G10/bench/rwlock_compare/20261009/README.md) | Native/TCLock/KD, 180 cacheline sessions at 1/16 workers, 12 KD controls, and the historical ABI1 hash-writer refusal resolved by ABI3 |
| [Protocol simplification](results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md) | Fresh 540-session spin/mutex baseline at all 15 thread counts under `nopvspin`; rejected translator/memory candidates and rechecks retained separately |
| [Historical hash diagnosis](results/380G10/bench/tclock_compare/HISTORY.md#hash-diagnosis) | Matched hash controls, NUMA effects and separate profiles in a fixed Git snapshot |
| [Evidence index](results/380G10/bench/tclock_compare/HISTORY.md) | All retained reports, full statistics, rejected candidates and fixed Git links to earlier reports |

These are recorded measurements, not reruns of subsequent cleanup commits.
Raw ignored/local/guest archives remain intact. A fresh checkout supplies reports,
not those large original run directories.
The original-host reports above used 40 vCPUs; the migration receipt below used
60. Keep them separate from the 64-vCPU and temporary 66-vCPU comparisons. Follow
[guest setup](../docs/PROJECT_GUIDE.md#guest-workflow) and explicitly choose a
collector outside the actual worker cohorts before new runs.

## VM migration validation

The 2026-10-10 migration to Ubuntu host `eric@10.176.26.71` was verified with
the initial 60 pinned guest CPUs, 24 GiB RAM, the captured `6.1.159-kdclobber2` kernel,
`nopvspin`, voluntary preemption and a fresh recovery snapshot. The host uses
an `ondemand` governor; these measurements remain separate from the historical
40-CPU, fixed-2.5-GHz reports. This benchmark receipt precedes the subsequent
64-vCPU change and does not establish performance for that topology.

One 16-worker KD spin functional check completed 1,600,000 operations and
455,538 JIT bodies. The RCUHT comparison completed all 72 sessions correctly
and drained: Native/TCLock/KD, 1%/20% writes, 1/16/32/56 workers, three rounds,
collector CPU 58. KD had 15 JIT-positive and nine `NO_JIT` sessions. Seven of
eight configurations met throughput parity. At 1% writes/56 workers, KD was
below TCLock by 1.66% on best peak and 4.52% on median whole-run throughput.

Synchronize current edits from `380G10` first. Then run on `10.176.26.71`:

```sh
cd /home/eric/vm/qemu-scripts
./vm_ssh.sh                # or ssh kdlock-vm
./bench.sh                 # new snapshot, smoke and comparison, host archive
```

Guest evidence is
`/root/kdlock-evidence/10.176.26.71/bench/migration-20261010T070707Z`.
The host archive is
`/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/bench/migration-20261010T070707Z/evidence.tar.gz`, with
SHA256 `bcf6dc00c9d298d8c90780f28b4e2a8d3f191af7ffeede3c731751cde2193801`.
`/home/eric/vm/migration/validation.json` records the acceptance and
`host-environment.json` records the physical CPU mappings and governor.
The [machine-specific receipt](results/10.176.26.71/bench/migration-20261010T070707Z/README.md)
retains the original topology and acceptance details. New `bench.sh` runs use
64 vCPUs, collector CPU 63 and machine-specific guest/host output directories.

## Measurement rules

Use NUMA-on, an UBSAN-off KD benchmark provider, 48000 operations of warmup per
worker, three rounds, two-second measurement and the highest valid 300 ms window
after settling. Record the actual host governor and frequency policy: historical
`380G10` reports used fixed 2.5 GHz, while the current destination uses `ondemand`.
Keep different policies separate. The complete matrix explicitly selects
`1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 64` for all runners.
Spin/mutex retain shorter defaults; rwlock retains the historical 15-point
default ending at 36. Use the [full driver](../tools/vm/README.md#complete-164-worker-comparison)
for all maintained payload sizes and the [offline exporter](full_compare/README.md)
after the workers drain.

Keep both the best peak and the distribution across rounds: minimum, median,
maximum and spread. Also keep whole-run throughput, observed JIT/delegation,
each worker's and NUMA node's share of work, source/binary/kernel identities and
shutdown checks. Amortized ns/op is the inverse of aggregate throughput; it does
not measure one caller's lock-acquisition latency. Preserve failed and NO_JIT runs,
and do not label them successful JIT executions.

The [spin/mutex](tclock_compare/README.md) and [rwlock](rwlock_compare/README.md)
runner guides own commands, result fields and acceptance rules;
[performance status](../docs/PERFORMANCE.md) records measured outcomes and deferred
designs. [Tests](../tests/README.md) owns correctness
check selection; [operations](../docs/AGENTS.md) owns guest/recovery/drain rules.
