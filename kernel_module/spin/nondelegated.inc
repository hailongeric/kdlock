// SPDX-License-Identifier: GPL-2.0
/* Self-execution uses the same pending/tail word and per-CPU MCS nodes as
 * delegation. Like TCLock's non-combinable nodes, these wait on a local flag
 * and hand queue-head status onward before returning to their own body.
 * There is no request/frame, register capture, source lease or stack switch.
 * The caller keeps preemption disabled through its later physical unlock. */
/* Receive the failed initial CAS. In particular, the paired cold entry must
 * not retry the same CAS or prepare queue state on its successful path. */
static noinline void kd_spin_acquire_nondelegated_contended(struct qspinlock *word,
							 u32 val)
{
	struct kd_spin_node *node, *previous, *next;
	u32 tail, old_tail, loops;
	int idx;

	if (val == _Q_PENDING_VAL_HL) {
		loops = _Q_PENDING_LOOPS_HL;
		val = atomic_cond_read_relaxed(&word->val,
			(VAL != _Q_PENDING_VAL_HL) || !loops--);
	}
	if (!(val & ~_Q_LOCKED_MASK_HL)) {
		val = kd_spin_fetch_set_pending_acquire(word);
		if (!(val & ~_Q_LOCKED_MASK_HL)) {
			if (val & _Q_LOCKED_MASK_HL)
				atomic_cond_read_acquire(&word->val,
					!(VAL & _Q_LOCKED_MASK_HL));
			clear_pending_set_locked(word);
			return;
		}
		if (!(val & _Q_PENDING_MASK_HL))
			clear_pending(word);
	}

	/* Interrupt nesting shares these four slots with delegating producers.
	 * Reserve atomically before initializing the node; no IRQ-off wait is
	 * needed, and an interrupt cannot reuse a partially initialized slot. */
	idx = this_cpu_inc_return(kd_spin_cpu.node_count) - 1;
	barrier();
	if (unlikely(idx >= MAX_NODES)) {
		/* Only genuine node exhaustion falls back to polling the word.
		 * Read before CAS, and respect every pending/tail bit. */
		do {
			atomic_cond_read_relaxed(&word->val, !VAL);
		} while (atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL));
		goto out;
	}
	node = this_cpu_ptr(&kd_spin_nodes[0]) + idx;
	tail = encode_tail(smp_processor_id(), idx);
	node->locked = true;
	node->completed = false;
	node->next = NULL;
	node->socket_id = IRQ_NUMA_NODE; /* non-combinable, including task callers */
	node->cpuid = smp_processor_id();
	node->execution = NULL;
	/* rsp stays untouched: a suspended combiner can reuse this scheduler
	 * slot. socket_id is the immutable boundary until queue-head handoff. */
	smp_wmb();
	old_tail = xchg_tail(word, tail);
	if (old_tail & _Q_TAIL_MASK_HL) {
		previous = decode_tail(old_tail);
		smp_store_release(&previous->next, node);
		smp_cond_load_acquire_sched(&node->locked, !VAL);
	}

	/* Only the queue head polls the shared word. Acquiring it does not
	 * execute another waiter's body; a successor is only made queue head. */
	val = atomic_cond_read_acquire(&word->val,
				       !(VAL & _Q_LOCKED_PENDING_MASK));
	if ((val & _Q_TAIL_MASK_HL) == tail &&
	    atomic_try_cmpxchg_relaxed(&word->val, &val, _Q_LOCKED_VAL_HL))
		goto out;
	set_locked(word);
	smp_cond_load_relaxed_sched(&node->next, VAL);
	next = READ_ONCE(node->next);
	smp_store_release(&next->locked, false);
	/* No node accesses after handoff: the successor may recycle its slot. */
out:
	barrier();
	this_cpu_dec(kd_spin_cpu.node_count);
}

static void kd_spin_acquire_nondelegated(struct qspinlock *word)
{
	u32 val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);

	if (val)
		kd_spin_acquire_nondelegated_contended(word, val);
}
