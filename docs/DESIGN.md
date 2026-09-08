# kdlock Design

This document describes current implementation contracts, not a chronological
test log. Usage and execution flow: [JIT_EXECUTION](JIT_EXECUTION.md).
Exact registers: [JIT_REGISTER_ABI](JIT_REGISTER_ABI.md).
Current failures and historical evidence: [VALIDATION](VALIDATION.md).
Priorities and explicit deferrals: [TODO](TODO.md).

## 1. Motivation And Scope

kdlock combines lock delegation with dynamic translation of existing kernel
critical-section machine code. A combiner executes a waiter's supported code
under real lock protection without rewriting that critical section's source.
Existing patched lock hooks are required. The current tests use purpose-built
workloads, not a validated unmodified production subsystem.

The design is inspired by TCLock-style delegation and BCD's binary execution
machinery, but adapting user execution to kernel code requires additional
ownership, context and lifetime rules. Address substitution is not a context
switch. JIT is not a security boundary, and a performance benefit remains to
be demonstrated separately from correctness tests.

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

Existing spin and mutex hook pointers pass the lock address, saved hook RSP
and return RIP. The latter is the instruction after lock acquisition.
Exact hook stack offsets are defined in the ABI document and the captured
[kernel baseline](../kernel_baseline/README.md).

`target_process` matches an exact task comm. Spin also recognizes live local
acquisition tickets; mutex recognizes active task records. These preserve
unlock routing through rename and native continuation. Eligibility affects
delegation, never which physical exclusion lock protects the data.

Hotlock sampling uses a bounded 131071-slot append-only table:
`INIT -> CHECKING -> DELEGATE/IGNORE`. After a module-wide one-billion-cycle
warmup, 10000 samples within the sampled window promote a lock. The global
initial window is 2.5 billion cycles and can shrink; each in-flight sample
captures its threshold at INIT-to-CHECKING. Another lock's promotion cannot
retroactively tighten it. New samples use the current threshold.
Spin samples lock/unlock, mutex samples lock. Decisions are sticky.
Frequency is not measured contention or a guarantee that delegation pays off.

Default work changes kdlock only. Missing hook capabilities and hook-reader
lifetime need separate assessment, not incidental guest kernel edits.

## 4. Spin Delegation Protocol

### 4.1 Native Lock And Private Queue

Linux qspinlock **L** remains the sole physical exclusion lock. kdlock uses a
separate scheduler word/tail **S** and private nodes; native and kdlock queue
encodings must never share L's tail. A scheduler handoff alone does not permit
critical-section execution: the physical executor first acquires L.

Native plain/trylock/IRQ-save/BH participants use Linux L. Their mutual
exclusion does not imply that IRQ/BH operations can be delegated; known
context-sensitive wrappers refuse translation.
The old shared-tail protocol and its compatibility claims are obsolete.

### 4.2 Acquisition Tickets And Node Lifetime

The physical hold and original waiter acquisition are different objects.
`kd_spin_hold` records real owner task/CPU/generation.
`kd_spin_ref` points into a stable origin-ticket pool with a generation.
A virtual B request carries the original HOOK waiter's `spin_origin`, while
its physical executor's acquisition ticket belongs to that executor.

Only the original waiter can end its pin/preemption obligation. A combiner
cannot remotely unpin it. Native borrow references defer completion until
the last owner ACK. These metadata do not add wrapper arguments.

Each CPU has four exact node reservations. Reserved-but-not-yet-acquired
nodes count as occupied; completion cannot release a different slot or use
a held-only count. Reservation spans every published queue pointer, saved RSP,
request and borrowed reference. Published/woken nodes may immediately be
reused; snapshot needed data before wake and never read them afterward.

### 4.3 Combiner And Native Returns

The combiner owns L and S while processing an eligible batch, validates entry
readiness/context, reconstructs waiter registers and enters a frame.
Unstarted work can receive native handoff. Partial JIT progress cannot be
converted into entry replay.

Ordinary acquisition returns restore `kd_spin_native_input.rsp`.
Nonlocal paths restore the lower of saved node RSP and virtual RSP before
copying state, preserving virtual CALL frames that grew into the old hook
frame. Completed paths end their own ticket only after taking the needed
snapshots. Return 5 means native continuation and retains the origin pin
until the final native ACK, not full completion.

The combiner eventually executes its own original critical section.
If logical A was released early, it must reacquire A first; see 9.4.

### 4.4 Nested Contention And Stack Resources

At B's lock CALL, a virtual spin waiter copies current GPR/RIP/RSP, explicit
held locks, GS/task and origin reference. A remote B combiner can execute it.
It uses the root/parent artifact with B's continuation RIP, not a separately
truncated B artifact that cannot represent A's later flow.

Logical requester/`resume_target` chains differ from physical C-frame chains.
A physical parent may wait on its own shadow stack while a child executes on
another CPU. Its C locals, frame and stack remain live until child completion.

Each shadow stack is 8 KiB; frame and held-lock depths are bounded at eight.
Frame count, logical depth, held-lock count and node reservations are distinct
resources. Sampled stack margins are not an arbitrary IRQ/NMI safety proof.
NUMA-local batching is opt-in; it is not a different physical lock protocol.

## 5. Mutex Delegation Protocol

### 5.1 Physical Lock And Scheduling Gate

`kd_mutex_shadows[]` maps original mutex addresses to 1024 bounded scheduler
entries under `kd_mutex_shadow_lock`. An entry contains a queue, `locked` gate,
and `physical_owner`. **Neither the gate nor a queue handoff grants exclusion
without the original Linux mutex being held by the tracked physical owner.**
Borrowed native execution does not change that owner; it follows the explicit
execution/unlock-notification protocol in section 5.3.
Unlock lookup never creates entries; table exhaustion uses the original mutex.
The old `delegated` transition and `mutex_origin_users` draining are removed.
There is no interval in which promotion substitutes a different exclusion lock.

The module's `kd_origin_mutex_lock/unlock()` use the existing native owner
fast paths and already-exported `__mutex_lock_slowpath` /
`__mutex_unlock_slowpath`. Ownership is checked against `current`, masking the
three native owner flag bits. kdlock does not invent an owner value, assign
ownership to the waiter, or modify native wait lists or handoff flags. This
implementation is tied to the tested non-RT 6.1.159 configuration without
DEBUG_MUTEXES/DEBUG_LOCK_ALLOC; other configurations require separate review.

Native trylock/interruptible/killable callers use the same original mutex.
Linux handles their cancellation and HANDOFF flags under its own wait lock.
They are independent native callers, not cancellable delegated requests.
The workload observers never rewrite owner flags or wait lists; bounded
signal/release tests do not cover every internal interleaving.

### 5.2 Entry, Completion, And Task Routing

1. Cold locks, `mutex_jit=0`, shadow/task-record allocation failure, and nested
   acquisitions by an already-active task go directly to the original mutex.
2. A promoted, eligible request registers its task before entering the scheduler.
   Winning the gate calls `kd_mutex_claim_origin()`, which acquires the original
   mutex and records `physical_owner=current`, before entering any CS.
3. Queued waiters capture the hook stack and waiter GS/task. Their combiner
   verifies real ownership, reconstructs `pt_regs`, checks exact entry readiness,
   and executes the translated CS in a frame. Missing code or a busy per-CPU
   frame context receives an unexecuted queue handoff. That next owner must
   acquire the original mutex; it cannot inherit exclusion from the gate alone.
4. Successful JIT execution reaches the final required unlock and completes its
   frame: normally A, or the last nested B after an earlier logical A unlock.
   The waiter snapshots published registers, releases its exact bitmap slot,
   restores preemption/migration state, drops its task record, and resumes
   after the logical unlock. The combiner can retain the original mutex across
   several requests, then run its own CS before unlocking as its real owner.
   Early A-before-B release instead detaches this batch, lets A's queue proceed,
   and requires reacquisition before the old combiner's own CS; see section 9.4.
5. `_kd_mutex_unlock_checked()` releases the original mutex before opening the
   scheduling gate. Native participants can acquire it between scheduler owners.

Each CPU has four independently reserved 8 KiB waiter stacks. An exhausted task
never publishes a queue node; it waits on its native stack for the gate and
then acquires the original mutex. Migration stays disabled during queued waits,
but preemption is temporarily enabled where scheduling or native locking is
required. A scheduled combiner retains ownership of its per-CPU frame context;
another task cannot overwrite it.

Resource tests compile the production reservation, shadow lookup, hooks and
entry/return consumer. They check no-node acquisition and copy-before-slot-reuse
with the guest's complete `pt_regs`; physical locks, scheduler, task records and
assembly are substitutes. Their scope and live-test separation are maintained
in [the mutex resource guide](JIT_EXECUTION.md#61-mutex-资源与恢复包).

`kd_mutex_tasks.c` keeps RCU-readable task membership with a task reference and
lock-protected acquisition refs. The existing mutex `is_kd` callback matches
target comm or membership. This preserves unlock routing after a rename; it
does not replace the original lock. `mutex_task_fail_once=1` tests pre-entry
allocation failure. No allocations are needed in the predicate. Unload requires
all callers stopped and records/queues drained; `rcu_barrier()` only completes
deferred task-record frees, not general hook hot-unload protection.

The opt-in `test_22` connects these real task functions to the production
native request/ACK path, with an actual RCU reader spanning final removal.
It covers both B-before-A and A-before-B unlock, shared acquisition refs and
deferred callback execution. Its constructed continuation and outer batch
callback do not exercise JIT or queue scheduling; see
[the lifecycle guide](JIT_EXECUTION.md#62-task-引用最终-ack-与-rcu).

### 5.3 Nested A -> B And Native Continuation

Nested B no longer creates a virtual mutex waiter or remote B combiner:

1. At translated `mutex_lock(B)`, validate the frame, return address, depth and
   non-recursion before touching B. Mixed spin/mutex control calls are rejected.
2. The same A combiner enables preemption while remaining migration-pinned,
   tries the original B, and waits via its native slowpath if contended.
3. Once it physically owns B, record B as `KD_EXEC_LOCK_NATIVE`. **Only then**
   consume the virtual CALL return address and resume A's artifact after the
   lock call. B need not be promoted or have a separate artifact.
4. Translated B instructions execute under real A/B ownership. Its known unlock
   releases B on the same combiner, pops the frame entry, and increments
   `nested_jit`; A continues in the same artifact until its outer unlock, or
   completes there if A was already logically released (section 9.4).

An ordinary CALL miss instead preserves exit GPRs/RIP/virtual stack and resumes
the original waiter natively. The combiner retains real A and any still-held B,
stops processing other requests, and services that waiter's unlock messages.
The waiter cannot directly unlock a mutex owned by the combiner. Native nested
unlocks release B on the actual owner; outer unlock acknowledges logical
completion while A stays held until the combiner finishes its own ownership
interval. No native `owner` handoff or new kernel protocol is introduced.

The waiter's acquisition reference survives until the combiner releases this
frame's last retained logical lock, removes its native registration, and drops
that reference before acknowledging. The final reference removes task membership;
RCU readers can retain the unlinked entry until its deferred free callback.
This logical ACK need not release physical A in a still-owned batch.
New native acquisitions by the waiter are ordinary original mutex acquisitions.
The combiner must not inspect a published waiter
node after wakeup because it can already have been released and reused.
Native continuation is counted by `kd_native`, not all-JIT completion counters;
unhandled post-entry errors remain fail-stop, never entry replay.

Signals do not transfer physical ownership or cancel a retained frame. The
ordinary native `mutex_lock(B)` suffix waits uninterruptibly, including with a
fatal signal pending. It must finish B, the remaining effects and the final A
owner ACK before Linux delivers the signal on return to userspace. The opt-in
[original-waiter signal test](JIT_EXECUTION.md#64-原-waiter-的信号与退出) checks
this bounded path and direct ordinary CALL misses to native
`mutex_lock_interruptible/killable(B)`. In the latter cases Linux returns
`-EINTR` on the original waiter: B was not acquired, so its error suffix skips
B's critical section and unlock, but still completes the borrowed A unlock
and final owner ACK. This is cancellation of a new native B acquisition, not
rollback of A or cancellation of its retained delegated frame. These APIs are
not added as translated lock controls or hostcalls. `do_exit` inside the suffix
and arbitrary abandonment remain unsupported.

Borrowed execution does not make `mutex.owner == current` true on the waiter.
Code that inspects ownership, recursively acquires a borrowed mutex, relies on
lockdep ownership, or requires task/CPU-local lock side effects is outside this
subset. It needs eligibility rejection or a separately evaluated service,
not an assignment to native owner bits.

Mode 4 uses actual independent B contention. Mode 11 is now a context-refusal
negative test, not a positive nested-JIT oracle. Current main-mode results and
the scope of the separately bounded fixtures are recorded in [VALIDATION](VALIDATION.md).

### 5.4 Differences from Spinlock Path

| Aspect | Spinlock | Mutex |
|--------|----------|-------|
| Queue structure | Per-CPU `kd_spin_node[4]` | Bitmap-reserved per-CPU `kd_mutex_node[4]` |
| Exclusion | Original Linux qspinlock L, held by the physical executor | Original Linux mutex and its actual owner |
| Scheduler state | Private S word/tail, never overlaid on L | `kd_mutex.locked/tail`, never sufficient for exclusion |
| Scheduling | Non-sleeping spin protocol | Waiters may schedule while migration-pinned |
| Nested contention | Virtual spin waiter and combiner snapshot | Same combiner waits for native B |
| OOO unlock | Owner-side A/S release, logical-parent rendezvous and ticket-preserving reclaim | Native A/S early release, same-owner B and A reacquisition after suffix |
| JIT disabled | Per-lock spin readiness policy | All mutex calls use original native protocol |


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
`kd_exe_on_call_hl_entry()` looks up `kd_get_exe(0, entry_ip)`. This avoids binding a
translation to one short-lived benchmark thread or process ID.

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
   continue execution rather than complete the frame.
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

### 7.1 Possible JIT Episode

`context_policy.jit_phase_blocks()` selects reachable decoded blocks using
entry and learned targets as roots. For an ordinary direct CALL to a callee
absent from those blocks, it retains the CALL/exit stub but removes the native
return edge. The waiter will complete that suffix without returning to this
JIT invocation.

Control calls, allowlisted hostcalls, decoded callees and indirect calls retain
their relevant successors. An alternate JIT path to a suffix keeps it in scope;
a deleted native edge must not contaminate that path's dataflow.
Every recompile rechecks the newly learned scope. Admission, lexical lock
boundaries, constant propagation, emitted blocks and entry dispatch share it.
Missing reachable branch text is not an implicitly safe empty block.
For a cross-window placeholder whose bytes are already cached, the translator
seeds the owning decoder window and recomputes the selected graph. Decoder roots
are split into dispatch blocks even when they lie inside an earlier block.
These seeds do not become independent admission roots. Text reads and decoder
reseeding share the 32-expansion bound; genuine undecodable blocks still refuse.

### 7.2 Context And Memory Admission

Production admission rejects retained GS memory, FS/base operations, known
per-CPU/current/scheduling/preemption/IRQ/BH/RCU references, backend mismatches
and other recognized unsupported context operations.
The retained GS/current lowering helpers do not imply permission to delegate
those operations. No read-only GS exception is granted.

Analysis covers explicit operands and lifted IR memory effects, including
implicit/internal-IR accesses, decoded CALL arguments/RET results and CALL
return-slot writes. Bounded facts propagate through selected CFG edges; merges
retain sensitive alternatives. Memory values, masks, alias origins and writes
are checked conservatively. It does not read runtime memory or treat source
RBP/RSP as private memory. Analysis limits affecting addresses refuse admission.

Eligible single-root nested entries can retry address-precision failures with
entry disjointness predicates. Every premise is enforced before generated body
execution; independently enterable callees cannot borrow those root facts.
For learned direct callees, a separate single-entry analysis seeds only the
checked root and propagates real CALL packets and RET effects. It removes the
fabricated immediate CALL fall-through, verifies every RET edge against the
generated whitelist, and refuses unvisited selected blocks, indirect control,
IJ history or adjusting RETs. Default independent-root analysis remains unchanged.
This does not assume callee-saved registers or untouched source memory for an
ordinary function. The predicate/continuation contract is in
[JIT_EXECUTION](JIT_EXECUTION.md#5-入口条件与嵌套续点).

This remains incomplete for arbitrary pointers, unlifted instructions and
concurrent mutation. Improving precision is not grounds for removing safety
probes. A refusal makes future entries native-only; it does not undo earlier
work or validate owner-sensitive native suffixes.

### 7.3 Build And Publication

The daemon has flat RIP and RIP/tgid workspace modes, independent of benchmark
mode. It maintains callee/indirect-target tables, reads /proc/kcore, combines
generated assembly with the wrapper, assembles/links and transfers jit.bin.
Policy refusal removes stale outputs and exits 2; launch failures/exceptions
are errors/retry conditions, not successful native-only decisions.

Images must be nonempty and fit 640 KiB. Transfers use up to 4000-byte chunks;
the last complete chunk sets NORMAL. The kernel checks entry, offset, payload
size and status, but does not establish complete image continuity/generation
or protect live executors. Recompilation overwrites the existing block.

Independent locks may share the RIP-keyed artifact; early A unlock can also
allow overlapping execution. Lock serialization is not version retirement.
Immutable versions, full publication validation and reclamation are explicitly
deferred under [C3](TODO.md#c3-immutable-jit-publication-and-lifetime).
See [daemon README](../daemon/README.md) for CLI and diagnostics.

## 8. Sandbox Code Model

### 8.1 Registers And State

The wrapper takes `pt_regs *` and exactly two words:
`{waiter kernel GS base, logical waiter task}`.
Inputs are reinstalled for every continuation. Hardware GS/current, scheduler,
IRQ/RCU state, flags and SIMD/FPU are not switched to the waiter.

Physical RSP/RBP belong to the wrapper; R13/R12 initially represent virtual
RSP/RBP. R11 is the branch-block budget. R12-R15 also form the special-register
mapping pool; ordinary instructions cannot hardcode guest R14/R15 locations.
R14 is target RIP at exit, R15 carries an IJ source. Exact slots and supported
GPR persistence are defined only in [the ABI](JIT_REGISTER_ABI.md).

### 8.2 Execution Witness And Budgets

Optional generated-body MOV instrumentation sets the reused args[1] output to
one; the wrapper initializes it to zero. The executor logs a matching positive
witness only after wrapper return. Public tests force this on; manual daemon
launches default off. A marker proves entry into generated body, not full
instruction/path coverage or version identity. Zero never authorizes replay.

Branch-ending blocks increment R11 and test bit 24; the counter resets at each
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
Module-exit diagnostics report
`exits`, `executed`, `resumed`, `rejected`, `failed`, and `limit`. Modes 2 and 5
require the first three to be equal and nonzero, and the final three to be zero.
Mode 5 additionally requires those three counts to equal both mutex
`jit_success` and `jit_resume`, proving internal sandbox continuation and final
waiter continuation occur once per delegated critical section.

The initial services are `ktime_get` and `ktime_get_ns` when those symbols are
available. They are fixed-signature, atomic-context-safe, independent of the
proxy task's `current`, and retry-safe. Variadic `printk`, sleeping APIs,
task-context-dependent APIs, and side-effecting calls are not allowed. A future
side-effecting service needs a fixed ABI and an exactly-once rule for failures
that occur after native execution.


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

### 9.1 Frames And Lock Ledger

A frame tracks backend, logical task, GS, supported registers, explicit held
locks, parent/requester links and control-call phase. Physical ownership is
not inferred from logical depth. Cross-backend controls are rejected.
Pre-entry context/resource refusal leaves valid queue/native ownership intact;
it does not grant permission to replay an executed frame.

### 9.2 A/B Execution

Spin B may enqueue a virtual request and resume remotely; mutex B is acquired
by the same A combiner. Both record the actual acquisition before consuming
the lock CALL. Inner unlock normally continues A, while final completion uses
the last required unlock return, including A-before-B execution.

### 9.3 Capacity And Refusal

Frame, logical held-lock, CPU-local shadow-held-lock and node pools have
independent limits. Capacity checks precede acquiring/publishing a new B.
A valid pre-acquisition PENDING resource failure can hand the original lock
CALL to the waiter. Already entered/acquired operations cannot use that path.

A virtual pre-entry refusal preserves the caller's full register packet and
queue connection. Already-progressed work cannot be recast as fresh native
entry. Exact node reservation and stack lifetimes persist through readmission,
child completion and native ACK; selected bounded tests are not arbitrary-depth
or arbitrary-schedule guarantees.

### 9.4 Out-Of-Order And Remote Completion

A logical unlock of A while B remains held is performed by A's real owner.
It drops A/S once, detaches the old batch and lets saved A successors progress.
B ownership is unchanged. The old combiner must reacquire A before running
its own original CS, without rereading a possibly reused old node.
Spin waits for full S availability and reuses its released ticket without
adding a new pin or switching back to a stale stack.

Remote child state is published as WAITING/NATIVE/DONE. Clear the child's
resume_target before release-publishing final DONE; do not touch the parent
after final publication. A parent with no remaining local locks still waits
for its child while keeping its frame alive.

NUMA deferred-list publication and nested-list isolation must preserve the
same ownership and completion rules. Native-aware waits must continue servicing
owner-side unlock requests, including ancestor release.
A zero-local-lock COMPLETE relay propagates the register packet only: no
extra ACK, borrowed reference or unpin. The last real lock ACK ends the origin
waiter's obligation. Deferred observation must not itself change queue state.

### 9.5 Forward Native Continuation

For an ordinary CALL miss, keep current GPRs, callee RIP and virtual CALL RSP.
The original waiter enters that callee, returns natively and finishes the suffix
without reentering this JIT invocation. Memory writes and completed B sections
remain committed; there is no transaction rollback.

The combiner retains its acquired physical locks and pauses other delegation.
The waiter borrows protection, not Linux ownership. Unlock requests return to
the physical owner and wait for ACK. The ACK resides on the waiter's native
stack; the executor drops borrow references before release-publishing done.
The spin waiter ends its origin pin only on the last ACK; a mutex waiter has
already restored migration/preemption state before entering its native suffix.
No owner may reread a released/woken node or frame. A later completion log is
not the ACK's linearization point.

Control-call phases are NONE/PENDING/ENTERED/ACQUIRED/COMPLETE. Only validated
PENDING -ENOMEM/-E2BIG before acquisition/publication can restore the original
lock callee RIP/CALL RSP while retaining current GPRs and effects.
Native registration independently admits NONE, eligible PENDING or validated
spin remote COMPLETE relay before borrowing/publishing/accounting. A still-held
A does not make later-phase failures recoverable.

If pending B is first acquired by the native waiter, B really belongs to that
waiter; earlier combiner-owned locks still use notifications. After A release,
continuation requires a consistent remaining ledger. Unhandled IJ/budget/fault
and later-phase errors fail-stop, not entry retry.

Borrowed mutex execution does not satisfy mutex.owner == current on the waiter.
Recursive acquisition, owner-sensitive code, lockdep or task-local locking
effects remain outside the supported subset; no owner-bit assignment fixes
those requirements.

### 9.6 BCD Comparison And Continuation Scope

The local BCD source inspection used revision
`dbde52c57a961a5cdb87c0212f9b032947d2df13`, not a BCD runtime test.
Its active daemon/asm/wrapper.S preserves supported registers in the waiter's
syscall pt_regs. Ordinary CALL miss retains the pushed original return address
and callee RIP; the syscall-return path resumes the updated user context.
Learning a missing callee is for future work, not an entry restart.

kdlock adopts forward progress but cannot reuse syscall return as its kernel
lock-ownership protocol. It additionally needs frames, phase validation,
physical-owner retention and native-unlock rendezvous. The old entry-register
retry and popped CALL frame were incompatible with this purpose.

Neither inspected BCD code nor kdlock's current wrapper preserves arbitrary
live arithmetic flags. Saving GPRs alone is not proof of arbitrary-fault
recovery. Supported outcomes are: native entry for unstarted work, current
callee continuation for ordinary CALL miss, validated pending-lock acquisition,
successful post-unlock return, or fail-stop for unsupported progressed state.

## 10. Kernel-Only Execution Entry

Only `kd_exe_on_call_hl_entry()` executes frame-backed spin/mutex requests.
The unused legacy futex entry, private result and unpinned task-CPU GS sampler
were removed. Historical guest futex/INT3 hooks remain untouched and unregistered.
Reintroducing userspace delegation requires a separate ABI/context/lifetime
design, not restoring an old function.

## 11. Configuration

`target_process` defaults to kd_test; `mutex_jit` defaults to 0.
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
11. **Persistent processor state is partial** — GS/current lowering helpers
    remain, but GS memory and known context operations are refused before JIT
    publication. Hardware FS/GS switching, FS operands, EFLAGS, and SIMD/FPU
    state are not supported as general cross-exit state. The optional
    `args[1]` body witness adds no processor-state restoration. See `docs/JIT_REGISTER_ABI.md`.
12. **Memory checks are incomplete** — the translator currently emits no
    effective canonical-address or bounds guard, so the JIT must not be treated
    as a security isolation boundary.
13. **Batch limits are fixed** — spin and mutex combiners process at most 1024
    waiters per round; these constants are not module parameters.
14. **Flags can be clobbered inside JIT** — entry predicates, dispatcher comparisons and inserted
    branch-block `INC`/`TEST` are not transparent to live flags. No liveness
    verifier enforces the restriction, even without a wrapper exit.
15. **Continuation is not rollback** — see 9.5; completed stores and child
    sections are retained. Register entry retry is limited to not-started work.
16. **Publication and lifetime are incomplete** — code is overwritten in place;
    no generation/refcount retirement handles concurrent execution, module-text
    unload/reload, or reused lock addresses. Hook removal uses
    `synchronize_rcu()`, but guest hook callers do not implement a matching
    reader/drain protocol. Stop all callers and drain queues before unloading.
17. **Scope is narrower than all kernel lock APIs** — delegation supports plain
    raw spin lock/unlock and non-RT mutex lock/unlock. Native mutex participants
    include non-target tasks and successful trylock/interruptible/killable calls;
    those alternate acquisitions are not themselves delegated. Controlled native
    interruptible/killable cancellation while the combiner retains L is tested,
    including head/non-head removal and survivor progress. Bounded native
    signal/release races also cover observed acquisitions/cancellations and
    real HANDOFF requests, not every internal removal/handoff interleaving.
    Separate original-waiter tests cover uninterruptible native B waiting and
    direct cancellable B CALL misses after JIT progress. Cancellation skips B,
    not A's completed stores or final owner ACK; it is not arbitrary delegated
    request cancellation or exit inside a native suffix.
    Arbitrary cancellation schedules, WW/PI/RT mutexes, irqsave/bh and
    lock-address reuse need separate work.
    Known mixed spin/mutex references in the discovered CFG now refuse before
    codegen using registered entry kind. Unresolved targets/callees can still
    hide such calls; the runtime backend guard remains fail-stop if reached
    after JIT entry. This is not complete call-graph or native-suffix safety.
