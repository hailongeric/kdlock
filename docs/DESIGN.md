# kdlock Design Document

## 1. Motivation & Background

Modern multicore systems suffer from severe lock contention in the kernel.
When multiple cores compete for the same spinlock or mutex, cache-line bouncing
dominates execution time — the lock-protected data migrates between cores on
every ownership transfer.

**Lock delegation** (TCLocks, OSDI'22) solves this by keeping the lock holder
(the *combiner*) on a single core and executing queued waiters' critical
sections on their behalf.  The protected data stays cache-local to the combiner,
eliminating cross-core transfers.

**Dynamic binary translation** (BCD, OSDI'23) shows how to discover and
translate critical sections at runtime without recompiling the application.  It
reads the instruction stream starting from the lock-acquire return address,
translates it into a sandboxed form that can be executed by a proxy, and handles
untranslated calls and indirect jumps incrementally.

**kdlock** combines these two ideas in kernel space:

1. A patched kernel spinlock/mutex path calls into a loadable module.
2. The module records the critical-section entry address (the return address
   after `spin_lock` / `mutex_lock`).
3. A userspace daemon translates that instruction stream into a JIT sandbox
   binary using miasm-based disassembly.
4. The kernel module executes the sandbox on behalf of queued waiters, achieving
   lock delegation without modifying the original kernel code.

The key insight is that the sandbox eliminates RSP/RIP-relative operations: all
register state is passed through a `struct pt_regs`, memory accesses are
bounds-checked, and control flow is flattened.  This makes it safe for the
combiner to execute another thread's critical section without a full context
switch.

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
│  (char device)  │                    │  kd_exe_on_call_hl()     │
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

The host kernel is patched to export function pointers at the spinlock and mutex
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

The module parameter `target_process` specifies which process names should be
intercepted.  The patched kernel calls `is_kd_test()` which compares
`current->comm` against the target list.  Only matching processes enter the
delegation path; all others use the original kernel lock implementation.

### 3.3 Hot-Lock Promotion

Not every lock is worth delegating.  The `count_uaddr_cnt()` / `check_uaddr_state()`
mechanism in `kd_int3.c` implements a promotion pipeline:

```
KD_UADDR_INIT → KD_UADDR_CHECKING → KD_UADDR_DELEGATE
                                   → KD_UADDR_IGNORE (if too infrequent)
```

A lock address starts in `INIT` state.  After the first access it moves to
`CHECKING` and begins counting.  If 10,000 accesses occur within a
cycle-budget window, the lock is promoted to `DELEGATE` and enters the
delegation path.  If the accesses are too spread out (exceed `count_uaddr_time`
cycles), the lock is marked `IGNORE` and always falls back to the original
kernel path.

### 3.4 Hook Implementation (kd_lock.c)

```c
void __kd_raw_spin_lock(raw_spinlock_t *lock, unsigned long ret_rsp,
                        unsigned long ret_addr)
{
    if (!check_uaddr_state((unsigned long)lock)) {
        count_uaddr_cnt((unsigned long)lock);
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
    frame = kd_exec_frame_push(...);
    import_combiner_and_lock_stack(frame, curr_node);
    ret = kd_exe_on_call_hl_entry(&frame->regs, ...,
                                  frame->entry_ip,
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

Native waiters first import callee-saved registers from the saved hook stack.
Nested virtual waiters already carry a complete `pt_regs` snapshot and an
explicit `kd_exec_frame`; they do not rely on the combiner's C stack.

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
| `ret_val == 1` | Delegated CS completed while its parent lock was OOO | Restore the actual node's saved register context |
| `ret_val == 2` | Became queue owner/combiner | Normal return (runs own CS) |
| `ret_val == 3` | CS was delegated | `jump_to_saved_regs(&regs)` — restore full context |
| `ret_val == 4` | JIT failed; waiter later acquired the outer lock normally | `jump_to_saved_regs_in_cs(&regs)` — resume at the original CS entry |

### 4.5 Out-of-Order (OOO) Unlock

When locks are released out of order (e.g., Acquire(A), Acquire(B), Release(A),
Release(B)), the unlock for A happens while B's combiner is still running:

1. `kd_spin_unlock` searches `lock_addr[]` for the lock.
2. If `my_idx < max_idx` (not the outermost lock), set
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
experimental, `mutex_jit` defaults to 0. In this safe mode `execute_cs()`
returns `KD_EXE_NO_RUN`, and the combiner hands ownership to the waiter without
marking its critical section complete.

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
| OOO unlock | Full support via `lock_addr[]` | LIFO nested unlock; reverse cleanup on abort |

## 6. JIT Execution Engine (exe.c)

### 6.1 Code Block Management

At module init, `kd_exe_init()` pre-allocates a pool of 64 executable memory
blocks (each 160 pages = 640KB).  These are vmalloc'd and marked executable via
`set_memory_x()`.  When `kd_exe_add()` is called from the lock hook (possibly
with IRQs disabled), it takes a block from the pool without calling vmalloc.
Only blocks for which both allocation and `set_memory_x()` succeeded enter the
pool. Pool or translation-table exhaustion fails closed.

Kernel critical-section text is shared across all tasks, so kernel-lock JIT
entries use a **RIP-only key**: the hook calls `kd_exe_add(0, ret_addr)` and
`kd_exe_on_call_hl()` looks up `kd_get_exe(0, regs->ip)`. This avoids binding a
translation to one short-lived benchmark thread or process ID.

The translation hash probes at most `KD_MAX_EXE` slots. It returns `NULL` when
full rather than looping in atomic/IRQ-disabled context. Code-block allocation
uses an atomic gate and never waits for the userspace daemon.

### 6.2 Entry Lifecycle

```
KD_EXE_UNUSED → KD_EXE_UNINIT → KD_EXE_NORMAL → (KD_EXE_CALL_MISS | KD_EXE_IJ_MISS) → KD_EXE_NORMAL
                     ↑                                        │
                     │              daemon recompiles         │
                     └────────────────────────────────────────┘
```

### 6.3 kd_exe_on_call_hl()

This is the core execution function called by the combiner:

```c
int kd_exe_on_call_hl(struct pt_regs *regs, void *outgoing_rsp_ptr)
{
    struct kd_exe_info *exe = kd_get_exe(0, regs->ip);

    if (exe->status_code != KD_EXE_NORMAL)
        return KD_EXE_NO_RUN;  // not ready

    void (*virt_ptr)(struct pt_regs *, unsigned long *) = exe->code_block;
    unsigned long args[2] = { exe->gsbase, 0 };

    virt_ptr(regs, args);  // execute sandbox

    // Interpret result
    if (args[0] == KD_EXE_CALL_MISS && is_end_point(regs->ip))
        return KD_EXE_RUN_TO_UNLOCK;  // CS complete
    ...
}
```

### 6.4 End-Point Detection

The `end_point[]` array lists kernel functions whose address signals the end of
a critical section.  These are resolved dynamically at module init via
`kallsyms_lookup_name`:

```c
end_point[end_point_count] = kallsyms_lookup_name("_raw_spin_unlock");
end_point[end_point_count] = kallsyms_lookup_name("mutex_unlock");
```

When the sandbox encounters a `CALL` to one of these addresses, it reports
`KD_EXE_CALL_MISS`.  The engine checks `is_end_point()` and returns
`KD_EXE_RUN_TO_UNLOCK` — the critical section has been fully executed.

## 7. Dynamic Translation Pipeline

### 7.1 Daemon (daemon/daemon.c)

The daemon runs in userspace and polls `/dev/kd_dev`:

1. **Read**: get array of `kd_exe_info` entries from the kernel.
2. **Dispatch** based on `status_code`:
   - `KD_EXE_UNINIT`: create workspace, run initial translation.
   - `KD_EXE_CALL_MISS`: append target to `callee_table.txt`, recompile.
   - `KD_EXE_IJ_MISS`: append `(from, target)` to `ij_table.txt`, recompile.
3. **Compile**: invoke `disassem.py` which produces `asm/jit.S`.
4. **Assemble**: `wrapper.S` includes `jit.S`, assembled into `jit.bin`.
5. **Write**: send `jit.bin` back through `/dev/kd_dev` in chunks (max 4000
   bytes per write), with `kd_recv_pkt` headers.

### 7.2 Translator (disassem/disassem.py)

The miasm-based translator:

1. Reads raw kernel bytes from `/proc/kcore` at the target RIP (`memread.py`).
2. Disassembles into a control-flow graph using miasm's `dis_multiblock`.
3. Stops disassembly at `dont_dis_retcall_funcs` (unlock functions).
4. For each basic block, translates instructions via `translation.py`:
   - Normal instructions: register conflict resolution, memory base checking.
   - Branches: translated to sandbox-local jumps.
   - Special instructions: handled by `special_inst.py`.
5. Handles indirect jumps (`indirect_jump.py`): builds jump tables, reports
   misses.
6. Outputs `asm/jit.S` which is included by `wrapper.S`.

### 7.3 Incremental Recompilation

When the sandbox hits an untranslated call or indirect jump at runtime:

1. Kernel sets `exe->status_code = KD_EXE_CALL_MISS` (or `IJ_MISS`) and records
   `exe->tgt_addr` / `exe->jump_from`.
2. Daemon reads this on next poll, appends to the callee/IJ table.
3. Daemon re-runs `disassem.py` which now includes the new target in its
   disassembly scope.
4. New `jit.bin` is written back, overwriting the code block.
5. Entry returns to `KD_EXE_NORMAL`.

The write path validates the destination block, offset, length, and requested
status. It publishes `KD_EXE_NORMAL` with release semantics only after the
complete artifact has been copied. Execution checks readiness with acquire
semantics. A combiner never waits for recompilation: a miss aborts that frame,
disables JIT for the affected outer lock, hands ownership to the waiter, and
retries from the original critical-section entry.

## 8. Sandbox Code Model

### 8.1 Register Convention

The sandbox uses a fixed register assignment to avoid RSP/RIP operations:

| Register | Sandbox role | Notes |
|----------|-------------|-------|
| R14 | `PT_REG` pointer | Points to `struct pt_regs` |
| R15 | `ARG_REG` pointer | Points to args[] (gsbase, return code) |
| R13 | Virtual RSP | Tracks the logical stack pointer |
| R12 | Virtual RBP | Tracks the logical frame pointer |
| R11 | Instruction counter | Incremented per basic block |

All other registers (RAX, RBX, RCX, RDX, RSI, RDI, R8-R10) hold their
"real" values from the waiter's context and are used normally by translated
instructions.

### 8.2 Wrapper (include/wrapper.S)

The wrapper provides prologue/epilogue around the translated code:

**Prologue:**
1. Save callee-saved registers (standard C ABI).
2. Load `pt_regs` pointer into R14, args pointer into R15.
3. Restore all general-purpose registers from `pt_regs`.
4. Push virtual RSP, RBP, R12-R15, R11, GS, FS onto the real stack for
   later recovery.
5. Initialize R13 = virtual RSP, R12 = virtual RBP.
6. Jump to translated code entry (`jit.S`).

**Epilogue (exit label):**
1. Save current R14 (RIP), R13 (RSP), R12 (RBP) back to stack slots.
2. Reload `pt_regs` and args pointers.
3. Write return code (`Stack_IJ`) into `args[0]`:
   - `0x0` = `KD_EXE_NORMAL` (syscall encountered)
   - `0x1` = `KD_EXE_CALL_MISS`
   - `0x4` = `KD_EXE_INST_LIMIT`
   - Other = indirect jump source address (`KD_EXE_IJ_MISS`)
4. Write final RIP into `pt_regs->ip`.
5. Restore all registers back to `pt_regs`.
6. Restore callee-saved registers and return.

### 8.3 Memory Access Safety

The translator inserts bounds checks before memory accesses through base
registers.  If a base register points to a non-canonical address (indicating
a user-space pointer that shouldn't be dereferenced in kernel context), the
sandbox jumps to `seg_error` / `seg_error2` and exits cleanly.

### 8.4 Instruction Count Limit

Each basic block increments R11.  When `R11 & 0x1000000` is set (~16M
instructions), the sandbox jumps to `inst_limit`, preventing infinite loops
in translated code.

### 8.5 Call Translation

Function calls in the original code are translated to:
- **Known callees** (in `callee_table.txt`): inlined or translated as part of
  the same sandbox.
- **Unknown callees**: trigger `KD_EXE_CALL_MISS` — set R14 to the target
  address, set `Stack_IJ = 0x1`, jump to exit.
- **End-point callees** (`_raw_spin_unlock`, `mutex_unlock`): same as call-miss
  mechanically, but the kernel engine recognizes the target as an end-point and
  returns `KD_EXE_RUN_TO_UNLOCK`.

## 9. Nested Spinlock JIT Handling

### 9.1 Execution Frames

Every delegated spin critical section owns a per-CPU `kd_exec_frame`. The frame
stores its complete `pt_regs`, entry and continuation RIP/RSP, parent frame,
outer lock, lock ownership kind, held-lock stack, and a snapshot of TCLock's
combiner state. Frames and lock stacks are bounded at eight entries.

Unlike the old adapter, this state survives suspension of A while B enters its
own fastpath, MCS queue, or combiner. Nested execution therefore does not depend
on the host C call stack.

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
code. This is the dynamic equivalent of preflight for call graphs whose indirect
targets cannot be known statically.

CALL miss, IJ miss, instruction-limit, capacity, and injected failures all use
one transaction abort:

1. Release unreleased nested locks in reverse order using their recorded
   `NATIVE`, `FAST`, or `QUEUE_OWNER` semantics.
2. Remove retained OOO shadow entries and restore A's combiner state.
3. Mark the frame `ERROR` and pop it once.
4. Keep the failed waiter uncompleted until it acquires A normally.
5. Return through the dedicated ret4 trampoline and resume at A's original
   critical-section entry. JIT stays disabled for that A lock until module
   reload, and per-lock diagnostics expose the fallback.

Modes 1/6/7/8 cover normal nested, deep nested, OOO, and independent A/B queue
behavior. Recovery mode 9 covers post-B and runtime JIT faults; mode 8's
not-ready variant additionally proves cleanup while B is a queue owner.

In mode 1, B's known lock/unlock calls are handled while the same translated A
stream remains active. Consequently the outer A lock owns the JIT-completion
counter, while B reports nested lock/unlock activity. Mode 8 is the separate
test for an independently queued and remotely executed spin B waiter.

## 10. Futex Delegation

For user-space lock delegation (the BCD path), `kd_exe_on_call()` handles
futex syscalls encountered inside translated critical sections:

- **futex_wake**: record the uaddr and wake count in `kd_exe_ret`.
- **futex_wait**: record the uaddr; the caller decides whether to actually
  block or continue.

The futex delegation engine (`kd_futex.c`) provides `new_futex_wait` /
`new_futex_wake` that execute futex operations on behalf of delegated waiters
without requiring them to enter the kernel syscall path.

## 11. Module Parameters & Runtime Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_process` | `"kd_test"` | Space-separated process names to intercept |
| `velvet_wait_queue` | 1 | Enable/disable velvet wait queue optimization |
| `delegate_election` | 1 | Enable/disable delegate election |
| `kd_combiner_batch_size` | (extern) | Max waiters processed per combiner round (spinlock) |
| `kd_mutex_batch_size` | 1024 | Max waiters processed per combiner round (mutex) |
| `mutex_jit` | 0 | Opt in to translated mutex execution, including mode 4 nested A/B proxying |
| `spin_jit_fail_after_nested_lock` | 0 | One-shot test failure after nested spin acquisition |
| `jit_hl_fault_after_known_call` | 0 | One-shot test fault: 1=CALL miss, 2=IJ miss, 3=instruction limit |

## 12. Current Status & Limitations

### Working

- Raw spinlock delegation with JIT sandbox (modes 0-2 and 6-9 tested).
- Mutex safe-mode queue/handoff (modes 3-5), mode 3 stress JIT, mode 4 nested
  A/B JIT proxying, and bounded mode 5 JIT.
- Dynamic translation pipeline (init, call-miss, ij-miss recompilation).
- Hot-lock promotion and fallback to original kernel path.
- TCLock-style nested spinlock and mutex JIT delegation, explicit frames,
  translation-readiness checks, and transactional native retry.
- Dynamic end_point resolution via kallsyms_lookup_name.
- Module exit safety with synchronize_rcu.
- User-space unit tests for core data structures.

### Limitations

1. **x86-64 only** — inline assembly, stack frame layout, and register
   conventions are architecture-specific.
2. **Patched kernel required** — the hook function pointers and exported
   symbols must exist in the running kernel.
3. **KASLR must be disabled** — `/proc/kcore` reading assumes fixed kernel
   text layout. (end_point[] is resolved dynamically and unaffected.)
4. **miasm dependency** — the translator requires miasm 0.1.5 and
   `/proc/kcore` access from userspace.
5. **No rwsem support** — only spinlock and mutex are implemented.
6. **NUMA-aware combining disabled** — `NUMA_AWARE` is defined but not
   enabled; multi-socket optimization is untested.
7. **Sandbox cannot handle all instructions** — unsupported instructions
   or complex indirect jumps cause delegation failure and fallback.
8. **Nested resources are bounded** — execution frames and lock stacks allow
   eight entries; each CPU has four spin nodes and four bitmap-reserved mutex
   nodes. Exhaustion aborts JIT or uses the documented native fallback.
9. **Spin JIT failure is sticky per lock** — after a translated frame fails,
   that outer lock remains on native handoff until `kdlock_km` is reloaded.
