// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi
//
// Ported to kdlock: TCLocks komb.c → kd_spinlock.c
//
// kd_spinlock implements transparent delegation for kernel spinlocks.
// The protocol uses a per-CPU MCS-style queue with a combiner/waiter model:
// the lock holder (combiner) executes critical sections on behalf of queued
// waiters by running JIT-translated code through kd_exe_on_call_hl_entry().
//
// Key differences from TCLocks komb.c:
//   - Calls kd_exe_on_call_hl_entry() inside execute_cs() for JIT delegation
//   - Uses kd_spin_node (renamed from komb_node) with embedded pt_regs
//   - Delegation via sandbox JIT, not raw stack-switch

/* Scheduling nodes carry packets, but kd_spin_entry owns origin tickets and
 * kd_spin_gate owns native L. Keep these lifetimes separate when reading the
 * nested queue paths: a remote executor may carry the same logical waiter.
 * Physical shadow-stack switches still support combiners; JIT replaces the
 * critical-section body handoff, not every stack switch in this backend. */
#include "kd_spinlock.h"
#include "utils.h"
#include "exe.h"
#include "kd_exec.h"
#include "kd_segment.h"
#include "kd_spin_entry.h"
#include <linux/sched.h>
#include <linux/topology.h>
#include <linux/vmalloc.h>
#include <linux/kernel.h>

#define SIZE_OF_SHADOW_STACK 8192L
#define IRQ_NUMA_NODE 255
#define KD_SPIN_DIAG_SLOTS 32
#define KD_SPIN_NUM_PREFETCH_LINES 6

static const unsigned int kd_combiner_batch_size = 1024;

static __always_inline int kd_spin_trylock(struct qspinlock *lock);

/* L is the public identity; only these private words contain kdlock tails. */
static struct qspinlock *kd_spin_word(struct qspinlock *lock)
{
	struct kd_spin_gate *gate = kd_spin_gate_find((raw_spinlock_t *)lock);

	BUG_ON(!gate);
	return &gate->word;
}

static bool kd_spin_is_ooo(struct qspinlock *lock)
{
	struct kd_spin_gate *gate = kd_spin_gate_find((raw_spinlock_t *)lock);

	/* Native ancestors have no scheduling word and cannot carry OOO markers. */
	return gate && READ_ONCE(gate->word.locked) == 7;
}

static void kd_spin_claim_origin(struct qspinlock *lock)
{
	struct kd_spin_ref ref = { 0 };
	int ret;

	BUG_ON(!kd_spin_entry_find((raw_spinlock_t *)lock, &ref));
	ret = kd_spin_entry_claim(&ref);
	if (unlikely(ret)) {
		KD_PR_ERR(
			"spin origin claim failed lock=%px cpu=%d task=%d ret=%d\n",
			lock, raw_smp_processor_id(), current->pid, ret);
		BUG();
	}
}

static void kd_spin_release_origin(struct qspinlock *lock)
{
	struct kd_spin_ref ref = { 0 };
	struct qspinlock *word = kd_spin_word(lock);

	BUG_ON(!kd_spin_entry_find((raw_spinlock_t *)lock, &ref));
	BUG_ON(kd_spin_entry_release_origin(&ref));
	smp_store_release(&word->locked, 0);
	/* No per-CPU accesses after this may schedule. */
	BUG_ON(kd_spin_entry_end(&ref));
}

#ifdef KDLOCK_SELFTEST
static int kd_spin_shadow_selftest(void);
static int kd_spin_selftest_frame_begin(const struct kd_exec_frame *frame);
static void kd_spin_selftest_frame_end(int event,
				       const struct kd_exec_frame *frame,
				       int ret);
static void kd_spin_selftest_frames_report(void);
static void kd_spin_selftest_stack_init(void *base);
static bool kd_spin_selftest_refuse(struct kd_exec_frame *frame,
				    const struct kd_spin_node *node, int *ret);
static void kd_spin_selftest_refusal_cancel(const struct kd_exec_frame *frame);
static void kd_spin_selftest_refusal_return(const struct kd_exec_frame *parent,
					    const struct kd_spin_node *node,
					    int ret);
static void kd_spin_selftest_refusal_end(const struct kd_exec_frame *frame,
					 int ret);
static void kd_spin_selftest_refusal_report(void);
static noinline void kd_spin_selftest_link(const struct kd_spin_node *node,
					   const struct kd_spin_node *previous,
					   int previous_task, int previous_cpu);
#ifdef NUMA_AWARE
static noinline void kd_spin_selftest_defer(const struct kd_spin_node *request,
					    const struct kd_spin_node *node);
static noinline void kd_spin_selftest_splice(struct qspinlock *lock,
					     const struct kd_spin_node *next,
					     bool outer);
static noinline void
kd_spin_selftest_restore(struct qspinlock *lock,
			 const struct kd_spin_node *request,
			 const struct kd_spin_node *discarded_tail, int result);
static noinline void kd_spin_selftest_queue_context(struct qspinlock *lock,
						    bool entering);
static void kd_spin_selftest_deferred_report(void);
#endif
#endif

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

#define smp_cond_load_relaxed_sched(ptr, cond_expr) \
	({                                          \
		typeof(ptr) __PTR = (ptr);          \
		__unqual_scalar_typeof(*ptr) VAL;   \
		for (;;) {                          \
			VAL = READ_ONCE(*__PTR);    \
			if (cond_expr)              \
				break;              \
			cpu_relax();                \
		}                                   \
		(typeof(*ptr))VAL;                  \
	})

#ifndef smp_cond_load_acquire_sched
#define smp_cond_load_acquire_sched(ptr, cond_expr)                 \
	({                                                          \
		__unqual_scalar_typeof(*ptr) _val;                  \
		_val = smp_cond_load_relaxed_sched(ptr, cond_expr); \
		smp_acquire__after_ctrl_dep();                      \
		(typeof(*ptr))_val;                                 \
	})
#endif

#define atomic_cond_read_acquire_sched(v, c) \
	smp_cond_load_acquire_sched(&(v)->counter, (c))

struct shadow_stack {
	/*
	 * Locks acquired by the current CPU. Tracking them separately from the
	 * execution stack supports sequences such as acquire A, acquire B,
	 * release A, release B.
	 */
	uint64_t lock_addr[8];

	/* Base of the private execution stack. */
	void *ptr;
	/*
	 * Used by the combiner to identify for which CPU is the critical section
	 * currently executing.
	 */
	uint32_t curr_cs_cpu;
	uint32_t prev_cs_cpu;
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
};

#ifdef KD_SPIN_STATS
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_combiner_count);
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_unlocks);
#endif

/*
 * Used by all threads to add itself to the queue on the slowpath.
 */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_spin_node,
				     kd_spin_nodes[MAX_NODES]);

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/spin_node_trace.c"
#else
#define kd_spin_selftest_node_event(event) \
	do {                               \
	} while (0)
#endif

struct kd_spin_native_input {
	unsigned long rsp;
	unsigned long regs_sp;
};

static DEFINE_PER_CPU(struct kd_spin_native_input, kd_spin_native_inputs);
static DEFINE_PER_CPU(struct kd_spin_node *, kd_spin_resume_nodes);

struct kd_spin_jit_context {
	struct kd_exec_frame *requester;
	unsigned int lock_depth;
	unsigned long lock_addr[KD_EXEC_MAX_LOCK_DEPTH];
	enum kd_exec_lock_kind lock_kind[KD_EXEC_MAX_LOCK_DEPTH];
	void *lock_node[KD_EXEC_MAX_LOCK_DEPTH];
	bool lock_released[KD_EXEC_MAX_LOCK_DEPTH];
};

static DEFINE_PER_CPU(struct kd_spin_jit_context *, kd_spin_jit_contexts);

#ifdef KDLOCK_SELFTEST
static bool kd_spin_selftest_virtual_begin(
	struct qspinlock *lock, const struct kd_spin_ref *request,
	const struct pt_regs *regs, const struct kd_exec_frame *parent,
	struct kd_spin_jit_context **contexts, int initial_preempt);
static void kd_spin_selftest_virtual_end(const struct kd_spin_ref *request,
					 const struct pt_regs *regs,
					 const struct kd_exec_frame *parent,
					 int result);
#endif

/*
 * 8KB shadow stack used by all the threads. For waiter threads, switch to
 * shadow stack, because of IRQs. For combiner thread, switch to shadow stack
 * to handle nesting
 */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct shadow_stack, local_shadow_stack);

#define _Q_LOCKED_PENDING_MASK (_Q_LOCKED_MASK_HL | _Q_PENDING_MASK_HL)
#define _Q_LOCKED_COMBINER_VAL 3
#define _Q_UNLOCKED_OOO_VAL 7 /* Lock released out of order. */
#define _Q_LOCKED_IRQ_VAL 15 /* Lock stolen by an IRQ context. */

static void kd_spin_diag_validate_lock_stack(const struct shadow_stack *ptr);

static inline unsigned int
kd_spin_lock_stack_depth(const struct shadow_stack *ptr)
{
	unsigned int depth = 0;

	while (depth < ARRAY_SIZE(ptr->lock_addr) &&
	       READ_ONCE(ptr->lock_addr[depth]) != 0)
		depth++;

	return depth;
}

bool kd_spin_nested_shadow_has_space(void)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	return kd_spin_lock_stack_depth(ptr) < ARRAY_SIZE(ptr->lock_addr);
}

/* Register a nested lock ownership record for this CPU's combiner stack.
 * The stack is used to validate outer-unlock ordering and out-of-order unlock
 * checks during delegated nested execution.
 */
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

/* Remove one lock from the nested shadow stack, allowing arbitrary hole compaction.
 * This keeps lock addresses topologically ordered in lock-depth tracking.
 */
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

/* Pop requires exact top-of-stack match; used when this lock is the current
 * nesting boundary being released.
 */
static int kd_spin_nested_shadow_pop(struct qspinlock *lock)
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

static void kd_spin_capture_combiner_state(struct kd_combiner_state *saved,
					   const struct shadow_stack *ptr)
{
	unsigned int i;

	for (i = 0; i < KD_EXEC_MAX_LOCK_DEPTH; i++)
		saved->lock_addr[i] = READ_ONCE(ptr->lock_addr[i]);
	saved->lock_depth = kd_spin_lock_stack_depth(ptr);
	saved->curr_cs_cpu = ptr->curr_cs_cpu;
	saved->prev_cs_cpu = ptr->prev_cs_cpu;
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

static __always_inline void kd_spin_diag_invariant_failure(void)
{
	atomic64_inc(&kd_spin_diag_invariant_failures);
	WARN_ON_ONCE(1);
}

static void kd_spin_diag_validate_lock_stack(const struct shadow_stack *ptr)
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

/* Verify a candidate unlock matches the latest expected nesting index.
 * Detects accidental reordering before mutating spin/qspin states.
 */
static void kd_spin_diag_validate_outer_unlock(const struct shadow_stack *ptr,
					       struct qspinlock *lock,
					       int my_idx, int max_idx)
{
	struct qspinlock *word = kd_spin_word(lock);
	if (my_idx < 0)
		return;

	if (my_idx > max_idx ||
	    ptr->lock_addr[my_idx] != (uint64_t)(unsigned long)lock)
		kd_spin_diag_invariant_failure();

	if (my_idx == max_idx &&
	    READ_ONCE(word->locked) != _Q_LOCKED_COMBINER_VAL)
		kd_spin_diag_invariant_failure();
}

static struct kd_spin_diag_slot *kd_spin_diag_find(unsigned long addr)
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
			observed =
				atomic_long_cmpxchg(&slot->addr, 0, (long)addr);
			if (observed == 0 || (unsigned long)observed == addr)
				return slot;
		}
	}

	atomic64_inc(&kd_spin_diag_overflow);
	return NULL;
}

static void kd_spin_diag_record_addr(unsigned long addr,
				     enum kd_spin_diag_event event,
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
		int previous =
			atomic_cmpxchg(&slot->max_depth, old_depth, depth);

		if (previous == old_depth)
			break;
		old_depth = previous;
	}
}

static void kd_spin_diag_record(struct qspinlock *lock,
				enum kd_spin_diag_event event,
				unsigned int depth)
{
	kd_spin_diag_record_addr((unsigned long)lock, event, depth);
}

static bool kd_spin_jit_is_disabled(struct qspinlock *lock)
{
	struct kd_spin_diag_slot *slot = kd_spin_diag_find((unsigned long)lock);

	return slot && atomic_read_acquire(&slot->jit_disabled);
}

static void kd_spin_jit_disable(struct qspinlock *lock)
{
	struct kd_spin_diag_slot *slot = kd_spin_diag_find((unsigned long)lock);

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

/* Test observers must not interpret the Linux lock word as our private queue. */
unsigned int kd_spin_debug_word(raw_spinlock_t *lock)
{
	struct kd_spin_gate *gate = kd_spin_gate_find(lock);

	return gate ? atomic_read(&gate->word.val) : 0;
}
EXPORT_SYMBOL_GPL(kd_spin_debug_word);

/* Only a physically held proxy gate has an owner; native Linux users do not. */
unsigned long kd_spin_debug_owner(raw_spinlock_t *lock)
{
	struct kd_spin_gate *gate = kd_spin_gate_find(lock);

	return gate && READ_ONCE(gate->held) ?
		       (unsigned long)READ_ONCE(gate->owner) :
		       0;
}
EXPORT_SYMBOL_GPL(kd_spin_debug_owner);

static void kd_spin_diag_record_nested(raw_spinlock_t *lock,
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

static void kd_spin_debug_combiner(struct qspinlock *lock, unsigned int depth)
{
	kd_spin_diag_record(lock, KD_SPIN_DIAG_COMBINER, depth);
}

static void kd_spin_debug_jit_success(struct qspinlock *lock,
				      unsigned int depth)
{
	kd_spin_diag_record(lock, KD_SPIN_DIAG_JIT_SUCCESS, depth);
}

static void kd_spin_debug_jit_not_ready(struct qspinlock *lock,
					unsigned int depth)
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

static void kd_spin_debug_ooo_unlock(struct qspinlock *lock, unsigned int depth)
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

static __always_inline void kd_spin_set_resume_node(struct kd_spin_node *node)
{
	WRITE_ONCE(*this_cpu_ptr(&kd_spin_resume_nodes), node);
}

static inline bool check_irq_node(struct kd_spin_node *node)
{
	return (node->socket_id == IRQ_NUMA_NODE || node->rsp == 0xdeadbeef);
}

static __always_inline void
clear_locked_set_completed(struct kd_spin_node *lock)
{
	/* On x86 this word sets completed and clears locked together. Publish
	 * the final register packet before the waiter can consume/reuse it. */
	smp_store_release(&lock->locked_completed, 1);
}

static __always_inline void clear_pending_set_locked(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
#ifdef DEBUG_KD_SPIN
	BUG_ON(word->locked != 0);
#endif
	WRITE_ONCE(word->locked_pending, _Q_LOCKED_VAL_HL);
}

static __always_inline u32 xchg_tail(struct qspinlock *lock, u32 tail)
{
	struct qspinlock *word = kd_spin_word(lock);
	return ((u32)xchg(&word->tail, tail >> _Q_TAIL_OFFSET_HL))
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
	struct qspinlock *word = kd_spin_word(lock);
	atomic_andnot(_Q_PENDING_VAL_HL, &word->val);
}

/**
 * set_locked - Set the lock bit and own the lock
 * @lock: Pointer to queued spinlock structure
 *
 * *,*,0 -> *,0,1
 */
static __always_inline void set_locked(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
	WRITE_ONCE(word->locked, _Q_LOCKED_VAL_HL);
}

static __always_inline void check_and_set_combiner(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
	u32 val, new_val;

#ifdef DEBUG_KD_SPIN
	BUG_ON(word->locked == _Q_LOCKED_VAL_HL);
#endif

	if (word->locked > 0) {
		while (true) {
			val = atomic_cond_read_relaxed(
				&word->val, !(VAL & _Q_LOCKED_PENDING_MASK));

#ifdef DEBUG_KD_SPIN
			BUG_ON(word->locked != 0);
#endif

			new_val = val >> _Q_LOCKED_BITS_HL;
			new_val <<= _Q_LOCKED_BITS_HL;
			new_val |= _Q_LOCKED_COMBINER_VAL;

			if (atomic_cmpxchg_acquire(&word->val, val, new_val) ==
			    val)
				return;
		}
	}
	WRITE_ONCE(word->locked, _Q_LOCKED_COMBINER_VAL);
}

/**
 * kd_spin_fetch_set_pending_acquire - fetch lock value and set pending
 * @lock : Pointer to queued spinlock structure
 * Return: The previous lock value
 *
 * *,*,* -> *,1,*
 */
static __always_inline u32
kd_spin_fetch_set_pending_acquire(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
	return atomic_fetch_or_acquire(_Q_PENDING_VAL_HL, &word->val);
}

#ifdef NUMA_AWARE
__always_inline static void add_to_local_queue(struct kd_spin_node *node)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	if (ptr->local_queue_head == NULL) {
		ptr->local_queue_head = node;
		ptr->local_queue_tail = node;
	} else {
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

	while (true) {
		if (next_node == NULL || next_node->next == NULL)
			goto next_node_null;
		else if (check_irq_node(next_node) ||
			 check_irq_node(next_node->next))
			goto next_node_null;

		if (next_node->socket_id == numa_node_id()) {
#ifdef PREFETCHING
			void *rsp_ptr = (per_cpu_ptr(&kd_spin_nodes[0],
						     next_node->cpuid)
						 ->rsp);
			prefetchw(rsp_ptr);
			int i;
			for (i = 1; i < KD_SPIN_NUM_PREFETCH_LINES; i++)
				prefetchw(rsp_ptr + (64 * i));

			prefetch(next_node->next);
#endif
			return next_node;
		}

		add_to_local_queue(next_node);
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_defer(my_node, next_node);
#endif
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

struct kd_spin_batch {
	struct kd_exec_outer_unlock outer;
	struct kd_spin_node *next;
};

/* A's executor keeps its ticket pin and local frame stack, not ownership of
 * A. No published successor can be inspected again by this detached batch. */
static int kd_spin_release_outer(struct kd_exec_frame *frame,
				 struct kd_exec_outer_unlock *hook)
{
	struct kd_spin_batch *batch =
		container_of(hook, struct kd_spin_batch, outer);
	struct qspinlock *lock = (struct qspinlock *)frame->outer_lock_addr;
	struct qspinlock *word = kd_spin_word(lock);
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	struct kd_spin_node *next = batch->next;
	struct kd_spin_ref ref = { 0 };
	unsigned int i, remaining = 0;
	int ret;

	if (frame->mutex_backend || !next || !next->task_struct_ptr ||
	    frame->jit_lock_kind[frame->outer_lock_index] !=
		    KD_EXEC_LOCK_QUEUE_OWNER ||
	    READ_ONCE(word->locked) != _Q_LOCKED_COMBINER_VAL ||
	    !kd_spin_entry_find((raw_spinlock_t *)lock, &ref))
		return -EINVAL;
#ifdef NUMA_AWARE
	if (ptr->local_queue_head) {
		if (!ptr->local_queue_tail)
			return -EINVAL;
		ptr->local_queue_tail->next = next;
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_splice(lock, next, true);
#endif
		next = ptr->local_queue_head;
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
		frame->saved_combiner.local_queue_head = NULL;
		frame->saved_combiner.local_queue_tail = NULL;
	}
#endif
	for (i = frame->outer_lock_index; i < frame->jit_lock_depth; i++)
		remaining += !frame->jit_lock_released[i];
	/* Log before L opens: a native successor may run immediately afterward. */
	pr_info("kd_spin outer release: task=%d owner=%d owner_task=%lx cpu=%u outer=%lx next_task=%d next_cpu=%d remaining=%u remote=%u\n",
		frame->logical_task->pid, current->pid, (unsigned long)current,
		raw_smp_processor_id(), frame->outer_lock_addr,
		next->task_struct_ptr->pid, next->cpuid, remaining,
		kd_exec_frame_remote_pending(frame));
	ret = kd_spin_entry_release_origin(&ref);
	if (ret)
		return ret;
	kd_spin_debug_ooo_unlock(lock, kd_spin_lock_stack_depth(ptr));
	smp_store_release(&word->locked, 0);
	smp_store_release(&next->locked, 0);
	return 0;
}

/* Reclaim the original waiter's outer lock on return from a native/remote
 * delegation run. The holder must reacquire origin scheduling only, never
 * open a new queue fast path through this packet.
 */
static void kd_spin_reclaim_outer(struct qspinlock *lock)
{
	struct kd_spin_ref ref = { 0 };

	BUG_ON(!kd_spin_entry_find((raw_spinlock_t *)lock, &ref));
	/* Like node-capacity fallback, wait for all of S, including pending/tail.
	 * Reentering the stack-switch slowpath would overwrite our live C stack. */
	while (!kd_spin_trylock(lock))
		cpu_relax();
	BUG_ON(kd_spin_entry_reclaim(&ref));
}

#pragma GCC push_options
#pragma GCC optimize("O3")
/*
 * Execute one waiter critical section in JIT mode.
 * For native waiters run until outer unlock or delegated native path and publish
 * the corresponding transition so combiner state and successor continuation stay
 * deterministic.
 */
__attribute__((noipa)) noinline notrace static int
execute_cs(struct qspinlock *lock, struct kd_spin_node *curr_node,
	   struct kd_spin_batch *batch)
{
	struct qspinlock *word = kd_spin_word(lock);
	void *incoming_rsp_ptr, *outgoing_rsp_ptr;
	unsigned int frame_lock_depth;
	struct kd_spin_jit_context *jit_context = curr_node->jit_context;
	unsigned long entry_ip;
	u64 queue_end;
	bool abort_cleaned = false;
#ifdef KDLOCK_SELFTEST
	int frame_event;
#endif

	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	ptr->curr_cs_cpu = curr_node->cpuid;

	/* A plain waiter cannot describe locks/context pinned before this request.
	 * Keep its private-queue position, but let it execute on its own stack. */
	if (!curr_node->jit_waiter && curr_node->pinned_context) {
		pr_warn_ratelimited(
			"[KD_JIT][WARN] reason=PINNED_NATIVE_WAITER task=%d cpu=%d lock=%px\n",
			curr_node->task_struct_ptr->pid, curr_node->cpuid,
			lock);
		return KD_EXE_NO_RUN;
	}
	if (kd_spin_jit_is_disabled(lock)) {
		kd_spin_diag_record(lock, KD_SPIN_DIAG_NATIVE_FALLBACK,
				    kd_spin_lock_stack_depth(ptr));
		return KD_EXE_NO_RUN;
	}

#ifdef DEBUG_KD_SPIN
	BUG_ON(curr_node->cpuid == smp_processor_id());
	if ((ptr->ptr - (ptr->local_shadow_stack_ptr)) > SIZE_OF_SHADOW_STACK) {
		printk(KERN_ALERT "%d %px %px\n", smp_processor_id(), ptr->ptr,
		       ptr->local_shadow_stack_ptr);
		BUG_ON(true);
	}
#endif

	incoming_rsp_ptr = (void *)curr_node->regs.sp;
	print_debug("incoming_rsp_ptr: %px\n", incoming_rsp_ptr);
	outgoing_rsp_ptr = &(ptr->local_shadow_stack_ptr);

	/* Native waiters expose the saved callee-register frame via their RSP. */
#ifdef DEBUG_KD_SPIN
#ifdef ENABLE_IRQS_CHECK
	BUG_ON(irqs_disabled());
#endif

	if (!curr_node->jit_waiter && !curr_node->native_regs_decoded)
		BUG_ON(*(uint64_t *)incoming_rsp_ptr == NULL);
	BUG_ON(*(uint64_t *)outgoing_rsp_ptr == NULL);
#endif
	/* Admission can fail before JIT entry. Later combiners must reuse the
	 * decoded packet, not consume another callee-save frame from its RSP. */
	if (!curr_node->jit_waiter && !curr_node->native_regs_decoded) {
		curr_node->regs.r15 =
			get_rsp_from_regs(r15, incoming_rsp_ptr, 5);
		curr_node->regs.r14 =
			get_rsp_from_regs(r14, incoming_rsp_ptr, 4);
		curr_node->regs.r13 =
			get_rsp_from_regs(r13, incoming_rsp_ptr, 3);
		curr_node->regs.r12 =
			get_rsp_from_regs(r12, incoming_rsp_ptr, 2);
		curr_node->regs.bx =
			get_rsp_from_regs(rbx, incoming_rsp_ptr, 1);
		curr_node->regs.bp =
			get_rsp_from_regs(rbp, incoming_rsp_ptr, 6);
		curr_node->regs.ip =
			get_rsp_from_regs(rip, incoming_rsp_ptr, 7);
		curr_node->regs.sp = ((unsigned long)incoming_rsp_ptr) + 64;
		curr_node->native_regs_decoded = true;
	}
	if (curr_node->jit_waiter && (!jit_context || !jit_context->requester))
		return KD_EXE_RUN_ERROR;
	/* B is a continuation in A's admitted code. An independent B translation
	 * starts at lexical depth one and can stop at an inherited A unlock. */
	entry_ip = curr_node->jit_waiter ? jit_context->requester->entry_ip :
					   curr_node->regs.ip;
	if (!kd_exe_is_ready(0, entry_ip)) {
		kd_spin_debug_jit_not_ready(lock,
					    kd_spin_lock_stack_depth(ptr));
		kd_exe_add(0, entry_ip, KD_EXE_LOCK_SPIN);
		return KD_EXE_NO_RUN;
	}
	print_debug(
		"r15 %lx r14 %lx r13 %lx r12 %lx bx %lx bp %lx ip %lx sp %lx\n",
		curr_node->regs.r15, curr_node->regs.r14, curr_node->regs.r13,
		curr_node->regs.r12, curr_node->regs.bx, curr_node->regs.bp,
		curr_node->regs.ip, curr_node->regs.sp);
	frame_lock_depth = curr_node->jit_waiter ?
				   jit_context->lock_depth :
				   kd_spin_lock_stack_depth(ptr);
	struct kd_exec_frame *frame = kd_exec_frame_push(
		&curr_node->regs, entry_ip, (unsigned long)lock, curr_node,
		outgoing_rsp_ptr, frame_lock_depth, curr_node->gsbase,
		curr_node->task_struct_ptr);
	int ret_flag;

	if (!frame) {
		KD_PR_ERR("spin JIT frame stack overflow lock=%px\n", lock);
		return KD_EXE_RUN_ERROR;
	}
	curr_node->exec_frame = frame;
	frame->spin_origin = curr_node->spin_origin;
	if ((curr_node->jit_waiter &&
	     kd_exec_frame_set_lock_entries(
		     frame, jit_context->lock_addr, jit_context->lock_kind,
		     jit_context->lock_node, jit_context->lock_released,
		     jit_context->lock_depth)) ||
	    (!curr_node->jit_waiter &&
	     kd_exec_frame_set_lock_stack(frame,
					  (const unsigned long *)ptr->lock_addr,
					  kd_spin_lock_stack_depth(ptr)))) {
		KD_PR_ERR("spin JIT frame lock stack invalid lock=%px\n", lock);
		kd_exec_frame_abort(frame);
		curr_node->regs = frame->regs;
		curr_node->exec_frame = NULL;
		if (kd_exec_frame_pop(frame, &curr_node->regs))
			KD_PR_ERR("spin JIT frame abort pop failed lock=%px\n",
				  lock);
		return KD_EXE_RUN_ERROR;
	}
	kd_spin_capture_combiner_state(&frame->saved_combiner, ptr);
	frame->outer_unlock_hook = &batch->outer;
	if (curr_node->jit_waiter) {
		frame->resume_target = jit_context->requester;
		BUG_ON(!frame->resume_target ||
		       frame->resume_target->logical_task !=
			       frame->logical_task ||
		       smp_load_acquire(&frame->resume_target->remote_result) !=
			       KD_EXEC_REMOTE_WAITING);
		pr_info("kd_remote start: task=%d cpu=%u entry=%lx ip=%lx outer=%lx parent_outer=%lx owner_task=%lx\n",
			frame->logical_pid, raw_smp_processor_id(),
			frame->entry_ip, frame->regs.ip, frame->outer_lock_addr,
			frame->resume_target->outer_lock_addr,
			(unsigned long)current);
	}
#ifdef KDLOCK_SELFTEST
	frame_event = kd_spin_selftest_frame_begin(frame);
#endif
	queue_end = kd_exe_queue_timing_start();
#ifdef KDLOCK_SELFTEST
	/* Exercise only an unexecuted child; never interrupt a live JIT body. */
	if (!kd_spin_selftest_refuse(frame, curr_node, &ret_flag))
#endif
		ret_flag = kd_exe_on_call_hl_entry(
			&frame->regs, frame->entry_ip, frame->outer_lock_addr);
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_frame_end(frame_event, frame, ret_flag);
	kd_spin_selftest_refusal_end(frame, ret_flag);
#endif
	/* A pre-body refusal is still waiting. Once a body ran, use its saved
	 * dispatch boundary and consume metadata before native/completion wake. */
	if (frame->executed)
		kd_exe_queue_timing_end(false, &curr_node->queued_at_ns, queue_end);
	if (ret_flag == KD_EXE_RUN_NATIVE) {
		/* Remote publication can release an ancestor before this node is
		 * woken. Start before both publications, not only local locked=0. */
		u64 handoff_start = kd_exe_native_timing_start();

		BUG_ON(kd_exec_native_begin(frame, false));
		BUG_ON(kd_exec_remote_native(frame));
		curr_node->regs = frame->regs;
		curr_node->exec_frame = NULL;
		WRITE_ONCE(curr_node->native_resume, true);
		smp_store_release(&curr_node->locked, 0);
		/* The waiter may reuse its queue slot after this publication. */
		BUG_ON(kd_exec_native_wait(frame));
		kd_exe_native_handoff_timing_end(false, handoff_start);
		BUG_ON(kd_spin_jit_nested_cleanup(frame));
		BUG_ON(!kd_spin_combiner_state_matches(&frame->saved_combiner,
						       ptr));
		BUG_ON(kd_exec_frame_complete(frame));
		BUG_ON(kd_exec_frame_pop(frame, NULL));
		return KD_EXE_NATIVE_DONE;
	}
	if (ret_flag != KD_EXE_RUN_TO_UNLOCK && frame->executed) {
		KD_PR_ERR(
			"spin JIT non-continuable exit: entry=%lx ip=%lx ret=%d\n",
			frame->entry_ip, frame->regs.ip, ret_flag);
		BUG();
	}
	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		if (!frame->outer_unlock_seen &&
		    kd_exec_frame_record_event(
			    frame, KD_EXEC_EVENT_OUTER_UNLOCK, &frame->regs)) {
			KD_PR_ERR(
				"spin JIT outer unlock event invalid lock=%px\n",
				lock);
			ret_flag = KD_EXE_RUN_ERROR;
		} else if (kd_spin_jit_nested_cleanup(frame)) {
			KD_PR_ERR("spin JIT nested cleanup invalid lock=%px\n",
				  lock);
			ret_flag = KD_EXE_RUN_ERROR;
		}
	}
	if (ret_flag != KD_EXE_RUN_TO_UNLOCK) {
		BUG_ON(frame->executed);
		if (kd_spin_jit_abort_cleanup(frame)) {
			KD_PR_ERR(
				"spin JIT abort cleanup failed lock=%px depth=%u\n",
				lock, frame->depth);
			kd_spin_diag_invariant_failure();
		}
		abort_cleaned = true;
	}
	if (!kd_spin_combiner_state_matches(&frame->saved_combiner, ptr)) {
		KD_PR_ERR(
			"nested combiner state restore mismatch lock=%px depth=%u\n",
			lock, frame->depth);
		kd_spin_diag_invariant_failure();
		ret_flag = KD_EXE_RUN_ERROR;
	}
	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		if (kd_exec_frame_complete(frame)) {
			KD_PR_ERR(
				"spin JIT frame completion invalid lock=%px\n",
				lock);
			ret_flag = KD_EXE_RUN_ERROR;
		}
	}
	if (ret_flag != KD_EXE_RUN_TO_UNLOCK) {
		BUG_ON(frame->executed);
		if (!abort_cleaned && kd_spin_jit_abort_cleanup(frame)) {
			KD_PR_ERR(
				"spin JIT late abort cleanup failed lock=%px depth=%u\n",
				lock, frame->depth);
			kd_spin_diag_invariant_failure();
		}
		if (kd_exec_frame_abort(frame))
			KD_PR_ERR(
				"spin JIT frame error transition failed lock=%px\n",
				lock);
	}
	if (ret_flag != KD_EXE_RUN_TO_UNLOCK) {
		/* Before JIT starts the queued input is unchanged and cannot be
		 * reused. Keep that packet off the recursively nested C stack. */
		frame->regs = curr_node->regs;
	}
	curr_node->regs = frame->regs;
	/* Only a native waiter needs the saved-entry return trampoline. A
	 * virtual waiter acquires B and continues its existing parent frame. */
	curr_node->jit_retry = !curr_node->jit_waiter &&
			       ret_flag != KD_EXE_RUN_TO_UNLOCK;
	if (curr_node->jit_retry)
		KD_PR_INFO(
			"spin JIT retry regs: node=%px cpu=%d ip=%lx failed_ip=%lx\n",
			curr_node, curr_node->cpuid, curr_node->regs.ip,
			ret_flag == KD_EXE_RUN_TO_UNLOCK ?
				0UL :
				frame->continuation_ip);
	curr_node->exec_frame = NULL;
	if (ret_flag == KD_EXE_RUN_TO_UNLOCK)
		BUG_ON(kd_exec_remote_complete(frame));
	else
		kd_exec_remote_cancel(frame);
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_refusal_cancel(frame);
#endif
	if (kd_exec_frame_pop(frame, &curr_node->regs)) {
		KD_PR_ERR("spin JIT frame pop mismatch lock=%px\n", lock);
		BUG();
	}

	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		kd_spin_debug_jit_success(lock, kd_spin_lock_stack_depth(ptr));
		KD_PR_DEBUG("delegation ok lock=%px depth=%u\n", lock,
			    kd_spin_lock_stack_depth(ptr));
	} else {
		KD_PR_DEBUG("error return exe run error\n");
		if (ret_flag == KD_EXE_RUN_ERROR)
			kd_spin_jit_disable(lock);
		return ret_flag;
	}

#ifdef DEBUG_KD_SPIN
	if ((ptr->ptr - (ptr->local_shadow_stack_ptr)) > SIZE_OF_SHADOW_STACK) {
		printk(KERN_ALERT "%d %px %px\n", smp_processor_id(), ptr->ptr,
		       ptr->local_shadow_stack_ptr);
		BUG_ON(true);
	}
	BUG_ON(ptr->ptr - (ptr->local_shadow_stack_ptr) > SIZE_OF_SHADOW_STACK);
#endif

	if (!batch->outer.released && word->locked == _Q_UNLOCKED_OOO_VAL) {
		print_debug("Combiner got control back OOO unlock\n");

#ifdef KD_SPIN_STATS
		this_cpu_inc(ooo_combiner_count);
#endif

		/* JIT waiters carry their continuation in pt_regs.  The native
		 * TCLock path copies a real RSP here, but the combiner's base node
		 * deliberately has rsp == NULL while run_combiner() is active. */
		ptr->prev_cs_cpu = -1;
		ptr->curr_cs_cpu = -1;
		word->locked = _Q_LOCKED_COMBINER_VAL;
	}
	return 0;
}
#pragma GCC pop_options

#pragma GCC push_options
#pragma GCC optimize("O3")
/*
 * Combiner loop over the currently-formed queue segment.
 * Stops at batch boundary, native handoff, OOO release, or JIT failure and
 * leaves the lock in a state expected by the successor waiter.
 */
__attribute__((noipa)) noinline notrace static void
run_combiner(struct qspinlock *lock, struct kd_spin_node *curr_node)
{
#ifdef DEBUG_KD_SPIN
	BUG_ON(curr_node == NULL);
#endif
	struct kd_spin_node *next_node = curr_node->next;
	struct kd_spin_batch batch = {
		.outer.release = kd_spin_release_outer,
	};
	int counter = 0;

	if (next_node == NULL || check_irq_node(curr_node) ||
	    check_irq_node(next_node)) {
		set_locked(lock);
		/*
		 * Make this node spin on the locked variable and then it will
		 * become the combiner.
		 */
		smp_store_release(&curr_node->locked, false);
		smp_mb();
		return;
	}

	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	kd_spin_debug_combiner(lock, kd_spin_lock_stack_depth(ptr));

	while (curr_node) {
#ifdef NUMA_AWARE
		struct kd_spin_node *saved_tail = ptr->local_queue_tail;
#endif
		counter++;

		next_node = get_next_node(curr_node);
		batch.next = next_node;
		batch.outer.released = false;

		int exe_flag = execute_cs(lock, curr_node, &batch);

#ifdef NUMA_AWARE
		if (exe_flag == KD_EXE_NO_RUN || exe_flag == KD_EXE_RUN_ERROR) {
#ifdef KDLOCK_SELFTEST
			struct kd_spin_node *discarded_tail =
				ptr->local_queue_tail;
#endif
			/* The rejected waiter's next still owns this scan's followers.
			 * Discard only speculative deferrals; the final splice attaches
			 * any previously committed prefix to the rejected waiter. */
			if (!saved_tail)
				ptr->local_queue_head = NULL;
			ptr->local_queue_tail = saved_tail;
#ifdef KDLOCK_SELFTEST
			if (discarded_tail != saved_tail)
				kd_spin_selftest_restore(lock, curr_node,
							 discarded_tail,
							 exe_flag);
#endif
		}
#endif
		if (exe_flag == KD_EXE_NO_RUN) {
			print_debug("can't assembly\n");
			next_node = curr_node;
			break;
		}
		if (exe_flag == KD_EXE_RUN_ERROR) {
			print_debug("run error\n");
			/* No JIT body ran. Keep the packet queued and uncompleted until
			 * it acquires the lock. Native packets may need ret4; virtual
			 * packets use the ordinary acquired return to their parent. */
			next_node = curr_node;
			break;
		}

		if (exe_flag != KD_EXE_NATIVE_DONE)
			clear_locked_set_completed(curr_node);

		if (batch.outer.released) {
			/* B and this logical frame have finished. A's queue was already
			 * published; only reacquire for our own original request. */
			kd_spin_reclaim_outer(lock);
			return;
		}

		if (next_node == NULL || next_node->next == NULL ||
		    counter >= kd_combiner_batch_size)
			break;

		curr_node = next_node;
	}

#ifdef NUMA_AWARE
	if (ptr->local_queue_head != NULL) {
		ptr->local_queue_tail->next = next_node;
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_splice(lock, next_node, false);
#endif
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

	/* Publish the finished queue splice before successor acquisition. This
	 * is the last node access: its waiter can immediately reuse the slot. */
	smp_store_release(&next_node->locked, false);
}
#pragma GCC pop_options

#pragma GCC push_options
#pragma GCC optimize("O3")
/*
 * Core queue+combiner protocol entry.
 * Returns:
 *  0/2/4 -> delegated completion / queue acquisition / retry-path variants,
 *  1/3   -> waiters resumed from JIT completion/native,
 *  5     -> native relay wait.
 */
__attribute__((noipa)) noinline notrace static int
__kd_spin_lock_longjmp(struct qspinlock *lock, int tail,
		       register struct kd_spin_node *curr_node)
{
	struct qspinlock *word = kd_spin_word(lock);
	register struct kd_spin_node *prev_node = NULL, *next_node = NULL;
	struct qspinlock *parent_lock;
	int old_tail, val, j;

	/*
	 * These values remain live while a nested waiter or combiner runs. Keep
	 * their storage in this frame so the parent combiner can restore them.
	 */
	uint32_t prev_cs_cpu;
	bool prev_locked_val;
	uint64_t prev_rsp;
#ifdef NUMA_AWARE
	struct kd_spin_node *prev_local_queue_head;
	struct kd_spin_node *prev_local_queue_tail;
#endif

	/* Publish the clock with the node, before any combiner can service it. */
	curr_node->queued_at_ns = kd_exe_queue_timing_start();
	old_tail = xchg_tail(lock, tail);
	kd_spin_diag_waiter_enter(lock);

	if (old_tail & _Q_TAIL_MASK_HL) {
		prev_node = decode_tail(old_tail);
#ifdef KDLOCK_SELFTEST
		/* Publication can let the predecessor finish and recycle its node. */
		int previous_task = prev_node->task_struct_ptr->pid;
		int previous_cpu = prev_node->cpuid;
#endif

		prev_node->next = curr_node;
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_link(curr_node, prev_node, previous_task,
				      previous_cpu);
#endif

		while (smp_load_acquire(&curr_node->locked)) {
			if (curr_node->jit_waiter) {
				kd_spin_selftest_node_event(
					KD_NODE_REMOTE_POLL);
				kd_exec_remote_poll(
					curr_node->jit_context->requester);
			}
			cpu_relax();
		}
		smp_rmb();
		if (READ_ONCE(curr_node->native_resume)) {
			this_cpu_ptr(&kd_spin_nodes[0])->count--;
			kd_spin_selftest_node_event(KD_NODE_NATIVE_RETURN);
			kd_spin_diag_waiter_exit(lock);
			kd_spin_set_resume_node(curr_node);
			return 5;
		}

		struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

		if (curr_node->completed) {
			print_debug("wakeup\n");
#ifdef ENABLE_IRQS_CHECK
			if (curr_node->irqs_disabled) {
				ptr->irqs_disabled = curr_node->irqs_disabled;
			}
#endif
			for (j = 7; j >= 0; j--)
				if (ptr->lock_addr[j] != 0)
					break;

			this_cpu_ptr(&kd_spin_nodes[0])->count--;
			kd_spin_selftest_node_event(KD_NODE_REMOTE_RETURN);

			if (!curr_node->jit_waiter && j >= 0) {
				parent_lock =
					(struct qspinlock *)(unsigned long)
						ptr->lock_addr[j];
#ifdef DEBUG_KD_SPIN
				BUG_ON(parent_lock == lock);
#endif
				if (kd_spin_is_ooo(parent_lock)) {
					print_debug("Waiter unlocked OOO\n");
					kd_spin_diag_waiter_exit(lock);
					kd_spin_set_resume_node(curr_node);
					return 1;
				}
			}

			prefetchw((void *)(unsigned long)curr_node->rsp);
			prefetchw((void *)(unsigned long)(curr_node->rsp + 64));
			prefetchw(
				(void *)(unsigned long)(curr_node->rsp + 128));
			prefetchw(
				(void *)(unsigned long)(curr_node->rsp + 192));
			prefetchw(
				(void *)(unsigned long)(curr_node->rsp + 256));
			prefetchw(
				(void *)(unsigned long)(curr_node->rsp + 320));
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

	val = atomic_cond_read_acquire(&word->val,
				       !(VAL & _Q_LOCKED_PENDING_MASK));

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
	    atomic_try_cmpxchg_relaxed(&word->val, &val, _Q_LOCKED_VAL_HL))
		goto release; /* No contention */

	/* Either somebody is queued behind us or _Q_PENDING_VAL_HL is set */
	check_and_set_combiner(lock);
	kd_spin_claim_origin(lock);
	/* This request now owns Linux L. Record before releasing/reusing its node
	 * to process followers; the combiner's batch is not this queue interval. */
	kd_exe_queue_timing_end(false, &curr_node->queued_at_ns,
				kd_exe_queue_timing_start());

	/*
	 * contended path; wait for next if not observed yet, release.
	 */
	smp_cond_load_relaxed_sched(&curr_node->next, (VAL));
	next_node = curr_node->next;
#ifdef DEBUG_KD_SPIN
	BUG_ON(next_node == NULL);
#endif
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	j = kd_spin_lock_stack_depth(ptr);
	if (unlikely(j >= ARRAY_SIZE(ptr->lock_addr))) {
		/*
		 * Keep native ownership without entering another combiner. The
		 * successor may wait on the physical lock, but cannot acquire it
		 * until our caller unlocks. No saved context has been changed and
		 * the common exit releases this node exactly once.
		 */
		set_locked(lock);
		smp_store_release(&next_node->locked, false);
		goto release;
	}

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
	kd_spin_selftest_node_event(KD_NODE_COMBINER_ENTER);
	prev_locked_val = word->locked;
#ifdef DEBUG_KD_SPIN
	BUG_ON(prev_locked_val >= _Q_LOCKED_COMBINER_VAL);
#endif
	word->locked = _Q_LOCKED_COMBINER_VAL;
	prev_rsp = curr_node->rsp;
	curr_node->rsp = 0;

#ifdef NUMA_AWARE
	prev_local_queue_head = ptr->local_queue_head;
	prev_local_queue_tail = ptr->local_queue_tail;

#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_queue_context(lock, true);
#endif
	ptr->local_queue_head = NULL;
	ptr->local_queue_tail = NULL;
#endif

	ptr->lock_addr[j] = (uint64_t)(unsigned long)lock;
	kd_spin_diag_validate_lock_stack(ptr);

	run_combiner(lock, next_node);

#ifdef DEBUG_KD_SPIN
	BUG_ON(this_cpu_ptr(&local_shadow_stack)->lock_addr[j] !=
	       (uint64_t)(unsigned long)lock);
#endif

	ptr->lock_addr[j] = 0;
	kd_spin_diag_validate_lock_stack(ptr);

#ifdef NUMA_AWARE
	ptr->local_queue_head = prev_local_queue_head;
	ptr->local_queue_tail = prev_local_queue_tail;
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_queue_context(lock, false);
#endif
#endif

	curr_node->rsp = prev_rsp;

	if (word->locked == _Q_UNLOCKED_OOO_VAL) {
		if (prev_cs_cpu != -1) {
			print_debug("Waking up %d\n", prev_cs_cpu);
			clear_locked_set_completed(
				per_cpu_ptr(&kd_spin_nodes[0], prev_cs_cpu));
		}
		ptr->curr_cs_cpu = -1;
	} else {
		ptr->curr_cs_cpu = prev_cs_cpu;
	}
	word->locked = prev_locked_val;

	kd_spin_diag_waiter_exit(lock);
	kd_spin_set_resume_node(curr_node);
	return READ_ONCE(curr_node->jit_retry) ? 4 : 2;
release:
	kd_spin_claim_origin(lock);
	kd_exe_queue_timing_end(false, &curr_node->queued_at_ns,
				kd_exe_queue_timing_start());
	/*
	 * release the node
	 */
	this_cpu_ptr(&kd_spin_nodes[0])->count--;
	kd_spin_selftest_node_event(KD_NODE_HEAD_RETURN);
	kd_spin_diag_waiter_exit(lock);
	kd_spin_set_resume_node(curr_node);
	return READ_ONCE(curr_node->jit_retry) ? 4 : 0;
}
#pragma GCC pop_options

/*
 * Slowpath entry for promoted locks:
 * allocates a per-CPU node, initializes queue state, and either waits or runs
 * combiner depending on queue position and contention.
 */
__attribute__((noipa)) noinline notrace static int
__kd_spin_lock_slowpath(struct qspinlock *lock)
{
	struct kd_spin_node *base, *curr_node;
	struct kd_spin_native_input *input;
	int tail, idx;

	base = this_cpu_ptr(&kd_spin_nodes[0]);
	kd_spin_diag_record(
		lock, KD_SPIN_DIAG_SLOWPATH,
		kd_spin_lock_stack_depth(this_cpu_ptr(&local_shadow_stack)));
	idx = base->count++;
	if (unlikely(idx >= MAX_NODES)) {
		base->count--;
		kd_spin_selftest_node_event(KD_NODE_NATIVE_FULL);
		while (!kd_spin_trylock(lock))
			cpu_relax();
		return 0;
	}
	kd_spin_selftest_node_event(KD_NODE_NATIVE_RESERVE);
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
	curr_node->native_resume = false;
	curr_node->pinned_context = (preempt_count() & PREEMPT_MASK) != 1;
	curr_node->native_regs_decoded = false;
	curr_node->jit_context = NULL;
	BUG_ON(!kd_spin_entry_find((raw_spinlock_t *)lock,
				   &curr_node->spin_origin));

	return __kd_spin_lock_longjmp(lock, tail, curr_node);
}

/*
 * Public API
 */

/* Free all spin-related per-CPU resources and shadow-node state.
 * Callers must ensure no active delegations remain before draining.
 */
static void kd_spinlock_free_percpu(void)
{
	int cpu;

	for_each_possible_cpu(cpu) {
		struct shadow_stack *stack =
			per_cpu_ptr(&local_shadow_stack, cpu);

		vfree(*per_cpu_ptr(&kd_spin_jit_contexts, cpu));
		*per_cpu_ptr(&kd_spin_jit_contexts, cpu) = NULL;
		if (stack->ptr)
			vfree((char *)stack->ptr - SIZE_OF_SHADOW_STACK);
		stack->ptr = NULL;
		stack->local_shadow_stack_ptr = 0;
	}
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_nodes_free();
#endif
}

/*
 * Initialize JIT/diagnostic state for all CPUs.
 * Any allocation failure rolls back partially created per-CPU state.
 */
int kd_spinlock_init(void)
{
	int i, j;
#ifdef KDLOCK_SELFTEST
	int ret;
#endif

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

#ifdef KDLOCK_SELFTEST
	ret = kd_spin_selftest_nodes_init();
	if (ret)
		return ret;
#endif
	for_each_possible_cpu(i) {
		void *stack_ptr = vzalloc(SIZE_OF_SHADOW_STACK);
		struct shadow_stack *ptr = per_cpu_ptr(&local_shadow_stack, i);
		struct kd_spin_jit_context *contexts;

		if (!stack_ptr)
			goto err_free;
		contexts = vzalloc(array_size(MAX_NODES, sizeof(*contexts)));
		if (!contexts) {
			vfree(stack_ptr);
			goto err_free;
		}
		*per_cpu_ptr(&kd_spin_jit_contexts, i) = contexts;

#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_stack_init(stack_ptr);
#endif
		ptr->ptr = stack_ptr + SIZE_OF_SHADOW_STACK;
		for (j = 0; j < 8; j++)
			ptr->lock_addr[j] = 0;
		ptr->local_shadow_stack_ptr =
			(uint64_t)(unsigned long)stack_ptr +
			SIZE_OF_SHADOW_STACK - 8;
		ptr->curr_cs_cpu = -1;
		ptr->prev_cs_cpu = -1;
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
			node->native_regs_decoded = false;
			node->jit_context = NULL;
			node->gsbase = 0;
		}
	}

#ifdef KDLOCK_SELFTEST
	ret = kd_spin_shadow_selftest();
	if (ret) {
		kd_spinlock_free_percpu();
		return ret;
	}
#endif
	return 0;

err_free:
	kd_spinlock_free_percpu();
	return -ENOMEM;
}

/* Print per-lock accounting and release per-CPU resources.
 * Must be invoked after all active frames and waiters have drained.
 */
void kd_spinlock_exit(void)
{
	int i;

#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_nodes_report();
	kd_spin_selftest_frames_report();
	kd_spin_selftest_refusal_report();
#ifdef NUMA_AWARE
	kd_spin_selftest_deferred_report();
#endif
#endif
	KD_PR_INFO("kd_spin diag overflow=%lld\n",
		   (long long)atomic64_read(&kd_spin_diag_overflow));
	KD_PR_INFO("kd_spin diag invariant_failures=%lld\n",
		   (long long)atomic64_read(&kd_spin_diag_invariant_failures));
	for (i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
		struct kd_spin_diag_slot *slot = &kd_spin_diag_slots[i];
		unsigned long addr =
			(unsigned long)atomic_long_read(&slot->addr);

		if (!addr)
			continue;
		KD_PR_INFO(
			"kd_spin lock stats: lock=%lx depth=%d slowpath=%lld "
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

	kd_spinlock_free_percpu();
}

/* Build a virtual waiter packet from a logical frame for nested delegation.
 * Parent frame lock vector is copied so nested ownership checks remain consistent.
 */
static int kd_spin_prepare_jit_node(struct kd_spin_node *node,
				    struct kd_spin_jit_context *context,
				    struct qspinlock *lock,
				    const struct pt_regs *regs,
				    struct kd_exec_frame *parent)
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
	node->spin_origin = parent->spin_origin;
	node->jit_waiter = true;
	node->pinned_context = false;
	node->jit_context = context;
	context->requester = parent;
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

/* Restore a virtual node's continuation after the callee returns from nested
 * critical-section execution.
 */
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

/* Complete the virtual-node resume decision after delegated nested execution:
 * parent done -> return to parent unlock path, else restore caller continuation.
 */
static int kd_spin_finish_remote_node(struct kd_spin_node *node,
				      struct pt_regs *regs,
				      struct kd_exec_frame *parent)
{
	if (smp_load_acquire(&parent->remote_result) != KD_EXEC_REMOTE_DONE)
		return -EINVAL;
	/* The physical waiter trampoline still needs the final unlock CALL word.
	 * Consume it only when this parent will resume more translated code. */
	if (kd_exec_frame_can_complete(parent)) {
		*regs = node->regs;
		return KD_SPIN_NESTED_PARENT_OOO;
	}
	if (kd_spin_advance_jit_node(node, regs))
		return -EINVAL;
	return KD_SPIN_NESTED_DELEGATED;
}

/* Register a nested spinlock request in logical parent frame and run queue protocol.
 * Returns acquired/delegated markers used by the parent CALL continuation handling.
 */
int kd_spin_nested_lock(struct qspinlock *lock, struct pt_regs *regs,
			struct kd_exec_frame *parent)
{
	struct kd_spin_ref request = { 0 };
	struct qspinlock *word;
	struct kd_spin_node *base, *node;
	struct kd_spin_jit_context *contexts;
	u32 tail;
	int idx, ret;
#ifdef KDLOCK_SELFTEST
	int initial_preempt = preempt_count();
	bool refusal_probe = false;
#endif

	if (!lock || !regs || !parent)
		return -EINVAL;
	if (kd_exec_frame_remote_pending(parent) ||
	    READ_ONCE(parent->remote_request))
		return -EBUSY;
	parent->remote_result = KD_EXEC_REMOTE_IDLE;

#ifdef KDLOCK_SELFTEST
	/* NULL requests select only the read-only pre-allocation observer. The
	 * context/node injection probes still start after a ticket is reserved.
	 */
	contexts = *this_cpu_ptr(&kd_spin_jit_contexts);
	refusal_probe = kd_spin_selftest_virtual_begin(
		lock, NULL, regs, parent, &contexts, initial_preempt);
#endif
	ret = kd_spin_entry_begin((raw_spinlock_t *)lock, KD_SPIN_ENTRY_VIRTUAL,
				  &request);
#ifdef KDLOCK_SELFTEST
	if (refusal_probe)
		kd_spin_selftest_virtual_end(&request, regs, parent, ret);
#endif
	if (ret)
		return ret;
	word = kd_spin_word(lock);
	if (atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL) == 0) {
		kd_spin_claim_origin(lock);
		parent->control_call.phase = KD_CALL_ACQUIRED;
		return KD_SPIN_NESTED_ACQUIRED;
	}

	base = this_cpu_ptr(&kd_spin_nodes[0]);
	contexts = *this_cpu_ptr(&kd_spin_jit_contexts);
#ifdef KDLOCK_SELFTEST
	/* Exercise real post-ticket cancellation before any node is published. */
	refusal_probe = kd_spin_selftest_virtual_begin(
		lock, &request, regs, parent, &contexts, initial_preempt);
#endif
	if (!contexts) {
		kd_spin_selftest_node_event(KD_NODE_CONTEXT_MISSING);
		ret = -ENOMEM;
		goto cancel;
	}
	idx = base->count++;
	if (unlikely(idx < 0 || idx >= MAX_NODES)) {
		base->count--;
		kd_spin_selftest_node_event(KD_NODE_VIRTUAL_FULL);
		ret = -E2BIG;
		goto cancel;
	}
	kd_spin_selftest_node_event(KD_NODE_VIRTUAL_RESERVE);
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
	node->native_resume = false;
	node->native_regs_decoded = false;
	ret = kd_spin_prepare_jit_node(node, &contexts[idx], lock, regs,
				       parent);
	if (ret) {
		base->count--;
		kd_spin_selftest_node_event(KD_NODE_PREPARE_CANCEL);
		goto cancel;
	}

	kd_spin_diag_record(
		lock, KD_SPIN_DIAG_SLOWPATH,
		kd_spin_lock_stack_depth(this_cpu_ptr(&local_shadow_stack)));
	parent->control_call.phase = KD_CALL_ENTERED;
	smp_store_release(&parent->remote_result, KD_EXEC_REMOTE_WAITING);
	ret = __kd_spin_lock_longjmp(lock, tail, node);
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_refusal_return(parent, node, ret);
#endif
	if (ret == 5) {
		BUG_ON(smp_load_acquire(&parent->remote_result) !=
		       KD_EXEC_REMOTE_NATIVE);
		*regs = node->regs;
		parent->control_call.phase = KD_CALL_COMPLETE;
		/* Retire B's physical request, not the logical waiter's native ref. */
		BUG_ON(kd_spin_entry_end(&request));
		return KD_SPIN_NESTED_NATIVE;
	}
	if (ret == 0) {
		parent->remote_result = KD_EXEC_REMOTE_IDLE;
		parent->control_call.phase = KD_CALL_ACQUIRED;
		return KD_SPIN_NESTED_ACQUIRED;
	}
	if (ret == 2) {
		parent->remote_result = KD_EXEC_REMOTE_IDLE;
		parent->control_call.phase = KD_CALL_ACQUIRED;
		return KD_SPIN_NESTED_ACQUIRED_QUEUE;
	}
	if (ret != 1 && ret != 3)
		return -EIO;
	ret = kd_spin_finish_remote_node(node, regs, parent);
	parent->control_call.phase = KD_CALL_COMPLETE;
	BUG_ON(kd_spin_entry_end(&request));
	return ret;
cancel:
	BUG_ON(kd_spin_entry_end(&request));
#ifdef KDLOCK_SELFTEST
	if (refusal_probe)
		kd_spin_selftest_virtual_end(&request, regs, parent, ret);
#endif
	return ret;
}

/* Resolve nested unlock for a delegated spinlock and propagate OOO condition.
 * For normal fast-path release it only pops the logical shadow stack entry.
 */
int kd_spin_nested_unlock(struct qspinlock *lock)
{
	bool ooo;

	if (!lock)
		return -EINVAL;

	kd_spin_unlock(lock);
	ooo = kd_spin_is_ooo(lock);
	if (ooo)
		return KD_SPIN_NESTED_UNLOCK_OOO;

	return kd_spin_nested_shadow_pop(lock);
}

__attribute__((noipa)) noinline notrace static uint64_t *
get_shadow_stack_ptr(void)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	return &(ptr->local_shadow_stack_ptr);
}

/* Resume node defaults to the current CPU node if no explicit wakeup target exists.
 * This ensures direct return paths remain valid even without explicit set_resume.
 */
__attribute__((noipa)) noinline notrace static struct kd_spin_node *
get_kd_spin_resume_node(void)
{
	struct kd_spin_node *node =
		READ_ONCE(*this_cpu_ptr(&kd_spin_resume_nodes));

	return node ? node : this_cpu_ptr(&kd_spin_nodes[0]);
}

/* Native-input scratch slot is used as a temporary spill area for RSP handoff
 * while executing queue/combiner on shadow stack.
 */
__attribute__((noipa)) noinline notrace static struct kd_spin_native_input *
get_kd_spin_native_input(void)
{
	return this_cpu_ptr(&kd_spin_native_inputs);
}

/* Pick the earliest of node-rsp and logical-frame-rsp.
 * This avoids returning into an already-unwound return slot.
 */
__attribute__((noipa)) noinline notrace static unsigned long
get_kd_spin_resume_stack(void)
{
	struct kd_spin_node *node = get_kd_spin_resume_node();

	/* JIT may have grown the virtual CALL stack into old hook frames. Put
	 * our register copy below both live stacks, never over a return word.
	 */
	return min(node->rsp, node->regs.sp);
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
#pragma GCC push_options
#pragma GCC optimize("O3")
/* Software packet restoration only: neither entry below loads flags. The
 * normal form consumes a saved stack return; the in-CS form pushes regs.ip.
 * Do not reuse them for a new flags-live exit without its separate contract. */
__attribute__((noipa)) noinline notrace void
jump_to_saved_regs(struct pt_regs *regs)
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
		     "movq 0x70(%%rdi), %%rdi\n"
		     "retq\n"
		     :
		     :
		     : "memory");
	__builtin_unreachable();
}

#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void
jump_to_saved_regs_in_cs(struct pt_regs *regs)
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
		     "pushq 0x80(%%rdi)\n"
		     "movq 0x70(%%rdi), %%rdi\n"
		     "retq\n"
		     :
		     :
		     : "memory");
	__builtin_unreachable();
}
#pragma GCC pop_options

__attribute__((noipa)) noinline notrace static void
kd_spin_resume_waiter(unsigned int mode)
{
	struct kd_spin_node *node = get_kd_spin_resume_node();
	struct pt_regs regs = node->regs;
	struct kd_spin_ref ref = node->spin_origin;

	if (node->jit_retry)
		KD_PR_INFO("spin JIT retry resume: node=%px cpu=%d ip=%lx\n",
			   node, node->cpuid, regs.ip);
	if (mode == 2)
		BUG_ON(kd_spin_entry_mark_native(&ref));
	else if (!mode)
		BUG_ON(kd_spin_entry_end(&ref));
	/* After end(), only native-stack locals may be read. */
	if (mode)
		jump_to_saved_regs_in_cs(&regs);
	jump_to_saved_regs(&regs);
	__builtin_unreachable();
}

#pragma GCC push_options
#pragma GCC optimize("O3")
/* Bridge from slow-path result code to resumed execution.
 * mode maps return classes from __kd_spin_lock_longjmp to:
 * 0=delegated native handoff, 1/3/4/5=queue/native restore variants.
 */
__attribute__((noipa)) noinline notrace static void
kd_spin_lock_slowpath(struct qspinlock *lock, unsigned long rsp_value)
{
	register int ret_val;

	asm volatile("callq %P0\n"
		     "movq %%rsp, %c1(%%rax)\n"
		     :
		     : "i"(get_kd_spin_native_input),
		       "i"(offsetof(struct kd_spin_native_input, rsp))
		     : "memory");
	WRITE_ONCE(this_cpu_ptr(&kd_spin_native_inputs)->regs_sp, rsp_value);
	asm volatile("callq %P0\n"
		     "movq (%%rax), %%rsp\n"
		     :
		     : "i"(get_shadow_stack_ptr)
		     : "memory");
	ret_val = __kd_spin_lock_slowpath(lock);
	if (ret_val == 0 || ret_val == 2) {
		/* This also handles node exhaustion, which has no resume node. */
		asm volatile("callq %P0\n"
			     "movq %c1(%%rax), %%rsp\n"
			     :
			     : "i"(get_kd_spin_native_input),
			       "i"(offsetof(struct kd_spin_native_input, rsp))
			     : "memory");
		return;
	}
	if (ret_val == 1 || ret_val == 3) {
		asm volatile("callq %P0\n"
			     "movq %%rax, %%rsp\n"
			     :
			     : "i"(get_kd_spin_resume_stack)
			     : "memory");
		kd_spin_resume_waiter(0);
		__builtin_unreachable();
	}
	if (ret_val == 4) {
		asm volatile("callq %P0\n"
			     "movq %%rax, %%rsp\n"
			     :
			     : "i"(get_kd_spin_resume_stack)
			     : "memory");
		kd_spin_resume_waiter(1);
		__builtin_unreachable();
	}
	if (ret_val == 5) {
		asm volatile("callq %P0\n"
			     "movq %%rax, %%rsp\n"
			     :
			     : "i"(get_kd_spin_resume_stack)
			     : "memory");
		kd_spin_resume_waiter(2);
		__builtin_unreachable();
	}
	BUG();
}
#pragma GCC pop_options

/* Hook entry for queued spin lock acquisition:
 * handles fast path when possible, otherwise routes to qspin queue protocol.
 */
__attribute__((noipa)) noinline notrace void
kd_spin_lock(struct qspinlock *lock, unsigned long rsp_value)
{
	struct kd_spin_ref ref = { 0 };
	struct qspinlock *word;
	u32 val, cnt;

	if (!in_task() || irqs_disabled() || softirq_count() ||
	    current->migration_disabled || kd_spin_entry_native_active())
		goto native;
	if (kd_spin_entry_begin((raw_spinlock_t *)lock, KD_SPIN_ENTRY_HOOK,
				&ref))
		goto native;
	/* A native helper called by JIT must not reenter its private C stack. */
	if (kd_exec_current_frame() || kd_exec_context_busy()) {
		BUG_ON(kd_spin_entry_end(&ref));
		goto native;
	}
	word = kd_spin_word(lock);
	val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);
	if (!val)
		goto acquired;
	if (val == _Q_PENDING_VAL_HL) {
		cnt = _Q_PENDING_LOOPS_HL;
		val = atomic_cond_read_relaxed(
			&word->val, (VAL != _Q_PENDING_VAL_HL) || !cnt--);
	}
	if (val & ~_Q_LOCKED_MASK_HL)
		goto queue;
	val = kd_spin_fetch_set_pending_acquire(lock);
	if (unlikely(val & ~_Q_LOCKED_MASK_HL)) {
		if (!(val & _Q_PENDING_MASK_HL))
			clear_pending(lock);
		goto queue;
	}
	if (val & _Q_LOCKED_MASK_HL)
		atomic_cond_read_acquire(&word->val,
					 !(VAL & _Q_LOCKED_MASK_HL));
	clear_pending_set_locked(lock);
	goto acquired;
queue:
	kd_spin_lock_slowpath(lock, rsp_value);
acquired:
	kd_spin_claim_origin(lock);
	return;
native:
	__raw_spin_lock((raw_spinlock_t *)lock);
}
EXPORT_SYMBOL_GPL(kd_spin_lock);

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
	struct qspinlock *word = kd_spin_word(lock);
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	int from_cpuid = ptr->curr_cs_cpu;
	int j, max_idx, my_idx;

	uint64_t temp_lock_addr;

	j = 0;
	max_idx = -1;
	my_idx = -1;

	if (word->locked == _Q_LOCKED_VAL_HL ||
	    word->locked == _Q_LOCKED_IRQ_VAL) {
		kd_spin_release_origin(lock);
		return;
	}

	for (j = 0; j < 8; j++) {
		temp_lock_addr = ptr->lock_addr[j];
		if (temp_lock_addr != 0)
			max_idx = j;
		if (temp_lock_addr == (uint64_t)(unsigned long)lock)
			my_idx = j;
		if (temp_lock_addr == 0)
			break;
	}
	kd_spin_diag_validate_lock_stack(ptr);
	kd_spin_diag_validate_outer_unlock(ptr, lock, my_idx, max_idx);

	if (my_idx == -1) {
		if (word->locked == _Q_LOCKED_COMBINER_VAL) {
#ifdef KD_SPIN_STATS
			this_cpu_inc(ooo_unlocks);
#endif
			kd_spin_debug_ooo_unlock(lock,
						 kd_spin_lock_stack_depth(ptr));
			word->locked = _Q_UNLOCKED_OOO_VAL;
			print_debug("OOO unlock\n");
		} else
			BUG_ON(true);
		return;
	}

#ifdef DEBUG_KD_SPIN
	if (word->locked != _Q_LOCKED_COMBINER_VAL)
		BUG_ON(true);

	BUG_ON(from_cpuid == -1);

	if (max_idx < 0) {
		BUG_ON(true);
	}

#endif
	if (my_idx < max_idx) {
#ifdef KD_SPIN_STATS
		this_cpu_inc(ooo_unlocks);
#endif

		kd_spin_debug_ooo_unlock(lock, kd_spin_lock_stack_depth(ptr));
		word->locked = _Q_UNLOCKED_OOO_VAL;
		return;
	}

	struct kd_spin_node *curr_node =
		per_cpu_ptr(&kd_spin_nodes[0], from_cpuid);

#ifdef ENABLE_IRQS_CHECK
	curr_node->irqs_disabled = irqs_disabled();
#endif
	if (ptr->irqs_disabled) {
		ptr->irqs_disabled = false;
		local_irq_disable();
	}
}

static __always_inline int kd_spin_trylock(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
	u32 val;

	val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);
	if (val == 0)
		return true;

	return false;
}

#ifdef KDLOCK_SELFTEST
/* Keep access to private queue state out of the production API. */
#include "../tests/kernel/spin_frame_trace.c"
#include "../tests/kernel/spin_readmission_trace.c"
#include "../tests/kernel/spin_refusal_trace.c"
#include "../tests/kernel/spin_deferred_trace.c"
#include "../tests/kernel/spin_shadow_selftest.c"
#include "../tests/kernel/spin_virtual_selftest.c"
#endif
