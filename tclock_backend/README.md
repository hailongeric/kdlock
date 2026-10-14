# TCLock spin, mutex and rwlock ports

These modules provide TCLock spinlocks, mutexes and rwlocks for the x86_64
benchmarks. Callers use `komb_spin_lock/unlock`, `komb_mutex_lock/unlock`, or the
`komb_read/write` pairs. Every caller sharing a lock must use that lock's TCLock
API. Loading a provider does not redirect other kernel lock calls.

`target_lock` identifies a lock for diagnostics. Change or clear it only after
all users have finished and the lock has drained. It does not select the algorithm
used by a lock operation.

[Lock protocols](../docs/design/lock_protocols.md) defines exclusion and lifetime.
[Spin](../docs/design/spin_implementation.md) and
[mutex](../docs/design/mutex_implementation.md) explain storage and handoff;
[rwlock protocols](../docs/design/lock_protocols.md#tclock-rwlock) cover reader
admission and writer delegation.

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

The private source fragments are included in their original declaration order and
compiled together. This preserves the assembly strings, GCC options and inlining
boundaries. [port.patch](port.patch) compares six upstream files with the maintained
C files after their fragments have been expanded, plus the corresponding headers.
Git also records the fragment organization and compatibility/provider changes.
Use the patch to review how the port differs from upstream; it is not an installer
for another kernel. Keep the upstream copy unchanged.

## Build and drain

Guest only; the runner normally creates isolated builds:

```sh
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_NUMA=1
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_MUTEX=1 TCLOCK_NUMA=1
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_RWLOCK=1 TCLOCK_NUMA=1
```

The outputs are `tclock_backend_km.ko`, `tclock_mutex_backend_km.ko` and
`tclock_rwlock_backend_km.ko`. Load the backend before its workload. To shut down,
join every worker, check `quiescent=1`, and clear the diagnostic target pointer.
Then unload the workload before the backend. Keep context storage and task
references until all workers, queues and borrowed stacks have finished. Never
force unload.

## Selected comparator scope

| Property | Spin | Ordinary mutex | Rwlock |
| --- | --- | --- | --- |
| Body execution | Real native waiter stack | Real native waiter stack | Reads local; queued writers may use native waiter stacks |
| Wait | Polling | Upstream parking/wakeup retained | Count/gate polling |
| Preemption | Caller pairs pin/unpin | Ordinary operation manages it | Caller pairs pin/unpin |
| Context storage | Per-CPU nodes/8 KiB shadow stack | Preallocated registered context; one fixed worker/CPU | Per-CPU nodes/8 KiB shadow stack; one non-nested worker/CPU |
| Execution counts | Unmeasured | Returned batches/delegated bodies and successful parks | Unmeasured |

The mutex port covers ordinary locking only, not unimplemented interruptible/killable/IO
or rwsem interfaces. Registration/task references replace upstream custom task
fields without changing parking, NUMA or stack switching. A live exiting task keeps
drain busy; retry outside measurement rather than releasing early.

The spin and mutex ports retain NUMA/WWJUMP with configured 1,024; zero-based jumps
can execute 1,025 bodies. The common header enables NUMA even if the Makefile variable is 0, so actual
ELF metadata must reject misleading off labels. The selected spin comparator disables
IRQ checks and accepts IRQ-enabled ordinary task-context workloads. It does not
promise arbitrary IRQ/BH, mixed trylock or nested/oversubscribed support.
Batches do not truncate on `need_resched()`. UBSAN is off for these modules;
the captured kernel and mitigation/frame-pointer configuration are unchanged.
Known stack-switch objtool warnings remain; audit the built trampoline before loading.

## Rwlock comparator

The rwlock backend ports the pinned **`komb_rwlock.c`**. An uncontended writer can
acquire the count word directly. Contended writers and slow readers queue at a
separate gate. A reader always runs its application body on its original CPU,
although the short acquisition path through the gate may be delegated. A combiner
can run a queued writer's body by switching to that waiter's saved native stack.
The rwlock code returns to the combiner between delegated requests; it does not
use the spin/mutex ports' WWJUMP chaining.

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
The [RCUHT comparison](../bench/results/380G10/bench/rwlock_compare/20261010-rcuht/README.md)
records the 1%/20% write mixes, built assembly audit and complete performance
matrix against Native and KD ABI3.

Spin counts cannot establish a delegation share. Mutex whole-run returned-batch
counts prove delegation but are not exact selected 300 ms window shares. KD mutexes
use bounded polling followed by blocking; result wake batching and the gate wait
queue differ from TCLock's parking policy. Data/JIT/context/progress/drain
acceptance and commands live in [the runner](../bench/tclock_compare/README.md).
