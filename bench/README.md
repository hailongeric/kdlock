# Benchmarks

The [KD-only mutex round](results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md) contains 504 fresh accepted/drained sessions
at 1–8 workers by one and 12–60 by four, three repetitions, with accepted KD,
Native and TCLock controls. It measures the removal of Linux mutex backing while
retaining legacy delegation. At 60 workers KD-only reaches
4.838/5.130 Mops/s for c01/post64 and
pipebytes n16. Full scaling, low-count variation, separate regression follow-ups,
intermediate trials and independently replayed evidence remain in the report.

The [legacy compatibility experiment](results/10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md)
compares fresh legacy and backported legacy against Native and TCLock in
504 accepted/drained sessions. It covers c01/post64 and pipebytes n16 at 1–8
workers by one and 12–60 by four, three repetitions, with the unchanged legacy
lock protocol. At 60 workers the backport reaches 4.914/5.375 Mops/s; the report
also retains the 44-worker pipebytes regression, full variation, commands,
source identities and independently replayed archive.

The [complete legacy c01/pipebytes sweep](results/10.176.26.71/bench/comparison/mutex-legacy-grid-20261016T125529Z/README.md)
contains 378 accepted, drained sessions: 21 worker counts, three backends and
three repetitions per workload. At 60 workers, legacy KD median throughput is
4.931 Mops/s for c01/post64 and 5.379 Mops/s for pipebytes n16. The report retains
all counts, warmed peaks, variation and source identities. This uses the recovered
legacy mutex; the only measured source adjustment selects the common 64-round
synthetic post-work. Follow its exact commands and frozen inputs to reproduce it.

Choose the runner for the lock you want to compare. The runners test KD, TCLock
and Linux Native with matching workloads:

- [Spin/mutex comparison](tclock_compare/README.md): spinlocks and ordinary mutexes.
- [Rwlock comparison](rwlock_compare/README.md): read-write locks, with RCUHT at
  1% and 20% writes across the historical 15-point thread set by default.
- [Complete comparison](../tools/vm/README.md#complete-164-worker-comparison):
  all three lock families and maintained performance payloads at 22 worker counts.
- [Real kernel APIs](real_api/README.md): OFD conflict queries, file-table
  bitmaps, pipe mutexes, file-position mutexes and bounded UTS reader/writer
  metadata, with scoped Native/TCLock/KD critical sections and a stock Linux
  control; xattr admission limits are retained too.

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

The historical [mutex optimization comparison](results/10.176.26.71/bench/comparison/mutex-opt-20261011T045425Z/README.md)
contains 396 accepted, drained c01/hash sessions: all three backends, three rounds
at the same 22 worker counts. It records task caching, polling layout, retirement
loads and bounded NUMA selection, with rejected candidates and remaining gaps.
KD meets both peak and whole-run targets against both alternatives at 14 of 42
multithreaded points; see [performance status](../docs/PERFORMANCE.md#mutex-c01-optimization-2026-10-11)
for the per-payload outcome. c02/c08/c16 were excluded.

The [earlier all-lock 22-point comparison](results/10.176.26.71/bench/comparison/full-matrix-20261011T025525Z/overview.md)
covers **1–8 workers in steps of one, then 12–64 in steps of four**, under KDLock,
TCLock and Linux Native, after the NUMA/mutex fixes. It uses c01 and hash payloads
for spin, mutex and rwlock, with rwlock at 1%/20% writes: **1,584 drained sessions**,
1,582 accepted, three rounds per configuration. **c02, c04, c08 and c16 are
excluded.** Reports retain all samples, round variation, JIT/NO_JIT evidence,
CSV/JSON and scaling plots. The temporary 66-vCPU layout puts workers on distinct
host cores, with collector vCPU 65; at 64 workers, the collector and QEMU services
share physical core 63 with the last worker. The governor remains `ondemand`.
That historical mutex comparison uses this same placement and frequency policy;
the earlier report retains the latest spin/rwlock results and prior mutex baseline.
The [earlier full baseline](results/10.176.26.71/bench/comparison/full-matrix-20261010T094831Z/README.md)
retains 3,960 sessions and multi-cacheline payloads at its original source version.

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
| [Mutex and read/write API results](results/10.176.26.71/bench/real_api/20261011-sync/RESULTS.md) | 504 accepted sessions: pipe-buffer/capacity queries, shared-file seeks and private UTS reads/writes; syscall-to-lock mapping, three-round scaling, JIT evidence and rwsem integration limits |
| [Spinlock API results](results/10.176.26.71/bench/real_api/20261011/RESULTS.md) | Workload-to-lock mapping, TCLocks paper context and scaling results from 288 accepted OFD/setfd sessions; stock plus matched Native/TCLock/KD, with regressions and exploratory failures retained |
| [Historical mutex optimization](results/10.176.26.71/bench/comparison/mutex-opt-20261011T045425Z/README.md) | `10.176.26.71`: 396 accepted sessions, c01/hash, 22 worker counts; causes, selected changes, rejected candidates and remaining parity gaps |
| [Earlier all-lock c01/hash rerun](results/10.176.26.71/bench/comparison/full-matrix-20261011T025525Z/overview.md) | `10.176.26.71`: 1,584 sessions, 22 worker counts, all backends and lock families; c02/c04/c08/c16 excluded |
| [Earlier complete baseline](results/10.176.26.71/bench/comparison/full-matrix-20261010T094831Z/README.md) | `10.176.26.71`: all maintained spin/mutex/rwlock payloads, 1–8 and 12–64 workers, 3,960 sessions; temporary 66-vCPU VM, collector 65 shares a physical core at 64 workers |
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
for the current c01/hash payloads and the [offline exporter](full_compare/README.md)
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
