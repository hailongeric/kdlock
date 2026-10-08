/* SPDX-License-Identifier: GPL-2.0 */
/* WWJUMP unlock continuation and release; previous waiter notification follows the upstream protocol. */
__attribute__((noipa)) noinline notrace void
komb_mutex_unlock(struct komb_mutex *lock)
{
	void *incoming_rsp_ptr, *outgoing_rsp_ptr;
	struct komb_mutex_node *curr_node;

	int j, max_idx, my_idx;

	struct komb_mutex *temp_lock_addr;

	j = 0;
	max_idx = -1;
	my_idx = -1;

	for (j = 0; j < 8; j++) {
		temp_lock_addr = tc_mutex_current()->komb_lock_addr[j];
		if (temp_lock_addr)
			max_idx = j;
		if (temp_lock_addr == lock)
			my_idx = j;
		if (temp_lock_addr == NULL)
			break;
	}

	if (my_idx == -1) {
		if (lock->locked == _Q_LOCKED_VAL)
			lock->locked = false;
		else if (lock->locked == _Q_LOCKED_COMBINER_VAL) {
#ifdef KOMB_STATS
			this_cpu_inc(ooo_unlocks);
#endif

			lock->locked = _Q_UNLOCKED_OOO_VAL;
			print_debug("OOO unlock\n");
		} else
			BUG_ON(true);
		return;
	}

	LOCK_END_TIMING_PER_CPU_DISABLE(combiner_loop);

	LOCK_START_TIMING_PER_CPU_DISABLE(combiner_loop);

#ifdef DEBUG_KOMB
	if (lock->locked != _Q_LOCKED_COMBINER_VAL)
		BUG_ON(true);

	BUG_ON(tc_mutex_current()->komb_curr_waiter_task == NULL);

	if (max_idx < 0) {
		BUG_ON(true);
	}

#endif
	if (my_idx < max_idx) {
#ifdef KOMB_STATS
		this_cpu_inc(ooo_unlocks);
#endif
		lock->locked = _Q_UNLOCKED_OOO_VAL;
		return;
	}

	curr_node = tc_mutex_task(tc_mutex_current()->komb_curr_waiter_task)->komb_mutex_node;

	struct komb_mutex_node *next_node = NULL;
	if (tc_mutex_current()->komb_next_waiter_task)
		next_node =
			tc_mutex_task(tc_mutex_current()->komb_next_waiter_task)->komb_mutex_node;

	uint64_t counter = tc_mutex_current()->counter_val;

#ifdef DEBUG_KOMB
	BUG_ON(lock->combiner_task != current);
#endif

	if (next_node == NULL || next_node->next == NULL ||
	    counter >= komb_batch_size) {
		incoming_rsp_ptr = &(tc_mutex_current()->komb_stack_curr_ptr);
		tc_mutex_current()->komb_prev_waiter_task = tc_mutex_current()->komb_curr_waiter_task;
		tc_mutex_current()->komb_curr_waiter_task = NULL;

	} else {
		tc_mutex_current()->komb_prev_waiter_task = tc_mutex_current()->komb_curr_waiter_task;
		tc_mutex_current()->komb_curr_waiter_task = tc_mutex_current()->komb_next_waiter_task;
		incoming_rsp_ptr = &(next_node->rsp);
		tc_mutex_current()->counter_val = counter + 1;
		print_debug("Jumping to the next waiter: %d\n",
			    next_node->cpuid);
	}

	/*
	 * Komb node still active here, because cpu (from_cpuid) still spinning.
	 */
	outgoing_rsp_ptr = &(curr_node->rsp);

	preempt_disable();
	komb_context_switch(incoming_rsp_ptr, outgoing_rsp_ptr);
	preempt_enable();
	return;
}

EXPORT_SYMBOL_GPL(komb_mutex_init);
EXPORT_SYMBOL_GPL(komb_mutex_lock);
EXPORT_SYMBOL_GPL(komb_mutex_unlock);
