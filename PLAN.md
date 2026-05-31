# Implementation Plan: Kernel Lock Delegation via Dynamic Binary Translation

## Goal

Automatically identify hot kernel critical sections protected by spinlocks and
mutexes, and accelerate them through dynamic proxy execution — a combiner core
executes translated sandbox code on behalf of queued waiters, keeping
lock-protected data cache-local and eliminating cross-core cache-line transfers.

## Foundational Principles

### From TCLocks: Lock Delegation

Instead of transferring lock ownership between cores (causing cache-line
bouncing), one core (the **combiner**) holds the lock and executes critical
sections for all queued waiters.  Waiters enqueue, spin locally, and receive
results without ever touching the lock-protected data.

### From BCD: Dynamic Binary Translation

Critical sections are discovered at runtime (not at compile time).  The
bytecode starting at the CS entry address is read, disassembled, and translated
into a **sandbox** form that:
- Eliminates RSP/RIP-relative operations (no real stack manipulation).
- Passes all register state through a `struct pt_regs` context.
- Detects the CS boundary (unlock call) and returns control to the combiner.

The combination: TCLocks provides the delegation protocol; BCD provides the
mechanism to execute another thread's code without a full context switch.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Phase 1: HOOK (Kernel Module)                  │
│                                                                 │
│  Patched kernel lock path                                       │
│       │                                                         │
│       ▼                                                         │
│  is_target_process() ──no──► original_lock_path()               │
│       │yes                                                      │
│       ▼                                                         │
│  is_hot_lock(lock_addr) ──no──► count_and_promote()             │
│       │yes                                                      │
│       ▼                                                         │
│  register_cs_entry(pid, ret_addr)                               │
│  enter_delegation_protocol(lock, ret_rsp)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                Phase 2: TRANSLATE (Userspace Daemon)              │
│                                                                 │
│  poll /dev/kd_dev for new CS entries                            │
│       │                                                         │
│       ▼                                                         │
│  read_kernel_text(RIP) via /proc/kcore                          │
│       │                                                         │
│       ▼                                                         │
│  disassemble(bytecode) → CFG                                    │
│       │                                                         │
│       ▼                                                         │
│  translate_to_sandbox(CFG) → jit.S                              │
│       │                                                         │
│       ▼                                                         │
│  assemble(wrapper.S + jit.S) → jit.bin                          │
│       │                                                         │
│       ▼                                                         │
│  write_back(jit.bin) → /dev/kd_dev → kernel code_block          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Phase 3: EXECUTE (Kernel Module)                     │
│                                                                 │
│  Combiner dequeues waiter                                       │
│       │                                                         │
│       ▼                                                         │
│  populate_pt_regs(waiter_stack_frame)                            │
│       │                                                         │
│       ▼                                                         │
│  sandbox_execute(pt_regs, code_block)                           │
│       │                                                         │
│       ▼                                                         │
│  check_result:                                                  │
│    RUN_TO_UNLOCK → mark_waiter_done()                           │
│    CALL_MISS     → notify_daemon_recompile()                    │
│    IJ_MISS       → notify_daemon_recompile()                    │
│    ERROR         → fallback_to_direct_execution()               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Kernel Hook Layer

### 1.1 Kernel Patch (minimal changes to kernel source)

Patch the kernel's lock fast paths to call through function pointers when a
target process is detected.

**Files to patch in kernel source:**
- `kernel/locking/spinlock.c` — raw spinlock acquire/release
- `kernel/locking/mutex.c` — mutex acquire/release

**Exported function pointers (declared in patched kernel, set by module):**

```c
// kernel/locking/spinlock.c
void (*kd_raw_spin_lock)(raw_spinlock_t *lock,
                         unsigned long caller_rsp,
                         unsigned long ret_addr) = NULL;
void (*kd_raw_spin_unlock)(raw_spinlock_t *lock,
                           unsigned long caller_rsp,
                           unsigned long ret_addr) = NULL;
EXPORT_SYMBOL(kd_raw_spin_lock);
EXPORT_SYMBOL(kd_raw_spin_unlock);

// kernel/locking/mutex.c
void (*kd_mutex_lock)(struct mutex *lock,
                      unsigned long caller_rsp,
                      unsigned long ret_addr) = NULL;
void (*kd_mutex_unlock)(struct mutex *lock,
                        unsigned long caller_rsp,
                        unsigned long ret_addr) = NULL;
EXPORT_SYMBOL(kd_mutex_lock);
EXPORT_SYMBOL(kd_mutex_unlock);
```

**Hook insertion point (example for spinlock):**

```c
// In __raw_spin_lock():
if (kd_raw_spin_lock && is_kd_test()) {
    kd_raw_spin_lock(lock, current_stack_pointer, _RET_IP_);
    return;
}
// ... original path
```

- `caller_rsp`: stack pointer at the call site — points to the saved
  callee-saved register frame.
- `ret_addr`: return address = first instruction of the critical section.

**Also export from kernel:**
- `int (*is_kd_test)(void)` — returns nonzero if `current` is a target process.
- `__mutex_lock_slowpath`, `__mutex_unlock_slowpath` — for fallback path.

### 1.2 Target Process Identification

**File:** `kernel_module/kd_main.c`

```c
// Module parameter
char *target_process = "my_app";
module_param(target_process, charp, S_IRUGO);

// Installed as is_kd_test callback
static int __is_kd_test(void)
{
    return strcmp(current->comm, target_process) == 0;
}
```

### 1.3 Hot-Lock Promotion

**File:** `kernel_module/kd_hotlock.c`

Not every lock benefits from delegation.  Only locks with high contention
(many waiters) should be promoted.

**Data structure:**

```c
#define KD_LOCK_INIT      0
#define KD_LOCK_CHECKING  1
#define KD_LOCK_DELEGATE  2
#define KD_LOCK_IGNORE    3

struct kd_lock_state {
    unsigned long lock_addr;
    int state;
    int hit_count;
    unsigned long first_seen_cycle;
};
```

**Functions:**

```c
// Called on every lock acquisition for target process
// Returns true if this lock should use delegation
bool kd_should_delegate(unsigned long lock_addr);

// Promotion logic:
//   INIT → CHECKING (first hit, record timestamp)
//   CHECKING → DELEGATE (if hit_count reaches threshold within time window)
//   CHECKING → IGNORE (if time window expires before threshold)
void kd_promote_lock(unsigned long lock_addr);
```

**Promotion criteria:**
- Threshold: 10,000 acquisitions
- Time window: configurable cycle count (default ~1 second)
- Once promoted to DELEGATE, stays there for the module's lifetime.

### 1.4 CS Entry Registration

**File:** `kernel_module/kd_exe.c`

When a hot lock is acquired, register the critical section entry point:

```c
// Called from the lock hook when delegation is active
void kd_exe_add(int pid, unsigned long cs_entry_rip);
```

This allocates a translation entry and marks it as needing translation.

---

## Phase 2: Delegation Protocol (Kernel Module)

### 2.1 Spinlock Delegation

**File:** `kernel_module/kd_spinlock.c`

Port the TCLocks MCS-queue combiner protocol, replacing the raw context-switch
with JIT sandbox execution.

**Data structures:**

```c
#define MAX_NODES 4  // max nesting depth per CPU

struct kd_spin_node {
    struct kd_spin_node *next;  // MCS queue link
    u32 tail;                   // encoded (cpu, idx)
    int count;                  // nesting depth at nodes[0]
    int cpuid;
    int socket_id;
    uint64_t rsp;               // saved stack pointer
    struct qspinlock *lock;
    struct task_struct *task;

    union {
        struct { u8 completed; u8 locked; };
        u16 locked_completed;
    };

    struct pt_regs regs;        // waiter's register context for sandbox
};

struct kd_shadow_stack {
    uint64_t lock_addr[8];      // nested lock tracking for OOO detection
    void *base;                 // vmalloc'd shadow stack base
    uint64_t stack_ptr;         // current shadow stack position
    uint32_t curr_cs_cpu;       // CPU whose CS is being executed
    uint32_t prev_cs_cpu;       // previous (for chaining)
};
```

**Per-CPU allocation:**
```c
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_spin_node, kd_nodes[MAX_NODES]);
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_shadow_stack, kd_shadow);
```

**Key functions:**

```c
// Public API (called from hook layer)
void kd_spin_lock(struct qspinlock *lock, unsigned long caller_rsp);
void kd_spin_unlock(struct qspinlock *lock);

// Internal
static int  kd_spin_lock_slowpath(struct qspinlock *lock, unsigned long rsp);
static int  __kd_spin_lock_queue(struct qspinlock *lock, int tail,
                                 struct kd_spin_node *node);
static void run_combiner(struct qspinlock *lock, struct kd_spin_node *first);
static int  execute_cs(struct qspinlock *lock, struct kd_spin_node *waiter);
```

**Protocol flow:**

```
kd_spin_lock(lock, rsp):
  1. Fastpath: atomic_cmpxchg(lock, 0, LOCKED) → success, return
  2. Midpath: pending-bit optimization for 2nd contender
  3. Slowpath:
     a. Save rsp to node->regs.sp
     b. Switch to per-CPU shadow stack
     c. Enqueue node into MCS queue (xchg_tail)
     d. If prev exists: link, spin on node->locked
        - If woken with node->completed: CS was delegated, return
        - Else: fall through to become combiner
     e. Become combiner:
        - Set lock->locked = COMBINER_VAL
        - Record lock in shadow.lock_addr[j]
        - Call run_combiner(lock, next_node)
        - Restore state, pass lock to next unprocessed waiter
```

**run_combiner(lock, first_waiter):**

```
for each waiter in queue (up to batch_size):
    ret = execute_cs(lock, waiter)
    if ret == SUCCESS:
        mark waiter completed (clear_locked_set_completed)
    else:
        // delegation failed — hand lock to this waiter directly
        break
pass lock to next_node
```

**execute_cs(lock, waiter_node):**

```
1. Read waiter's saved stack frame at regs.sp:
   regs.r15 = stack[5], regs.r14 = stack[4], ...
   regs.ip  = stack[7]  (= CS entry address)
   regs.sp  = original_sp + 64

2. Call sandbox_execute(&waiter->regs, &shadow.stack_ptr)

3. If result == RUN_TO_UNLOCK: return SUCCESS
   Else: return FAILURE
```

### 2.2 Mutex Delegation

**File:** `kernel_module/kd_mutex.c`

Same combiner model as spinlock, but:
- Uses a shadow `struct kd_mutex` (separate from kernel's `struct mutex`).
- Shadow table maps `struct mutex *` → `struct kd_mutex *`.
- Preemption disabled only during slowpath (mutex can sleep, spinlock cannot).

**Data structures:**

```c
struct kd_mutex_node {
    struct kd_mutex_node *next;
    u32 tail;
    int count;
    int cpuid;
    uint64_t rsp;
    struct kd_mutex *lock;
    struct task_struct *task;
    union { struct { u8 completed; u8 locked; }; u16 locked_completed; };
    struct pt_regs regs;
};

struct kd_mutex {
    struct kd_mutex_node *tail;
    union { atomic_t state; struct { u8 locked; }; };
};

// Shadow table: kernel mutex addr → kd_mutex
struct kd_mutex_shadow_entry {
    unsigned long mutex_addr;
    struct kd_mutex shadow;
};
```

**Key functions:**

```c
void _kd_mutex_lock(struct kd_mutex *lock, unsigned long rsp);
void _kd_mutex_unlock(struct kd_mutex *lock);

static int  kd_mutex_lock_slowpath(struct kd_mutex *lock);
static void kd_mutex_run_combiner(struct kd_mutex *lock,
                                  struct kd_mutex_node *first);
static int  kd_mutex_execute_cs(struct kd_mutex *lock,
                                struct kd_mutex_node *waiter);

// Shadow table lookup
struct kd_mutex *kd_get_shadow_mutex(struct mutex *kernel_lock);
```

### 2.3 Nested Lock Handling

**Invariant:** If a CPU is already inside a delegation (count > 0), or is in
IRQ context, it must NOT enter the JIT sandbox path.

**Detection (at queue entry):**

```c
if (node->count > 0 || !in_task() || irqs_disabled()) {
    // Mark as non-delegatable
    node->socket_id = IRQ_MARKER;
    node->rsp = POISON_VALUE;
    // Enter simple MCS queue, no sandbox execution
}
```

**Combiner skip logic:**

```c
static bool is_non_delegatable(struct kd_spin_node *node) {
    return node->socket_id == IRQ_MARKER || node->rsp == POISON_VALUE;
}

// In run_combiner: skip delegation for such nodes
if (is_non_delegatable(waiter)) {
    // Pass lock directly, waiter executes own CS
    break;
}
```

**OOO unlock detection:**

```c
// In kd_spin_unlock:
// Search lock_addr[] for this lock
// If found at index < max_index → out-of-order unlock
//   Set lock->locked = OOO_VAL
//   Combiner detects OOO_VAL after execute_cs returns
```

---

## Phase 3: JIT Execution Engine (Kernel Module)

### 3.1 Translation Entry Management

**File:** `kernel_module/kd_exe.c`

**Data structure:**

```c
#define EXE_UNUSED    -2
#define EXE_UNINIT    -1  // waiting for daemon translation
#define EXE_READY      0  // translation complete, executable
#define EXE_CALL_MISS  1  // hit untranslated function call
#define EXE_IJ_MISS    2  // hit untranslated indirect jump
#define EXE_INST_LIMIT 4  // instruction count exceeded

struct kd_exe_entry {
    int status;
    int pid;
    int tgid;
    unsigned long rip;          // CS entry address
    void *code_block;           // pre-allocated executable memory
    unsigned long miss_target;  // address that caused CALL_MISS/IJ_MISS
    unsigned long miss_source;  // source of indirect jump
    unsigned long gsbase;       // saved GS base for sandbox
};
```

**Pre-allocated code block pool:**

```c
#define CODE_BLOCK_POOL_SIZE  64
#define CODE_BLOCK_PAGES      160  // 640KB per block

static void *code_pool[CODE_BLOCK_POOL_SIZE];
static int code_pool_free;
static DEFINE_SPINLOCK(code_pool_lock);

void kd_exe_init(void) {
    for (i = 0; i < CODE_BLOCK_POOL_SIZE; i++) {
        code_pool[i] = vmalloc(CODE_BLOCK_PAGES * PAGE_SIZE);
        set_memory_x((unsigned long)code_pool[i], CODE_BLOCK_PAGES);
    }
    code_pool_free = CODE_BLOCK_POOL_SIZE;
}
```

**Key functions:**

```c
// Register a new CS entry (called from lock hook, may have IRQs off)
void kd_exe_add(int pid, unsigned long cs_rip);

// Execute sandbox for combiner delegation
// Returns: RUN_TO_UNLOCK, NO_RUN, RUN_ERROR
int kd_exe_run(struct pt_regs *regs, void *outgoing_rsp);

// Lookup entry by (pid, rip)
struct kd_exe_entry *kd_exe_lookup(int pid, unsigned long rip);
```

### 3.2 Sandbox Execution (kd_exe_run)

```c
int kd_exe_run(struct pt_regs *regs, void *outgoing_rsp)
{
    struct kd_exe_entry *exe = kd_exe_lookup(current->pid, regs->ip);

    if (!exe || exe->status != EXE_READY)
        return NO_RUN;

    // Prepare sandbox arguments
    unsigned long args[2] = { exe->gsbase, 0 };

    // Call translated code block as function pointer
    void (*sandbox)(struct pt_regs *, unsigned long *) = exe->code_block;
    sandbox(regs, args);

    // Interpret sandbox return code (in args[0])
    switch (args[0]) {
    case 0x0:  // syscall encountered (not expected in kernel CS)
        return RUN_ERROR;
    case 0x1:  // CALL_MISS
        if (is_unlock_function(regs->ip))
            return RUN_TO_UNLOCK;  // CS completed!
        exe->miss_target = regs->ip;
        exe->status = EXE_CALL_MISS;
        return RUN_ERROR;
    case 0x4:  // instruction limit
        return RUN_ERROR;
    default:   // indirect jump miss (args[0] = source addr)
        exe->miss_source = args[0];
        exe->miss_target = regs->ip;
        exe->status = EXE_IJ_MISS;
        return RUN_ERROR;
    }
}
```

### 3.3 End-Point Detection

```c
// Addresses of kernel unlock functions (must match running kernel)
static unsigned long unlock_endpoints[] = {
    0, // filled at module init via kallsyms_lookup_name
    0,
};

void kd_exe_init_endpoints(void) {
    unlock_endpoints[0] = kallsyms_lookup_name("_raw_spin_unlock");
    unlock_endpoints[1] = kallsyms_lookup_name("mutex_unlock");
}

static bool is_unlock_function(unsigned long addr) {
    for (int i = 0; i < ARRAY_SIZE(unlock_endpoints); i++)
        if (addr == unlock_endpoints[i])
            return true;
    return false;
}
```

### 3.4 Character Device (/dev/kd_dev)

**File:** `kernel_module/kd_sys.c`

Provides communication channel between kernel module and userspace daemon.

```c
// Read: daemon reads array of kd_exe_entry (status != READY)
static ssize_t kd_dev_read(struct file *f, char __user *buf,
                           size_t count, loff_t *off);

// Write: daemon writes translated binary back
//   Header: struct kd_recv_pkt { status, pid, rip, offset }
//   Body: raw jit.bin bytes
static ssize_t kd_dev_write(struct file *f, const char __user *buf,
                            size_t count, loff_t *off);
```

---

## Phase 4: Dynamic Translation (Userspace)

### 4.1 Daemon

**File:** `daemon/daemon.c`

Polling loop that drives the translation pipeline:

```c
void daemon_loop(void) {
    while (running) {
        entries[] = read_dev("/dev/kd_dev");
        for each entry in entries:
            switch (entry.status):
            case EXE_UNINIT:
                init_workspace(entry);
                translate(entry);
                write_binary(entry);
                break;
            case EXE_CALL_MISS:
                append_callee_table(entry.miss_target);
                retranslate(entry);
                write_binary(entry);
                break;
            case EXE_IJ_MISS:
                append_ij_table(entry.miss_source, entry.miss_target);
                retranslate(entry);
                write_binary(entry);
                break;
        usleep(poll_interval);
    }
}
```

**Key functions:**

```c
void init_workspace(entry)
    // mkdir workspace/<RIP>/<tgid>/
    // cp asm/ template (wrapper.S, asm_head.h)

void translate(entry)
    // Invoke: python3 disassem.py <pid> <rip>
    // Produces: workspace/asm/jit.S

void assemble(entry)
    // gcc -c wrapper.S → wrapper.o
    // objcopy -O binary wrapper.o jit.bin

void write_binary(entry)
    // Read jit.bin, send to /dev/kd_dev in chunks with kd_recv_pkt header
```

### 4.2 Disassembler / Translator

**File:** `disassem/disassem.py`

**Pipeline:**

```python
def dis_assem(pid, entry_rip):
    # 1. Read kernel text
    bytecode, targets = memread.read(pid, entry_rip)

    # 2. Disassemble into CFG using miasm
    machine = Machine("x86_64")
    mdis = machine.dis_engine(bytecode)
    mdis.dont_dis_retcall_funcs = {SPIN_UNLOCK_ADDR, MUTEX_UNLOCK_ADDR}
    cfg = mdis.dis_multiblock(entry_rip)

    # 3. Translate each basic block
    for block in sorted(cfg.blocks):
        for instruction in block:
            translated = translate(instruction, ...)
            write_to_jit_s(translated)
```

**Key translation modules:**

| Module | Responsibility |
|--------|---------------|
| `memread.py` | Read kernel bytes from `/proc/kcore` |
| `disassem.py` | Main driver: disassemble → translate → output |
| `translation.py` | Dispatch: normal / branch / special instruction |
| `normal.py` | Translate regular instructions (MOV, ADD, etc.) |
| `special_inst.py` | Handle CALL, RET, SYSCALL, etc. |
| `indirect_jump.py` | Build jump tables for indirect branches |
| `conflict.py` | Register conflict resolution (R12/R13/R14/R15 remapping) |
| `assist.py` | Helper utilities |

### 4.3 Sandbox Code Model

**Register convention inside sandbox:**

| Physical Register | Sandbox Role | Original Value |
|-------------------|-------------|----------------|
| R14 | PT_REG pointer | → struct pt_regs |
| R15 | ARG_REG pointer | → args[2] |
| R13 | Virtual RSP | Logical stack pointer |
| R12 | Virtual RBP | Logical frame pointer |
| R11 | Instruction counter | Incremented per block |
| RAX-RDI, R8-R10 | Normal use | Waiter's actual values |

**Translation rules:**

1. **RSP references** → replaced with R13 (virtual RSP)
2. **RBP references** → replaced with R12 (virtual RBP)
3. **PUSH/POP** → translated to R13 manipulation + memory store/load
4. **CALL target** → if target in callee_table: inline/translate
                   → if target unknown: emit CALL_MISS exit sequence
5. **RET** → should not appear (CS doesn't return normally)
6. **Indirect JMP** → lookup in ij_table, emit IJ_MISS if not found
7. **Memory access** → bounds-check base register (non-canonical → seg_error)
8. **SYSCALL** → emit comp_syscall exit (return to engine)

**CALL_MISS exit sequence (generated for unknown callees):**

```asm
MOVABS  R14, <target_address>    ; store target in virtual RIP
MOV     Stack_IJ, 0x1            ; return code = CALL_MISS
JMP     exit                     ; return to wrapper epilogue
```

**Instruction counting (per basic block header):**

```asm
MOVABS  R14, <block_address>     ; track current position
INC     R11                      ; increment counter
TEST    R11, 0x1000000           ; check limit (~16M)
JNZ     inst_limit               ; bail if exceeded
```

### 4.4 Wrapper (include/wrapper.S)

The wrapper provides the C-callable entry/exit around translated code:

```
Function signature: void sandbox(struct pt_regs *regs, unsigned long *args)
                                  RDI                   RSI

PROLOGUE:
  1. push rbp; mov rbp, rsp          (standard frame)
  2. push rbx, r12-r15               (save callee-saved)
  3. push rdi, rsi                   (save PT_REG, ARG_REG pointers)
  4. R14 = rdi (PT_REG), R15 = rsi (ARG_REG)
  5. Load all GPRs from pt_regs into physical registers
  6. Push virtual state onto stack: RBP, RSP, R15-R11, GS, FS
  7. Allocate space for: RIP, IJ_code, INST_CNT
  8. R13 = virtual RSP, R12 = virtual RBP
  9. Fall through to jit.S

TRANSLATED CODE (jit.S):
  ... executes until hitting exit label ...

EXIT LABELS:
  comp_syscall: Stack_IJ = 0x0; JMP exit    (syscall)
  ij_failed:   Stack_IJ = R15; JMP exit     (indirect jump miss)
  seg_error:   JMP exit                      (memory fault)
  inst_limit:  Stack_IJ = 0x4; JMP exit     (too many instructions)

EPILOGUE (exit):
  1. Save R14→Stack_RIP, R13→Stack_RSP, R12→Stack_RBP
  2. Reload PT_REG and ARG_REG from stack
  3. Pop IJ_code → args[0], INST_CNT → args[1], RIP → pt_regs->ip
  4. Pop virtual state, write back all GPRs to pt_regs
  5. Restore callee-saved, pop rbp, ret
```

---

## Phase 5: Module Initialization & Lifecycle

### 5.1 Module Init

**File:** `kernel_module/kd_main.c`

```c
static int __init kdlock_init(void)
{
    // 1. Parse target_process parameter
    parse_target_names(target_process);

    // 2. Initialize subsystems
    kd_exe_init();           // pre-allocate code block pool
    kd_exe_init_endpoints(); // resolve unlock function addresses
    kd_spinlock_init();      // allocate per-CPU shadow stacks + nodes
    kd_mutex_init_percpu();  // allocate per-CPU mutex shadow stacks
    kd_sys_init();           // register /dev/kd_dev

    // 3. Install hooks (atomic — enables interception)
    is_kd_test = __is_kd_test;
    kd_raw_spin_lock = __kd_raw_spin_lock;
    kd_raw_spin_unlock = __kd_raw_spin_unlock;
    kd_mutex_lock = __kd_mutex_lock;
    kd_mutex_unlock = __kd_mutex_unlock;

    return 0;
}
```

### 5.2 Module Exit

```c
static void __exit kdlock_exit(void)
{
    // 1. Disable hooks (atomic — stops interception)
    kd_raw_spin_lock = NULL;
    kd_raw_spin_unlock = NULL;
    kd_mutex_lock = NULL;
    kd_mutex_unlock = NULL;
    is_kd_test = NULL;

    // 2. Synchronize (ensure no CPU is mid-delegation)
    synchronize_rcu();

    // 3. Teardown subsystems
    kd_spinlock_exit();      // free shadow stacks
    kd_mutex_exit();         // free mutex shadow stacks
    kd_sys_exit();           // unregister /dev/kd_dev
    kd_exe_exit();           // free code block pool + entries
}
```

---

## Phase 6: Testing & Verification

### 6.1 Test Module

**File:** `klock_module/klock_module.c`

A small kernel module that exposes `/dev/lock_dev` with ioctl-driven workloads:

```c
// Benchmark modes:
// 0: contended single spinlock
// 1: nested spinlocks (A then B)
// 2: spinlock with kernel API call inside CS
// 3: contended single mutex
// 4: nested mutexes
// 5: mutex with kernel API call inside CS
```

### 6.2 Userspace Benchmark Driver

**File:** `bench/klock_test.c`

```c
// Usage: klock_test <threads> <iterations> <cs_work> <non_cs_work> <mode>
// Spawns threads that hammer /dev/lock_dev
```

### 6.3 End-to-End Test Procedure

```bash
# Terminal 1: Load modules
sysctl -w kernel.randomize_va_space=0
insmod kdlock_km.ko target_process="klock_test"
insmod klock_module.ko

# Terminal 2: Start daemon
cd daemon/ && ./daemon --mode 2

# Terminal 1: Run benchmark
./bench/klock_test 4 100000 1000 10 0   # spinlock
./bench/klock_test 4 100000 1000 10 3   # mutex

# Verify: check dmesg for delegation success/failure stats
dmesg -T | grep "kd_exe\|delegation"
```

---

## File Layout Summary

```
kdlock/
├── kernel_module/
│   ├── kd_main.c          # Module init/exit, hook installation
│   ├── kd_lock.c          # Hook implementations, fallback paths
│   ├── kd_spinlock.c      # Spinlock delegation protocol
│   ├── kd_mutex.c         # Mutex delegation protocol
│   ├── kd_exe.c           # JIT execution engine
│   ├── kd_hotlock.c       # Hot-lock promotion logic
│   ├── kd_sys.c           # /dev/kd_dev char device
│   ├── combiner.S         # kd_context_switch (asm, if needed)
│   └── Makefile
├── include/
│   ├── kd_lock.h          # Hook function declarations
│   ├── kd_spinlock.h      # Spinlock types and constants
│   ├── kd_mutex.h         # Mutex types
│   ├── exe_info.h         # kd_exe_entry, kd_recv_pkt
│   ├── combiner.h         # Shared constants, batch size externs
│   ├── wrapper.S          # Sandbox prologue/epilogue
│   └── asm_head.h         # Register/stack slot definitions
├── daemon/
│   ├── daemon.c           # Polling loop, workspace management
│   ├── asm/               # Template: wrapper.S, asm_head.h
│   └── Makefile
├── disassem/
│   ├── disassem.py        # Main translator driver
│   ├── memread.py         # Read kernel text from /proc/kcore
│   ├── translation.py     # Instruction translation dispatch
│   ├── normal.py          # Normal instruction translation
│   ├── special_inst.py    # CALL/RET/SYSCALL handling
│   ├── indirect_jump.py   # Indirect jump table management
│   └── conflict.py        # Register conflict resolution
├── klock_module/
│   ├── klock_module.c     # Test workload module
│   └── Makefile
├── bench/
│   └── klock_test.c       # Userspace benchmark driver
└── PLAN.md                # This file
```

---

## Implementation Order (Recommended)

| Step | Component | Depends On | Deliverable |
|------|-----------|-----------|-------------|
| 1 | Kernel patch | — | Hook function pointers exported |
| 2 | kd_main.c + kd_sys.c | Step 1 | Module loads, /dev/kd_dev works |
| 3 | kd_exe.c (pool + add + lookup) | Step 2 | Entries registered, readable by daemon |
| 4 | daemon.c + disassem/ | Step 3 | Translation pipeline produces jit.bin |
| 5 | wrapper.S + asm_head.h | — | Sandbox calling convention defined |
| 6 | kd_spinlock.c (full protocol) | Steps 3,5 | Spinlock delegation with JIT sandbox |
| 7 | kd_hotlock.c | Step 6 | Only hot locks enter delegation |
| 8 | kd_mutex.c | Step 6 | Mutex delegation (same model) |
| 9 | Nested lock handling | Step 6 | ENABLE_IRQS_CHECK, OOO unlock |
| 10 | klock_module + bench | Steps 6,8 | End-to-end testing |

