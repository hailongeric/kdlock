// SPDX-License-Identifier: GPL-2.0
#include <linux/percpu.h>
#include <linux/sched.h>
#include "kd_owned_mutex_internal.h"

/* Private port of the captured Linux 6.1.159 OSQ. See linux-source.json.
 * Names and the node type are private; the queue/cancellation ordering is
 * unchanged. No Linux osq_lock/osq_unlock symbol is imported. */
struct kd_owned_osq_node {
	struct kd_owned_osq_node *next, *prev;
	int locked;
	int cpu;
	/* Advisory membership only; never grants ownership or permits reuse. */
	struct optimistic_spin_queue *queue;
	unsigned int probes;
};

/*
 * An MCS like lock especially tailored for optimistic spinning for sleeping
 * lock implementations (mutex, rwsem, etc).
 *
 * Using a single mcs node per CPU is safe because sleeping locks should not be
 * called from interrupt context and we have preemption disabled while
 * spinning.
 */
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_owned_osq_node, kd_owned_osq_nodes);

/*
 * We use the value 0 to represent "no CPU", thus the encoded value
 * will be the CPU number incremented by 1.
 */
static inline int kd_owned_osq_encode_cpu(int cpu_nr)
{
	return cpu_nr + 1;
}

static inline int kd_owned_osq_node_cpu(struct kd_owned_osq_node *node)
{
	return node->cpu - 1;
}

static inline struct kd_owned_osq_node *kd_owned_osq_decode_cpu(int encoded_cpu_val)
{
	int cpu_nr = encoded_cpu_val - 1;

	return per_cpu_ptr(&kd_owned_osq_nodes, cpu_nr);
}

/*
 * Seven distinct existing spinners plus this arriving caller establish at
 * least eight contenders without double-counting an owner still leaving OSQ.
 * Nodes have provider lifetime, so a bounded, lockless walk is safe even when
 * cancellation changes the links.
 * Membership and duplicate checks make stale/cross-lock chains inconclusive.
 * This is only an admission hint: it must never drive queue unlinking, owner
 * selection, object retirement or any other exact lifetime decision.
 */
bool kd_owned_osq_crowded(struct optimistic_spin_queue *lock)
{
	struct kd_owned_osq_node *node, *seen[7];
	unsigned int count, i;
	int tail;

	lockdep_assert_preemption_disabled();
	/* Avoid walking remote cache lines on every short-cohort acquisition. */
	if (++this_cpu_ptr(&kd_owned_osq_nodes)->probes & 63)
		return false;
	tail = atomic_read(&lock->tail);
	if (!tail)
		return false;
	node = kd_owned_osq_decode_cpu(tail);
	for (count = 0; count < 7; count++) {
		if (!node || READ_ONCE(node->queue) != lock)
			return false;
		for (i = 0; i < count; i++)
			if (seen[i] == node)
				return false;
		seen[count] = node;
		if (count == 6)
			return true;
		if (READ_ONCE(node->locked))
			return false;
		node = READ_ONCE(node->prev);
	}
	return false;
}

/*
 * Get a stable @node->next pointer, either for unlock() or unqueue() purposes.
 * Can return NULL in case we were the last queued and we updated @lock instead.
 */
static inline struct kd_owned_osq_node *
kd_owned_osq_wait_next(struct optimistic_spin_queue *lock,
	      struct kd_owned_osq_node *node,
	      struct kd_owned_osq_node *prev)
{
	struct kd_owned_osq_node *next = NULL;
	int curr = kd_owned_osq_encode_cpu(smp_processor_id());
	int old;

	/*
	 * If there is a prev node in queue, then the 'old' value will be
	 * the prev node's CPU #, else it's set to OSQ_UNLOCKED_VAL since if
	 * we're currently last in queue, then the queue will then become empty.
	 */
	old = prev ? prev->cpu : OSQ_UNLOCKED_VAL;

	for (;;) {
		if (atomic_read(&lock->tail) == curr &&
		    atomic_cmpxchg_acquire(&lock->tail, curr, old) == curr) {
			/*
			 * We were the last queued, we moved @lock back. @prev
			 * will now observe @lock and will complete its
			 * unlock()/unqueue().
			 */
			break;
		}

		/*
		 * We must xchg() the @node->next value, because if we were to
		 * leave it in, a concurrent unlock()/unqueue() from
		 * @node->next might complete Step-A and think its @prev is
		 * still valid.
		 *
		 * If the concurrent unlock()/unqueue() wins the race, we'll
		 * wait for either @lock to point to us, through its Step-B, or
		 * wait for a new @node->next from its Step-C.
		 */
		if (node->next) {
			next = xchg(&node->next, NULL);
			if (next)
				break;
		}

		cpu_relax();
	}

	return next;
}

/* A preflight may become the immediate head, but must not join and wait on
 * an existing OSQ. Publish initialized node fields with both acquire/release
 * ordering, as the full OSQ entry does. A successor may join after our CAS. */
bool kd_owned_osq_trylock(struct optimistic_spin_queue *lock)
{
	struct kd_owned_osq_node *node;
	int curr;

	lockdep_assert_preemption_disabled();
	if (atomic_read(&lock->tail) != OSQ_UNLOCKED_VAL)
		return false;
	node = this_cpu_ptr(&kd_owned_osq_nodes);
	curr = kd_owned_osq_encode_cpu(smp_processor_id());
	node->locked = 0;
	node->next = NULL;
	node->prev = NULL;
	node->cpu = curr;
	WRITE_ONCE(node->queue, lock);
	if (atomic_cmpxchg(&lock->tail, OSQ_UNLOCKED_VAL, curr) == OSQ_UNLOCKED_VAL)
		return true;
	WRITE_ONCE(node->queue, NULL);
	return false;
}

/* Count deliberate queued observations only. Stabilizing and unlinking an
 * admitted node must finish even after this budget expires. */
static __always_inline bool kd_owned_osq_budget_expired(unsigned int *remaining)
{
	if (!remaining)
		return false;
	if (!*remaining)
		return true;
	return !--*remaining;
}

static __always_inline bool
kd_owned_osq_lock_common(struct optimistic_spin_queue *lock, unsigned int *remaining)
{
	struct kd_owned_osq_node *node = this_cpu_ptr(&kd_owned_osq_nodes);
	struct kd_owned_osq_node *prev, *next;
	int curr = kd_owned_osq_encode_cpu(smp_processor_id());
	int old;

	node->locked = 0;
	node->next = NULL;
	node->prev = NULL;
	node->cpu = curr;
	WRITE_ONCE(node->queue, lock);

	/*
	 * We need both ACQUIRE (pairs with corresponding RELEASE in
	 * unlock() uncontended, or fastpath) and RELEASE (to publish
	 * the node fields we just initialised) semantics when updating
	 * the lock tail.
	 */
	old = atomic_xchg(&lock->tail, curr);
	if (old == OSQ_UNLOCKED_VAL)
		return true;

	prev = kd_owned_osq_decode_cpu(old);
	node->prev = prev;

	/*
	 * kd_owned_osq_lock()			unqueue
	 *
	 * node->prev = prev		kd_owned_osq_wait_next()
	 * WMB				MB
	 * prev->next = node		next->prev = prev // unqueue-C
	 *
	 * Here 'node->prev' and 'next->prev' are the same variable and we need
	 * to ensure these stores happen in-order to avoid corrupting the list.
	 */
	smp_wmb();

	WRITE_ONCE(prev->next, node);

	/*
	 * Normally @prev is untouchable after the above store; because at that
	 * moment unlock can proceed and wipe the node element from stack.
	 *
	 * However, since our nodes are static per-cpu storage, we're
	 * guaranteed their existence -- this allows us to apply
	 * cmpxchg in an attempt to undo our queueing.
	 */

	/*
	 * Wait to acquire the lock or cancellation. Note that need_resched()
	 * will come with an IPI, which will wake smp_cond_load_relaxed() if it
	 * is implemented with a monitor-wait. vcpu_is_preempted() relies on
	 * polling, be careful.
	 */
	if (smp_cond_load_relaxed(&node->locked,
				  kd_owned_osq_budget_expired(remaining) || VAL ||
				  need_resched() ||
				  vcpu_is_preempted(kd_owned_osq_node_cpu(node->prev))))
		return true;

	/* unqueue */
	/*
	 * Step - A  -- stabilize @prev
	 *
	 * Undo our @prev->next assignment; this will make @prev's
	 * unlock()/unqueue() wait for a next pointer since @lock points to us
	 * (or later).
	 */

	for (;;) {
		/*
		 * cpu_relax() below implies a compiler barrier which would
		 * prevent this comparison being optimized away.
		 */
		if (data_race(prev->next) == node &&
		    cmpxchg(&prev->next, node, NULL) == node)
			break;

		/*
		 * We can only fail the cmpxchg() racing against an unlock(),
		 * in which case we should observe @node->locked becoming
		 * true.
		 */
		if (smp_load_acquire(&node->locked))
			return true;

		cpu_relax();

		/*
		 * Or we race against a concurrent unqueue()'s step-B, in which
		 * case its step-C will write us a new @node->prev pointer.
		 */
		prev = READ_ONCE(node->prev);
	}

	/*
	 * Step - B -- stabilize @next
	 *
	 * Similar to unlock(), wait for @node->next or move @lock from @node
	 * back to @prev.
	 */

	next = kd_owned_osq_wait_next(lock, node, prev);
	if (!next)
		return false;

	/*
	 * Step - C -- unlink
	 *
	 * @prev is stable because its still waiting for a new @prev->next
	 * pointer, @next is stable because our @node->next pointer is NULL and
	 * it will wait in Step-A.
	 */

	WRITE_ONCE(next->prev, prev);
	WRITE_ONCE(prev->next, next);

	return false;
}

bool kd_owned_osq_lock(struct optimistic_spin_queue *lock)
{
	bool acquired = kd_owned_osq_lock_common(lock, NULL);

	if (!acquired)
		WRITE_ONCE(this_cpu_ptr(&kd_owned_osq_nodes)->queue, NULL);
	return acquired;
}

bool kd_owned_osq_lock_bounded(struct optimistic_spin_queue *lock,
			     unsigned int *remaining)
{
	bool acquired;

	lockdep_assert_preemption_disabled();
	if (!remaining || !*remaining)
		return false;
	/* A predecessor grant racing expiration, including Step A, returns true.
	 * The caller then owns OSQ and must unlock even if remaining reached zero.
	 * Neither cancellation nor unlock has a wall-clock or iteration bound. */
	acquired = kd_owned_osq_lock_common(lock, remaining);
	if (!acquired)
		WRITE_ONCE(this_cpu_ptr(&kd_owned_osq_nodes)->queue, NULL);
	return acquired;
}

void kd_owned_osq_unlock(struct optimistic_spin_queue *lock)
{
	struct kd_owned_osq_node *node, *next;
	int curr = kd_owned_osq_encode_cpu(smp_processor_id());

	/* Stop advertising membership before the real, unchanged handoff. */
	WRITE_ONCE(this_cpu_ptr(&kd_owned_osq_nodes)->queue, NULL);
	/*
	 * Fast path for the uncontended case.
	 */
	if (likely(atomic_cmpxchg_release(&lock->tail, curr,
					  OSQ_UNLOCKED_VAL) == curr))
		return;

	/*
	 * Second most likely case.
	 */
	node = this_cpu_ptr(&kd_owned_osq_nodes);
	next = xchg(&node->next, NULL);
	if (next) {
		WRITE_ONCE(next->locked, 1);
		return;
	}

	next = kd_owned_osq_wait_next(lock, node, NULL);
	if (next)
		WRITE_ONCE(next->locked, 1);
}
