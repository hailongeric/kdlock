# Benchmarks

Use the maintained runner for the lock family. [The workload catalog](../docs/BENCHMARK_WORKLOADS.md)
defines protected operations and API parameters; [performance status](../docs/PERFORMANCE.md)
summarizes the accepted version. Build and run only in the verified VM on
`10.176.26.71`, following [VM operations](../docs/operations/VM.md).
The [terminology guide](../docs/TERMINOLOGY.md) defines lock names, just-in-time
(JIT) execution, status labels and measurement terms such as post4 and Mops/s.

| Comparison | Entry point | Payloads |
| --- | --- | --- |
| Spin | [tclock_compare/run.py](tclock_compare/run.py) | c01/c08 and RCUHT |
| Mutex | [tclock_compare/run_mutex.py](tclock_compare/run_mutex.py) | Same payloads, selected KD-only mutex |
| Rwlock | [rwlock_compare/run.py](rwlock_compare/run.py) | c01/c08 and RCUHT, default 1%/20% writes |
| Sleeping reader/writer semaphore (rwsem) | [rwlock_compare/run.py](rwlock_compare/run.py), `--lock-kind rwsem --backends native kdlock` | c01/c08 or RCUHT; local readers and writers that may delegate, with `--delegate off` local control; no TCLock implementation |
| Proc snapshots | [rwlock_compare/run.py](rwlock_compare/run.py), `--lock-kind spin` | `argbounds` and exact `taskname`; separate from full procfs/ps |
| Syscall/API | [real_api/run.py](real_api/run.py) | OFD, setfd, pipebytes, pipecap, seek, bounded UTS and xattr controls |

Runner contracts: [spin/mutex](tclock_compare/README.md), [rwlock](rwlock_compare/README.md),
[API](real_api/README.md). Shared client, peak analysis and snapshot code lives in
[spin_cacheline](spin_cacheline/README.md). Kernel payloads live in
[workload_modules](../workload_modules/README.md).

The retained KD mutex has a 32-byte object with native 8-byte alignment. Its
OSQ and delegation queues share four preallocated node slots per CPU while
keeping independent links and retirement. The NUMA locality boundary is 256
bodies, with larger deferred cohorts handed off and smaller prefixes followed
by FIFO service within the total 1024-body cap. See the
[mutex implementation guide](../docs/design/mutex_implementation.md).

## Standard worker grid

Use 21 counts: `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`.
Workers use the CPU prefix 0 through N−1; collector 63 is separate. Use three
repetitions per configuration. A plan preview for the mutex c01 case is:

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
Spin/mutex uses post64; rwlock/rwsem uses post4. Retain actual host governor, CPU/NUMA
placement, source and ELF hashes, kernel identity and instrumentation policy.

Validate business results, every worker's progress, required execution evidence
and complete drain. Synthetic mutex counters witness generated-body entry;
they do not prove returned bodies. The real API runner separately records
matching returned completions. Keep entry-only, returned-body and NO_JIT
controls/refusals distinct.
Preserve failures, partial attempts and all valid rounds. Never pool different
source versions, workloads, topologies, call shells or instrumentation settings.
Functional mode uses one explicit round and produces no performance claim.

## Results

The [historical KD-only report](results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
contains 504 sessions for c01/post64 and pipebytes n16 with accepted KD baseline,
Native and TCLock controls on the older 256-byte object. Use the [results index](results/README.md) for current
versions and lock families; historical results retain their own frozen inputs.

The [accepted rwsem report](results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
records the `c21345b` Native/KD comparison for c01/c08/RCUHT at 1%/20% writes on
the standard worker grid. It retains candidate screens, separate baseline
controls, JIT execution groups and diagnostic profiles. Acceptance includes the
substantial two-worker regressions as well as the 60-worker gains. A distinct spinning-rwlock
reference selects Native/TCLock/KD, the same three payloads and mixes, and
1/8/32/36/60 workers: 270 completed sessions with three repetitions. That reference
uses non-sleeping lock semantics and is not scored as rwsem parity. The
[initial rwsem comparison](results/10.176.26.71/bench/rwsem/20261018/README.md)
remains evidence for the earlier shared-queue implementation.

Write guest results outside the checkout to
`/root/kdlock-evidence/10.176.26.71/bench/<new-run>`. Track compact reports under
`bench/results/<machine>/bench/` and retain raw archives under ignored
`bench/results/<machine>/raw/bench/`. The historical full-matrix exporter is
isolated in [archive](archive/README.md); it is not a current benchmark driver.

## Archiving a completed round

After runners and evidence replay have exited, save a final health receipt and
kernel logs inside the completed evidence directory. The health JSON must state
`idle: true` and the current `/proc/sys/kernel/random/boot_id` as `boot_id`.
Then run [archive_run.py](archive_run.py) in the idle recovery guest:

```sh
python3 bench/archive_run.py \
  --base /mnt/kdlock-builds/taskname-xattr-ROUND \
  --output /mnt/kdlock-builds/taskname-xattr-ROUND-archives \
  --health /mnt/kdlock-builds/taskname-xattr-ROUND/health.json \
  --group taskname=taskname --group xattr=xattr
```

Both evidence and archive paths are explicit; the archive directory must be a
new sibling. Each group selects one top-level path. Every unassigned path,
including command logs, metadata and replay results, goes into `metadata.tar.gz`.
Files and symlinks are preserved; link targets are not followed. The helper
checks live idle state, rejects open writers to the evidence tree, records its
inventory and compressed hashes, and checks that inputs remained unchanged.
Redirect the helper's own output outside the input evidence directory.

Accept capture only when `archives.json` records `completed: true`. A timeout
or error leaves partial archives and a failure receipt; preserve them and use a
new output directory for a retry. Nothing in the source tree or original evidence
is deleted. Archive preservation is separate from result validation.

## VM migration validation

The [initial migration receipt](results/10.176.26.71/bench/migration-20261010T070707Z/README.md)
records the original 60-vCPU destination setup. The
[64-vCPU setup receipt](results/10.176.26.71/tests/20261010-topology64/README.md)
and [current operations](../docs/operations/VM.md) describe the subsequent layout.
Keep these separate from original-host 40-vCPU and historical 66-vCPU samples.
