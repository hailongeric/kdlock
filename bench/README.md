# Benchmarks

Choose a maintained runner for the workload you want to compare. Each uses matching
KD, TCLock and Linux Native payloads; the real API runner also provides Stock Linux.
KD mutexes always support blocking after bounded polling.

| Runner | Scope |
| --- | --- |
| [Spin/mutex comparison](tclock_compare/README.md) | Separate spinlock and ordinary blocking-mutex cacheline/RCUHT workloads |
| [Rwlock comparison](rwlock_compare/README.md) | Cacheline and RCUHT reader/writer mixes; 1%/20% writes by default |
| [Complete comparison](../tools/vm/README.md#complete-164-worker-comparison) | All three lock families, c01/hash and 22 worker counts; larger payloads are opt-in |
| [Real kernel APIs](real_api/README.md) | OFD queries, descriptor flags, pipe/file-position mutexes and bounded UTS reader/writer metadata |
| [Shared components](spin_cacheline/README.md) | Clients, warmup, peak selection, provider preparation and offline reports |

The [workload guide](../docs/BENCHMARK_WORKLOADS.md) explains cacheline and hash
payloads, reader/writer mixes and real API parameters such as `n16` and `v64`.
Kernel payloads live under [workload_modules](../workload_modules/README.md).

## Environment and output

Edit source on `380G10`, synchronize with `python3 tools/vm/sync_to_vm.py`, and run
builds, tests and benchmarks in the recovery VM on `10.176.26.71`. Follow
[guest setup](../docs/PROJECT_GUIDE.md#guest-workflow) and
[operations](../docs/AGENTS.md) for kernel identity, dependencies, snapshot confirmation
and drain. The regular boot has 64 vCPUs across two NUMA nodes. Use collector CPU
63 and exclude it from worker cohorts. A full 64-worker run needs the separately
verified temporary [66-vCPU layout](../tools/vm/README.md#complete-164-worker-comparison).

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

The complete grid is
`1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 64`.
Individual runners retain shorter defaults; use explicit placement and worker
counts for a comparison. Follow the [complete driver](../tools/vm/README.md#complete-164-worker-comparison)
and its [offline exporter](full_compare/README.md) for the full c01/hash matrix.

Retain best peak and whole-run throughput, minimum/median/maximum/spread across
rounds, returned JIT/delegation counts, each worker's and NUMA node's progress,
source/binary/kernel identities and final drain. Amortized ns/op is the inverse
of aggregate throughput, not one caller's acquisition latency. Failed and NO_JIT
sessions remain visible and are not successful JIT measurements.

## Results

[Performance status](../docs/PERFORMANCE.md) summarizes the recent c01 mutex
studies, retained changes and rejected experiments. The
[validation index](../docs/VALIDATION.md) separates correctness checks from
performance acceptance. The [machine indexes](results/README.md) retain complete
reports, earlier all-lock comparisons and rejected trials. Each result applies
to its captured source, workload, boot policy and topology.

## VM migration validation

The [2026-10-10 migration receipt](results/10.176.26.71/bench/migration-20261010T070707Z/README.md)
records the initial 60-vCPU setup and its functional/performance checks. It is
historical evidence for that topology. Current connection, synchronization and
64/66-vCPU instructions live in the [project guide](../docs/PROJECT_GUIDE.md)
and [VM tools guide](../tools/vm/README.md).

The [spin/mutex](tclock_compare/README.md), [rwlock](rwlock_compare/README.md) and
[real API](real_api/README.md) guides own runner commands and acceptance rules.
[Tests](../tests/README.md) owns correctness-check selection.
