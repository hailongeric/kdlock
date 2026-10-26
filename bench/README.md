# Benchmarks

The [project roadmap](../docs/ROADMAP.md) places lock micro/nano comparisons in
stage 1, actual mmap/page-fault comparisons in stage 2, and unchanged applications
on integrated kernels in stage 3. Use this guide for implemented runner selection;
the roadmap's exact mmap1 target remains a new runner/validation task.

Use the maintained runner for the lock family. [The workload catalog](../docs/BENCHMARK_WORKLOADS.md)
defines protected operations and API parameters; [performance status](../docs/PERFORMANCE.md)
summarizes the accepted version. Build and run only in the verified VM on
`10.176.26.71`, following [VM operations](../docs/operations/VM.md).
The [terminology guide](../docs/TERMINOLOGY.md) defines lock names, just-in-time
(JIT) execution, status labels and measurement terms such as post4 and Mops/s.

For a short functional run, use [basic/run.py](basic/run.py) and the
[quick-start commands](../docs/PROJECT_GUIDE.md#basic-working-version). It runs
one existing resident-list case per KD family, with public mutex calls,
concurrent local readers, returned-body checks and complete drain. It produces
no timing acceptance or throughput score. Comparison timing rules stay unchanged.

| Comparison | Entry point | Payloads |
| --- | --- | --- |
| Spin | [tclock_compare/run.py](tclock_compare/run.py) | c01/c08, resident list with matched prefetch variants, and RCUHT |
| Mutex | [tclock_compare/run_mutex.py](tclock_compare/run_mutex.py) | Same payloads, selected KD-only mutex |
| Rwlock | [rwlock_compare/run.py](rwlock_compare/run.py) | c01/c08, resident list and RCUHT, default 1%/20% writes |
| Favorable nano | [nano/best_case.py](nano/best_case.py), [guide](nano/README.md) | Ten padded-counter profiles: c01/c16 mutex, plus c01/c16 rwsem and rwlock at 1%/20% writes; all post256, one round by default |
| Sleeping reader/writer semaphore (rwsem) | [rwlock_compare/run.py](rwlock_compare/run.py), `--lock-kind rwsem --backends native tclock kdlock` | Same synthetic payloads; local readers and writers that may delegate, with `--delegate off` KD local control; original TCLock rwsem with fixed-affinity registered workers |
| Proc snapshots | [rwlock_compare/run.py](rwlock_compare/run.py), `--lock-kind spin` | `argbounds` and exact `taskname`; separate from full procfs/ps |
| Syscall/API | [real_api/run.py](real_api/run.py) | OFD, setfd, pipebytes, pipecap, seek, bounded UTS and xattr controls |
| Private mapping/fault controls | [mmap_fault](mmap_fault/README.md) | Native independent-mm mmap/munmap; Native/KD/TCLock private-backing fault cycles, with actual mmap locks Native |
| Actual mmap-lock comparison | [mmap_lock](mmap_lock/README.md), reusing [mmap_writer](mmap_writer/README.md) | Native/KD shared-mm untouched 4 KiB device mappings; separate from the planned 128 MiB anonymous mmap1 workload |

Runner contracts: [spin/mutex](tclock_compare/README.md), [rwlock](rwlock_compare/README.md),
[API](real_api/README.md). Shared client, peak analysis and snapshot code lives in
[spin_cacheline](spin_cacheline/README.md). Kernel payloads live in
[workload_modules](../workload_modules/README.md).

The retained KD mutex has a 32-byte object with native 8-byte alignment. Its
OSQ and delegation queues share four preallocated node slots per CPU while
keeping independent links and retirement. The NUMA locality boundary is 768
bodies, with larger deferred cohorts handed off and smaller prefixes followed
by FIFO service within the total 1024-body cap. See the
[mutex implementation guide](../docs/design/mutex_implementation.md).

## Full selected catalog

The active catalog contains **61 lock/API configurations**: the 51 micro/API
cases selected for the October 26 screen and ten padded-counter nano profiles.
The original micro c01/c08 cases retain their post64 spin/mutex and post4
reader/writer settings; the new nano c01/c16/post256 cases are additional
workloads. Retired two-word nano profiles remain in historical source/results,
not the current selection. Three separately implemented MM suites add Native
independent-mm mappings, private-backing fault controls and Native/KD actual
shared-mm mappings, with distinct kernel/backend requirements.

The current one-round command generator is
[`catalog_single/current_plan.py`](catalog_single/current_plan.py). Its static
preview creates no workloads or benchmark outputs:

```sh
python3 bench/catalog_single/current_plan.py \
  --guest-root /root/kdlock-evidence/10.176.26.71/bench/catalog-fixedfreq-NEW
```

That plan covers 3,843 lock/API points on the standard 21-count grid. The three
MM suites add 126 points through their separately prepared runners, for 3,969
planned observations. The requested fixed-2.0-GHz campaign uses one round per
point and publishes each workload table after collection. It remains a planned
campaign until its reports establish completion; failed preparation is retained
as failure rather than a measured pass. The original
[`catalog_single/plan.py`](catalog_single/plan.py) and October 26 reports preserve
the historical 51-case selection. A request to run this catalog does not imply
running the full unit-test suite. Follow the VM guide for frequency receipts,
snapshot verification and any separately authorized MM kernel transitions.

## Standard worker grid

Use 21 counts: `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`.
Workers use the CPU prefix 0 through N−1; collector 63 is separate. The standard
confirmatory plan uses three repetitions per configuration. Explicit single-round
screens and the nano runner's one-round default retain their own manifests and
cannot establish repeat variability. A plan preview for mutex c01 is:

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
For [resident-list variants](../docs/BENCHMARK_WORKLOADS.md#resident-linked-list-traversal),
the micro catalog selects plain `list` at 16 nodes. A 64-node case remains
planned; 128 nodes and both prefetch variants are historical selections.
Currently use `--workload list
--list-nodes 16`, omitting `--cachelines`; 64-node support still requires
implementation and validation. Add `--mutex-api public` for literal public
mutex calls. The rwlock/rwsem runner uses plural `--workloads`.
The frozen `bench/nano/run.py` campaign recipe and existing reports retain the
original matrix. Use `bench/nano/best_case.py` for the ten active padded-counter
nano profiles; it does not run resident-list cases.

The public mutex acceptance driver, [mutex_api_compare/run.py](mutex_api_compare/run.py),
has separate `prepare`, `smoke` and `measure` actions with one `--output` directory.
Live actions require `--host-state` pointing to the recorded host
placement/snapshot JSON captured within the preceding five minutes.
After the same snapshot and host-policy verification, `prepare` freezes fresh
public/Native/TCLock builds and copies hash-verified pre-unification OUTER inputs
from the retained seven-workload round. `smoke` runs 16 fresh binding checks;
`measure` rotates four arms at all 21 worker counts with three repetitions
(1,764 sessions). Each session regenerates JIT from its matching translator
and fully drains before the next arm. STOP requests and the time budget stop at
a drained boundary. Unsafe failures stop immediately without forced unload.
The selected input trees must remain unchanged through the collection.
Focused reruns of the original seven public-mutex regressions use
`mutex_api_compare/run.py replay --prepared <original-r2> --output <new-directory>
--host-state <fresh-host-receipt>`. The fixed selection also includes the three
incomparable points: ten points, three repetitions and four original arms,
120 serialized sessions in the original arm order. Replay uses the pinned
original binaries, translation sources and retained collector, with separate
scheduler provenance. It refuses changed manifests, unexpected imports, output
overlap, or a changed VM/host configuration. Resident NUMA page counts are
recorded separately from the unchanged binding policy. Preserve NO_JIT and
failed sessions; do not extend repeats to obtain a favorable execution class.
These reruns do not validate performance of later source revisions.

Use [mutex_api_compare/report.py](mutex_api_compare/report.py) on the resulting
`matrix` directory for separate source/caller/execution-class summaries.
It reports the provisional coordinator-proposed 5% median-throughput criterion,
observed variation and missing repetitions. Individual operation latency is
not sampled: p95 remains unmeasured and overall performance acceptance remains
open. Earlier OUTER gains or losses are retained under their original identity.

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
and complete drain. Retained c01/c08/RCUHT mutex receipts witness generated-body
entry; they do not prove returned bodies. New list profiles and the real API
runner separately record matching returned completions. Keep entry-only, returned-body and NO_JIT
controls/refusals distinct.
Preserve failures, partial attempts and all valid rounds. Never pool different
source versions, workloads, topologies, call shells or instrumentation settings.
Functional mode uses one explicit round and produces no performance claim.

## Results

The [current mutex comparison](results/10.176.26.71/bench/mutex32-native-tclock-20261020/README.md)
covers c01, c08, exclusive-update RCUHT, `SEEK_SET`, `SEEK_END`, pipe byte
count and pipe capacity with fresh Linux Native, TCLock and KD controls.
It contains 567 valid, drained sessions: three repetitions at
`1 2 4 8 16 32 36 48 60` workers, with no matched kernel faults. This is a
nine-point comparison, not the full standard grid. The `bd9d4ce` collection
keeps the `752fec1` mutex runtime unchanged. KD's whole-run median exceeds both
controls on all seven workloads at 60 workers; at eight workers its three
synthetic medians remain below Native. The report retains observed ranges,
local `NO_JIT` results and separate entry/returned-body evidence; c08 at two
workers splits into one local and two entry-witnessed samples.

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
