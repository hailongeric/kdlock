/* SPDX-License-Identifier: GPL-2.0 */
/* Fast/pending acquisition and queue entry; all callers on a target use this same spin protocol. */
__attribute__((noipa)) noinline notrace void
komb_spin_lock(struct qspinlock *lock)
{
	u32 val, cnt;
	/* With IRQ checks disabled, this local is only used by debug checks. */
	struct komb_node *curr_node __maybe_unused = NULL;

	/*
	 * Fastpath
	 */

	val = atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL);
	if (val == 0)
		return;

	/*
	 * Mid-path
	 *
	 * Wait for in-progress pending->locked hand-overs with a bounded
	 * number of spins so that we guarantee forward progress.
	 *
	 * 0,1,0 -> 0,0,1
	 */
	if (val == _Q_PENDING_VAL) {
		cnt = _Q_PENDING_LOOPS;
		val = atomic_cond_read_relaxed(
			&lock->val, (VAL != _Q_PENDING_VAL) || !cnt--);
	}

	/*
	 * If we observe any contention; queue.
	 */
	if (val & ~_Q_LOCKED_MASK ||
	    (val & _Q_LOCKED_MASK) == _Q_LOCKED_IRQ_VAL)
		goto queue;

	/*
	 * trylock || pending
	 *
	 * 0,0,* -> 0,1,* -> 0,0,1 pending, trylock
	 */
	val = komb_fetch_set_pending_acquire(lock);

	/*
	 * If we observe contention, there is a concurrent locker.
	 *
	 * Undo and queue; our setting of PENDING might have made the
	 * n,0,0 -> 0,0,0 transition fail and it will now be waiting
	 * on @next to become !NULL.
	 */
	if (unlikely(val & ~_Q_LOCKED_MASK)) {
		/* Undo PENDING if we set it. */
		if (!(val & _Q_PENDING_MASK))
			clear_pending(lock);

		goto queue;
	}

	/*
	 * We're pending, wait for the owner to go away.
	 *
	 * 0,1,1 -> 0,1,0
	 *
	 * this wait loop must be a load-acquire such that we match the
	 * store-release that clears the locked bit and create lock
	 * sequentiality; this is because not all
	 * clear_pending_set_locked() implementations imply full
	 * barriers.
	 */
	if (val & _Q_LOCKED_MASK)
		atomic_cond_read_acquire(&lock->val, !(VAL & _Q_LOCKED_MASK));

	/*
	 * take ownership and clear the pending bit.
	 *
	 * 0,1,0 -> 0,0,1
	 */
	clear_pending_set_locked(lock);
	return;

	/*
	 * End of pending bit optimistic spinning and beginning of MCS
	 * queuing.
	 */
queue:

	curr_node = this_cpu_ptr(&komb_nodes[0]);
#ifdef DEBUG_KOMB
	BUG_ON(curr_node == NULL);
#endif
#ifdef ENABLE_IRQS_CHECK
	if (curr_node->count > 0 || !in_task() || irqs_disabled() ||
	    current->migration_disabled) {
		/*print_debug("Nested lock: waiting for lock\n");
		while (true) {
			atomic_cond_read_acquire(&lock->val, !(VAL));

			if (atomic_cmpxchg_acquire(&lock->val, 0,
						   _Q_LOCKED_IRQ_VAL) == 0)
				break;
		}
		print_debug("Nested lock: got the lock\n");
		return;
	} else if (!in_task() ||irqs_disabled() || current->migration_disabled) {*/
		struct komb_node *prev_node, *next_node;
		u32 tail, idx;

		idx = curr_node->count++;
		/*
	 * 4 nodes are allocated based on the assumption that there will
	 * not be nested NMIs taking spinlocks. That may not be true in
	 * some architectures even though the chance of needing more than
	 * 4 nodes will still be extremely unlikely. When that happens,
	 * we fall back to spinning on the lock directly without using
	 * any MCS node. This is not the most elegant solution, but is
	 * simple enough.
	 */
		if (unlikely(idx >= MAX_NODES)) {
			while (!komb_spin_trylock(lock))
				cpu_relax();
			goto irq_release;
		}

		curr_node += idx;
		tail = encode_tail(smp_processor_id(), idx);

		barrier();

		curr_node->locked = true;
		curr_node->completed = false;
		curr_node->next = NULL;
		curr_node->tail = tail;
		curr_node->socket_id = IRQ_NUMA_NODE;
		curr_node->cpuid = smp_processor_id();
		curr_node->irqs_disabled = false;
		curr_node->lock = lock;
		curr_node->task_struct_ptr = current;

		uint64_t prev_rsp = curr_node->rsp;
		curr_node->rsp = 0xdeadbeef;

		smp_wmb();

		u32 old_tail = xchg_tail(lock, tail);

		if (old_tail & _Q_TAIL_MASK) {
			prev_node = decode_tail(old_tail);
			WRITE_ONCE(prev_node->next, curr_node);

			print_debug("IRQ going to waiting for lock\n");
			smp_cond_load_relaxed_sched(&curr_node->locked, !(VAL));
		}

		curr_node->rsp = prev_rsp;

		u32 val, new_val;

		print_debug("IRQ spinning on the locked field\n");

		val = atomic_cond_read_acquire(&lock->val,
					       !(VAL & _Q_LOCKED_PENDING_MASK));

		if (((val & _Q_TAIL_MASK) == tail) &&
		    atomic_try_cmpxchg_relaxed(&lock->val, &val,
					       _Q_LOCKED_IRQ_VAL)) {
			print_debug("IRQ only one in the queue unlocked\n");
			goto irq_release;
		}

		//set_locked(lock);

		while (true) {
			val = atomic_cond_read_relaxed(
				&lock->val, !(VAL & _Q_LOCKED_PENDING_MASK));

#ifdef DEBUG_KOMB
			BUG_ON(lock->locked != 0);
#endif

			new_val = val >> _Q_LOCKED_BITS;
			new_val <<= _Q_LOCKED_BITS;
			new_val |= _Q_LOCKED_IRQ_VAL;

			if (atomic_cmpxchg_acquire(&lock->val, val, new_val) ==
			    val)
				break;
		}

		print_debug("IRQ got the lock\n");

		smp_cond_load_relaxed_sched(&curr_node->next, (VAL));
		next_node = curr_node->next;

#ifdef DEBUG_KOMB
		BUG_ON(next_node == NULL);
#endif

		WRITE_ONCE(next_node->locked, false);

		print_debug("IRQ passing lock next node: %d\n",
			    next_node->cpuid);

	irq_release:
		curr_node = this_cpu_ptr(&komb_nodes[0]);
		curr_node->count--;
		return;
	} else {
#endif

#ifdef LOCK_MEASURE_TIME
		*this_cpu_ptr(&lock_stack_switch) = UINT64_MAX;
		*this_cpu_ptr(&unlock_stack_switch) = UINT64_MAX;
#endif
		LOCK_START_TIMING_PER_CPU(lock_stack_switch);

		komb_spin_lock_slowpath(lock);

#ifdef WWJUMP
		struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

		uint32_t curr_cpuid = ptr->curr_cs_cpu;
		if (curr_cpuid != -1) {
			struct komb_node *curr_node =
				per_cpu_ptr(&komb_nodes[0], curr_cpuid);
			if (curr_node->lock == lock) {
#ifdef DEBUG_KOMB
				BUG_ON(lock->locked != _Q_LOCKED_COMBINER_VAL);
#endif
				struct komb_node *next_node =
					get_next_node(curr_node);
				ptr->next_node_ptr = next_node;
			}

			uint32_t prev_cpuid = ptr->prev_cs_cpu;
			if (prev_cpuid != -1) {
				struct komb_node *prev_node =
					per_cpu_ptr(&komb_nodes[0], prev_cpuid);

#ifdef DEBUG_KOMB
				BUG_ON(prev_node->lock != lock);
#endif
				print_debug("Waking up prev waiter: %d\n",
					    prev_cpuid);
				clear_locked_set_completed(prev_node);
				ptr->prev_cs_cpu = -1;

				//	LOCK_END_TIMING_PER_CPU(combiner_loop);
			}
		}
#endif

#ifdef ENABLE_IRQS_CHECK
	}
#endif
}
EXPORT_SYMBOL_GPL(komb_spin_lock);
