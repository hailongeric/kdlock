# Original TCLock spin, mutex, rwlock and rwsem ports

These are the stage 1 reference backends in the [project roadmap](../docs/ROADMAP.md).
TCLock's paper evaluated mmap1 using modified kernel lock implementations. This
external-module port has no equivalent actual-MM integration; that is a local
port limit, not a claim that the paper lacked a mmap comparison. A future stage 3
reference needs a compatible full-kernel integration and matched baseline.

These modules provide TCLock spinlocks, mutexes, rwlocks and rwsems for the x86_64
benchmarks. Callers use `komb_spin_lock/unlock`, `komb_mutex_lock/unlock`, or the
`komb_read/write` pairs, or `komb_rwsem_down/up_read/write`. Every caller sharing a lock must use that lock's TCLock
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
[upstream](upstream) retains twelve unchanged upstream files and author statements;
[UPSTREAM.json](UPSTREAM.json) records their SHA256 hashes.

| Entry/components | Responsibility |
| --- | --- |
| [komb.c](komb.c) → [spin](spin) | State, queue, combiner, waiter, lifecycle, trampoline, lock and unlock |
| [komb_mutex.c](komb_mutex.c) → [mutex](mutex) | State, parking/wakeup, queue, combiner, slowpath, trampoline and unlock |
| [combiner.c](combiner.c), [include/lib/combiner.h](include/lib/combiner.h) | Original six-GPR/RSP switch and shared constants |
| [provider.c](provider.c), [compat.h](compat.h) | Spin lifecycle, binding and drain |
| [mutex_provider.c](mutex_provider.c), [mutex_compat.h](mutex_compat.h) | Registered fixed-affinity contexts, stacks, task refs and complete cohort drain |
| [komb_rwlock.c](komb_rwlock.c), [rwlock_provider.c](rwlock_provider.c) | Upstream rwlock reader counts, fast/queued writers, stack delegation and quiescent drain |
| [komb_rwsem.c](komb_rwsem.c), [aqs.c](aqs.c), [rwsem_provider.c](rwsem_provider.c) | Original rwsem writer delegation and AQS reader gate; registered task storage and drain |

The private source fragments are included in their original declaration order and
compiled together. This preserves the assembly strings, GCC options and inlining
boundaries. [port.patch](port.patch) compares six upstream files with the maintained
C files after their fragments have been expanded, plus the corresponding headers.
Git also records the fragment organization and compatibility/provider changes.
Use the patch to review how the port differs from upstream; it is not an installer
for another kernel. Keep the upstream copy unchanged. Regenerate all review patches with
`python3 tclock_backend/update_patches.py` on the source host.

The selected source is the upstream RCUHT implementation, not a reconstruction
of its protocol. Preserve its admission, queue ordering, scheduling, parking,
wakeup, NUMA selection, batch exits and stack switches. Changes are restricted
to kernel/module integration, types, explicit caller-context restoration and
lifetime diagnostics. Do not replace a missing behavior with a newly designed
lock and label it original TCLock. The original repository already contains
rwsem; earlier statements that **this port** lacked rwsem described a local
omission, not an upstream limitation.

## Build and drain

Guest only; the runner normally creates isolated builds:

```sh
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_NUMA=1
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_MUTEX=1 TCLOCK_NUMA=1
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_RWLOCK=1 TCLOCK_NUMA=1
make -C tclock_backend KDIR=/root/linux-6.1.159-kdclobber2 TCLOCK_RWSEM=1 TCLOCK_NUMA=1
```

The outputs are `tclock_backend_km.ko`, `tclock_mutex_backend_km.ko`,
`tclock_rwlock_backend_km.ko` and `tclock_rwsem_backend_km.ko`. Load the backend before its workload. To shut down,
join every worker, check `quiescent=1`, and clear the diagnostic target pointer.
Then unload the workload before the backend. Keep context storage and task
references until all workers, queues and borrowed stacks have finished. Never
force unload.

## Selected comparator scope

| Property | Spin | Ordinary mutex | Rwlock | Rwsem |
| --- | --- | --- | --- | --- |
| Body execution | Real native waiter stack | Real native waiter stack | Reads local; queued writers may use native waiter stacks | Reads local; queued writers may use native waiter stacks |
| Wait | Original RCUHT polling/scheduling | Upstream parking/wakeup retained | Count/gate polling | Original AQS reader gate and writer scheduling/parking |
| Preemption | Caller brackets operation; upstream wait loop may schedule | Ordinary operation manages it | Caller brackets operation and restores IRQ-enabled context | Original read/write operations manage it |
| Context storage | Per-CPU nodes/8 KiB shadow stack | Registered context; one fixed worker/CPU | Per-CPU nodes/8 KiB shadow stack; one non-nested worker/CPU | Registered context; one fixed worker/CPU |
| Benchmark execution counts | Unmeasured | Returned batches/delegated bodies and successful parks | Unmeasured | Unmeasured; separate correctness probe records remote writers |

The mutex port covers ordinary locking only, not unimplemented interruptible/killable/IO
or rwsem interfaces. Registration/task references replace upstream custom task
fields without changing parking, NUMA or stack switching. A live exiting task keeps
drain busy; retry outside measurement rather than releasing early.

The spin and mutex ports retain NUMA/WWJUMP with configured 1,024; zero-based jumps
can execute 1,025 bodies. The common header enables NUMA even if the Makefile variable is 0, so actual
ELF metadata must reject misleading off labels. The selected spin comparator disables
IRQ checks and accepts IRQ-enabled ordinary task-context workloads. It does not
promise arbitrary IRQ/BH, mixed trylock or nested/oversubscribed support.
Spin restores the upstream `need_resched()` batch exit and the RCUHT
wait loop that enables preemption, schedules, then disables preemption again.
Mutex retains its original batch and parking policy. UBSAN is off for these modules;
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
The original rwlock IRQ toggles are retained. Its inline assembly returns can
bypass the trailing IRQ enable. The supported callers enter with IRQs enabled
and restore that context after the complete pair, before enabling preemption.
This caller adaptation replaces the former deletion of IRQ operations inside
the lock; it does not alter admission, ownership or stack handoff. Arbitrary
IRQ-disabled callers remain unsupported. The six-register/RSP switch remains the original code
and is checked both in a userspace fixture and the built module.

Callers pair preemption disable/enable around the complete read/write operation
and restore IRQ-enabled task context at the end.
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
counts prove delegation but are not exact selected 300 ms window shares. KD retains
pinned polling, so mutex parking policies differ. Data/JIT/context/progress/drain
acceptance and commands live in [the runner](../bench/tclock_compare/README.md).

## Original rwsem comparator

The pinned upstream `locks/komb_rwsem.c` and `include/rwsem/komb_rwsem.h`
implement a separate reader/writer semaphore. They were missing from the old
local port. This backend also imports the original AQS (adaptive queue spinlock)
reader gate from `locks/aqs.c` and `include/spinlock/aqs.h`; it does not substitute
a Linux spinlock, TCLock rwlock, or a new reader/writer wrapper around the mutex.
[rwsem-port.patch](rwsem-port.patch) records every adaptation.

Readers use the original count and AQS gate and execute locally. Writers use
the original fast path or queued waiter-stack execution, including the original
parking/wakeup states, NUMA selection and WWJUMP chaining. Reader admission can
spin; calling this a semaphore does not imply that every wait sleeps. BRAVO and
bounded opportunistic writer spinning remain disabled, as in the selected source.

The upstream kernel adds fields to `task_struct`. To avoid modifying the recovery
kernel, the external module stores those fields in registered contexts, one
fixed-affinity worker per CPU. Register before acquisition with
`tc_rwsem_worker_register()`. Only ordinary read/write pairs are exported for
benchmark use. Join the entire worker cohort, then invoke
`tc_rwsem_workers_drain()` (or write `1` to the provider's `drain` parameter).
An exiting task can still yield `EBUSY`; retry outside measurement and keep the
context and task reference until retirement. Check `quiescent=1`, clear the
diagnostic target, and unload the workload before the provider.

The original killable wrappers call ordinary acquisition and return success;
they do not implement signal cancellation. Original downgrade calls `BUG_ON`.
These functions are retained in source but are not exported as supported module
APIs, and this port supplies no equivalent actual-mmap integration API. Nested,
migrating, oversubscribed and arbitrary sleeping critical sections
are not validated by this fixed-worker port. Do not claim Linux rwsem API parity.

Use `bench/rwlock_compare/run.py --lock-kind rwsem --backends native tclock kdlock`
with the documented explicit workload/CPU grid. The TCLock shell is labelled
`upstream-stack`; worker registration and retirement are outside operation timing.
Benchmark delegation counts remain unmeasured; the separate correctness probe
records actual different-task execution. Historical nano reports and their
unsupported slots remain unchanged because they used the earlier source.

See [original-port validation](../tests/kernel/tclock_original/README.md) for
short commands, actual coverage, retained failures and adapter limitations.
