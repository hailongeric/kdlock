# Best-case nano profiles and controls

This is stage 1 of the [project roadmap](../../docs/ROADMAP.md): establish the
mechanism's favorable regime and retain its costs elsewhere. Gains here motivate
the scoped MM experiments; they do not predict gains from local mmap locking or
prove final kernel replacement performance.

[`best_case.py`](best_case.py) runs ten small resident profiles for mutexes,
sleeping reader/writer semaphores (rwsems) and reader/writer spinlocks (rwlocks).
It is designed to expose favorable
conditions for KD: resident data, helper-free critical sections, repeated access
and fixed-affinity callers. “Best case” describes the intended scope; matched
measurements determine whether KD actually wins. It is not a claim about
arbitrary kernel workloads.

The October 26 [catalog analysis](../results/10.176.26.71/bench/catalog-single-20261026/PERFORMANCE_ANALYSIS.md)
motivates two distinct mechanisms. The strongest measured mutex examples include
`seek-set` and pipe-capacity queries: small bounded updates or loads with high
returned-JIT shares under contention. The strongest rwsem gains over Native came
from 1%-write workloads that recorded **NO_JIT**. Those results motivate a local
reader/admission profile, not an explanation based on delegated readers.
TCLock remained faster in those strongest read-mostly rwsem examples. The larger
counter profile separately tests a shared footprint of sixteen cachelines.

The earlier [two-word mutex measurement](../results/10.176.26.71/bench/nano-pair-20261026/mutex-minimal/)
is retained as a counterexample: in one exploratory round at 60 workers, KD
achieved 5.003 Mops/s versus Native's 5.586 Mops/s, despite 97.3% of writes
returning from JIT bodies. A minimal body and
successful delegation alone do not guarantee a win. Its frozen source and
four-round post-work setting remain historical evidence; the two-word profile
is no longer selected or accepted by the active launcher. The previous
[post64 locality selection](../results/10.176.26.71/bench/nano-pair-20261026/README.md)
and [fresh 36-point comparison](../results/10.176.26.71/bench/nano-mutex-20261026/README.md)
retain their original bodies, defaults and mixed Native results.

The current mutex defaults are **`mutex-throughput` (one padded counter)** and
**`mutex-locality` (sixteen padded counters)**, both with **256 post-unlock
rounds**. The same-source [54-point factor study](../results/10.176.26.71/bench/mutex-profile-20261026/factor-grid/README.md)
motivates this selection:

| Selected body, post256 | KD Mops/s at 16 / 36 / 60 workers | KD / Native at 16 / 36 / 60 |
|:---|:---|:---|
| One counter, 64 bytes | 5.987 / 4.927 / 4.892 | 1.920 / 2.327 / 3.328 |
| Sixteen counters, 1024 bytes | 4.783 / 3.796 / 4.033 | 1.540 / 1.985 / 3.056 |

Both won every measured coordinate above. One counter gives the simplest body
and highest observed KD rate at 36/60; sixteen counters retain a distinct
resident-footprint case. Four counters added little distinct coverage and
remain a separately measured factor. Longer post-work mainly reduced Native's
rate while KD's stayed similar or fell, rather than increasing KD's absolute
throughput. [Completed-work fairness](../results/10.176.26.71/bench/mutex-profile-20261026/factor-grid/FAIRNESS.md)
supports the observed change in contention but does not prove rapid Native
reacquisition or actual overlap between producer post-work and combiner service.

That selection study used source `b0d12ba8`, the **1024/256 policy**, only
16/36/60 workers, and Native/KD controls. The user then promoted the
provider default to **total cap 1024 / NUMA boundary 768** after the
[policy experiment](../results/10.176.26.71/bench/mutex-profile-20261026/OPTIMIZATION.md):
four 36/60-worker observations improved 8.41–15.95%, while both 16-worker bodies
regressed. The subsequent full-grid measurements at 768 have their own source,
policy and TCLock comparisons; the earlier factor results do not establish those outcomes.
Promotion records the user's choice from exploratory evidence, not a universal
optimum or guaranteed improvement. On October 28 the user selected KD mutex
**1024/1024**, removing the earlier count-based local cutoff; existing measured
results retain their original limits. KD spin retains its 1024-body limit.
The rwsem/rwlock profiles apply the same one-/sixteen-counter, post256 selection at 1% and 20% writes. That is an explicit
new workload choice, not a measured rwsem/rwlock optimum or a continuation of the
earlier two-word/post4 results.

The [completed promoted-default campaign](../results/10.176.26.71/bench/nano-mutex-promoted-20261026/README.md)
at `e5b7f84c` publishes both full-grid tables and charts: 126 measurements and
126 warmups passed exact replay and drain. It retains the four-worker locality
loss to Native, low-count NO_JIT results and the one-counter two-worker near tie
with TCLock. The campaign remains exploratory, with one observation per point.

The [October 27 rerun at fixed 2.0 GHz](../results/10.176.26.71/bench/nano-mutex-fixedfreq-20261027/README.md)
completed the same 126 timings and warmups with identical source bytes and
workload plans. All passed exact replay and drain. All 64 host CPU policies use
the performance governor, equal 2.0 GHz minimum/maximum limits and disabled
turbo; separate APERF/MPERF telemetry records effective frequency. The earlier
large single-worker gap disappeared: Native/TCLock/KD measured
1.925/1.929/1.923 Mops/s for one counter and 1.927/1.926/1.919 for sixteen.
At 60 workers, KD measured 4.895 and 3.831 Mops/s respectively, or 3.065 and
2.643 times Native. The host remains pinned at the user's request. Keep these
single-round exploratory results separate from the earlier ondemand rates;
strict host task-membership qualification remains failed.

## Expanded fixed-frequency measurements

The [full October 27 catalog](../results/10.176.26.71/bench/catalog-fixedfreq-20261027/README.md)
at `a9aeb280` completed all ten nano profiles: **630 measurements and 630
warmups**, with exact replay and drain. Each coordinate has one round at the
fixed 2.0 GHz host target. The [performance guide](../../docs/PERFORMANCE.md)
contains the ten-profile comparison and returned-write shares; each workload's
report contains its full worker grid and chart.

At 60 workers, only the two mutex profiles exceed both Native and TCLock.
Every rwsem/rwlock nano profile remains below TCLock; the sixteen-counter,
1%-write rwlock also loses to Native at every cross-NUMA count. The two
1%-write rwsem profiles record NO_JIT throughout, so their gains over Native
are local-path results. These outcomes bound the favorable regime; selection
alone does not establish a best case for every lock family. Keep this campaign
separate from the earlier two-profile and historical two-word/post4 studies.

## Bodies and profiles

All active profiles reuse the existing
[unrolled counter payload](../../workload_modules/rwlock_bench/payload.h): one or
sixteen 64-bit counters, each padded and aligned to its own 64-byte cacheline.
Their total payload footprints are 64 and 1,024 bytes. Every writer increments
every selected counter under one exclusive acquisition. Rwsem/rwlock readers
compare every selected counter with the first while holding shared ownership;
the one-counter reader reloads its sole counter. Reader results stay caller-local.
There is no list traversal, hashing, allocation or helper call.
The loop below is pseudocode; the actual body expands to explicit updates.

```c
write_lock(lock);
for (i = 0; i < selected_counters; ++i)
    WRITE_ONCE(counter[i].value, READ_ONCE(counter[i].value) + 1);
write_unlock(lock);
```

These profiles use the existing cacheline workload ID 0 with `lines=1` or
`lines=16`; they do not add a payload or lock protocol. Native, KD and TCLock
perform the same selected updates, and every counter must advance by the exact
completed write count. The one-counter body is distinct from the historical
two-word body, even though both occupy one cacheline. Lock storage is separate
from the payload. Within each profile, Native, KD and TCLock compile the same
business body, operation mix and register-only post-work.

All ten profiles below are selected by default and use post256.

| Profile | Lock | Counters / footprint | Writes |
| --- | --- | --- | ---: |
| `mutex-throughput` | Mutex | 1 / 64 bytes | 100% |
| `mutex-locality` | Mutex | 16 / 1,024 bytes | 100% |
| `rwsem-throughput-read` | Rwsem | 1 / 64 bytes | 1% |
| `rwsem-throughput-mixed` | Rwsem | 1 / 64 bytes | 20% |
| `rwsem-locality-read` | Rwsem | 16 / 1,024 bytes | 1% |
| `rwsem-locality-mixed` | Rwsem | 16 / 1,024 bytes | 20% |
| `rwlock-throughput-read` | Rwlock | 1 / 64 bytes | 1% |
| `rwlock-throughput-mixed` | Rwlock | 1 / 64 bytes | 20% |
| `rwlock-locality-read` | Rwlock | 16 / 1,024 bytes | 1% |
| `rwlock-locality-mixed` | Rwlock | 16 / 1,024 bytes | 20% |

KD mutex uses public `kd_mutex_lock/unlock` through ABI2. Rwsem readers execute
locally; explicitly prepared ordinary writers reserve a reader-free phase and may
delegate. The current `public-prepared-direct-abi2` shell replaces the historical
OUTER/cookie shell; keep measurements from these source versions separate.
Rwlock readers also execute locally; direct writer pairs admit eligible
exclusive bodies. Returned-body evidence, not publication alone, establishes
successful delegation in each family. The 20%-write profiles retain distinct
writer-interference cases rather than dedicated writer threads.

All workers mix their own operations using the existing deterministic phase-17
schedule; these are not dedicated reader and writer thread pools. The mutex
profiles accept only 100% writes. Mutex readers would require a separately
defined and measured call shell.

The runner defaults to 21 counts: `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`,
a two-second timed interval and one round per point. After each unlock,
every active profile performs 256 dependent multiply/add rounds.
Workers use CPUs `0..N-1`; the collector uses CPU 63. Counts above 32 cross the
32-CPU NUMA boundary. The default
ten-profile, three-backend matrix has 630 planned measured points. Selecting only the
two favorable mutex profiles gives 126 points. One round supplies no repeat-variability estimate;
`--repeats 3` selects a separately recorded repeated comparison.

Each worker enters one ioctl for the whole operation loop. This isolates the
small protected body using the established resident-workload harness. The
motivating real API benchmarks instead execute one syscall per operation,
including file/VFS handling, redirection and result validation outside the lock.
Their throughput ratios cannot be transferred to this nano workload. The
selected mutex profiles use post256, separately from the historical post64
synthetic setting. Keep body, source, policy, post-work and call-shell identities
separate in reports, including historical post4 controls. The original c01/c08
micro configurations remain in the full catalog with their existing post64
(spin/mutex) or post4 (rwlock/rwsem) settings. They are not replaced by these
ten profiles. The requested full catalog adds the separate API and MM suites;
`best_case.py` alone runs only the nano matrix.

## Commands and execution environment

Source edits and static plan inspection belong on `380G10`. All builds,
functional checks, module activity and timing run only in the recovery VM at
`root@10.176.26.71:2222`. Follow [VM operations](../../docs/operations/VM.md),
including idle synchronization, the pinned Python environment, the
`7.0.0-38-kdlock1` schema-2 identity and actual confirmation of a recovery snapshot
of the new platform. The [port record](../results/10.176.26.71/tests/linux70-port-20261027/README.md)
records current validation limits; existing nano numbers retain their Linux 6.1 scope.
Environment variables alone do not prove snapshot availability.

Static preview, without creating outputs or executing workloads:

```sh
python3 bench/nano/best_case.py --plan-only --output /tmp/nano-plan-preview
```

The remaining commands run in `/root/host_fs/kdlock` inside the verified VM.
Use a new external evidence directory for every invocation. After verifying the
snapshot through the host monitor, set the recorded environment:

```sh
export PATH=/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin:$PATH
export LC_ALL=C
export KDLOCK_RECOVERY_CONFIRMED=1
: "${KDLOCK_SNAPSHOT_TAG:?Set the exact new-platform tag verified in the monitor}"

# Fixed-iteration functional checks; no performance scores.
python3 bench/nano/best_case.py --functional --threads 1 8 \
  --output /root/kdlock-evidence/10.176.26.71/tests/nano-functional-NEW

# All ten active profiles, full grid, three backends, one round (630 points).
python3 bench/nano/best_case.py \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-catalog-NEW

# A separate two-mutex-profile comparison (126 points).
python3 bench/nano/best_case.py --profiles mutex-throughput mutex-locality \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-best-case-NEW

# Separate KD local control at counts present in the default comparison.
python3 bench/nano/best_case.py --backends kdlock --delegate off \
  --threads 1 16 60 \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-local-control-NEW
```

Without `--profiles`, the launcher selects all ten rows in the active table.
The old `mutex`, `rwsem-read` and `rwsem-mixed` choices are removed; consult their
frozen historical runners when interpreting existing evidence. Changing `--post-work-rounds`
overrides every selected profile's default, changes the workload and requires
matched arms and a distinct result identity. In particular, `--profiles
mutex-locality --post-work-rounds 4` selects the tighter-arrival body. Use
`--post-work-rounds 64` for the former locality spacing, and record the provider
policy explicitly when comparing with its historical 256-boundary measurements.

## Unscored mutex diagnostics

[`profile.py`](profile.py) selects the `c01` body (`mutex-throughput`, one padded
counter) and the `c16` body (`mutex-locality`, sixteen padded counters), preserving
post256 and one round per point. It uses the shared Linux 7 schema-2 identity
verification and recovery requirements above. `--kernel-source` names the separate
build directory; `--kernel-baseline` names its captured bundle, with the same defaults
as the ordinary runner. Thread selections are `16 20 32 36 60`; the default remains
`16 36 60`. Set `NANO_PROFILE_SOURCE_COMMIT` to the full reviewed source-host commit;
the runner also retains exact source and binary hashes.

The pin diagnostics and updated runner are a source candidate until their focused
VM checks pass. These commands do not establish validation or measurements. Existing
Linux 6.1 diagnostic evidence retains its original kernel and source identity.
For perf modes, supply a separately verified Linux 7-capable tool through `--perf`;
the retained default path identifies the historical tool and is not evidence of
current PMU support. Compiled batch and pin modes do not launch perf.

```sh
# Requested PMU/software counters for Native and KD.
python3 bench/nano/profile.py --mode stat --threads 16 36 60 --perf "$NANO_PERF" \
  --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-stat-NEW

# Flat instruction-pointer samples for Native and KD.
python3 bench/nano/profile.py --mode record --threads 16 36 60 --frequency 499 --perf "$NANO_PERF" \
  --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-record-NEW

# KD batch accounting; compiled diagnostics enabled, with no perf process.
python3 bench/nano/profile.py --mode batch --threads 16 36 60 \
  --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-batch-NEW

# KD selected-pin accounting; no perf process or TSC sampling.
python3 bench/nano/profile.py --mode pin --threads 20 36 60 \
  --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-pin-NEW

# Separate sampled-current-ACK experiment: ordered TSC on one in 64 observations.
python3 bench/nano/profile.py --mode pin --pin-tsc --threads 20 36 60 \
  --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-pin-tsc-NEW
```

Preparation, translation and warmup finish before the measured client starts.
The `stat` and `record` modes wrap only that client and its inherited threads;
their raw scope includes client startup and collection. The sample report
separately selects `rb_worker` samples during the settled interval when all
workers are active, using sampled periods for attribution. It retains unknown
and generated-image addresses and uses no borrowed-stack unwinding. Requested
counter availability is checked before the workload; unsupported or uncounted
events are failures, not zero measurements.

The `batch` mode retains `KDLOCK_MUTEX_DIAGNOSTICS=1`; ordinary builds and
the two perf modes use mode 0. Quiescent snapshots after warmup and
after joined measurement produce deltas for batch lengths, exit reasons,
deferred requests and local/remote JIT service. Histogram bin zero represents
zero; bin `i > 0` represents `[2^(i-1), 2^i-1]`. The validator checks exact
accounting identities and requires the batch `jit_completed` delta to equal
the returned-body completion-counter delta. Dispatch-node locality does not
prove that a sleepable body stayed on that node. These observations never
replace exact ownership, ACK, source/frame retirement or final drain checks.

The KD-only `pin` mode uses `KDLOCK_MUTEX_DIAGNOSTICS=2`, replacing batch
observations to stay within the reserved per-CPU storage budget. It reads
`mutex_pin_stats` after warmup and after the joined measurement, saving
`pin-before.json`, `pin-after.json` and `pin-delta.json`. Schema 1 binds compiled
mode 2, a four-request window, both selected mutex policy limits and the TSC
sample shift. The seventeen counters retain selections, requested/consumed/cancelled
pins, drain calls, current and cancellation ACK behavior, batch-resume calls and samples.
`full_resumes` counts calls to `kd_exe_mutex_batch_resume`, including checked
pre-entry refusals; it does not assert that a FULL service or body returned.
The two five-bin histograms record exact occupancy `0..4` before and after selection;
the ten refill-stop reasons account for every selection.

The validator requires both occupancy totals and refill-stop totals to equal
selections; requested pins must equal consumed plus cancelled pins at quiescence.
Cancelled pins must equal their immediate plus stalled ACK counts. ACK-loop totals
must cover stalled ACKs and must be zero when none stalled. Nonempty drains cannot
exceed drain calls, and drains retaining the current pin cannot exceed nonempty
drains. These counters describe pin lifetimes: consumed pins are not a count of
returned JIT bodies, and neither a counter identity nor a histogram proves drain.
The unchanged workload oracle, physical ownership/ACK checks and source/frame
retirement remain required before unloading or advancing to another case.

TSC sampling is off by default (`KDLOCK_MUTEX_PIN_TSC_SHIFT=0`), requiring zero
samples and cycles. `--pin-tsc` is valid only with `--mode pin` and selects shift 6.
It samples one in 64 current-pin ACK waits per CPU. Ordered timestamps have
explicit compiler barriers and LFENCE on both sides. The delta includes fence and
timestamp overhead, the first ACK cacheline load, and any interruptions during
the wait; zero polling iterations do not mean zero latency. Samples cannot
exceed current ACKs. Keep sampled and unsampled diagnostic runs separate.

Both perf collection and compiled counters perturb execution. Keep their rates
separate from uninstrumented throughput and do not infer speedups from
instrumented rates. All four modes retain `score_eligible=false`; a published
image alone still does not establish a returned JIT body.

The active `best_case.py` launcher and profiler accept explicit mutex policy
experiments. Change one limit per campaign and retain a matched default control:

```sh
# Uninstrumented comparison: total cap 4096, NUMA boundary still 1024.
python3 bench/nano/best_case.py --profiles mutex-throughput mutex-locality \
  --threads 16 36 60 --mutex-batch-limit 4096 \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-cap4096-NEW

# Separate batch diagnostic control; retain its policy in the result identity.
python3 bench/nano/profile.py --mode batch --threads 16 36 60 \
  --mutex-numa-boundary 256 --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-boundary256-batch-NEW
```

Both launchers accept either option. The profiler records the selection in all
four diagnostic modes.
Defaults are total cap 1024 and NUMA boundary 1024, so the locality boundary
does not shorten the default batch by count. Terminal/deferred exits remain.
Each accepts `1..32767` independently; a smaller total cap can stop service before the NUMA boundary.
Nondefault policies require mutex-only profiles, KD among the selected backends
and public delegation enabled. Plans and receipts record both values, and the
runner verifies the provider's `mutex_batch` and `mutex_numa_boundary` modinfo.
Keep source, policy and diagnostic settings as separate result identities.
The deferred-handoff threshold remains eight and the scan budget remains 64.
A larger same-node cohort can delay remote service; bounded body counts are not
a wall-time fairness bound. The user's default promotion does not extend the
measured performance claims beyond their recorded workloads and counts.

For changes to this driver or compiled diagnostics, run the basic checks plus
the directly affected drivers in the VM:

```sh
make -C tests/unit run \
  PY_TESTS="test_nano_profile.py test_mutex_policy.py test_mutex_batch_diag.py test_mutex_terminal.py test_mutex_outer_progress.py"
```

Add checks for any other execution code changed by a candidate. Full suites
require an explicit request. Missing dependencies, skips, compile/load failures
and omitted measurements remain unvalidated; retaining their evidence does not
turn them into passes.

## Interpretation and exact checks

The local control compiles callable KD mutex acquisition/unlock instead of the
public ABI2 call shell. Rwsem local control selects ordinary writer admission
instead of a shared delegated-writer reservation. These changes preserve exact
provider routing and the same payload, but also change call-shell or admission
costs. They are not a pure isolated switch for JIT execution. Rwlock local
control retains the public ABI3 writer shell and published images while setting
provider `spin_delegate=0`; no returned JIT bodies may occur. Compare controls
within each family and retain these mechanism differences.

The existing [reader/writer runner](../rwlock_compare/README.md) validates every
worker's CPU, complete operations, deterministic read/write counts, post-work
checksum and zero reader errors. Every locality profile requires all 16
counter deltas to equal the exact sum of completed writes. Every throughput profile
requires its single counter to advance by the write count and all fifteen unused
fields to remain zero. Native and local controls
must have no JIT execution. KD entries
and returned completions remain separate evidence; a published `NORMAL` image
alone does not prove a completed delegated body.

Kernel-fault checks, stopped translators, exact source/frame retirement and
final idle state remain mandatory. TCLock mutex workers register before the
operation loop; `RB_DRAIN` retires registrations only after exact task exit and
queue/stack quiescence. An `EBUSY` result retains the object and registrations.
Registration is inside the inherited whole-run interval, although outside the
operation loop; it is not claimed to be excluded from whole-run throughput.
The controller freezes source identities, uses the shared nano owner lock and
stops on failure or exhausted storage reserve. A deadline leaves the child
untouched and drain unproven; it does not permit unload or the next profile.

This launcher does not itself qualify host timing. Capture host identity,
frequency policy, NUMA placement and QEMU task membership separately. Under the
explicitly authorized exploratory policy, retain auxiliary QEMU workers pinned
to host CPU 63 and keep strict timing qualification failed. Do not present such
results as qualified repeated baselines or use a quiet later endpoint to erase
an earlier failed gate.

## Historical broad matrix

The retired focused `mutex`, `rwsem-read` and `rwsem-mixed` profiles used the
[two-word payload](../../workload_modules/rwlock_bench/nano_payload.h), workload
ID 6: two adjacent 64-bit fields in one 64-byte record, with four post-unlock
rounds. Writers stored the same incremented value in both fields; readers
compared them. Their `lines=2` counted logical words, and their oracle required
both deltas to match completed writes with fourteen unused fields zero.
The low-level payload remains available for frozen historical inputs, but the
active nano and profiling launchers no longer offer these profile names.

[`run.py`](run.py) and its existing resume/report helpers belong to the older
broad nano campaign. Retained padded-cacheline and RCUHT measurements keep
their original source and repetition identities. Use `best_case.py` for
the current focused profiles. Reusing the old counter body with a new mutex
shell and post-work setting does not rewrite or fill gaps in historical results.
