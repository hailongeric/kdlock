# kdlock Design

本轮执行：[单锁字、本地哈希与稳定角色](design/locking.md)。基线已提交为
`7e2460c`；已清理停用 spin 分发/缓存并实现单锁字、本地哈希及角色；mutex 接入及生命周期检查保留。
下方 L/S 和缓存描述属于历史基线；当前协议以链接的 locking 章节为准。

This document describes current implementation contracts, not a chronological
test log. Usage and execution flow: [JIT_EXECUTION](JIT_EXECUTION.md).
Exact registers: [JIT_REGISTER_ABI](JIT_REGISTER_ABI.md).
Current failures and historical evidence: [VALIDATION](VALIDATION.md).
Priorities and explicit deferrals: [TODO](TODO.md). Performance experiments:
[PERFORMANCE_PLAN](PERFORMANCE_PLAN.md).

Detailed contracts are maintained once: [source and hook lifetimes](design/lifetimes.md),
[spin/mutex locking](design/locking.md), [admission](design/admission.md), and
[frame storage and continuation](design/frames.md). This overview retains
section links for existing bookmarks.

## 1. Motivation And Scope

The implementation, tests and planned work target x86_64 machines only.
Cross-architecture adaptation is outside the project, not a deferred feature.
The [delivery scope](TODO.md#delivery-scope) prioritizes supported main paths;
rare-case generalization and dedicated tests are optional. The limits below
describe unsupported or unproven behavior, not a requirement to implement and
test every exceptional interleaving before current delivery.

kdlock combines lock delegation with dynamic translation of existing kernel
critical-section machine code. A combiner executes a waiter's supported code
under real lock protection without rewriting that critical section's source.
Existing patched lock hooks are required. The current tests use purpose-built
workloads, not a validated unmodified production subsystem.

The design is inspired by TCLock-style delegation and BCD's binary execution
machinery, but adapting user execution to kernel code requires additional
ownership, context and lifetime rules. Address substitution is not a context
switch. JIT is not a security boundary. Measured benefits are workload-specific;
current results and native/TCLock comparisons live in [bench](../bench/README.md),
separately from correctness evidence.

## 2. System Overview

```text
benchmark ioctl -> klock workload -> existing Linux lock hooks
                                       |
                                       v
             kd_lock / kd_hotlock -> spin or mutex scheduler
                                       |
                         native physical lock + execution frame
                                       |
                                       v
                  exe.c <-> /dev/kd_dev <-> daemon
                    |                       |
                    v                       v
               JIT wrapper             miasm translator
                    ^                       |
                    +-------- jit.bin ------+
```

Hooks discover entry RIP and register backend kind. The daemon reads kernel
text, selects the possible JIT range, checks admission, emits/assembles code
and publishes it. Executors use explicit waiter registers and frame state.
Only the frame-backed spin/mutex entry remains; no user/futex frontend is active.

## 3. Kernel Hook Layer

The legacy spin/mutex hooks pass lock address, saved hook RSP and return RIP.
Ordinary spin and mutex on `kdclobber2` instead use distinct versioned bridges
with RDI=lock, RSI=pre-CALL RSP, RDX=the local post-CALL label and RCX=caller RBP.
The compiler spills live values across the declared GPR clobbers; RSP/RBP obey
the call boundary. This path does not decode a compiler-generated prologue.
Legacy hook offsets and the new ABI are defined in [the register ABI](JIT_REGISTER_ABI.md);
[kernel baselines](../kernel_baseline/README.md) remain distinct.

`target_process` matches an exact task comm. Spin also recognizes live local
acquisition tickets; mutex recognizes active task records. These preserve
unlock routing through rename and native continuation. Eligibility affects
delegation, never which physical exclusion lock protects the data.

<a id="hotlock-monitoring"></a>

Each CPU has separate spin and mutex hash tables: 16 buckets and six
preallocated candidates linked by slot indices. Lookup hashes the full address
and compares complete keys. Hits increment score; only a full-table miss scans
six scores, unlinks the minimum candidate and inserts the new identity. Its
error equals the replaced score, so `score-error >= 10000` is a conservative
admission requirement and a new address cannot inherit false heat.

Each table retains the 10240-observation clock batch, strict 40-billion-TSC CPU
window and 2.5-billion-TSC candidate window. Window reset clears both score and
error. No global promotion set/query remains. `record_spin`, `record_mutex`,
`query_spin` and `query_mutex` are explicitly CPU-local. IRQ/NMI reentry drops
only a sample; the CPU pin ends before a mutex can sleep. `adaptive` is the load
default; `observe` records identical statistics with fixed admission for protocol
comparisons. Neither policy supplies JIT safety permission.

Fast owners/tickets and stable request frames retain OWNER/WAITER/COMBINER/DONE
independently of the statistics table. Eviction, reset and CPU migration cannot
revoke ownership, modify an active request, or route unlock. See the
[current protocol](design/locking.md) and [scoped tests](../tests/README.md).

### 3.1 Source, Lock And Hook Lifetimes

详细说明见 [lifetimes](design/lifetimes.md#31-source-lock-and-hook-lifetimes)。


## 4. Spin Delegation Protocol

详细说明见 [locking](design/locking.md#4-spin-delegation-protocol)。

## 5. Mutex Delegation Protocol

详细说明见 [locking](design/locking.md#5-mutex-delegation-protocol)。

<a id="41-native-lock-and-private-queue"></a>
<a id="42-acquisition-tickets-and-node-lifetime"></a>
<a id="43-combiner-and-native-returns"></a>
<a id="44-nested-contention-and-stack-resources"></a>
<a id="51-physical-lock-and-scheduling-gate"></a>
<a id="52-entry-completion-and-task-routing"></a>
<a id="53-nested-a---b-and-native-continuation"></a>
<a id="54-differences-from-spinlock-path"></a>
<a id="pinned-busy-polling"></a>

## 6. JIT Execution Engine (exe.c)

### 6.1 Code Block Management

At module init, `kd_exe_init()` pre-allocates a pool of 64 executable memory
blocks (each 160 pages = 640KB).  These are vmalloc'd and marked executable via
`set_memory_x()`.  When `kd_exe_add()` is called from the lock hook (possibly
with IRQs disabled), it takes a block from the pool without calling vmalloc.
Only blocks for which both allocation and `set_memory_x()` succeeded enter the
pool. Pool or translation-table exhaustion fails closed.

Registration publishes a new key only after obtaining its code block. If the
pool is empty, the unused slot is left unchanged and existing entries remain
usable. Re-registering an existing key consumes no block, even after a miss or
terminal policy refusal. Allocated blocks are retained until drained module
teardown, not returned to the pool on native-only publication. Thus the 64-block
pool fills before the 511-slot execution table in the current configuration;
the full-table lookup guard still has an independent bounded-probe test.

The full executable pool is 40 MiB. These blocks remain writable; there is no
RW-staging/RX-publication transition or code-generation lifetime protocol.

Kernel critical-section text is shared across all tasks, so kernel-lock JIT
entries use a **RIP-only key**: the hook calls `kd_exe_add(0, ret_addr, kind)` and
spin/mutex `execute_cs()` resolves `kd_exe_find_ready(0, entry_ip)` and passes that
slot to `kd_exe_on_call_hl_entry()`. This avoids binding a translation to one
short-lived benchmark thread or process ID. A successful execution now probes
the registry once across these two functions, excluding registration/discovery.

The dispatcher rechecks the same slot with `kd_exe_entry_is_ready()` after frame
setup: source must still be OPEN, an acquire load must observe NORMAL, and
PID/RIP/code storage must match. It also retains backend and logical-scope
validation. Passing a pointer eliminates the second and third hash lookups,
not the second readiness observation. Closure before frame push refuses its
lease; closure observed by the dispatcher refuses before the body. Closure
racing after that check must wait for the admitted frame and its continuations
to drain before invalidation and source release. Slot storage/keys are stable
until controlled provider teardown. This is not a code-version lease and does
not solve the existing in-place upload limitation.

Registration records immutable `KD_EXE_LOCK_SPIN` or `KD_EXE_LOCK_MUTEX` in
`kd_exe_info.lock_kind`, using offset 12's former alignment padding. The entry
remains 64 bytes and existing field offsets are unchanged. Different kinds at
the same key make it native-only, not a second executable backend. High-level
entry checks the frame kind before invoking the wrapper. This does not revoke
already-started execution or provide immutable JIT versions.

The translation hash probes at most `KD_MAX_EXE` slots. It returns `NULL` when
full rather than looping in atomic/IRQ-disabled context. Code-block allocation
uses an atomic gate and never waits for the userspace daemon.

An unavailable root entry returns before wrapper execution; spin/mutex queue
handling then lets the unstarted waiter obtain native execution. This is not
PENDING-lock continuation after progress. Resource classes, tests and remaining
coverage gaps are listed in [the usage guide](JIT_EXECUTION.md#6-资源拒绝与测试边界).

### 6.2 Entry Lifecycle

```
KD_EXE_UNUSED -> KD_EXE_UNINIT -> KD_EXE_NORMAL
                                      |  ^
                 daemon recompiles   |  | complete write-back
                                      v  |
                        KD_EXE_CALL_MISS / KD_EXE_IJ_MISS

KD_EXE_NORMAL -> KD_EXE_ERROR_INST  (terminal unsupported instruction)

UNINIT / NORMAL / miss -> KD_EXE_NATIVE_ONLY  (terminal policy/backend refusal)
```

`KD_EXE_HOSTCALL` and `KD_EXE_ENTRY_REFUSED` are deliberately absent from this
lifecycle. They are transient sandbox exit reasons handled by the kernel
executor, not translation-entry states observed by the daemon.

### 6.3 kd_exe_on_call_hl_entry()

This is the core execution function called by the combiner. Its actual signature
is:

```c
int kd_exe_on_call_hl_entry(struct pt_regs *regs, unsigned long entry_ip,
                            unsigned long outer_lock_addr);
```

1. Validate the active frame, waiter GS/task, and exact `(0, entry_ip)` readiness.
   Require a fresh root or a published logical spin child with matching entry,
   task, GS, post-lock-CALL packet and lock depth. A CPU-local physical parent
   alone is insufficient; this checks logical scope, not image generation.
2. Install the two inputs `{frame->gsbase, frame->logical_task}` and enter the
   wrapper. Conditional images check entry disjointness before body. Only an
   explicit `ENTRY_REFUSED` on the first pristine root call, with original
   RIP/RSP and zero witness, can clear the conservative executed mark and
   return `NO_RUN`. It is not a retry after progress or a daemon state change.
3. On hostcall, enforce budgets, dispatch the typed service, pop the virtual
   return address, save continuation state, and re-enter the same artifact.
4. On a control-call exit, use `handle_known_call()` to acquire/release nested
   locks or recognize the matching outer unlock. Nested and OOO handling may
   continue execution rather than complete the frame. Local mutex controls
   first establish and then verify their stack checkpoint; a changed window
   takes the separately validated native suffix after the completed CALL.
5. On an ordinary CALL miss, retain the virtual CALL frame, record the target
   for future translation, and return `KD_EXE_RUN_NATIVE`. A remote child's
   native exit propagates through `KD_EXE_KNOWN_NATIVE` without re-entering JIT.
   Known nested acquisition has separate phase metadata. A PENDING resource
   failure restores its original CALL RIP/RSP and takes the same native handoff
   without publishing a translation miss; see 9.5.
6. Other unsupported exits return an error. Once `frame->executed` is set,
   backends fail-stop rather than replaying the entry. No stores or services
   are undone. IJ, budget, and arbitrary fault continuation remain deferred.

### 6.4 End-Point Detection

The `end_points[]` array lists kernel functions whose address signals the end of
a critical section.  These are resolved dynamically at module init via
`kallsyms_lookup_name`:

```c
end_points[end_point_count] = kallsyms_lookup_name("_raw_spin_unlock");
end_points[end_point_count] = kallsyms_lookup_name("mutex_unlock");
```

When the sandbox encounters a `CALL` to one of these addresses, it reports
`KD_EXE_CALL_MISS`. For the active high-level path, an endpoint address alone
is insufficient: `regs->di` must match `outer_lock_addr`, known-call handling
must finish any deferred spin OOO release, and the backend must validate frame
completion. An inner B unlock normally resumes A. Only the legacy
`outer_lock_addr == 0` branch accepts `is_end_point()` alone.


## 7. Translation And Publication

详细说明见 [admission](design/admission.md#7-translation-and-publication)。

<a id="71-possible-jit-episode"></a>
<a id="72-context-and-memory-admission"></a>
<a id="721-dynamic-address-gap"></a>
<a id="722-static-per-cpu-ranges"></a>
<a id="73-build-and-publication"></a>

## 8. Sandbox Code Model

### 8.1 Registers And State

The wrapper takes `pt_regs *` and exactly two words:
`{waiter kernel GS base, logical waiter task}`.
Inputs are reinstalled for every continuation. Hardware GS/current, scheduler,
IRQ/RCU state, flags and SIMD/FPU are not switched to the waiter.

Physical RSP/RBP belong to the wrapper; R13/R12 initially represent virtual
RSP/RBP. R11 is the shared `pt_regs` backing pointer; virtual GPR spills use
that packet directly, with no wrapper-stack copy on entry or exit. CPU-resident
values still require materialization before C consumes a full packet.
R12-R15 also form the special-register
mapping pool; ordinary instructions cannot hardcode guest R14/R15 locations.
R14 is target RIP at exit, R15 carries an IJ source. Exact slots and supported
GPR persistence are defined only in [the ABI](JIT_REGISTER_ABI.md).

### 8.2 Execution Witness And Budgets

Optional generated-body MOV instrumentation sets the reused args[1] output to
one; the wrapper initializes it to zero. The executor logs a matching positive
witness only after wrapper return. Public tests force this on; manual daemon
launches default off. A marker proves entry into generated body, not full
instruction/path coverage or version identity. Zero never authorizes replay.

Branch-ending blocks increment the private `Stack_BUDGET` slot and test bit 24;
the counter resets at each
wrapper entry. It is not a retired-instruction or whole-CS budget.
Entry predicates, dispatcher CMP and budget INC/TEST can clobber flags. No
flags liveness verifier enforces the limitation. INT-to-NOP and warning-only
special lowering remain; diagnostics do not repair instruction semantics.

### 8.3 Calls And Memory Boundaries

CALL pushes the original return RIP on the virtual stack. Decoded callees can
run inside JIT; an ordinary miss retains the CALL packet for waiter-native
execution. Control/hostcall handlers consume it only when their respective
operation has succeeded. The final unlock return is deliberately left for
successful waiter restoration.

No effective canonical-address or general bounds guard is emitted.
Neither admission nor the word "sandbox" implies a security isolation boundary.

### 8.4 Native Hostcalls

`include/kd_hostcalls.def` is the shared declarative service manifest. The
kernel expands it into a registry of stable IDs, symbol names, safety flags,
resolved addresses, and typed handlers. `disassem/hostcall.py` parses the same
manifest and maps resolved targets to hostcall stubs. Runtime dispatch matches
the exact address against the kernel registry; translated code cannot request an
arbitrary function pointer.

For a hostcall, translated CALL lowering has already pushed the post-CALL RIP
onto the virtual stack. The generated stub puts the service target in R14,
returns `KD_EXE_HOSTCALL`, and deliberately does not pop that RIP. The kernel
handler writes its result to `regs->ax`, calls
`advance_and_save_continuation()`, and invokes the same JIT artifact again. The
outer lock and current `kd_exec_frame` remain active across this boundary.

Each `kd_exe_on_call_hl_entry()` invocation has a 16-hostcall budget and shares
a 16-continuation counter with normal known-call resumes. Child invocations
have their own counters; the early outer-unlock/OOO branch bypasses the normal
known-call limit check, so this is not a strict whole-nesting budget.

At either CALL-count limit, the next callee has not executed. The executor
validates the frame/retained-lock scope, pending-request state, original task's
bounded readable CALL word and source residency for both target and return RIP.
For a HOSTCALL it also checks the existing manifest policy without invoking the
service. A valid packet takes `KD_EXE_RUN_NATIVE`: retain all current GPRs, the
callee RIP and pushed CALL RSP, clear only a previous completed control phase,
and let the original waiter run the callee and remaining native suffix. Physical
owners retain their locks and acknowledge unlocks; this request never reenters
JIT. Quota is not a learning miss and leaves the published image NORMAL.
Invalid packets/targets, synthetic faults and post-dispatch service failures
remain fail-stop. Source pinning does not certify the stack's concurrent privacy.
This is an existing CALL-boundary exit, not instruction-budget recovery,
access-time checking or new flags preservation.

Module-exit diagnostics report `exits`, `executed`, `resumed`, `rejected`,
`failed`, and `limit`. Normal mode 2 and mode 5 service phases require matching
nonzero execution/resume counts and no rejection/failure/limit. Mode 5 keeps
those normal completions and adds a final quota phase in the same session;
its excess callee runs natively on the waiter, not through the hostcall adapter.
The combined counter equations and required CALL/native/ACK witnesses are in
[the mode 5 flow](JIT_EXECUTION.md#613-call-次数额度与原生后缀), not the old
one-service-per-JIT equality for the whole case.

The current manifest has three fixed-signature services. Only symbols resolved
in the running baseline are enabled; the x86-64 contracts are:

| ID / symbol | Saved input | Saved output | Native execution contract |
| --- | --- | --- | --- |
| 1 / `ktime_get` | None | RAX: signed 64-bit nanoseconds | Existing atomic-safe clock adapter; no logical-task context switch |
| 2 / `ktime_get_ns` | None | RAX: unsigned 64-bit nanoseconds | Same clock contract when this symbol is available |
| 3 / `int_sqrt` | RDI: full unsigned 64-bit `unsigned long` | RAX: floor square root, 0 through `2^32-1` | At most 32 scalar iterations in the captured kernel implementation; no pointer argument, allocation, sleeping, lock, callback or task/per-CPU dependency |

All three preserve other saved GPRs. Native execution uses the combiner's C
stack; its ordinary compiler register clobbers do not replace the saved waiter
packet. `int_sqrt` calls the exported kernel helper, not a copied algorithm.
Its input covers the full unsigned range without truncation or signed-result
extension; there is no caller-supplied memory whose lifetime must be validated.
Mode 2/5 consume one scalar result after their clock loop. Thus each normal
JIT completion returns from two services, while mode 5's quota suffix reaches
the scalar operation only on the original waiter after the 17th clock call.

These contracts are atomic-context-safe, independent of the proxy task's
`current`, and retry-safe; they do not authorize replay of a progressed CS.
Variadic `printk`, sleeping APIs, task-context-dependent APIs, opaque pointer
services and side-effecting calls remain excluded. A future side-effecting
service needs a fixed ABI and an exactly-once rule for failures after native
execution. No new access-time check or flags contract is introduced here.


### 8.5 Workload Oracle

Each physical lock protects its own state object with sequence, sum, branch
mix, rotate/checksum, four indexed lanes and commit value. Native replay after
worker drain compares every field and an independently protected completion
count. Generated artifacts are checked for actual executable branch, rotate,
multiply and indexed-access instructions, not source comments.

This catches many wrong updates and continuations, but identical deterministic
transitions cannot distinguish every duplicated/skipped request pair.
Native-register probes separately check marked JIT samples, saved registers,
CALL stack, waiter identity and exactly-once effects. Native fallback is not
a positive JIT result. Current results belong in VALIDATION, not this design.

## 9. Nested Ownership And Continuation

详细说明见 [frames](design/frames.md#9-nested-ownership-and-continuation)。

<a id="91-frames-and-lock-ledger"></a>
<a id="911-reuse-before-copy-contract"></a>
<a id="912-tclock-spin-reference-and-state-boundaries"></a>
<a id="92-ab-execution"></a>
<a id="93-capacity-and-refusal"></a>
<a id="94-out-of-order-and-remote-completion"></a>
<a id="95-forward-native-continuation"></a>
<a id="96-bcd-comparison-and-continuation-scope"></a>

## 10. Kernel-Only Execution Entry

Only `kd_exe_on_call_hl_entry()` executes frame-backed spin/mutex requests.
The unused legacy futex entry, private result and unpinned task-CPU GS sampler
were removed. Historical guest futex/INT3 hooks remain untouched and unregistered.
Reintroducing userspace delegation requires a separate ABI/context/lifetime
design, not restoring an old function.

## 11. Configuration

`target_process` defaults to kd_test; `mutex_jit` defaults to 1.
Batch limits are fixed at 1024. Spin NUMA is opt-in via KDLOCK_NUMA=1.
Recovery-only fault/capacity/rename probes are test controls, not production
recovery guarantees. Use scripts and their preconditions from
[JIT_EXECUTION](JIT_EXECUTION.md), never synthetic post-entry faults as safe
rollback tests.

## 12. Supported Scope And Limits

The concise support matrix is in `README.md`, current execution evidence is in
`docs/VALIDATION.md`, and actionable gaps are tracked only in `docs/TODO.md`.
The implementation boundaries are:

1. **x86-64 only** — inline assembly, stack frame layout, and register
   conventions are architecture-specific.
2. **Patched kernel required** — the hook function pointers and exported
   symbols must exist in the running kernel.
3. **KASLR must be disabled** — `/proc/kcore` reading assumes fixed kernel
   text layout. (`end_points[]` is resolved dynamically and unaffected.)
4. **miasm dependency** — the translator requires miasm 0.1.5 and
   `/proc/kcore` access from userspace.
5. **No rwsem support** — only spinlock and mutex are implemented.
6. **NUMA-aware combining off by default** — `KDLOCK_NUMA=1` opts into the
   existing spin `NUMA_AWARE` branch. Test 21 covers bounded, directly observed
   deferred-follower histories; results depend on source version and fixture. This is not validation of
   arbitrary list lengths, fairness or NUMA-enabled deep physical stacks. Mutex
   delegation has no NUMA-local queue implementation.
7. **No general instruction verifier** — segment/decoder rejection is
   implemented, but `special_inst.py` lowers `INT` to NOP and only warns for
   unhandled special operations such as its `PUSHF`/`POPF` cases. Ordinary
   mnemonics are emitted without a general privilege allowlist. Some unsafe
   instructions can therefore be mistranslated or executed, not rejected.
8. **Nested resources are bounded** — execution frames and lock stacks allow
   eight entries; each CPU has four spin nodes and four bitmap-reserved mutex
   nodes. Before execution, exhaustion uses native handoff; an unhandled
   post-progress exhaustion is fail-stop.
9. **Partial progress is not replayed** — ordinary CALL misses use native
   continuation, as do proven PENDING acquisition resource failures; other
   exits after entering JIT fail-stop until supported.
10. **Hostcalls are an explicit allowlist** — only fixed-signature, atomic-safe,
    task-context-independent, retry-safe services are currently accepted.
    General variadic `printk` and side-effecting services are unsupported.
11. **Persistent processor state is partial** — GS memory uses the pinned
    origin base and logical current; known unsupported context operations are
    refused. Hardware FS/GS switching, FS operands, EFLAGS, and SIMD/FPU
    state are not supported as general cross-exit state. The optional
    `args[1]` body witness adds no processor-state restoration. See `docs/JIT_REGISTER_ABI.md`.
12. **Memory checks are incomplete** — the translator currently emits no
    effective canonical-address or bounds guard, so the JIT must not be treated
    as a security isolation boundary. Access-time checking and its pre-instruction
    native exit, including local condition-code preservation, remain explicitly
    deferred and unimplemented; static screening can miss runtime pointer changes.
13. **Batch limits are fixed** — spin and mutex combiners process at most 1024
    waiters per round; these constants are not module parameters.
14. **Flags can be clobbered inside JIT** — entry predicates, dispatcher comparisons and inserted
    branch-block `INC`/`TEST` are not transparent to live flags. No liveness
    verifier enforces the restriction, even without a wrapper exit.
15. **Continuation is not rollback** — see 9.5; completed stores and child
    sections are retained. Register entry retry is limited to not-started work.
16. **Publication and lifetime are incomplete** — concurrent code replacement
    remains deferred under C3; source-module, lock-object and hook-provider
    lifetimes are separate unresolved contracts in 3.1. Guest predicates are
    called by non-target tasks too, without a matching reader/drain protocol.
    Stopping benchmark callers and draining requests is an experimental
    prerequisite, not a proof of safe provider hot unload.
17. **Scope is narrower than all kernel lock APIs** — delegation supports plain
    raw spin lock/unlock and non-RT mutex lock/unlock. Native mutex participants
    include non-target tasks and successful trylock/interruptible/killable calls;
    those alternate acquisitions are not themselves delegated. Controlled native
    interruptible/killable cancellation while the combiner retains L is tested,
    including head/non-head removal and survivor progress. Bounded native
    signal/release races also cover observed acquisitions/cancellations and
    real HANDOFF requests, not every internal removal/handoff interleaving.
    Separate original-waiter tests cover uninterruptible native B waiting and
    direct cancellable B CALL misses after JIT progress, including pidfd signal
    versus real B-owner release races. Acquired B runs/unlocks once; cancellation
    skips B, not A's completed stores or final owner ACK. Neither outcome
    cancels an arbitrary delegated request or supports exit inside a native suffix.
    Arbitrary cancellation schedules, WW/PI/RT mutexes, irqsave/bh and
    lock-address reuse need separate work.
    Known mixed spin/mutex references in the discovered CFG now refuse before
    codegen using registered entry kind. Unresolved targets/callees can still
    hide such calls; the runtime backend guard remains fail-stop if reached
    after JIT entry. This is not complete call-graph or native-suffix safety.

## 13. Performance Comparator Contract

The [instrumented driver](../bench/lock_scenarios/README.md#33-带观测的负载测量) provides a timing
boundary, not three interchangeable lock implementations. Keep these comparison
groups distinct before interpreting a comparison; all target x86_64:

| Candidate | Actual execution path | Valid comparison boundary |
| --- | --- | --- |
| Native with existing hooks | Same guest/module/workload, nonmatching `target_process`, original Linux locks | A possible same-kernel reference; still includes the installed selector hooks, not pristine unmodified Linux |
| kdlock JIT | Matching task, published supported CS, `mutex_jit=1`, actual returned body and complete state | Instrumented delegation; measured invocations can also contain direct native acquisitions or checked native suffixes |
| `mutex_jit=0` | `__kd_mutex_lock()` calls `kd_origin_mutex_lock()` before shadow scheduling | Explicit debug/native control with its own target/promotion overhead; **not native delegation** |
| Upstream TCLock | Native stack-switch delegation with TCLock lock/task state | Not available as an unchanged mutex module on this guest; a different kernel or an explicitly assessed port is required |
| Independent TCLock spin port | Upstream pending/queue, six-register/RSP switching and native critical-section continuation through the existing hook | Implemented in `tclock_backend/`; same workload and caller binaries as Linux/kdlock, validated for the single-lock global-counter workload |
| TCLock LiTL userspace library | Interposes `pthread_mutex_*` through `LD_PRELOAD` | Does not replace the kernel locks reached through `/dev/lock_dev`; not a kernel comparator |

The local read-only TCLock checkout is `~/TCLocks`, revision
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`. The decisive source locations, relative
to that checkout, are:

- `src/kernel/rcuht/locks/komb_mutex.c`: `get_shadow_stack_ptr()`,
  `get_komb_mutex_node()` and nested combiner paths directly access task fields.
- `src/kernel/linux-5.14.16/include/linux/sched.h`: the `komb_*` task-state
  block; `kernel/fork.c` allocates/initializes and frees its storage.
- `src/kernel/linux-5.14.16/include/linux/mutex.h`: TCLock replaces the mutex
  representation with tail/state/combiner fields. The nano-benchmark's separate
  `src/kernel/rcuht/include/mutex/komb_mutex.h` likewise defines `komb_mutex`;
  neither may be cast onto this guest's owner/wait_list-based Linux mutex.
- `src/kernel/rcuht/rcuht.c`: explicit table/bucket lock adapters and kthread
  state initialization. Its hash-table operations are not kdlock's CS workload.
- `src/userspace/litl/README.md` and `src/liblock.in`: userspace interposition
  contract; the latter path is relative to the LiTL directory.

The [guest compile audit](VALIDATION.md#tclock-comparator-feasibility) builds a
normal external control object but rejects the unchanged TCLock mutex object
for nine missing task members. This is a concrete incompatibility, not a
failed runtime test or proof that every possible module-only port is impossible.
No TCLock module was linked/loaded; spin and LiTL were not compiled in this audit.

An upstream-kernel comparison would change more than a condition and hook:
task layout, task allocation/free and the physical lock representation/protocol
are involved. It is outside the current no-guest-edit default. A module-owned
task/stack table could be investigated separately, but its lifecycle, nested
switching, cleanup and overhead need a new port contract and acceptance; it
must be labelled an adaptation, not unmodified TCLock. Do not introduce a
JIT-disabled production delegation mode merely to fill a results table.

The opt-in [paired experiment](../bench/lock_scenarios/README.md#34-原生锁与-jit-配对实验) implements
native-with-hooks/JIT comparison groups on ordinary mode 2/5, without changing
the guest kernel. Ordinary spin now has the independent
[native-delegation comparison](../bench/tclock_compare/README.md), using two
caller ABIs and balanced six-arm trials. Mutex native delegation and broader
context acceptance remain open in [TODO](TODO.md#comparator-feasibility-and-matched-experiments). Each pair needs
identical workload text, parameters, state preparation, affinity and accounting
boundaries, fresh/drained sessions, retained failures and repeated balanced
order. Native must have no JIT; JIT must have new matching returned bodies in
the measured phase. Different mode timings or old runs are not paired trials.
Do not turn a SELFTEST role that waits for a JIT frame, queue or combiner event
into a native reference: its progress conditions can require delegation.
Use matched ordinary CS paths for measurement and retain those specialized
roles as independent correctness gates.
The implementation retains even, alternating repetitions and explicit thread/
workload sweeps, preparation records, full-session rebuilds and failed pairs.
Generated images and NORMAL registry identity are checked before/after the
payload with translators stopped; this is an experimental constraint, not C3
version isolation. Equal CPU masks and state do not imply equal cache/thermal
conditions, exclusive CPUs or identical native/JIT execution proportions.
Cost separation and amortization remain work, not inferred from these gates.

Routine mutex queue/JIT traces use INFO, not ALERT; their text and availability
in dmesg are preserved. At console level 4 without `ignore_loglevel`, these
records no longer force serial output from native framework code that may
still hold the physical mutex. This is not a sandbox hostcall-policy change.
The [severity follow-up](VALIDATION.md#mutex-routine-log-severity) diagnoses the
initial mode-5 anomaly with unchanged console controls and actual-JIT gates;
it does not remove logging cost or provide a complete cost breakdown. Retain
console settings alongside comparisons, since verbose consoles can emit INFO
again. The paired controller now collects them at initial, phase and publication
boundaries, rejects changes and requires identical settings across groups; these
samples do not prove continuous control of external sysctl writers.

Opt-in daemon accounting measures each translator child from pre-fork to reap,
with wait4 CPU and largest-process RSS, separately from the prepared payload.
The controller joins each record to the published entry and retains both raw
attempts and summaries. Preparation latency includes polling and settling;
translation can overlap promotion, so those intervals cannot be summed as
disjoint costs. Neither child CPU/RSS nor the process/worker-envelope difference
measures kernel queue, hostcall or pure-JIT cost. Detailed boundaries live in
the [paired flow](../bench/lock_scenarios/README.md#34-原生锁与-jit-配对实验); P2 remains open.

The separate, default-off `jit_timing` module parameter records inclusive C
intervals for dispatch, actual wrapper calls, typed hostcall dispatch and lock
control handling, plus spin/mutex physical-owner native waits, private-queue
residence and native-handoff envelopes. Selection is read-only after load; drained unload emits ten
aggregate rows. Invalid clocks/overflow invalidate measurements only, never
execution or native-replay decisions. The paired controller's ordinary mode 2/5
contract joins one body to 1/3/2/1 calls respectively, requires native-wait/handoff
rows to be zero, matches the active backend's queue samples to drained slowpath
counts and rejects missing or
inconsistent timing rows. Statistics span the whole loaded session, including
preparation; nested intervals can overlap and cumulative elapsed is not CPU or
experiment wall time. Native wait starts after publication, so it may miss a
waiter suffix prefix and includes unlock/ACK handling and scheduling. Only local
timestamp/backend values are used after the final ACK, not waiter storage. Remote
relay waits overlap; they cannot be added as disjoint costs.

The wider `native_*_handoff` starts in the backend before validated borrowing,
including before spin's remote-native publication can release an ancestor. It
ends after successful owner-wait return and before frame cleanup. Thus it covers
the early waiter work omitted by the inner wait, without adding fields or
touching waiter/node storage after publication. Handoff contains wait; matching
completed counts and nondecreasing outer elapsed totals are required. It is
not pure waiter CPU time: borrowing, publication, scheduling, unlock/ACK and
measurement overhead remain included. Remote parent/child envelopes overlap,
and code after the last source unlock returns is outside this boundary.

Each queue node has one additional 64-bit timestamp, initialized before tail
publication. A queue owner consumes it after acquiring Linux L, before running
followers or releasing its node. A combiner saves the dispatch-start endpoint,
then accounts it only after a body actually ran and before waking/releasing the
waiter. Thus body/native-suffix time is not charged to this queue interval, a
pre-body refusal retains its start, and immediate node reuse cannot double count.
This covers kdlock-published nodes, not every native/fastpath acquisition or
pre-publication refusal; mutex's nested Linux B wait remains outside this queue
metric. No frame, wrapper argument, instruction or flags contract changes.
Complete acquisition, pure native execution and observation costs remain open. Commands and
subtraction limits live in
[boundary timing](../bench/lock_scenarios/README.md#可选的-jit-边界计时).
