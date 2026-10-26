# Minimal shared-record nano benchmark

[`best_case.py`](best_case.py) runs a small shared-record workload for mutexes
and sleeping reader/writer semaphores (rwsems). It is designed to expose favorable
conditions for KD: a resident object, a short helper-free critical section,
repeated access to the same data and fixed-affinity callers. “Best case” describes
the workload's intended scope; fresh matched measurements determine whether KD
actually wins. It is not a claim about arbitrary kernel workloads.

The October 26 [catalog analysis](../results/10.176.26.71/bench/catalog-single-20261026/PERFORMANCE_ANALYSIS.md)
motivates two separate profiles. The strongest measured mutex examples include
`seek-set` and pipe-capacity queries: small bounded updates or loads with high
returned-JIT shares under contention. The strongest rwsem gains over Native came
from 1%-write workloads that recorded **NO_JIT**. Those results motivate a local
reader/admission profile, not an explanation based on delegated readers.
TCLock remained faster in those strongest read-mostly rwsem examples.

## Shared body and profiles

The [payload](../../workload_modules/rwlock_bench/nano_payload.h) is one
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

Native, KD and TCLock compile the same business body, operation mix and
register-only post-work. The record has no linked-list traversal, hashing,
allocation, helper call, user-memory access or shared per-operation statistics.
The writer counter gives an exact final oracle; the duplicate field lets readers
detect inconsistent snapshots. Lock storage is separate from the payload.

| Profile | Lock and operation mix | KD execution scope |
| --- | --- | --- |
| `mutex` | 100% exclusive updates | Public `kd_mutex_lock/unlock` through ABI2; successful returned-body evidence establishes delegation. |
| `rwsem-read` | 99% reads, 1% writes | Readers execute locally. Explicit outer writers reserve a reader-free phase and may delegate. |
| `rwsem-mixed` | 80% reads, 20% writes | A separate control with more writer interference; the same local-reader and outer-writer interfaces. |

All workers mix their own operations using the existing deterministic phase-17
schedule; these are not dedicated reader and writer thread pools. The initial
mutex profile accepts only 100% writes. Mutex readers would require a separately
defined and measured call shell.

The runner defaults to counts `1 8 16 32 36 60`, a two-second timed interval,
one round per point and four dependent multiply/add rounds after each unlock.
Workers use CPUs `0..N-1`; the collector uses CPU 63. The 36- and 60-worker
cohorts cross the 32-CPU NUMA boundary. The default three-profile, three-backend
screen has 54 measured points. One round supplies no repeat-variability estimate;
`--repeats 3` selects a separately recorded repeated comparison.

Each worker enters one ioctl for the whole operation loop. This isolates the
small protected body using the established resident-workload harness. The
motivating real API benchmarks instead execute one syscall per operation,
including file/VFS handling, redirection and result validation outside the lock.
Their throughput ratios cannot be transferred to this nano workload. Its four
post-work rounds also differ from the historical exclusive synthetic post64
shell. Keep both call-shell identities separate in reports.

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

`--profiles mutex rwsem-read` can select the two principal profiles; keep
`rwsem-mixed` as a separately identified writer-interference control. Changing
`--post-work-rounds` changes the workload and requires matched arms and a distinct
result identity.

## Interpretation and exact checks

The local control compiles callable KD mutex acquisition/unlock instead of the
public ABI2 call shell. Rwsem local control selects ordinary writer admission
instead of a shared delegated-writer reservation. These changes preserve exact
provider routing and the same payload, but also change call-shell or admission
costs. They are not a pure isolated switch for JIT execution. Compare their
results as mechanism evidence with those limits stated.

The existing [reader/writer runner](../rwlock_compare/README.md) validates every
worker's CPU, complete operations, deterministic read/write counts, post-work
checksum and zero reader errors. Before/after snapshots require both word deltas
to equal the exact sum of completed writes and all fourteen unused fields to
remain zero. Native and local controls must have no JIT execution. KD entries
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
the new minimal shared-record profiles; the new body does not rewrite or fill
gaps in those historical results.
