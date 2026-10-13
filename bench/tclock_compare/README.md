# KD, TCLock and Linux Native comparison

[run.py](run.py) measures spin; [run_mutex.py](run_mutex.py) measures ordinary mutex.
Each backend has its own compiled workload functions and lock object. They use
the same protected operations, timing method and reports. Choosing spin versus
mutex happens at build time, without a runtime `is_mutex` branch in each operation.
Build and execute in the verified recovery guest on `10.176.26.71`; follow [operations](../../docs/AGENTS.md)
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

Example timed spin cacheline comparison after that verification:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --workload cacheline --cachelines 1 \
  --threads 1 8 16 32 48 60 --repeats 3 \
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
| `--threads 1 4 8 16 20` | Short default; set worker counts explicitly for a timed comparison |
| `--repeats 3` | Three rounds/configuration, rotating backend order |
| `--duration-ms 0` | Fixed iterations by default; use 2,000 for the timed comparison |
| `--peak-window-ms 300`, `--peak-settle-ms 300` | Highest valid cohort window after settling |
| `--collector-cpu 30` | Built-in default; override with an available CPU outside workers (63 on the documented destination, 38 in the original full matrix) |
| `--numa on`, `--kd-batch-size 1024` | KD spin/mutex NUMA selection and total body bound; separate scan/cohort budgets |
| `--spin-prefetch 2` |KD producer-prepared hints |
| `--spin-entry-ratio-limit 2` | Adaptive ratio rule; 0 bypasses only ratio filtering |
| `--kd-provider-ubsan off` | Private KD provider only; `kernel` inherits kernel policy |
| `--mutex-spin-limit 4096` | KD mutex polling budget before uninterruptible sleep; 0 parks immediately |
| `--cpus LIST` | Ordered worker placement; each cohort takes its prefix. Choose node membership from the verified topology |
| `--dry-run` | Print plan without live execution |

KD mutexes always support blocking. `--mutex-wait-mode` has been removed;
each backend runs once per round. Records retain `mutex_wait_mode=blocking`
and the polling budget so current runs remain distinct from historical spin
measurements. The runner rejects providers with the obsolete policy selector.

Both entries now accept any worker count from 1 through 64. The full new-host
comparison uses 22 counts: 1–8 in steps of one, then 12–64 in steps of four.
Use the [complete-matrix driver](../../tools/vm/README.md#complete-164-worker-comparison)
for one-cacheline and hash payloads; larger cacheline sizes require an explicit
opt-in. Its temporary 66-vCPU placement keeps
64 distinct worker vCPUs and a separate guest collector; the collector shares
a physical core with the last worker at the 64-worker point. The example above
uses six worker counts and fits the regular 64-vCPU boot.

The runner builds matching copies of each backend, workload and provider. It
checks the built ELF interfaces, return layouts and sanitizer references. KD
publishes the prepared entry before every worker warms up with 48,000 operations.
The daemon stops before measurement. Recorded NUMA and layout settings come from
the actual build, so requested option names alone cannot mislabel a sample.

## Workloads and backends

Cacheline comparisons default to one line; 8/16-line bodies remain available only
when explicitly requested. Hash uses 1,024 buckets, 4,096 preallocated
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
contexts/task refs survive complete cohort drain. KD mutex waiters retain migration
pins and reserved stacks while sleeping after bounded polling. Historical waiting-policy
comparisons are indexed in the [archive guide](../mutex_wait_compare/README.md).
See [TCLock scope](../../tclock_backend/README.md) and
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

Mutex acceptance defaults to `--mutex-acceptance jit-required`. Explicit
`--mutex-acceptance adaptive-performance` also scores correct, drained native
execution chosen by admission. Those samples retain zero returned bodies and
the `ADAPTIVE_NATIVE` classification; they do not pass JIT acceptance.
Functional checks always retain JIT-required acceptance.

`--mutex-entry-ratio-limit` accepts powers of two from 2 through 256 (default
256). The CPU compares `(entries >> 10) < limit` every 1,024 failed native
attempts. The 1,025-record exact-address heat check and strict comparison stay
unchanged. The pinned sampler skips cold table access between CPU comparisons;
no threshold or route depends on the benchmark's worker count.

`--mutex-routing native` forces the existing native fallback after sampling.
It is an unscored `NATIVE_ROUTING_CONTROL` diagnostic and must return zero JIT
bodies. Every sample records threshold, routing, acceptance and execution class.
Reports keep different thresholds and policies separate, retain median whole-run
rates, and exclude diagnostic/PMU samples from performance scores.

The [c01 acceptance auditor](mutex_study.py) verifies frozen inputs and recomputes
peaks from raw progress. Its primary grid is 1–8, 12, 16, 20, 24 and 28 workers;
32, 36, 48 and 60 compare against fresh baseline KD and require returned JIT in
every round. Both median whole-run and best warmed peak must reach 97% of their
respective controls. A failing screening rung rejects a candidate; missing grid
points cannot pass. A new default requires the smallest passing threshold and
two independent fresh three-round confirmation blocks.

Timed peak selection requires all workers to progress in the full cohort window.
Keep whole-run per-worker and node shares too, especially cohorts with unequal
NUMA membership (24 threads in the original 40-vCPU setup). A bounded batch and
positive observed counts do not prove starvation freedom.

[Performance status](../../docs/PERFORMANCE.md) summarizes the latest frozen
comparison and remaining gaps. The [machine result indexes](../results/README.md)
retain older reports, source identities and rejected trials. Current blocking-only
mutex checks are [recorded separately](../results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json).
Publication, correct execution and performance acceptance are distinct results.

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
`--perf-record` instead collects 199 Hz kernel cycle samples around the measured
client and its workers. It retains `perf.data`, the live module/symbol maps,
a flat symbol report and timestamped CPU samples. Symbols are resolved before
module unload; borrowed stacks are not interpreted as call graphs. This option
is mutually exclusive with `--pmu` and excludes every backend from performance
scores. Check lost samples and instrumentation-induced behavior changes before
using a profile to choose an optimization.
`--profile-lock --cachelines 1` adds separate intrusive kprobes for Native spin
or Native/KD mutex. It counts native slow entries, accepted/declined admission
and completed packets per combiner, and samples the mutex owner every 100 us on
the collector CPU. Histogram bucket 0 is empty; bucket k covers
`2**(k-1)..2**k-1`, with bucket 11 also including larger counts. Returned JIT
bodies are counted independently. Owner changes count changes between nonzero
samples, not exact ownership streaks or cacheline transfers. Probe overhead can
change admission and scheduling; do not use these rates for acceptance. The
runner requires zero missed probes and unloads the profiler after worker drain,
before retiring the source/provider whose storage it observes.
[Tests](../../tests/README.md) selects affected fixtures and source/assembly audits.

## Shutdown

Join workers → verify data/lock/queue/frame drain → stop translators → retire KD
sources → unload workload → unload backend/provider. Clear TCLock's diagnostic
`target_lock` before freeing its workload storage. Do not force unload on EBUSY,
reuse old RIP-keyed JIT after replacing only a source module, or alter frozen inputs.
For Native and KD mutex workloads, the worker-drain ioctl also requires a zero
original owner word, an empty sleeping wait list and an empty configured Linux
OSQ. It checks these only after workers return while holding the snapshot gate.
