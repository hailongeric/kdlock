# Best-case nano profiles and controls

This is stage 1 of the [project roadmap](../../docs/ROADMAP.md): establish the
mechanism's favorable regime and retain its costs elsewhere. Gains here motivate
the scoped MM experiments; they do not predict gains from local mmap locking or
prove final kernel replacement performance.

[`best_case.py`](best_case.py) runs small resident workloads for mutexes and
sleeping reader/writer semaphores (rwsems). It is designed to expose favorable
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
TCLock remained faster in those strongest read-mostly rwsem examples. The resident
list mutex result also motivates testing a larger shared footprint while removing
its traversal and application logic.

The new [one-cacheline mutex measurement](../results/10.176.26.71/bench/nano-pair-20261026/mutex-minimal/)
is retained as a counterexample: in one exploratory round at 60 workers, KD
achieved 5.003 Mops/s versus Native's 5.586 Mops/s, despite 97.3% of writes
returning from JIT bodies. A minimal body and
successful delegation alone do not guarantee a win. The `mutex-locality` profile
therefore tests a separate hypothesis: repeated ownership of a larger resident
working set can amortize synchronization and data movement. Its results must
remain separate from the one-cacheline control.

The [fresh matched results](../results/10.176.26.71/bench/nano-pair-20261026/README.md)
select the locality profile with **64 post-unlock rounds** as the default mutex
case. At 60 workers it reached 1.435× Native and 1.839× TCLock, with 98.20%
returned writers. At 32 workers it also beat both controls; at 8, 16 and 36 it
still lost to Native. The post4 locality control lost to Native at every
contended count. Adding outside-lock work reduced Native throughput more than
KD's; it did not make KD execute faster. These are exploratory, single-round
observations, not a universal optimum or an isolated causal cost breakdown.

A subsequent [fresh mutex-only comparison](../results/10.176.26.71/bench/nano-mutex-20261026/README.md)
runs both implemented mutex profiles from the committed defaults. It retains
all 36 new observations, per-profile tables and charts separately from the
selection study above; the two campaigns are not pooled into repeated means.

## Bodies and profiles

The default mutex profile, `mutex-locality`, reuses the existing
[unrolled counter payload](../../workload_modules/rwlock_bench/payload.h): 16
64-bit counters, each padded and aligned to its own 64-byte cacheline. The total
payload footprint is 1,024 bytes. Every operation increments all 16 counters
under one mutex. There is no list traversal, hashing, allocation or helper call.
The loop below is pseudocode; the actual body expands to 16 explicit updates.

```c
mutex_lock(lock);
for (i = 0; i < 16; ++i)
    WRITE_ONCE(counter[i].value, READ_ONCE(counter[i].value) + 1);
mutex_unlock(lock);
```

This profile uses the existing cacheline workload ID 0 with `lines=16`; it does
not change the payload or lock protocol. Native, KD and TCLock perform all 16
updates, and every counter must advance by the exact completed write count.

The two rwsem profiles and optional minimal `mutex` control use a
[two-word payload](../../workload_modules/rwlock_bench/nano_payload.h): one
64-byte-aligned record occupying exactly one 64-byte cacheline. Its two adjacent
64-bit fields start at zero. The recorded `lines=2` counts logical words for this
workload, not two cachelines. Workload ID 6 distinguishes it from existing padded
cacheline, list and hash payloads.

```c
/* Writer: protected load plus two stores. */
write_lock(lock);
next = READ_ONCE(record.sequence) + 1;
WRITE_ONCE(record.sequence, next);
WRITE_ONCE(record.copy, next);
write_unlock(lock);

/* Reader: a caller-local consistency result. */
read_lock(lock);
sequence = READ_ONCE(record.sequence);
copy = READ_ONCE(record.copy);
read_unlock(lock);
read_error = sequence != copy;
```

Within each profile, Native, KD and TCLock compile the same business body,
operation mix and register-only post-work. The two-word record has no linked-list
traversal, hashing, allocation, helper call, user-memory access or shared
per-operation statistics.
The writer counter gives an exact final oracle; the duplicate field lets readers
detect inconsistent snapshots. Lock storage is separate from the payload.

| Profile | Default | Lock, footprint and operation mix | KD execution scope |
| --- | --- | --- | --- |
| `mutex-locality` | Yes | 100% exclusive updates of 16 counters across 16 cachelines | Public `kd_mutex_lock/unlock` through ABI2; returned-body evidence establishes delegation. |
| `rwsem-read` | Yes | 99% reads, 1% writes of the 64-byte record | Readers execute locally. Explicit outer writers reserve a reader-free phase and may delegate. |
| `rwsem-mixed` | Yes | 80% reads, 20% writes of the 64-byte record | A separate writer-interference control using the same reader and outer-writer interfaces. |
| `mutex` | No | 100% exclusive updates of the 64-byte record | The same public ABI2 shell, retained as the minimal-body counterexample. |

All workers mix their own operations using the existing deterministic phase-17
schedule; these are not dedicated reader and writer thread pools. The mutex
profiles accept only 100% writes. Mutex readers would require a separately
defined and measured call shell.

The runner defaults to counts `1 8 16 32 36 60`, a two-second timed interval and
one round per point. After each unlock, `mutex-locality` performs 64 dependent
multiply/add rounds; the minimal mutex and both rwsem profiles perform four.
Workers use CPUs `0..N-1`; the collector uses CPU 63. The 36- and 60-worker
cohorts cross the 32-CPU NUMA boundary. The default three-profile, three-backend
screen has 54 measured points. One round supplies no repeat-variability estimate;
`--repeats 3` selects a separately recorded repeated comparison.

Each worker enters one ioctl for the whole operation loop. This isolates the
small protected body using the established resident-workload harness. The
motivating real API benchmarks instead execute one syscall per operation,
including file/VFS handling, redirection and result validation outside the lock.
Their throughput ratios cannot be transferred to this nano workload. The
locality mutex now matches the historical synthetic post64 setting, but its
body, source and harness remain separately identified. Keep the post4 controls
and all call-shell identities separate in reports.

## Commands and execution environment

Source edits and static plan inspection belong on `380G10`. All builds,
functional checks, module activity and timing run only in the recovery VM at
`root@10.176.26.71:2222`. Follow [VM operations](../../docs/operations/VM.md),
including idle synchronization, the pinned Python environment, the unchanged
`6.1.159-kdclobber2` identity and actual confirmation of the recovery snapshot.
Environment variables alone do not prove snapshot availability.

Static preview, without creating outputs or executing workloads:

```sh
python3 bench/nano/best_case.py --plan-only --output /tmp/nano-plan-preview
```

The remaining commands run in `/root/host_fs/kdlock` inside the verified VM.
Use a new external evidence directory for every invocation. After verifying the
snapshot through the host monitor, set the recorded environment:

```sh
export PATH=/root/kdlock-translation-venv-20261019/bin:$PATH
export LC_ALL=C
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z

# Fixed-iteration functional checks; no performance scores.
python3 bench/nano/best_case.py --functional --threads 1 8 \
  --output /root/kdlock-evidence/10.176.26.71/tests/nano-functional-NEW

# Default six-count, three-profile, one-round comparison.
python3 bench/nano/best_case.py \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-best-case-NEW

# Separate KD local control at counts present in the default comparison.
python3 bench/nano/best_case.py --backends kdlock --delegate off \
  --threads 1 16 60 \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-local-control-NEW
```

`--profiles mutex-locality rwsem-read` selects the two principal profiles; keep
`rwsem-mixed` as a separately identified writer-interference control. Use
`--profiles mutex` to reproduce the one-cacheline control, or explicitly select
all four profiles to include it in a new campaign. Changing `--post-work-rounds`
overrides every selected profile's default, changes the workload and requires
matched arms and a distinct result identity. In particular, `--profiles
mutex-locality --post-work-rounds 4` reproduces the tighter-arrival control.

## Profiling the mutex profiles

[`profile.py`](profile.py) collects separate, unscored diagnostics for `mutex`
and `mutex-locality`, preserving their four- and 64-round post-work settings.
It uses one round per point. Run it only in the verified recovery VM under the
environment above, after idle synchronization and the relevant checks. Set
`NANO_PROFILE_SOURCE_COMMIT` to the full reviewed source-host commit recorded in
the synchronization receipt; source and binary hashes are also retained.

```sh
# Requested PMU/software counters for Native and KD.
python3 bench/nano/profile.py --mode stat --threads 16 36 60 \
  --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-stat-NEW

# Flat instruction-pointer samples for Native and KD.
python3 bench/nano/profile.py --mode record --threads 16 36 60 --frequency 499 \
  --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-record-NEW

# KD batch accounting; compiled diagnostics enabled, with no perf process.
python3 bench/nano/profile.py --mode batch --threads 16 36 60 \
  --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-batch-NEW
```

Preparation, translation and warmup finish before the measured client starts.
The `stat` and `record` modes wrap only that client and its inherited threads;
their raw scope includes client startup and collection. The sample report
separately selects `rb_worker` samples during the settled interval when all
workers are active, using sampled periods for attribution. It retains unknown
and generated-image addresses and uses no borrowed-stack unwinding. Requested
counter availability is checked before the workload; unsupported or uncounted
events are failures, not zero measurements.

The `batch` mode builds KD with `KDLOCK_MUTEX_DIAGNOSTICS=1`; ordinary builds and
the two perf modes keep it compiled out. Quiescent snapshots after warmup and
after joined measurement produce deltas for batch lengths, exit reasons,
deferred requests and local/remote JIT service. Histogram bin zero represents
zero; bin `i > 0` represents `[2^(i-1), 2^i-1]`. The validator checks exact
accounting identities and requires the batch `jit_completed` delta to equal
the returned-body completion-counter delta. Dispatch-node locality does not
prove that a sleepable body stayed on that node. These observations never
replace exact ownership, ACK, source/frame retirement or final drain checks.

Both perf collection and compiled counters perturb execution. Keep their rates
separate from uninstrumented throughput and do not infer speedups from
instrumented rates. All three modes retain `score_eligible=false`; a published
image alone still does not establish a returned JIT body.

Both launchers accept explicit mutex policy experiments. Change one limit per
campaign and retain a matched default control; for example:

```sh
# Uninstrumented comparison: total cap 4096, NUMA boundary still 256.
python3 bench/nano/best_case.py --profiles mutex mutex-locality \
  --threads 16 36 60 --mutex-batch-limit 4096 \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-cap4096-NEW

# Separate diagnostic campaign: boundary 768, total cap still 1024.
python3 bench/nano/profile.py --mode batch --threads 16 36 60 \
  --mutex-numa-boundary 768 --source-commit "$NANO_PROFILE_SOURCE_COMMIT" \
  --output /root/kdlock-evidence/10.176.26.71/bench/nano-boundary768-batch-NEW
```

Either option works with either launcher, including `stat` and `record` modes.
Defaults remain total cap 1024 and NUMA boundary 256. Each accepts `1..32767`
independently; a smaller total cap can stop service before the NUMA boundary.
Nondefault policies require mutex-only profiles, KD among the selected backends
and public delegation enabled. Plans and receipts record both values, and the
runner verifies the provider's `mutex_batch` and `mutex_numa_boundary` modinfo.
Keep source, policy and diagnostic settings as separate result identities.
The deferred-handoff threshold remains eight and the scan budget remains 64.
A larger same-node cohort can delay remote service; bounded body counts are not
a wall-time fairness bound. These options make no performance-gain claim.

For changes to this driver or batch diagnostics, run the basic checks plus
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
costs. They are not a pure isolated switch for JIT execution. Compare their
results as mechanism evidence with those limits stated.

The existing [reader/writer runner](../rwlock_compare/README.md) validates every
worker's CPU, complete operations, deterministic read/write counts, post-work
checksum and zero reader errors. For the two-word record, before/after snapshots
require both word deltas to equal the exact sum of completed writes and all
fourteen unused fields to remain zero. The locality profile requires all 16
counter deltas to equal that same exact write count. Native and local controls
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

[`run.py`](run.py) and its existing resume/report helpers preserve the older
broad nano campaign: four lock families, padded cachelines, RCUHT, resident lists
and historical prefetch/size variants, generally with three rounds. Its frozen
plans and measurements remain source-specific evidence. Use `best_case.py` for
the current focused profiles. Reusing the old counter body with a new mutex
shell and post-work setting does not rewrite or fill gaps in historical results.
