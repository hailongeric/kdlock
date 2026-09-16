// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Original-lock identity, per-CPU nodes, shadow state and observer declarations.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

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
#include "../../tests/kernel/spin/spin_node_trace.c"
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
