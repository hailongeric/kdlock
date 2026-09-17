// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Original-lock identity, per-CPU nodes, shadow state and observer declarations.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

#define IRQ_NUMA_NODE 255
#define KD_SPIN_DIAG_SLOTS 32
#define KD_SPIN_NUM_PREFETCH_LINES 6

static const unsigned int kd_combiner_batch_size = 1024;

static __always_inline int kd_spin_trylock(struct qspinlock *word);

/* Physical request state lives on the caller's stack, not a recyclable node
 * or the logical waiter's spin_origin (which can belong to an ancestor).
 * The entry pin keeps this request local; stable S is passed through the
 * queue/batch, including early release and reclaim, without another map scan. */
struct kd_spin_request {
	struct kd_spin_ref ref;
	struct qspinlock *word;
};

static struct qspinlock *kd_spin_request_word(const struct kd_spin_ref *ref)
{
	struct kd_spin_gate *gate = kd_spin_entry_gate(ref);

	BUG_ON(!gate);
	return &gate->word;
}

/* L is the public identity; only these private words contain kdlock tails. */
static struct qspinlock *kd_spin_word(struct qspinlock *lock)
{
	struct kd_spin_gate *gate = kd_spin_gate_find((raw_spinlock_t *)lock);

	BUG_ON(!gate);
	return &gate->word;
}

/* Normal unlocks recover S from their live ticket. An OOO ancestor can be
 * represented only by shadow/frame state on this CPU, so keep one read-only
 * map fallback for that case; it grants no right to release physical L. */
static struct kd_spin_request kd_spin_unlock_lookup(struct qspinlock *lock)
{
	struct kd_spin_request request = { 0 };

	if (kd_spin_entry_find((raw_spinlock_t *)lock, &request.ref))
		request.word = kd_spin_request_word(&request.ref);
	else
		request.word = kd_spin_word(lock);
	return request;
}

static void kd_spin_unlock_request(struct qspinlock *lock,
				   struct kd_spin_request *request);

static bool kd_spin_is_ooo(struct qspinlock *lock)
{
	struct kd_spin_gate *gate = kd_spin_gate_find((raw_spinlock_t *)lock);

	/* Native ancestors have no scheduling word and cannot carry OOO markers. */
	return gate && READ_ONCE(gate->word.locked) == 7;
}

static void kd_spin_claim_origin(const struct kd_spin_request *request)
{
	int ret;

	ret = kd_spin_entry_claim(&request->ref);
	if (unlikely(ret)) {
		KD_PR_ERR(
			"spin origin claim failed word=%px cpu=%d task=%d ret=%d\n",
			request->word, raw_smp_processor_id(), current->pid, ret);
		BUG();
	}
}

static void kd_spin_release_origin(struct kd_spin_request *request)
{
	BUG_ON(kd_spin_entry_release_origin(&request->ref));
	smp_store_release(&request->word->locked, 0);
	/* No per-CPU accesses after this may schedule. */
	BUG_ON(kd_spin_entry_end(&request->ref));
}

#ifdef KDLOCK_SELFTEST
static int kd_spin_shadow_selftest(void);
static int kd_spin_selftest_frame_begin(const struct kd_exec_frame *frame);
static void kd_spin_selftest_frame_end(int event,
				       const struct kd_exec_frame *frame,
				       int ret);
static void kd_spin_selftest_frames_report(void);
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

#define KD_SPIN_WAIT_STACK_SIZE 8192

struct shadow_stack {
	/*
	 * Locks acquired by the current CPU. Tracking them separately from the
	 * execution stack supports sequences such as acquire A, acquire B,
	 * release A, release B.
	 */
	uint64_t lock_addr[8];

	/*
	 * Used by the combiner to identify for which CPU is the critical section
	 * currently executing.
	 */
	uint32_t curr_cs_cpu;
	uint32_t prev_cs_cpu;
	/* Wrapper RSP scratch only; execution uses the combiner's task stack. */
	uint64_t local_shadow_stack_ptr;
	/* TCLock-style physical waiter stack, distinct from wrapper scratch.
	 * IRQs stay masked and the ticket pins the sole polling user to this CPU.
	 * Virtual waiters retain their executor stack for nested owner/ACK work. */
	void *wait_stack_top;
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
	unsigned long irq_flags;
};

static DEFINE_PER_CPU(struct kd_spin_node *, kd_spin_resume_nodes);

/* Queue slots can be recycled while native owners finish. Requests therefore
 * have their own bounded, boot-allocated pool; no allocation occurs in a CS. */
#define KD_SPIN_REQUEST_SLOTS (KD_EXEC_MAX_NESTING + MAX_NODES)
static DEFINE_PER_CPU(struct kd_spin_exec_request *, kd_spin_requests);

struct kd_spin_jit_context {
	struct kd_exec_frame *requester;
	unsigned int lock_depth;
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

/* Lock ledger, wrapper scratch and the separately allocated polling stack. */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct shadow_stack, local_shadow_stack);

#define _Q_LOCKED_PENDING_MASK (_Q_LOCKED_MASK_HL | _Q_PENDING_MASK_HL)
#define _Q_LOCKED_COMBINER_VAL 3
#define _Q_UNLOCKED_OOO_VAL 7 /* Lock released out of order. */
#define _Q_LOCKED_IRQ_VAL 15 /* Lock stolen by an IRQ context. */

static void kd_spin_diag_validate_lock_stack(const struct shadow_stack *ptr);
