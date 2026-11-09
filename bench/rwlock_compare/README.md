# Reader/writer and proc snapshot comparisons

These are stage 1 comparisons in the [project roadmap](../../docs/ROADMAP.md).
They use explicit benchmark objects, including the mutex nano profiles below.
Stage 2 actual-MM experiments use a separate kernel adapter; passing these
rwsem workloads does not establish mmap1 or page-fault performance.

Reader/writer spinlocks (rwlocks) permit concurrent readers or one exclusive
writer and wait by spinning. Reader/writer semaphores (rwsems) can sleep while
waiting. KD delegation lets a lock holder execute a waiting caller's work using
just-in-time compiled (JIT) code. The
[terminology guide](../../docs/TERMINOLOGY.md) explains the interface and result
labels used below.

This runner compares Linux native rwlocks, the
[TCLock rwlock port](../../tclock_backend/README.md) and
[KD rwlocks](../../docs/design/rwlock_implementation.md) on the same workload.
Use the separate [correctness test](../../tests/kernel/rwlock/fixture/README.md) for
instrumented checks of reader overlap and writer exclusion.
The same runner also supports sleeping rwsems and extracted proc spin
snapshots. These modes keep distinct lock, caller and execution identities.

The ten [active nano profiles](../nano/README.md) use one or sixteen padded
counters with 256 post-unlock rounds. They select public ABI2 mutex writes or
rwlock/rwsem mixes with 1% or 20% writes. All backends share the same body and
exact completed-write oracle. `--delegate off` supplies a separately labeled
callable-local mutex or ordinary-writer reader/writer control. These bulk-ioctl
profiles are separate from the real-syscall catalog and historical nano matrix.
For example, `mutex-locality` uses `--workloads cacheline --cachelines 16
--lock-kind mutex --write-percent 100 --post-work-rounds 256`; every counter must match
the exact completed-write total. The older two-word workload remains available
only for its historical controls and is not selected by the active nano launcher.

## Additional explicit modes

`--lock-kind rwsem --backends native tclock kdlock` compares Linux rwsem, the
[original TCLock rwsem](../../tclock_backend/README.md#original-rwsem-comparator), and the
[KD sleeping semaphore](../../docs/design/rwsem_implementation.md) on c01/c08 or
RCUHT. The waiting implementation in **`c21345b` is accepted as current**, including
the low-count regressions recorded in its comparison. Readers execute locally.
The benchmark explicitly prepares the KD object, then ordinary public
`kd_down_write/up_write` reserve a writer-only phase, block new readers,
wait for existing readers while the caller can sleep, and then enter the unchanged KD
mutex ABI2 protocol (its machine-level calling agreement). Its matching unlock finishes before the original
caller releases that reservation. Local writers, including downgrade callers,
use a separate exclusive admission state on the same semaphore; they cannot add
readers during a delegated writer phase. Separate queues for waiting to enter
and waiting for readers to finish, plus limited condition checks before sleeping,
are described in the rwsem design; the KD
mutex protocol is unchanged.

`--delegate off` compiles callable local KD writer acquisition and labels its variant
`-local`; it requires zero JIT counts. The prepared call shell is labelled `public-prepared-direct-abi2`; the local
control is `callable-local`. This replaces the historical OUTER/cookie benchmark
shell, so performance requires fresh measurements and separate source identities.
`--require-jit` applies only to eligible
multithreaded default-KD writers. TCLock uses its original writer-stack protocol
and AQS reader gate, with per-worker registration and post-client retirement
outside the measured loop. Its `upstream-stack` shell supports ordinary pairs,
not Linux-compatible killable/downgrade semantics. This
mode does not replace the real kernel mmap lock. Use the
[scheduler probe](../../tests/kernel/rwsem/README.md) for sleeping holders,
same-CPU progress, cancellation, epoch exclusion and downgrade coverage.

The [rwsem optimization report](../results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
records the current Native/KD standard-grid comparison, candidate screens,
separate baseline controls, diagnostic profiles and execution groups. The
[focused validation receipt](../results/10.176.26.71/tests/rwsem-optimization-20261018/README.md)
records sleeping/cancellation/downgrade checks and actual returned JIT evidence.
The [initial writer-delegation report](../results/10.176.26.71/bench/rwsem/20261018/README.md)
retains the earlier shared-queue implementation's full comparison, high-count
regressions and local fallback results. Those measurements remain historical
source-specific evidence.

`--lock-kind spin --workloads argbounds taskname` selects module-owned extracted
proc snapshots. All snapshots take an exclusive spinlock; KD may delegate the
snapshot read, while mutation runs locally through the same selected lock.
`argbounds` copies four words. `taskname` calls the exact kernel `strscpy_pad()`
with a 16-byte name and 64-byte padded output. Names/tuples are validated after
unlock; a mixed run also checks exact mutation totals. These are not full procfs
syscalls or an end-to-end `ps` workload.

Task-name preparation uses at most `--helper-waves 8` fully drained learning
rounds, saving each published image. A NORMAL image with no completed body does
not establish helper readiness. `--helper-workers 8` selects a separate
preparation cohort on CPUs from the configured list, even when timing uses
only one worker. Each preparation worker performs 240,000 iterations by
default. All preparation callers finish before the next translation and before
the measured cohort starts; preparation is excluded from throughput. The
record retains both CPU sets and their NUMA nodes.

Taskname uses the ordinary `KD_SPIN_DIRECT_LOCK` shell and the original
`strscpy_pad(result, name, 64)` call. The API contract introduced in version 10 invokes it without
helper-code checks, source-string scans or runtime destination checks. The
native caller supplies valid storage; analysis retains the source CALL write,
the statically known count of 64 and all 64 destination writes. See the
[writing-service contract](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/admission.md#original-strscpy_pad-writing-service).
Version 11 optionally uses a
[direct-call route](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/admission.md#direct-original-helper-calls)
inside one generated invocation, preserving the original arguments, 64-byte
effect and actual CALL return word. Its immutable ABI1 spin image contains
relative CALL operands filled before publication; the runner saves both the
upload and loaded generated bytes outside timing. The two-word wrapper ABI and
selected KD mutex protocol remain unchanged. Focused results are linked from
[validation](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/VALIDATION.md#taskname-and-xattr-helper-validation);
the [later direct-route comparison](../results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
records its completed grid under a separate frozen source identity.
Version 10 candidate 6 passed the read-only taskname correctness check on Linux
Native, TCLock and KD, with matching generated-body entries and completions on
KD. A separate 20% mutation check with `--helper-waves 0` passed correctness on
all three backends but recorded zero KD generated bodies. Disabling preparation
for that control does not establish delegated execution or supersede the
earlier failed strict delegation check. The
[version 10 development record](../results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md)
retains these outcomes. The separate
[`88bb5a4` standard-grid comparison](../results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
is complete for read-only taskname; it does not establish mutation-case delegation.

In the preceding `c79d84f` implementation, the ordinary shell's 16-worker
read-only check completed 3,200,000 operations and 3,194,222 delegated bodies.
The 20% mutation check produced correct results and drained on all three
backends, but KD completed only nine preparation bodies and none during
measurement. That strict measured-delegation check remains failed. The
[development record](../results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
keeps those source-specific results separate from new measurements.

The earlier exact-helper translation was refused for uncaptured R13 under spin
ABI1. The [reintegration checks](../results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
passed local rwsem and snapshot correctness; taskname exhausted its learning
waves without a returned delegated body. Argbounds completed delegated bodies
in three timed eight-worker runs, while its short 16-worker check was `NO_JIT`.
These are historical outcomes. `--delegate off` remains an explicitly local KD
control, separate from default-KD delegation attempts.

Examples below run only after the guest/snapshot checks described next. Choose
new external output directories:

```sh
# Explicit local sleeping rwsem control; correctness only, no performance score.
timeout 900s python3 bench/rwlock_compare/run.py \
  --lock-kind rwsem --backends native kdlock --workloads cacheline \
  --cachelines 1 8 --write-percent 1 20 --threads 1 8 \
  --delegate off --functional --repeats 1 --collector-cpu 63 \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwsem-functional-NEW

# Extracted four-word snapshot; read-only and controlled mutations.
timeout 900s python3 bench/rwlock_compare/run.py \
  --lock-kind spin --workloads argbounds --write-percent 0 20 \
  --threads 1 8 --functional --repeats 1 --collector-cpu 63 \
  --output /root/kdlock-evidence/10.176.26.71/tests/argbounds-functional-NEW
```

An explicitly requested single-round screen may use `--repeats 1` in timed
mode. Its rates are individual observations without a repeat-variability
estimate. The summary and parity report retain their three-round completeness
criterion; `--require-parity` requires three rounds. Functional mode remains
separate and produces no performance score.

For fresh performance use the standard grid through 60 workers and three
repetitions from [benchmark commands](../README.md#standard-worker-grid).
The explicit rwsem comparison below plans **756 sessions**: three workloads,
two write mixes, 21 worker counts, three repetitions and two backends. It retains
zero-entry and partial-entry KD groups separately from completed delegation;
single-worker results do not require a delegated body.

```sh
timeout 10800s python3 bench/rwlock_compare/run.py \
  --lock-kind rwsem --backends native kdlock \
  --workloads cacheline rcuht --cachelines 1 8 --write-percent 1 20 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 \
  --collector-cpu 63 --duration-ms 2000 --repeats 3 \
  --output /root/kdlock-evidence/10.176.26.71/bench/rwsem-comparison-NEW
```

The optimization report also records a separate spinning-rwlock reference.
It selects Native/TCLock/KD on c01, c08 and RCUHT at 1%/20% writes and
1/8/32/36/60 workers, with three repetitions: **270 completed sessions**. The
32/36-worker points straddle the current guest's NUMA boundary. This reference
uses non-sleeping bodies and does not substitute TCLock rwlock for a sleeping
rwsem or count as rwsem parity.

```sh
timeout 7200s python3 bench/rwlock_compare/run.py \
  --lock-kind rwlock --backends native tclock kdlock \
  --workloads cacheline rcuht --cachelines 1 8 --write-percent 1 20 \
  --threads 1 8 32 36 60 --collector-cpu 63 --duration-ms 2000 --repeats 3 \
  --output /root/kdlock-evidence/10.176.26.71/bench/rwlock-reference-NEW
```

The [2026-10-15 snapshot results](../results/10.176.26.71/bench/proc_snapshots/20261015/README.md)
belong to their frozen historical provider; restoring source is not a new score.

Build, test and run only in the recovery guest on `10.176.26.71`. Follow
[operations](../../docs/operations/VM.md) to verify the kernel, confirm a recovery snapshot
and check that all work has finished before unloading modules.

Edit source in the checkout on `380G10` and synchronize it to this guest first.
New guest evidence belongs under `/root/kdlock-evidence/10.176.26.71/bench/<run>`;
retain host archives and compact summaries in [the machine result layout](../results/README.md).

The [2026-10-15 c01 report](../results/10.176.26.71/bench/rwlock/20261015-c01/README.md)
contains 378 accepted sessions at 1%/20% writes, over 1–8 workers and 12–60 by four.
Its strict peak-and-whole parity criterion passes at 39 of 42 points; mixed JIT
statuses remain separate. The [original-host RCUHT report](../results/380G10/bench/rwlock_compare/20261010-rcuht/README.md)
retains its 270 runs and 21/30 parity result at the older topology/source version.
These records do not constitute a new run of the consolidated provider.

## Cases

| Workload | Protected operations | Benchmark sizes |
| --- | --- | --- |
| `cacheline` | Readers load and compare a consistent version; writers increment every selected line | 1 or 8 distinct 64-byte lines |
| `rcuht` | Readers look up a key; writers move a preallocated node between hash buckets | 1,024 buckets, 4,096 nodes, 8,192 possible keys |

The hash update and final structure checks reuse the previous
[KD/TCLock hash payload](../../workload_modules/spin_cacheline/hash_body.h),
adapted from TCLocks `rcuhashbash_write_lock`. One global reader/writer lock protects the table.
Despite the RCUHT name, readers take that lock: the body uses no lock-free RCU,
node allocation or RCU services.

The default workload is **RCUHT**, with two mixes: **1% writes / 99% reads** and
**20% writes / 80% reads**. Every worker performs the selected mix. Writes are
spaced evenly, with a deterministic starting offset for each worker. For example,
20% writes means each worker performs one write for every four reads; it does not
mean 20% of the workers are dedicated writers. The runner checks each worker's
exact read and write totals.

Use `--workloads cacheline` for the earlier single-cacheline workload. KD's ABI3
acquires exclusive writer access before the JIT body, allowing the current hash
writer to pass the existing translation checks. The older ABI1 refusal stays in
its original report.

The default thread set matches the earlier spin/mutex comparison:
`1 2 3 4 5 6 7 8 12 16 20 24 28 32 36`. Three rounds of each case with all three
backends produce **270 sessions**. `--threads` selects an explicit set, including the current 21-count grid
through 60 workers;
`--full-matrix` explicitly restores the default 15-point set.
`--cpus` is an ordered list: a run with N workers uses the first N CPUs. Keep
runs on one NUMA node separate from runs spanning nodes. The collector samples
progress on its own CPU, which must be online, available and outside every worker
set. Its built-in default is CPU 38, as used in the recorded 40-vCPU runs.

The commands below explicitly use collector CPU 63 for the current 64-vCPU
destination, with 32 cores per NUMA node. Its earlier 60-vCPU
[migration checks](../README.md#vm-migration-validation) remain separate; recheck
the live topology and snapshot before each new run. Default workers remain the
prefixes of CPUs 0..35. On the current destination, 32 workers fit in node 0 and
36 workers cross nodes; in the original 40-vCPU reports, 24/28 workers crossed
as well. Reproducing those reports requires their original topology and collector
38, not just the same thread counts. Do not pool samples across those placements.

## Commands

Inspect a plan without compiling or loading anything:

```sh
python3 bench/rwlock_compare/run.py --dry-run --collector-cpu 63
```

Current runs use the `7.0.0-38-kdlock1` build directory and schema-2 bundle
selected by the shared defaults. The [port record](../results/10.176.26.71/tests/linux70-port-20261027/README.md)
separates compilation, emitted-assembly checks and live correctness; historical
comparison results do not establish Linux 7 support. After verifying the actual
monitor snapshot and guest identity:

```sh
export PATH=/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin:$PATH
export LC_ALL=C
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT
python3 disassem/miasm_python314.py
python3 bench/spin_cacheline/kernel_identity.py

# Small correctness/drain check; one round, no performance scores.
timeout 900s python3 bench/rwlock_compare/run.py \
  --functional --repeats 1 --workloads cacheline --cachelines 1 \
  --write-percent 1 20 --threads 1 16 --collector-cpu 63 \
  --output /root/kdlock-evidence/10.176.26.71/bench/rwlock-functional

# Three-round timed comparison: the two default mixes and all 15 thread counts.
timeout 3600s python3 bench/rwlock_compare/run.py \
  --workloads rcuht --write-percent 1 20 --full-matrix --require-parity \
  --collector-cpu 63 \
  --output /root/kdlock-evidence/10.176.26.71/bench/rwlock-comparison

# Explicit JIT acceptance on contended writers; zero returned bodies fails.
timeout 600s python3 bench/rwlock_compare/run.py \
  --functional --repeats 1 --backends kdlock --workloads rcuht \
  --write-percent 20 --threads 16 36 --collector-cpu 63 --require-jit \
  --spin-entry-ratio-limit 0 --output /root/kdlock-evidence/10.176.26.71/bench/rwlock-jit
```

`--delegate off --backends kdlock` supplies a KD native writer control. Ratio
limit zero bypasses only the optional spin entry-ratio filter; adaptive CPU/lock
heat admission remains enabled. The default ratio limit is 2, NUMA is on,
prefetch mode is 2, and the KD/TCLock batch setting is 1,024. All benchmark modules
disable UBSAN; the captured kernel's configuration and mitigations stay intact.
The ratio filter and spin delegation switch do not govern rwsem's mutex ABI2
entry: it retains the current mutex heat admission, queue and NUMA batching.
Its compiled batch upper bound is also 1,024, with the mutex's existing earlier
fairness boundaries. Rwsem local controls use ordinary API calls in a separate
compiled shell, rather than relying on a spin-only module switch.
Replace `YOUR_CONFIRMED_SNAPSHOT` with the actual destination monitor tag and use
new output directories. The archived original-host snapshot is not portable.

## Measurement and acceptance

Each run loads fresh modules and prepares one KD writer entry. Translation
finishes and the daemon exits before all workers warm up with 48,000 operations
each. A read-only case needs no writer publication. Each pinned worker executes
its measured loop in one ioctl. Python does not run an operation-by-operation
loop, and measurement adds no shared reader counters.

After releasing the lock, every backend performs the same register-only arithmetic.
`--post-work-rounds` sets its amount explicitly; the default is **4**, matching the
earlier KD benchmarks. Record it when comparing results. Different amounts of
post-work are different workloads, including when comparing newer spin/mutex runs.

### Throughput measurements

Timed runs last two seconds by default. Each worker publishes progress every 256
operations, and the collector samples it every 10 ms. The report gives two rates:

| Measure | How it is calculated |
| --- | --- |
| Warmed peak | After 300 ms of settling, choose the highest observed valid 300 ms window in which every worker progresses. Use the actual kernel timestamps; do not interpolate samples. |
| Whole-run throughput | Count completed reads and writes over the whole run, including start, tail, collection and worker-join overhead. |

Raw samples preserve collection delays, the 256-operation reporting granularity
and every worker's progress. Peak read/write rates use the exact deterministic
mix at each sampled count. Whole-run rates and JIT shares do not describe the
selected peak window. The inverse of aggregate throughput is amortized time per
operation, not a measurement of how long one acquisition waited.

### Correctness and JIT checks

A valid run must have exact read/write counts. Cacheline readers must see consistent
values; writers must update exactly the active lines and leave inactive lines
unchanged. Hash checks cover membership, unique keys, backlinks, bucket placement
and move/conflict/miss totals. Worker CPU, arithmetic checksum, preemption/IRQ
balance and final reader/writer count and gate state must also match.

For rwlock and delegated rwsem, KD's eligible operations are writes; for spin snapshots they are
reads. Entry witnesses and complete matching-outer-unlock bodies are recorded
separately. `--require-jit` requires at least one complete body, and
`PARTIAL_JIT` must not count as completion. Read-only rwsem and explicit local controls
must return zero JIT. NORMAL only means code was published.
`--require-jit` fails a selected multithreaded KD writer case if it returns no JIT
bodies. Read-only and delegation-disabled controls must return zero. TCLock uses
native stack delegation, but its share is **UNMEASURED**. Neither throughput nor
contention supplies a missing execution count.

### Saved results and the performance target

The output directory keeps `plan.json`, `environment.json`, frozen source/binaries,
build logs, ELF context audit, translated images, raw phase samples and kernel
logs. Each run also has a `session.json`.

| File | Contents |
| --- | --- |
| `records.json` | Every planned run, including failed and unrun cases. |
| `summary.json` | Only valid timed runs that finished and drained. JIT and NO_JIT runs form separate groups. Each group reports its best peak, peak min/median/max/spread, whole-run min/median/max, and whether all three rounds are present. |
| `parity.json` | Whether KD meets the throughput target at each combination of write percentage and thread count. |

Functional runs have no performance summary entries. For performance parity, both
of these must hold against **each** of Native and TCLock for spin/rwlock, or
against Native for a two-arm rwsem comparison. When rwsem includes TCLock,
both controls are required:

1. KD's best warmed peak is at least as high.
2. KD's median whole-run rate is at least as high.

`--require-parity` completes all sessions, then returns failure if any point is
slower or lacks three comparable rounds. There is no tolerance and no merging
of JIT and NO_JIT groups to reach three rounds. This checks the observed rates;
a small difference does not by itself prove a statistically significant gap.

### Stop and cleanup

Create `<output>/STOP` to stop after the current case has finished and drained.
A timeout or kernel fault keeps processes and modules available for diagnosis;
it does not prove workers have stopped. Successful cleanup joins workers, stops
translators, retires KD sources, and checks TCLock's count, gate, stacks and queues.
It then clears the diagnostic target binding and unloads the workload before the
backend. Never force unload.

The runner checks live native qspinlock function pointers using the captured
kernel's DWARF layout. It reads only the two dispatch pointers from `/proc/kcore`.
This still verifies boot policy when old boot messages have left the kernel log.

## Focused checks

Run in the guest, alongside the two basic unit programs:

```sh
make -C tests/unit run PY_TESTS='rwlock/test_tclock_rwlock_context.py rwlock/test_rwlock.py'
python3 bench/rwlock_compare/test_bench.py
python3 bench/spin_cacheline/test_peak.py
```

Changes to ABI3 admission, completion or native retry also need the affected
drivers listed in the [rwlock correctness guide](../../tests/kernel/rwlock/README.md#unit-checks).

These check the real TCLock acquisition/return assembly, six callee-saved registers
and RSP, deterministic operation mixes, damaged-result rejection, JIT writer
denominators, incomplete-round reporting and narrow kernel-memory mapping.
The client regression also delays released barrier waiters to check that a
successful fixed-iteration phase cannot accidentally cancel late worker starts.
The runner also audits the compiled module's stack-switch prologue/helpers before
allowing a live TCLock load.
