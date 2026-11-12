/* SPDX-License-Identifier: GPL-2.0 */
/* Per-CPU nodes, shadow-stack state and wait primitives; shared by the ordered spin fragments. */
#ifdef DSM_DEBUG
#define print_debug(fmt, ...)                                                  \
	({                                                                     \
		printk(KERN_EMERG "[%d] komb (%s) lock(%px): " fmt,            \
		       smp_processor_id(), __func__, lock, ##__VA_ARGS__);     \
	})
#else
#define print_debug(fmt, ...)
#endif

#define SIZE_OF_SHADOW_STACK 8192L
#define IRQ_NUMA_NODE 255

#define UINT64_MAX 0xffffffffffffffffL

#define KERNEL_SYNCSTRESS 1
#ifdef KERNEL_SYNCSTRESS
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
#else
#define smp_cond_load_relaxed_sched(ptr, cond_expr)                            \
	({                                                                     \
		typeof(ptr) __PTR = (ptr);                                     \
		__unqual_scalar_typeof(*ptr) VAL;                              \
		for (;;) {                                                     \
			VAL = READ_ONCE(*__PTR);                               \
			if (cond_expr)                                         \
				break;                                         \
			cpu_relax();                                           \
		}                                                              \
		(typeof(*ptr))VAL;                                             \
	})

//if (need_resched()) {
//	schedule_preempt_disabled();
//}
#endif

#ifndef smp_cond_load_acquire_sched
#define smp_cond_load_acquire_sched(ptr, cond_expr)                            \
	({                                                                     \
		__unqual_scalar_typeof(*ptr) _val;                             \
		_val = smp_cond_load_relaxed_sched(ptr, cond_expr);            \
		smp_acquire__after_ctrl_dep();                                 \
		(typeof(*ptr))_val;                                            \
	})
#endif

#define atomic_cond_read_acquire_sched(v, c)                                   \
	smp_cond_load_acquire_sched(&(v)->counter, (c))

struct shadow_stack {
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
	struct komb_node *next_node_ptr;
	uint64_t local_shadow_stack_ptr;
#ifdef NUMA_AWARE
	/*
 * Create a queue which is used by the combiner to store nodes which belong to
 * different socket.
 */

	struct komb_node *local_queue_head;
	struct komb_node *local_queue_tail;
#endif

	int irqs_disabled;

} ____cacheline_aligned_in_smp;

#ifdef LOCK_MEASURE_TIME
static DEFINE_PER_CPU_ALIGNED(uint64_t, combiner_loop);
static DEFINE_PER_CPU_ALIGNED(uint64_t, lock_stack_switch);
static DEFINE_PER_CPU_ALIGNED(uint64_t, unlock_stack_switch);
#endif

#ifdef KOMB_STATS
DEFINE_PER_CPU_ALIGNED(uint64_t, combiner_count);
DEFINE_PER_CPU_ALIGNED(uint64_t, waiter_combined);
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_combiner_count);
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_waiter_combined);
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_unlocks);
#endif

/*
 * Used by all threads to add itself to the queue on the slowpath.
 */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct komb_node, komb_nodes[MAX_NODES]);

/*
 * 8KB shadow stack used by all the threads. For waiter threads, switch to
 * shadow stack, because of IRQs. For combiner thread, switch to shadow stack
 * to handle nesting
 */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct shadow_stack, local_shadow_stack);
