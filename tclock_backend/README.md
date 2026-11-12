# TCLock comparator sources

This tree retains the original TCLock module ports used as comparison inputs.
The rebuilt branch currently has kernel9 build, emitted-context audit and live
evidence for the **ordinary mutex and rwsem** lanes in the
[cacheline1/post256 runner](../bench/nano/README.md). The other retained source
files do not establish current spin/rwlock support or validation.

Pinned upstream: [TCLocks](https://github.com/rs3lab/TCLocks), commit
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`, subtree `src/kernel/rcuht/`.
[UPSTREAM.json](UPSTREAM.json) records twelve unchanged upstream file hashes;
[upstream/](upstream/) retains those files. Review patches describe module and
Linux compatibility changes. Keep original admission, queue ordering, NUMA
selection, scheduling, parking/wakeup, batch exits and native-stack switches.
The adaptation is not a new locking protocol. All private `.inc` files are
required build inputs and belong in each frozen source manifest.

| Components | Responsibility |
| --- | --- |
| [komb_mutex.c](komb_mutex.c), [mutex/](mutex/) | Original mutex queue, combiner, parking and continuation switches |
| [mutex_provider.c](mutex_provider.c), [mutex_compat.h](mutex_compat.h) | Registered task storage, fixed-affinity context, references and drain |
| [komb_rwsem.c](komb_rwsem.c), [aqs.c](aqs.c) | Original writer delegation and concurrent reader gate |
| [rwsem_provider.c](rwsem_provider.c), [rwsem_compat.h](rwsem_compat.h) | Rwsem task storage, context and complete drain |
| [combiner.c](combiner.c), [include/lib/combiner.h](include/lib/combiner.h) | Native six-register/RSP switching |

The current runner selects `TCLOCK_NUMA=1` and `komb_batch_size=1024`. The
latter tests a continuation counter that starts at zero on the first borrowed
body and increases on each subsequent waiter jump. Missing next/lookahead nodes
can end combining earlier. It is not a measured physical batch length.
Readers run their bodies locally; queued writers can use a waiter's saved
native stack. Every user of a lock must use the same TCLock API. Loading these
modules does not replace arbitrary kernel lock calls.

Build/sign only in the VM using [build.py](../bench/nano/build.py) and the
source/output-separated exact kernel build. The current evidence retains
compiler/objtool warnings and both emitted mutex/rwsem context audits; it does
not establish general return-mitigation coverage. The manually managed entry
trampolines retain their scoped frame option and explicit register saves.

Use fixed-affinity, non-nested benchmark workers. Killable cancellation,
downgrade, migration, oversubscription and arbitrary sleeping bodies remain
outside this comparator lane. `target_lock` is a diagnostic pointer. Set or
clear it only when the lock and workers are quiescent, and clear it before
freeing the workload object. Retain task/context/stack storage through all
queue and borrowed-stack users. Join/retire workers, require exact ordinary
drain, unload the workload, then unload the provider; never force unload.

The [kernel9 report](../bench/results/10.176.26.71/bench/kernel9-nano-20261112/README.md)
binds current source/binary/boot/topology identities and preserves all results.
Its frozen inputs also retain the earlier README verbatim as historical port
context. Earlier validation claims and old command paths are not current
kernel9 evidence.
