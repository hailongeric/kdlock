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
    kd_exe_add(current->pid, ret_addr);  // register CS entry
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
    // 1. Read callee-saved registers from waiter's saved stack frame
    void *incoming_rsp_ptr = (void *)curr_node->regs.sp;
    curr_node->regs.r15 = ((unsigned long *)incoming_rsp_ptr)[5];
    curr_node->regs.r14 = ((unsigned long *)incoming_rsp_ptr)[4];
    curr_node->regs.r13 = ((unsigned long *)incoming_rsp_ptr)[3];
    curr_node->regs.r12 = ((unsigned long *)incoming_rsp_ptr)[2];
    curr_node->regs.bx  = ((unsigned long *)incoming_rsp_ptr)[1];
    curr_node->regs.bp  = ((unsigned long *)incoming_rsp_ptr)[6];
    curr_node->regs.ip  = ((unsigned long *)incoming_rsp_ptr)[7];
    curr_node->regs.sp  = (unsigned long)incoming_rsp_ptr + 64;

    // 2. Call JIT sandbox
    int ret = kd_exe_on_call_hl(&curr_node->regs, outgoing_rsp_ptr);

    // 3. Check result
    if (ret == KD_EXE_RUN_TO_UNLOCK)
        return 0;  // CS executed successfully, reached unlock
    return ret;    // delegation failed
}
```

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
| `ret_val == 2` | Became combiner | Normal return (runs own CS) |
| `ret_val == 3` | CS was delegated | `jump_to_saved_regs(&regs)` — restore full context |
| `ret_val == 4` | IJ miss mid-CS | `jump_to_saved_regs_in_cs(&regs)` — resume at translated point |

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

### 5.2 Protocol (mirrors spinlock)

```c
void _kd_mutex_lock(struct kd_mutex *lock, unsigned long rsp_value,
                    unsigned long ret_addr,
                    unsigned long s_rbx, unsigned long s_r12,
                    unsigned long s_r13, unsigned long s_r14,
                    unsigned long s_r15, unsigned long s_rbp)
{
    // Fastpath: cmpxchg
    if (cmpxchg(&lock->locked, 0, 1) == 0)
        return;

    // Store callee-saved registers captured at hook entry into node[0]
    // (copied to node[idx] by kd_mutex_lock_slowpath when idx > 0)
    preempt_disable();
    curr_node->saved_rbx = s_rbx;  // ...etc
    kd_mutex_lock_slowpath_asm(lock, rsp_value);
    preempt_enable();
}
```

The mutex combiner loop is identical in structure to the spinlock combiner:
populate `pt_regs` from the waiter's stack frame at `ret_rsp`, optionally call
`kd_exe_on_call_hl()`, check for `KD_EXE_RUN_TO_UNLOCK`.

Because translated mutex CS execution is still experimental, `mutex_jit` defaults
to 0. In this safe mode, `execute_cs()` returns `KD_EXE_RUN_ERROR`, so
`run_combiner()` hands the lock to the waiter without marking it completed. This
exercises the queue/combiner/fallback/handoff protocol without executing
translated mutex critical-section code. Normal mutex validation should keep this
default. Enable actual mutex sandbox execution only for explicit debugging with
`insmod kdlock_km.ko mutex_jit=1`.

**Stack frame layout** (confirmed via disassembly of the kernel's `mutex_lock`):
the kernel's `mutex_lock` saves all 6 callee-saved registers in the same order
as `raw_spin_lock`, so both paths share identical offsets in `execute_cs()`.

**Node count management**: the `count` field lives exclusively in `nodes[0]`.
All increments (`base_node->count++`) and decrements
(`this_cpu_ptr(&kd_mutex_nodes[0])->count--`) target this single location.
When `idx > 0`, `regs.sp` and saved registers are copied from `nodes[0]` to
`nodes[idx]` in `kd_mutex_lock_slowpath`.

### 5.3 Differences from Spinlock Path

| Aspect | Spinlock | Mutex |
|--------|----------|-------|
| Queue structure | Per-CPU `kd_spin_node[4]` | Per-CPU `kd_mutex_node[4]` |
| Lock state | `qspinlock.val` (atomic) | `kd_mutex.locked` (u8) |
| Tail encoding | In `qspinlock.tail` field | In `kd_mutex.tail` pointer |
| Preemption | Disabled throughout | Disabled only in slowpath |
| OOO unlock | Full support via `lock_addr[]` | Simplified (no chaining) |

## 6. JIT Execution Engine (exe.c)

### 6.1 Code Block Management

At module init, `kd_exe_init()` pre-allocates a pool of 64 executable memory
blocks (each 160 pages = 640KB).  These are vmalloc'd and marked executable via
`set_memory_x()`.  When `kd_exe_add()` is called from the lock hook (possibly
with IRQs disabled), it takes a block from the pool without calling vmalloc.

Kernel critical-section text is shared across all tasks, so kernel-lock JIT
entries use a **RIP-only key**: the hook calls `kd_exe_add(0, ret_addr)` and
`kd_exe_on_call_hl()` looks up `kd_get_exe(0, regs->ip)`. This avoids binding a
translation to one short-lived benchmark thread or process ID.

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
    struct kd_exe_info *exe = kd_get_exe(pid, regs->ip);

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

## 9. Nested Lock Handling

### 9.1 Detection

Nested locking occurs when:
- A combiner's sandbox executes a waiter's CS that acquires another lock.
- A thread holds lock A and acquires lock B (level locking).
- An IRQ handler acquires a lock while the thread already holds one.

### 9.2 Per-CPU Node Array

Each CPU has `kd_spin_nodes[MAX_NODES]` (4 nodes).  The `count` field at
`nodes[0]` tracks nesting depth.  Each nested acquisition uses `nodes[idx]`
where `idx = count++`.  If `idx >= MAX_NODES`, fall back to trylock spinning.

### 9.3 ENABLE_IRQS_CHECK Guard

When enabled, the entry to `kd_spin_lock`'s queue path checks:

```c
if (curr_node->count > 0 || !in_task() || irqs_disabled() ||
    current->migration_disabled)
```

If any condition is true, the thread takes the **IRQ path**:
- `socket_id = IRQ_NUMA_NODE` (255)
- `rsp = 0xdeadbeef`

The combiner's `check_irq_node()` detects these markers and **skips
delegation** for such nodes, passing the lock directly without JIT execution.

### 9.4 lock_addr[] Tracking

The combiner records each lock it processes in `shadow_stack.lock_addr[j]`.
During unlock, the engine searches this array to determine:
- `my_idx`: position of the lock being unlocked.
- `max_idx`: position of the outermost active lock.

If `my_idx < max_idx`, the unlock is out-of-order → set
`lock->locked = _Q_UNLOCKED_OOO_VAL`.

### 9.5 OOO Recovery

When the combiner returns from `execute_cs` and finds
`lock->locked == _Q_UNLOCKED_OOO_VAL`:
1. Wake the waiter whose CS triggered the OOO unlock.
2. Reset `curr_cs_cpu` / `prev_cs_cpu`.
3. Restore `lock->locked = _Q_LOCKED_COMBINER_VAL`.
4. Continue with remaining waiters if any.

### 9.6 Sandbox Behavior with Nested Locks

If the translated CS contains a `spin_lock(B)` call:
1. Sandbox reports `KD_EXE_CALL_MISS` (since `_raw_spin_lock` is not an
   end-point and not in the callee table).
2. `kd_exe_on_call_hl` returns `KD_EXE_RUN_ERROR`.
3. The combiner does NOT mark the waiter as completed.
4. The waiter is handed the lock and becomes the new combiner, executing its
   own CS directly.

This is a graceful degradation: nested-lock critical sections are not delegated
but still execute correctly.

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

## 12. Current Status & Limitations

### Working

- Raw spinlock delegation with JIT sandbox (modes 0-2 tested).
- Mutex delegation with JIT sandbox (modes 3-5, same execute_cs path as spinlock).
- Dynamic translation pipeline (init, call-miss, ij-miss recompilation).
- Hot-lock promotion and fallback to original kernel path.
- Nested lock detection and graceful degradation.
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


