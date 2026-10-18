# Lock and benchmark terminology

These definitions explain terms used in the maintained guides. Names in code or
recorded results stay unchanged so that a reader can find the corresponding
implementation or measurement.

## Locks and execution

| Term | Meaning in this project |
| --- | --- |
| API / syscall / ioctl | An application programming interface (API) is a set of callable operations. A system call (syscall) enters the kernel from a userspace program. `ioctl` is a system call that sends a device- or object-specific command. |
| Critical section / body / payload | The work performed while a lock protects shared data. A benchmark payload is the particular protected operation being measured. |
| Mutex | A lock that permits one owner at a time and can let blocked callers sleep. |
| Spinlock | An exclusive lock whose blocked callers wait by repeatedly checking state instead of sleeping. |
| Rwlock | A reader/writer spinlock: several readers may enter together, or one writer may enter alone. |
| Rwsem | A reader/writer semaphore: several readers may enter together, or one writer may enter alone, and blocked callers can sleep. The KD version has additional restrictions once a delegation request is published. |
| KD / delegation | This project's lock implementation. A lock holder can execute another waiting task's protected work on that task's behalf. |
| Native / Linux Native | The corresponding unmodified Linux lock implementation used in a comparison. This label does not mean that every surrounding benchmark adapter is original kernel code. |
| TCLock | The separately maintained comparison implementation, which can delegate work by switching to a waiting caller's stack. This repository has TCLock spin, mutex and rwlock ports, but no sleeping rwsem port. |
| Backend / arm | One implementation in a comparison, such as Native, TCLock or KD. |
| Origin / waiter / producer | The task that requested an operation. When its request is delegated, it waits for the result. |
| Executor / combiner | The task that executes another task's delegated operation. Combining means serving several queued requests while holding the lock. |
| Local execution / local control | The original task performs its own operation. A local control deliberately disables delegation for comparison or validation. |
| Physical owner / gate | The owner record and underlying exclusive lock that prevent competing writers from touching protected data simultaneously. Logical delegation does not remove this physical exclusion. |
| Outer writer | A writer using the explicit paired interface that allows its protected body to be delegated. Ordinary writer interfaces execute locally. |
| Admission / phase / epoch / reservation | Admission decides who may enter. A phase, also called an epoch, is the current reader/writer admission state. A reservation records a writer's right to remain in that phase until its matching release. This differs from instruction admission, which checks whether code can be delegated. |
| Reader drain | Waiting until all previously admitted readers have released their read access. |
| Final drain / retirement | After work stops, all requests, acknowledgements and references have finished, so their storage and source code can safely be released. An idle lock alone does not prove this. |
| Waitqueue | A kernel list of sleeping tasks waiting for a condition. A wakeup makes a task eligible to run again; the task must still recheck the condition. |
| Polling / condition probe | Repeatedly checking a condition without sleeping. A probe is one such check. A probe-count limit is not a fixed time limit. |
| Predicate | The condition being checked, such as whether the reader count is zero. Some checks also acquire a reader count or writer reservation when they succeed. |
| Preemption / pinned waiter | Preemption lets the scheduler pause a running task to run another. A published KD mutex waiter polls with preemption disabled, so it cannot yield its CPU in the ordinary way while that request remains outstanding. |
| Publication | Making a request or generated code image visible to other participants. Publishing code does not prove that any caller executed it. |
| Heat policy / promotion | The policy that decides when repeated lock activity justifies preparing or enabling delegated execution. Promotion makes an eligible critical section available for that execution path. |
| Cancellation / interruptible / killable | Cancellation stops a waiting acquisition without retaining ownership. Interruptible waits can respond to ordinary signals; killable waits respond only to fatal signals. |
| Trylock / downgrade | A trylock returns immediately if it cannot acquire access. A downgrade converts an exclusive writer into a shared reader without admitting another writer in between. |
| Fairness / bounded wait | Fairness concerns which waiting caller gets access next. A bounded-wait guarantee limits how long a caller can be delayed. Current KD rwsem does not provide Linux rwsem's fairness policy or such a bound. |
| Oversubscription / same-CPU / colocated | Oversubscription means more runnable tasks than available CPUs. Same-CPU or colocated tests deliberately place multiple participants on one CPU to check scheduling progress. |

## Translation, ownership and machine state

| Term | Meaning in this project |
| --- | --- |
| JIT | Just-in-time compilation: KD translates a critical section into machine code for delegated execution. |
| Provider / translator / daemon | The provider is the kernel module that implements KD locks and delegated execution. The translator generates machine code. The userspace daemon coordinates translation and publication requests. |
| Image / immutable image | A generated-code object. An immutable image is not rewritten after publication; a replacement uses a separate version. |
| Returned JIT body / entry and completion | A delegated body that reached its matching unlock and returned through the completion protocol. Entry counts alone, or an image labelled `NORMAL`, do not prove completion. |
| Synthetic completion | The original caller resumes after its matching unlock because another task has already executed the protected body and completed the release protocol on its behalf. The original caller must not execute that body again. |
| Fail-closed admission | If the translator or runtime cannot establish the required safety conditions, it must refuse delegated execution rather than assume the code is safe. |
| `NORMAL` / `NO_JIT` / `PARTIAL_JIT` | Recorded status labels. `NORMAL` means an image was published. `NO_JIT` means the measured session returned no JIT bodies. `PARTIAL_JIT` does not qualify as complete-body evidence. |
| ABI / ABI1 / ABI2 / ABI3 | Application binary interface: the machine-level agreement between callers, generated code and recovery code. KD entry identities 1, 2 and 3 identify ordinary spin, ordinary mutex and rwlock-writer interfaces respectively. Rwsem outer writers use the existing mutex entry identity, ABI2. These are not Linux-wide ABI version numbers. |
| Wrapper / call shell | Code around a protected body that acquires/releases the lock and exchanges execution state. Different call shells must be recorded separately in comparisons. |
| Clobber boundary / compiler spill | A boundary tells the compiler which registers may be overwritten. The compiler saves needed values, usually to the stack; these saves are called spills. |
| Continuation / `noipa` | A continuation is the point where execution resumes. The `noipa` compiler attribute prevents interprocedural optimization from changing a function in ways that invalidate its prepared continuation. |
| Packet / frame / ledger | A packet stores the execution state shared between waiter and executor. A frame tracks one active delegated operation. A ledger records exact acquisitions and ownership obligations. None can be replaced by approximate activity counts. |
| Source lease | A reference that keeps the module containing an operation's original code loaded while it can still be used. |
| ACK / unlock acknowledgement | Confirmation required by the ownership protocol that a lock release has completed. Storage cannot be retired merely because the body stopped executing. |
| Memory ordering / barrier | Rules and instructions that ensure one CPU observes shared-state changes in the required order. Acquire ordering constrains later accesses; a full barrier orders accesses on both sides. |
| CAS / compare-and-exchange | An atomic operation that changes a value only if it still equals the expected old value. It prevents two writers from reserving the same exclusive state. |
| Cacheline / alignment | The unit transferred between CPU caches; the workloads use 64-byte lines. Alignment places an object at an address divisible by the specified size. Separating frequently written fields can reduce traffic between CPUs. |
| IRQ / BH / RT / lockdep / ww_mutex | Linux facilities: hardware interrupt context, bottom-half interrupt handling, real-time kernel locking, lock dependency checking, and wound/wait mutexes used for some multi-lock operations. Whole-kernel support for these facilities is outside the accepted rwsem measurements. |
| MM / VMA / mmap lock | MM refers to memory management. A virtual memory area (VMA) describes an address range. A process's `mmap_lock` protects parts of its memory-map state. Benchmarking a private KD rwsem does not replace this kernel lock. |
| R13 / RSP / registers | Registers are small storage locations in the processor. R13 is one general-purpose x86-64 register; RSP holds the current stack pointer. A caller interface must capture or establish a register's value before generated code uses it. |

## Measurements and evidence

| Term | Meaning in this project |
| --- | --- |
| Session / repetition / point / grid | A session is one run. Repetitions rerun the same configuration. A point fixes workload, write percentage and worker count; a grid is the planned collection of points. |
| Worker / collector | Workers execute benchmark operations. The collector records their progress and normally has a separate CPU. |
| Probe / witness / functional check | A probe deliberately exercises specified behavior; a witness is a recorded observation such as an entry or completion count. A functional check verifies correctness instead of scoring speed. |
| c01 / c08 / RCUHT | The maintained synthetic payloads: one shared counter cacheline, eight shared counter cachelines, and hash-table lookup/move work. RCU means read-copy-update, a Linux synchronization mechanism, but the RCUHT benchmark itself uses the selected global lock rather than per-operation RCU reclamation. |
| post4 / post64 | Four or 64 dependent arithmetic rounds performed after each unlock. This work is outside the critical section and changes the workload. |
| Mops/s / throughput | Millions of completed operations per second, summed across workers. It is not the latency of an individual request. |
| Whole-run median | Compute each repetition's rate over its entire measured interval, then take the middle rate among the three repetitions. |
| Warmup / settling / best peak | Warmup executes operations before timing. Settling excludes early measured windows from peak selection. The best peak is the highest eligible window rate under the runner's progress and operation-mix checks. |
| Ratio / parity / regression | A ratio divides one throughput by another: 2× means twice as fast; 0.286× means 28.6% of the reference rate, or 71.4% slower. In the current rwsem/rwlock comparison, parity requires both the observed median whole-run rate and best peak to be at least the reference values. A regression is a lower measured rate; these comparisons alone are not statistical significance tests. |
| Split execution-status group | Repetitions at one point contain both sessions with returned JIT bodies and `NO_JIT` sessions. They are reported separately instead of being merged into one three-repetition group. All planned runs may still have completed. |
| Baseline / candidate screen / profile | A baseline is the recorded comparison version. A candidate screen is a smaller exploratory comparison. A profile counts or times internal functions to investigate cost; instrumented profiles are excluded from scored throughput. |
| Hits/op | Recorded function calls divided by completed benchmark operations. These profiles can include background work and nested functions, so counts or times cannot be added as exclusive CPU costs. |
| Manifest / content hash / receipt / replay | A manifest lists captured files and their hashes. A hash identifies their bytes. A receipt records checks and outcomes. Offline replay recomputes results from retained data; it does not rerun the kernel test. |
| VM / vCPU / topology / NUMA | A virtual machine (VM) has virtual CPUs (vCPUs). Topology records their placement on physical CPUs and memory nodes. Non-uniform memory access (NUMA) means memory-access cost depends on the CPU and memory node. |
| Governor / instrumentation / UBSAN / ELF | A governor is the host's CPU-frequency policy. Instrumentation adds measurement or checking code. UBSAN is the compiler's undefined-behavior sanitizer. ELF is the executable/module file format whose bytes and identity are recorded. |
| Proc / procfs / snapshot | Procfs is Linux's `/proc` interface for process and kernel information. An extracted snapshot benchmark copies a small selected record under a lock; it does not run the complete procfs operation or the `ps` process-listing command. |

See the [workload catalog](BENCHMARK_WORKLOADS.md) for exact protected operations,
[performance status](PERFORMANCE.md) for accepted measurements and limitations,
and the [rwsem design](design/rwsem_implementation.md) for the waiting protocol.
