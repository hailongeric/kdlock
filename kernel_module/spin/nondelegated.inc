// SPDX-License-Identifier: GPL-2.0
/* Self-execution uses the same pending/tail word and per-CPU MCS nodes as
 * delegation. Like TCLock's non-combinable nodes, these wait on a local flag
 * and hand queue-head status onward before returning to their own body.
 * There is no request/frame, register capture, source lease or stack switch.
 * The caller keeps preemption disabled through its later physical unlock. */
/* Only a native queue head, before physical acquisition, checks this prefix.
 * Capture the held word and its tail together: require six linked successors
 * at or before that tail, in addition to this head and the outside holder.
 * The extra backlog avoids marginal delegation when fast bodies outpace
 * waiter refill and leave short batches.
 * The head blocks successor reuse; stop at the captured tail so a holder that
 * releases and requeues during this walk cannot be counted twice. Missing
 * links decline immediately. Native/IRQ nodes count without inspecting frames.
 * This advisory veto runs at the approximate MCS boundary: the sampler's
 * reset to zero satisfies the existing low-bit check without another flag. */
static __always_inline void
kd_spin_qualify_native_queue(struct qspinlock *word, struct kd_spin_node *node)
{
	struct kd_spin_node *captured_tail;
	unsigned int successors;
	u32 captured;

	if ((this_cpu_read(kd_hotlock_spin_mcs) &
	     (KD_HOTLOCK_SPIN_MCS_INTERVAL - 1U)) ||
	    !kd_spin_delegate || !kd_hotlock_spin_cpu_hot_pinned())
		return;
	captured = atomic_read_acquire(&word->val);
	if (!(captured & _Q_LOCKED_MASK_HL) || !(captured & _Q_TAIL_MASK_HL))
		goto cold;
	captured_tail = decode_tail(captured & _Q_TAIL_MASK_HL);
	for (successors = 0; successors < 6; successors++) {
		if (node == captured_tail)
			goto cold;
		node = smp_load_acquire(&node->next);
		if (!node)
			goto cold;
	}
	return;
cold:
	kd_hotlock_cool_spin_pinned();
}

/* A read count precedes every notification. The credited interval is only
 * admission under this gate; each caller runs its own read body after return.
 * Keep one real terminal node and stop at the first writer, ordinary spin
 * waiter or incompatible physical context. No link is rewritten and no new
 * publication is awaited to extend the group. */
static struct kd_spin_node *
kd_rwlock_admit_readers(kd_rwlock_t *lock, struct kd_spin_node *first,
		      u8 context)
{
	struct kd_spin_node *next = first, *following, *cursor;
	unsigned int followers = 0;

	/* A fast writer may have won before the gate: retain our count while
	 * observing its release, exactly as the original local read slowpath. */
	atomic_add(KD_RWLOCK_READER_BIAS, &lock->cnts);
	atomic_cond_read_acquire(&lock->cnts, !(VAL & KD_RWLOCK_WRITER_LOCKED));
	while (followers + 1 < kd_combiner_batch_size && next &&
	       READ_ONCE(next->read_admission) == lock &&
	       check_irq_node(next) && !READ_ONCE(next->execution) &&
	       kd_spin_proxy_context_matches(READ_ONCE(next->proxy_context), context)) {
		following = smp_load_acquire(&next->next);
		if (!following)
			break;
		followers++;
		next = following;
	}
	if (!followers)
		return next;

	/* These exact, still-pinned queue members cannot retire before the
	 * notifications below. One RMW credits precisely that retained prefix.
	 * Our own read prevents a fast writer during both traversals. */
	atomic_add(followers * KD_RWLOCK_READER_BIAS, &lock->cnts);
	cursor = first;
	while (cursor != next) {
		following = READ_ONCE(cursor->next);
		WRITE_ONCE(cursor->completed, true);
		smp_store_release(&cursor->locked, false);
		/* The notified CPU may immediately recycle cursor. */
		cursor = following;
	}
	return next;
}

enum kd_native_admission {
	KD_NATIVE_GATE_HELD,
	KD_NATIVE_READ_GRANTED,
	KD_NATIVE_READ_AND_GATE_HELD,
};

/* Receive the failed initial CAS. In particular, the paired cold entry must
 * not retry the same CAS or prepare queue state on its successful path. */
static __always_inline enum kd_native_admission
kd_spin_acquire_nondelegated_common(struct qspinlock *word, u32 val,
				    kd_rwlock_t *reader)
{
	struct kd_spin_node *node, *previous, *next;
	u32 tail, old_tail, loops;
	int idx;
	enum kd_native_admission result = KD_NATIVE_GATE_HELD;

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
			return KD_NATIVE_GATE_HELD;
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
	node->proxy_context = reader ? kd_spin_proxy_context() : 0;
	node->read_admission = reader;
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
		if (reader && READ_ONCE(node->completed)) {
			result = KD_NATIVE_READ_GRANTED;
			goto out;
		}
	}

	/* Handoff is complete and our successors cannot advance until we own S. */
	kd_spin_qualify_native_queue(word, node);
	/* Only the queue head polls the shared word. Acquiring it does not
	 * execute another waiter's body; a successor is only made queue head. */
	val = atomic_cond_read_acquire(&word->val,
				       !(VAL & _Q_LOCKED_PENDING_MASK));
	if ((val & _Q_TAIL_MASK_HL) == tail &&
	    atomic_try_cmpxchg_relaxed(&word->val, &val, _Q_LOCKED_VAL_HL)) {
		goto out;
	}
	set_locked(word);
	smp_cond_load_relaxed_sched(&node->next, VAL);
	next = smp_load_acquire(&node->next);
	if (reader) {
		next = kd_rwlock_admit_readers(reader, next, node->proxy_context);
		result = KD_NATIVE_READ_AND_GATE_HELD;
	}
	smp_store_release(&next->locked, false);
	/* No node accesses after handoff: the successor may recycle its slot. */
out:
	barrier();
	this_cpu_dec(kd_spin_cpu.node_count);
	return result;
}

/* Keep ordinary spin callers on the same native specialization. */
static noinline void
kd_spin_acquire_nondelegated_contended(struct qspinlock *word, u32 val)
{
	(void)kd_spin_acquire_nondelegated_common(word, val, NULL);
}

/* The public inline reader already holds its original preemption pin and has
 * withdrawn its failed speculative count. A group grant owns only one read;
 * it must never release the gate subsequently held by another queue member. */
void kd_rwlock_read_slowpath(kd_rwlock_t *lock)
{
	enum kd_native_admission result = KD_NATIVE_GATE_HELD;
	u32 val;

	this_cpu_inc(kd_spin_fast_cpu.nondelegated);
	val = atomic_cmpxchg_acquire(&lock->gate.val, 0, KD_SPIN_DIRECT_NATIVE_HELD);
	kd_hotlock_spin_entry_pinned();
	if (val)
		result = kd_spin_acquire_nondelegated_common(&lock->gate, val, lock);
	if (result == KD_NATIVE_READ_GRANTED) {
		this_cpu_dec(kd_spin_fast_cpu.nondelegated);
		return;
	}
	if (result == KD_NATIVE_GATE_HELD) {
		atomic_add(KD_RWLOCK_READER_BIAS, &lock->cnts);
		atomic_cond_read_acquire(&lock->cnts, !(VAL & KD_RWLOCK_WRITER_LOCKED));
	}
	kd_spin_direct_native_release_inline(&lock->gate);
}
EXPORT_SYMBOL_GPL(kd_rwlock_read_slowpath);

static void kd_spin_acquire_nondelegated(struct qspinlock *word)
{
	u32 val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);

	if (val)
		kd_spin_acquire_nondelegated_contended(word, val);
}
