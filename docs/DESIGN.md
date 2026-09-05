# kdlock Design Document

Documentation/source audit: 2026-09-05, against `ed00edb` and the guest's patched
Linux 6.1.159 lock hooks. This describes a tested research prototype, not a
general correctness or performance guarantee. Implementation priorities and
acceptance criteria are in [TODO.md](TODO.md).

## 1. Motivation & Background

Modern multicore systems suffer from severe lock contention in the kernel.
When multiple cores compete for the same spinlock or mutex, transfer of modified
lock-protected data can become a major cost, depending on the workload.

**Lock delegation**, as used by
[TCLocks (OSDI 2023)](https://www.usenix.org/conference/osdi23/presentation/gupta),
lets a lock holder (the *combiner*) execute queued waiters' critical sections.
Batching can retain protected data near the combiner; it does not eliminate
queue traffic, cache eviction, or transfers between batches.

**Binary-compatible delegation**, as described by
[BCD (PPoPP 2026)](https://ppopp26.sigplan.org/details/PPoPP-2026-papers/29/Binary-Compatible-Critical-Section-Delegation),
uses kernel support at futex boundaries to supervise delegated userspace
instructions without rewriting application binaries. kdlock reuses translation
machinery for a different target: kernel critical sections entered through
patched spinlock/mutex hooks. BCD's userspace correctness claims do not establish
the safety of this kernel adaptation.

**kdlock** combines these two ideas in kernel space:

1. A patched kernel spinlock/mutex path calls into a loadable module.
2. The module records the critical-section entry address (the return address
   after `spin_lock` / `mutex_lock`).
3. A userspace daemon translates that instruction stream into a JIT sandbox
   binary using miasm-based disassembly.
4. The kernel module executes the sandbox on behalf of queued waiters, achieving
   lock delegation without rewriting the critical-section source. The kernel
   lock implementation still needs patches, and the current validation uses
   purpose-built workload code rather than unmodified production subsystems.

The key mechanism is that the sandbox virtualizes RSP/RIP-sensitive operations:
supported register state is passed through `struct pt_regs`, waiter per-CPU GS
accesses are lowered to explicit addressing, and control flow is redirected
through generated dispatch tables. This lets a combiner execute another
thread's supported critical section without a full context switch. General
translated-memory bounds checking is not complete, so this sandbox is not a
security isolation boundary.

## 2. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Patched Linux Kernel                          │
│                                                                     │
│  spin_lock(L) ──► kd_raw_spin_lock hook ──► kdlock_km.ko           │
│  mutex_lock(L) ──► kd_mutex_lock hook ──► kdlock_km.ko             │
└─────────────────────────────────────────────────────────────────────┘
         │                                          │
         │ (1) Record CS entry RIP                  │ (3) Execute JIT sandbox
         ▼                                          ▼
┌─────────────────┐                    ┌──────────────────────────┐
│  /dev/kd_dev    │◄── poll ───────────│  exe.c: code_block pool  │
│  (char device)  │                    │ kd_exe_on_call_hl_entry()│
└────────┬────────┘                    └──────────────────────────┘
         │                                          ▲
         │ (2) Translate                            │ write jit.bin
         ▼                                          │
┌─────────────────────────────────────────────────────────────────────┐
│                        Userspace Daemon                              │
│                                                                     │
│  daemon.c ──► disassem.py (miasm) ──► wrapper.S + jit.S ──► jit.bin│
│              read /proc/kcore         assemble & link               │
└─────────────────────────────────────────────────────────────────────┘
```

The system operates in three phases:

| Phase | Component | Action |
|-------|-----------|--------|
| Hook | kd_lock.c | Intercept lock calls, promote hot locks, record CS entry RIP |
| Translate | daemon + disassem | Read kernel text, disassemble, emit sandbox assembly, produce binary |
| Execute | exe.c + kd_spinlock.c/kd_mutex.c | Combiner runs JIT sandbox with waiter's pt_regs |

## 3. Kernel Hook Layer

### 3.1 Patched Kernel Interface

The guest kernel is patched to export function pointers at the spinlock and mutex
fast paths.  When a target process acquires or releases a lock, the kernel calls
through these pointers:

```c
// Exported by patched kernel, installed by kdlock_km.ko
extern void (*kd_raw_spin_lock)(raw_spinlock_t *lock,
                                unsigned long ret_rsp,
                                unsigned long ret_addr);
extern void (*kd_raw_spin_unlock)(raw_spinlock_t *lock,
                                  unsigned long ret_rsp,
                                  unsigned long ret_addr);
extern void (*kd_mutex_lock)(struct mutex *lock,
                             unsigned long ret_rsp,
                             unsigned long ret_addr);
extern void (*kd_mutex_unlock)(struct mutex *lock,
                               unsigned long ret_rsp,
                               unsigned long ret_addr);
```

- `ret_rsp`: the caller's stack pointer at the lock call site.  This is the
  base address of the saved callee-saved register frame.
- `ret_addr`: the return address — i.e., the first instruction of the critical
  section that follows the lock acquisition.

### 3.2 Target Process Matching

The module parameter `target_process` specifies which process name should be
intercepted. The patched spin path calls `is_kd_test()` and the mutex path calls
`is_kd()`; both point to `__is_kd_test()`, which compares
`current->comm` with this single exact name. Only matching processes enter the
delegation path; all others use the original kernel lock implementation.

This is a workload selector, not a per-lock compatibility protocol. In
particular, a promoted shadow mutex and its original Linux mutex are distinct
locks. `mutex_origin_users` drains only acquisitions registered through the
hook; it cannot exclude an unhooked task entering the original mutex after
promotion. Mixed users can therefore violate mutual exclusion, even with
`mutex_jit=0`. Tests use controlled lock participants. Process renaming and
other lock API variants also require a routing audit before wider use.

### 3.3 Hot-Lock Promotion

Not every lock is worth delegating. `kd_hotlock.c` keeps a bounded, append-only,
open-addressed table and implements this promotion pipeline:

```
KD_HOTLOCK_INIT -> KD_HOTLOCK_CHECKING -> KD_HOTLOCK_DELEGATE
                                           -> KD_HOTLOCK_IGNORE
```

Sampling begins after a module-wide one-billion-cycle warmup. A lock address
starts in `INIT`; its first sampled access moves it to `CHECKING`. If 10,000
samples arrive within an adaptive cycle window that initially equals 2.5
billion cycles, the lock becomes `DELEGATE`. Reaching the window first makes it
`IGNORE`. The 131071-slot table uses bounded linear probing under a raw spinlock
and fails closed when full, so a hook cannot loop forever in atomic context.

The signal is access frequency, not measured contention or delegation benefit.
Spin hooks count both lock and unlock events; mutex sampling is in the lock
hook. `IGNORE` and `DELEGATE` are sticky, and the window adapts globally rather
than independently per lock. Table synchronization also adds shared hot-path
traffic. Promotion is a heuristic, not evidence of acceleration.

### 3.4 Hook Implementation (kd_lock.c)

```c
void __kd_raw_spin_lock(raw_spinlock_t *lock, unsigned long ret_rsp,
                        unsigned long ret_addr)
{
    if (!kd_hotlock_is_promoted((unsigned long)lock)) {
        kd_hotlock_record((unsigned long)lock);
        origin_raw_spin_lock(lock);  // fallback
        return;
    }
    kd_exe_add(0, ret_addr);  // kernel CS translations use a RIP-only key
    kd_spin_lock((struct qspinlock *)lock, ret_rsp);
}
```

The mutex hook additionally maps `struct mutex *` to a shadow `struct kd_mutex *`
via a hash table (`kd_mutex_shadows[]`), since the delegation protocol requires
its own queue structure separate from the kernel's mutex internals.

## 4. Spinlock Delegation Protocol

### 4.1 Architecture (ported from TCLocks komb.c)

The spinlock delegation uses a per-CPU MCS-style queue:

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ node[cpu0]│────►│ node[cpu1]│────►│ node[cpu2]│────► NULL
│ (combiner)│     │ (waiter) │     │ (waiter) │
└──────────┘     └──────────┘     └──────────┘
```

- **Fastpath**: `atomic_cmpxchg_acquire(&lock->val, 0, 1)` — uncontended acquire.
- **Midpath**: pending-bit optimization for the second contender.
- **Slowpath**: enqueue into MCS queue, spin on `node->locked`.

### 4.2 Combiner Execution Model

When a thread reaches the head of the queue and finds waiters behind it, it
becomes the **combiner**:

1. Set `lock->locked = _Q_LOCKED_COMBINER_VAL` (3).
2. Record the lock in `shadow_stack.lock_addr[j]` for OOO tracking.
3. For each queued waiter, call `execute_cs(lock, waiter_node)`.
4. On success, mark the waiter as completed (`clear_locked_set_completed`).
5. After the batch, pass the lock to the next unprocessed waiter.

### 4.3 JIT Sandbox Execution (execute_cs)

```c
static int execute_cs(struct qspinlock *lock, struct kd_spin_node *curr_node)
{
    if (!kd_exe_is_ready(0, curr_node->regs.ip))
        return KD_EXE_NO_RUN;

    retry_regs = curr_node->regs;
    frame = kd_exec_frame_push(..., curr_node->gsbase,
                               curr_node->task_struct_ptr);
    import_combiner_and_lock_stack(frame, curr_node);
    ret = kd_exe_on_call_hl_entry(&frame->regs, frame->entry_ip,
                                  frame->outer_lock_addr);

    if (ret == KD_EXE_RUN_TO_UNLOCK)
        complete_frame_once(frame);
    else {
        release_nested_locks_in_reverse_order(frame);
        restore_combiner_state(frame);
        curr_node->regs = retry_regs;
        curr_node->jit_retry = true;
        disable_jit_for_lock(lock);
    }
    pop_frame(frame);
    return ret;
}
```

Native waiters first import callee-saved registers from the saved hook stack and
use the kernel GS base captured on their origin CPU. Nested virtual waiters
already carry a complete `pt_regs` snapshot and inherit the parent's GS base,
logical task, and explicit `kd_exec_frame`; they do not reconstruct guest state
from the combiner's `current`. The virtual waiter's `jit_context` is still
stack-owned, so the suspended combiner stack must remain alive until completion.
Restoring `retry_regs` above does not restore memory written by the JIT (9.5).

The stack frame layout at `ret_rsp` (set by the compiler at the hook call site):

```
[ret_rsp + 0x00]: (padding/alignment)
[ret_rsp + 0x08]: RBX
[ret_rsp + 0x10]: R12
[ret_rsp + 0x18]: R13
[ret_rsp + 0x20]: R14
[ret_rsp + 0x28]: R15
[ret_rsp + 0x30]: RBP
[ret_rsp + 0x38]: RIP (return address = CS entry)
```

### 4.4 Waiter Wake-up Paths

After `execute_cs` returns, the waiter is woken via `clear_locked_set_completed`:

| Return value | Meaning | Waiter action |
|---|---|---|
| `ret_val == 0` | Uncontended acquire | Normal return |
| `ret_val == 1` | Parent lock was released OOO | Restore the actual node's saved context |
| `ret_val == 2` | Became queue owner/combiner | Normal return (runs own CS) |
| `ret_val == 3` | CS was delegated | Restore with `jump_to_saved_regs()` |
| `ret_val == 4` | JIT failed; waiter acquired natively | Resume CS with `jump_to_saved_regs_in_cs()` |

### 4.5 Out-of-Order (OOO) Unlock

When locks are released out of order (e.g., Acquire(A), Acquire(B), Release(A),
Release(B)), the unlock for A happens while B's combiner is still running:

1. `kd_spin_unlock` searches `lock_addr[]` for the lock.
2. If `my_idx < max_idx` (not the innermost tracked lock), set
   `lock->locked = _Q_UNLOCKED_OOO_VAL` (7).
3. The combiner detects this value after `execute_cs` returns and handles the
   early unlock by waking the appropriate waiter.

### 4.6 Shadow Stack

Each CPU has a per-CPU `shadow_stack` (8KB, vmalloc'd) used by:
- **Waiters**: switch to shadow stack while spinning, so IRQ handlers don't
  corrupt the original stack.
- **Combiners**: use shadow stack during delegation to handle nesting.

The `kd_spin_lock_slowpath` function saves the real RSP to `node->rsp`, switches
to the shadow stack, runs the slowpath logic, then restores the original RSP
before returning.

## 5. Mutex Delegation Protocol

### 5.1 Shadow Table

Each `struct mutex *` from the kernel is mapped to a `struct kd_mutex *` via
`kd_mutex_shadows[]` (1024-entry hash table with linear probing, protected by
`kd_mutex_shadow_lock`).  The shadow lock has its own queue and state
independent of the kernel mutex internals.

The lock path uses a create-or-find lookup: once hot-lock promotion routes a
mutex through kdlock, `__kd_mutex_lock()` allocates or reuses the corresponding
shadow entry.  The unlock path is lookup-only: `__kd_mutex_unlock()` calls
`find_kd_mutex_shadow()` and falls back to `origin_mutex_unlock()` when no entry
exists.  This prevents ordinary unlocks for never-delegated mutexes from
permanently consuming slots in the fixed-size shadow table.

### 5.2 Base Protocol

```c
void _kd_mutex_lock(struct kd_mutex *lock, ...)
{
    if (cmpxchg(&lock->locked, 0, 1) == 0)
        return;

    migrate_disable();
    preempt_disable();
    node = reserve_per_cpu_bitmap_slot();
    if (!node)
        wait_and_acquire_without_entering_the_queue(lock);
    else {
        capture_waiter_registers(node);
        run_queue_on_node_private_shadow_stack(lock, node);
        release_exact_bitmap_slot(node);
    }
    preempt_enable();
    migrate_enable();
}
```

The mutex combiner reconstructs `pt_regs` from the waiter's saved hook stack and
calls `kd_exe_on_call_hl_entry()`. Because translated mutex execution remains
experimental, `mutex_jit` defaults to 0. In this non-JIT mode `execute_cs()`
returns `KD_EXE_NO_RUN`, and the combiner hands ownership to the waiter without
marking its critical section complete.

This avoids translated execution, but still uses the shadow queue and retains
the mixed-participant restriction in 3.2.

With `mutex_jit=1`, every translated waiter owns a `kd_exec_frame` containing
its original mutex address, registers, and lock ownership. Only an exact outer
`mutex_unlock` followed by valid frame completion can publish success. A
post-unlock invariant failure is fail-stop: retrying natively at that point
would duplicate already committed side effects.

Completion uses release/acquire ordering. The waiter snapshots the completed
node's `pt_regs` while migration and preemption remain disabled, releases the
exact slot, restores scheduler state, and jumps to the instruction after its
translated `mutex_unlock`. Every one of the four per-CPU slots owns an
independent 8KB shadow stack. Exhaustion stays outside the delegation queue and
acquires the shadow mutex from the native task stack.

The saved `mutex_lock` frame has the same six callee-saved register offsets as
the raw-spin path; this layout is verified against the guest kernel
disassembly. Waiter slots are bitmap-reserved rather than managed through the
old shared `nodes[0].count`, so a scheduled task cannot release or overwrite a
different live slot.

### 5.3 Nested A -> B Mutex Proxy

Mode 4 extends the base protocol instead of using the old trylock-only adapter:

1. When translated A reaches `mutex_lock(B)`, the known-call handler consumes
   the call return address and records A's post-call continuation.
2. An uncontended B is acquired directly and recorded in A's frame as `FAST`.
3. If B is contended, kdlock reserves another mutex node and creates a virtual
   waiter. Its stack-owned JIT context copies A's register state and lock stack,
   then appends B as `QUEUE_OWNER`.
4. The B queue treats this node like a native waiter. A B combiner creates a
   child execution frame from the copied A/B state and runs the translated code
   after `mutex_lock(B)` until the exact `mutex_unlock(B)` endpoint.
5. B publishes the resulting registers and wakes the suspended A combiner. A
   advances past that B unlock and continues the original translated section
   toward `mutex_unlock(A)`; it does not acquire or execute B a second time.
6. If the current task becomes B's queue owner instead of being remotely
   completed, A records B locally and the translated `mutex_unlock(B)` releases
   it normally. Abort cleanup releases locally retained nested mutexes in
   reverse order before A falls back.

The parent A frame remains in a per-CPU execution context while its task may
schedule. The context records `current` as owner; another task scheduled on the
same CPU cannot reuse it and receives normal queue handoff instead. The virtual
waiter's inherited context lives on the migration-pinned combiner stack until B
publishes completion, avoiding both lifetime ambiguity and a large per-CPU
module allocation.

Translation readiness is checked independently for A and B. Mode 4's recovery
test first translates the two exact return addresses, then uses seven
CPU-pinned roles to create holder -> direct -> nested -> trailing queues on both
locks. Passing requires two JIT completions plus `nested_queued` and
`nested_remote` evidence, exact counter accounting, and no protocol failures or
resource leaks. Current measured results are recorded in `VALIDATION.md`.

### 5.4 Differences from Spinlock Path

| Aspect | Spinlock | Mutex |
|--------|----------|-------|
| Queue structure | Per-CPU `kd_spin_node[4]` | Bitmap-reserved per-CPU `kd_mutex_node[4]` |
| Lock state | `qspinlock.val` (atomic) | `kd_mutex.locked` (u8) |
| Tail encoding | In `qspinlock.tail` field | In `kd_mutex.tail` pointer |
| Scheduling | Non-sleeping spin protocol | Waiters may schedule while migration-pinned |
| Nested contention | Virtual spin waiter and combiner snapshot | Virtual mutex waiter and inherited frame context |
| OOO unlock | Tested patterns via bounded `lock_addr[]` | LIFO nested unlock; reverse cleanup on abort |

## 6. JIT Execution Engine (exe.c)

### 6.1 Code Block Management

At module init, `kd_exe_init()` pre-allocates a pool of 64 executable memory
blocks (each 160 pages = 640KB).  These are vmalloc'd and marked executable via
`set_memory_x()`.  When `kd_exe_add()` is called from the lock hook (possibly
with IRQs disabled), it takes a block from the pool without calling vmalloc.
Only blocks for which both allocation and `set_memory_x()` succeeded enter the
pool. Pool or translation-table exhaustion fails closed.

The full executable pool is 40 MiB. These blocks remain writable; there is no
RW-staging/RX-publication transition or code-generation lifetime protocol.

Kernel critical-section text is shared across all tasks, so kernel-lock JIT
entries use a **RIP-only key**: the hook calls `kd_exe_add(0, ret_addr)` and
`kd_exe_on_call_hl_entry()` looks up `kd_get_exe(0, entry_ip)`. This avoids binding a
translation to one short-lived benchmark thread or process ID.

The translation hash probes at most `KD_MAX_EXE` slots. It returns `NULL` when
full rather than looping in atomic/IRQ-disabled context. Code-block allocation
uses an atomic gate and never waits for the userspace daemon.

### 6.2 Entry Lifecycle

```
KD_EXE_UNUSED -> KD_EXE_UNINIT -> KD_EXE_NORMAL
                                      |  ^
                 daemon recompiles   |  | complete write-back
                                      v  |
                        KD_EXE_CALL_MISS / KD_EXE_IJ_MISS

KD_EXE_NORMAL -> KD_EXE_ERROR_INST  (terminal unsupported instruction)
```

`KD_EXE_HOSTCALL` is deliberately absent from this lifecycle. It is a transient
sandbox exit reason handled synchronously by the kernel executor, not a
translation-entry state observed by the daemon.

### 6.3 kd_exe_on_call_hl_entry()

This is the core execution function called by the combiner. Its actual signature
is:

```c
int kd_exe_on_call_hl_entry(struct pt_regs *regs, unsigned long entry_ip,
                            unsigned long outer_lock_addr);
```

1. Validate the active frame, waiter GS/task, and exact `(0, entry_ip)` readiness.
2. Install the two inputs `{frame->gsbase, frame->logical_task}` and enter the
   wrapper.
3. On hostcall, enforce budgets, dispatch the typed service, pop the virtual
   return address, save continuation state, and re-enter the same artifact.
4. On a control-call exit, use `handle_known_call()` to acquire/release nested
   locks or recognize the matching outer unlock. Nested and OOO handling may
   continue execution rather than complete the frame.
5. On a miss, unsupported exit, or exhausted budget, return failure. The lock
   backend decides cleanup and waiter handoff; this function does not roll back
   writes or undo services.

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

## 7. Dynamic Translation Pipeline

### 7.1 Daemon (daemon/daemon.c)

The daemon runs in userspace and polls `/dev/kd_dev`:

1. **Read**: get array of `kd_exe_info` entries from the kernel.
2. **Dispatch** based on `status_code`:
   - `KD_EXE_UNINIT`: create an isolated `asm/` workspace, initialize empty
     callee/IJ tables, and run the first translation.
   - `KD_EXE_CALL_MISS`: append target to `callee_table.txt`, recompile.
   - `KD_EXE_IJ_MISS`: append `(from, target)` to `ij_table.txt`, recompile.
3. **Compile**: invoke `disassem.py` which produces `asm/jit.S`.
4. **Assemble**: `wrapper.S` includes `jit.S`, assembled into `jit.bin`.
5. **Write**: reject empty or over-640-KiB images, then send `jit.bin` through
   `/dev/kd_dev` in checked chunks (max 4000 payload bytes) with `kd_recv_pkt`
   headers. The daemon requests `KD_EXE_NORMAL` on its final chunk only; kernel
   transfer and concurrency limitations are described in 7.3.

### 7.2 Translator (disassem/disassem.py)

The miasm-based translator:

1. Reads raw kernel bytes from `/proc/kcore` at the target RIP (`memread.py`) and
   logs only entry/target/region/byte counts, never the raw bytes.
2. Loads `include/kd_hostcalls.def`, resolves available service symbols, and
   excludes those targets from callee-table expansion.
3. Resolves the x86 per-CPU `current_task` offset from `/proc/kallsyms`.
4. Disassembles into a control-flow graph using miasm's `dis_multiblock`.
5. Initially stops disassembly at `_raw_spin_unlock` in
   `dont_dis_retcall_funcs`; `mutex_unlock` is not in that set. Explicitly adds
   discovered resumable control/hostcall fall-through blocks. The fetched CFG
   can include post-unlock code; runtime outer-lock matching defines completion.
6. Preflights segment operands in the discovered CFG and rejects undecodable/empty
   blocks inside fetched translation ranges. Out-of-range bad blocks are CALL
   miss placeholders. Unsupported FS/base-register operations, including raw
   encodings that miasm 0.1.5 misdecodes, or unsupported `current_task` forms
   produce a terminal `KD_EXE_ERROR_INST` artifact before any partial
   translated side effect runs.
7. For each basic block, translates instructions via `translation.py`:
   - Normal instructions: register conflict resolution and operand rewriting.
   - Generic `%gs:` memory operands: explicit waiter-GS-base addressing.
   - `%gs:current_task`: logical waiter task substitution.
   - Branches: translated to sandbox-local jumps.
   - Special instructions: handled by `special_inst.py`.
8. Handles indirect jumps (`indirect_jump.py`): builds jump tables, reports
   misses.
9. Emits distinct control-call, hostcall, and ordinary call-miss stubs.
10. Outputs `asm/jit.S` which is included by `wrapper.S`.

### 7.3 Incremental Recompilation

When the sandbox hits an untranslated call or indirect jump at runtime:

1. Kernel sets `exe->status_code = KD_EXE_CALL_MISS` (or `IJ_MISS`) and records
   `exe->tgt_addr` / `exe->jump_from`.
2. Daemon reads this on next poll, appends to the callee/IJ table.
3. Daemon re-runs `disassem.py` which now includes the new target in its
   disassembly scope.
4. New `jit.bin` is written back, overwriting the code block.
5. Entry returns to `KD_EXE_NORMAL`.

The write path validates the entry key, destination block, offset, payload
length, and requested status. It publishes `KD_EXE_NORMAL` with release semantics
after copying the chunk marked final. Only the daemon knows the total length;
the kernel does not verify complete coverage, chunk order, or image generation.
The `install JIT chunk` log precedes even key validation and payload copying.
Execution checks readiness with acquire semantics, but an already running
executor can still reference the overwritten block. A concurrent read of an
entry's status/target fields is not a versioned coherent miss snapshot either.
Thus release/acquire is not an immutable-artifact replacement protocol.

A combiner does not wait for recompilation: a miss returns failure, the backend
cleans up lock/frame state and hands ownership to the waiter for entry retry.
Spin JIT is then disabled for that outer lock; mutex has no equivalent sticky
per-lock disable. Neither path rolls back data writes (9.5).

An allowlisted hostcall never enters this recompilation sequence. It leaves the
entry in `KD_EXE_NORMAL`, executes synchronously in the kernel, and resumes the
same artifact at the saved post-CALL RIP.

## 8. Sandbox Code Model

### 8.1 Register Convention

The register assignment is phase-specific. R14/R15 carry the two C arguments
only during the wrapper prologue and epilogue; translated code reuses them after
the pointers have been saved in wrapper stack slots:

| Physical register | Translated-code role | Notes |
|----------|-------------|-------|
| RSP / RBP | Wrapper real stack/frame | Never represent guest RSP/RBP |
| R13 | Virtual RSP | Stable mapping, temporarily borrowable by the register mapper |
| R12 | Virtual RBP | Stable mapping, temporarily borrowable by the register mapper |
| R14 | Special-register pool / RIP target | Carries RIP or target at dispatch and exit boundaries |
| R15 | Special-register pool / IJ source | Carries source RIP on an indirect-jump miss |
| R11 | Basic-block budget counter | Guest R11 is kept in a spill slot/mapped through R12-R15 |

RAX, RBX, RCX, RDX, RSI, RDI, and R8-R10 directly represent their guest
counterparts. Guest R11-R15, RIP, RSP, RBP, waiter GS (`RGS`), and logical
current task (`RCT`) are virtual registers managed by `disassem/conflict.py`;
ordinary translated instructions must not assume a fixed physical location for
them. The complete current convention, including stack slots, exit values,
hostcall continuations, flags, segment lowering, and waiter resume behavior, is
specified in `docs/JIT_REGISTER_ABI.md`.

### 8.2 Wrapper (include/wrapper.S)

The wrapper provides prologue/epilogue around the translated code:

**Prologue:**
1. Save callee-saved registers (standard C ABI).
2. Load `pt_regs` pointer into R14, args pointer into R15.
3. Load directly mapped GPRs from `pt_regs` and copy guest RSP, RBP, R11-R15
   into wrapper stack slots.
4. Copy `args[0]` to `Stack_RGS` and `args[1]` to the reused
   `Stack_TASK`/`Stack_RCT` slot. No third input or extra physical slot exists.
5. Initialize the reserved `Stack_INST_CNT` output to zero.
6. Initialize R13 = virtual RSP and R12 = virtual RBP.
7. Set R11 to the block-budget counter, load the requested RIP into R14, and
   dispatch to the matching translated entry/continuation label.

**Epilogue (exit label):**
1. Save current R14 (RIP), R13 (RSP), R12 (RBP) back to stack slots.
2. Reload `pt_regs` and args pointers.
3. Write return code (`Stack_IJ`) into `args[0]`:
   - `0x0` = `KD_EXE_NORMAL` (syscall encountered)
   - `0x1` = `KD_EXE_CALL_MISS`
   - `0x3` = `KD_EXE_ERROR_INST`
   - `0x4` = `KD_EXE_INST_LIMIT`
   - `0x5` = `KD_EXE_HOSTCALL`
   - Other = indirect jump source address (`KD_EXE_IJ_MISS`)
4. Write the reserved zero `Stack_INST_CNT` value into `args[1]`.
5. Write final RIP into `pt_regs->ip`.
6. Write the supported GPR/RIP/RSP state back to `pt_regs`; EFLAGS, hardware
   segment-base state, and SIMD/FPU state are not restored by the wrapper.
7. Restore callee-saved registers and return.

`args[1]` remains a reserved output and is always zero. It is not the R11 block
budget and must not be consumed as an execution counter.

### 8.3 Memory Access Check Status

`normal.py` does not emit canonical-address or bounds guards for translated
memory operands. Segment-policy failures return `KD_EXE_ERROR_INST`, but that
does not make the JIT a security boundary. Effective-address validation and
the EFLAGS preservation it requires remain explicit implementation gaps.

### 8.4 Kernel GS And Logical Current

The two wrapper inputs are exactly `{waiter kernel GS base, logical waiter
task}`. A top-level spin or mutex waiter captures both when it queues; a nested
waiter inherits both from its parent frame. Hostcall and known-call continuation
reinstall the same pair before re-entering the artifact. The legacy futex path
samples `task_cpu(task)` to obtain a kernel GS base and passes that task as
logical current; it has no in-tree frontend guaranteeing task lifetime or CPU
stability.

The translator never changes the combiner's hardware GS base. It rewrites
generic `%gs:offset` reads, writes, and RMW instructions to ordinary memory
operands based on the captured GS value. A 64-bit MOV source at the resolved
`current_task` per-CPU offset instead reads the logical task input, so proxy
execution observes the waiter rather than the combiner. Writes/RMW to
`current_task`, `%fs:` operands, direct FS/GS base instructions (including
`SWAPGS`), and unsupported segment prefixes fail closed before normal
translated code executes. Segment prefixes used only as alignment-NOP pseudo
operands are discarded.

Modes 10 and 11 validate this contract for nested spinlock and nested mutex
proxying. They require artifacts containing both virtual inputs, no live
hardware segment operand, actual translated execution, exact per-CPU
read/write/RMW results, logical-current identity, and zero mismatch counters.

Address equivalence is not execution-context equivalence. A remote access to an
origin CPU's per-CPU area can race with local operations on that CPU; pinning
the waiter does not stop interrupts or other scheduled tasks. Linux explicitly
warns that remote writes can interfere with local non-locked `this_cpu` RMW.
See the [kernel this_cpu documentation](https://www.kernel.org/doc/html/latest/core-api/this_cpu_ops.html).
Logical `current` substitution also does not switch scheduler, RCU, preemption,
or IRQ state, and native handlers run in the combiner's real context. The
synthetic GS tests do not establish safe arbitrary per-CPU writes.

### 8.5 Instruction Count Limit

Translated blocks classified as ending in a branch increment R11. When
`R11 & 0x1000000` is set (roughly 16M counted branch blocks in one wrapper
invocation), the sandbox jumps to `inst_limit`. R11 is reset on every re-entry,
so this is neither a precise instruction counter nor a whole-critical-section
budget.

### 8.6 Call Translation

Function calls are assigned to four disjoint policies:

| Class | Examples | Behavior |
| --- | --- | --- |
| Control | lock/unlock functions | Preserve the virtual CALL frame and use nested-lock or end-point handling. |
| Hostcall | allowlisted time API | Exit with the CALL frame, execute its typed handler, and resume. |
| Translatable | discovered callee | Report a miss, unwind for native retry, record the target, and recompile. |
| Unsupported | unresolved or rejected target | Fail closed; never invoke an arbitrary address as a service. |

### 8.7 Native Hostcalls

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

### 8.8 Complex Workload Correctness Oracle

The synthetic workload does not use a single increment as its only translated
side effect. Every lock protects one of seven independent `kd_cs_state` objects
(global/A/B/C spin states and global/A/B mutex states). Each acquisition updates
a sequence, cumulative sum, odd/even branch mix, rotating checksum, one of four
dynamically indexed lanes, and a final commit value before incrementing the
legacy global counter. The compiled critical section therefore includes
dependent loads/stores, a conditional branch, `ROL`, `IMUL`, and scaled-index
memory addressing.

At workload-module unload, native code starts from zero and replays the observed
number of transitions for every active lock. It compares every field, sums all
per-lock operation counts, and requires that sum to equal `global_counter`. The
integration tests require both an exact expected operation count and
the expected number of independently protected active states, plus `failures=0`
in the `kd_cs integrity` report. This detects many errors that a lone increment
could miss: partial or duplicate execution, updates assigned to the wrong lock,
incorrect branch state, and resuming at the wrong IP.

Since workers apply the same deterministic transition, this is not a
per-request exactly-once or linearizability oracle: a duplicated request and a
skipped request with the same net transition count may be indistinguishable.

Artifact checks inspect only executable generated assembly, excluding source
comments. They require the four-lane selector plus a conditional jump, rotate,
multiply, and indexed access. Constants that the compiler hoists before the lock
are deliberately not required inside the artifact; their correctness is covered
by the initial-register ABI and the runtime replay result.

## 9. Nested Spinlock JIT Handling

### 9.1 Execution Frames

Every delegated spin critical section owns a per-CPU `kd_exec_frame`. The frame
stores its complete `pt_regs`, entry and continuation RIP/RSP, waiter GS base,
logical waiter task, parent frame, outer lock, lock ownership kind, held-lock
stack, and a snapshot of TCLock's combiner state. Frames and lock stacks are
bounded at eight entries.

Unlike the old adapter, this state survives suspension of A while B enters its
own fastpath, MCS queue, or combiner. Guest continuation is explicit rather than
inferred from a native return chain. The inherited `jit_context` still lives on
the suspended combiner's stack, which must remain valid until the nested waiter
returns.

### 9.2 A -> B Protocol

When translated critical section A reaches `_raw_spin_lock(B)`:

1. `handle_known_call()` saves the post-call virtual continuation.
2. Repeated B acquisition is rejected with `-EDEADLK`.
3. If B is promoted, `kd_spin_nested_lock()` tries B's kdlock fastpath and then
   its normal MCS/combiner protocol. It does not call the original raw-spinlock
   path.
4. B is recorded as `FAST` or `QUEUE_OWNER` when this frame owns it. If another
   combiner executes B's critical section remotely, its updated registers are
   restored into A and execution resumes after B's unlock.
5. If B is not promoted, it is deliberately acquired as `NATIVE`, recorded in
   the same frame, and included in the same reverse-order cleanup rules.
6. `_raw_spin_unlock(B)` performs normal kdlock handoff/OOO processing. Only
   `_raw_spin_unlock(A)` can complete A, and only after all nested locks are
   released.

The same protocol recursively supports A -> B -> C up to the configured frame,
lock-stack, and node limits.

### 9.3 Queue and Capacity Rules

Each CPU has four MCS nodes. Native node exhaustion uses direct trylock spinning
without incrementing the retained node count. Nested JIT node exhaustion
returns `-E2BIG`; the enclosing frame aborts and the outer waiter retries
natively. Frame or lock-stack exhaustion also aborts rather than executing with
partial state.

The same lock may not appear twice in one execution frame. kdlock returns
`-EDEADLK`; recursive spinlock semantics are intentionally not invented.

### 9.4 Out-of-Order Unlock

The explicit lock stack retains released entries when A is unlocked before B.
The protocol marks A with `_Q_UNLOCKED_OOO_VAL`, records the outer-unlock event,
and continues B. Once B is handed off or released, cleanup removes the retained
shadow entries and completes A exactly once. The complete combiner snapshot is
compared after each nested run; a mismatch is an invariant failure.

### 9.5 Readiness and Abort Recovery

Before executing any native or nested waiter remotely, `execute_cs()` requires
its exact entry to be fully published. An untranslated B waiter is registered
and receives normal queue ownership instead of partially executing translated
code. This is an entry-readiness gate, not a proof that all subsequently reached
calls, indirect targets, resources, and instructions can complete.

CALL miss, IJ miss, instruction-limit, capacity, and injected failures all use
lock/frame abort cleanup (not a memory transaction):

1. Release unreleased nested locks in reverse order using their recorded
   `NATIVE`, `FAST`, or `QUEUE_OWNER` semantics.
2. Remove retained OOO shadow entries and restore A's combiner state.
3. Mark the frame `ERROR` and pop it once.
4. Keep the failed waiter uncompleted until it acquires A normally.
5. Return through the dedicated ret4 trampoline and resume at A's original
   critical-section entry. JIT stays disabled for that A lock until module
   reload, and per-lock diagnostics expose the fallback.

**Correctness gap:** translated stores modify real shared memory and the waiter
stack immediately. `retry_regs` restores registers only; no write set, undo log,
or service-result journal exists. A write followed by a CALL/IJ miss or limit
failure can therefore be applied again on native entry retry. A nested B section
may already have completed and released B before A later fails. Reacquiring B
does not undo that earlier externally visible effect. The mutex failure path
has the same gap. Even retry-safe time services do not make earlier data writes
retry-safe. General use requires pre-execution eligibility and a defined
post-side-effect continuation/commit policy, not blind entry replay. This does
not mean delegation requires transactional rollback: preserving completed
effects and resuming the original code at a precise exit point is the preferred
direction (9.6), but the current high-level paths do not implement it.

Modes 1/6/7/8 cover normal nested, deep nested, OOO, and independent A/B queue
behavior. Fault-enabled mode 9 variants exercise post-B and runtime JIT faults;
mode 8's not-ready variant additionally checks cleanup while B is a queue owner.
Mode 10 reuses the independent A/B topology and adds translated GS/current
validation for the nested remote waiter.

The latest plain mode 9 run had no injection flags. Existing injected tests
must not be presented as proof of rollback after arbitrary partial writes.

In mode 1, B's known lock/unlock calls are handled while the same translated A
stream remains active. Consequently the outer A lock owns the JIT-completion
counter, while B reports nested lock/unlock activity. Mode 8 is the separate
test for an independently queued and remotely executed spin B waiter.

### 9.6 BCD Comparison And Forward Continuation Target

Source inspection on 2026-09-05 used the local `~/BCD` checkout at
`dbde52c57a961a5cdb87c0212f9b032947d2df13`. The active translation template is
`daemon/asm/wrapper.S`, copied by `daemon/daemon1.c` and `daemon/daemon2.c`;
the separate `disassem/asm/wrapper.S` is not the template used by those daemons.
BCD's missing kernel worktree files were read from this Git revision without
restoring or modifying them. This was a source inspection, not a BCD test run.

BCD's ordinary CALL-miss path preserves forward progress:

1. `disassem/special_inst.py:38` pushes the original post-CALL address onto the
   virtual stack. `disassem/indirect_jump.py:62` sets R14 to the original callee
   address and exits without removing that return address.
2. `daemon/asm/wrapper.S:67` writes the current original RIP, virtual RSP/RBP,
   and supported GPRs back into the waiter's actual syscall `pt_regs`.
3. `kernel_module/exe.c:475` records the missing target for later translation
   and returns `-1`, without replacing those registers with an entry snapshot.
4. `kernel_module/new_futex.c:1009` executes using the waiter's register frame
   and then publishes its wake state. The waiter observes the updated RIP;
   `new_futex.c:659` preserves the computed RAX as the syscall return value
   when execution advanced. The patched kernel's x86 syscall-return path
   restores that updated user context.

Thus a miss at `CALL f` resumes **native f at its entry with the CALL already
represented on the virtual stack**, then returns to the instruction after that
CALL. Earlier stores are retained and are not replayed. An IJ miss similarly
records the resolved original target and retains the post-branch/RET state.
`fast_path_success` in the wake protocol does not by itself mean the entire
critical section completed. A later translation can improve a future request;
it is not necessary to restart this request to compile the missing target.

This is continuation, not exception rollback. In particular, the inspected BCD
wrapper does not write live arithmetic EFLAGS back into `pt_regs`. Its code is
not evidence that arbitrary faults, arbitrary instructions, or the kdlock
kernel lock protocol can resume correctly just by loading saved GPRs.

The kdlock high-level paths differ in three material ways:

- Ordinary CALL-miss stubs in `disassem/indirect_jump.py` pop the virtual return
  address, and spin/mutex `execute_cs()` replace exit registers with
  `retry_regs`. Removing only the latter assignment would leave a callee-entry
  RIP without its required return frame.
- Nested abort cleanup releases held child locks. Resuming inside B after
  this cleanup would execute without B. If B already completed and unlocked,
  its effects should instead remain committed and A should resume after them.
- Kernel control-call handling has its own progress state: for example,
  `kd_mutex_jit_advance_call()` consumes the CALL before attempting a nested
  acquisition. A failed acquisition cannot safely resume at its post-CALL RIP
  as though B were acquired. Queue ownership, physical lock state, and the
  original waiter's scheduling/IRQ/preemption context also need a transfer
  protocol; a userspace syscall return does not supply one for kernel code.

The target protocol, **not implemented yet**, is:

| Outcome | Required action |
| --- | --- |
| Not started | Native entry handoff is allowed only when no semantic progress occurred. |
| Supported exit after progress | Resume native original code at a precise continuation with its registers, flags, virtual stack, and logically held locks intact. Do not restore the entry snapshot or release locks needed by that continuation. |
| Completed outer unlock | Keep the existing successful post-unlock return contract. |
| Unrecoverable state | Fail-stop or use a separately proven recovery protocol; never disguise it as an entry retry. |

Implementation should start with a single-lock ordinary CALL miss, then test
A continuing after a completed B, then transfer a still-held nested B and
queued/remote child frames. Define original instruction boundaries and
control-call phase metadata before extending to IJ, budget, or guard exits.
Preserve live flags and pin the relevant code/stack lifetimes. Progress and
lock metadata belong in execution frames; the two-word wrapper args ABI does
not need a third element. Detailed acceptance work is tracked in C1 of
`TODO.md`.

## 10. Legacy Low-Level Futex Exit

The retained BCD-derived `kd_exe_on_call()` recognizes futex syscalls:

- **futex_wake**: record the uaddr and wake count in `kd_exe_ret`.
- **futex_wait/wait_bitset**: compare the current uaddr with the entry uaddr
  and return a disposition in `kd_exe_ret.ret`; this entry does not enqueue or
  block a waiter.

Before invoking the shared wrapper, this path obtains kernel GS from the target
task's `task_cpu(task)` and passes `{GS base, task}`. It therefore does not use
the executor/combiner CPU directly, but the sample is not a captured, pinned
origin context. An external caller would have to guarantee task and CPU lifetime.

This low-level API remains as a compatibility execution entry only. There is no
in-tree scheduler/wakeup frontend that submits delegated futex waiters to it;
the unused former `kd_futex.c` frontend has been removed. Current spinlock and
mutex delegation use `kd_exe_on_call_hl_entry()` instead.
Since the translator now rejects FS and defines only kernel-code semantics,
this retained entry is not a supported userspace TLS/futex delegation feature.

## 11. Module Parameters & Runtime Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_process` | `"kd_test"` | One exact `current->comm` name routed through kdlock hooks |
| `mutex_jit` | 0 | Opt in to translated mutex modes 3, 4, 5, and 11 |
| `spin_jit_fail_after_nested_lock` | 0 | One-shot test failure after nested spin acquisition |
| `jit_hl_fault_after_known_call` | 0 | One-shot test fault: 1=CALL miss, 2=IJ miss, 3=instruction limit |

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
6. **NUMA-aware combining disabled** — dormant spinlock branches exist behind
   `NUMA_AWARE`, but the macro is not enabled and multi-socket behavior is
   untested. Mutex delegation has no NUMA-local queue implementation.
7. **No general instruction verifier** — segment/decoder rejection is
   implemented, but `special_inst.py` lowers `INT` to NOP and only warns for
   unhandled special operations such as its `PUSHF`/`POPF` cases. Ordinary
   mnemonics are emitted without a general privilege allowlist. Some unsafe
   instructions can therefore be mistranslated or executed, not rejected.
8. **Nested resources are bounded** — execution frames and lock stacks allow
   eight entries; each CPU has four spin nodes and four bitmap-reserved mutex
   nodes. Exhaustion aborts JIT or uses the documented native fallback.
9. **Spin JIT failure is sticky per lock** — after a translated frame fails,
   that outer lock remains on native handoff until `kdlock_km` is reloaded.
10. **Hostcalls are an explicit allowlist** — only fixed-signature, atomic-safe,
    task-context-independent, retry-safe services are currently accepted.
    General variadic `printk` and side-effecting services are unsupported.
11. **Persistent processor state is partial** — waiter kernel GS memory
    semantics and logical `current_task` reads are supported through explicit
    translation, but hardware FS/GS switching, FS operands, EFLAGS, and SIMD/FPU
    state are not supported as general cross-exit state. The reserved
    `args[1]` output is fixed at zero. See `docs/JIT_REGISTER_ABI.md`.
12. **Memory checks are incomplete** — the translator currently emits no
    effective canonical-address or bounds guard, so the JIT must not be treated
    as a security isolation boundary.
13. **Batch limits are fixed** — spin and mutex combiners process at most 1024
    waiters per round; these constants are not module parameters.
14. **Flags can be clobbered inside JIT** — dispatcher comparisons and inserted
    branch-block `INC`/`TEST` are not transparent to live flags. No liveness
    verifier enforces the restriction, even without a wrapper exit.
15. **Failure cleanup is not rollback** — see 9.5; memory, completed child
    sections, and service effects are not restored by an entry-register snapshot.
16. **Publication and lifetime are incomplete** — code is overwritten in place;
    no generation/refcount retirement handles concurrent execution, module-text
    unload/reload, or reused lock addresses. Hook removal uses
    `synchronize_rcu()`, but guest hook callers do not implement a matching
    reader/drain protocol. Stop all callers and drain queues before unloading.
17. **Scope is narrower than all kernel lock APIs** — the verified hooks are
    plain raw spin lock/unlock and mutex lock/unlock. Trylock, irqsave/bh,
    interruptible/killable mutex, mixed spin/mutex nesting, and interactions with
    non-target tasks are not covered by the current acceptance suite.
