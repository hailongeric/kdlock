# Read-write lock comparison

This runner compares Linux native rwlocks, the
[TCLock rwlock port](../../tclock_backend/README.md) and
[KD rwlocks](../../docs/design/rwlock_implementation.md) on the same workload.
Use the separate [correctness test](../../workload_modules/rwlock/README.md) for
instrumented checks of reader overlap and writer exclusion.

Build, test and run only in the recovery guest on `10.176.26.71`. Follow
[operations](../../docs/AGENTS.md) to verify the kernel, confirm a recovery snapshot
and check that all work has finished before unloading modules.

Edit source in the checkout on `380G10` and synchronize it to this guest first.
New guest evidence belongs under `/root/kdlock-evidence/10.176.26.71/bench/<run>`;
retain host archives and compact summaries in [the machine result layout](../results/README.md).

[Performance status](../../docs/PERFORMANCE.md) summarizes measured outcomes and
remaining gaps. The [destination-host index](../results/10.176.26.71/README.md)
and [original-host index](../results/380G10/README.md) retain the separate
measurements, caller ABIs, JIT evidence and topology limits.

## Cases

The [workload guide](../../docs/BENCHMARK_WORKLOADS.md#synthetic-readerwriter-mixes)
explains the reader and writer bodies and labels such as `c08-w20`.

| Workload | Protected operations | Sizes |
| --- | --- | --- |
| `cacheline` | Readers load and compare a consistent version; writers increment every selected line | 1, 2, 4, 8, 16 distinct 64-byte lines |
| `rcuht` | Readers look up a key; writers move a preallocated node between hash buckets | 1,024 buckets, 4,096 nodes, 8,192 possible keys |

The hash update and final structure checks reuse the previous
[KD/TCLock hash payload](../../workload_modules/spin_cacheline/hash_payload.h),
adapted from TCLocks `rcuhashbash_write_lock`. One global rwlock protects the table.
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
backends produce **270 sessions**. `--threads` selects a shorter set;
`--full-matrix` explicitly restores the default 15-point set.
`--cpus` is an ordered list: a run with N workers uses the first N CPUs. Keep
runs on one NUMA node separate from runs spanning nodes. The collector samples
progress on its own CPU, which must be online, available and outside every worker
set. Its built-in default is CPU 38, as used in the recorded 40-vCPU runs.

All new runs use exactly CPUs 0–63, with NUMA node 0 on 0–31 and node 1 on
32–63, pinned to the same-numbered host cores. Do not add extra vCPUs or an
unused spare CPU. The commands below use collector CPU 63 outside worker
cohorts. At 64 workers the collector must share CPU 63; the current runner needs
support for that overlap before execution. See the
[placement limitation](../../tools/vm/README.md#complete-164-worker-comparison).
The earlier 60-vCPU
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

After verifying the actual monitor snapshot and guest identity:

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT

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
Replace `YOUR_CONFIRMED_SNAPSHOT` with the actual destination monitor tag and use
new output directories. The archived original-host snapshot is not portable.

## Measurement and acceptance

Each run loads fresh modules and prepares one KD writer entry. Translation
finishes and the daemon exits before all workers warm up with 48,000 operations
each. A read-only case needs no writer publication. Each pinned worker executes
its measured loop in one ioctl. Python does not run an operation-by-operation
loop, and measurement adds no shared reader counters.

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

KD's JIT share is **returned JIT writer bodies / completed writes**. Reads are
excluded. `NO_JIT` means no returned JIT bodies were observed; a native run may
still have valid throughput. NORMAL only means code was published.
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
of these must hold against **each** of Native and TCLock:

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
