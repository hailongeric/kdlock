// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi
//
// Ported to kdlock: TCLocks komb.c → kd_spinlock.c
//
// kd_spinlock implements transparent delegation for kernel spinlocks.
// The protocol uses a per-CPU MCS-style queue with a combiner/waiter model:
// the lock holder (combiner) executes critical sections on behalf of queued
// waiters via kd_context_switch.  JIT-translated sandbox code is run through
// kd_exe_on_call_hl() (see exe.c).
//
// Key differences from TCLocks komb.c:
//   - Calls kd_exe_on_call_hl() inside execute_cs() for JIT delegation
//   - Uses kd_spin_node (renamed from komb_node) with embedded pt_regs
//   - Delegation via sandbox JIT, not raw stack-switch

/*
 * TODO: (Performance optimiztion)
 * Fix the index part when same is acquired multiple times.
 * Currently nested locking becomes TTAS lock.
 * irqs_disabled() will hurt performance when running in VM.
 */
// #ifdef KERNEL_SYNCSTRESS
#include "kd_spinlock.h"
#include "timing_stats.h"
#include "utils.h"
#include "exe.h"
#include "kd_exec.h"
#include "kd_segment.h"
// #else
// #include <asm-generic/qspinlock.h>
#include <linux/sched.h>
// #include <linux/combiner.h>
// #define LOCK_START_TIMING_PER_CPU(combiner_loop)
// #define LOCK_END_TIMING_PER_CPU(combiner_loop)
// #endif

// #include <linux/topology.h>
#include <linux/vmalloc.h>

// #include <linux/percpu-defs.h>
#include <linux/kernel.h>
// #include <linux/syscalls.h>



#define SIZE_OF_SHADOW_STACK 8192L
#define IRQ_NUMA_NODE 255

// #define DEBUG_KD_SPIN 1

#define UINT64_MAX 0xffffffffffffffffL
#define KD_SPIN_DIAG_SLOTS 32

enum kd_spin_diag_event {
    KD_SPIN_DIAG_SLOWPATH = 0,
    KD_SPIN_DIAG_COMBINER,
    KD_SPIN_DIAG_JIT_SUCCESS,
    KD_SPIN_DIAG_JIT_NOT_READY,
    KD_SPIN_DIAG_NESTED_LOCK,
    KD_SPIN_DIAG_NESTED_UNLOCK,
    KD_SPIN_DIAG_NESTED_REMOTE,
    KD_SPIN_DIAG_NATIVE_FALLBACK,
    KD_SPIN_DIAG_OOO_UNLOCK,
    KD_SPIN_DIAG_EVENT_COUNT,
};

struct kd_spin_diag_slot {
    atomic_long_t addr;
    atomic64_t event[KD_SPIN_DIAG_EVENT_COUNT];
    atomic_t max_depth;
    atomic_t waiter_count;
    atomic_t jit_disabled;
};

static struct kd_spin_diag_slot kd_spin_diag_slots[KD_SPIN_DIAG_SLOTS];
static atomic64_t kd_spin_diag_overflow;
static atomic64_t kd_spin_diag_invariant_failures;

#ifdef KERNEL_SYNCSTRESS
#define smp_cond_load_relaxed_sched(ptr, cond_expr) \
    ({                                              \
        typeof(ptr) __PTR = (ptr);                  \
        __unqual_scalar_typeof(*ptr) VAL;           \
        for (;;)                                    \
        {                                           \
            VAL = READ_ONCE(*__PTR);                \
            if (cond_expr)                          \
                break;                              \
            cpu_relax();                            \
            if (need_resched())                     \
            {                                       \
                preempt_enable();                   \
                schedule();                         \
                preempt_disable();                  \
            }                                       \
        }                                           \
        (typeof(*ptr))VAL;                          \
    })
#else
#define smp_cond_load_relaxed_sched(ptr, cond_expr) \
    ({                                              \
        typeof(ptr) __PTR = (ptr);                  \
        __unqual_scalar_typeof(*ptr) VAL;           \
        for (;;)                                    \
        {                                           \
            VAL = READ_ONCE(*__PTR);                \
            if (cond_expr)                          \
                break;                              \
            cpu_relax();                            \
        }                                           \
        (typeof(*ptr))VAL;                          \
    })

// if (need_resched()) {
//	schedule_preempt_disabled();
// }
#endif

#ifndef smp_cond_load_acquire_sched
#define smp_cond_load_acquire_sched(ptr, cond_expr)         \
    ({                                                      \
        __unqual_scalar_typeof(*ptr) _val;                  \
        _val = smp_cond_load_relaxed_sched(ptr, cond_expr); \
        smp_acquire__after_ctrl_dep();                      \
        (typeof(*ptr))_val;                                 \
    })
#endif

#define atomic_cond_read_acquire_sched(v, c) \
    smp_cond_load_acquire_sched(&(v)->counter, (c))

struct shadow_stack
{
    /*
     * lock_addr represents the lock addresses acquired by the current CPU.
     * when acquiring multiple locks on the same CPU (level locking). Each
     * lock address is stored in the lock_addr array. This helps when locks
     * are released out of order [Example : Acquire(A), Acquire(B),
     * Release(A), Release(B)]
     *
     * TODO (Space Optimization): Fix this to be at the base of the shadow
     * stack.
     */
    uint64_t lock_addr[8];

    /*
     * ptr points to the base of the shadow stack.
     */
    void *ptr;
    /*
     * Used by the combiner to identify for which CPU is the critical section
     * currently executing.
     */
    uint32_t curr_cs_cpu;
    uint32_t prev_cs_cpu;
    uint64_t counter_val;
    struct kd_spin_node *next_node_ptr;
    uint64_t local_shadow_stack_ptr;
#ifdef NUMA_AWARE
    /*
     * Create a queue which is used by the combiner to store nodes which belong to
     * different socket.
     */

    struct kd_spin_node *local_queue_head;
    struct kd_spin_node *local_queue_tail;
#endif

    int irqs_disabled;

} __cacheline_aligned_in_smp;

#ifdef LOCK_MEASURE_TIME
static DEFINE_PER_CPU_ALIGNED(uint64_t, combiner_loop);
static DEFINE_PER_CPU_ALIGNED(uint64_t, lock_stack_switch);
static DEFINE_PER_CPU_ALIGNED(uint64_t, unlock_stack_switch);
#endif

#ifdef KD_SPIN_STATS
DEFINE_PER_CPU_ALIGNED(uint64_t, combiner_count);
DEFINE_PER_CPU_ALIGNED(uint64_t, waiter_combined);
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_combiner_count);
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_waiter_combined);
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_unlocks);
#endif

/*
 * Used by all threads to add itself to the queue on the slowpath.
 */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_spin_node, kd_spin_nodes[MAX_NODES]);

struct kd_spin_native_input {
    unsigned long rsp;
    unsigned long regs_sp;
};

static DEFINE_PER_CPU(struct kd_spin_native_input, kd_spin_native_inputs);
static DEFINE_PER_CPU(struct kd_spin_node *, kd_spin_resume_nodes);

struct kd_spin_jit_context {
    unsigned int lock_depth;
    unsigned long lock_addr[KD_EXEC_MAX_LOCK_DEPTH];
    enum kd_exec_lock_kind lock_kind[KD_EXEC_MAX_LOCK_DEPTH];
    void *lock_node[KD_EXEC_MAX_LOCK_DEPTH];
    bool lock_released[KD_EXEC_MAX_LOCK_DEPTH];
};

static DEFINE_PER_CPU(struct kd_spin_jit_context *, kd_spin_jit_contexts);

/*
 * 8KB shadow stack used by all the threads. For waiter threads, switch to
 * shadow stack, because of IRQs. For combiner thread, switch to shadow stack
 * to handle nesting
 */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct shadow_stack, local_shadow_stack);

#define _Q_LOCKED_PENDING_MASK (_Q_LOCKED_MASK_HL | _Q_PENDING_MASK_HL)
#define _Q_LOCKED_COMBINER_VAL 3
#define _Q_UNLOCKED_OOO_VAL 7 // Unlocked a lock out-of-order
#define _Q_LOCKED_IRQ_VAL 15  // Lock Stealing by IRQ

static void
kd_spin_diag_validate_lock_stack(const struct shadow_stack *ptr);

static inline unsigned int
kd_spin_lock_stack_depth(const struct shadow_stack *ptr)
{
    unsigned int depth = 0;

    while (depth < ARRAY_SIZE(ptr->lock_addr) &&
           READ_ONCE(ptr->lock_addr[depth]) != 0)
        depth++;

    return depth;
}

int kd_spin_nested_shadow_push(struct qspinlock *lock)
{
    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
    unsigned int depth;

    if (!lock)
        return -EINVAL;

    depth = kd_spin_lock_stack_depth(ptr);
    if (depth >= ARRAY_SIZE(ptr->lock_addr))
        return -E2BIG;

    if (kd_exec_frame_lock_depth(kd_exec_current_frame()) &&
        kd_exec_frame_lock_contains(kd_exec_current_frame(),
                                     (unsigned long)lock))
        return -EDEADLK;

    WRITE_ONCE(ptr->lock_addr[depth], (uint64_t)lock);
    kd_spin_diag_validate_lock_stack(ptr);
    return 0;
}

int kd_spin_nested_shadow_remove(struct qspinlock *lock)
{
    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
    unsigned int depth, i;

    if (!lock)
        return -EINVAL;

    depth = kd_spin_lock_stack_depth(ptr);
    for (i = 0; i < depth; i++) {
        if (ptr->lock_addr[i] != (uint64_t)lock)
            continue;

        for (; i + 1 < depth; i++)
            ptr->lock_addr[i] = ptr->lock_addr[i + 1];
        ptr->lock_addr[depth - 1] = 0;
        kd_spin_diag_validate_lock_stack(ptr);
        return 0;
    }

    return -ENOENT;
}

int kd_spin_nested_shadow_pop(struct qspinlock *lock)
{
    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
    unsigned int depth;

    if (!lock)
        return -EINVAL;
    depth = kd_spin_lock_stack_depth(ptr);
    if (!depth || ptr->lock_addr[depth - 1] != (uint64_t)lock)
        return -EINVAL;
    return kd_spin_nested_shadow_remove(lock);
}

static void
kd_spin_capture_combiner_state(struct kd_combiner_state *saved,
                               const struct shadow_stack *ptr)
{
    unsigned int i;

    for (i = 0; i < KD_EXEC_MAX_LOCK_DEPTH; i++)
        saved->lock_addr[i] = READ_ONCE(ptr->lock_addr[i]);
    saved->lock_depth = kd_spin_lock_stack_depth(ptr);
    saved->curr_cs_cpu = ptr->curr_cs_cpu;
    saved->prev_cs_cpu = ptr->prev_cs_cpu;
    saved->counter_val = ptr->counter_val;
    saved->next_node_ptr = ptr->next_node_ptr;
    saved->local_shadow_stack_ptr = ptr->local_shadow_stack_ptr;
#ifdef NUMA_AWARE
    saved->local_queue_head = ptr->local_queue_head;
    saved->local_queue_tail = ptr->local_queue_tail;
#else
    saved->local_queue_head = NULL;
    saved->local_queue_tail = NULL;
#endif
    saved->irqs_disabled = ptr->irqs_disabled;
}

static bool
kd_spin_combiner_state_matches(const struct kd_combiner_state *saved,
                               const struct shadow_stack *ptr)
{
    unsigned int i;

    if (!saved || !ptr ||
        saved->lock_depth != kd_spin_lock_stack_depth(ptr) ||
        saved->curr_cs_cpu != ptr->curr_cs_cpu ||
        saved->prev_cs_cpu != ptr->prev_cs_cpu ||
        saved->counter_val != ptr->counter_val ||
        saved->next_node_ptr != ptr->next_node_ptr ||
        saved->local_shadow_stack_ptr != ptr->local_shadow_stack_ptr ||
        saved->irqs_disabled != ptr->irqs_disabled)
        return false;
#ifdef NUMA_AWARE
    if (saved->local_queue_head != ptr->local_queue_head ||
        saved->local_queue_tail != ptr->local_queue_tail)
        return false;
#endif
    for (i = 0; i < KD_EXEC_MAX_LOCK_DEPTH; i++) {
        if (saved->lock_addr[i] != READ_ONCE(ptr->lock_addr[i]))
            return false;
    }
    return true;
}

static __always_inline void
kd_spin_diag_invariant_failure(void)
{
    atomic64_inc(&kd_spin_diag_invariant_failures);
    WARN_ON_ONCE(1);
}

static void
kd_spin_diag_validate_lock_stack(const struct shadow_stack *ptr)
{
    bool hole_seen = false;
    unsigned int i;

    for (i = 0; i < ARRAY_SIZE(ptr->lock_addr); i++) {
        if (READ_ONCE(ptr->lock_addr[i]) != 0) {
            if (hole_seen)
                kd_spin_diag_invariant_failure();
        } else {
            hole_seen = true;
        }
    }
}

static void
kd_spin_diag_validate_outer_unlock(const struct shadow_stack *ptr,
                                   struct qspinlock *lock,
                                   int my_idx, int max_idx)
{
    if (my_idx < 0)
        return;

    if (my_idx > max_idx || ptr->lock_addr[my_idx] != lock)
        kd_spin_diag_invariant_failure();

    if (my_idx == max_idx &&
        READ_ONCE(lock->locked) != _Q_LOCKED_COMBINER_VAL)
        kd_spin_diag_invariant_failure();
}

static struct kd_spin_diag_slot *
kd_spin_diag_find(unsigned long addr)
{
    unsigned int start;
    unsigned int i;

    if (!addr)
        return NULL;

    start = (unsigned int)(((addr >> 6) ^ (addr >> 17)) %
                           KD_SPIN_DIAG_SLOTS);
    for (i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
        struct kd_spin_diag_slot *slot =
            &kd_spin_diag_slots[(start + i) % KD_SPIN_DIAG_SLOTS];
        long observed = atomic_long_read(&slot->addr);

        if ((unsigned long)observed == addr)
            return slot;
        if (observed == 0) {
            observed = atomic_long_cmpxchg(&slot->addr, 0, (long)addr);
            if (observed == 0 || (unsigned long)observed == addr)
                return slot;
        }
    }

    atomic64_inc(&kd_spin_diag_overflow);
    return NULL;
}

static void
kd_spin_diag_record_addr(unsigned long addr, enum kd_spin_diag_event event,
                         unsigned int depth)
{
    struct kd_spin_diag_slot *slot;
    int old_depth;

    if (event >= KD_SPIN_DIAG_EVENT_COUNT)
        return;

    slot = kd_spin_diag_find(addr);
    if (!slot)
        return;

    atomic64_inc(&slot->event[event]);
    old_depth = atomic_read(&slot->max_depth);
    while (old_depth < (int)depth) {
        int previous = atomic_cmpxchg(&slot->max_depth, old_depth, depth);

        if (previous == old_depth)
            break;
        old_depth = previous;
    }
}

static void
kd_spin_diag_record(struct qspinlock *lock, enum kd_spin_diag_event event,
                    unsigned int depth)
{
    kd_spin_diag_record_addr((unsigned long)lock, event, depth);
}

static bool kd_spin_jit_is_disabled(struct qspinlock *lock)
{
    struct kd_spin_diag_slot *slot =
        kd_spin_diag_find((unsigned long)lock);

    return slot && atomic_read_acquire(&slot->jit_disabled);
}

static void kd_spin_jit_disable(struct qspinlock *lock)
{
    struct kd_spin_diag_slot *slot =
        kd_spin_diag_find((unsigned long)lock);

    if (!slot)
        return;
    if (atomic_cmpxchg(&slot->jit_disabled, 0, 1) == 0)
        kd_spin_diag_record(lock, KD_SPIN_DIAG_NATIVE_FALLBACK,
                            kd_spin_lock_stack_depth(
                                this_cpu_ptr(&local_shadow_stack)));
}

static void kd_spin_diag_waiter_enter(struct qspinlock *lock)
{
    struct kd_spin_diag_slot *slot = kd_spin_diag_find((unsigned long)lock);

    if (slot)
        atomic_inc(&slot->waiter_count);
}

static void kd_spin_diag_waiter_exit(struct qspinlock *lock)
{
    struct kd_spin_diag_slot *slot = kd_spin_diag_find((unsigned long)lock);

    if (!slot)
        return;
    if (unlikely(atomic_dec_return(&slot->waiter_count) < 0)) {
        atomic_set(&slot->waiter_count, 0);
        kd_spin_diag_invariant_failure();
    }
}

int kd_spin_debug_waiter_count(raw_spinlock_t *lock)
{
    struct kd_spin_diag_slot *slot;

    if (!lock)
        return -EINVAL;
    slot = kd_spin_diag_find((unsigned long)lock);
    return slot ? atomic_read(&slot->waiter_count) : -ENOSPC;
}
EXPORT_SYMBOL_GPL(kd_spin_debug_waiter_count);

static void
kd_spin_diag_record_nested(raw_spinlock_t *lock,
                           enum kd_spin_diag_event event,
                           bool native_fallback)
{
    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
    unsigned int depth = kd_spin_lock_stack_depth(ptr);

    kd_spin_diag_record_addr((unsigned long)lock, event, depth);
    if (native_fallback)
        kd_spin_diag_record_addr((unsigned long)lock,
                                 KD_SPIN_DIAG_NATIVE_FALLBACK, depth);
}

void kd_spin_debug_combiner(struct qspinlock *lock, unsigned int depth)
{
    kd_spin_diag_record(lock, KD_SPIN_DIAG_COMBINER, depth);
}

void kd_spin_debug_jit_success(struct qspinlock *lock, unsigned int depth)
{
    kd_spin_diag_record(lock, KD_SPIN_DIAG_JIT_SUCCESS, depth);
}

void kd_spin_debug_jit_not_ready(struct qspinlock *lock, unsigned int depth)
{
    kd_spin_diag_record(lock, KD_SPIN_DIAG_JIT_NOT_READY, depth);
}

void kd_spin_debug_nested_lock(raw_spinlock_t *lock, bool native_fallback)
{
    kd_spin_diag_record_nested(lock, KD_SPIN_DIAG_NESTED_LOCK,
                               native_fallback);
}

void kd_spin_debug_nested_unlock(raw_spinlock_t *lock)
{
    kd_spin_diag_record_nested(lock, KD_SPIN_DIAG_NESTED_UNLOCK, false);
}

void kd_spin_debug_nested_remote(raw_spinlock_t *lock)
{
    kd_spin_diag_record_nested(lock, KD_SPIN_DIAG_NESTED_REMOTE, false);
}

void kd_spin_debug_ooo_unlock(struct qspinlock *lock, unsigned int depth)
{
    kd_spin_diag_record(lock, KD_SPIN_DIAG_OOO_UNLOCK, depth);
}
/*
 * We must be able to distinguish between no-tail and the tail at 0:0,
 * therefore increment the cpu number by one.
 */
static inline u32 encode_tail(int cpu, int idx)
{
    u32 tail;

    tail = (cpu + 1) << _Q_TAIL_CPU_OFFSET_HL;
    tail |= idx << _Q_TAIL_IDX_OFFSET_HL; /* assume < 4 */

    return tail;
}

static inline struct kd_spin_node *decode_tail(u32 tail)
{
    int cpu = (tail >> _Q_TAIL_CPU_OFFSET_HL) - 1;
    int idx = (tail & _Q_TAIL_IDX_MASK_HL) >> _Q_TAIL_IDX_OFFSET_HL;

    return per_cpu_ptr(&kd_spin_nodes[idx], cpu);
}

static __always_inline void
kd_spin_set_resume_node(struct kd_spin_node *node)
{
    WRITE_ONCE(*this_cpu_ptr(&kd_spin_resume_nodes), node);
}

inline u32 get_cpu_from_tail(u32 tail)
{
    return ((tail >> _Q_TAIL_CPU_OFFSET_HL) - 1);
}

static inline bool check_irq_node(struct kd_spin_node *node)
{
    return (node->socket_id == IRQ_NUMA_NODE || node->rsp == 0xdeadbeef);
}

__always_inline void clear_locked_set_completed(struct kd_spin_node *lock)
{
    WRITE_ONCE(lock->locked_completed, 1);
}

__always_inline void clear_pending_set_locked(struct qspinlock *lock)
{
#ifdef DEBUG_KD_SPIN
    BUG_ON(lock->locked != 0);
#endif
    WRITE_ONCE(lock->locked_pending, _Q_LOCKED_VAL_HL);
}

static __always_inline u32 xchg_tail(struct qspinlock *lock, u32 tail)
{
    return ((u32)xchg(&lock->tail, tail >> _Q_TAIL_OFFSET_HL))
           << _Q_TAIL_OFFSET_HL;
}

__always_inline u32 cmpxchg_tail(struct qspinlock *lock, u32 tail, u32 new_tail)
{
    return ((u32)cmpxchg(&lock->tail, tail >> _Q_TAIL_OFFSET_HL,
                         new_tail >> _Q_TAIL_OFFSET_HL))
           << _Q_TAIL_OFFSET_HL;
}

/**
 * clear_pending - clear the pending bit.
 * @lock: Pointer to queued spinlock structure
 *
 * *,1,* -> *,0,*
 */
static __always_inline void clear_pending(struct qspinlock *lock)
{
    atomic_andnot(_Q_PENDING_VAL_HL, &lock->val);
}

/**
 * set_locked - Set the lock bit and own the lock
 * @lock: Pointer to queued spinlock structure
 *
 * *,*,0 -> *,0,1
 */
static __always_inline void set_locked(struct qspinlock *lock)
{
    WRITE_ONCE(lock->locked, _Q_LOCKED_VAL_HL);
}

static __always_inline void check_and_set_combiner(struct qspinlock *lock)
{
    u32 val, new_val;

#ifdef DEBUG_KD_SPIN
    BUG_ON(lock->locked == _Q_LOCKED_VAL_HL);
#endif

    if (lock->locked > 0)
    {
        while (true)
        {
            val = atomic_cond_read_relaxed(
                &lock->val, !(VAL & _Q_LOCKED_PENDING_MASK));

#ifdef DEBUG_KD_SPIN
            BUG_ON(lock->locked != 0);
#endif

            new_val = val >> _Q_LOCKED_BITS_HL;
            new_val <<= _Q_LOCKED_BITS_HL;
            new_val |= _Q_LOCKED_COMBINER_VAL;

            if (atomic_cmpxchg_acquire(&lock->val, val, new_val) ==
                val)
                return;
        }
    }
    WRITE_ONCE(lock->locked, _Q_LOCKED_COMBINER_VAL);
}

/**
 * queued_fetch_set_pending_acquire - fetch the whole lock value and set pending
 * @lock : Pointer to queued spinlock structure
 * Return: The previous lock value
 *
 * *,*,* -> *,1,*
 */
static __always_inline u32 kd_spin_fetch_set_pending_acquire(struct qspinlock *lock)
{
    return atomic_fetch_or_acquire(_Q_PENDING_VAL_HL, &lock->val);
}

#ifdef NUMA_AWARE
__always_inline static void add_to_local_queue(struct kd_spin_node *node)
{
    // printk(KERN_ALERT "%d Move node to local queue: %d\n",
    //      smp_processor_id(), node->cpuid);

    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

    if (ptr->local_queue_head == NULL)
    {
        ptr->local_queue_head = node;
        ptr->local_queue_tail = node;
    }
    else
    {
        ptr->local_queue_tail->next = node;
        ptr->local_queue_tail = node;
    }
}
#endif

__always_inline static struct kd_spin_node *
get_next_node(struct kd_spin_node *my_node)
{
#ifdef NUMA_AWARE
    struct kd_spin_node *curr_node, *next_node;

    curr_node = my_node;
    next_node = curr_node->next;

    while (true)
    {
        if (next_node == NULL || next_node->next == NULL)
            goto next_node_null;
        else if (check_irq_node(next_node) ||
                 check_irq_node(next_node->next))
            goto next_node_null;

        if (next_node->socket_id == numa_node_id())
        {
#ifdef PREFETCHING
            void *rsp_ptr =
                (per_cpu_ptr(&kd_spin_nodes[0], next_node->cpuid)
                     ->rsp);
            prefetchw(rsp_ptr);
            int i;
            for (i = 1; i < NUM_PREFETCH_LINES; i++)
                prefetchw(rsp_ptr + (64 * i));

            prefetch(next_node->next);
#endif
            return next_node;
        }

        add_to_local_queue(next_node);
        curr_node = next_node;
        next_node = curr_node->next;
    }

next_node_null:
    return next_node;
#else
    return my_node->next;
#endif
}

#define get_rsp_from_regs(name, regs, i) ((unsigned long *)regs)[i]

#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
execute_cs(struct qspinlock *lock, struct kd_spin_node *curr_node)
{
    void *incoming_rsp_ptr, *outgoing_rsp_ptr;
    unsigned int frame_lock_depth;
    struct kd_spin_jit_context *jit_context = curr_node->jit_context;
    struct pt_regs retry_regs;
    bool abort_cleaned = false;

    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

    ptr->curr_cs_cpu = curr_node->cpuid;

    if (kd_spin_jit_is_disabled(lock)) {
        kd_spin_diag_record(lock, KD_SPIN_DIAG_NATIVE_FALLBACK,
                            kd_spin_lock_stack_depth(ptr));
        return KD_EXE_NO_RUN;
    }

#ifdef DEBUG_KD_SPIN
    BUG_ON(curr_node->cpuid == smp_processor_id());
    if ((ptr->ptr - (ptr->local_shadow_stack_ptr)) > SIZE_OF_SHADOW_STACK)
    {
        printk(KERN_ALERT "%d %px %px\n", smp_processor_id(), ptr->ptr,
               ptr->local_shadow_stack_ptr);
        BUG_ON(true);
    }
#endif

    incoming_rsp_ptr = (void *)curr_node->regs.sp;
    print_debug("incoming_rsp_ptr: %px\n", incoming_rsp_ptr);
    outgoing_rsp_ptr = &(ptr->local_shadow_stack_ptr);

#ifdef LOCK_MEASURE_TIME
    *this_cpu_ptr(&combiner_loop) = UINT64_MAX;
#endif

    /*
     * Make the actual switch, the pushed return address is after this
     * function call, which we will resume execution at using the switch
     * in unlock.
     */
#ifdef DEBUG_KD_SPIN
#ifdef ENABLE_IRQS_CHECK
    BUG_ON(irqs_disabled());
#endif

    BUG_ON(*(uint64_t *)incoming_rsp_ptr == NULL);
    BUG_ON(*(uint64_t *)outgoing_rsp_ptr == NULL);
#endif
    // local_irq_disable();
    //! todo modify those call_exe
    // kd_context_switch(incoming_rsp_ptr, outgoing_rsp_ptr);

    if (!curr_node->jit_waiter) {
        curr_node->regs.r15 = get_rsp_from_regs(r15, incoming_rsp_ptr, 5);
        curr_node->regs.r14 = get_rsp_from_regs(r14, incoming_rsp_ptr, 4);
        curr_node->regs.r13 = get_rsp_from_regs(r13, incoming_rsp_ptr, 3);
        curr_node->regs.r12 = get_rsp_from_regs(r12, incoming_rsp_ptr, 2);
        curr_node->regs.bx = get_rsp_from_regs(rbx, incoming_rsp_ptr, 1);
        curr_node->regs.bp = get_rsp_from_regs(rbp, incoming_rsp_ptr, 6);
        curr_node->regs.ip = get_rsp_from_regs(rip, incoming_rsp_ptr, 7);
        curr_node->regs.sp = ((unsigned long)incoming_rsp_ptr) + 64;
    }
    if (!kd_exe_is_ready(0, curr_node->regs.ip)) {
        kd_spin_debug_jit_not_ready(lock, kd_spin_lock_stack_depth(ptr));
        kd_exe_add(0, curr_node->regs.ip);
        return KD_EXE_NO_RUN;
    }
    print_debug("r15 %lx r14 %lx r13 %lx r12 %lx bx %lx bp %lx ip %lx sp %lx\n",
                curr_node->regs.r15, curr_node->regs.r14, curr_node->regs.r13,
                curr_node->regs.r12, curr_node->regs.bx, curr_node->regs.bp,
                curr_node->regs.ip, curr_node->regs.sp);
    if (curr_node->jit_waiter && !jit_context)
        return KD_EXE_RUN_ERROR;
    retry_regs = curr_node->regs;
    frame_lock_depth = curr_node->jit_waiter ?
        jit_context->lock_depth : kd_spin_lock_stack_depth(ptr);
    struct kd_exec_frame *frame =
        kd_exec_frame_push(&curr_node->regs,
                           curr_node->regs.ip,
                           (unsigned long)lock,
                           curr_node,
                           outgoing_rsp_ptr,
                           frame_lock_depth,
                           curr_node->gsbase,
                           curr_node->task_struct_ptr);
    int ret_flag;

    if (!frame) {
        KD_PR_ERR("spin JIT frame stack overflow lock=%px\n", lock);
        return KD_EXE_RUN_ERROR;
    }
    curr_node->exec_frame = frame;
    if ((curr_node->jit_waiter &&
         kd_exec_frame_set_lock_entries(frame,
                                        jit_context->lock_addr,
                                        jit_context->lock_kind,
                                        jit_context->lock_node,
                                        jit_context->lock_released,
                                        jit_context->lock_depth)) ||
        (!curr_node->jit_waiter &&
         kd_exec_frame_set_lock_stack(
             frame, (const unsigned long *)ptr->lock_addr,
             kd_spin_lock_stack_depth(ptr)))) {
        KD_PR_ERR("spin JIT frame lock stack invalid lock=%px\n", lock);
        kd_exec_frame_abort(frame);
        curr_node->regs = frame->regs;
        curr_node->exec_frame = NULL;
        if (kd_exec_frame_pop(frame, &curr_node->regs))
            KD_PR_ERR("spin JIT frame abort pop failed lock=%px\n", lock);
        return KD_EXE_RUN_ERROR;
    }
    kd_spin_capture_combiner_state(&frame->saved_combiner, ptr);

    ret_flag = kd_exe_on_call_hl_entry(&frame->regs,
                                       outgoing_rsp_ptr,
                                       frame->entry_ip,
                                       frame->outer_lock_addr);
    if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
        if (!frame->outer_unlock_seen &&
            kd_exec_frame_record_event(frame, KD_EXEC_EVENT_OUTER_UNLOCK,
                                       &frame->regs)) {
            KD_PR_ERR("spin JIT outer unlock event invalid lock=%px\n",
                      lock);
            ret_flag = KD_EXE_RUN_ERROR;
        } else if (kd_spin_jit_nested_cleanup(frame)) {
            KD_PR_ERR("spin JIT nested cleanup invalid lock=%px\n", lock);
            ret_flag = KD_EXE_RUN_ERROR;
        }
    }
    if (ret_flag != KD_EXE_RUN_TO_UNLOCK) {
        if (kd_spin_jit_abort_cleanup(frame)) {
            KD_PR_ERR("spin JIT abort cleanup failed lock=%px depth=%u\n",
                      lock, frame->depth);
            kd_spin_diag_invariant_failure();
        }
        abort_cleaned = true;
    }
    if (!kd_spin_combiner_state_matches(&frame->saved_combiner, ptr)) {
        KD_PR_ERR("nested combiner state restore mismatch lock=%px depth=%u\n",
                  lock, frame->depth);
        kd_spin_diag_invariant_failure();
        ret_flag = KD_EXE_RUN_ERROR;
    }
    if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
        if (kd_exec_frame_complete(frame)) {
            KD_PR_ERR("spin JIT frame completion invalid lock=%px\n", lock);
            ret_flag = KD_EXE_RUN_ERROR;
        }
    }
    if (ret_flag != KD_EXE_RUN_TO_UNLOCK) {
        if (!abort_cleaned && kd_spin_jit_abort_cleanup(frame)) {
            KD_PR_ERR("spin JIT late abort cleanup failed lock=%px depth=%u\n",
                      lock, frame->depth);
            kd_spin_diag_invariant_failure();
        }
        if (kd_exec_frame_abort(frame))
            KD_PR_ERR("spin JIT frame error transition failed lock=%px\n",
                      lock);
    }
    if (ret_flag != KD_EXE_RUN_TO_UNLOCK)
        frame->regs = retry_regs;
    curr_node->regs = frame->regs;
    curr_node->jit_retry = ret_flag != KD_EXE_RUN_TO_UNLOCK;
    if (curr_node->jit_retry)
        KD_PR_INFO("spin JIT retry regs: node=%px cpu=%d ip=%lx failed_ip=%lx\n",
                   curr_node, curr_node->cpuid, curr_node->regs.ip,
                   ret_flag == KD_EXE_RUN_TO_UNLOCK ? 0UL : frame->continuation_ip);
    curr_node->exec_frame = NULL;
    if (kd_exec_frame_pop(frame, &curr_node->regs)) {
        KD_PR_ERR("spin JIT frame pop mismatch lock=%px\n", lock);
        return KD_EXE_RUN_ERROR;
    }

    if (ret_flag == KD_EXE_RUN_TO_UNLOCK)
    {
        kd_spin_debug_jit_success(lock, kd_spin_lock_stack_depth(ptr));
        KD_PR_DEBUG("delegation ok lock=%px depth=%u\n",
                    lock, kd_spin_lock_stack_depth(ptr));
        // curr_node->regs.ip += 5; //! skip raw_spin_unlock function
    }
    else
    {
        KD_PR_DEBUG("error return exe run error\n");
        if (ret_flag == KD_EXE_RUN_ERROR)
            kd_spin_jit_disable(lock);
        // BUG_ON(true);
        return ret_flag;
        // ! import it's hard to deal, maybe use this delegation thread to deal exception
    }
    // local_irq_enable();

#ifdef DEBUG_KD_SPIN
    if ((ptr->ptr - (ptr->local_shadow_stack_ptr)) > SIZE_OF_SHADOW_STACK)
    {
        printk(KERN_ALERT "%d %px %px\n", smp_processor_id(), ptr->ptr,
               ptr->local_shadow_stack_ptr);
        BUG_ON(true);
    }
    BUG_ON(ptr->ptr - (ptr->local_shadow_stack_ptr) > SIZE_OF_SHADOW_STACK);
#endif

    if (lock->locked == _Q_UNLOCKED_OOO_VAL)
    {
        print_debug("Combiner got control back OOO unlock\n");

#ifdef KD_SPIN_STATS
        this_cpu_add(ooo_waiter_combined, ptr->counter_val);
        this_cpu_inc(ooo_combiner_count);
#endif

        /* JIT waiters carry their continuation in pt_regs.  The native
         * TCLock path copies a real RSP here, but the combiner's base node
         * deliberately has rsp == NULL while run_combiner() is active. */
        ptr->prev_cs_cpu = -1;
        ptr->curr_cs_cpu = -1;
        lock->locked = _Q_LOCKED_COMBINER_VAL;
    }

    // clear_locked_set_completed(curr_node);
    return 0;
}
#pragma GCC pop_options

#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static void
run_combiner(struct qspinlock *lock, struct kd_spin_node *curr_node)
{
#ifdef DEBUG_KD_SPIN
    BUG_ON(curr_node == NULL);
#endif
    struct kd_spin_node *next_node = curr_node->next;
    int counter = 0;

    if (next_node == NULL || check_irq_node(curr_node) ||
        check_irq_node(next_node)) //!  maybe the list is short , I can't delegation
    {
        set_locked(lock);
        /*
         * Make this node spin on the locked variable and then it will
         * become the combiner.
         */
        curr_node->locked = false;
        smp_mb();
        return;
    }

    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
    kd_spin_debug_combiner(lock, kd_spin_lock_stack_depth(ptr));

#ifndef WWJUMP
    while (curr_node)
    {
        counter++;

        next_node = get_next_node(curr_node);

        int exe_flag = execute_cs(lock, curr_node);

        if(exe_flag == KD_EXE_NO_RUN){
            print_debug("can't assembly\n");
            next_node = curr_node; 
            //! no exe any waiter
            break;
        }
        if(exe_flag == KD_EXE_RUN_ERROR){
            print_debug("run error\n");
            /*
             * Abort cleanup restored the waiter to its critical-section
             * entry.  Keep it uncompleted: it must first acquire ownership
             * of the outer lock through the normal queue path.  Once it is
             * the owner, __kd_spin_lock_longjmp() returns ret4 and resumes
             * the saved entry context.
             */
            next_node = curr_node;
            break;
        }

        clear_locked_set_completed(curr_node);

        if (next_node == NULL || next_node->next == NULL ||
            counter >= kd_combiner_batch_size)
            break;

        curr_node = next_node;
    }
#else
    ptr->counter_val = 0;

    print_debug("Combiner %d giving control to %d\n", smp_processor_id(),
                curr_node->cpuid);

    execute_cs(lock, curr_node);

    print_debug(
        "Combiner got the control back: %d counter: %d last_waiter: %d\n",
        smp_processor_id(), ptr->counter_val, ptr->curr_cs_cpu);

#ifdef KD_SPIN_STATS
    this_cpu_add(waiter_combined, ptr->counter_val);
    this_cpu_inc(combiner_count);
#endif

    if (ptr->prev_cs_cpu != -1)
    {
        clear_locked_set_completed(
            per_cpu_ptr(&kd_spin_nodes[0], ptr->prev_cs_cpu));
        ptr->prev_cs_cpu = -1;
    }

    next_node = ptr->next_node_ptr;
#endif

#ifdef NUMA_AWARE
    if (ptr->local_queue_head != NULL)
    {
        ptr->local_queue_tail->next = next_node;
        next_node = ptr->local_queue_head;
        ptr->local_queue_head = NULL;
        ptr->local_queue_tail = NULL;
    }
#endif

    print_debug("After combiner %d, next node: %d\n", smp_processor_id(),
                next_node->cpuid);

#ifdef DEBUG_KD_SPIN
    BUG_ON(next_node == NULL);
#endif

    set_locked(lock);

#ifdef WWJUMP
    ptr->curr_cs_cpu = -1;
#endif
    /*
     * Make this node spin on the locked variable and then it will become
     * the combiner.
     */
    next_node->locked = false;
}
#pragma GCC pop_options

#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
__kd_spin_lock_longjmp(struct qspinlock *lock, int tail,
                         register struct kd_spin_node *curr_node)
{
    register struct kd_spin_node *prev_node = NULL, *next_node = NULL;
    struct qspinlock *parent_lock;
    int old_tail, val, j;

    /*
     * TODO: Make sure these variables are stored on the combiner stack
     * so that they can be restored later.
     * These variables are needed when there is a waiter or a combiner
     * running within a combiner (For same or different lock).
     */
    uint32_t prev_cs_cpu;
    bool prev_locked_val;
    uint64_t prev_rsp;
    uint64_t prev_counter_val;
    struct kd_spin_node *prev_next_node_ptr = NULL;
#ifdef NUMA_AWARE
    struct kd_spin_node *prev_local_queue_head;
    struct kd_spin_node *prev_local_queue_tail;
#endif

    old_tail = xchg_tail(lock, tail);
    kd_spin_diag_waiter_enter(lock);

    if (old_tail & _Q_TAIL_MASK_HL)
    {
        prev_node = decode_tail(old_tail);

        prev_node->next = curr_node;

        int count = 0;

        smp_cond_load_relaxed_sched(&curr_node->locked, !(VAL));
        

        //! waiter is waiting here! spinlock
        /*while (READ_ONCE(curr_node->locked)) {
            cpu_relax();
            count++;
            if (count == INT_MAX)
                BUG_ON(true);
        }*/
        //! todo recover

        struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

        if (curr_node->completed)
        {
            print_debug("wakeup\n");
#ifdef ENABLE_IRQS_CHECK
            if (curr_node->irqs_disabled)
            {
                // local_irq_disable();
                ptr->irqs_disabled = curr_node->irqs_disabled;
            }
#endif
            for (j = 7; j >= 0; j--)
                if (ptr->lock_addr[j] != NULL)
                    break;

            this_cpu_ptr(&kd_spin_nodes[0])->count--;

            if (j >= 0)
            {
                parent_lock = ptr->lock_addr[j];
#ifdef DEBUG_KD_SPIN
                BUG_ON(parent_lock == lock);
#endif
                if (parent_lock->locked ==
                    _Q_UNLOCKED_OOO_VAL)
                {
                    print_debug("Waiter unlocked OOO\n");
                    kd_spin_diag_waiter_exit(lock);
                    kd_spin_set_resume_node(curr_node);
                    return 1;
                }
            }

            prefetchw(curr_node->rsp);
            prefetchw(curr_node->rsp + 64);
            prefetchw(curr_node->rsp + 128);
            prefetchw(curr_node->rsp + 192);
            prefetchw(curr_node->rsp + 256);
            prefetchw(curr_node->rsp + 320);
            LOCK_START_TIMING_PER_CPU(unlock_stack_switch);
            kd_spin_diag_waiter_exit(lock);
            kd_spin_set_resume_node(curr_node);
            return 3;
        }
        
    
    }

    /*
     * we're at the head of the waitqueue, wait for the owner & pending to
     * go away.
     *
     * *,x,y -> *,0,0
     *
     * this wait loop must use a load-acquire such that we match the
     * store-release that clears the locked bit and create lock
     * sequentiality; this is because the set_locked() function below
     * does not imply a full barrier.
     *
     */

    val = atomic_cond_read_acquire(&lock->val,
                                   !(VAL & _Q_LOCKED_PENDING_MASK));
                                   // ! wait the quene to release

    /*
     * claim the lock:
     *
     * n,0,0 -> 0,0,1 : lock, uncontended
     * *,*,0 -> *,*,1 : lock, contended
     *
     * If the queue head is the only one in the queue (lock value == tail)
     * and nobody is pending, clear the tail code and grab the lock.
     * Otherwise, we only need to grab the lock.
     */

    if (((val & _Q_TAIL_MASK_HL) == tail) &&
        atomic_try_cmpxchg_relaxed(&lock->val, &val, _Q_LOCKED_VAL_HL))
        goto release; /* No contention */

    /* Either somebody is queued behind us or _Q_PENDING_VAL_HL is set */
    check_and_set_combiner(lock);

    /*
     * contended path; wait for next if not observed yet, release.
     */
    smp_cond_load_relaxed_sched(&curr_node->next, (VAL));
    next_node = curr_node->next;
#ifdef DEBUG_KD_SPIN
    BUG_ON(next_node == NULL);
#endif
    /*while (!next_node) {
        next_node = curr_node->next;
        cpu_relax();
    }*/
    // ! combiner, wait for hang it

    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

    prev_cs_cpu = ptr->curr_cs_cpu;
    ptr->curr_cs_cpu = -1;

    ptr->irqs_disabled = false;

#ifdef DEBUG_KD_SPIN
    BUG_ON(ptr->prev_cs_cpu != -1);
#endif
    /*
     * curr_node at the head of the queue.
     * Release the node and run_combiner.
     */
    this_cpu_ptr(&kd_spin_nodes[0])->count--;
    prev_locked_val = lock->locked;
#ifdef DEBUG_KD_SPIN
    BUG_ON(prev_locked_val >= _Q_LOCKED_COMBINER_VAL);
#endif
    lock->locked = _Q_LOCKED_COMBINER_VAL;
    prev_rsp = curr_node->rsp;
    curr_node->rsp = NULL;

    prev_counter_val = ptr->counter_val;
    ptr->counter_val = 0;

    prev_next_node_ptr = ptr->next_node_ptr;
    ptr->next_node_ptr = NULL;

#ifdef NUMA_AWARE
    prev_local_queue_head = ptr->local_queue_head;
    prev_local_queue_tail = ptr->local_queue_tail;

    ptr->local_queue_head = NULL;
    ptr->local_queue_tail = NULL;
#endif

    j = 7;
    for (j = 7; j >= 0; j--)
        if (ptr->lock_addr[j] != NULL)
            break;
    j += 1;
#ifdef DEBUG_KD_SPIN
    BUG_ON(j >= 8 || j < 0);
#endif
    if (unlikely(j >= 8))
        goto release;
    ptr->lock_addr[j] = lock;
    kd_spin_diag_validate_lock_stack(ptr);

    run_combiner(lock, next_node);

#ifdef DEBUG_KD_SPIN
    BUG_ON(this_cpu_ptr(&local_shadow_stack)->lock_addr[j] != lock);
#endif

    ptr->lock_addr[j] = NULL;
    kd_spin_diag_validate_lock_stack(ptr);

    ptr->next_node_ptr = prev_next_node_ptr;
    ptr->counter_val = prev_counter_val;

#ifdef NUMA_AWARE
    ptr->local_queue_head = prev_local_queue_head;
    ptr->local_queue_tail = prev_local_queue_tail;
#endif

    curr_node->rsp = prev_rsp;

    if (lock->locked == _Q_UNLOCKED_OOO_VAL)
    {
        if (prev_cs_cpu != -1)
        {
            print_debug("Waking up %d\n", prev_cs_cpu);
            clear_locked_set_completed(
                per_cpu_ptr(&kd_spin_nodes[0], prev_cs_cpu));
        }
        ptr->curr_cs_cpu = -1;
    }
    else
    {
        ptr->curr_cs_cpu = prev_cs_cpu;
    }
    lock->locked = prev_locked_val;

    kd_spin_diag_waiter_exit(lock);
    kd_spin_set_resume_node(curr_node);
    return READ_ONCE(curr_node->jit_retry) ? 4 : 2;
release:
    /*
     * release the node
     */
    this_cpu_ptr(&kd_spin_nodes[0])->count--;
    kd_spin_diag_waiter_exit(lock);
    kd_spin_set_resume_node(curr_node);
    return READ_ONCE(curr_node->jit_retry) ? 4 : 0;
}
#pragma GCC pop_options

__attribute__((noipa)) noinline notrace static int
__kd_spin_lock_slowpath(struct qspinlock *lock)
{
    struct kd_spin_node *base, *curr_node;
    struct kd_spin_native_input *input;
    int tail, idx;

    LOCK_END_TIMING_PER_CPU(lock_stack_switch);

    base = this_cpu_ptr(&kd_spin_nodes[0]);
    kd_spin_diag_record(lock, KD_SPIN_DIAG_SLOWPATH,
                        kd_spin_lock_stack_depth(
                            this_cpu_ptr(&local_shadow_stack)));
    idx = base->count++;
    if (unlikely(idx >= MAX_NODES)) {
        base->count--;
        while (!kd_spin_trylock(lock))
            cpu_relax();
        return 0;
    }
    curr_node = base + idx;
    input = this_cpu_ptr(&kd_spin_native_inputs);
    tail = encode_tail(smp_processor_id(), idx);

    /*
     * Initialize curr_node
     */
    curr_node->locked = true;
    curr_node->completed = false;
    curr_node->next = NULL;
    curr_node->tail = tail;
    curr_node->socket_id = numa_node_id();
    curr_node->cpuid = smp_processor_id();
    curr_node->rsp = READ_ONCE(input->rsp);
    curr_node->regs.sp = READ_ONCE(input->regs_sp);
    curr_node->irqs_disabled = false;
    curr_node->lock = lock;
    curr_node->task_struct_ptr = current;
    curr_node->gsbase = kd_read_kernel_gsbase();
    curr_node->exec_frame = NULL;
    curr_node->jit_waiter = false;
    curr_node->jit_retry = false;
    curr_node->jit_context = NULL;

    return __kd_spin_lock_longjmp(lock, tail, curr_node);
}

/*
 * Public API
 */

void kd_spinlock_init(void)
{
    int i, j;

    atomic64_set(&kd_spin_diag_overflow, 0);
    atomic64_set(&kd_spin_diag_invariant_failures, 0);
    for (i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
        atomic_long_set(&kd_spin_diag_slots[i].addr, 0);
        for (j = 0; j < KD_SPIN_DIAG_EVENT_COUNT; j++)
            atomic64_set(&kd_spin_diag_slots[i].event[j], 0);
        atomic_set(&kd_spin_diag_slots[i].max_depth, 0);
        atomic_set(&kd_spin_diag_slots[i].waiter_count, 0);
        atomic_set(&kd_spin_diag_slots[i].jit_disabled, 0);
    }

    for_each_possible_cpu(i)
    {
        void *stack_ptr = vzalloc(SIZE_OF_SHADOW_STACK);
        struct shadow_stack *ptr = per_cpu_ptr(&local_shadow_stack, i);
        struct kd_spin_jit_context *contexts;

        contexts = vzalloc(array_size(MAX_NODES, sizeof(*contexts)));
        *per_cpu_ptr(&kd_spin_jit_contexts, i) = contexts;

#ifdef DEBUG_KD_SPIN
        BUG_ON(stack_ptr == NULL);
#endif

        ptr->ptr = stack_ptr + SIZE_OF_SHADOW_STACK;
        for (j = 0; j < 8; j++)
            ptr->lock_addr[j] = 0;
        ptr->local_shadow_stack_ptr =
            stack_ptr + SIZE_OF_SHADOW_STACK - 8;
        ptr->curr_cs_cpu = -1;
        ptr->prev_cs_cpu = -1;
        ptr->counter_val = 0;
        ptr->next_node_ptr = NULL;
#ifdef NUMA_AWARE
        ptr->local_queue_head = NULL;
        ptr->local_queue_tail = NULL;
#endif

        ptr->irqs_disabled = false;
        memset(per_cpu_ptr(&kd_spin_native_inputs, i), 0,
               sizeof(struct kd_spin_native_input));
        *per_cpu_ptr(&kd_spin_resume_nodes, i) = NULL;

        for (j = 0; j < MAX_NODES; j++) {
            struct kd_spin_node *node =
                per_cpu_ptr(&kd_spin_nodes[j], i);

            node->jit_waiter = false;
            node->jit_retry = false;
            node->jit_context = NULL;
            node->gsbase = 0;
        }

#ifdef LOCK_MEASURE_TIME
        *per_cpu_ptr(&combiner_loop, i) = UINT64_MAX;
#endif
    }
}

void kd_spinlock_exit(void)
{
    int i;

    KD_PR_INFO("kd_spin diag overflow=%lld\n",
               (long long)atomic64_read(&kd_spin_diag_overflow));
    KD_PR_INFO("kd_spin diag invariant_failures=%lld\n",
               (long long)atomic64_read(&kd_spin_diag_invariant_failures));
    for (i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
        struct kd_spin_diag_slot *slot = &kd_spin_diag_slots[i];
        unsigned long addr = (unsigned long)atomic_long_read(&slot->addr);

        if (!addr)
            continue;
        KD_PR_INFO("kd_spin lock stats: lock=%lx depth=%d slowpath=%lld "
                   "combiner=%lld jit_success=%lld jit_not_ready=%lld "
                   "nested_lock=%lld "
                   "nested_unlock=%lld nested_remote=%lld "
                   "native_fallback=%lld ooo_unlock=%lld "
                   "jit_disabled=%d waiters=%d\n",
                   addr, atomic_read(&slot->max_depth),
                   (long long)atomic64_read(
                       &slot->event[KD_SPIN_DIAG_SLOWPATH]),
                   (long long)atomic64_read(
                       &slot->event[KD_SPIN_DIAG_COMBINER]),
                   (long long)atomic64_read(
                       &slot->event[KD_SPIN_DIAG_JIT_SUCCESS]),
                   (long long)atomic64_read(
                       &slot->event[KD_SPIN_DIAG_JIT_NOT_READY]),
                   (long long)atomic64_read(
                       &slot->event[KD_SPIN_DIAG_NESTED_LOCK]),
                   (long long)atomic64_read(
                       &slot->event[KD_SPIN_DIAG_NESTED_UNLOCK]),
                   (long long)atomic64_read(
                       &slot->event[KD_SPIN_DIAG_NESTED_REMOTE]),
                   (long long)atomic64_read(
                       &slot->event[KD_SPIN_DIAG_NATIVE_FALLBACK]),
                   (long long)atomic64_read(
                       &slot->event[KD_SPIN_DIAG_OOO_UNLOCK]),
                   atomic_read(&slot->jit_disabled),
                   atomic_read(&slot->waiter_count));
    }

    for_each_possible_cpu(i)
    {
        vfree(*per_cpu_ptr(&kd_spin_jit_contexts, i));
        *per_cpu_ptr(&kd_spin_jit_contexts, i) = NULL;
        vfree(per_cpu_ptr(&local_shadow_stack, i)->ptr -
              SIZE_OF_SHADOW_STACK);
    }
}

static int kd_spin_prepare_jit_node(struct kd_spin_node *node,
                                    struct kd_spin_jit_context *context,
                                    struct qspinlock *lock,
                                    const struct pt_regs *regs,
                                    const struct kd_exec_frame *parent)
{
    unsigned int i, depth;

    if (!node || !context || !lock || !regs || !parent ||
        !kd_exec_frame_validate(parent))
        return -EINVAL;

    depth = kd_exec_frame_lock_depth(parent);
    if (depth >= KD_EXEC_MAX_LOCK_DEPTH)
        return -E2BIG;

    node->regs = *regs;
    node->gsbase = parent->gsbase;
    node->task_struct_ptr = parent->logical_task;
    node->jit_waiter = true;
    node->jit_context = context;
    context->lock_depth = depth + 1;
    for (i = 0; i < depth; i++) {
        context->lock_addr[i] = parent->jit_lock_addr[i];
        context->lock_kind[i] = parent->jit_lock_kind[i];
        context->lock_node[i] = parent->jit_lock_node[i];
        context->lock_released[i] = parent->jit_lock_released[i];
    }
    context->lock_addr[depth] = (unsigned long)lock;
    context->lock_kind[depth] = KD_EXEC_LOCK_QUEUE_OWNER;
    context->lock_node[depth] = node;
    context->lock_released[depth] = false;
    return 0;
}

static int kd_spin_advance_jit_node(struct kd_spin_node *node,
                                    struct pt_regs *regs)
{
    unsigned long return_ip;

    if (!node || !regs || !node->regs.sp)
        return -EINVAL;
    return_ip = READ_ONCE(*(unsigned long *)node->regs.sp);
    if (!return_ip)
        return -EINVAL;
    node->regs.sp += sizeof(unsigned long);
    node->regs.ip = return_ip;
    *regs = node->regs;
    return 0;
}

int kd_spin_nested_lock(struct qspinlock *lock, struct pt_regs *regs,
                        const struct kd_exec_frame *parent)
{
    struct kd_spin_node *base, *node;
    struct kd_spin_jit_context *contexts;
    u32 tail;
    int idx, ret;

    if (!lock || !regs || !parent)
        return -EINVAL;

    if (atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL_HL) == 0)
        return KD_SPIN_NESTED_ACQUIRED;

    base = this_cpu_ptr(&kd_spin_nodes[0]);
    contexts = *this_cpu_ptr(&kd_spin_jit_contexts);
    if (!contexts)
        return -ENOMEM;
    idx = base->count++;
    if (unlikely(idx < 0 || idx >= MAX_NODES)) {
        base->count--;
        return -E2BIG;
    }
    node = base + idx;
    tail = encode_tail(smp_processor_id(), idx);

    node->locked = true;
    node->completed = false;
    node->next = NULL;
    node->tail = tail;
    node->socket_id = numa_node_id();
    node->cpuid = smp_processor_id();
    node->rsp = regs->sp;
    node->lock = lock;
    node->task_struct_ptr = NULL;
    node->gsbase = 0;
    node->irqs_disabled = false;
    node->exec_frame = NULL;
    node->jit_retry = false;
    ret = kd_spin_prepare_jit_node(node, &contexts[idx], lock, regs,
                                   parent);
    if (ret) {
        base->count--;
        return ret;
    }

    kd_spin_diag_record(lock, KD_SPIN_DIAG_SLOWPATH,
                        kd_spin_lock_stack_depth(
                            this_cpu_ptr(&local_shadow_stack)));
    ret = __kd_spin_lock_longjmp(lock, tail, node);
    if (ret == 0)
        return KD_SPIN_NESTED_ACQUIRED;
    if (ret == 2)
        return KD_SPIN_NESTED_ACQUIRED_QUEUE;
    if (ret != 1 && ret != 3)
        return -EIO;
    if (kd_spin_advance_jit_node(node, regs))
        return -EINVAL;
    return ret == 1 ? KD_SPIN_NESTED_PARENT_OOO :
        KD_SPIN_NESTED_DELEGATED;
}

int kd_spin_nested_unlock(struct qspinlock *lock)
{
    bool ooo;

    if (!lock)
        return -EINVAL;

    kd_spin_unlock(lock);
    ooo = READ_ONCE(lock->locked) == _Q_UNLOCKED_OOO_VAL;
    if (ooo)
        return KD_SPIN_NESTED_UNLOCK_OOO;

    return kd_spin_nested_shadow_pop(lock);
}

void kd_spin_lock_init(struct qspinlock *lock)
{
    atomic_set(&lock->val, 0);
}

__attribute__((noipa)) noinline notrace static uint64_t
get_shadow_stack_ptr(void)
{
    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

    return &(ptr->local_shadow_stack_ptr);
}

__attribute__((noipa)) noinline notrace static struct kd_spin_node *
get_kd_spin_resume_node(void)
{
    struct kd_spin_node *node =
        READ_ONCE(*this_cpu_ptr(&kd_spin_resume_nodes));

    return node ? node : this_cpu_ptr(&kd_spin_nodes[0]);
}

__attribute__((noipa)) noinline notrace static struct kd_spin_native_input *
get_kd_spin_native_input(void)
{
    return this_cpu_ptr(&kd_spin_native_inputs);
}

/*
 * When the following function is called, the compiler in caller frame does
 * this sequence:
 *
 * push caller-saved-regs			(rdi, rsi, rdx, rcx, ...)
 * ...<prepare arguments>...
 * .- push eip+1				(eip + 1 == pop insn)
 * callq |
 * `- jmp kd_spin_lock
 * pop caller-saved-regs
 *
 * This means that the following function must in no way modify the the rsp
 * before it is written to the task_frame, otherwise the top of the stack
 * (rsp) would no longer point to the return address. To do this, emit a
 * call in assembly and pass the top of the stack as an argument so that
 * we can use the stack while preserving the semantics of the combiner.
 *
 * NOTE: One advantage of offloading the caller-saved register spill to the
 * compiler is that it only saves the caller-saved registers in use in the
 * caller frame. If we were to inline this whole logic in assembly, we wouldn't
 * know the registers in use and would have to save all possible caller-saved
 * registers.
 */
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void jump_to_saved_regs(struct pt_regs *regs)
{
    asm volatile("movq 0x00(%%rdi), %%r15\n"
                 "movq 0x08(%%rdi), %%r14\n"
                 "movq 0x10(%%rdi), %%r13\n"
                 "movq 0x18(%%rdi), %%r12\n"
                 "movq 0x20(%%rdi), %%rbp\n"
                 "movq 0x28(%%rdi), %%rbx\n"
                 "movq 0x30(%%rdi), %%r11\n"
                 "movq 0x38(%%rdi), %%r10\n"
                 "movq 0x40(%%rdi), %%r9\n"
                 "movq 0x48(%%rdi), %%r8\n"
                 "movq 0x50(%%rdi), %%rax\n"
                 "movq 0x58(%%rdi), %%rcx\n"
                 "movq 0x60(%%rdi), %%rdx\n"
                 "movq 0x68(%%rdi), %%rsi\n"
                 "movq 0x98(%%rdi), %%rsp\n"
                //  "pushq 0x80(%%rdi)\n" // rip/
                 "movq 0x70(%%rdi), %%rdi\n"
                //  "retq\n"
                 "retq\n"  // !skip spin_unlock
                 :
                 :
                 : "memory");
    // no reach here and can't return function : add code
    __builtin_unreachable();
}

#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void jump_to_saved_regs_in_cs(struct pt_regs *regs)
{
    asm volatile("movq 0x00(%%rdi), %%r15\n"
                 "movq 0x08(%%rdi), %%r14\n"
                 "movq 0x10(%%rdi), %%r13\n"
                 "movq 0x18(%%rdi), %%r12\n"
                 "movq 0x20(%%rdi), %%rbp\n"
                 "movq 0x28(%%rdi), %%rbx\n"
                 "movq 0x30(%%rdi), %%r11\n"
                 "movq 0x38(%%rdi), %%r10\n"
                 "movq 0x40(%%rdi), %%r9\n"
                 "movq 0x48(%%rdi), %%r8\n"
                 "movq 0x50(%%rdi), %%rax\n"
                 "movq 0x58(%%rdi), %%rcx\n"
                 "movq 0x60(%%rdi), %%rdx\n"
                 "movq 0x68(%%rdi), %%rsi\n"
                 "movq 0x98(%%rdi), %%rsp\n"
                 "pushq 0x80(%%rdi)\n" // rip
                 "movq 0x70(%%rdi), %%rdi\n"
                 "retq\n"
                 :
                 :
                 : "memory");
    // no reach here and can't return function : add code
    __builtin_unreachable();
}

#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void
kd_spin_lock_slowpath(struct qspinlock *lock, unsigned long rsp_value)
{
    register int ret_val;
    register struct kd_spin_node *cur_node;
    /*
     * We must save the callee-saved registers now, since we will resume
     * execution at the return address currently at top of stack. If we
     * defer saving to when context switch happens later, the C function
     * may have saved callee-saved registers and will restore them before
     * returning.
     *
     * Due to unstructured control flow, do the saving now.
     *
     * NOTE: When we touch the stack inside this function, so a 16-byte
     * stack's alignment will change to 8-byte alignment when callq pushes
     * our return address, but Linux only assumes 8-byte stack alignment,
     * so it isn't a problem for us.
     */
#ifdef KD_SPIN_DEBUG
#ifdef ENABLE_IRQS_CHECK
    BUG_ON(irqs_disabled());
#endif
#endif
    // local_irq_disable();
    // asm volatile("pushq %%rbp\n"
    //              "pushq %%rbx\n"
    //              "pushq %%r12\n"
    //              "pushq %%r13\n"
    //              "pushq %%r14\n"
    //              "pushq %%r15\n"
    //              :
    //              :
    //              : "memory");
    asm volatile("callq %P0\n"
                 "movq %%rsp, %c1(%%rax)\n"
                 :
                 : "i"(get_kd_spin_native_input),
                   "i"(offsetof(struct kd_spin_native_input, rsp))
                 : "memory");
    WRITE_ONCE(this_cpu_ptr(&kd_spin_native_inputs)->regs_sp, rsp_value);

    // wait are use the shadow stack ptr
    asm volatile("callq %P0\n"
                 "movq (%%rax), %%rsp\n"
                 :
                 : "i"(get_shadow_stack_ptr)
                 : "memory");
    // local_irq_enable();
    // print_debug("pid %d into __kd_spin_lock_slowpath", current->tgid);

    ret_val = __kd_spin_lock_slowpath(lock);



    // local_irq_disable();
    if (ret_val == 1)
    {
        asm volatile("callq %P0\n"
                "movq %c1(%%rax), %%rsp\n"
                :
                : "i"(get_kd_spin_resume_node), "i"(offsetof(struct kd_spin_node, rsp))
                : "memory");
        /*
         * TCLock ret1 is a completed waiter whose parent was unlocked
         * out-of-order.  Its critical section has already run, so resume
         * through the saved node exactly like the regular ret3 handoff.
         */
        cur_node = get_kd_spin_resume_node();
        jump_to_saved_regs(&cur_node->regs);
        __builtin_unreachable();
    }
    else if (ret_val == 2)
    {
        asm volatile("callq %P0\n"
                "movq %c1(%%rax), %%rsp\n"
                :
                : "i"(get_kd_spin_resume_node), "i"(offsetof(struct kd_spin_node, rsp))
                : "memory");
        // ! combiner
        return;
    }
    else if(ret_val == 0){ 
        asm volatile("callq %P0\n"
                "movq %c1(%%rax), %%rsp\n"
                :
                : "i"(get_kd_spin_resume_node), "i"(offsetof(struct kd_spin_node, rsp))
                : "memory");
        // asm volatile("callq %P0\n"
        //              "movq (%%rax), %%rsp\n"
        //              :
        //              : "i"(get_shadow_stack_ptr)
        //              : "memory");
        return;
    }
    else if(ret_val == 3)
    {
        asm volatile("callq %P0\n"
                "movq %c1(%%rax), %%rsp\n"
                :
                : "i"(get_kd_spin_resume_node), "i"(offsetof(struct kd_spin_node, rsp))
                : "memory");
        // ! waiter
        // asm volatile("callq %P0\n"
        //              "movq (%%rax), %%rsp\n"
        //              :
        //              : "i"(get_shadow_stack_ptr)
        //              : "memory");
        // asm volatile("popq %%r15\n"
        //              "popq %%r14\n"
        //              "popq %%r13\n"
        //              "popq %%r12\n"
        //              "popq %%rbx\n"
        //              "popq %%rbp\n"
        //              "retq\n"
        //              :
        //              :
        //  : "memory");'
        print_debug("pid %d ret_val: %d", current->pid, ret_val);

        cur_node = get_kd_spin_resume_node();
        if (cur_node->jit_retry)
            KD_PR_INFO("spin JIT retry resume: node=%px cpu=%d ip=%lx\n",
                       cur_node, cur_node->cpuid, cur_node->regs.ip);
        if (cur_node->jit_retry)
            jump_to_saved_regs_in_cs(&cur_node->regs);
        jump_to_saved_regs(&cur_node->regs);
        __builtin_unreachable();
    }
    else if(ret_val == 4)
    {
        asm volatile("callq %P0\n"
                "movq %c1(%%rax), %%rsp\n"
                :
                : "i"(get_kd_spin_resume_node), "i"(offsetof(struct kd_spin_node, rsp))
                : "memory");
        // ! waiter resumes at the saved critical-section entry
        cur_node = get_kd_spin_resume_node();
        if (cur_node->jit_retry)
            KD_PR_INFO("spin JIT retry resume: node=%px cpu=%d ip=%lx\n",
                       cur_node, cur_node->cpuid, cur_node->regs.ip);
        jump_to_saved_regs_in_cs(&cur_node->regs);
        __builtin_unreachable();
    }
    // local_irq_enable();
}
#pragma GCC pop_options

__attribute__((noipa)) noinline notrace void
kd_spin_lock(struct qspinlock *lock, unsigned long rsp_value)
{
    u32 val, cnt;
    struct kd_spin_node *curr_node = NULL;

    /*
     * Fastpath
     */

    val = atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL_HL);
    if (val == 0)
        return;

    /*
     * Mid-path
     *
     * Wait for in-progress pending->locked hand-overs with a bounded
     * number of spins so that we guarantee forward progress.
     *
     * 0,1,0 -> 0,0,1
     */
    if (val == _Q_PENDING_VAL_HL)
    {
        cnt = _Q_PENDING_LOOPS_HL;
        val = atomic_cond_read_relaxed(
            &lock->val, (VAL != _Q_PENDING_VAL_HL) || !cnt--);
    }

    /*
     * If we observe any contention; queue.
     */
    if (val & ~_Q_LOCKED_MASK_HL ||
        (val & _Q_LOCKED_MASK_HL) == _Q_LOCKED_IRQ_VAL)
        goto queue;

    /*
     * trylock || pending
     *
     * 0,0,* -> 0,1,* -> 0,0,1 pending, trylock
     */
    val = kd_spin_fetch_set_pending_acquire(lock);  //setup pending

    /*
     * If we observe contention, there is a concurrent locker.
     *
     * Undo and queue; our setting of PENDING might have made the
     * n,0,0 -> 0,0,0 transition fail and it will now be waiting
     * on @next to become !NULL.
     */
    if (unlikely(val & ~_Q_LOCKED_MASK_HL))
    {
        /* Undo PENDING if we set it. */
        if (!(val & _Q_PENDING_MASK_HL))
            clear_pending(lock);

        goto queue;
    }

    /*
     * We're pending, wait for the owner to go away.
     *
     * 0,1,1 -> 0,1,0
     *
     * this wait loop must be a load-acquire such that we match the
     * store-release that clears the locked bit and create lock
     * sequentiality; this is because not all
     * clear_pending_set_locked() implementations imply full
     * barriers.
     */
    if (val & _Q_LOCKED_MASK_HL)
        atomic_cond_read_acquire(&lock->val, !(VAL & _Q_LOCKED_MASK_HL));

    /*
     * take ownership and clear the pending bit.
     *
     * 0,1,0 -> 0,0,1
     */
    clear_pending_set_locked(lock);
    return;

    /*
     * End of pending bit optimistic spinning and beginning of MCS
     * queuing.
     */
queue:

    curr_node = this_cpu_ptr(&kd_spin_nodes[0]);  // ! other info
#ifdef DEBUG_KD_SPIN
    BUG_ON(curr_node == NULL);
#endif
#ifdef ENABLE_IRQS_CHECK
    if (curr_node->count > 0 || !in_task() || irqs_disabled() ||
        current->migration_disabled)
    {
        /*print_debug("Nested lock: waiting for lock\n");
        while (true) {
            atomic_cond_read_acquire(&lock->val, !(VAL));

            if (atomic_cmpxchg_acquire(&lock->val, 0,
                           _Q_LOCKED_IRQ_VAL) == 0)
                break;
        }
        print_debug("Nested lock: got the lock\n");
        return;
    } else if (!in_task() ||irqs_disabled() || current->migration_disabled) {*/
        struct kd_spin_node *prev_node, *next_node;
        u32 tail, idx;

        idx = curr_node->count++;
        /*
         * 4 nodes are allocated based on the assumption that there will
         * not be nested NMIs taking spinlocks. That may not be true in
         * some architectures even though the chance of needing more than
         * 4 nodes will still be extremely unlikely. When that happens,
         * we fall back to spinning on the lock directly without using
         * any MCS node. This is not the most elegant solution, but is
         * simple enough.
         */
        if (unlikely(idx >= MAX_NODES))
        {
            while (!kd_spin_trylock(lock))
                cpu_relax();
            goto irq_release;
        }

        curr_node += idx;
        tail = encode_tail(smp_processor_id(), idx);

        barrier();

        curr_node->locked = true;
        curr_node->completed = false;
        curr_node->next = NULL;
        curr_node->tail = tail;
        curr_node->socket_id = IRQ_NUMA_NODE;
        curr_node->cpuid = smp_processor_id();
        curr_node->irqs_disabled = false;
        curr_node->lock = lock;
        curr_node->task_struct_ptr = current;
        curr_node->gsbase = kd_read_kernel_gsbase();

        uint64_t prev_rsp = curr_node->rsp;
        curr_node->rsp = 0xdeadbeef;

        smp_wmb();

        u32 old_tail = xchg_tail(lock, tail);

        if (old_tail & _Q_TAIL_MASK_HL)
        {
            prev_node = decode_tail(old_tail);
            WRITE_ONCE(prev_node->next, curr_node);

            print_debug("IRQ going to waiting for lock\n");
            smp_cond_load_relaxed_sched(&curr_node->locked, !(VAL));
        }

        curr_node->rsp = prev_rsp;

        u32 val, new_val;

        print_debug("IRQ spinning on the locked field\n");

        val = atomic_cond_read_acquire(&lock->val,
                                       !(VAL & _Q_LOCKED_PENDING_MASK));

        if (((val & _Q_TAIL_MASK_HL) == tail) &&
            atomic_try_cmpxchg_relaxed(&lock->val, &val,
                                       _Q_LOCKED_IRQ_VAL))
        {
            print_debug("IRQ only one in the queue unlocked\n");
            goto irq_release;
        }

        // set_locked(lock);

        while (true)
        {
            val = atomic_cond_read_relaxed(
                &lock->val, !(VAL & _Q_LOCKED_PENDING_MASK));

#ifdef DEBUG_KD_SPIN
            BUG_ON(lock->locked != 0);
#endif

            new_val = val >> _Q_LOCKED_BITS_HL;
            new_val <<= _Q_LOCKED_BITS_HL;
            new_val |= _Q_LOCKED_IRQ_VAL;

            if (atomic_cmpxchg_acquire(&lock->val, val, new_val) ==
                val)
                break;
        }

        print_debug("IRQ got the lock\n");

        smp_cond_load_relaxed_sched(&curr_node->next, (VAL));
        next_node = curr_node->next;

#ifdef DEBUG_KD_SPIN
        BUG_ON(next_node == NULL);
#endif

        WRITE_ONCE(next_node->locked, false);

        print_debug("IRQ passing lock next node: %d\n",
                    next_node->cpuid);

    irq_release:
        curr_node = this_cpu_ptr(&kd_spin_nodes[0]);
        curr_node->count--;
        return;
    }
    else
    {
#endif

#ifdef LOCK_MEASURE_TIME
        *this_cpu_ptr(&lock_stack_switch) = UINT64_MAX;
        *this_cpu_ptr(&unlock_stack_switch) = UINT64_MAX;
#endif
        LOCK_START_TIMING_PER_CPU(lock_stack_switch);

        kd_spin_lock_slowpath(lock, rsp_value);

#ifdef WWJUMP
        struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

        uint32_t curr_cpuid = ptr->curr_cs_cpu;
        if (curr_cpuid != -1)
        {
            struct kd_spin_node *curr_node =
                per_cpu_ptr(&kd_spin_nodes[0], curr_cpuid);
            if (curr_node->lock == lock)
            {
#ifdef DEBUG_KD_SPIN
                BUG_ON(lock->locked != _Q_LOCKED_COMBINER_VAL);
#endif
                struct kd_spin_node *next_node =
                    get_next_node(curr_node);
                ptr->next_node_ptr = next_node;
            }

            uint32_t prev_cpuid = ptr->prev_cs_cpu;
            if (prev_cpuid != -1)
            {
                struct kd_spin_node *prev_node =
                    per_cpu_ptr(&kd_spin_nodes[0], prev_cpuid);

#ifdef DEBUG_KD_SPIN
                BUG_ON(prev_node->lock != lock);
#endif
                print_debug("Waking up prev waiter: %d\n",
                            prev_cpuid);
                clear_locked_set_completed(prev_node);
                ptr->prev_cs_cpu = -1;

                //	LOCK_END_TIMING_PER_CPU(combiner_loop);
            }
        }
#endif

#ifdef ENABLE_IRQS_CHECK
    }
#endif
}
EXPORT_SYMBOL_GPL(kd_spin_lock);

struct task_struct *kd_spin_get_current(spinlock_t *lock)
{
    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

    int j, my_idx;

    j = 0;
    my_idx = -1;

    for (j = 0; j < 8; j++)
    {
        if (ptr->lock_addr[j] == lock)
        {
#ifdef DEBUG_KD_SPIN
            BUG_ON(ptr->curr_cs_cpu < 0);
#endif
            return per_cpu_ptr(&kd_spin_nodes[0], ptr->curr_cs_cpu)
                ->task_struct_ptr;
        }
    }

    return current;
}

void kd_spin_set_current_state(spinlock_t *lock, unsigned int state)
{
    WRITE_ONCE(kd_spin_get_current(lock)->__state, state);
    smp_mb();
}

/*
 * No IPA is even more relevant here, because even if assembly is removed,
 * compiler shouldn't assume which caller-saved registers are in use inside
 * the function. When we jump from the spin loop to the return address after
 * the unlock function, we have caller-saved registers that are completely
 * inconsistent, because we only restored the callee-saved registers.
 */
__attribute__((noipa)) noinline notrace void
kd_spin_unlock(struct qspinlock *lock)
{
    struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
    int from_cpuid = ptr->curr_cs_cpu;
    void *incoming_rsp_ptr, *outgoing_rsp_ptr;

    int j, max_idx, my_idx;

    uint64_t temp_lock_addr;

    j = 0;
    max_idx = -1;
    my_idx = -1;

    if (lock->locked == _Q_LOCKED_VAL_HL ||
        lock->locked == _Q_LOCKED_IRQ_VAL)
    {
        lock->locked = false;
        return;
    }

    for (j = 0; j < 8; j++)
    {
        temp_lock_addr = ptr->lock_addr[j];
        if (temp_lock_addr != NULL)
            max_idx = j;
        if (temp_lock_addr == lock)
            my_idx = j;
        if (temp_lock_addr == NULL)
            break;
    }
    kd_spin_diag_validate_lock_stack(ptr);
    kd_spin_diag_validate_outer_unlock(ptr, lock, my_idx, max_idx);

    if (my_idx == -1)
    {
        if (lock->locked == _Q_LOCKED_VAL_HL ||
            lock->locked == _Q_LOCKED_IRQ_VAL)
            lock->locked = false;
        else if (lock->locked == _Q_LOCKED_COMBINER_VAL)
        {
#ifdef KD_SPIN_STATS
            this_cpu_inc(ooo_unlocks);
#endif
            kd_spin_debug_ooo_unlock(lock, kd_spin_lock_stack_depth(ptr));
            lock->locked = _Q_UNLOCKED_OOO_VAL;
            print_debug("OOO unlock\n");
        }
        else
            BUG_ON(true);
        return;
    }

    LOCK_END_TIMING_PER_CPU_DISABLE(combiner_loop);

    LOCK_START_TIMING_PER_CPU_DISABLE(combiner_loop);

#ifdef DEBUG_KD_SPIN
    if (lock->locked != _Q_LOCKED_COMBINER_VAL)
        BUG_ON(true);

    BUG_ON(from_cpuid == -1);

    if (max_idx < 0)
    {
        BUG_ON(true);
    }

#endif
    if (my_idx < max_idx)
    {
#ifdef KD_SPIN_STATS
        this_cpu_inc(ooo_unlocks);
#endif

        kd_spin_debug_ooo_unlock(lock, kd_spin_lock_stack_depth(ptr));
        lock->locked = _Q_UNLOCKED_OOO_VAL;
        return;
    }

    struct kd_spin_node *curr_node = per_cpu_ptr(&kd_spin_nodes[0], from_cpuid);

#ifdef WWJUMP
    struct kd_spin_node *next_node = ptr->next_node_ptr;

    uint64_t counter = ptr->counter_val;

    if (next_node == NULL || next_node->next == NULL ||
        check_irq_node(next_node) || check_irq_node(next_node->next) ||
        counter >= kd_combiner_batch_size || need_resched())
    {
        incoming_rsp_ptr = &(ptr->local_shadow_stack_ptr);
        ptr->curr_cs_cpu = -1;
        ptr->prev_cs_cpu = curr_node->cpuid;
    }
    else
    {
        ptr->curr_cs_cpu = next_node->cpuid;
        ptr->prev_cs_cpu = curr_node->cpuid;
        incoming_rsp_ptr = &(next_node->rsp);
        ptr->counter_val = counter + 1;
        print_debug("Jumping to the next waiter: %d\n",
                    next_node->cpuid);
    }
#else
    incoming_rsp_ptr = &(ptr->local_shadow_stack_ptr);
#endif
    /*
     * Komb node still active here, because cpu (from_cpuid) still spinning.
     */
    outgoing_rsp_ptr = &(curr_node->rsp);

#ifdef DEBUG_KD_SPIN
    BUG_ON(incoming_rsp_ptr == NULL);
    BUG_ON(outgoing_rsp_ptr == NULL);
    BUG_ON(incoming_rsp_ptr == 0xdeadbeef);
    BUG_ON(outgoing_rsp_ptr == 0xdeadbeef);
#endif

#ifdef ENABLE_IRQS_CHECK
    curr_node->irqs_disabled = irqs_disabled();
#endif
    // local_irq_disable();
    // kd_context_switch(incoming_rsp_ptr, outgoing_rsp_ptr);
    // ! hl mod
    ptr = this_cpu_ptr(&local_shadow_stack);
    // local_irq_enable();
    if (ptr->irqs_disabled)
    {
        ptr->irqs_disabled = false;
        local_irq_disable();
    }
    LOCK_END_TIMING_PER_CPU(unlock_stack_switch);
    return;
}

__always_inline int kd_spin_trylock(struct qspinlock *lock)
{
    u32 val;

    // Qspinlock Fastpath

    val = atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL_HL);
    if (val == 0)
        return true;

    return false;
}

// void kd_spin_lock_nested(struct qspinlock *lock, int level)
// {
//     kd_spin_lock(lock);
// }
// EXPORT_SYMBOL_GPL(kd_spin_lock_nested);

void kd_spin_assert_locked(struct qspinlock *lock)
{
    BUG_ON(!kd_spin_is_locked(lock));
}

__always_inline int kd_spin_is_locked(struct qspinlock *lock)
{
    return atomic_read(&lock->val);
}
EXPORT_SYMBOL(kd_spin_is_locked);

__always_inline int kd_spin_is_contended(struct qspinlock *lock)
{
    return atomic_read(&lock->val) & ~_Q_LOCKED_MASK_HL;
}

__always_inline int kd_spin_value_unlocked(struct qspinlock lock)
{
    return !atomic_read(&lock.val);
}
