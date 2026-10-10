# Read-write lock comparison

Compare Linux native rwlocks, the [TCLock rwlock port](../../tclock_backend/README.md)
and [KD rwlocks](../../docs/design/rwlock_implementation.md). This is a performance
workload separate from the instrumented [rwlock correctness test](../../workload_modules/rwlock/README.md).
All compilation, tests and live runs belong in the recovery guest; follow
[operations](../../docs/AGENTS.md) for kernel identity, snapshot and drain requirements.

[RCUHT comparison, 2026-10-10](results/20261010-rcuht/README.md) records the
ABI3 hash-writer JIT results, optimization trials and strict parity outcome.
All 270 sessions passed correctness and drain, but KD met both throughput targets
at only 21 of 30 configurations. The remaining nine points fail the requested
Native/TCLock parity requirement; no universal performance win is claimed.

[Full thread sweep, 2026-10-09](results/20261009-scaling/README.md): 270 sessions
for 1% and 20% writes on the historical ABI1 single-cacheline workload, all 15
thread counts, throughput curves and NUMA progress.
The [initial mix comparison](results/20261009/README.md) retains the earlier
180 cacheline sessions, 12 delegation-disabled controls and the ABI1 hash refusal.

## Cases

| Workload | Protected operations | Sizes |
| --- | --- | --- |
| `cacheline` | Readers load and compare a consistent version; writers increment every selected line | 1, 2, 4, 8, 16 distinct 64-byte lines |
| `rcuht` | Readers look up a key; writers move a preallocated node between hash buckets | 1,024 buckets, 4,096 nodes, 8,192 possible keys |

Hash moves and the complete structural oracle reuse the previous
[KD/TCLock hash payload](../../workload_modules/spin_cacheline/hash_payload.h),
adapted from TCLocks `rcuhashbash_write_lock`. This is a global rwlock benchmark,
not lock-free RCU. It allocates no nodes and calls no RCU services in the body.

The default workload is **RCUHT**, with exactly two mixes: **1% writes**
(99% reads) and **20% writes** (80% reads). Select `--workloads cacheline` for the
previous single-cacheline workload. ABI3 writer admission runs before the JIT
body; the earlier ABI1 hash refusal remains in the historical evidence.
Every worker uses the same percentage
with evenly spaced writes and a deterministic phase offset;
this is a mixed-operation workload, not a fixed writer-thread population.
The runner verifies the exact mix from each worker's completed count.

The default thread set matches the earlier spin/mutex comparison:
`1 2 3 4 5 6 7 8 12 16 20 24 28 32 36`. Three rounds of each case with all three
backends produce **270 sessions**. `--threads` selects a shorter set;
`--full-matrix` explicitly restores the default 15-point set.
`--cpus` takes an ordered list whose prefixes form cohorts.
Use separate directories for compact and cross-NUMA placements. The built-in
collector default remains CPU 38, matching the recorded 40-vCPU runs. Every
collector must be online, available and outside all worker cohorts.

The commands below explicitly use collector CPU 58 for the documented 60-vCPU
destination, after its pending [migration verification](../../docs/PROJECT_GUIDE.md#guest-workflow).
Default workers remain the prefixes of CPUs 0..35. On that destination, 32/36
workers cross NUMA nodes; in the original 40-vCPU reports, 24/28 workers crossed
as well. Reproducing those reports requires their original topology and collector
38, not just the same thread counts. Do not pool samples across those placements.

## Commands

Inspect a plan without compiling or loading anything:

```sh
python3 bench/rwlock_compare/run.py --dry-run --collector-cpu 58
```

After verifying the actual monitor snapshot and guest identity:

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT

# Small correctness/drain check; one round, no performance scores.
timeout 900s python3 bench/rwlock_compare/run.py \
  --functional --repeats 1 --workloads cacheline --cachelines 1 \
  --write-percent 1 20 --threads 1 16 --collector-cpu 58 \
  --output /root/kdlock-evidence/rwlock-functional

# Three-round timed comparison: the two default mixes and all 15 thread counts.
timeout 3600s python3 bench/rwlock_compare/run.py \
  --workloads rcuht --write-percent 1 20 --full-matrix --require-parity \
  --collector-cpu 58 \
  --output /root/kdlock-evidence/rwlock-comparison

# Explicit JIT acceptance on contended writers; zero returned bodies fails.
timeout 600s python3 bench/rwlock_compare/run.py \
  --functional --repeats 1 --backends kdlock --workloads rcuht \
  --write-percent 20 --threads 16 36 --collector-cpu 58 --require-jit \
  --spin-entry-ratio-limit 0 --output /root/kdlock-evidence/rwlock-jit
```

`--delegate off --backends kdlock` supplies a KD native writer control. Ratio
limit zero bypasses only the optional spin entry-ratio filter; adaptive CPU/lock
heat admission remains enabled. The default ratio limit is 2, NUMA is on,
prefetch mode is 2, and the KD/TCLock batch setting is 1,024. All benchmark modules
disable UBSAN; the captured kernel's configuration and mitigations stay intact.
Replace `YOUR_CONFIRMED_SNAPSHOT` with the actual destination monitor tag and use
new output directories. The archived original-host snapshot is not portable.

## Measurement and acceptance

Each case loads fresh modules and prepares exactly one KD writer entry. Translation
finishes and the daemon exits before all-worker warmup (48,000 operations each).
Read-only cases require no writer publication. Measurement is one ioctl per pinned
worker, with no Python operation loop or added shared reader counters. All backends
execute identical register-only post-work, explicitly set by `--post-work-rounds`
(default **4**, the earlier KD benchmark setting). Record this value when comparing
against later spin/mutex runs; do not pool different post-work amounts.

Timed runs default to two seconds, progress checkpoints every 256 operations,
10 ms collector samples and the existing highest observed 300 ms full-cohort
window after 300 ms settling. Actual kernel timestamp brackets determine its
duration; no interpolation is used. Raw samples retain sampling delay, count
quantization and per-worker progress. Whole-run read/write rates include start,
tail and collector/join overhead; these rates and JIT shares do not describe the
selected peak window. Separate peak read/write rates use the exact deterministic
mix at each sampled worker count. Inverse aggregate throughput is not acquisition latency.

The oracle requires exact read/write counts, consistent cacheline reads, exact
writer increments on active lines, unchanged inactive lines, valid hash membership,
unique keys/backlinks/bucket placement and exact move/conflict/miss totals. Worker
CPU, post-work checksum, preemption/IRQ balance and final count/gate state must also match.

KD counts **returned JIT writer bodies**, divided by completed **writes**.
`NO_JIT` remains visible even when adaptive native execution has valid throughput;
NORMAL publication never proves JIT execution. `--require-jit` makes zero bodies
a failed case for each selected multithreaded KD writer configuration. Read-only
and disabled controls require zero JIT. TCLock's native stack delegation is used,
but its share is **UNMEASURED**, like the existing spin comparator; do not infer it
from contention or throughput.

`plan.json`, `environment.json`, frozen sources/binaries, build logs, ELF context
audit, translation images, raw phase samples, kernel logs and each `session.json`
remain in the output directory. `records.json` includes failed/not-run cases.
`summary.json` contains only validated drained timed cases, grouping JIT positives
separately from NO_JIT controls. It reports best peak, min/median/max/spread,
whole-run min/median/max and whether all three rounds are present. Functional
runs produce no performance summary entries.

`parity.json` checks the requested performance target at every point: KD's best
warmed peak and median whole-run rate must each meet both native and TCLock.
`--require-parity` returns a failure after completing all sessions if any point
is slower or lacks three comparable rounds. There is no tolerance or pooling of
JIT/NO_JIT groups. This is an observed-throughput threshold, not a statistical
claim that small differences exceed measurement noise.

Create `<output>/STOP` to stop at the next drained case boundary. A timeout or
kernel fault preserves processes/modules for diagnosis; it is never evidence
that callers drained. Successful teardown joins workers, stops translators,
retires KD sources, checks TCLock count/gate/stack/queue state, clears its target
binding, and unloads workload before backend. Never force unload.

The runner verifies live native qspinlock function pointers from the captured
kernel's DWARF layout, so rotated boot messages do not require skipping boot-policy
verification. Only the two dispatch pointers are read from `/proc/kcore`.

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
