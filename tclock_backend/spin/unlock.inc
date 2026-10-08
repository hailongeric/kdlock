/* SPDX-License-Identifier: GPL-2.0 */
/* Owner lookup, WWJUMP continuation and release; context-idle observation does not grant ownership. */
struct task_struct *komb_get_current(spinlock_t *lock)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	int j, my_idx __maybe_unused;

	j = 0;
	my_idx = -1;

	for (j = 0; j < 8; j++) {
		if (ptr->lock_addr[j] == (unsigned long)lock) {
#ifdef DEBUG_KOMB
			BUG_ON(ptr->curr_cs_cpu < 0);
#endif
			return per_cpu_ptr(&komb_nodes[0], ptr->curr_cs_cpu)
				->task_struct_ptr;
		}
	}

	return current;
}

void komb_set_current_state(spinlock_t *lock, unsigned int state)
{
	WRITE_ONCE(komb_get_current(lock)->__state, state);
	smp_mb();
}

/*
 * No IPA is even more relevant here, because even if assembly is removed,
 * compiler shouldn't assume which caller-saved registers are in use inside
 * the function. When we jump from the spin loop to the return address after
 * the unlock function, we have caller-saved registers that are completely
 * inconsistent, because we only restored the callee-saved registers.
 */
__attribute__((noipa)) noinline notrace void
komb_spin_unlock(struct qspinlock *lock)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	int from_cpuid = ptr->curr_cs_cpu;
	void *incoming_rsp_ptr, *outgoing_rsp_ptr;

	int j, max_idx, my_idx;

	uint64_t temp_lock_addr;

	j = 0;
	max_idx = -1;
	my_idx = -1;

	if (lock->locked == _Q_LOCKED_VAL ||
	    lock->locked == _Q_LOCKED_IRQ_VAL) {
		lock->locked = false;
		return;
	}

	for (j = 0; j < 8; j++) {
		temp_lock_addr = ptr->lock_addr[j];
		if (temp_lock_addr != 0)
			max_idx = j;
		if (temp_lock_addr == (unsigned long)lock)
			my_idx = j;
		if (temp_lock_addr == 0)
			break;
	}

	if (my_idx == -1) {
		if (lock->locked == _Q_LOCKED_VAL ||
		    lock->locked == _Q_LOCKED_IRQ_VAL)
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

	BUG_ON(from_cpuid == -1);

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

	struct komb_node *curr_node = per_cpu_ptr(&komb_nodes[0], from_cpuid);


#ifdef WWJUMP
	struct komb_node *next_node = ptr->next_node_ptr;

	uint64_t counter = ptr->counter_val;

	/* Batch progress depends on queue eligibility and budget, not scheduler
	 * requests. Keep the protocol's successor and batch-limit checks. */
	if (next_node == NULL || next_node->next == NULL ||
	    check_irq_node(next_node) || check_irq_node(next_node->next) ||
	    counter >= komb_batch_size) {
		incoming_rsp_ptr = &(ptr->local_shadow_stack_ptr);
		ptr->curr_cs_cpu = -1;
		ptr->prev_cs_cpu = curr_node->cpuid;

	} else {
		ptr->curr_cs_cpu = next_node->cpuid;
		ptr->prev_cs_cpu = curr_node->cpuid;
		incoming_rsp_ptr = &(next_node->rsp);
		ptr->counter_val = counter + 1;
		print_debug("Jumping to the next waiter: %d\n",
			    next_node->cpuid);
	}
#else
	incoming_rsp_ptr = &(ptr->local_shadow_stack_ptr);
#endif
	/*
	 * Komb node still active here, because cpu (from_cpuid) still spinning.
	 */
	outgoing_rsp_ptr = &(curr_node->rsp);

#ifdef DEBUG_KOMB
	BUG_ON(incoming_rsp_ptr == NULL);
	BUG_ON(outgoing_rsp_ptr == NULL);
	BUG_ON(incoming_rsp_ptr == 0xdeadbeef);
	BUG_ON(outgoing_rsp_ptr == 0xdeadbeef);
#endif

#ifdef ENABLE_IRQS_CHECK
	curr_node->irqs_disabled = irqs_disabled();
#endif
	komb_context_switch(incoming_rsp_ptr, outgoing_rsp_ptr);
	ptr = this_cpu_ptr(&local_shadow_stack);
	if (ptr->irqs_disabled) {
		ptr->irqs_disabled = false;
		local_irq_disable();
	}
	LOCK_END_TIMING_PER_CPU(unlock_stack_switch);
	return;
}
EXPORT_SYMBOL_GPL(komb_spin_unlock);

__always_inline int komb_spin_trylock(struct qspinlock *lock)
{
	u32 val;

	// Qspinlock Fastpath

	val = atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL);
	if (val == 0)
		return true;

	return false;
}

void komb_spin_lock_nested(struct qspinlock *lock, int level)
{
	komb_spin_lock(lock);
}
EXPORT_SYMBOL_GPL(komb_spin_lock_nested);

void komb_assert_spin_locked(struct qspinlock *lock)
{
	BUG_ON(!komb_spin_is_locked(lock));
}

__always_inline int komb_spin_is_locked(struct qspinlock *lock)
{
	return atomic_read(&lock->val);
}
EXPORT_SYMBOL(komb_spin_is_locked);

__always_inline int komb_spin_is_contended(struct qspinlock *lock)
{
	return atomic_read(&lock->val) & ~_Q_LOCKED_MASK;
}

__always_inline int komb_spin_value_unlocked(struct qspinlock lock)
{
	return !atomic_read(&lock.val);
}

/* Read only after all benchmark clients have joined. This is an unload oracle,
 * not a concurrent admission gate or a general hook reader lifetime protocol. */
int tc_contexts_idle(void)
{
    int cpu, i;
    for_each_possible_cpu(cpu) {
        struct shadow_stack *s = per_cpu_ptr(&local_shadow_stack, cpu);
        for (i = 0; i < MAX_NODES; i++)
            if (READ_ONCE(per_cpu_ptr(&komb_nodes[i], cpu)->count))
                return 0;
        for (i = 0; i < ARRAY_SIZE(s->lock_addr); i++)
            if (READ_ONCE(s->lock_addr[i]))
                return 0;
        if (s->curr_cs_cpu != (u32)-1 || s->prev_cs_cpu != (u32)-1)
            return 0;
    }
    return 1;
}
