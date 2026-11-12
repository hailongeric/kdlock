/* SPDX-License-Identifier: GPL-2.0 */
/* Native body stack switches and batch handoff; preserve WWJUMP state and deferred remote links. */
#pragma GCC push_options
#pragma GCC optimize("O3")

__attribute__((noipa)) noinline notrace static void
execute_cs(struct qspinlock *lock, struct komb_node *curr_node)
{
	void *incoming_rsp_ptr, *outgoing_rsp_ptr;
	struct komb_node *next_node = NULL;

	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	ptr->curr_cs_cpu = curr_node->cpuid;

#ifdef DEBUG_KOMB
	BUG_ON(curr_node->cpuid == smp_processor_id());
	if ((ptr->ptr - (ptr->local_shadow_stack_ptr)) > SIZE_OF_SHADOW_STACK) {
		printk(KERN_ALERT "%d %px %px\n", smp_processor_id(), ptr->ptr,
		       ptr->local_shadow_stack_ptr);
		BUG_ON(true);
	}
#endif

	incoming_rsp_ptr = &(curr_node->rsp);
	outgoing_rsp_ptr = &(ptr->local_shadow_stack_ptr);

#ifdef LOCK_MEASURE_TIME
	*this_cpu_ptr(&combiner_loop) = UINT64_MAX;
#endif

	/*
	 * Make the actual switch, the pushed return address is after this
	 * function call, which we will resume execution at using the switch
	 * in unlock.
	 */
#ifdef DEBUG_KOMB
#ifdef ENABLE_IRQS_CHECK
	BUG_ON(irqs_disabled());
#endif

	BUG_ON(*(uint64_t *)incoming_rsp_ptr == NULL);
	BUG_ON(*(uint64_t *)outgoing_rsp_ptr == NULL);
#endif
	komb_context_switch(incoming_rsp_ptr, outgoing_rsp_ptr);

#ifdef DEBUG_KOMB
	if ((ptr->ptr - (ptr->local_shadow_stack_ptr)) > SIZE_OF_SHADOW_STACK) {
		printk(KERN_ALERT "%d %px %px\n", smp_processor_id(), ptr->ptr,
		       ptr->local_shadow_stack_ptr);
		BUG_ON(true);
	}
	BUG_ON(ptr->ptr - (ptr->local_shadow_stack_ptr) > SIZE_OF_SHADOW_STACK);
#endif

	if (lock->locked == _Q_UNLOCKED_OOO_VAL) {
		print_debug("Combiner got control back OOO unlock\n");

#ifdef KOMB_STATS
		this_cpu_add(ooo_waiter_combined, ptr->counter_val);
		this_cpu_inc(ooo_combiner_count);
#endif

		if (ptr->curr_cs_cpu != -1) {
			print_debug("OOO waking up %d\n", ptr->curr_cs_cpu);
			curr_node =
				per_cpu_ptr(&komb_nodes[0], ptr->curr_cs_cpu);
			curr_node->rsp = this_cpu_ptr(&komb_nodes[0])->rsp;
			clear_locked_set_completed(curr_node);
#ifdef DEBUG_KOMB
			BUG_ON(ptr->prev_cs_cpu != -1);
#endif
		}
		ptr->prev_cs_cpu = -1;
		ptr->curr_cs_cpu = -1;
		lock->locked = _Q_LOCKED_COMBINER_VAL;

		next_node = ptr->next_node_ptr;

		if (next_node != NULL && next_node->next != NULL &&
		    !check_irq_node(next_node) &&
		    !check_irq_node(next_node->next)) {
			execute_cs(lock, ptr->next_node_ptr);
		}
	}
}
#pragma GCC pop_options

#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static void
run_combiner(struct qspinlock *lock, struct komb_node *curr_node)
{
#ifdef DEBUG_KOMB
	BUG_ON(curr_node == NULL);
#endif
	struct komb_node *next_node = curr_node->next;
	int counter __maybe_unused = 0;

	if (next_node == NULL || check_irq_node(curr_node) ||
	    check_irq_node(next_node)) {
		set_locked(lock);
		/*
		 * Make this node spin on the locked variable and then it will
		 * become the combiner.
		 */
		curr_node->locked = false;
		smp_mb();
		return;
	}

	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

#ifndef WWJUMP
	while (curr_node) {
		counter++;

		next_node = get_next_node(curr_node);

		execute_cs(lock, curr_node);

		clear_locked_set_completed(curr_node);

		if (next_node == NULL || next_node->next == NULL ||
		    counter >= komb_batch_size)
			break;

		curr_node = next_node;
	}
#else
	ptr->counter_val = 0;

	print_debug("Combiner %d giving control to %d\n", smp_processor_id(),
		    curr_node->cpuid);

	execute_cs(lock, curr_node);

	print_debug(
		"Combiner got the control back: %d counter: %d last_waiter: %d\n",
		smp_processor_id(), ptr->counter_val, ptr->curr_cs_cpu);

#ifdef KOMB_STATS
	this_cpu_add(waiter_combined, ptr->counter_val);
	this_cpu_inc(combiner_count);
#endif

	if (ptr->prev_cs_cpu != -1) {
		clear_locked_set_completed(
			per_cpu_ptr(&komb_nodes[0], ptr->prev_cs_cpu));
		ptr->prev_cs_cpu = -1;
	}

	next_node = ptr->next_node_ptr;
#endif

#ifdef NUMA_AWARE
	if (ptr->local_queue_head != NULL) {
		ptr->local_queue_tail->next = next_node;
		next_node = ptr->local_queue_head;
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
	}
#endif

	print_debug("After combiner %d, next node: %d\n", smp_processor_id(),
		    next_node->cpuid);

#ifdef DEBUG_KOMB
	BUG_ON(next_node == NULL);
#endif

	set_locked(lock);

#ifdef WWJUMP
	ptr->curr_cs_cpu = -1;
#endif
	/*
	 * Make this node spin on the locked variable and then it will become
	 * the combiner.
	 */
	next_node->locked = false;
}
#pragma GCC pop_options
