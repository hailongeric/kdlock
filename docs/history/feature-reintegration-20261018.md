# Non-protocol feature reintegration, 2026-10-18

The accepted KD-only mutex remains the main mutex protocol. This follow-up
reviews branch contents, rather than treating merged Git ancestry as proof that
every feature survived the [initial consolidation](main-consolidation-20261018.md).
That consolidation preserved the selected runtime but excluded too much of the
independent proc snapshot and benchmark infrastructure work.

## Why rwsem was missing

Commit `8ce6ab9` introduced a sleeping reader/writer semaphore and proc snapshot
workloads; old master `2c88895` retains that implementation. The later owned
branch `9a4bf2a` diverged before rwsem integration and is not a superset. Its
merge base with old master is `c67bb1c`; rwsem arrived on a separate branch and
was merged through `82f92db`. Reviewing only the owned branch tip misses that
independent feature.

The old semaphore was coupled to the owned mutex's **unlock-time** combining.
A physical writer acquired the gate, drained readers and then eventually
combined writers during unlock. The accepted legacy mutex can combine during
**acquisition**, before the caller returns to drain readers. Renaming the old
gate calls would allow a delegated write while a reader is still active.
The old cookie test is also incompatible: zero in the current outer cookie can
describe a queued physical writer, not only a delegated invocation.

Reader-drain ordering is not the only issue. Published legacy mutex waiters
poll with preemption disabled. A waiter can occupy a CPU needed by a sleeping
rwsem reader to resume and release, preventing writer progress. A pre-batch
drain hook alone does not establish a general sleeping rwsem contract. Closing
reader admission before publishing writers also needs an audited interaction
with ordinary writer downgrade, cancellation and native continuation.

## Safe integration boundary

The ordinary sleeping semaphore can use the accepted KD physical mutex as an
admission gate without changing that mutex's protocol. Readers execute locally
and can overlap and sleep; a physical writer retains the gate while sleeping
for readers to drain. Trylocks and ordinary writer downgrade belong to this
API. Task-sensitive cancellation must release the gate when reader drain is
interrupted.

The maintained [rwsem guide](../design/rwsem_implementation.md) defines the actual
implemented API and exclusions. There is no delegated rwsem outer API in this
port. Native/KD rwsem benchmarks are ordinary local-execution comparisons and
must not publish a JIT score. The existing TCLock port has no sleeping rwsem arm.

This is an explicit KD object, not an installed replacement for Linux
`mm->mmap_lock`. Kernel-wide conversion still needs all-consumer and object-layout
changes, full lifetime/access-check analysis, fault/retry and lock-mode handling,
and renewed kernel validation. No guest kernel is rebuilt or changed here.

## Feature dispositions

| Feature / source | Disposition |
| --- | --- |
| Accepted mutex `d2a2304`, compatibility fixes `555b8b7` | Retain physical exclusion, ABI2, immutable images, fail-closed admission, legacy queues and pinned delegation waiters |
| Sleeping semaphore from `8ce6ab9` / `2c88895` | Port ordinary APIs to KD physical locking; exclude unsafe inherited writer delegation |
| Proc `argbounds` / `taskname` snapshots from `2c88895` | Restore independent spin payloads and runner/oracle integration; preserve exact helper refusal rather than substituting another copy |
| Snapshot helper learning and complete-body evidence | Restore benchmark-only instrumentation and learning checks; publication or entry alone is insufficient |
| Unscored CPU sampling from `1255bdc` | Restore diagnostic benchmark tooling independently of mutex policy |
| API publication fences, plan validation and report identity | Restore compatible safeguards with current ABI2 and dedicated collector constraints |
| Optional frozen translator/daemon paths | Restore source-isolation tooling without changing lock execution |
| Owned/adaptive mutex, ABI4, origin-context experiments and parked producers | Keep archived; these depend on or change the rejected mutex execution protocol |
| Retired launchers and obsolete shadow/signal fixtures | Keep historical; they depend on retired topology or deleted provider interfaces |

The [fresh validation receipt](../../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
identifies exact inputs and all outcomes: ordinary rwsem scheduling/cancellation,
61 successful workload sessions, complete rwlock/argbounds bodies and two retained
delegation-acceptance failures. Taskname passed local controls but not delegated
preparation. Historical 2026-10-15 scores remain attached to their original
implementation and are not pooled with this port. No mutex throughput-regression
or rwsem parity claim is made from this focused integration round.
