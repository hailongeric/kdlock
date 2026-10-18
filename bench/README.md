# Benchmarks

Use the maintained runner for the lock family. [The workload catalog](../docs/BENCHMARK_WORKLOADS.md)
defines protected operations and API parameters; [performance status](../docs/PERFORMANCE.md)
summarizes the accepted version. Build and run only in the verified VM on
`10.176.26.71`, following [VM operations](../docs/operations/VM.md).

| Comparison | Entry point | Payloads |
| --- | --- | --- |
| Spin | [tclock_compare/run.py](tclock_compare/run.py) | c01/c08 and RCUHT |
| Mutex | [tclock_compare/run_mutex.py](tclock_compare/run_mutex.py) | Same payloads, selected KD-only mutex |
| Rwlock | [rwlock_compare/run.py](rwlock_compare/run.py) | Cachelines and RCUHT, default 1%/20% writes |
| Sleeping rwsem | [rwlock_compare/run.py](rwlock_compare/run.py), `--lock-kind rwsem --backends native kdlock` | c01/c08 or RCUHT; ordinary local bodies, no JIT/TCLock |
| Proc snapshots | [rwlock_compare/run.py](rwlock_compare/run.py), `--lock-kind spin` | `argbounds` and exact `taskname`; separate from full procfs/ps |
| Syscall/API | [real_api/run.py](real_api/run.py) | OFD, setfd, pipebytes, pipecap, seek, bounded UTS and xattr controls |

Runner contracts: [spin/mutex](tclock_compare/README.md), [rwlock](rwlock_compare/README.md),
[API](real_api/README.md). Shared client, peak analysis and snapshot code lives in
[spin_cacheline](spin_cacheline/README.md). Kernel payloads live in
[workload_modules](../workload_modules/README.md).

## Standard worker grid

Use 21 counts: `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`.
Workers use the CPU prefix 0 through N−1; collector 63 is separate. Use three
repetitions per configuration. A plan preview for the accepted mutex c01 case is:

```sh
python3 bench/tclock_compare/run_mutex.py --dry-run \
  --backends native tclock kdlock --cachelines 1 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 \
  --cpus 0-59 --collector-cpu 63 --repeats 3 \
  --duration-ms 2000 --peak-window-ms 300 --peak-settle-ms 300 --sample-ms 10 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/10.176.26.71/bench/mutex-c01-NEW
```

Before live execution, confirm a recoverable snapshot and set the documented
recovery variables, then omit `--dry-run` and use an outer timeout. For other
synthetic sizes select `--cachelines 1 8`; for RCUHT use `--workload rcuht`
and omit `--cachelines`. These choices define different workloads.

The optional synthetic spin/mutex 64-worker point requires `--cpus 0-63
--collector-cpu 63 --share-collector`, timed mode and a 64-vCPU guest. Smaller
cohorts keep a separate collector; only the 64-worker point records
`collector_shared=true`. API and rwlock runners do not support shared collection.
Do not use the retired temporary 66-vCPU launcher for new measurements.

## Measurement rules

Use NUMA-on, the UBSAN-off private KD benchmark provider, 48,000 warmup operations
per worker, two-second measurements and the highest valid 300 ms window after
300 ms settling. Record min/median/max/spread and median whole-run throughput.
Spin/mutex uses post64; rwlock uses post4. Retain actual host governor, CPU/NUMA
placement, source and ELF hashes, kernel identity and instrumentation policy.

Validate business results, every worker's progress, required returned JIT bodies
and complete drain. Keep NO_JIT controls/refusals distinct from JIT acceptance.
Preserve failures, partial attempts and all valid rounds. Never pool different
source versions, workloads, topologies, call shells or instrumentation settings.
Functional mode uses one explicit round and produces no performance claim.

## Results

The [current KD-only report](results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
contains 504 sessions for c01/post64 and pipebytes n16 with accepted KD baseline,
Native and TCLock controls. Use the [results index](results/README.md) for other
versions and lock families; historical results retain their own frozen inputs.

Write guest results outside the checkout to
`/root/kdlock-evidence/10.176.26.71/bench/<new-run>`. Track compact reports under
`bench/results/<machine>/bench/` and retain raw archives under ignored
`bench/results/<machine>/raw/bench/`. The historical full-matrix exporter is
isolated in [archive](archive/README.md); it is not a current benchmark driver.

## VM migration validation

The [initial migration receipt](results/10.176.26.71/bench/migration-20261010T070707Z/README.md)
records the original 60-vCPU destination setup. The
[64-vCPU setup receipt](results/10.176.26.71/tests/20261010-topology64/README.md)
and [current operations](../docs/operations/VM.md) describe the subsequent layout.
Keep these separate from original-host 40-vCPU and historical 66-vCPU samples.
