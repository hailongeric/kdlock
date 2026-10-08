# KD, TCLock and Linux Native comparison

[run.py](run.py) measures spin; [run_mutex.py](run_mutex.py) measures ordinary mutex.
Each arm has separate workload functions and lock objects, sharing payload, timing
and reporting. Operations do not branch on a runtime `is_mutex` selector.
Build and execute in the verified recovery guest; follow [operations](../../docs/AGENTS.md)
for snapshots, frozen inputs and drain.

## Prepare and run

Verify the captured kernel and idle state with [the project guide](../../docs/PROJECT_GUIDE.md).
The current VM uses [nopvspin](../../docs/PROJECT_GUIDE.md#native-qspinlocks-in-the-vm).
Check the live argument and boot confirmation; Build ID alone does not select
the spin path. Use a confirmed snapshot of this boot and replace
`YOUR_CONFIRMED_SNAPSHOT` in the examples with its actual monitor tag.
Fix host CPUs at 2.5 GHz and check vCPU/NUMA affinity; keep the existing kernel,
mitigations and preemption configuration. Confirm a real monitor snapshot before
setting recovery variables. Output must be a new directory outside the checkout.

Recommended full spin cacheline matrix:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --workload cacheline --cachelines 1 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 --repeats 3 \
  --duration-ms 2000 --peak-window-ms 300 --collector-cpu 38 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/spin-matrix-new
```

For mutex, replace the entry with `run_mutex.py` and choose a new output directory.
For hash, use `--workload rcuht` and omit `--cachelines`. Mutex accepts only ordinary
`plain` operations and its current fixed 1,024 batch configuration. KD mutex JIT
is always enabled; the provider has no `mutex_jit` parameter.

| Option/default | Meaning |
| --- | --- |
| `--threads 1 4 8 16 20` | Short default; explicitly select the full 15-point set above |
| `--repeats 3` | Three rounds/configuration, rotating backend order |
| `--duration-ms 0` | Fixed iterations by default; use 2,000 for the timed comparison |
| `--peak-window-ms 300`, `--peak-settle-ms 300` | Highest valid cohort window after settling |
| `--collector-cpu 30` | Dedicated CPU outside workers; use38 for the full 36-worker matrix |
| `--numa on`, `--kd-batch-size 1024` |KD NUMA selection and body bound; separate scan budget |
| `--spin-prefetch 2` |KD producer-prepared hints |
| `--spin-entry-ratio-limit 2` | Adaptive ratio rule; 0 bypasses only ratio filtering |
| `--kd-provider-ubsan off` | Private KD provider only; `kernel` inherits kernel policy |
| `--cpus 0-7,20-27` | Ordered worker placement; each cohort takes its prefix |
| `--dry-run` | Print plan without live execution |

The runner builds matching backend/workload/provider copies and audits actual ELF
interfaces, return layouts and sanitizer references. KD preparation publishes the
entry before all workers warm up with 48,000 operations each; the daemon is stopped
before measurement. NUMA tables and layout metadata describe actual builds, not
requested labels alone.

## Workloads and backends

Cacheline bodies update 1/8/16 cachelines. Hash uses 1,024 buckets, 4,096 preallocated
nodes, 8,192 keys and 100% writes: each request records one move, conflict or miss.
The three arms use the same immediate unlink/relink body and fixed CPU-seeded random
streams; this adaptation is not a byte-identical upstream RCUHT environment.
There are no per-body allocation/RCU services. Lock-outside arithmetic stays timed;
the selected hash loop has no `cond_resched()` points. Layout ABI v2 records that
policy. Static snapshots check complete structure and exact operation totals.

| Arm | Spin | Mutex |
| --- | --- | --- |
| Native | Original kernel functions, no provider | Original mutex functions bypass experimental clobber macros |
| TCLock | Native waiter-stack delegation | Actual upstream ordinary mutex port with parking |
| KD | Explicit KD word, ABI1/JIT | Original Linux mutex plus shadow gate, ABI2/outer cookie/JIT |

TCLock retains NUMA/WWJUMP and configured 1,024; zero-based jumps can execute 1,025
bodies. The shared port header currently enables NUMA even when Makefile's variable
is 0; actual ELF metadata rejects misleading off labels. Spin IRQ checks are disabled
for this IRQ-enabled task-context comparator, and batches do not truncate on
`need_resched()`. TCLock/workloads have UBSAN off; the kernel's policy is unchanged.
Mutex workers preregister one fixed-affinity context per CPU before measurement;
contexts/task refs survive complete cohort drain. KD published waiters remain pinned
polling. See [TCLock scope](../../tclock_backend/README.md) and
[all six protocols](../../docs/design/lock_protocols.md).

## Results and validity

`records.json` keeps every planned sample, including failure/not-run states.
Only correct, completed, drained samples enter `summary.csv/json`.
Timed comparison uses `best_valid_warmed_peak`; fixed iteration uses
`best_valid_throughput`. The chosen session supplies both its throughput and
amortized ns/op. Keep `best_whole_*` too; peak superiority does not imply sustained
superiority. Spread is `(max-min)/median ×100%`. Backend ratios compare corresponding
best valid peaks; medians describe repeatability and regression.

Keep workload, lock kind, caller shell/cookie, heat policy, ratio and UBSAN settings
separate. Never pool historical observe/percentage policies with current adaptive
right-shift rules. [Execution flow](../../docs/JIT_EXECUTION.md#heat-and-roles)
defines the current counters. Session-end counters may include warmup and are not
selected-window counts.

KD actual JIT requires wrapper-returned body evidence where the configuration
requires delegation. Native low-contention samples can be valid performance
observations while marked NO_JIT; they are not JIT passes. Contended mutex positives
require returned bodies. TCLock spin delegation is `UNMEASURED`, not zero; mutex
reports returned-batch delegated bodies and parks, with positive contended evidence.
`--keep-going-no-jit` retains drained failures and continues collection, but excludes
failed scores and leaves the final exit nonzero.

Timed peak selection requires all workers to progress in the full cohort window.
Keep whole-run per-worker and node shares too, especially 24-thread minority-node
cases. A bounded batch and positive observed counts do not prove starvation freedom.

The [2026-10-08 spin/mutex matrix](results/20261008-threeway-spin-mutex.md)
reruns committed `009e8e3` with one-cacheline/hash payloads, all 15 thread counts
and 540 valid samples. It preserves four lock-outside arithmetic rounds; the
uncommitted 64-round change was excluded. Hash and minority-node gaps remain.
This matrix predates `nopvspin`; it is not a measurement of the current boot policy.
Earlier comparisons and failed candidates are in [the evidence index](results/HISTORY.md).

## Functional and diagnostic checks

Use a new output directory for selected plain/nested/early JIT checks:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT \
  LC_ALL=C timeout --kill-after=10s 180s python3 bench/tclock_compare/run.py \
  --functional --backends kdlock --cachelines 1 --threads 20 --repeats 1 \
  --iterations 100000 --scenario nested --spin-entry-ratio-limit 0 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/nested-new
```

Nested/early are KD spin cacheline only. Functional runs require actual JIT for
multithread positives and write `functional.json`, not performance summaries.
`--spin-delegate off` is an explicit zero-JIT native control marked DISABLED_CONTROL.
It applies only to spin; the mutex entry rejects it.
Ratio0 does not guarantee admission or waive returned-body/context/drain checks.

`--pmu` is a separate long-batch diagnostic using supported perf events. Verify
availability, sample loss and identity before attribution; do not add its scores to
normal measurements or infer remote-memory latency from flat cycle samples.
[Tests](../../tests/README.md) selects affected fixtures and source/assembly audits.

## Shutdown

Join workers → verify data/lock/queue/frame drain → stop translators → retire KD
sources → unload workload → unload backend/provider. Clear TCLock's diagnostic
`target_lock` before freeing its workload storage. Do not force unload on EBUSY,
reuse old RIP-keyed JIT after replacing only a source module, or alter frozen inputs.
