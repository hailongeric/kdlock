# Benchmarks

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

The [legacy mutex recovery](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-recovery-20261016T113518Z/README.md) restores the exact source
associated with the historical 5.330 Mops/s pipebytes result. Commit `6ecdd0a`
in `/tmp/kdlock-mutex-legacy-5m330` reaches 5.367 Mops/s at 60 workers in the
fresh three-round comparison. The adaptive experiment was rejected; its
evidence remains preserved separately.

Choose a maintained runner for the workload you want to compare. Each uses matching
KD, TCLock and Linux Native payloads; the real API runner also provides Stock Linux.
KD mutexes support blocking. Their delegation-result polling budget is separate
from the owned protocol's Linux-style optimistic SELF acquisition.

| Runner | Scope |
| --- | --- |
| [Spin/mutex comparison](tclock_compare/README.md) | Separate spinlock and ordinary blocking-mutex c01/c02/c04/c08/c16 and RCUHT workloads |
| [Owned mutex c01 full grid](tclock_compare/README.md#owned-c01-full-grid) | ABI4/reuse-32, one shared counter, Native/TCLock/KD, 22 worker counts and 198 samples |
| [Rwlock comparison](rwlock_compare/README.md) | Cacheline and RCUHT reader/writer mixes; 1%/20% writes by default |
| [Complete comparison](../tools/vm/README.md#complete-164-worker-comparison) | All three lock families, c01/hash and 22 worker counts; larger payloads are opt-in |
| [Real kernel APIs](real_api/README.md) | OFD queries, descriptor flags, private owned pipe/file-position mutex adapters and bounded UTS reader/writer metadata |
| [Shared components](spin_cacheline/README.md) | Clients, warmup, peak selection, provider preparation and offline reports |

The [workload guide](../docs/BENCHMARK_WORKLOADS.md) explains cacheline and hash
payloads, reader/writer mixes and real API parameters such as `n16` and `v64`.
Kernel payloads live under [workload_modules](../workload_modules/README.md).

## Environment and output

Edit source on `380G10`, synchronize with `python3 tools/vm/sync_to_vm.py`, and run
builds, tests and benchmarks in the recovery VM on `10.176.26.71`. Follow
[guest setup](../docs/PROJECT_GUIDE.md#guest-workflow) and
[operations](../docs/AGENTS.md) for kernel identity, dependencies, snapshot confirmation
and drain. All new runs use exactly 64 CPUs: node 0 has CPUs 0–31 and node 1
has CPUs 32–63, pinned to the same-numbered host cores. Do not add extra vCPUs
or an unused spare CPU. For up to 63 workers, use collector CPU 63 outside
worker cohorts. At 64 workers, the collector must share CPU 63 with a worker
and QEMU services. Spin/mutex timed runs support this with
`--cpus 0-63 --collector-cpu 63 --share-collector`; rwlock, real-API and the full
matrix driver still require a separate collector. See the
[64-CPU placement and runner support](../tools/vm/README.md#complete-164-worker-comparison).

Live output belongs in a new directory outside the guest checkout:
`/root/kdlock-evidence/10.176.26.71/bench/<run>`. Archive raw evidence under
`bench/results/10.176.26.71/raw/bench/<run>/`; publish compact reports under
`bench/results/10.176.26.71/bench/<runner>/<run>/`. The
[results index](results/README.md) owns the layout, history and machine-specific receipts.

## Measurement rules

Use NUMA-on, an UBSAN-off KD benchmark provider, 48,000 warmup operations per
worker, three rounds, a two-second measurement and the highest valid 300 ms
window after settling. Real API warmup additionally lasts at least one second
per worker. Record the actual host governor, frequency policy and CPU/NUMA placement.
Functional runs explicitly use one round and are separate from performance
measurements.

The complete driver's historical grid is
`1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 64`.
Individual runners retain shorter defaults; use explicit placement and worker
counts for a comparison. Follow the [complete driver](../tools/vm/README.md#complete-164-worker-comparison)
and its [offline exporter](full_compare/README.md) for the full c01/hash matrix.
That driver now includes owned ABI2 KD mutexes for every selected synthetic
mutex payload, alongside Native and TCLock. Its separate-collector requirement
still prevents the 64-worker point on the required 64-vCPU topology. The latest
all-lock and expanded-mutex rounds use 1–8 workers in steps of one and 12–60 in
steps of four; their frozen drivers and exact commands are retained with their
reports. The ABI4/reuse-32 c01 profile has its own explicit command above.

Retain best peak and whole-run throughput, minimum/median/maximum/spread across
rounds, returned JIT/delegation counts, each worker's and NUMA node's progress,
source/binary/kernel identities and final drain. Amortized ns/op is the inverse
of aggregate throughput, not one caller's acquisition latency. Failed and NO_JIT
sessions remain visible and are not successful JIT measurements.

## Results

The [adaptive mutex comparison](results/10.176.26.71/bench/comparison/mutex-adaptive-20261016T075356Z/README.md)
contains 504 accepted/drained c01 and pipebytes n16 sessions across the same
21 worker counts, with adaptive KD, exact pre-change KD, Native and TCLock.
The new policy remains opt-in; the report retains its regressions, full curves,
JIT share and the new 128-byte layout's compatibility/performance limits.

[The expanded mutex comparison](results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md)
contains 2,079 fresh accepted and drained sessions across six synthetic and five
pipe/file API variants, with three repetitions per backend and worker count.
It completes the previously missing KD mutex coverage. The
[earlier all-lock round](results/10.176.26.71/bench/comparison/workloads-20261015T180603Z/README.md)
retains the separate spin/rwlock and other-API results; samples are not pooled.

[Performance status](../docs/PERFORMANCE.md) summarizes these comparisons, the
c01 mutex acceptance studies, retained changes and rejected experiments. The
[validation index](../docs/VALIDATION.md) separates correctness checks from
performance acceptance. The [machine indexes](results/README.md) retain complete
reports, earlier all-lock comparisons and rejected trials. Each result applies
to its captured source, workload, boot policy and topology.

## VM migration validation

The [2026-10-10 migration receipt](results/10.176.26.71/bench/migration-20261010T070707Z/README.md)
records the initial 60-vCPU setup and its functional/performance checks. It is
historical evidence for that topology. Current connection, synchronization and
64-vCPU instructions live in the [project guide](../docs/PROJECT_GUIDE.md)
and [VM tools guide](../tools/vm/README.md).

The [spin/mutex](tclock_compare/README.md), [rwlock](rwlock_compare/README.md) and
[real API](real_api/README.md) guides own runner commands and acceptance rules.
[Tests](../tests/README.md) owns correctness-check selection.
