# Subjects and measurement contract

This rerun compares the existing KD implementation with TCLock and Linux Native
on `10.176.26.71`. It covers every configuration in the earlier six-count
[waiting-policy comparison](../20261012/README.md), at all requested counts:

`1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 64`.

The completed matrix is 20 kernel payload/mix configurations × 22 counts × four
arms × three rounds, plus 11 API configurations × 22 counts × five arms × three
rounds: **8,910 measured sessions**. The larger cacheline configurations are
retained for completeness alongside the requested c01 and hash payloads.
The run finished on 2026-10-12 at 13:01 UTC: all sessions drained, 8,908 were
accepted and two zero-JIT spin controls remain unscored. The [results](README.md)
describe these exclusions and the measured performance limits.

## Test subjects and locks

| Subject | Protected work and shared state | Native | KD and TCLock |
| --- | --- | --- | --- |
| Mutex c01/c08/c16 | Increment one word in each of 1/8/16 shared cachelines | Linux `struct mutex` | KD spin and blocking policies; TCLock ordinary mutex port |
| Mutex hash | Preallocated hash lookup and unlink/relink; move/conflict/miss outcomes | Linux `struct mutex` | Same protected payload under the two KD policies and TCLock |
| Spin c01/c08/c16 and hash | The same counter/hash update bodies | Native qspinlock (`nopvspin`) | KD and TCLock spin protocols |
| Rwlock c01/c02/c04/c08/c16 and hash | Shared reads with either 1% or 20% writes | Native reader/writer spinlock | Readers execute locally; eligible contended writers may delegate |
| `ioctl(FIONREAD)`, 16/128 buffers | Traverse real occupied pipe buffers and sum their lengths | `pipe_inode_info.mutex` | KD spin/blocking mutex and TCLock mutex |
| `fcntl(F_GETPIPE_SZ)` | Read the capacity of one shared 16-page pipe | `pipe_inode_info.mutex` | Short mutex body on the same subsystem |
| `lseek(SEEK_SET/SEEK_END)` | Bounds checks and updates to a shared file's position/version | `file.f_pos_lock` | KD spin/blocking mutex and TCLock mutex |
| `fcntl(F_OFD_GETLK)`, 16/128 ranges | Traverse real OFD ranges to find a tail conflict and copy it | `file_lock_context.flc_lock` | KD and TCLock spin protocols |
| `F_SETFD` plus `F_GETFD`, strides 16/512 | Update the close-on-exec bitmap and validate each worker's descriptor flag | `files_struct.file_lock` | KD and TCLock spin protocols; one operation includes both syscalls |
| 80% `uname`, 20% hostname/domain updates | Readers copy the full `new_utsname`; writers replace one 64-byte name plus its terminator in real private-namespace metadata | Private Linux rwsem in matched Native; global `uts_sem` in Stock | KD/TCLock reader/writer spinlocks around a bounded non-sleeping body |

The hash payload is the maintained RCUHT-shaped structure: 1,024 buckets,
4,096 nodes and 8,192 possible keys. It performs no per-operation allocation or
RCU service. The name does not imply lock-free readers. Spin/mutex use 100%
update operations; rwlock adds concurrent lookups. Structural snapshots and
exact outcome counters validate the hash. Cacheline oracles check every active
counter and inactive sentinel.

Register-only work outside the lock remains inside timing: 64 multiply/add
rounds for spin/mutex, four for rwlock. These are separate workload contracts;
absolute rates across lock families do not isolate the cost of a lock.

The API cases include syscall entry, descriptor/security work, result copying
and userspace validation in timing. A scoped module substitutes the selected
helper only for a bound private test object. Matched Native, TCLock and KD
compile the same protected body with their selected lock calls. Stock uses the
original helper in the captured kernel. The kernel has UBSAN enabled; all timed
replacement/provider modules disable it. Stock and matched Native therefore
answer different comparisons and remain separate in the tables.
For pipe/file mutex cases, Native and KD retain the original object's Linux
mutex. TCLock uses its own `komb_mutex` object for the bound target; independent
consumers of the original object are excluded by the test contract.

UTS matched arms use private locks and move proc notification after unlock on
the original caller. Stock retains the global rwsem and original notification
placement. This bounded adaptation does not implement a general sleeping KD
rwsem or demonstrate mmap support. FxMark, mmap and the rejected xattr admission
case are outside this rerun. These are kernel/API microbenchmarks, not complete
application workloads; API variants are not independent applications.

The [API contract](../../../../../real_api/README.md) gives the exact bindings,
specializations and lifetime restrictions. TCLock uses the repository port of
upstream `bbfb9f00a12af51dff6ca291cb9829a82960c2ef`, with its emitted context-switch
audit, NUMA policy and batch limit 1,024 retained.

## KD policies

Both KD modes use the current provider source. Spin is `mutex_blocking=0`;
blocking is `mutex_blocking=1 mutex_spin_limit=4096`. These parameters are fixed
for the loaded provider. Blocking polls for a bounded number of PAUSE iterations,
then uses uninterruptible sleep. Result completion notifications are batched,
with a one-tick timeout recheck to preserve progress when a later delegated body
depends on an earlier completed caller. The Linux tick is 4 ms; it is not a
bound on acquisition or scheduling latency.

The [implementation report](../20261012/README.md) covers ownership, lifetimes,
native unlock acknowledgments and scheduler tests. This rerun changes no lock
algorithm. Spin/rwlock do not use the mutex waiting policy: their two KD settings
are repeated controls of an unchanged protocol, not distinct algorithms.

## Machine and placement

| Setting | Value |
| --- | --- |
| Physical host | `10.176.26.71`, two Xeon Gold 6438N sockets, 32 cores/socket, SMT off |
| Frequency policy | Host `ondemand`; no fixed-frequency claim |
| Guest | Temporary 66-vCPU recovery boot, two NUMA nodes, 24 GiB RAM |
| Memory | 12 GiB per guest NUMA node, bound to its matching physical node |
| Worker CPU order | Guest `0–31,33–64`, taking a prefix for each requested count |
| Physical worker pins | Guest `0–31` → host `0–31`; guest `33–64` → host `32–63` |
| Collector | Guest 65 → host 63; spare guest 32 → host 31 |
| Kernel | `6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Boot policy | `nokaslr nopvspin`, voluntary preemption; kernel unchanged |
| Recovery snapshot | `full-wait-66cpu-20261012-v1`, verified through the QEMU monitor |

Counts above 32 use both physical NUMA nodes. At **64 workers**, the last worker,
collector and QEMU service threads share physical host core 63. The collector
has its own guest CPU, but not its own physical core. The 60-worker results
provide a nearby point without this collector/worker overlap. Neither the
32→36 nor 60→64 transition isolates one hardware cause: worker count also changes.

Worker/collector affinities are verified during execution. Preparation retains
the normal allowed CPU set; payload page placement at module load is not measured.
Do not pool this topology with the earlier 64-vCPU six-count comparison.

## Timing, order and acceptance

Each configuration has three rounds. Microbench warmup is 48,000 operations
per worker. API warmup requires at least 48,000 operations and one second per
worker. Measurement targets two seconds; whole-run throughput uses the actual
recorded wall interval through worker completion.

The peak is the highest valid full-cohort window of at least 300 ms after
300 ms of settling. Sampling is every 10 ms, with 256-operation progress
checkpoints. Every worker must make progress in the selected window. Tables
show median whole-run throughput and the highest valid warmed peak; exports
retain all three samples, min/median/max and `(max-min)/median × 100%` spread.
Plot shading is the observed range, not a confidence interval.

Direct spin/mutex and all API runs place KD spin and blocking next to each
other, reversing their order on odd rounds. Baseline order also changes between
rounds. Direct rwlock payloads retain separate spin-setting and blocking-setting
groups; their mutex parameter is inactive. There is no randomization, and
pairing does not eliminate run-order or frequency effects. Slow-start samples
remain in the statistics.

Data checks, positive progress, affinity, returned-body counters, kernel health,
retirement and final drain remain mandatory. A published NORMAL JIT image does
not establish that a translated body executed. Permitted zero-JIT observations
remain labelled native-path controls, while missing required JIT evidence is
retained as an unscored exclusion. Plain 2/3-worker direct cases allow such
controls; direct mutex cases at four or more workers require JIT. Rwlock/UTS
JIT shares use writes, not all mixed operations, as the denominator.

Summed worker CPU time per operation is CPU cost, not acquisition latency or
hardware energy. Result schedule/gate wait counters count calls; they alone
do not prove a task descheduled. Throughput and JIT shares can support an
interpretation of delegation, but cannot by themselves prove a cache-locality
cause. This performance matrix collects no hardware cache-miss counters.

## Source and reproduction

Runner support was committed as `e378642`. Nine pre-existing working-tree edits
were preserved, including the spin/mutex post-work inputs. Each group freezes
actual source bytes, binary identities, kernel inputs and generated JIT images;
the Git commit alone is insufficient to reconstruct those inputs.

Run only in the verified VM after source synchronization and a confirmed
snapshot of the 66-vCPU topology:

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_66_VCPU_SNAPSHOT
python3 bench/mutex_wait_compare/run.py --full-grid --paired-policies \
  --cpus $(seq 0 31) $(seq 33 64) --collector-cpu 65 \
  --output /root/kdlock-evidence/10.176.26.71/bench/full-wait-NEW
python3 bench/mutex_wait_compare/export.py --input RAW_RUN --output NEW_REPORT --plots
python3 analyze.py --report NEW_REPORT --plots
```

The maintained [runner guide](../../../../../mutex_wait_compare/README.md)
describes stopping and evidence handling. Exporting never reruns measurements.
Archive raw evidence before restoring the regular 64-vCPU boot; saved states
from different CPU topologies must not be loaded interchangeably.
