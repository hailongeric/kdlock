# KD, TCLock and Linux Native comparison

The current KD mutex arm uses a 256-byte `struct kd_mutex` with no Linux mutex
imports. The shared client validates its full object extent; other lock types
keep their own sizes. The accepted `555b8b7` baseline uses its frozen older client,
provider and translator in the [paired round](../results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md).

[run.py](run.py) measures spin; [run_mutex.py](run_mutex.py) measures ordinary mutex.
Each backend has its own compiled workload functions and lock object. They use
the same protected operations, timing method and reports. Choosing spin versus
mutex happens at build time, without a runtime `is_mutex` branch in each operation.
Build and execute in the verified recovery guest on `10.176.26.71`; follow [operations](../../docs/operations/VM.md)
for snapshots, frozen inputs and drain.
Mixed read/write workloads use the separate [rwlock runner](../rwlock_compare/README.md),
which compares Native, TCLock and KD on the same adapted RCUHT payload.

Keep new guest evidence under `/root/kdlock-evidence/10.176.26.71/bench/<run>`.
Host archives and compact reports use the corresponding machine directory in
[the result layout](../results/README.md). Edit source on `380G10` and synchronize
reviewed inputs to the new-host VM before running.

## Prepare and run

Verify the captured kernel and idle state with [the project guide](../../docs/PROJECT_GUIDE.md).
Benchmark boot policy requires [nopvspin](../../docs/PROJECT_GUIDE.md#native-qspinlocks-in-the-vm).
Check the live argument and boot confirmation; Build ID alone does not select
the spin path. Use a confirmed snapshot of this boot and replace
`YOUR_CONFIRMED_SNAPSHOT` in the examples with its actual monitor tag.
Check the benchmark host frequency policy and vCPU/NUMA affinity; keep the existing kernel,
mitigations and preemption configuration. Confirm a real monitor snapshot before
setting recovery variables. Output must be a new directory outside the checkout.

The example uses collector 63 for the documented 64-vCPU destination. Its
[migration checks](../README.md#vm-migration-validation) are recorded separately
from the historical 40-vCPU runs, which used collector 38. Verify the actual
online/available CPUs and keep the collector outside every worker set.

Full spin cacheline matrix after that verification:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --workload cacheline --cachelines 1 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 --repeats 3 \
  --duration-ms 2000 --peak-window-ms 300 --collector-cpu 63 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/10.176.26.71/bench/spin-matrix-new
```

For mutex, replace the entry with `run_mutex.py` and choose a new output directory.
For hash, use `--workload rcuht` and omit `--cachelines`. Mutex accepts only ordinary
`plain` operations. Its default batch cap is 1,024 bodies; `--kd-batch-size`
sets the compile-time cap, checked against `mutex_batch` provider metadata. KD mutex
delegation requires JIT; native-first acquisition remains enabled. The provider
has no `mutex_jit` parameter.

| Option/default | Meaning |
| --- | --- |
| `--threads 1 4 8 16 20` | Short default; explicitly select the standard 21-point set above |
| `--repeats 3` | Three rounds/configuration, rotating backend order |
| `--duration-ms 0` | Fixed iterations by default; use 2,000 for the timed comparison |
| `--peak-window-ms 300`, `--peak-settle-ms 300` | Highest valid cohort window after settling |
| `--collector-cpu 63` | Separate collector on the current 64-vCPU VM |
| `--share-collector` | Explicit optional 64-worker point only; timed mode and workers 0–63 required |
| `--numa on`, `--kd-batch-size 1024` | KD spin/mutex NUMA selection and total body bound; separate scan/cohort budgets |
| `--spin-prefetch 2` |KD producer-prepared hints |
| `--spin-entry-ratio-limit 2` | Adaptive ratio rule; 0 bypasses only ratio filtering |
| `--kd-provider-ubsan off` | Private KD provider only; `kernel` inherits kernel policy |
| `--cpus LIST` | Ordered worker placement; each cohort takes its prefix. Choose node membership from the verified topology |
| `--dry-run` | Print plan without live execution |

Both entries accept 1–64 workers. The standard grid stops at 60 and keeps
collector 63 separate. For an optional 64-worker point on exactly 64 online CPUs,
select `--cpus 0-63 --collector-cpu 63 --share-collector` in timed mode.
Only that cohort records `collector_shared=true`; smaller cohorts remain separate.
The client and peak reader reject unlabelled/partial overlap. Report identity
separates shared, dedicated and historical unrecorded collector settings.

The runner builds matching copies of each backend, workload and provider. It
checks the built ELF interfaces, return layouts and sanitizer references. KD
publishes the prepared entry before every worker warms up with 48,000 operations.
The daemon stops before measurement. Recorded NUMA and layout settings come from
the actual build, so requested option names alone cannot mislabel a sample.

## Workloads and backends

Future cacheline comparisons use c01 and c08. The default is one line; select
`--cachelines 1 8` for both cases. Spin/mutex post-work is 64 dependent arithmetic
rounds. Hash uses 1,024 buckets, 4,096 preallocated
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
| KD | Explicit KD word, ABI1/JIT | KD-owned physical mutex and embedded legacy gate, ABI2/outer cookie/JIT |

TCLock retains NUMA/WWJUMP and configured 1,024; zero-based jumps can execute 1,025
bodies. The shared port header currently enables NUMA even when Makefile's variable
is 0; actual ELF metadata rejects misleading off labels. Spin IRQ checks are disabled
for this IRQ-enabled task-context comparator, and batches do not truncate on
`need_resched()`. TCLock/workloads have UBSAN off; the kernel's policy is unchanged.
Mutex workers preregister one fixed-affinity context per CPU before measurement;
contexts/task refs survive complete cohort drain. KD published waiters remain pinned
polling. See [TCLock scope](../../tclock_backend/README.md) and
[all nine lock protocols](../../docs/design/lock_protocols.md).

## Results and validity

`records.json` keeps every planned sample, including failed or unrun cases.
`summary.csv/json` includes only samples with correct results, completed work and
successful drain. Timed comparisons select `best_valid_warmed_peak`; fixed-iteration
comparisons select `best_valid_throughput`. The selected run supplies both its
throughput and amortized ns/op.

Keep the `best_whole_*` rates as well: winning a short peak window does not mean
winning over the whole run. Spread is `(max-min)/median ×100%`. Ratios between
backends use their corresponding best valid peaks, while medians help show
repeatability and regressions.

Keep workload, lock kind, caller shell/cookie, heat policy, ratio and UBSAN settings
separate. Never pool historical observe/percentage policies with current adaptive
right-shift rules. [Execution flow](../../docs/JIT_EXECUTION.md#heat-and-roles)
defines the current counters. Session-end counters may include warmup and are not
selected-window counts.

A configuration that requires KD delegation must record JIT bodies returned by
the wrapper. With little contention, a native run may have valid throughput but
is marked NO_JIT, not a JIT pass. Contended mutex cases require returned bodies.
TCLock spin delegation is `UNMEASURED`; that does not mean zero. TCLock mutex reports
returned delegated bodies and successful parks, and must show delegation under
contention. `--keep-going-no-jit` keeps drained failures and continues collecting,
but excludes their failed scores and still exits nonzero.

Timed peak selection requires all workers to progress in the full cohort window.
Keep whole-run per-worker and node shares too, especially cohorts with unequal
NUMA membership (24 threads in the original 40-vCPU setup). A bounded batch and
positive observed counts do not prove starvation freedom.

The [current KD-only comparison](../results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
retains 504 sessions for c01/post64 and pipebytes n16 over the standard grid,
including the compatibility baseline and Native/TCLock controls. Use
[performance status](../../docs/PERFORMANCE.md) for outcomes and
[historical evidence](../../docs/history/README.md) for superseded implementations.
The `adaptive` session suffix refers to admission heat policy, not the rejected
adaptive mutex locking protocol.

## Functional and diagnostic checks

Use a new output directory for selected plain/nested/early JIT checks:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT \
  LC_ALL=C timeout --kill-after=10s 180s python3 bench/tclock_compare/run.py \
  --functional --backends kdlock --cachelines 1 --threads 20 --repeats 1 \
  --collector-cpu 63 \
  --iterations 100000 --scenario nested --spin-entry-ratio-limit 0 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/10.176.26.71/bench/nested-new
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
