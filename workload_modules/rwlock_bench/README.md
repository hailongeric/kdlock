# Read-write lock benchmark workload

`rwlock_bench.ko` exposes `/dev/kd_rwlock_bench` for the
[comparison runner](../../bench/rwlock_compare/README.md). Build variants select
Linux native, TCLock or KD rwlocks through `RB_BACKEND`; all use the same timed
worker loop, operation mix and payload.

Cacheline variants compile a fixed `RB_LINES` body. Hash variants use
`RB_WORKLOAD=rcuht RB_LINES=0` and share the existing spin benchmark's preallocated
hash move body and structural snapshot oracle, adding concurrent read lookups.
The KD hash writer currently fails strict JIT address admission; hash comparisons
with KD writers stop and preserve the refusal instead of producing a JIT score.
`RB_SHARED` points to that hash payload header. Register-only post-work follows
the earlier cacheline benchmark's multiply/add pattern;
`RB_POST_WORK_ROUNDS` is always explicit in the runner and layout response.

The versioned [ABI](api.h) configures a joined phase, claims each worker slot once,
executes a full batch in one ioctl, and publishes per-worker progress every 256
completed operations on separate 128-byte slots. A quiescent control gate protects
configuration, snapshots and KD preparation; it is outside the measured lock.
Mixed-operation selection and random keys also stay outside critical sections.

Readers update only caller-local result counters. Writers update protected data;
hash outcome totals aggregate once per returned ioctl. Snapshots and the Python
oracle check business results after callers join. Use the separate
[rwlock test workload](../rwlock/README.md) for instrumented reader/writer overlap
checks. These benchmarks support pinned task-context callers with IRQs enabled,
one global lock and no recursive reads, upgrades or nested/IRQ/BH locking.
