// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi
//
// Ported to kdlock: kd_mutex — TCLocks-style mutex delegation protocol.
//
// Architecture
// ===========================================================================
// kd_mutex implements transparent critical-section delegation for kernel
// mutexes.  When a waiter contends on a mutex, instead of blocking, it
// packages its state into a per-CPU kd_mutex_node and queues itself.  The
// lock holder (combiner) then executes the waiter's critical section on the
// waiter's behalf using a lightweight stack switch (kd_context_switch).
//
// Flow summary
// ------------
// _kd_mutex_lock():
//   fastpath:  cmpxchg(locked, 0→1) → return immediately
//   slowpath:  save callee regs, switch to shadow stack, queue as waiter.
//              If at head of queue, become the combiner and execute CS for
//              queued waiters via execute_cs().
//
// _kd_mutex_unlock():
//   fastpath:  if simple-locked (locked==1), clear and return
//   combiner:  context-switch to next waiter (chaining), or back to own
//              shadow stack (end-of-batch).  OOO unlock is detected when
//              the lock is released from a non-outermost nesting level.
//
// Differences from the TCLocks reference (komb_mutex)
// ---------------------------------------------------
// - Per-CPU storage:  kd_mutex_nodes and kd_mutex_shadows are per-CPU
//   rather than per-task (current->komb_*).  This avoids task_struct
//   modifications, which a loadable module cannot perform.
// - Node pointers:  curr_cs_node / prev_cs_node store kd_mutex_node*
//   directly instead of CPU IDs or task pointers.
// - No task_struct extensions:  all delegation state lives in the per-CPU
//   shadow stack and node structures.
// ===========================================================================

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
#include "utils.h"

/* _Q_LOCKED_VAL comes from the spinlock world; define locally. */
#ifndef _Q_LOCKED_VAL
#define _Q_LOCKED_VAL 1
#endif

/* --------------------------------------------------------------------------
 * Debug helpers
 * -------------------------------------------------------------------------- */
// #define DEBUG_KD_MUTEX 1

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
#define KD_MUTEX_WAITER_UNPROCESSED   0
#define KD_MUTEX_WAITER_PARKED        1
#define KD_MUTEX_WAITER_PROCESSING    2
#define KD_MUTEX_WAITER_PROCESSED     4

#define _Q_LOCKED_COMBINER_VAL        3
#define _Q_UNLOCKED_OOO_VAL           7

#define UINT64_MAX 0xffffffffffffffffL

long kd_mutex_batch_size = 1024;

/* --------------------------------------------------------------------------
 * Per-CPU shadow stack for mutex delegation context switches
 *
 * curr_cs_node / prev_cs_node store node pointers directly, avoiding
 * the need for task_struct extensions that a loadable module cannot add.
 * -------------------------------------------------------------------------- */
struct kd_mutex_shadow {
	uint64_t lock_addr[8];
	void *ptr;
	struct kd_mutex_node *curr_cs_node;
	struct kd_mutex_node *prev_cs_node;
	uint64_t counter_val;
	struct kd_mutex_node *next_node_ptr;
	uint64_t local_shadow_stack_ptr;
#ifdef NUMA_AWARE
	struct kd_mutex_node *local_queue_head;
	struct kd_mutex_node *local_queue_tail;
#endif
} __cacheline_aligned_in_smp;

static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_mutex_node, kd_mutex_nodes);
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_mutex_shadow, kd_mutex_shadows);

/* --------------------------------------------------------------------------
 * Scheduling / wait helpers
 * -------------------------------------------------------------------------- */
static inline void schedule_out_curr_task(void)
{
	preempt_enable();
	schedule();
	preempt_disable();
}

static inline void park_waiter(struct kd_mutex_node *node)
{
	__set_current_state(TASK_INTERRUPTIBLE);
	if (cmpxchg(&node->completed, KD_MUTEX_WAITER_UNPROCESSED,
		    KD_MUTEX_WAITER_PARKED) != KD_MUTEX_WAITER_UNPROCESSED) {
		__set_current_state(TASK_RUNNING);
		return;
	}
	schedule_out_curr_task();
	__set_current_state(TASK_RUNNING);
}

static inline void wake_up_waiter(struct kd_mutex_node *node)
{
	u8 old_val = xchg(&node->completed, KD_MUTEX_WAITER_PROCESSING);
	if (old_val == KD_MUTEX_WAITER_PARKED) {
		struct task_struct *task = node->task_struct_ptr;
		get_task_struct(task);
		wake_up_process(task);
		put_task_struct(task);
	}
}

static __always_inline void
clear_locked_set_completed(struct kd_mutex_node *node)
{
	WRITE_ONCE(node->completed, KD_MUTEX_WAITER_PROCESSED);
	WRITE_ONCE(node->locked, 0);
}

static __always_inline void set_locked(struct kd_mutex *lock)
{
	WRITE_ONCE(lock->locked, 1);
}

/* --------------------------------------------------------------------------
 * Spin-with-possible-schedule macros
 * -------------------------------------------------------------------------- */
#ifndef smp_cond_load_relaxed_sched
#define smp_cond_load_relaxed_sched(ptr, cond_expr)                            \
	({                                                                     \
		typeof(ptr) __PTR = (ptr);                                     \
		__unqual_scalar_typeof(*ptr) VAL;                              \
		for (;;) {                                                     \
			VAL = READ_ONCE(*__PTR);                               \
			if (cond_expr)                                         \
				break;                                         \
			cpu_relax();                                           \
			if (need_resched()) {                                  \
				preempt_enable();                              \
				schedule();                                    \
				preempt_disable();                             \
			}                                                      \
		}                                                              \
		(typeof(*ptr))VAL;                                             \
	})
#endif

#define smp_cond_load_relaxed_sleep(curr_node, ptr, cond_expr)                 \
	({                                                                     \
		typeof(ptr) __PTR = (ptr);                                     \
		__unqual_scalar_typeof(*ptr) VAL;                              \
		for (;;) {                                                     \
			VAL = READ_ONCE(*__PTR);                               \
			if (cond_expr)                                         \
				break;                                         \
			cpu_relax();                                           \
			if (need_resched()) {                                  \
				if (single_task_running())                     \
					schedule_out_curr_task();              \
				else {                                         \
					if (READ_ONCE(curr_node->completed) == \
					    KD_MUTEX_WAITER_UNPROCESSED)       \
						park_waiter(curr_node);        \
					else                                   \
						schedule_out_curr_task();      \
				}                                              \
			}                                                      \
		}                                                              \
		(typeof(*ptr))VAL;                                             \
	})

/* --------------------------------------------------------------------------
 * Per-CPU accessors (noipa — required for inline asm callq pattern)
 * -------------------------------------------------------------------------- */
__attribute__((noipa)) noinline notrace static uint64_t
get_mutex_shadow_stack_ptr(struct kd_mutex *lock)
{
	struct kd_mutex_shadow *ptr = this_cpu_ptr(&kd_mutex_shadows);
	return (uint64_t)&ptr->local_shadow_stack_ptr;
}

__attribute__((noipa)) noinline notrace static struct kd_mutex_node *
get_kd_mutex_node(struct kd_mutex *lock)
{
	return this_cpu_ptr(&kd_mutex_nodes);
}

/* --------------------------------------------------------------------------
 * NUMA-aware queue helpers
 * -------------------------------------------------------------------------- */
#ifdef NUMA_AWARE
__always_inline static void add_to_local_queue(struct kd_mutex_node *node)
{
	struct kd_mutex_node **head, **tail;
	struct kd_mutex_shadow *ptr = this_cpu_ptr(&kd_mutex_shadows);
	head = &ptr->local_queue_head;
	tail = &ptr->local_queue_tail;

	if (*head == NULL) {
		*head = node;
		*tail = node;
	} else {
		(*tail)->next = node;
		*tail = node;
	}
}
#endif

__always_inline static struct kd_mutex_node *
get_next_node(struct kd_mutex_node *my_node)
{
#ifdef NUMA_AWARE
	struct kd_mutex_node *curr_node, *next_node;
	curr_node = my_node;
	next_node = curr_node->next;

	while (true) {
		if (next_node == NULL || next_node->next == NULL)
			goto next_node_null;

		if (next_node->socket_id == numa_node_id()) {
			void *rsp_ptr = (void *)(next_node->rsp);
			prefetchw(rsp_ptr);
			prefetchw(rsp_ptr + 64);
			prefetchw(rsp_ptr + 128);
			prefetchw(rsp_ptr + 192);
			prefetchw(rsp_ptr + 256);
			prefetchw(rsp_ptr + 320);
			prefetch(next_node->next);
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

/* --------------------------------------------------------------------------
 * Core: execute a waiter's critical section as the combiner.
 *
 * The combiner context-switches from the shadow stack to the waiter's stack
 * (pointed to by curr_node->rsp).  The waiter's code runs until it calls
 * _kd_mutex_unlock, which switches back here.  On return, we check for
 * out-of-order (OOO) unlock: the lock was released by a nested critical
 * section, not the outermost one.  In that case we wake up the waiter that
 * was preempted by the OOO unlock and continue chaining.
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static void
execute_cs(struct kd_mutex *lock, struct kd_mutex_node *curr_node)
{
	void *incoming_rsp_ptr, *outgoing_rsp_ptr;
	struct kd_mutex_node *next_node;
	struct kd_mutex_shadow *ptr = this_cpu_ptr(&kd_mutex_shadows);

	ptr->curr_cs_node = curr_node;

#ifdef DEBUG_KD_MUTEX
	BUG_ON(curr_node->cpuid == smp_processor_id());
#endif

	/* Switch to the waiter's saved stack pointer.  The pushed return
	 * address inside kd_context_switch resumes here when the waiter's
	 * unlock switches back. */
	incoming_rsp_ptr = &(curr_node->rsp);
	outgoing_rsp_ptr = &ptr->local_shadow_stack_ptr;

	kd_context_switch(incoming_rsp_ptr, outgoing_rsp_ptr);

	/* --- we resume here after the waiter's unlock context-switches back --- */

	if (lock->locked == _Q_UNLOCKED_OOO_VAL) {
		print_debug("Combiner got control back OOO unlock\n");

		curr_node = ptr->curr_cs_node;
		struct kd_mutex_node *my_node = this_cpu_ptr(&kd_mutex_nodes);

		if (curr_node) {
			curr_node->rsp = my_node->rsp;
			wake_up_waiter(curr_node);
			clear_locked_set_completed(curr_node);
		}
		ptr->prev_cs_node = NULL;
		ptr->curr_cs_node = NULL;
		lock->locked = _Q_LOCKED_COMBINER_VAL;

		next_node = ptr->next_node_ptr;
		if (next_node != NULL && next_node->next != NULL)
			execute_cs(lock, next_node);
	}
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Core: combiner loop — execute CS for queued waiters
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static void
run_combiner(struct kd_mutex *lock, struct kd_mutex_node *curr_node)
{
	struct kd_mutex_node *next_node = curr_node->next;
	struct kd_mutex_shadow *ptr = this_cpu_ptr(&kd_mutex_shadows);

#ifdef DEBUG_KD_MUTEX
	BUG_ON(curr_node == NULL);
#endif

	if (next_node == NULL) {
		set_locked(lock);
		wake_up_waiter(curr_node);
		WRITE_ONCE(curr_node->locked, 0);
		return;
	}

	WRITE_ONCE(lock->combiner_task, current);
	ptr->counter_val = 0;

	print_debug("mutex Combiner %d giving control to %d\n",
		    smp_processor_id(), curr_node->cpuid);

	execute_cs(lock, curr_node);

	print_debug("mutex Combiner got control back: %d counter: %lld\n",
		    smp_processor_id(), ptr->counter_val);

	if (ptr->prev_cs_node) {
		wake_up_waiter(ptr->prev_cs_node);
		clear_locked_set_completed(ptr->prev_cs_node);
		ptr->prev_cs_node = NULL;
	}

	next_node = ptr->next_node_ptr;
	ptr->next_node_ptr = NULL;

#ifdef NUMA_AWARE
	if (ptr->local_queue_head != NULL) {
		ptr->local_queue_tail->next = next_node;
		next_node = ptr->local_queue_head;
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
	}
#endif

	WRITE_ONCE(lock->combiner_task, NULL);
	set_locked(lock);

	print_debug("mutex Passing lock to next node %d\n", next_node->cpuid);
	wake_up_waiter(next_node);
	WRITE_ONCE(next_node->locked, 0);
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Slowpath: queue as waiter, spin, possibly become combiner.
 *
 * This is the heart of the mutex delegation protocol.
 *
 * Two paths out:
 *   1. Waiter path (prev != NULL):  link into queue, spin on node->locked.
 *      If completed == PROCESSED → the combiner executed our CS → return 0
 *      (restore original stack and return to caller as if we held the lock).
 *      Otherwise → fall through to become combiner.
 *
 *   2. Combiner path (prev == NULL, or waiter fell through):  wait for
 *      locked→0, cmpxchg ownership, then run_combiner to execute CS for
 *      queued waiters.
 *
 * Nested locking:  lock_addr[] tracks the stack of held locks so OOO
 * unlock can be detected.  All per-CPU shadow state is saved/restored
 * around the run_combiner call so nested delegation works correctly.
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
__kd_mutex_lock_slowpath(struct kd_mutex *lock,
			 register struct kd_mutex_node *curr_node)
{
	register struct kd_mutex_node *prev, *next;
	u8 prev_locked_val;
	int j;
	struct kd_mutex *parent_lock;
	struct kd_mutex_shadow *ptr = this_cpu_ptr(&kd_mutex_shadows);

#ifdef NUMA_AWARE
	struct kd_mutex_node *prev_local_queue_head;
	struct kd_mutex_node *prev_local_queue_tail;
#endif

	prev = xchg(&lock->tail, curr_node);
	next = NULL;

	if (prev) {
		WRITE_ONCE(prev->next, curr_node);

		print_debug("Mutex waiter going to spin\n");
		smp_cond_load_relaxed_sleep(curr_node, &curr_node->locked,
					    VAL == 0);

		print_debug("Mutex spin completed\n");
		if (READ_ONCE(curr_node->completed) ==
		    KD_MUTEX_WAITER_PROCESSED) {
			print_debug("Mutex CS processed\n");
			for (j = 7; j >= 0; j--)
				if (ptr->lock_addr[j])
					break;

			if (j >= 0) {
				parent_lock =
					(struct kd_mutex *)ptr->lock_addr[j];
#ifdef DEBUG_KD_MUTEX
				BUG_ON(parent_lock == lock);
#endif
				if (parent_lock->locked ==
				    _Q_UNLOCKED_OOO_VAL) {
					print_debug("Waiter unlocked OOO\n");
					return 1;
				}
			}

			prefetchw((void *)curr_node->rsp);
			return 0;
		}
	}

	/*
	 * At head of queue — wait for lock to become free.
	 */
	for (;;) {
		while (READ_ONCE(lock->locked)) {
			cpu_relax();
			if (need_resched())
				schedule_out_curr_task();
		}
		if (cmpxchg(&lock->locked, 0, 1) == 0)
			break;
	}

	print_debug("Mutex lock owner\n");

	if (cmpxchg(&lock->tail, curr_node, NULL) == curr_node)
		goto release;

	while (!next) {
		next = READ_ONCE(curr_node->next);
		cpu_relax();
		if (need_resched())
			schedule_out_curr_task();
	}

	/* Head of queue — become the combiner. */
	{
		struct kd_mutex_node *prev_cs_node = ptr->curr_cs_node;
		ptr->curr_cs_node = NULL;

#ifdef DEBUG_KD_MUTEX
		BUG_ON(ptr->prev_cs_node != NULL);
#endif

		prev_locked_val = lock->locked;
#ifdef DEBUG_KD_MUTEX
		BUG_ON(prev_locked_val >= _Q_LOCKED_COMBINER_VAL);
#endif
		lock->locked = _Q_LOCKED_COMBINER_VAL;

		struct task_struct *prev_task = curr_node->task_struct_ptr;
		uint64_t prev_rsp = curr_node->rsp;
		curr_node->rsp = 0;
		uint64_t prev_counter_val = ptr->counter_val;
		ptr->counter_val = 0;
		struct kd_mutex_node *prev_next_node = ptr->next_node_ptr;
		ptr->next_node_ptr = NULL;

#ifdef NUMA_AWARE
		prev_local_queue_head = ptr->local_queue_head;
		prev_local_queue_tail = ptr->local_queue_tail;
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
#endif
		uint64_t prev_stack_ptr = ptr->local_shadow_stack_ptr;

		j = 7;
		for (j = 7; j >= 0; j--)
			if (ptr->lock_addr[j])
				break;
		j += 1;
#ifdef DEBUG_KD_MUTEX
		BUG_ON(j >= 8 || j < 0);
#endif
		ptr->lock_addr[j] = (uint64_t)lock;

		run_combiner(lock, next);

#ifdef DEBUG_KD_MUTEX
		BUG_ON(ptr->lock_addr[j] != (uint64_t)lock);
#endif
		ptr->lock_addr[j] = 0;

		ptr->next_node_ptr = prev_next_node;
		ptr->counter_val = prev_counter_val;

#ifdef NUMA_AWARE
		ptr->local_queue_head = prev_local_queue_head;
		ptr->local_queue_tail = prev_local_queue_tail;
#endif

		ptr->local_shadow_stack_ptr = prev_stack_ptr;
		ptr->curr_cs_node = prev_cs_node;
		curr_node->rsp = prev_rsp;
		curr_node->task_struct_ptr = prev_task;

		if (lock->locked == _Q_UNLOCKED_OOO_VAL) {
			if (prev_cs_node) {
				wake_up_waiter(prev_cs_node);
				clear_locked_set_completed(prev_cs_node);
			}
			ptr->curr_cs_node = NULL;
		}
		lock->locked = prev_locked_val;
	}

release:
	return 0;
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Mutex lock slowpath (node init + queue)
 * -------------------------------------------------------------------------- */
__attribute__((noipa)) noinline notrace static int
kd_mutex_lock_slowpath(struct kd_mutex *lock)
{
	struct kd_mutex_node *curr_node = get_kd_mutex_node(lock);

	curr_node->locked = true;
	curr_node->completed = KD_MUTEX_WAITER_UNPROCESSED;
	curr_node->next = NULL;
	curr_node->cpuid = smp_processor_id();
	curr_node->task_struct_ptr = current;
	curr_node->lock = lock;

	return __kd_mutex_lock_slowpath(lock, curr_node);
}

/* --------------------------------------------------------------------------
 * Mutex lock entry: save callee regs, switch to shadow stack, call slowpath.
 *
 * This is the inline-asm trampoline.  It must be noipa so the compiler does
 * not assume anything about caller-saved registers after the stack switch.
 *
 * The sequence:
 *   1. Push callee-saved regs (rbp, rbx, r12–r15)
 *   2. Save current rsp → node->rsp   (get_kd_mutex_node)
 *   3. Load shadow stack ptr → rsp    (get_mutex_shadow_stack_ptr)
 *   4. Push rdi (lock argument) onto shadow stack
 *   5. Call kd_mutex_lock_slowpath(lock)
 *   6. On return: if OOO, return via shadow stack; otherwise restore
 *      waiter's rsp from node->rsp, pop callee regs, and ret.
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void
__kd_mutex_lock_asm(struct kd_mutex *lock)
{
	register int ret_val;

	asm volatile("pushq %%rbp\n"
		     "pushq %%rbx\n"
		     "pushq %%r12\n"
		     "pushq %%r13\n"
		     "pushq %%r14\n"
		     "pushq %%r15\n"
		     :
		     :
		     : "memory");
	asm volatile("callq %P0\n"
		     "movq %%rsp, %c1(%%rax)\n"
		     :
		     : "i"(get_kd_mutex_node),
		       "i"(offsetof(struct kd_mutex_node, rsp))
		     : "memory");
	asm volatile("callq %P0\n"
		     "movq (%%rax), %%rsp\n"
		     "pushq %%rdi\n"
		     :
		     : "i"(get_mutex_shadow_stack_ptr)
		     : "memory");

	ret_val = kd_mutex_lock_slowpath(lock);

	if (ret_val) {
		/* OOO unlock — return via shadow stack */
		asm volatile("popq %%rdi\n"
			     "callq %P0\n"
			     "movq (%%rax), %%rsp\n"
			     "popq %%r15\n"
			     "popq %%r14\n"
			     "popq %%r13\n"
			     "popq %%r12\n"
			     "popq %%rbx\n"
			     "popq %%rbp\n"
			     "retq\n"
			     :
			     : "i"(get_mutex_shadow_stack_ptr)
			     : "memory");
	} else {
		/* Normal — restore waiter's stack and return */
		asm volatile("popq %%rdi\n"
			     "callq %P0\n"
			     "movq %%rsp, (%%rax)\n"
			     :
			     : "i"(get_mutex_shadow_stack_ptr)
			     : "memory");
		asm volatile("callq %P0\n"
			     "movq %c1(%%rax), %%rsp\n"
			     :
			     : "i"(get_kd_mutex_node),
			       "i"(offsetof(struct kd_mutex_node, rsp))
			     : "memory");
		asm volatile("popq %%r15\n"
			     "popq %%r14\n"
			     "popq %%r13\n"
			     "popq %%r12\n"
			     "popq %%rbx\n"
			     "popq %%rbp\n"
			     "retq\n"
			     :
			     :
			     : "memory");
	}
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
		void *stack_ptr = vzalloc(KD_MUTEX_SHADOW_STACK_SIZE);
		struct kd_mutex_shadow *ptr =
			per_cpu_ptr(&kd_mutex_shadows, i);

		ptr->ptr = stack_ptr + KD_MUTEX_SHADOW_STACK_SIZE;
		for (j = 0; j < 8; j++)
			ptr->lock_addr[j] = 0;
		ptr->local_shadow_stack_ptr =
			(uint64_t)(stack_ptr + KD_MUTEX_SHADOW_STACK_SIZE - 8);
		ptr->curr_cs_node = NULL;
		ptr->prev_cs_node = NULL;
		ptr->counter_val = 0;
		ptr->next_node_ptr = NULL;
#ifdef NUMA_AWARE
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
#endif
	}
}

void kd_mutex_exit(void)
{
	int i;
	for_each_possible_cpu(i) {
		struct kd_mutex_shadow *ptr =
			per_cpu_ptr(&kd_mutex_shadows, i);
		vfree(ptr->ptr - KD_MUTEX_SHADOW_STACK_SIZE);
	}
}

__attribute__((noipa)) noinline notrace void
_kd_mutex_lock(struct kd_mutex *lock)
{
	int ret;

	ret = cmpxchg(&lock->locked, 0, 1);
	if (likely(ret == 0))
		return;

	preempt_disable();
	{
		struct kd_mutex_node *curr_node = get_kd_mutex_node(lock);
		curr_node->socket_id = numa_node_id();

		__kd_mutex_lock_asm(lock);

		/* Post-combiner cleanup */
		struct kd_mutex_shadow *ptr =
			this_cpu_ptr(&kd_mutex_shadows);
		struct kd_mutex_node *cs_node = ptr->curr_cs_node;

		if (cs_node) {
			if ((struct kd_mutex *)cs_node->lock == lock) {
				struct kd_mutex_node *next_node =
					get_next_node(cs_node);
				ptr->next_node_ptr = next_node;
			}
			wake_up_waiter(cs_node);

			if (ptr->prev_cs_node) {
				wake_up_waiter(ptr->prev_cs_node);
				clear_locked_set_completed(ptr->prev_cs_node);
				ptr->prev_cs_node = NULL;
			}
		}
	}
	preempt_enable();
}

int _kd_mutex_trylock(struct kd_mutex *lock)
{
	if (!lock->locked && cmpxchg(&lock->locked, 0, 1) == 0)
		return 1;
	return 0;
}

/*
 * _kd_mutex_unlock — release the kd_mutex.
 *
 * Three cases:
 *   Fastpath:  locked == _Q_LOCKED_VAL → clear to 0, return.
 *   OOO:       my_idx < max_idx in lock_addr[] → set OOO flag.
 *   Combiner:  context-switch to next waiter (chaining) or back to
 *              shadow stack (end-of-batch).
 */
__attribute__((noipa)) noinline notrace void
_kd_mutex_unlock(struct kd_mutex *lock)
{
	void *incoming_rsp_ptr, *outgoing_rsp_ptr;
	struct kd_mutex_shadow *ptr = this_cpu_ptr(&kd_mutex_shadows);
	struct kd_mutex_node *curr_node, *next_node;
	int j, max_idx, my_idx;
	uint64_t temp_lock_addr;

	j = 0;
	max_idx = -1;
	my_idx = -1;

	/* Fastpath: simple locked bit */
	if (lock->locked == _Q_LOCKED_VAL) {
		lock->locked = false;
		return;
	}

	for (j = 0; j < 8; j++) {
		temp_lock_addr = ptr->lock_addr[j];
		if (temp_lock_addr)
			max_idx = j;
		if (temp_lock_addr == (uint64_t)lock)
			my_idx = j;
		if (temp_lock_addr == 0)
			break;
	}

	if (my_idx == -1) {
		if (lock->locked == _Q_LOCKED_COMBINER_VAL) {
			lock->locked = _Q_UNLOCKED_OOO_VAL;
			print_debug("OOO unlock\n");
		}
		return;
	}

	/* Out-of-order unlock */
	if (my_idx < max_idx) {
		lock->locked = _Q_UNLOCKED_OOO_VAL;
		return;
	}

	curr_node = ptr->curr_cs_node;
#ifdef DEBUG_KD_MUTEX
	BUG_ON(curr_node == NULL);
	BUG_ON(lock->locked != _Q_LOCKED_COMBINER_VAL);
	BUG_ON(lock->combiner_task != current);
#endif

	next_node = ptr->next_node_ptr;
	uint64_t counter = ptr->counter_val;

	if (next_node == NULL || next_node->next == NULL ||
	    counter >= kd_mutex_batch_size) {
		incoming_rsp_ptr = &ptr->local_shadow_stack_ptr;
		ptr->prev_cs_node = curr_node;
		ptr->curr_cs_node = NULL;
	} else {
		ptr->prev_cs_node = curr_node;
		ptr->curr_cs_node = next_node;
		incoming_rsp_ptr = &(next_node->rsp);
		ptr->counter_val = counter + 1;
		print_debug("Jumping to next waiter: %d\n", next_node->cpuid);
	}

	outgoing_rsp_ptr = &(curr_node->rsp);

	preempt_disable();
	kd_context_switch(incoming_rsp_ptr, outgoing_rsp_ptr);
	preempt_enable();
}

/* --------------------------------------------------------------------------
 * Stub implementations for API completeness
 * -------------------------------------------------------------------------- */
void _kd_mutex_lock_rwsem_writer(struct kd_mutex *lock)
{
	_kd_mutex_lock(lock);
}

int __must_check _kd_mutex_lock_interruptible(struct kd_mutex *lock)
{
	return 0;
}

int __must_check _kd_mutex_lock_killable(struct kd_mutex *lock)
{
	return 0;
}
