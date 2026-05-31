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

#include "kd_mutex.h"
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

/* --------------------------------------------------------------------------
 * Per-CPU shadow stack
 * -------------------------------------------------------------------------- */
struct kd_mutex_shadow {
	uint64_t lock_addr[8];           /* nested lock tracking              */
	void *ptr;                       /* base of shadow stack              */
	uint64_t local_shadow_stack_ptr; /* current shadow stack position     */
} __cacheline_aligned_in_smp;

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
	int idx = (tail & _Q_TAIL_IDX_MASK) >> _Q_TAIL_IDX_OFFSET;
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
	WRITE_ONCE(node->locked, 0);
}

static __always_inline void set_locked(struct kd_mutex *lock)
{
	WRITE_ONCE(lock->locked, _Q_LOCKED_VAL);
}

/* --------------------------------------------------------------------------
 * Shadow-stack accessors (noipa for callq in inline asm)
 * -------------------------------------------------------------------------- */
__attribute__((noipa)) noinline notrace static uint64_t
get_mutex_shadow_stack_ptr(void)
{
	struct kd_mutex_shadow *p = this_cpu_ptr(&kd_mutex_shadows);
	return (uint64_t)&p->local_shadow_stack_ptr;
}

__attribute__((noipa)) noinline notrace static struct kd_mutex_node *
get_kd_mutex_node(void)
{
	return this_cpu_ptr(&kd_mutex_nodes[0]);
}

/* --------------------------------------------------------------------------
 * JIT-sandbox execution of a waiter's critical section
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
execute_cs(struct kd_mutex *lock, struct kd_mutex_node *curr_node)
{
	struct kd_mutex_shadow *ptr = this_cpu_ptr(&kd_mutex_shadows);
	void *outgoing_rsp_ptr = &ptr->local_shadow_stack_ptr;
	void *incoming_rsp_ptr = (void *)curr_node->regs.sp;
	int ret_flag;

	/*
	 * Populate pt_regs from the waiter's saved stack frame.
	 * Layout matches the callee-saved register spill produced by the
	 * compiler at the hook call site (same as kd_spinlock.c execute_cs).
	 */
	curr_node->regs.r15 = ((unsigned long *)incoming_rsp_ptr)[5];
	curr_node->regs.r14 = ((unsigned long *)incoming_rsp_ptr)[4];
	curr_node->regs.r13 = ((unsigned long *)incoming_rsp_ptr)[3];
	curr_node->regs.r12 = ((unsigned long *)incoming_rsp_ptr)[2];
	curr_node->regs.bx  = ((unsigned long *)incoming_rsp_ptr)[1];
	curr_node->regs.bp  = ((unsigned long *)incoming_rsp_ptr)[6];
	curr_node->regs.ip  = ((unsigned long *)incoming_rsp_ptr)[7];
	curr_node->regs.sp  = (unsigned long)incoming_rsp_ptr + 64;

	print_debug("JIT-sandbox exec for waiter cpu %d ip %lx sp %lx\n",
		    curr_node->cpuid, curr_node->regs.ip, curr_node->regs.sp);

	ret_flag = kd_exe_on_call_hl(&curr_node->regs, outgoing_rsp_ptr);

	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		KD_PR_DEBUG("mutex JIT delegation ok\n");
		return 0;
	}

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
	int counter = 0;

	if (!curr_node || !curr_node->next) {
		/* Only one waiter — pass lock directly, no delegation needed */
		set_locked(lock);
		curr_node->locked = false;
		smp_mb();
		return;
	}

	while (curr_node) {
		counter++;
		next_node = curr_node->next;

		int exe_flag = execute_cs(lock, curr_node);

		if (exe_flag == KD_EXE_NO_RUN ||
		    exe_flag == KD_EXE_RUN_ERROR) {
			/*
			 * Delegation failed — do NOT mark completed.
			 * Hand the lock to this waiter so it can execute
			 * its own CS as the new combiner.
			 */
			next_node = curr_node;
			break;
		}

		clear_locked_set_completed(curr_node);

		if (!next_node || !next_node->next ||
		    counter >= kd_mutex_batch_size)
			break;

		curr_node = next_node;
	}

	/* Pass lock to the next waiter who will become the new combiner.
	 * next_node is guaranteed non-NULL: either it's the failed curr_node,
	 * or it was validated as non-NULL before the break above. */
	set_locked(lock);
	if (next_node)
		next_node->locked = false;
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

	if (old_tail) {
		/* --- waiter path: link behind prev, spin until woken --- */
		prev_node = decode_tail(old_tail);
		WRITE_ONCE(prev_node->next, curr_node);

		print_debug("Mutex waiter spinning\n");
		smp_cond_load_relaxed_sched(&curr_node->locked, !VAL);

		/* CS was processed by combiner via JIT sandbox → done */
		if (curr_node->completed) {
			curr_node->count--;
			return 0;
		}
		/* Fall through: become combiner */
	}

	/* --- become lock holder / combiner --- */
	for (;;) {
		while (READ_ONCE(lock->locked))
			cpu_relax();
		if (cmpxchg(&lock->locked, 0, _Q_LOCKED_VAL) == 0)
			break;
	}

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
	if (unlikely(j >= 8))
		goto release;
	ptr->lock_addr[j] = (uint64_t)lock;

	run_combiner(lock, next_node);

	ptr->lock_addr[j] = 0;
	curr_node->rsp = prev_rsp;
	lock->locked = old_locked;

release:
	curr_node->count--;
	return 2;
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Slowpath entry: init node, queue, may become combiner
 * -------------------------------------------------------------------------- */
__attribute__((noipa)) noinline notrace static int
kd_mutex_lock_slowpath(struct kd_mutex *lock)
{
	struct kd_mutex_node *curr_node = this_cpu_ptr(&kd_mutex_nodes[0]);
	int idx = curr_node->count++;
	int tail = encode_tail(smp_processor_id(), idx);

	if (unlikely(idx >= KD_MUTEX_MAX_NODES)) {
		/* Nested too deep — fall back to spinning */
		while (!_kd_mutex_trylock(lock))
			cpu_relax();
		curr_node->count--;
		return 0;
	}

	curr_node += idx;
	curr_node->locked = true;
	curr_node->completed = false;
	curr_node->next = NULL;
	curr_node->tail = tail;
	curr_node->socket_id = numa_node_id();
	curr_node->cpuid = smp_processor_id();
	curr_node->lock = lock;
	curr_node->task_struct_ptr = current;

	return __kd_mutex_lock_slowpath(lock, tail, curr_node);
}

/* --------------------------------------------------------------------------
 * Asm trampoline: save regs, switch to shadow stack, call slowpath
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void
kd_mutex_lock_slowpath_asm(struct kd_mutex *lock, unsigned long rsp_value)
{
	register int ret_val;
	register struct kd_mutex_node *cur_node;

	/* Save callee rsp to node, record original sp for JIT sandbox */
	asm volatile("callq %P1\n"
		     "movq %%rsp, %c2(%%rax)\n"
		     "movq %%rax, %0\n"
		     : "=r"(cur_node)
		     : "i"(get_kd_mutex_node),
		       "i"(offsetof(struct kd_mutex_node, rsp))
		     : "memory");
	cur_node->regs.sp = rsp_value;

	/* Switch to per-CPU shadow stack */
	asm volatile("callq %P0\n"
		     "movq (%%rax), %%rsp\n"
		     :
		     : "i"(get_mutex_shadow_stack_ptr)
		     : "memory");

	ret_val = kd_mutex_lock_slowpath(lock);

	/* Restore original stack before returning */
	asm volatile("callq %P0\n"
		     "movq %c1(%%rax), %%rsp\n"
		     :
		     : "i"(get_kd_mutex_node),
		       "i"(offsetof(struct kd_mutex_node, rsp))
		     : "memory");

	if (ret_val == 2) {
		/* Became combiner — return to caller (runs own CS now) */
		return;
	}

	/* Waiter — CS was processed by combiner via JIT sandbox.
	 * The JIT sandbox already executed our CS code and reached unlock.
	 * We can simply return as if we held the lock. */
	return;
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
}

void kd_mutex_init_percpu(void)
{
	int i, j;
	for_each_possible_cpu(i) {
		void *stack_ptr = vzalloc(SIZE_OF_SHADOW_STACK);
		struct kd_mutex_shadow *p = per_cpu_ptr(&kd_mutex_shadows, i);
		p->ptr = stack_ptr + SIZE_OF_SHADOW_STACK;
		for (j = 0; j < 8; j++)
			p->lock_addr[j] = 0;
		p->local_shadow_stack_ptr =
			(uint64_t)(stack_ptr + SIZE_OF_SHADOW_STACK - 8);
	}
}

void kd_mutex_exit(void)
{
	int i;
	for_each_possible_cpu(i)
		vfree(per_cpu_ptr(&kd_mutex_shadows, i)->ptr
		      - SIZE_OF_SHADOW_STACK);
}

/*
 * _kd_mutex_lock — fastpath cmpxchg, slowpath delegation queue.
 */
__attribute__((noipa)) noinline notrace void
_kd_mutex_lock(struct kd_mutex *lock, unsigned long rsp_value)
{
	if (likely(cmpxchg(&lock->locked, 0, _Q_LOCKED_VAL) == 0))
		return;

	preempt_disable();
	{
		struct kd_mutex_node *curr_node =
			this_cpu_ptr(&kd_mutex_nodes[0]);
		curr_node->socket_id = numa_node_id();
		kd_mutex_lock_slowpath_asm(lock, rsp_value);
	}
	preempt_enable();
}

/*
 * _kd_mutex_unlock — release the kd_mutex.
 *
 * Fastpath only: clear the locked bit.  No context switching, OOO detection,
 * or chaining — the JIT sandbox intercepted mutex_unlock inside the waiter's
 * CS and returned KD_EXE_RUN_TO_UNLOCK.  The combiner's run_combiner() loop
 * handles all waiter transitions.
 */
__attribute__((noipa)) noinline notrace void
_kd_mutex_unlock(struct kd_mutex *lock)
{
	if (lock->locked == _Q_LOCKED_VAL ||
	    lock->locked == _Q_LOCKED_COMBINER_VAL) {
		lock->locked = false;
		return;
	}
	/* Should not reach here in JIT sandbox model */
	KD_PR_ERR("kd_mutex_unlock: unexpected locked state %d\n",
		  lock->locked);
}

int _kd_mutex_trylock(struct kd_mutex *lock)
{
	if (!lock->locked && cmpxchg(&lock->locked, 0, _Q_LOCKED_VAL) == 0)
		return 1;
	return 0;
}
