# KD, TCLock and Linux Native comparison

[run.py](run.py) measures spin; [run_mutex.py](run_mutex.py) measures ordinary mutex.
Each backend has its own compiled workload functions and lock object. They use
the same protected operations, timing method and reports. Choosing spin versus
mutex happens at build time, without a runtime `is_mutex` branch in each operation.
Build and execute in the verified recovery guest; follow [operations](../../docs/AGENTS.md)
for snapshots, frozen inputs and drain.
Mixed read/write workloads use the separate [rwlock runner](../rwlock_compare/README.md),
which compares Native, TCLock and KD on the same adapted RCUHT payload.

## Prepare and run

Verify the captured kernel and idle state with [the project guide](../../docs/PROJECT_GUIDE.md).
Benchmark boot policy requires [nopvspin](../../docs/PROJECT_GUIDE.md#native-qspinlocks-in-the-vm).
Check the live argument and boot confirmation; Build ID alone does not select
the spin path. Use a confirmed snapshot of this boot and replace
`YOUR_CONFIRMED_SNAPSHOT` in the examples with its actual monitor tag.
Fix host CPUs at 2.5 GHz and check vCPU/NUMA affinity; keep the existing kernel,
mitigations and preemption configuration. Confirm a real monitor snapshot before
setting recovery variables. Output must be a new directory outside the checkout.

The example uses collector 58 for the documented 60-vCPU destination. Its
[migration checks](../README.md#vm-migration-validation) are recorded separately
from the historical 40-vCPU runs, which used collector 38. Verify the actual
online/available CPUs and keep the collector outside every worker set.

Full spin cacheline matrix after that verification:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --workload cacheline --cachelines 1 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 --repeats 3 \
  --duration-ms 2000 --peak-window-ms 300 --collector-cpu 58 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/spin-matrix-new
```

For mutex, replace the entry with `run_mutex.py` and choose a new output directory.
For hash, use `--workload rcuht` and omit `--cachelines`. Mutex accepts only ordinary
`plain` operations and its current fixed 1,024 batch configuration. KD mutex
delegation requires JIT; native-first acquisition remains enabled. The provider
has no `mutex_jit` parameter.

| Option/default | Meaning |
| --- | --- |
| `--threads 1 4 8 16 20` | Short default; explicitly select the full 15-point set above |
| `--repeats 3` | Three rounds/configuration, rotating backend order |
| `--duration-ms 0` | Fixed iterations by default; use 2,000 for the timed comparison |
| `--peak-window-ms 300`, `--peak-settle-ms 300` | Highest valid cohort window after settling |
| `--collector-cpu 30` | Built-in default; override with an available CPU outside workers (58 on the documented destination, 38 in the original full matrix) |
| `--numa on`, `--kd-batch-size 1024` |KD NUMA selection and body bound; separate scan budget |
| `--spin-prefetch 2` |KD producer-prepared hints |
| `--spin-entry-ratio-limit 2` | Adaptive ratio rule; 0 bypasses only ratio filtering |
| `--kd-provider-ubsan off` | Private KD provider only; `kernel` inherits kernel policy |
| `--cpus LIST` | Ordered worker placement; each cohort takes its prefix. Choose node membership from the verified topology |
| `--dry-run` | Print plan without live execution |

The runner builds matching copies of each backend, workload and provider. It
checks the built ELF interfaces, return layouts and sanitizer references. KD
publishes the prepared entry before every worker warms up with 48,000 operations.
The daemon stops before measurement. Recorded NUMA and layout settings come from
the actual build, so requested option names alone cannot mislabel a sample.

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

The closed phase screened candidates separately at 16/36 threads, adding 2 for
caller changes and 24 for fairness. An apparent regression was rechecked once;
repeatable median losses above 3% at protected points caused rejection. The full
comparison used all 15 thread counts and both payloads. Parity required matching
the stronger of TCLock and Native at each point, with peak and sustained rates
reported separately; 90% of TCLock's peak was an intermediate milestone.

The [protocol simplification report](results/20261008-protocol-simplification/README.md)
keeps isolated screens, full 15-point matrices and rechecks separate under
`nopvspin`. Both combined terminal/memory and memory-only candidates were rejected
for repeated regressions. No runtime change was promoted; the eager code pool
remains current. Raw stage names `final` and `retained` identify those rejected
candidates. The fresh restored-runtime comparison (`restored`) contains 540
sessions across all 15 thread counts and both payloads for spin and mutex.

The spin/mutex phase closed on 2026-10-09. The earlier
[hash diagnosis](results/HISTORY.md#hash-diagnosis) and
[mandatory-JIT mutex trials](results/20261008-mutex-priority-trials.md) use the same
boot policy. The [previous 540-sample matrix](results/HISTORY.md#pre-nopvspin-matrix)
predates `nopvspin` and must remain separate. All of these runs use four lock-outside
arithmetic rounds; the unrelated 64-round working-tree change was excluded.
The [evidence index](results/HISTORY.md) links source identities, failed candidates
and complete statistics. Publication, correct execution and performance acceptance
are distinct results.

## Functional and diagnostic checks

Use a new output directory for selected plain/nested/early JIT checks:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT \
  LC_ALL=C timeout --kill-after=10s 180s python3 bench/tclock_compare/run.py \
  --functional --backends kdlock --cachelines 1 --threads 20 --repeats 1 \
  --collector-cpu 58 \
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
