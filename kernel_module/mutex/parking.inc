// SPDX-License-Identifier: GPL-2.0
/* Included by kd_mutex.c. Result publication permits packet/node reuse.
 * Only the separately allocated, provider-lifetime rcuwait object may be read
 * afterwards. A late wake of a reused wait slot is harmless and spurious. */

static __always_inline void kd_mutex_publish_result(struct kd_mutex_node *node,
                                                    bool completed)
{
	struct rcuwait *wait;

	if (!kd_mutex_blocking) {
		if (completed)
			WRITE_ONCE(node->completed, KD_MUTEX_WAITER_PROCESSED);
		smp_store_release(&node->locked, 0);
		return;
	}
	wait = node->wait;
	/* One aligned x86 store publishes completion and releases the poll byte.
	 * No queue packet field can be read again after this point. */
	smp_store_release(&node->result, completed ? KD_MUTEX_WAITER_PROCESSED : 0);
	/* Pair condition publication with set_current_state's full barrier:
	 * either the waiter sees its result or we see its rcuwait registration.
	 * The common bounded-spin completion needs neither a remote CAS nor a
	 * task-reference RMW. The cold kernel wake helper supplies RCU lifetime. */
	smp_mb();
	if (rcuwait_active(wait) && rcuwait_wake_up(wait))
		this_cpu_inc(kd_mutex_result_wakes);
}

static void kd_mutex_park_result(struct kd_mutex_node *node)
{
	struct rcuwait *wait = node->wait;

	prepare_to_rcuwait(wait);
	for (;;) {
		set_current_state(TASK_UNINTERRUPTIBLE);
		if (!smp_load_acquire(&node->locked))
			break;
		this_cpu_inc(kd_mutex_result_parks);
		preempt_enable();
		/* Completion wakes can be batched. A later translated body may
		 * poll data produced by an already completed caller without making
		 * a FULL service call. Recheck on the next tick even if that body
		 * has not returned to flush its predecessor's wake. This also
		 * bounds dependence on an executor delayed between publication
		 * and notification. The ordinary wake path can end this sleep
		 * sooner; keep the state set before the condition read above. */
		schedule_timeout(1);
		preempt_disable();
	}
	/* Clear registration before slot release. The acquisition's task ref
	 * remains held through completion; cache eviction frees it via RCU, so
	 * rcuwait_wake_up can finish even after this task drops its last ref. */
	finish_rcuwait(wait);
}

/* Common COMPLETE bodies can share the store->wake barrier. Keep only stable
 * wake-slot pointers, never packets/tasks. Flush before leaving the batch and
 * before any FULL/native service can sleep or wait for another caller. */
static void kd_mutex_flush_wakes(struct rcuwait **wake, unsigned int *count)
{
	unsigned int i, n = *count;

	if (!n)
		return;
	*count = 0;
	smp_mb();
	for (i = 0; i < n; i++)
		if (rcuwait_active(wake[i]) && rcuwait_wake_up(wake[i]))
			this_cpu_inc(kd_mutex_result_wakes);
}

static __always_inline void kd_mutex_defer_result(struct kd_mutex_node *node,
					struct rcuwait **wake, unsigned int *count)
{
	if (!kd_mutex_blocking) {
		kd_mutex_publish_result(node, true);
		return;
	}
	wake[(*count)++] = node->wait;
	smp_store_release(&node->result, KD_MUTEX_WAITER_PROCESSED);
	if (*count == 16)
		kd_mutex_flush_wakes(wake, count);
}

/* Poll a bounded number of times; honour scheduler pressure at short
 * intervals. A read-only completion during this phase needs no scheduler work.
 * Migration remains disabled by the enclosing acquisition. */
static bool kd_mutex_spin_ready(u8 *notification)
{
	unsigned int left = kd_mutex_spin_limit;

	while (smp_load_acquire(notification)) {
		if (!left || (!(left & 63) && need_resched()))
			return false;
		left--;
		cpu_relax();
	}
	return true;
}

static void kd_mutex_wait_result_blocking(struct kd_mutex_node *node)
{
	if (!kd_mutex_spin_ready(&node->locked))
		kd_mutex_park_result(node);
}

static void kd_mutex_wait_gate_blocking(struct kd_mutex *lock)
{
	if (kd_mutex_spin_ready(&lock->locked))
		return;
	this_cpu_inc(kd_mutex_gate_parks);
	preempt_enable();
	wait_event(lock->gate_wait, !smp_load_acquire(&lock->locked));
	preempt_disable();
}

static void kd_mutex_open_gate(struct kd_mutex *lock)
{
	smp_store_release(&lock->locked, 0);
	if (kd_mutex_blocking) {
		/* Pairs with prepare_to_wait's state barrier: either the head sees
		 * zero, or we see its list insertion. Never skip a required wake. */
		smp_mb();
		if (waitqueue_active(&lock->gate_wait))
			wake_up_all(&lock->gate_wait);
	}
}
