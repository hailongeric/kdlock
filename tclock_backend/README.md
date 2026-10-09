# TCLock spin, mutex and rwlock ports

These are independent x86_64 external-module backends. Callers explicitly use
`komb_spin_lock/unlock`, `komb_mutex_lock/unlock`, or the `komb_read/write` pairs; every participant on a target
must use the same TCLock protocol. Providers install no global hooks.
`target_lock` is a drained diagnostic binding, not a hot-path selector.

[Lock protocols](../docs/design/lock_protocols.md) defines exclusion and lifetime.
[Spin](../docs/design/spin_implementation.md) and
[mutex](../docs/design/mutex_implementation.md) explain storage and handoff.

## Source and organization

Pinned source: [TCLocks](https://github.com/rs3lab/TCLocks), commit
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`, subtree `src/kernel/rcuht/`.
[upstream](upstream/) retains eight unchanged upstream files and author statements;
[UPSTREAM.json](UPSTREAM.json) records their SHA256 hashes.

| Entry/components | Responsibility |
| --- | --- |
| [komb.c](komb.c) → [spin](spin/) | State, queue, combiner, waiter, lifecycle, trampoline, lock and unlock |
| [komb_mutex.c](komb_mutex.c) → [mutex](mutex/) | State, parking/wakeup, queue, combiner, slowpath, trampoline and unlock |
| [combiner.c](combiner.c), [include/lib/combiner.h](include/lib/combiner.h) | Original six-GPR/RSP switch and shared constants |
| [provider.c](provider.c), [compat.h](compat.h) | Spin lifecycle, binding and drain |
| [mutex_provider.c](mutex_provider.c), [mutex_compat.h](mutex_compat.h) | Registered fixed-affinity contexts, stacks, task refs and complete cohort drain |
| [komb_rwlock.c](komb_rwlock.c), [rwlock_provider.c](rwlock_provider.c) | Upstream rwlock reader counts, fast/queued writers, stack delegation and quiescent drain |

Private fragments stay in original declaration order in one translation unit,
preserving assembly strings, GCC options and inlining boundaries. They are not
separate objects. [port.patch](port.patch) compares the six upstream files against
the **expanded** maintained C units and corresponding headers; fragment organization
and compat/provider adaptation are also reviewed in Git. It is a provenance diff,
not an installation patch for another kernel. Do not edit the immutable upstream copy.

## Build and drain

Guest only; the runner normally creates isolated builds:

```sh
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_NUMA=1
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_MUTEX=1 TCLOCK_NUMA=1
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_RWLOCK=1 TCLOCK_NUMA=1
```

Outputs are `tclock_backend_km.ko`, `tclock_mutex_backend_km.ko` and
`tclock_rwlock_backend_km.ko`. Load backend
before its dependent workload. Join workers, check `quiescent=1`, clear the diagnostic
target pointer, then unload workload before backend. Never force unload or free
context/task refs before the complete cohort and queue/stack drain.

## Selected comparator scope

| Property | Spin | Ordinary mutex |
| --- | --- | --- |
| Body execution | Real native waiter stack | Real native waiter stack |
| Wait | Polling | Upstream parking/wakeup retained |
| Preemption | Caller pairs pin/unpin | Ordinary operation manages it |
| Context storage | Per-CPU nodes/8 KiB shadow stack | Preallocated registered context; one fixed worker/CPU |
| Execution counts | Unmeasured | Returned batches/delegated bodies and successful parks |

The port covers ordinary mutex only, not unimplemented interruptible/killable/IO
or rwsem interfaces. Registration/task references replace upstream custom task
fields without changing parking, NUMA or stack switching. A live exiting task keeps
drain busy; retry outside measurement rather than releasing early.

Both ports retain NUMA/WWJUMP with configured 1,024; zero-based jumps can execute 1,025
bodies. The common header enables NUMA even if the Makefile variable is 0, so actual
ELF metadata must reject misleading off labels. The selected spin comparator disables
IRQ checks and accepts IRQ-enabled ordinary task-context workloads. It does not
promise arbitrary IRQ/BH, mixed trylock or nested/oversubscribed support.
Batches do not truncate on `need_resched()`. UBSAN is off for these modules;
the captured kernel and mitigation/frame-pointer configuration are unchanged.
Known stack-switch objtool warnings remain; audit the built trampoline before loading.

## Rwlock comparator

The rwlock backend ports the pinned **`komb_rwlock.c`**, including its separate
count-word writer fast path, queued writer path and short slow-reader gate path.
It does not replace that algorithm with the spin port. Readers execute their
application body on the original CPU; slow reader admission itself can use the
upstream gate's stack delegation. Queued writer bodies run on borrowed waiter
stacks. Unlike the spin/mutex variants, this upstream rwlock implementation returns
to its combiner between delegates and does not implement WWJUMP chaining.

[rwlock-port.patch](rwlock-port.patch) records Linux qspinlock type substitution,
pointer typing, exported noipa boundaries, possible-CPU allocation rollback and
drain bookkeeping. The original code decrements the node count without incrementing
it; the port balances this at queue entry to make ownership drain observable.
As in the selected spin comparator, explicit IRQ toggles are omitted for the
IRQ-enabled task-context workload. In particular, an inline assembly return must
not bypass IRQ restoration. The six-register/RSP switch remains the original code
and is checked both in a userspace fixture and the built module.

Callers pair preemption disable/enable around the complete read/write operation.
Only one non-nested, pinned benchmark operation per CPU is supported. The original
8-bit current-CPU field limits this port to at most 256 possible CPUs. Module
unload requires zero reader/writer count and gate, balanced per-CPU node counts,
empty lock/NUMA queues, restored shadow-stack pointers and original CPU context.
Rwlock delegation counts are unmeasured; the
[rwlock runner](../bench/rwlock_compare/README.md) reports that explicitly.

Spin counts cannot establish a delegation share. Mutex whole-run returned-batch
counts prove delegation but are not exact selected 300 ms window shares. KD retains
pinned polling, so mutex parking policies differ. Data/JIT/context/progress/drain
acceptance and commands live in [the runner](../bench/tclock_compare/README.md).
