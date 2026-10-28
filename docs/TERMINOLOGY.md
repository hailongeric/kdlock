# Lock and benchmark terminology

These definitions explain the maintained interfaces and evidence labels.
Historical service quotas, CALL-alias experiments and direct string relocation
contracts remain in the [fixed glossary](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/TERMINOLOGY.md).
Recorded names and numeric outcomes remain unchanged.

The [project roadmap](ROADMAP.md) defines the development stages and their
completion criteria. A stage is a research/integration milestone; a campaign is
one fixed set of measurements. Completing a campaign does not establish that a
stage's correctness and performance requirements have been met.

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
| Native execution / native continuation | The original waiter runs its original source instructions. This can still use KD locks; it does not mean switching a KD object to Linux Native locking. |
| TCLock | The separately maintained comparison implementation, which can delegate work by switching to a waiting caller's stack. This repository ports the original TCLock spin, mutex, rwlock and rwsem implementations; module support is restricted to the documented ordinary APIs and fixed-affinity callers. |
| Backend / arm | One implementation in a comparison, such as Native, TCLock or KD. |
| Origin / waiter / producer | The task that requested an operation. When its request is delegated, it waits for the result. |
| Executor / combiner | The task that executes another task's delegated operation. Combining means serving several queued requests while holding the lock. |
| Local execution / local control | The original task performs its own operation. A local control deliberately disables delegation for comparison or validation. |
| Physical owner | The task or acquisition that actually holds exclusion and is responsible for physical release. A logical waiter may have its work executed without becoming that owner. |
| Gate | A lock or state that orders admission. Its meaning depends on the family: KD mutex has a scheduling gate separate from physical ownership; rwlock embeds a spin gate; rwsem's `gate` field is an entire KD mutex. Holding an admission reservation is not physical ownership. |
| Outer writer | A writer using the explicit paired interface that allows its protected body to be delegated. Ordinary writer interfaces execute locally. |
| Admission / phase / epoch / reservation | Admission decides who may enter. A phase, also called an epoch, is the current reader/writer admission state. A reservation records a writer's right to remain in that phase until its matching release. This differs from instruction admission, which checks whether code can be delegated. |
| Reader drain | Waiting until all previously admitted readers have released their read access. |
| Final drain / retirement | After work stops, all requests, acknowledgements and references have finished, so their storage and source code can safely be released. An idle lock alone does not prove this. |
| Waitqueue | A kernel list of sleeping tasks waiting for a condition. A wakeup makes a task eligible to run again; the task must still recheck the condition. |
| MCS queue / queue head / handoff | An MCS (Mellor-Crummey–Scott) queue links waiter-owned nodes so callers mostly poll their own notification state. The queue head is next to attempt physical acquisition. A queue handoff grants that position; it does not by itself prove lock ownership or completed work. |
| Optimistic spinning / OSQ | A mutex caller briefly polls while its owner appears able to run, then sleeps if needed. An optimistic spin queue (OSQ) orders competing spinners. KD has its own OSQ storage and functions. |
| NUMA / locality / cohort | Non-uniform memory access (NUMA) groups CPUs by memory-access locality. KD can group nearby queued callers into a cohort to reduce movement between groups. This selection policy does not grant ownership or guarantee fairness. |
| FIFO / batch | First-in, first-out (FIFO) follows arrival order. A batch serves several waiting operations under one physical lock acquisition; NUMA selection can change their order within documented bounds. |
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

Production uses `trusted_source=True`: selected kernel/module source safety and
compiler entry inputs are caller assumptions. Decoding, lowering, source leases,
publication and runtime ownership/continuation contracts remain enforced.
Semantic, memory and input proofs below belong to optional checked regression
analysis (`trusted_source=False`). Historical string services and direct bridges
are not selected by current images; strings use ordinary decoded CALL/RET, while
only `ktime_get`, `ktime_get_ns` and `int_sqrt` remain selected scalar services.
See [translation policy](design/admission.md) for the scope of each mode.

| Term | Meaning in this project |
| --- | --- |
| JIT | Just-in-time compilation: KD translates a critical section into machine code for delegated execution. |
| Provider / translator / daemon | The provider is the kernel module that implements KD locks and delegated execution. The translator generates machine code. The userspace daemon coordinates translation and publication requests. |
| Image / immutable image | A generated-code object. An immutable image is not rewritten after publication; a replacement uses a separate version. |
| Returned JIT body / entry and completion | A delegated body that reached its matching unlock and returned through the completion protocol. Entry counts alone, or an image labelled `NORMAL`, do not prove completion. |
| Synthetic completion | The original caller resumes after its matching unlock because another task has already executed the protected body and completed the release protocol on its behalf. The original caller must not execute that body again. |
| Fail-closed admission | Required decoding, lowering, source-lease, publication and runtime contracts must hold before delegated execution can proceed. Production trusts source semantics; optional checked mode additionally refuses code when its required semantic proofs fail. |
| `NORMAL` / `PASS` / `NO_JIT` / `PARTIAL_JIT` | `NORMAL` describes a published image. In the taskname/xattr comparison's measured execution groups, `PASS` means at least one complete delegated body; `PARTIAL_JIT` means generated code was entered but no body completed; `NO_JIT` means no generated-code entry. `PASS` here does not mean performance parity. Older reports and the snapshot runner's strict required-completion failure can use `NO_JIT` more broadly for zero completed bodies; retain their recorded meaning and inspect entry and completion counts separately. |
| ABI / ABI1 / ABI2 / ABI3 | Application binary interface: the machine-level agreement between callers, generated code and recovery code. KD entry identities 1, 2 and 3 identify ordinary spin, ordinary mutex and rwlock-writer interfaces respectively. Rwsem outer writers use the existing mutex entry identity, ABI2. These are not Linux-wide ABI version numbers. |
| Wrapper / call shell | Code around a protected body that acquires/releases the lock and exchanges execution state. Different call shells must be recorded separately in comparisons. |
| Clobber boundary / compiler spill | A boundary tells the compiler which registers may be overwritten. The compiler saves needed values, usually to the stack; these saves are called spills. |
| Caller-saved / callee-saved registers | A call may overwrite caller-saved registers, so its caller must save any needed values. The called function must preserve callee-saved registers under their calling agreement. |
| Helper entry / register initialization | The optional spin helper entry defines five already-clobbered registers before a C helper can save them. This supplies defined source values without capturing more waiter registers or changing the helper operation. |
| Constant branch proof | An optional checked-mode analysis that removes a branch alternative only when every incoming source state has the same required constant values. It does not infer constants from runtime memory or permit an otherwise forbidden instruction. Production retains the source branches. |
| Continuation / `noipa` | A continuation is the point where execution resumes. The `noipa` compiler attribute disables interprocedural optimization, including transformations that could duplicate a named continuation. |
| Packet / frame / ledger | A packet stores the execution state shared between waiter and executor. A frame tracks one active delegated operation. A ledger records exact acquisitions and ownership obligations. None can be replaced by approximate activity counts. |
| Source lease | A reference that keeps the module containing an operation's original code loaded while it can still be used. |
| Typed native service / hostcall | Generated code asks the executor to invoke one named original helper under its defined argument, result and continuation contract; it is not permission to call arbitrary kernel functions. Current selection is scalar-only. Historical string services relied on the original C caller's memory and lifetime guarantees. |
| Reviewed / audited caller | Caller code whose memory, lifetime and temporary return-storage obligations have been established by source review. This is an explicit assumption for that selected caller, not a runtime check or a proof about arbitrary kernel code. |
| Temporary CALL storage / control token | The return-address bytes written by a source CALL so execution can return to its continuation. Historical `strcmp` and `strscpy_pad` services used a selected-caller promise not to observe or overwrite these bytes as data, with a separate analysis model. Current ordinary callees use actual CALL words and generated return routing without that service-specific exception. |
| Widened value / widening | Optional checked analysis can no longer bound every possible value within its finite tracking limits. A widened address remains a reason for that analyzer to refuse delegation; it cannot bypass the refusal by treating it as an ordinary unknown pointer. Production does not run this analysis. |
| No-fault read / NUL terminator | A no-fault read reports an invalid address without raising a kernel exception. KD uses it when reading saved return state. A NUL terminator is the zero byte marking the end of a C string. Historical string services did not scan strings before invoking the original helper; current translation decodes the helper normally. |
| Helper source closure | The original helper and every other routine or return sequence it can reach. Production decodes selected leased callee text without semantic screening. Earlier checked helper implementations inspected that code; historical API services instead relied on the original caller contract. |
| Instruction marker / native suffix / `NATIVE_ONLY` | A marker is generated code that exits before a reviewed original instruction. The native suffix is the remaining code, resumed by the original waiter at that instruction without repeating earlier work. `NATIVE_ONLY` disables further delegation of that entry for the source session. |
| Address guard / stack alias | Optional checked translation can emit a spin guard checking whether a pointer load overlaps recorded writes on the waiter's stack; two addresses referring to the same bytes are aliases. It does not validate every object or pointer. Failure resumes that load on the original waiter without repeating prior work. Production trusted translation does not select this analysis or guard retry. |
| Arithmetic flags / control flags | Arithmetic flags record carry, parity, auxiliary carry, zero, sign and overflow from calculations. Control flags govern matters such as interrupt delivery, string-operation direction and access checks. The mutex instruction-exit path restores source arithmetic flags while retaining the waiter's control flags. |
| Flags-dead proof | An optional checked-mode proof that incoming arithmetic flags are no longer needed: every source path overwrites each flag before reading it, or reaches the declared final clobber unlock. The checked spin address exit requires this proof because its native restore does not preserve those flags. That path refuses bodies requiring constant-branch simplification, which could hide a flags read in the original native suffix. |
| Capability / image requirement | A capability advertises a provider's supported execution contract. An image requirement declares a contract that particular generated image needs. The provider rejects unknown or mismatched requirements instead of silently running the image with weaker guarantees. |
| Opcode / encoding / prefix | An opcode identifies a machine instruction; its encoding is the exact sequence of bytes the CPU executes. Prefix bytes can change its meaning. The marker policy admits only individually reviewed encodings. |
| Scalar / vector / SIMD / FPU | Scalar operations act on individual values. Vector operations process several values together; SIMD means single instruction, multiple data. FPU denotes floating-point processing. Vector and floating-point execution state is outside the instruction-marker contract. |
| ACK / unlock acknowledgement | Confirmation that the physical owner handled a logical release request. The owner may retain physical exclusion for a batch, and frame/storage retirement has additional requirements; neither follows merely because the body stopped executing. |
| Memory ordering / barrier | Rules and instructions that ensure one CPU observes shared-state changes in the required order. Acquire ordering constrains later accesses; a full barrier orders accesses on both sides. |
| CAS / compare-and-exchange | An atomic operation that changes a value only if it still equals the expected old value. It prevents two writers from reserving the same exclusive state. |
| RMW / atomic flag bits | A read-modify-write (RMW) operation reads and updates a value indivisibly. Flag bits encode additional state in a word; for example, KD mutex's low owner bits distinguish sleepers, requested handoff and reserved pickup. |
| PAUSE / prefetch | PAUSE is an x86 polling hint. Prefetch asks the CPU to fetch a cacheline early. Neither supplies lock ownership, memory ordering, data validity or a lifetime reference. |
| Compilation unit | Source compiled together. This provider includes private `.inc` fragments in their owning unit instead of linking those fragments as separate objects. |
| RCU / GFP_ATOMIC | Read-copy-update (RCU) defers freeing shared records until prior readers have finished. `GFP_ATOMIC` requests a kernel allocation that must not sleep and can fail; neither replaces exact acquisition-reference accounting. |
| ELF / DWARF | ELF is the compiled module's file format; DWARF is its debug information. Captured layout evidence can use these to identify symbols, field offsets and object sizes for that particular build. |
| WWJUMP | The TCLock port's direct jump between delegated waiter continuations, avoiding a return to its ordinary batch loop between those bodies. It does not name KD's execution mechanism. |
| Cacheline / alignment | The unit transferred between CPU caches; the workloads use 64-byte lines. Alignment places an object at an address divisible by the specified size. Separating frequently written fields can reduce traffic between CPUs. |
| IRQ / BH / RT / lockdep / ww_mutex | Linux facilities: hardware interrupt context, bottom-half interrupt handling, real-time kernel locking, lock dependency checking, and wound/wait mutexes used for some multi-lock operations. Whole-kernel support for these facilities is outside the accepted rwsem measurements. |
| MM / VMA / mmap lock | MM refers to memory management. A virtual memory area (VMA) describes an address range. A process's `mmap_lock` protects parts of its memory-map state. Benchmarking a private KD rwsem does not replace this kernel lock. |
| Independent mm / shared mm | Separate processes normally have distinct address spaces and mmap locks. Pthreads in one process share an address space and its lock. Shared file descriptors or `MAP_SHARED` alone do not establish shared mm identity. |
| mmap1 | will-it-scale's repeated 128 MiB anonymous private read/write mmap followed by munmap, without accessing the range. Its thread and process executables use different mm topologies. Existing 4 KiB device mappings are different workloads. |
| Private backing lock | A driver's lock protecting its own backing pages/metadata. It can be shared by workers with independent mms. Selecting KD here does not replace the kernel mmap lock; the current fault mapping uses `MAP_SHARED`, not `MAP_PRIVATE`. |
| Native kernel control | Native mode in the integration tree, distinct from a separately built stock Linux kernel. Both need recorded source/configuration identities; neither means caller-local KD execution. |
| GPR / R13 / RSP / registers | Registers are small storage locations in the processor. A general-purpose register (GPR) holds scalar machine state; R13 is one such x86-64 register. RSP holds the stack pointer. A caller interface must capture or establish a register's value before generated code uses it. |

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
| Ratio / parity / regression | A ratio divides one throughput by another: 2× means twice as fast; 0.286× means 28.6% of the reference rate, or 71.4% slower. The existing rwsem/rwlock report's parity predicate requires both median whole-run rate and best peak to reach the reference. The roadmap's proposed stage 2 tolerance is a separate prospective contract and does not alter that predicate or historical verdicts. A lower rate is a measured regression; significance and parity require the declared variability analysis. |
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
