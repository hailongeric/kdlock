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

All new runs use exactly CPUs 0–63: NUMA node 0 has 0–31 and node 1 has 32–63,
with each vCPU pinned to the same-numbered host core. Do not add extra vCPUs
or an unused spare CPU. The example uses collector 63. Its
[migration checks](../README.md#vm-migration-validation) are recorded separately
from the historical 40-vCPU runs, which used collector 38. Verify the actual
online/available CPUs and keep the collector outside worker sets of up to 63
workers. For the 64-worker point, explicitly select
`--cpus 0-63 --collector-cpu 63 --share-collector`. This marks the overlap in the
client/session records; smaller cohorts still have a separate collector.

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
| `--repeats 3` | Three rounds/configuration, reversing backend order in the middle round |
| `--duration-ms 0` | Fixed iterations by default; use 2,000 for the timed comparison |
| `--peak-window-ms 300`, `--peak-settle-ms 300` | Highest valid cohort window after settling |
| `--collector-cpu 30` | Built-in default; override with an available CPU outside workers (63 on the documented destination, 38 in the original full matrix) |
| `--share-collector` | Off by default; timed runs only, with the full ordered CPU list `0-63` and collector 63; labels overlap at 64 workers |
| `--numa on`, `--kd-batch-size 1024` | KD spin/legacy-mutex NUMA selection and total body bound; owned selection has its own opt-in switch |
| `--spin-prefetch 2` | KD producer-prepared hints |
| `--spin-entry-ratio-limit 2` | Adaptive ratio rule; 0 bypasses only ratio filtering |
| `--kd-provider-ubsan off` | Private KD provider only; `kernel` inherits kernel policy |
| `--mutex-spin-limit 4096` | KD mutex result polling budget before uninterruptible sleep; 0 skips polling. For owned-v1 this does not limit SELF owner spinning through OSQ |
| `--mutex-implementation legacy` | `owned-v1` opts into the separate KD-owned c01 object; nested/early require functional mode |
| `--owned-mutex-entry-ratio-limit 256` | Independent ABI2 admission threshold for `owned-v1`; powers of two 2–256. ABI4 local-first does not use heat admission |
| `--owned-mutex-cabi` | Opt-in ABI4 ordinary-C caller; Linux local acquisition before late capture, with no fixed owner-spin budget |
| `--owned-mutex-reuse-spins 0` | ABI4 allowance 0/8/32/128 after an unflagged release, once per OSQ turn; measured profile selects 32 |
| `--owned-mutex-refill` | Opt-in FIFO refilling within the same total batch cap; default is one finite snapshot |
| `--owned-mutex-origin-spin` | Opt into audited origin-GS execution with an exclusive readiness claim; requires `owned-v1` |
| `--owned-mutex-numa` | Opt into the eight-request/four-bypass selector; requires `owned-v1`, independent of origin claims |
| `--owned-mutex-preflight` | Compile the experimental ABI2 C gate; default false retains capture-first entry; mutually exclusive with ABI4 |
| `--owned-mutex-preflight-spins` | Opt-in gate budget: 0 (default), 64, 256, 1024 or 4096 polling steps; positive values require the gate flag |
| `--owned-mutex-preflight-queue` | Opt in to joining the private OSQ within a positive preflight polling budget; default false |
| `--cpus LIST` | Ordered worker placement; each cohort takes its prefix. Choose node membership from the verified topology |
| `--mutex-acceptance jit-required` | Default JIT acceptance; `adaptive-performance` also scores valid local execution with distinct classification |
| `--mutex-routing adaptive` | `native` is an unscored legacy control; `self` is an unscored owned control |
| `--dry-run` | Print plan without live execution |

KD mutexes always support blocking. `--mutex-wait-mode` has been removed;
each backend runs once per round. Records retain `mutex_wait_mode=blocking`
and the polling budget so current runs remain distinct from historical spin
measurements. The runner rejects providers with the obsolete policy selector.
Owned wait counters cover delegated result waits; the third gate counter is
zero because owned-v1 has no separate legacy gate. They do not count SELF sleeps.

Both entries now accept any worker count from 1 through 64. The full new-host
comparison uses 22 counts: 1–8 in steps of one, then 12–64 in steps of four.
Use the [complete-matrix driver](../../tools/vm/README.md#complete-164-worker-comparison)
for one-cacheline and hash payloads; larger cacheline sizes require an explicit
opt-in. That driver still requires a separate collector and cannot complete
its grid on the required topology. The individual spin/mutex runners support
all 22 counts with explicit collector sharing; the rwlock runner does not yet
support that overlap. Keep the 64-vCPU topology. The example above uses six
worker counts and a separate collector.

The runner builds matching copies of each backend, workload and provider. It
checks the built ELF interfaces, return layouts and sanitizer references. KD
publishes the prepared entry before every worker warms up with 48,000 operations.
The daemon stops before measurement. Recorded NUMA and layout settings come from
the actual build, so requested option names alone cannot mislabel a sample.

## Owned origin and NUMA comparison

The origin-readiness/NUMA comparison uses [owned_origin.py](owned_origin.py)
with a separately archived and built pre-change source tree. Its `current-kd`
arm uses that tree's provider, daemon and translator; Native and TCLock are also
measured afresh. The `numa` candidate enables origin claims and the
eight-request/four-bypass selector. Both switches remain independently
selectable in `run_mutex.py` as `--owned-mutex-origin-spin` and
`--owned-mutex-numa`. Provider defaults are off.

The screen requires the full 22-count grid on the fixed 64-vCPU topology.
`--share-collector` explicitly permits the 64-worker cohort to share CPU 63;
all smaller cohorts retain a separate collector:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_64_VCPU_SNAPSHOT \
  LC_ALL=C timeout --kill-after=10s 7200s python3 bench/tclock_compare/owned_origin.py \
  --baseline-root /root/kdlock-evidence/BASELINE_SOURCE \
  --baseline-commit FULL_BASELINE_COMMIT \
  --mutex-implementation owned-v1 --owned-mutex-cabi --owned-mutex-reuse-spins 32 \
  --mutex-acceptance adaptive-performance --workload cacheline --cachelines 1 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 64 \
  --cpus 0-63 --collector-cpu 63 --share-collector \
  --backends native tclock kdlock --repeats 3 --duration-ms 2000 \
  --output /root/kdlock-evidence/10.176.26.71/bench/origin-screen-NEW
```

Build the archived baseline's private provider and daemon in the guest before
running. Replace `BASELINE_SOURCE` with that tree and `FULL_BASELINE_COMMIT` with
its 40-character commit ID. The screen and each confirmation have four arms and
264 sessions: Native, TCLock, frozen KD and origin/NUMA.
The matrix retains three alternating-order rounds, 64 post-work rounds,
48,000 warmup operations per worker and the existing warmed-peak rules. Confirm
the NUMA candidate with the same command in two new three-round output
directories. Never combine blocks or CPU topologies into one
score. The 64-worker point must use workers 0–63 and collector 63, sharing that
CPU with the final worker and QEMU services. Record that contention separately.
The session and raw client JSON mark this point with `collector_shared=true`;
unlabelled overlap and partially shared cohorts are rejected.

`origin-gates.json` compares median whole-run throughput and each arm's highest
valid warmed peak against fresh current KD. It also retains and checks the
whole-run rate from that winning peak session. All must reach 97% at every
worker count in the screen and both confirmations before enabling NUMA by default.
Require all 22 counts, including the shared 64-worker point; passing a subset
does not authorize changing the default.
The 97%-of-Native target at 1–8 workers is assessed separately. Session JSON keeps
worker progress, CPU time, returned bodies and shares, parking, claims/failures,
preparation requests and bypasses. GS correctness/diagnostic runs contribute no
performance scores.

The [2026-10-15 report](../results/10.176.26.71/bench/mutex_owned/20261015-origin/README.md)
records the screen, separate confirmations, affected correctness checks and
the decision to retain opt-in defaults.

## Owned c01 full grid

The recorded c01 profile uses `owned-v1`, ABI4 and reuse allowance 32.
All workers increment the same counter in one 64-byte payload line; the lock
has its own aligned slot. The source currently defines 64 post-work arithmetic
rounds in [post_work.h](../../workload_modules/spin_cacheline/post_work.h).
Changing that value requires a separate baseline and evidence block.

For new measurements, verify the fixed
[64-vCPU placement](../../tools/vm/README.md#complete-164-worker-comparison),
confirm its recovery snapshot, and use the pinned guest Python environment.
The command below covers 1–8 and 12–64 workers, explicitly sharing the collector
at 64. Run only in that guest, with a fresh external output directory:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_64_VCPU_SNAPSHOT \
  LC_ALL=C timeout --kill-after=10s 7200s python3 bench/tclock_compare/run_mutex.py \
  --mutex-implementation owned-v1 --owned-mutex-cabi --owned-mutex-reuse-spins 32 \
  --mutex-acceptance adaptive-performance --kd-provider-ubsan off \
  --workload cacheline --cachelines 1 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 64 \
  --cpus 0-63 --collector-cpu 63 --share-collector \
  --backends native tclock kdlock --repeats 3 \
  --duration-ms 2000 --peak-window-ms 300 --peak-settle-ms 300 --sample-ms 10 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/10.176.26.71/bench/mutex-owned-c01-full-NEW
```

This collects 198 samples, with 48,000 warmup operations per worker and finite
FIFO batching. Origin claims and owned NUMA selection remain off. Keep the same
64-vCPU topology for the whole block and archive its evidence. At 64 workers,
CPU 63 carries the final worker, collector and QEMU services; record that
contention separately. For the separate 1–8 profile, omit `--share-collector`
and use `--threads 1 2 3 4 5 6 7 8 --cpus 0-7 --collector-cpu 63`.

The [recorded full-grid report](../results/10.176.26.71/bench/mutex_owned/20261014-full-grid/README.md)
owns all samples, variation, worker shares, CPU cost, plot and offline auditor.
That historical report used a temporary 66-vCPU topology, which must not be
reused for new runs or relabeled as the required 64-vCPU placement.
The [accepted 1–8 study](../../docs/PERFORMANCE.md#accepted-c01-18-worker-profile)
has its own screen and two confirmation blocks. A descriptive full-grid run
does not substitute for that acceptance procedure or the functional FULL/ACK checks.

## Workloads and backends

See [workloads and critical sections](../../docs/BENCHMARK_WORKLOADS.md#synthetic-cacheline-updates)
for the meaning of `c01`–`c16`, the shared counter layout and each hash move attempt.

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
| KD | Explicit KD word, ABI1/JIT | Default legacy: original mutex plus shadow gate, ABI2; explicit owned-v1: private owner/OSQ/FIFO, ABI2 or ABI4 |

`--mutex-implementation owned-v1` selects a distinct KD-owned `struct kd_mutex`
for the KD arm. The default `legacy` implementation and Native/TCLock arms keep
their existing objects and interfaces. The owned object is exactly 32 bytes and
occupies the same 64-byte-aligned lock slot as Native. Its caller uses the owned
outer-cookie interface with default ABI2 or opt-in ABI4, and distinct registry lock kind 3; it never
casts the object to a Linux mutex. The initial owned performance workload supports
plain c01; nested/early are available only as KD-only functional checks. RCUHT,
other body sizes and replacement of kernel-owned pipe/file mutexes are rejected.
This option names an implementation,
not a claim of performance acceptance.

The owned caller is compiled with `SC_MUTEX_OWNED=1`; the runner checks its
`mutex_implementation=owned-v1` module metadata and owned symbol imports. It
prepares the owned continuation, verifies publication identity and returned JIT
bodies, and checks object idleness after worker drain before source retirement.
New owned headers and implementation fragments are covered by the ordinary
frozen source manifest.

TCLock retains NUMA/WWJUMP and configured 1,024; zero-based jumps can execute 1,025
bodies. The shared port header currently enables NUMA even when Makefile's variable
is 0; actual ELF metadata rejects misleading off labels. Spin IRQ checks are disabled
for this IRQ-enabled task-context comparator, and batches do not truncate on
`need_resched()`. TCLock/workloads have UBSAN off; the kernel's policy is unchanged.
Mutex workers preregister one fixed-affinity context per CPU before measurement;
contexts/task refs survive complete cohort drain. KD mutex waiters retain migration
pins and reserved stacks while sleeping after bounded polling.
See [TCLock scope](../../tclock_backend/README.md) and
[lock protocols](../../docs/design/lock_protocols.md).

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
`--mutex-acceptance adaptive-performance` also scores correct, drained local
execution chosen by the selected policy. Zero-JIT legacy samples retain
the `ADAPTIVE_NATIVE` classification; they do not pass JIT acceptance.
Functional checks always retain JIT-required acceptance.

For `owned-v1`, self-execution is classified `KD_SELF`; adaptive acceptance with
zero returned bodies is `ADAPTIVE_SELF`, never `ADAPTIVE_NATIVE` or a JIT pass.
`--mutex-routing self` is an owned-only diagnostic control requiring zero JIT
bodies and excluded from scores. It keeps the owned lock protocol active.
`--mutex-routing native` is prohibited for an owned object. The owned threshold
uses the separate `owned_mutex_entry_ratio_limit` provider parameter; changing
the legacy threshold with an owned run is rejected. Results and acceptance
screens keep implementation, queue policy and threshold identities separate.
Owned records identify `owned_queue_policy=finite_fifo` by default. The opt-in
`--owned-mutex-refill` experiment records `bounded_fifo_refill` and verifies its
read-only provider parameter. It takes another FIFO snapshot only after consuming
the previous one, within the same total body cap and without crossing a SELF or
handoff boundary. These labels describe batch refilling. NUMA reordering is
controlled separately by `--owned-mutex-numa`, which defaults to off regardless
of the shared provider's NUMA build switch. Records retain both
`owned_mutex_numa` and `owned_mutex_origin_spin`; compare each policy separately.

`--profile-lock` observes the matching admission and batch symbols for each
implementation. Owned runs also retain probes on Linux lock/unlock and require
zero calls with the owned target address. Its 100 us owner samples are not exact
ownership streaks; probe overhead changes throughput and contention, so these
runs never score. Separate PMU/flat-PC diagnostics remain available. Owned
wait observations count delegated-result parks and wakes; their third field
is zero because there is no legacy gate, and they do not claim a count of all
self-execution waits.

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

That broader through-28 threshold study is distinct from the accepted ABI4/reuse-32
[1–8 auditor](mutex_local_study.py) and the descriptive 22-count full-grid report.
The latter has one three-round block and does not promote a default or supply
the two additional confirmations required for broader parity acceptance.

Timed peak selection requires all workers to progress in the full cohort window.
Keep whole-run per-worker and node shares too, especially cohorts with unequal
NUMA membership (24 threads in the original 40-vCPU setup). A bounded batch and
positive observed counts do not prove starvation freedom.

[Performance status](../../docs/PERFORMANCE.md) summarizes the latest frozen
comparison and remaining gaps. The [machine result indexes](../results/README.md)
retain older reports, source identities and rejected trials. The
[validation index](../../docs/VALIDATION.md) separates current owned protocol
checks, the full-grid audit and historical blocking-only receipts.
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

Owned mutex c01 additionally supports `--scenario nested` and `--scenario early`
with `run_mutex.py --mutex-implementation owned-v1 --functional --backends kdlock
--repeats 1`. These build a separate aligned inner owned mutex. Nested uses
ordinary owned controls and early uses the direct clobber interface. Nested releases the inner lock
first; early alternates LIFO and outer-before-inner release using protected
counter parity. LIFO callers supply executors while native early unlocks decline
combining with B still held. Acceptance requires a delegated early-release
observation and verifies both objects are idle. Add `--owned-mutex-force-full`
to resume one checked post-control continuation on its logical caller, requiring
both physical-owner ACKs. This uses `owned_mutex_native_after_control`; the
older `jit_hl_fault_after_known_call` intentionally fabricates invalid exits
and must not be used as a valid FULL continuation probe. Legacy mutex scenarios and all
timed nested/early runs are rejected. Keep these runs in separate output directories.

Functional runs require actual JIT for
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
For owned-v1 it probes the owned admission and batch functions, records
`lock_profile.owned.self_calls`, `self_slow` and `self_wait`, and still watches the Linux
mutex entry/slowpath/unlock functions at the target address. All three Linux
target counts and both missed-probe totals must be zero. SELF call counts cover
the out-of-line refusal path; successful outer inline acquisitions bypass that
probe. Batch packet counts use the owned completion counter and remain distinct
from the independently measured returned JIT bodies.
[Tests](../../tests/README.md) selects affected fixtures and source/assembly audits.

## Shutdown

Join workers → verify data/lock/queue/frame drain → stop translators → retire KD
sources → unload workload → unload backend/provider. Clear TCLock's diagnostic
`target_lock` before freeing its workload storage. Do not force unload on EBUSY,
reuse old RIP-keyed JIT after replacing only a source module, or alter frozen inputs.
For Native and legacy KD mutex workloads, the worker-drain ioctl also requires
a zero original owner word, an empty sleeping wait list and an empty configured
Linux OSQ. Owned-v1 instead calls `kd_owned_mutex_is_idle` on its distinct owner,
wait list and private OSQ; functional scenarios check both owned objects.
These checks run only after workers return while holding the snapshot gate.

## Owned preflight experiment

Owned callers use capture-first entry by default: a failed inline probe enters
the clobber boundary, then records the attempt and checks admission. There is no
C-gate call or added runtime policy load on this default caller path.
`--owned-mutex-preflight` compiles the experimental ordinary C-ABI gate after the
first failed outer probe. It makes exactly one entry/contention observation,
then attempts physical SELF acquisition before reserving delegation resources.
`--owned-mutex-preflight-spins 0` disables the additional optimistic polling;
the explicitly enabled C gate remains active, including its cold SELF path.
Compare this control separately with the default capture-first build. The bounded
poll loop normally never joins an occupied OSQ. `--owned-mutex-preflight-queue`
allows joining with the same polling budget and records a separate boolean
policy. OSQ cancellation and normal release can still wait for a concurrently
arriving successor to finish linking; neither policy guarantees a wall-time bound. All owned paths use KD's
private mutex core and never pass the owned object to Linux mutex operations.
An admitted BUSY gate result permits capture only. The prepared entry checks
delegation eligibility before any references or request resources, avoiding a
duplicate task-state lookup in the gate.

New samples record `owned_preflight_policy=capture_first` or `c_abi_v1`, the
explicit `owned_mutex_preflight` boolean, exact spin budget and
`owned_mutex_preflight_queue`. Positive budgets and queueing require the explicit
gate flag; queueing also requires a positive budget. Native/TCLock controls
always record false. The workload's module metadata and imported capture symbol
must match the plan. Historical implicit `c_abi_v1` records lacking the boolean
remain auditable and separate from both new caller choices. Both provider entry
symbols are available, but a prepared entry must only follow the C gate's false
return; the original endpoint performs its own one-time observation. Replace
provider, caller and JIT session together when changing this interface.
Summaries and admission-study checks separate these from earlier records and
from other budgets. The broad-clobber continuation remains ABI2, so skipping
capture does not eliminate the enclosing function's compiler callee-save spills.
The [c01 protocol study](../results/10.176.26.71/bench/mutex_owned/20261014-hybrid/README.md)
records the measured gains and remaining gaps. No preflight policy passed its
complete performance acceptance; these controls remain opt-in.

## Owned Linux-local-first study

`--mutex-implementation owned-v1 --owned-mutex-cabi` selects internal ABI4 with
ordinary C register preservation. Its owner-word leaf CAS and private Linux
OSQ path execute locally before KD admission, task/registry work or capture.
The optimistic loop has no fixed poll budget; scheduling and owner state decide
when it stops. Only failure after any required rescheduling and a final exact
retry permits late capture. ABI4 does not update ABI2's heat/entry-ratio history.
Source or resource refusal then commits to SELF waiting without another initial
optimistic pass. No owned target is passed to a Linux mutex API.

The 32-byte object geometry and outer acquisition cookie are unchanged. A
nonzero return identifies physical ownership; a zero delegated cookie retains
the FULL owner-ACK path. Both owned caller ABIs now use guarded owner release:
SELF-only release can clear ownership before acquiring `wait_lock`, while a
published or detached DELEGATE retains the guard until its queue is drained.
ABI2 remains the default caller, and the benchmark's implementation default
remains `legacy`. ABI4 is incompatible with the ABI2 preflight switches.

`--owned-mutex-reuse-spins 0` preserves Linux retry timing. Experimental values
8, 32 and 128 permit one short grace after an unflagged release per OSQ turn,
to test whether the releasing owner can reuse the protected cacheline. First
waiters and flagged releases bypass it; rescheduling interrupts it. The read-only
provider value is recorded and checked for every sample. Positive values require
ABI4 in this runner, and different values must not be pooled.

Records distinguish `owned_acquire_policy=linux_local_first` from ABI2
`capture_admission`, and record `owned_release_policy=guarded_owner_release`.
The provider must report `owned_mutex_protocol=linux_local_first_v1`; the old
native-first budget and optional early-release parameters are absent. Existing
caller ABI, preparation, ELF imports and source checks still apply.
`--profile-lock` automatically adds the ABI4 `local_first` diagnostic probe and
stores a separate `owned_local_first_profile` record. Its acquired/failed counts
come from the fused gate's full-width acquisition cookie, and missed returns must be zero. These
instrumented sessions remain excluded from scores.

The separate [local study auditor](mutex_local_study.py) covers c01 with the
frozen 64-round post-work header and **1–8 workers only**. Use
`--mutex-acceptance adaptive-performance`, 48,000 warmup operations per worker,
two-second measurement and the existing 300 ms warmed-peak rules. Each candidate
gets three rounds in alternating backend order, paired with fresh Native runs.
A selected candidate needs two additional fresh three-round blocks with the
same source and policy; each block must independently reach 97% of Native for
both median whole-run throughput and best valid warmed peak at every count.
Retain all samples, worker progress/shares, CPU cost, correctness and drain.
KD_SELF and returned JIT remain distinct classifications; this scoped study has
no minimum JIT share or higher-thread gate. It makes no claim above eight workers
or for other mutex workloads. Implementation and a passing screen alone do not
establish accepted parity.

The [2026-10-14 study](../results/10.176.26.71/bench/mutex_owned/20261014-linux-local/README.md)
passes the full screen and both confirmations with ABI4 and reuse bound 32.
Reproduce the accepted profile in the verified recovery guest with a new output:

```sh
python3 bench/tclock_compare/run_mutex.py \
  --mutex-implementation owned-v1 --owned-mutex-cabi --owned-mutex-reuse-spins 32 \
  --mutex-acceptance adaptive-performance --kd-provider-ubsan off \
  --cachelines 1 --threads 1 2 3 4 5 6 7 8 --duration-ms 2000 \
  --collector-cpu 63 --backends native kdlock --repeats 3 --output NEW_OUTPUT
```

Audit frozen run directories without executing workloads:

```sh
python3 bench/tclock_compare/mutex_local_study.py --raw RAWROOT \
  --baseline REL_BASELINE --screen REL_SCREEN \
  --confirmations REL_BLOCK1 REL_BLOCK2 --out REPORTDIR
```

Paths for each block are relative to `RAWROOT`. Omit screen/confirmation options
for a baseline-only receipt; it cannot report accepted parity.
