/* SPDX-License-Identifier: GPL-2.0 */
/* Real waiter-stack execution and deferred handoff; retain completion and parking/wakeup ordering. */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static void
execute_cs(struct komb_mutex *lock, struct komb_mutex_node *curr_node)
{
	void *incoming_rsp_ptr, *outgoing_rsp_ptr;
	struct komb_mutex_node *my_node, *next_node;

	WRITE_ONCE(tc_mutex_current()->komb_curr_waiter_task, curr_node->task_struct_ptr);
#ifdef DEBUG_KOMB
	BUG_ON(curr_node->cpuid == smp_processor_id());
#endif

	incoming_rsp_ptr = &(curr_node->rsp);
	outgoing_rsp_ptr = get_shadow_stack_ptr(lock);
#ifdef LOCK_MEASURE_TIME
	*this_cpu_ptr(&combiner_loop) = UINT64_MAX;
#endif
	/*
	 * Make the actual switch, the pushed return address is after this
	 * function call, which we will resume execution at using the switch
	 * in unlock.
	 */
	komb_context_switch(incoming_rsp_ptr, outgoing_rsp_ptr);

#ifdef DEBUG_KOMB
	BUG_ON(tc_mutex_current()->komb_stack_base_ptr - (tc_mutex_current()->komb_stack_curr_ptr) >
	       SIZE_OF_SHADOW_STACK);
#endif

	if (lock->locked == _Q_UNLOCKED_OOO_VAL) {
		print_debug("Combiner got control back OOO unlock\n");

#ifdef KOMB_STATS
		this_cpu_add(ooo_waiter_combined, tc_mutex_current()->counter_val);
		this_cpu_inc(ooo_combiner_count);
#endif

#ifdef DEBUG_KOMB
		BUG_ON(tc_mutex_current()->komb_curr_waiter_task == NULL);
#endif

		curr_node =
			tc_mutex_task(tc_mutex_current()->komb_curr_waiter_task)->komb_mutex_node;
		my_node = tc_mutex_current()->komb_mutex_node;

		if (curr_node) {
			curr_node->rsp = my_node->rsp;
			wake_up_waiter(curr_node);
			clear_locked_set_completed(curr_node);
#ifdef DEBUG_KOMB
			BUG_ON(tc_mutex_current()->komb_prev_waiter_task != NULL);
#endif
		}
		tc_mutex_current()->komb_prev_waiter_task = NULL;
		tc_mutex_current()->komb_curr_waiter_task = NULL;
		lock->locked = _Q_LOCKED_COMBINER_VAL;

		next_node = NULL;
		if (tc_mutex_current()->komb_next_waiter_task)
			next_node = tc_mutex_task(tc_mutex_current()->komb_next_waiter_task)->komb_mutex_node;

		if (next_node && next_node->next) {
			execute_cs(lock, next_node);
		}
	}
}
#pragma GCC pop_options

#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static void
run_combiner(struct komb_mutex *lock, struct komb_mutex_node *curr_node)
{
#ifdef DEBUG_KOMB
	BUG_ON(curr_node == NULL);
#endif

#ifdef NUMA_AWARE
	struct komb_mutex_node **local_head, **local_tail;
#endif

	struct komb_mutex_node *next_node = curr_node->next;

	if (next_node == NULL) {
		set_locked(lock);

		/*
		 * Make this node spin on the locked variable and then it will
		 * become the combiner.
		 */

		print_debug("mutex combiner only one in the queue. Passing lock to %d\n", curr_node->cpuid);
		wake_up_waiter(curr_node);
		WRITE_ONCE(curr_node->locked, 0);
		return;
	}

	WRITE_ONCE(lock->combiner_task, current);


	tc_mutex_current()->counter_val = 0;

	print_debug("mutex Combiner %d giving control to %d\n", smp_processor_id(),
		    curr_node->cpuid);

	execute_cs(lock, curr_node);

	/* One observation per returned batch; no per-body payload counter. */
	tc_mutex_current()->delegated += tc_mutex_current()->counter_val + 1;
	tc_mutex_current()->batches++;

	print_debug(
		"mutex Combiner got the control back: %d counter: %d last_waiter: %d\n",
		smp_processor_id(), tc_mutex_current()->counter_val,
		tc_mutex_current()->komb_curr_waiter_task);

#ifdef KOMB_STATS
	this_cpu_add(waiter_combined, tc_mutex_current()->counter_val);
	this_cpu_inc(combiner_count);
#endif

	if (tc_mutex_current()->komb_prev_waiter_task) {
		struct komb_mutex_node *prev_node =
			tc_mutex_task(tc_mutex_current()->komb_prev_waiter_task)->komb_mutex_node;
		wake_up_waiter(prev_node);
		clear_locked_set_completed(prev_node);
		tc_mutex_current()->komb_prev_waiter_task = NULL;
	}

	next_node = NULL;
	if (tc_mutex_current()->komb_next_waiter_task) {
		next_node =
			tc_mutex_task(tc_mutex_current()->komb_next_waiter_task)->komb_mutex_node;
		tc_mutex_current()->komb_next_waiter_task = NULL;
	}

	WRITE_ONCE(lock->combiner_task, NULL);

#ifdef NUMA_AWARE
	local_head =
		(struct komb_mutex_node **)(&tc_mutex_current()->komb_local_queue_head);
	local_tail =
		(struct komb_mutex_node **)(&tc_mutex_current()->komb_local_queue_tail);

	if (*local_head) {
		(*local_tail)->next = next_node;
		next_node = *local_head;
		*local_head = NULL;
		*local_tail = NULL;
	}
#endif

	set_locked(lock);

#ifdef DEBUG_KOMB
	BUG_ON(next_node == NULL);
#endif

	/*
	 * Make this node spin on the locked variabe and then it will
	 * become the combiner.
	 */
	print_debug("mutex Passing lock to next node %d\n", next_node->cpuid);
	wake_up_waiter(next_node);
	WRITE_ONCE(next_node->locked, 0);
}
#pragma GCC pop_options
