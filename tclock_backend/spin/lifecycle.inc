/* SPDX-License-Identifier: GPL-2.0 */
/* Per-CPU shadow-stack setup, rollback and release; callers must drain before freeing storage. */
/*
 * Public API
 */

int komb_init(void)
{
	int i, j;
	for_each_possible_cpu (i) {
		void *stack_ptr = vzalloc(SIZE_OF_SHADOW_STACK);
		struct shadow_stack *ptr = per_cpu_ptr(&local_shadow_stack, i);

		if (!stack_ptr) {
			komb_free();
			return -ENOMEM;
		}

		ptr->ptr = stack_ptr + SIZE_OF_SHADOW_STACK;
		for (j = 0; j < 8; j++)
			ptr->lock_addr[j] = 0;
		ptr->local_shadow_stack_ptr =
			(unsigned long)(stack_ptr + SIZE_OF_SHADOW_STACK - 8);
		ptr->curr_cs_cpu = -1;
		ptr->prev_cs_cpu = -1;
		ptr->counter_val = 0;
		ptr->next_node_ptr = NULL;
#ifdef NUMA_AWARE
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
#endif

		ptr->irqs_disabled = false;

#ifdef LOCK_MEASURE_TIME
		*per_cpu_ptr(&combiner_loop, i) = UINT64_MAX;
#endif
	}
	return 0;
}

void komb_free(void)
{
	int i;
	for_each_possible_cpu (i) {
		struct shadow_stack *ptr = per_cpu_ptr(&local_shadow_stack, i);
		if (ptr->ptr) {
			vfree(ptr->ptr - SIZE_OF_SHADOW_STACK);
			ptr->ptr = NULL;
		}
	}
}

void komb_spin_lock_init(struct qspinlock *lock)
{
	atomic_set(&lock->val, 0);
}
