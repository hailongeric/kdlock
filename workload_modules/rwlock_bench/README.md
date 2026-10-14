# Read-write lock benchmark workload

`rwlock_bench.ko` exposes `/dev/kd_rwlock_bench` for the
[comparison runner](../../bench/rwlock_compare/README.md). Build variants select
Linux native, TCLock or KD rwlocks through `RB_BACKEND`; all use the same timed
worker loop, operation mix and payload.
The runner defaults to RCUHT at 1% and 20% writes across all fifteen requested
thread counts. Readers execute locally; only KD writer bodies can contribute
to the returned-body JIT count. TCLock uses the actual upstream rwlock algorithm,
with its delegation share reported as unmeasured.

Cacheline variants compile a fixed `RB_LINES` body. Hash variants use
`RB_WORKLOAD=rcuht RB_LINES=0` and share the existing spin benchmark's preallocated
hash move body and structural snapshot oracle, adding concurrent read lookups.
KD writers use ABI3: native or delegated writer admission precedes the JIT
payload. Hash pointer traversal therefore retains the original strict admission
checks without including reader-drain counter stores in its translated body.
`RB_SHARED` points to that hash payload header.
RCUHT here is a globally locked hash workload, with no per-body
allocation or RCU services; the name does not imply lock-free reader execution.

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
