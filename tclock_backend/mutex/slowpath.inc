/* SPDX-License-Identifier: GPL-2.0 */
/* Queued mutex acquisition and nested stack restoration; preserve exact saved context until handoff. */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
__komb_mutex_lock_slowpath(struct komb_mutex *lock,
			   register struct komb_mutex_node *curr_node)
{
	register struct komb_mutex_node *prev, *next;
	u8 prev_locked_val;
	int j;
	struct komb_mutex *parent_lock;

#ifdef NUMA_AWARE
	struct komb_mutex_node *prev_local_queue_head;
	struct komb_mutex_node *prev_local_queue_tail;
#endif

	prev = xchg(&lock->tail, curr_node);
	next = NULL;

	if (prev) {
		WRITE_ONCE(prev->next, curr_node);

		print_debug("Mutex waiter going to spin\n");
		smp_cond_load_relaxed_sleep(curr_node, &curr_node->locked,
					    VAL == 0);

		print_debug("Mutex spin completed\n");
		if (READ_ONCE(curr_node->completed) == KOMB_WAITER_PROCESSED) {
			print_debug("Mutex CS processed\n");
			for (j = 7; j >= 0; j--)
				if (tc_mutex_current()->komb_lock_addr[j])
					break;

			if (j >= 0) {
				parent_lock = tc_mutex_current()->komb_lock_addr[j];
#ifdef DEBUG_KOMB
				BUG_ON(parent_lock == lock);
#endif
				if (parent_lock->locked ==
				    _Q_UNLOCKED_OOO_VAL) {
					print_debug("Waiter unlocked OOO\n");
					return 1;
				}
			}

			prefetchw((void *)curr_node->rsp);
			prefetchw((void *)curr_node->rsp + 64);
			prefetchw((void *)curr_node->rsp + 128);
			prefetchw((void *)curr_node->rsp + 192);
			prefetchw((void *)curr_node->rsp + 256);
			prefetchw((void *)curr_node->rsp + 320);
			return 0;
		}
	}

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

	//Head of the queue. Run Combiner.

	struct task_struct *prev_curr_waiter_task =
		tc_mutex_current()->komb_curr_waiter_task;
	tc_mutex_current()->komb_curr_waiter_task = NULL;

#ifdef DEBUG_KOMB
	BUG_ON(tc_mutex_current()->komb_prev_waiter_task != NULL);
#endif

	prev_locked_val = lock->locked;
#ifdef DEBUG_KOMB
	BUG_ON(prev_locked_val >= _Q_LOCKED_COMBINER_VAL);
#endif

	lock->locked = _Q_LOCKED_COMBINER_VAL;

	struct task_struct *prev_task_struct_ptr = curr_node->task_struct_ptr;
	uint64_t prev_rsp = curr_node->rsp;
	curr_node->rsp = 0;
	uint64_t prev_counter_val = tc_mutex_current()->counter_val;
	tc_mutex_current()->counter_val = 0;

	struct task_struct *prev_next_waiter_task =
		tc_mutex_current()->komb_next_waiter_task;
	tc_mutex_current()->komb_next_waiter_task = NULL;

	uint64_t prev_stack_curr_ptr = tc_mutex_current()->komb_stack_curr_ptr;

#ifdef NUMA_AWARE
	prev_local_queue_head =
		(struct komb_mutex_node *)tc_mutex_current()->komb_local_queue_head;
	prev_local_queue_tail =
		(struct komb_mutex_node *)tc_mutex_current()->komb_local_queue_tail;

	tc_mutex_current()->komb_local_queue_head = NULL;
	tc_mutex_current()->komb_local_queue_tail = NULL;
#endif

	j = 7;
	for (j = 7; j >= 0; j--)
		if (tc_mutex_current()->komb_lock_addr[j])
			break;
	j += 1;
#ifdef DEBUG_KOMB
	BUG_ON(j >= 8 || j < 0);
#endif
	tc_mutex_current()->komb_lock_addr[j] = lock;

	run_combiner(lock, next);
#ifdef DEBUG_KOMB
	BUG_ON(tc_mutex_current()->komb_lock_addr[j] != lock);
#endif

	tc_mutex_current()->komb_lock_addr[j] = NULL;

	tc_mutex_current()->komb_next_waiter_task = prev_next_waiter_task;
	tc_mutex_current()->counter_val = prev_counter_val;

#ifdef NUMA_AWARE
	tc_mutex_current()->komb_local_queue_head = prev_local_queue_head;
	tc_mutex_current()->komb_local_queue_tail = prev_local_queue_tail;
#endif

	tc_mutex_current()->komb_stack_curr_ptr = prev_stack_curr_ptr;
	tc_mutex_current()->komb_curr_waiter_task = prev_curr_waiter_task;
	curr_node->rsp = prev_rsp;
	curr_node->task_struct_ptr = prev_task_struct_ptr;

	if (lock->locked == _Q_UNLOCKED_OOO_VAL) {
		if (prev_curr_waiter_task) {
			wake_up_waiter(
				tc_mutex_task(prev_curr_waiter_task)->komb_mutex_node);
			clear_locked_set_completed(
				tc_mutex_task(prev_curr_waiter_task)->komb_mutex_node);
		}
		tc_mutex_current()->komb_curr_waiter_task = NULL;
	}
	lock->locked = prev_locked_val;

release:
	return 0;
}
#pragma GCC pop_options

__attribute__((noipa)) noinline notrace static int
komb_mutex_lock_slowpath(struct komb_mutex *lock)
{
	struct komb_mutex_node *curr_node = get_komb_mutex_node(lock);

	curr_node->locked = true;
	curr_node->completed = KOMB_WAITER_UNPROCESSED;
	curr_node->next = NULL;
	//curr_node->socket_id = numa_node_id();
	curr_node->cpuid = smp_processor_id();
	curr_node->task_struct_ptr = current;
	curr_node->lock = lock;

	return __komb_mutex_lock_slowpath(lock, curr_node);
}
