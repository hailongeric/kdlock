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

/* Bound delegated bodies per physical hold; NUMA scan work has a separate
 * batch-local budget. A 1024-body cap amortizes hash working-set transfers
 * between combiners. This is a work bound, not a scheduler latency guarantee. */
#ifndef KDLOCK_SPIN_BATCH
#define KDLOCK_SPIN_BATCH 1024
#endif
#if KDLOCK_SPIN_BATCH < 1 || KDLOCK_SPIN_BATCH > 1024
#error "KDLOCK_SPIN_BATCH must be 1..1024"
#endif
static const unsigned int kd_combiner_batch_size = KDLOCK_SPIN_BATCH;
MODULE_INFO(spin_batch, __stringify(KDLOCK_SPIN_BATCH));
#ifdef NUMA_AWARE
MODULE_INFO(spin_numa, "1");
#else
MODULE_INFO(spin_numa, "0");
#endif

/* Fixed self-execution control for protocol comparisons. This changes only
 * fresh admission; unlock always follows the acquisition's ownership record. */
bool kd_spin_delegate __read_mostly = true;
EXPORT_SYMBOL_GPL(kd_spin_delegate);
module_param_named(spin_delegate, kd_spin_delegate, bool, 0400);
MODULE_PARM_DESC(spin_delegate, "Allow JIT delegation; false keeps KD self-execution");


static __always_inline int kd_spin_trylock(struct qspinlock *word);

/* Physical request state lives on the caller's stack, not a recyclable node
 * or the logical waiter's spin_origin (which can belong to an ancestor).
 * The entry pin keeps this request local; the KD word is passed through the
 * queue/batch, including early release and reclaim, without another map scan. */
struct kd_spin_request {
	struct kd_spin_ref ref;
	struct qspinlock *word;
};

static struct qspinlock *kd_spin_request_word(const struct kd_spin_ref *ref)
{
	kd_spinlock_t *word = kd_spin_entry_word(ref);

	BUG_ON(!word);
	return word;
}

/* Normal unlocks use their live ticket. An OOO ancestor can be represented
 * by shadow/frame state only; its direct word grants no ownership by itself. */
static struct kd_spin_request kd_spin_unlock_lookup(struct qspinlock *lock)
{
	struct kd_spin_request request = { 0 };

	if (kd_spin_entry_find((raw_spinlock_t *)lock, &request.ref))
		request.word = kd_spin_request_word(&request.ref);
	else
		request.word = lock;
	return request;
}

static void kd_spin_unlock_request(struct qspinlock *lock,
				   struct kd_spin_request *request);

static bool kd_spin_is_ooo(struct qspinlock *lock)
{
 return READ_ONCE(lock->locked) == 7;
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
	/* end() drops the ticket pin and may schedule; do not access CPU-local
	 * state after it returns. */
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
	/* Waiter totals live per CPU. Only identity and the disable latch remain
	 * shared; keep adjacent identities on separate 128-byte boundaries. */
	atomic_long_t addr __aligned(2 * L1_CACHE_BYTES);
	atomic_t jit_disabled;
};

/* Slots keep their identity for the module session. Only the disable latch
 * is mutable shared state; reporting folds these CPU-local counters. The two
 * waiter totals preserve final balance without a shared per-request RMW. */
struct kd_spin_diag_counts {
	u64 event[KD_SPIN_DIAG_EVENT_COUNT];
	int max_depth;
	u64 waiter_enter, waiter_exit;
};

struct kd_spin_diag_cpu {
	struct kd_spin_diag_counts slot[KD_SPIN_DIAG_SLOTS];
	u64 overflow;
	u64 invariant_failures;
	u64 batch_entries;
	u64 ww_jumps;
};

static struct kd_spin_diag_slot kd_spin_diag_slots[KD_SPIN_DIAG_SLOTS];
static struct kd_spin_diag_cpu __percpu *kd_spin_diag_cpu;

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

struct kd_spin_cpu_state {
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
	/* CPU-owned reservation depth; not part of any published queue node. */
	int node_count;
	/* TCLock-style physical waiter stack, separate from the logical frame.
	 * The ticket pins the sole polling user to this CPU; polling preserves
	 * the caller's IRQ state.
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
};

/* CPU lock ledger, node reservation depth and separately allocated polling stack. */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_spin_cpu_state, kd_spin_cpu);

#ifdef KD_SPIN_STATS
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_combiner_count);
DEFINE_PER_CPU_ALIGNED(uint64_t, ooo_unlocks);
#endif

/*
 * Used by all threads to add itself to the queue on the slowpath.
 * Keep each two-line node in its own aligned pair, apart from CPU-local
 * pointers that can change while another CPU reads the queue links.
 */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_spin_node,
				     kd_spin_nodes[MAX_NODES]) __aligned(2 * L1_CACHE_BYTES);

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
	unsigned long ip;
	unsigned long bp;
	unsigned int entry_abi;
};

static DEFINE_PER_CPU(struct kd_spin_node *, kd_spin_resume_nodes);

static DEFINE_PER_CPU(struct kd_spin_continuation_stack *, kd_spin_continuations);
/* A native root remains pinned to its CPU until all executor borrows retire. */
static DEFINE_PER_CPU(struct kd_spin_continuation *, kd_spin_native_root);

#ifdef KDLOCK_SELFTEST
static bool kd_spin_selftest_virtual_begin(
	struct qspinlock *lock, const struct kd_spin_ref *request,
	const struct kd_regs *regs, const struct kd_exec_frame *parent,
	struct kd_spin_continuation_stack **requests, int initial_preempt);
static void kd_spin_selftest_virtual_end(const struct kd_spin_ref *request,
					 const struct kd_regs *regs,
					 const struct kd_exec_frame *parent,
					 int result);
#endif

#define _Q_LOCKED_PENDING_MASK (_Q_LOCKED_MASK_HL | _Q_PENDING_MASK_HL)
#define _Q_LOCKED_COMBINER_VAL 3
#define _Q_UNLOCKED_OOO_VAL 7 /* Lock released out of order. */
#define _Q_LOCKED_IRQ_VAL 15 /* Lock stolen by an IRQ context. */

static void kd_spin_diag_validate_lock_stack(const struct kd_spin_cpu_state *ptr);
