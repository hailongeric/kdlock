// SPDX-License-Identifier: GPL-2.0
#include <linux/percpu.h>
#include <linux/sched.h>
#include <linux/bug.h>
#include "kd_mutex_local.h"

/*
 * An MCS like lock especially tailored for optimistic spinning for sleeping
 * lock implementations (mutex, rwsem, etc).
 *
 * Nodes share the preallocated delegation pool but have independent links.
 * Every member stays preemption-disabled until this abortable queue has
 * finished all accesses. The caller owns or explicitly borrows its reservation.
 */
static inline int node_cpu(struct kd_mutex_osq_node *node)
{
	return (node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1;
}

static inline struct kd_mutex_osq_node *decode_tail(u32 tail)
{
	int cpu = (tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1;
	int slot = (tail >> KD_MUTEX_TAIL_IDX_OFFSET) & KD_MUTEX_TAIL_IDX_MASK;

	return &per_cpu_ptr(&kd_mutex_nodes[slot], cpu)->osq;
}

/* IDLE is exact retirement evidence for the reservation owner. Publish it
 * only after unlink/handoff has finished; it is never an acquisition grant. */
static void osq_retire(struct kd_mutex_osq_node *node)
{
	WRITE_ONCE(node->next, NULL);
	WRITE_ONCE(node->prev, NULL);
	WRITE_ONCE(node->locked, KD_MUTEX_OSQ_IDLE);
}

/*
 * Get a stable @node->next pointer, either for unlock() or unqueue() purposes.
 * Can return NULL in case we were the last queued and we updated @lock instead.
 */
static inline struct kd_mutex_osq_node *
osq_wait_next(struct optimistic_spin_queue *lock,
	      struct kd_mutex_osq_node *node,
	      struct kd_mutex_osq_node *prev)
{
	struct kd_mutex_osq_node *next = NULL;
	int curr = node->tail;
	int old;

	/*
	 * If there is a prev node in queue, then the 'old' value will be
	 * the prev node's encoded CPU/slot, else it's OSQ_UNLOCKED_VAL since if
	 * we're currently last in queue, then the queue will then become empty.
	 */
	old = prev ? prev->tail : OSQ_UNLOCKED_VAL;

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

bool kd_mutex_osq_lock(struct optimistic_spin_queue *lock,
		       struct kd_mutex_osq_node *node)
{
	struct kd_mutex_osq_node *prev, *next;
	int curr = node->tail;
	int old;

	BUG_ON(node_cpu(node) != smp_processor_id());
	BUG_ON(READ_ONCE(node->locked) != KD_MUTEX_OSQ_IDLE);
	node->locked = KD_MUTEX_OSQ_WAITING;
	node->next = NULL;
	node->prev = NULL;

	/*
	 * We need both ACQUIRE (pairs with corresponding RELEASE in
	 * unlock() uncontended, or fastpath) and RELEASE (to publish
	 * the node fields we just initialised) semantics when updating
	 * the lock tail.
	 */
	old = atomic_xchg(&lock->tail, curr);
	if (old == OSQ_UNLOCKED_VAL)
		return true;

	prev = decode_tail(old);
	node->prev = prev;

	/*
	 * osq_lock()			unqueue
	 *
	 * node->prev = prev		osq_wait_next()
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
				  VAL == KD_MUTEX_OSQ_GRANTED || need_resched() ||
				  vcpu_is_preempted(node_cpu(node->prev))) ==
	    KD_MUTEX_OSQ_GRANTED)
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
		if (smp_load_acquire(&node->locked) == KD_MUTEX_OSQ_GRANTED)
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

	next = osq_wait_next(lock, node, prev);
	if (!next) {
		osq_retire(node);
		return false;
	}

	/*
	 * Step - C -- unlink
	 *
	 * @prev is stable because its still waiting for a new @prev->next
	 * pointer, @next is stable because our @node->next pointer is NULL and
	 * it will wait in Step-A.
	 */

	WRITE_ONCE(next->prev, prev);
	WRITE_ONCE(prev->next, next);

	osq_retire(node);
	return false;
}

void kd_mutex_osq_unlock(struct optimistic_spin_queue *lock,
			 struct kd_mutex_osq_node *node)
{
	struct kd_mutex_osq_node *next;
	int curr = node->tail;

	BUG_ON(READ_ONCE(node->locked) == KD_MUTEX_OSQ_IDLE);

	/*
	 * Fast path for the uncontended case.
	 */
	if (likely(atomic_cmpxchg_release(&lock->tail, curr,
					  OSQ_UNLOCKED_VAL) == curr)) {
		osq_retire(node);
		return;
	}

	/*
	 * Second most likely case.
	 */
	next = xchg(&node->next, NULL);
	if (next) {
		WRITE_ONCE(next->locked, KD_MUTEX_OSQ_GRANTED);
		osq_retire(node);
		return;
	}

	next = osq_wait_next(lock, node, NULL);
	if (next)
		WRITE_ONCE(next->locked, KD_MUTEX_OSQ_GRANTED);
	osq_retire(node);
}
