# Reader/writer and proc snapshot benchmark workload

`rwlock_bench.ko` exposes `/dev/kd_rwlock_bench` for the
[comparison runner](../../bench/rwlock_compare/README.md). Build variants select
Linux native, TCLock or KD through `RB_BACKEND` and the locking shell through
`RB_LOCK_KIND=rwlock|spin|rwsem`. All use the same timed worker loop, operation
mix and payload. TCLock has no sleeping rwsem backend.
The runner defaults to RCUHT at 1% and 20% writes across all fifteen requested
thread counts. Rwlock readers execute locally; only KD writer bodies can contribute
to the complete-body JIT count. TCLock uses the actual upstream rwlock algorithm,
with its delegation share reported as unmeasured.

Cacheline variants compile a fixed `RB_LINES` body. Hash variants use
`RB_WORKLOAD=rcuht RB_LINES=0` and share the existing spin benchmark's preallocated
hash move body and structural snapshot oracle, adding concurrent read lookups.
KD rwlock writers use ABI3: native or delegated writer admission precedes the JIT
payload. Hash pointer traversal therefore retains the original strict admission
checks without including reader-drain counter stores in its translated body.
`RB_SHARED` points to that hash payload header. Register-only post-work follows
the earlier cacheline benchmark's multiply/add pattern;
`RB_POST_WORK_ROUNDS` is always explicit in the runner and layout response.
Its default is four rounds, independent of the shared spin/mutex post-work
setting. RCUHT here is a globally locked hash workload, with no per-body
allocation or RCU services; the name does not imply lock-free reader execution.
Future cacheline benchmark selections use `RB_LINES=1` or `RB_LINES=8`.

`RB_LOCK_KIND=spin RB_WORKLOAD=argbounds|taskname RB_LINES=0` selects extracted
Linux 6.1.159 proc snapshots. Argument bounds copy four related address fields;
task names call `strscpy_pad()` and verify the complete padded destination after
unlock. Both retain exclusive spin semantics. Snapshot reads are the KD delegated
entry; optional mutations use the same physical KD lock locally. The mutation
counter and per-reader checks detect lost updates and inconsistent snapshots.
These tests exclude task/MM lifetime management and procfs I/O. Task-name helper
learning can be refused by strict instruction admission; a published NORMAL image
or an entry witness alone does not establish complete delegation.

`RB_LOCK_KIND=rwsem` selects Native or KD sleeping reader/writer operations for
the cacheline/hash payloads. `RB_RWSEM_DELEGATE=1` selects the explicit KD writer
shell: reserve a reader-free epoch, enter the existing mutex ABI2 wrapper and
release the reservation on the original caller after the matching unlock.
Reader-drain waiting happens before queue publication. Ordinary writers reserve
an exclusive admission state, so downgrade cannot create readers inside an
existing delegated epoch. Readers remain local. The runner selects this shell
for its default KD comparison and binds completion observation to the embedded
physical KD mutex. `RB_RWSEM_DELEGATE=0` is the build default and ordinary local
control; the runner requests it with `--delegate off` and names it `-local`.
No owned-mutex protocol or ABI4 is restored. Default-KD runs require a stable ABI2
publication across measurement, and their returned writer completions remain
separate from entry-only or zero-entry runs.
This extracted benchmark does not replace a live kernel `mmap_lock`.

The versioned [ABI](api.h) configures each phase while no workers are active. Each
worker claims its slot once and executes its whole batch in one ioctl. It publishes
progress every 256 completed operations in a separate 128-byte slot. A control gate
protects configuration, snapshots and KD preparation, outside the lock being
measured. Choosing read versus write and generating random keys also happen outside
the critical section.

Readers update only their own result counters. Writers update the protected data.
Hash outcome totals are combined once per returned ioctl. After all callers finish,
snapshots and the Python checker verify the resulting data. Use the separate
[rwlock test workload](../rwlock/README.md) for instrumented reader/writer overlap
checks. These benchmarks support pinned task-context callers with IRQs enabled,
one global lock and no recursive reads, upgrades or nested/IRQ/BH locking.
