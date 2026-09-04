// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi
//
// Ported to kdlock: kd_mutex — JIT-sandbox mutex delegation.
// Follows the same kd_exe_on_call_hl() model as kd_spinlock.c.

#include <linux/module.h>
#include <linux/smp.h>
#include <linux/bug.h>
#include <linux/percpu.h>
#include <linux/hardirq.h>
#include <linux/prefetch.h>
#include <linux/atomic.h>
#include <asm/byteorder.h>
#include <linux/vmalloc.h>
#include <linux/sched/stat.h>
#include <linux/sched/task.h>
#include <linux/sched.h>
#include <linux/topology.h>
#include <linux/errno.h>

#include "kd_mutex.h"
#include "kd_lock.h"
#include "kd_exec.h"
#include "exe.h"
#include "utils.h"

/* --------------------------------------------------------------------------
 * Debug
 * -------------------------------------------------------------------------- */
#ifdef DSM_DEBUG
#define print_debug(fmt, ...)                                                  \
	({                                                                     \
		printk(KERN_ALERT "[%d] [%d] kd_mutex (%s) lock(%px): " fmt,  \
		       smp_processor_id(), current->pid, __func__, lock,       \
		       ##__VA_ARGS__);                                         \
	})
#else
#define print_debug(fmt, ...)
#endif

/* --------------------------------------------------------------------------
 * Constants
 * -------------------------------------------------------------------------- */
#define KD_MUTEX_WAITER_UNPROCESSED  0
#define KD_MUTEX_WAITER_PROCESSED    1

#define _Q_LOCKED_VAL                1
#define _Q_LOCKED_COMBINER_VAL       3

#define SIZE_OF_SHADOW_STACK         8192L
#define UINT64_MAX                   0xffffffffffffffffL

long kd_mutex_batch_size = 1024;

/* Always-on protocol counters used for validation and post-mortem diagnosis. */
static atomic64_t kd_mutex_slowpath_count;
static atomic64_t kd_mutex_combiner_count;
static atomic64_t kd_mutex_handoff_count;
static atomic64_t kd_mutex_jit_success_count;
static atomic64_t kd_mutex_jit_not_ready_count;
static atomic64_t kd_mutex_jit_failure_count;
static atomic64_t kd_mutex_jit_resume_count;
static atomic64_t kd_mutex_frame_failure_count;
static atomic64_t kd_mutex_node_overflow_count;
static atomic64_t kd_mutex_multi_slot_count;
static atomic64_t kd_mutex_context_busy_count;
static atomic64_t kd_mutex_nested_lock_count;
static atomic64_t kd_mutex_nested_fast_count;
static atomic64_t kd_mutex_nested_queued_count;
static atomic64_t kd_mutex_nested_remote_count;
static atomic64_t kd_mutex_nested_unlock_count;
static atomic64_t kd_mutex_nested_abort_release_count;
static atomic_t kd_mutex_active_waiters;
static atomic_t kd_mutex_max_waiters;
static atomic_t kd_mutex_reserved_nodes;

/*
 * Mutex JIT sandbox is still experimental.  Keep it opt-in so normal mutex
 * delegation tests exercise the queue / combiner / fallback protocol without
 * risking VM-wide crashes from translated code bugs.  Enable with:
 *   insmod kdlock_km.ko mutex_jit=1
 */
int kd_mutex_jit_enabled;
module_param_named(mutex_jit, kd_mutex_jit_enabled, int, 0644);

/* --------------------------------------------------------------------------
 * Spin-with-schedule macros (for waiter spinning)
 * -------------------------------------------------------------------------- */
#ifndef smp_cond_load_relaxed_sched
#define smp_cond_load_relaxed_sched(ptr, cond_expr)                            \
	({                                                                     \
		typeof(ptr) __PTR = (ptr);                                     \
		__unqual_scalar_typeof(*ptr) VAL;                              \
		for (;;) {                                                     \
			VAL = READ_ONCE(*__PTR);                               \
			if (cond_expr) break;                                  \
			cpu_relax();                                           \
			if (need_resched()) {                                  \
				preempt_enable(); schedule(); preempt_disable();\
			}                                                      \
		}                                                              \
		(typeof(*ptr))VAL;                                             \
	})
#endif

#define kd_cond_load_acquire_sched(ptr, cond_expr)                             \
	({                                                                     \
		typeof(ptr) __PTR = (ptr);                                     \
		__unqual_scalar_typeof(*ptr) VAL;                              \
		for (;;) {                                                     \
			VAL = smp_load_acquire(__PTR);                         \
			if (cond_expr) break;                                  \
			cpu_relax();                                           \
			if (need_resched()) {                                  \
				preempt_enable(); schedule(); preempt_disable();\
			}                                                      \
		}                                                              \
		(typeof(*ptr))VAL;                                             \
	})

/* --------------------------------------------------------------------------
 * Per-CPU shadow stack
 * -------------------------------------------------------------------------- */
struct kd_mutex_shadow {
	uint64_t lock_addr[8];           /* nested lock tracking              */
	unsigned long node_slots;        /* reserved per-CPU waiter slots     */
	struct kd_mutex_node *resume_node; /* valid while waiter is CPU-pinned */
} __cacheline_aligned_in_smp;

struct kd_mutex_jit_context {
	unsigned int lock_depth;
	unsigned long lock_addr[KD_EXEC_MAX_LOCK_DEPTH];
	enum kd_exec_lock_kind lock_kind[KD_EXEC_MAX_LOCK_DEPTH];
	void *lock_node[KD_EXEC_MAX_LOCK_DEPTH];
	bool lock_released[KD_EXEC_MAX_LOCK_DEPTH];
};

static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_mutex_node,
				     kd_mutex_nodes[KD_MUTEX_MAX_NODES]);
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_mutex_shadow,
				     kd_mutex_shadows);

/* --------------------------------------------------------------------------
 * Tail encoding (same scheme as qspinlock: cpu+idx packed into u32)
 * -------------------------------------------------------------------------- */
#define _Q_TAIL_IDX_OFFSET  2
#define _Q_TAIL_IDX_BITS    2
#define _Q_TAIL_IDX_MASK    ((1U << _Q_TAIL_IDX_BITS) - 1)
#define _Q_TAIL_CPU_OFFSET  (_Q_TAIL_IDX_OFFSET + _Q_TAIL_IDX_BITS)

static inline u32 encode_tail(int cpu, int idx)
{
	return (cpu + 1) << _Q_TAIL_CPU_OFFSET | idx << _Q_TAIL_IDX_OFFSET;
}

static inline struct kd_mutex_node *decode_tail(u32 tail)
{
	int cpu = (tail >> _Q_TAIL_CPU_OFFSET) - 1;
	int idx = (tail >> _Q_TAIL_IDX_OFFSET) & _Q_TAIL_IDX_MASK;
	return per_cpu_ptr(&kd_mutex_nodes[idx], cpu);
}

static inline u32 xchg_tail(struct kd_mutex *lock, u32 tail)
{
	return (u32)(unsigned long)xchg(&lock->tail, (void *)(unsigned long)tail);
}

/* --------------------------------------------------------------------------
 * Small helpers
 * -------------------------------------------------------------------------- */
static __always_inline void
clear_locked_set_completed(struct kd_mutex_node *node)
{
	WRITE_ONCE(node->completed, KD_MUTEX_WAITER_PROCESSED);
	smp_store_release(&node->locked, 0);
}

static __always_inline void set_locked(struct kd_mutex *lock)
{
	smp_store_release(&lock->locked, _Q_LOCKED_VAL);
}

static void kd_mutex_update_max_waiters(int active)
{
	int old = atomic_read(&kd_mutex_max_waiters);

	while (active > old) {
		int previous = atomic_cmpxchg(&kd_mutex_max_waiters, old, active);

		if (previous == old)
			break;
		old = previous;
	}
}

static void kd_mutex_waiter_enter(struct kd_mutex *lock)
{
	int active = atomic_inc_return(&kd_mutex_active_waiters);

	atomic_inc(&lock->waiter_count);
	kd_mutex_update_max_waiters(active);
}

static void kd_mutex_waiter_exit(struct kd_mutex *lock)
{
	if (unlikely(atomic_dec_return(&lock->waiter_count) < 0)) {
		atomic_set(&lock->waiter_count, 0);
		atomic64_inc(&kd_mutex_frame_failure_count);
		KD_PR_ERR("kd_mutex lock waiter count underflow lock=%px\n", lock);
	}
	if (unlikely(atomic_dec_return(&kd_mutex_active_waiters) < 0)) {
		atomic_set(&kd_mutex_active_waiters, 0);
		atomic64_inc(&kd_mutex_frame_failure_count);
		KD_PR_ERR("kd_mutex active waiter count underflow\n");
	}
}

/* Called with preemption disabled and migration pinned. */
static void kd_mutex_schedule_if_needed(void)
{
	if (!need_resched())
		return;
	preempt_enable();
	schedule();
	preempt_disable();
}

static void kd_mutex_wait_and_lock(struct kd_mutex *lock)
{
	for (;;) {
		while (smp_load_acquire(&lock->locked)) {
			cpu_relax();
			kd_mutex_schedule_if_needed();
		}
		if (cmpxchg(&lock->locked, 0, _Q_LOCKED_VAL) == 0)
			return;
		cpu_relax();
		kd_mutex_schedule_if_needed();
	}
}

/* Reservation is serialized by preemption disable on this migration-pinned
 * CPU. A separate stack per slot permits the reservation to survive schedule(). */
static struct kd_mutex_node *kd_mutex_reserve_node(void)
{
	struct kd_mutex_shadow *shadow = this_cpu_ptr(&kd_mutex_shadows);
	unsigned long slots = READ_ONCE(shadow->node_slots);
	int idx;

	for (idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
		struct kd_mutex_node *node;

		if (slots & BIT(idx))
			continue;
		node = this_cpu_ptr(&kd_mutex_nodes[idx]);
		if (!node->shadow_stack_base)
			continue;
		WRITE_ONCE(shadow->node_slots, slots | BIT(idx));
		if (slots)
			atomic64_inc(&kd_mutex_multi_slot_count);
		atomic_inc(&kd_mutex_reserved_nodes);
		return node;
	}

	return NULL;
}

static void kd_mutex_release_node(struct kd_mutex_node *node)
{
	struct kd_mutex_shadow *shadow = this_cpu_ptr(&kd_mutex_shadows);
	unsigned long slots = READ_ONCE(shadow->node_slots);
	unsigned long bit;

	if (unlikely(!node || node->slot < 0 ||
		     node->slot >= KD_MUTEX_MAX_NODES))
		goto invalid;
	bit = BIT(node->slot);
	if (unlikely(!(slots & bit)))
		goto invalid;

	node->next = NULL;
	node->lock = NULL;
	node->task_struct_ptr = NULL;
	node->jit_context = NULL;
	node->jit_waiter = false;
	WRITE_ONCE(shadow->node_slots, slots & ~bit);
	atomic_dec(&kd_mutex_reserved_nodes);
	return;

invalid:
	atomic64_inc(&kd_mutex_frame_failure_count);
	KD_PR_ERR("kd_mutex invalid waiter slot release node=%px slots=%lx\n",
		  node, slots);
}

/* --------------------------------------------------------------------------
 * JIT-sandbox execution of a waiter's critical section
 *
 * The kernel's mutex_lock saves ALL callee-saved registers before capturing
 * ret_rsp (confirmed via disassembly).  Stack layout at ret_rsp:
 *   [0] = lock ptr / padding    [4] = saved r14
 *   [1] = saved rbx             [5] = saved r15
 *   [2] = saved r12             [6] = saved rbp (caller's)
 *   [3] = saved r13             [7] = return address (CS entry)
 * ret_rsp + 64 = caller's RSP.  Identical to the spinlock path.
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
execute_cs(struct kd_mutex *lock, struct kd_mutex_node *curr_node)
{
	unsigned long outgoing_rsp;
	void *outgoing_rsp_ptr = &outgoing_rsp;
	void *incoming_rsp_ptr = (void *)curr_node->regs.sp;
	struct kd_mutex_jit_context *jit_context = curr_node->jit_context;
	struct kd_exec_frame *frame;
	struct pt_regs retry_regs;
	unsigned long lock_addr[1];
	enum kd_exec_lock_kind lock_kind[1];
	void *lock_node[1];
	int ret_flag;
	int frame_ret;

	asm volatile("movq %%rsp, %0" : "=r"(outgoing_rsp));

	if (!lock->origin_mutex_addr ||
	    (!curr_node->jit_waiter && !incoming_rsp_ptr) ||
	    (curr_node->jit_waiter && !jit_context)) {
		atomic64_inc(&kd_mutex_frame_failure_count);
		return KD_EXE_RUN_ERROR;
	}

	if (!kd_mutex_jit_enabled) {
		KD_PR_DEBUG("mutex JIT disabled, hand lock to waiter\n");
		return KD_EXE_NO_RUN;
	}

	if (!curr_node->jit_waiter) {
		curr_node->regs.bx  = ((unsigned long *)incoming_rsp_ptr)[1];
		curr_node->regs.r12 = ((unsigned long *)incoming_rsp_ptr)[2];
		curr_node->regs.r13 = ((unsigned long *)incoming_rsp_ptr)[3];
		curr_node->regs.r14 = ((unsigned long *)incoming_rsp_ptr)[4];
		curr_node->regs.r15 = ((unsigned long *)incoming_rsp_ptr)[5];
		curr_node->regs.bp  = ((unsigned long *)incoming_rsp_ptr)[6];
		curr_node->regs.ip  = ((unsigned long *)incoming_rsp_ptr)[7];
		curr_node->regs.sp  = (unsigned long)incoming_rsp_ptr + 64;
		if (!curr_node->regs.ip ||
		    (curr_node->saved_ret_addr &&
		     curr_node->regs.ip != curr_node->saved_ret_addr)) {
			atomic64_inc(&kd_mutex_frame_failure_count);
			KD_PR_ERR("mutex JIT invalid waiter entry: stack=%lx saved=%lx\n",
				  curr_node->regs.ip, curr_node->saved_ret_addr);
			return KD_EXE_RUN_ERROR;
		}
	}

	print_debug("JIT exec waiter cpu %d ip %lx sp %lx\n",
		    curr_node->cpuid, curr_node->regs.ip, curr_node->regs.sp);

	if (!kd_exe_is_ready(0, curr_node->regs.ip)) {
		atomic64_inc(&kd_mutex_jit_not_ready_count);
		kd_exe_add(0, curr_node->regs.ip);
		return KD_EXE_NO_RUN;
	}
	if (kd_exec_context_busy()) {
		/* A scheduled mutex combiner owns this CPU's frame stack. The
		 * current waiter must use queue handoff without touching it. */
		atomic64_inc(&kd_mutex_context_busy_count);
		return KD_EXE_NO_RUN;
	}

	retry_regs = curr_node->regs;
	frame = kd_exec_frame_push(&curr_node->regs, curr_node->regs.ip,
				   lock->origin_mutex_addr, curr_node,
				   outgoing_rsp_ptr,
				   curr_node->jit_waiter ?
				   jit_context->lock_depth : 1);
	if (!frame) {
		atomic64_inc(&kd_mutex_frame_failure_count);
		return KD_EXE_RUN_ERROR;
	}

	if (curr_node->jit_waiter) {
		frame_ret = kd_exec_frame_set_lock_entries(
			frame, jit_context->lock_addr, jit_context->lock_kind,
			jit_context->lock_node, jit_context->lock_released,
			jit_context->lock_depth);
	} else {
		lock_addr[0] = lock->origin_mutex_addr;
		lock_kind[0] = KD_EXEC_LOCK_QUEUE_OWNER;
		lock_node[0] = curr_node;
		frame_ret = kd_exec_frame_set_lock_entries(
			frame, lock_addr, lock_kind, lock_node, NULL, 1);
	}
	if (frame_ret) {
		atomic64_inc(&kd_mutex_frame_failure_count);
		KD_PR_ERR("mutex JIT frame lock entry invalid: %d\n",
			  frame_ret);
		frame_ret = kd_exec_frame_abort(frame);
		if (!frame_ret)
			frame_ret = kd_exec_frame_pop(frame, NULL);
		if (unlikely(frame_ret)) {
			atomic64_inc(&kd_mutex_frame_failure_count);
			KD_PR_ERR("mutex JIT invalid-frame cleanup failed: %d\n",
				  frame_ret);
			/* A live invalid frame poisons every later translation on this
			 * CPU, so native continuation is no longer safe. */
			BUG();
		}
		return KD_EXE_RUN_ERROR;
	}

	ret_flag = kd_exe_on_call_hl_entry(&frame->regs, outgoing_rsp_ptr,
					   frame->entry_ip,
					   frame->outer_lock_addr);
	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		frame_ret = kd_exec_frame_record_event(
			frame, KD_EXEC_EVENT_OUTER_UNLOCK, &frame->regs);
		if (!frame_ret)
			frame_ret = kd_exec_frame_complete(frame);
		if (unlikely(frame_ret)) {
			atomic64_inc(&kd_mutex_frame_failure_count);
			KD_PR_ERR("mutex JIT committed frame transition failed: %d\n",
				  frame_ret);
			/* The translated CS has already reached its outer unlock. A
			 * native retry would execute its side effects twice. */
			BUG();
		}
	}

	if (ret_flag != KD_EXE_RUN_TO_UNLOCK) {
		frame_ret = kd_mutex_jit_abort_cleanup(frame);
		if (unlikely(frame_ret)) {
			atomic64_inc(&kd_mutex_frame_failure_count);
			KD_PR_ERR("mutex JIT nested abort cleanup failed: %d\n",
				  frame_ret);
			BUG();
		}
		if (kd_exec_frame_state(frame) != KD_EXEC_FRAME_COMPLETE &&
		    kd_exec_frame_abort(frame))
			atomic64_inc(&kd_mutex_frame_failure_count);
		frame->regs = retry_regs;
	}

	frame_ret = kd_exec_frame_pop(frame, &curr_node->regs);
	if (frame_ret) {
		atomic64_inc(&kd_mutex_frame_failure_count);
		KD_PR_ERR("mutex JIT frame pop failed: %d\n", frame_ret);
		if (ret_flag == KD_EXE_RUN_TO_UNLOCK)
			BUG();
		return KD_EXE_RUN_ERROR;
	}

	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		KD_PR_DEBUG("mutex JIT delegation ok\n");
		return 0;
	}

	atomic64_inc(&kd_mutex_jit_failure_count);
	KD_PR_DEBUG("mutex JIT delegation failed: %d\n", ret_flag);
	return ret_flag;
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Combiner loop: execute CS for each queued waiter via JIT sandbox
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static void
run_combiner(struct kd_mutex *lock, struct kd_mutex_node *curr_node)
{
	struct kd_mutex_node *next_node = NULL;
	struct task_struct *previous_combiner;
	int counter = 0;

	atomic64_inc(&kd_mutex_combiner_count);

	if (!curr_node || !curr_node->next) {
		/* Only one waiter — pass lock directly, no delegation needed */
		atomic64_inc(&kd_mutex_handoff_count);
		set_locked(lock);
		if (curr_node)
			smp_store_release(&curr_node->locked, 0);
		return;
	}

	previous_combiner = READ_ONCE(lock->combiner_task);
	WRITE_ONCE(lock->combiner_task, current);
	while (curr_node) {
		counter++;
		next_node = curr_node->next;

		int exe_flag = execute_cs(lock, curr_node);

		if (exe_flag != 0) {
			/*
			 * Only execute_cs() returning 0 means the sandbox reached
			 * mutex_unlock. Any other status must fall back without marking
			 * the waiter completed.
			 * Hand the lock to this waiter so it can execute
			 * its own CS as the new combiner.
			 */
			atomic64_inc(&kd_mutex_handoff_count);
			next_node = curr_node;
			break;
		}

		atomic64_inc(&kd_mutex_jit_success_count);
		clear_locked_set_completed(curr_node);

		if (!next_node || !next_node->next ||
		    counter >= kd_mutex_batch_size)
			break;

		curr_node = next_node;
	}
	WRITE_ONCE(lock->combiner_task, previous_combiner);

	/* Pass lock to the next waiter who will become the new combiner.
	 * next_node is guaranteed non-NULL: either it's the failed curr_node,
	 * or it was validated as non-NULL before the break above. */
	set_locked(lock);
	if (next_node)
		smp_store_release(&next_node->locked, 0);
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Slowpath: queue as waiter, spin, possibly become combiner
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
__kd_mutex_lock_slowpath(struct kd_mutex *lock, int tail,
			  struct kd_mutex_node *curr_node)
{
	struct kd_mutex_node *prev_node = NULL, *next_node = NULL;
	struct kd_mutex_shadow *ptr = this_cpu_ptr(&kd_mutex_shadows);
	u32 old_tail;
	int old_locked;
	int j;

	old_tail = xchg_tail(lock, tail);
	kd_mutex_waiter_enter(lock);

	if (old_tail) {
		/* --- waiter path: link behind prev, spin until woken --- */
		prev_node = decode_tail(old_tail);
		WRITE_ONCE(prev_node->next, curr_node);

		print_debug("Mutex waiter spinning\n");
		kd_cond_load_acquire_sched(&curr_node->locked, !VAL);

		/* CS was processed by combiner via JIT sandbox → done */
		if (curr_node->completed) {
			if (!curr_node->jit_waiter) {
				/* Keep the node reachable until _kd_mutex_lock snapshots its
				 * post-JIT registers with migration disabled. */
				WRITE_ONCE(ptr->resume_node, curr_node);
			}
			kd_mutex_waiter_exit(lock);
			return 3;
		}
		/* Fall through: become combiner */
	}

	/* --- become lock holder / combiner --- */
	kd_mutex_wait_and_lock(lock);

	/* Only waiter in queue? */
	if (cmpxchg(&lock->tail,
		    (struct kd_mutex_node *)(unsigned long)curr_node->tail,
		    NULL) == (struct kd_mutex_node *)(unsigned long)curr_node->tail)
		goto release;

	/* Wait for next waiter to appear */
	while (!next_node)
		next_node = READ_ONCE(curr_node->next);

	/* --- combiner path --- */
	old_locked = lock->locked;
	lock->locked = _Q_LOCKED_COMBINER_VAL;

	/* Save/restore nested delegation state */
	uint64_t prev_rsp = curr_node->rsp;
	curr_node->rsp = 0;

	j = 7;
	for (j = 7; j >= 0; j--)
		if (ptr->lock_addr[j])
			break;
	j += 1;
	if (unlikely(j >= 8)) {
		atomic64_inc(&kd_mutex_frame_failure_count);
		curr_node->rsp = prev_rsp;
		WRITE_ONCE(lock->locked, old_locked);
		goto release;
	}
	ptr->lock_addr[j] = (uint64_t)lock;

	run_combiner(lock, next_node);

	ptr->lock_addr[j] = 0;
	curr_node->rsp = prev_rsp;
	WRITE_ONCE(lock->locked, old_locked);

release:
	kd_mutex_waiter_exit(lock);
	return 2;
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Slowpath entry: init node, queue, may become combiner
 * -------------------------------------------------------------------------- */
__attribute__((noipa)) noinline notrace static int
kd_mutex_lock_slowpath(struct kd_mutex *lock,
			   struct kd_mutex_node *curr_node)
{
	atomic64_inc(&kd_mutex_slowpath_count);
	return __kd_mutex_lock_slowpath(lock, curr_node->tail, curr_node);
}

static int kd_mutex_prepare_jit_node(
	struct kd_mutex_node *node,
	struct kd_mutex_jit_context *context,
	struct kd_mutex *lock,
	const struct pt_regs *regs,
	const struct kd_exec_frame *parent)
{
	unsigned int i, depth;

	if (!node || !context || !lock || !lock->origin_mutex_addr ||
	    !regs || !regs->ip || !regs->sp || !parent ||
	    !kd_exec_frame_validate(parent))
		return -EINVAL;

	depth = kd_exec_frame_lock_depth(parent);
	if (depth >= KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;

	memset(context, 0, sizeof(*context));
	node->regs = *regs;
	node->jit_waiter = true;
	node->jit_context = context;
	context->lock_depth = depth + 1;
	for (i = 0; i < depth; i++) {
		context->lock_addr[i] = parent->jit_lock_addr[i];
		context->lock_kind[i] = parent->jit_lock_kind[i];
		context->lock_node[i] = parent->jit_lock_node[i];
		context->lock_released[i] = parent->jit_lock_released[i];
	}
	context->lock_addr[depth] = lock->origin_mutex_addr;
	context->lock_kind[depth] = KD_EXEC_LOCK_QUEUE_OWNER;
	context->lock_node[depth] = node;
	context->lock_released[depth] = false;
	return 0;
}

static int kd_mutex_advance_jit_node(struct kd_mutex_node *node,
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

int kd_mutex_nested_lock(struct kd_mutex *lock, struct pt_regs *regs,
			 const struct kd_exec_frame *parent)
{
	struct kd_mutex_jit_context context;
	struct kd_mutex_node *node;
	int ret;

	if (!lock || !regs || !parent)
		return -EINVAL;

	atomic64_inc(&kd_mutex_nested_lock_count);
	if (cmpxchg(&lock->locked, 0, _Q_LOCKED_VAL) == 0) {
		atomic64_inc(&kd_mutex_nested_fast_count);
		return KD_MUTEX_NESTED_ACQUIRED;
	}

	node = kd_mutex_reserve_node();
	if (!node) {
		atomic64_inc(&kd_mutex_node_overflow_count);
		return -E2BIG;
	}

	node->locked = true;
	node->completed = false;
	node->next = NULL;
	node->tail = encode_tail(smp_processor_id(), node->slot);
	node->socket_id = numa_node_id();
	node->cpuid = smp_processor_id();
	node->rsp = 0;
	node->lock = lock;
	node->task_struct_ptr = current;
	node->saved_ret_addr = 0;
	ret = kd_mutex_prepare_jit_node(node, &context, lock, regs, parent);
	if (ret)
		goto release_node;

	atomic64_inc(&kd_mutex_nested_queued_count);
	atomic64_inc(&kd_mutex_slowpath_count);
	ret = __kd_mutex_lock_slowpath(lock, node->tail, node);
	if (ret == 3) {
		ret = kd_mutex_advance_jit_node(node, regs);
		if (!ret) {
			atomic64_inc(&kd_mutex_nested_remote_count);
			ret = KD_MUTEX_NESTED_DELEGATED;
		}
	} else if (ret == 2) {
		ret = KD_MUTEX_NESTED_ACQUIRED_QUEUE;
	} else {
		ret = -EIO;
	}

release_node:
	kd_mutex_release_node(node);
	return ret;
}

int kd_mutex_nested_unlock(struct kd_mutex *lock)
{
	int ret = _kd_mutex_unlock_checked(lock);

	if (!ret)
		atomic64_inc(&kd_mutex_nested_unlock_count);
	return ret;
}

int kd_mutex_waiter_count(struct kd_mutex *lock)
{
	return lock ? atomic_read(&lock->waiter_count) : -EINVAL;
}

void kd_mutex_note_nested_abort_release(void)
{
	atomic64_inc(&kd_mutex_nested_abort_release_count);
}

/* --------------------------------------------------------------------------
 * Asm trampoline: save regs, switch to shadow stack, call slowpath
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace int
kd_mutex_lock_slowpath_asm(struct kd_mutex *lock,
			   struct kd_mutex_node *curr_node)
{
	register int ret_val;
	register struct kd_mutex_node *cur_node = curr_node;
	register uint64_t shadow_sp;

	/* Save the native call stack so this waiter can schedule while executing
	 * the queue protocol on its independently reserved shadow stack. */
	asm volatile("movq %%rsp, %c1(%0)\n"
		     :
		     : "r"(cur_node),
		       "i"(offsetof(struct kd_mutex_node, rsp))
		     : "memory");

	shadow_sp = cur_node->shadow_stack_ptr;
	if (unlikely(!shadow_sp)) {
		KD_PR_ERR("kd_mutex: waiter shadow stack is NULL on cpu %d slot %d\n",
			  smp_processor_id(), cur_node->slot);
		kd_mutex_wait_and_lock(lock);
		return 0;
	}

	/* Switch to this reservation's shadow stack. */
	asm volatile("movq %0, %%rsp" :: "r"(shadow_sp) : "memory");

	ret_val = kd_mutex_lock_slowpath(lock, cur_node);

	/* Restore original stack before returning */
	asm volatile("movq %c1(%0), %%rsp\n"
		     :
		     : "r"(cur_node),
		       "i"(offsetof(struct kd_mutex_node, rsp))
		     : "memory");

	return ret_val;
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Public API
 * -------------------------------------------------------------------------- */

void kd_mutex_init(struct kd_mutex *lock)
{
	lock->tail = NULL;
	atomic_set(&lock->state, 0);
	lock->combiner_task = NULL;
	lock->origin_mutex_addr = 0;
	atomic_set(&lock->waiter_count, 0);
}

void kd_mutex_init_percpu(void)
{
	int i, j;

	atomic64_set(&kd_mutex_slowpath_count, 0);
	atomic64_set(&kd_mutex_combiner_count, 0);
	atomic64_set(&kd_mutex_handoff_count, 0);
	atomic64_set(&kd_mutex_jit_success_count, 0);
	atomic64_set(&kd_mutex_jit_not_ready_count, 0);
	atomic64_set(&kd_mutex_jit_failure_count, 0);
	atomic64_set(&kd_mutex_jit_resume_count, 0);
	atomic64_set(&kd_mutex_frame_failure_count, 0);
	atomic64_set(&kd_mutex_node_overflow_count, 0);
	atomic64_set(&kd_mutex_multi_slot_count, 0);
	atomic64_set(&kd_mutex_context_busy_count, 0);
	atomic64_set(&kd_mutex_nested_lock_count, 0);
	atomic64_set(&kd_mutex_nested_fast_count, 0);
	atomic64_set(&kd_mutex_nested_queued_count, 0);
	atomic64_set(&kd_mutex_nested_remote_count, 0);
	atomic64_set(&kd_mutex_nested_unlock_count, 0);
	atomic64_set(&kd_mutex_nested_abort_release_count, 0);
	atomic_set(&kd_mutex_active_waiters, 0);
	atomic_set(&kd_mutex_max_waiters, 0);
	atomic_set(&kd_mutex_reserved_nodes, 0);

	for_each_possible_cpu(i) {
		struct kd_mutex_shadow *p = per_cpu_ptr(&kd_mutex_shadows, i);

		memset(per_cpu_ptr(&kd_mutex_nodes[0], i), 0,
		       sizeof(struct kd_mutex_node) * KD_MUTEX_MAX_NODES);
		memset(p, 0, sizeof(*p));
		for (j = 0; j < 8; j++)
			p->lock_addr[j] = 0;
		p->node_slots = 0;
		p->resume_node = NULL;
		for (j = 0; j < KD_MUTEX_MAX_NODES; j++) {
			struct kd_mutex_node *node =
				per_cpu_ptr(&kd_mutex_nodes[j], i);
			void *node_stack = vzalloc(SIZE_OF_SHADOW_STACK);

			node->slot = j;
			node->shadow_stack_base = node_stack;
			if (!node_stack) {
				KD_PR_ERR("kd_mutex: waiter stack allocation failed on cpu %d slot %d\n",
					  i, j);
				continue;
			}
			node->shadow_stack_ptr =
				(uint64_t)((char *)node_stack +
					   SIZE_OF_SHADOW_STACK - 8);
		}
	}
}

void kd_mutex_exit(void)
{
	int i;

	KD_PR_INFO("kd_mutex stats: slowpath=%lld combiner=%lld handoff=%lld "
		   "jit_success=%lld jit_not_ready=%lld jit_failure=%lld "
		   "jit_resume=%lld frame_failure=%lld node_overflow=%lld "
		   "multi_slot=%lld context_busy=%lld nested_lock=%lld "
		   "nested_fast=%lld nested_queued=%lld nested_remote=%lld "
		   "nested_unlock=%lld nested_abort_release=%lld "
		   "active_waiters=%d max_waiters=%d "
		   "reserved_nodes=%d\n",
		   (long long)atomic64_read(&kd_mutex_slowpath_count),
		   (long long)atomic64_read(&kd_mutex_combiner_count),
		   (long long)atomic64_read(&kd_mutex_handoff_count),
		   (long long)atomic64_read(&kd_mutex_jit_success_count),
		   (long long)atomic64_read(&kd_mutex_jit_not_ready_count),
		   (long long)atomic64_read(&kd_mutex_jit_failure_count),
		   (long long)atomic64_read(&kd_mutex_jit_resume_count),
		   (long long)atomic64_read(&kd_mutex_frame_failure_count),
		   (long long)atomic64_read(&kd_mutex_node_overflow_count),
		   (long long)atomic64_read(&kd_mutex_multi_slot_count),
		   (long long)atomic64_read(&kd_mutex_context_busy_count),
		   (long long)atomic64_read(&kd_mutex_nested_lock_count),
		   (long long)atomic64_read(&kd_mutex_nested_fast_count),
		   (long long)atomic64_read(&kd_mutex_nested_queued_count),
		   (long long)atomic64_read(&kd_mutex_nested_remote_count),
		   (long long)atomic64_read(&kd_mutex_nested_unlock_count),
		   (long long)atomic64_read(
			   &kd_mutex_nested_abort_release_count),
		   atomic_read(&kd_mutex_active_waiters),
		   atomic_read(&kd_mutex_max_waiters),
		   atomic_read(&kd_mutex_reserved_nodes));

	for_each_possible_cpu(i) {
		struct kd_mutex_shadow *p = per_cpu_ptr(&kd_mutex_shadows, i);
		int j;

		if (READ_ONCE(p->node_slots))
			KD_PR_ERR("kd_mutex: cpu %d leaked waiter slots=%lx\n",
				  i, READ_ONCE(p->node_slots));
		for (j = 0; j < KD_MUTEX_MAX_NODES; j++) {
			struct kd_mutex_node *node =
				per_cpu_ptr(&kd_mutex_nodes[j], i);

			if (node->shadow_stack_base)
				vfree(node->shadow_stack_base);
			node->shadow_stack_base = NULL;
			node->shadow_stack_ptr = 0;
		}

		p->node_slots = 0;
		p->resume_node = NULL;
	}
}

/*
 * _kd_mutex_lock — fastpath cmpxchg, slowpath delegation queue.
 */
__attribute__((noipa)) noinline notrace void
_kd_mutex_lock(struct kd_mutex *lock, unsigned long rsp_value,
	       unsigned long ret_addr,
	       unsigned long s_rbx, unsigned long s_r12,
	       unsigned long s_r13, unsigned long s_r14,
	       unsigned long s_r15, unsigned long s_rbp)
{
	struct pt_regs resume_regs;
	bool resume_ready = false;
	int ret_val;

	if (likely(cmpxchg(&lock->locked, 0, _Q_LOCKED_VAL) == 0))
		return;

	/* Waiters may schedule, so pin each one to the CPU that owns its reserved
	 * node and private shadow-stack slot. */
	migrate_disable();
	preempt_disable();
	{
		struct kd_mutex_node *curr_node = kd_mutex_reserve_node();

		if (unlikely(!curr_node)) {
			/* This task never enters the queue, so waiting on its native stack
			 * is safe and returns only after it owns the shadow mutex. */
			atomic64_inc(&kd_mutex_node_overflow_count);
			kd_mutex_wait_and_lock(lock);
			ret_val = 0;
			goto scheduler_restore;
		}

		memset(&curr_node->regs, 0, sizeof(curr_node->regs));
		curr_node->regs.sp = rsp_value;
		curr_node->locked = true;
		curr_node->completed = false;
		curr_node->next = NULL;
		curr_node->tail = encode_tail(smp_processor_id(), curr_node->slot);
		curr_node->socket_id = numa_node_id();
		curr_node->cpuid = smp_processor_id();
		curr_node->lock = lock;
		curr_node->task_struct_ptr = current;
		curr_node->jit_context = NULL;
		curr_node->jit_waiter = false;
		/* Store callee-saved registers captured at hook entry */
		curr_node->saved_rbx = s_rbx;
		curr_node->saved_r12 = s_r12;
		curr_node->saved_r13 = s_r13;
		curr_node->saved_r14 = s_r14;
		curr_node->saved_r15 = s_r15;
		curr_node->saved_rbp = s_rbp;
		curr_node->saved_ret_addr = ret_addr;
		ret_val = kd_mutex_lock_slowpath_asm(lock, curr_node);
		if (ret_val == 3) {
			struct kd_mutex_shadow *shadow =
				this_cpu_ptr(&kd_mutex_shadows);
			struct kd_mutex_node *resume_node =
				READ_ONCE(shadow->resume_node);

			if (unlikely(!resume_node)) {
				atomic64_inc(&kd_mutex_frame_failure_count);
				KD_PR_ERR("mutex JIT completion missing resume node\n");
				BUG();
			}
			resume_regs = resume_node->regs;
			WRITE_ONCE(shadow->resume_node, NULL);
			kd_mutex_release_node(resume_node);
			resume_ready = true;
			atomic64_inc(&kd_mutex_jit_resume_count);
		} else {
			kd_mutex_release_node(curr_node);
		}
	scheduler_restore:
		;
	}
	preempt_enable();
	migrate_enable();

	if (resume_ready) {
		/* The combiner already executed this waiter's CS through
		 * mutex_unlock. Resume after that call only after restoring scheduler
		 * state, otherwise the waiter would execute its original CS again or
		 * remain permanently non-preemptible. */
		KD_PR_DEBUG("mutex JIT resume sp=%lx target=%lx ip=%lx\n",
			    resume_regs.sp,
			    READ_ONCE(*(unsigned long *)resume_regs.sp),
			    resume_regs.ip);
		jump_to_saved_regs(&resume_regs);
		BUG(); /* jump_to_saved_regs() must never return */
	}

	return;
}

/*
 * _kd_mutex_unlock — release the kd_mutex.
 *
 * Fastpath only: clear the locked bit.  No context switching, OOO detection,
 * or chaining — the JIT sandbox intercepted mutex_unlock inside the waiter's
 * CS and returned KD_EXE_RUN_TO_UNLOCK.  The combiner's run_combiner() loop
 * handles all waiter transitions.
 */
__attribute__((noipa)) noinline notrace int
_kd_mutex_unlock_checked(struct kd_mutex *lock)
{
	u8 locked = smp_load_acquire(&lock->locked);

	if (locked == _Q_LOCKED_VAL ||
	    locked == _Q_LOCKED_COMBINER_VAL) {
		smp_store_release(&lock->locked, 0);
		return 0;
	}
	/* Should not reach here in JIT sandbox model */
	KD_PR_ERR("kd_mutex_unlock: unexpected locked state %d\n",
		  locked);
	return -EINVAL;
}

__attribute__((noipa)) noinline notrace void
_kd_mutex_unlock(struct kd_mutex *lock)
{
	_kd_mutex_unlock_checked(lock);
}

int _kd_mutex_trylock(struct kd_mutex *lock)
{
	if (!READ_ONCE(lock->locked) &&
	    cmpxchg(&lock->locked, 0, _Q_LOCKED_VAL) == 0)
		return 1;
	return 0;
}
