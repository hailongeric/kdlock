/* SPDX-License-Identifier: GPL-2.0 */
/* Queued acquisition and nested combiner restoration; keep saved owner/stack state until handoff. */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
__komb_spin_lock_longjmp(struct qspinlock *lock, int tail,
			 register struct komb_node *curr_node)
{
	register struct komb_node *prev_node = NULL, *next_node = NULL;
	struct qspinlock *parent_lock;
	int old_tail, val, j;

	/*
	 * TODO: Make sure these variables are stored on the combiner stack
	 * so that they can be restored later.
	 * These variables are needed when there is a waiter or a combiner
	 * running within a combiner (For same or different lock).
	 */
	uint32_t prev_cs_cpu;
	bool prev_locked_val;
	uint64_t prev_rsp;
	uint64_t prev_counter_val;
	struct komb_node *prev_next_node_ptr = NULL;
#ifdef NUMA_AWARE
	struct komb_node *prev_local_queue_head;
	struct komb_node *prev_local_queue_tail;
#endif

	old_tail = xchg_tail(lock, tail);

	if (old_tail & _Q_TAIL_MASK) {
		prev_node = decode_tail(old_tail);

		prev_node->next = curr_node;

		int count __maybe_unused = 0;

		komb_cond_load_relaxed(&curr_node->locked, !(VAL));



		struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

		if (curr_node->completed) {
#ifdef ENABLE_IRQS_CHECK
			if (curr_node->irqs_disabled) {
				ptr->irqs_disabled = curr_node->irqs_disabled;
			}
#endif
			for (j = 7; j >= 0; j--)
				if (ptr->lock_addr[j] != 0)
					break;

			curr_node->count--;

			if (j >= 0) {
				parent_lock = (void *)(unsigned long)ptr->lock_addr[j];
#ifdef DEBUG_KOMB
				BUG_ON(parent_lock == lock);
#endif
				if (parent_lock->locked ==
				    _Q_UNLOCKED_OOO_VAL) {
					print_debug("Waiter unlocked OOO\n");
					return 1;
				}
			}

			prefetchw((void *)(unsigned long)(curr_node->rsp));
			prefetchw((void *)(unsigned long)(curr_node->rsp + 64));
			prefetchw((void *)(unsigned long)(curr_node->rsp + 128));
			prefetchw((void *)(unsigned long)(curr_node->rsp + 192));
			prefetchw((void *)(unsigned long)(curr_node->rsp + 256));
			prefetchw((void *)(unsigned long)(curr_node->rsp + 320));
			LOCK_START_TIMING_PER_CPU(unlock_stack_switch);
			return 0;
		}
	}

	/*
	 * we're at the head of the waitqueue, wait for the owner & pending to
	 * go away.
	 *
	 * *,x,y -> *,0,0
	 *
	 * this wait loop must use a load-acquire such that we match the
	 * store-release that clears the locked bit and create lock
	 * sequentiality; this is because the set_locked() function below
	 * does not imply a full barrier.
	 *
	 */

	val = atomic_cond_read_acquire(&lock->val,
				       !(VAL & _Q_LOCKED_PENDING_MASK));

	/*
	 * claim the lock:
	 *
	 * n,0,0 -> 0,0,1 : lock, uncontended
	 * *,*,0 -> *,*,1 : lock, contended
	 *
	 * If the queue head is the only one in the queue (lock value == tail)
	 * and nobody is pending, clear the tail code and grab the lock.
	 * Otherwise, we only need to grab the lock.
	 */

	if (((val & _Q_TAIL_MASK) == tail) &&
	    atomic_try_cmpxchg_relaxed(&lock->val, &val, _Q_LOCKED_VAL))
		goto release; /* No contention */

	/* Either somebody is queued behind us or _Q_PENDING_VAL is set */
	check_and_set_combiner(lock);

	/*
	 * contended path; wait for next if not observed yet, release.
	 */
	komb_cond_load_relaxed(&curr_node->next, (VAL));
	next_node = curr_node->next;
#ifdef DEBUG_KOMB
	BUG_ON(next_node == NULL);
#endif


	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	prev_cs_cpu = ptr->curr_cs_cpu;
	ptr->curr_cs_cpu = -1;

	ptr->irqs_disabled = false;

#ifdef DEBUG_KOMB
	BUG_ON(ptr->prev_cs_cpu != -1);
#endif
	/*
	 * curr_node at the head of the queue.
	 * Release the node and run_combiner.
	 */
	curr_node->count--;
	prev_locked_val = lock->locked;
#ifdef DEBUG_KOMB
	BUG_ON(prev_locked_val >= _Q_LOCKED_COMBINER_VAL);
#endif
	lock->locked = _Q_LOCKED_COMBINER_VAL;
	prev_rsp = curr_node->rsp;
	curr_node->rsp = 0;

	prev_counter_val = ptr->counter_val;
	ptr->counter_val = 0;

	prev_next_node_ptr = ptr->next_node_ptr;
	ptr->next_node_ptr = NULL;

#ifdef NUMA_AWARE
	prev_local_queue_head = ptr->local_queue_head;
	prev_local_queue_tail = ptr->local_queue_tail;

	ptr->local_queue_head = NULL;
	ptr->local_queue_tail = NULL;
#endif

	j = 7;
	for (j = 7; j >= 0; j--)
		if (ptr->lock_addr[j] != 0)
			break;
	j += 1;
#ifdef DEBUG_KOMB
	BUG_ON(j >= 8 || j < 0);
#endif
	ptr->lock_addr[j] = (unsigned long)lock;

	run_combiner(lock, next_node);

#ifdef DEBUG_KOMB
	BUG_ON(this_cpu_ptr(&local_shadow_stack)->lock_addr[j] != lock);
#endif

	ptr->lock_addr[j] = 0;

	ptr->next_node_ptr = prev_next_node_ptr;
	ptr->counter_val = prev_counter_val;

#ifdef NUMA_AWARE
	ptr->local_queue_head = prev_local_queue_head;
	ptr->local_queue_tail = prev_local_queue_tail;
#endif

	curr_node->rsp = prev_rsp;

	if (lock->locked == _Q_UNLOCKED_OOO_VAL) {
		if (prev_cs_cpu != -1) {
			print_debug("Waking up %d\n", prev_cs_cpu);
			clear_locked_set_completed(
				per_cpu_ptr(&komb_nodes[0], prev_cs_cpu));
		}
		ptr->curr_cs_cpu = -1;
	} else {
		ptr->curr_cs_cpu = prev_cs_cpu;
	}
	lock->locked = prev_locked_val;

	return 0;
release:
	/*
	 * release the node
	 */
	curr_node->count--;
	return 0;
}
#pragma GCC pop_options

__attribute__((noipa)) noinline notrace static int
__komb_spin_lock_slowpath(struct qspinlock *lock)
{
	struct komb_node *curr_node;
	int tail, idx;

	LOCK_END_TIMING_PER_CPU(lock_stack_switch);

	curr_node = this_cpu_ptr(&komb_nodes[0]);
	idx = curr_node->count++;
	tail = encode_tail(smp_processor_id(), idx);

	/*
	 * Initialize curr_node
	 */
	curr_node->locked = true;
	curr_node->completed = false;
	curr_node->next = NULL;
	curr_node->tail = tail;
	curr_node->socket_id = numa_node_id();
	curr_node->cpuid = smp_processor_id();
	curr_node->irqs_disabled = false;
	curr_node->lock = lock;
	curr_node->task_struct_ptr = current;

	return __komb_spin_lock_longjmp(lock, tail, curr_node);
}
