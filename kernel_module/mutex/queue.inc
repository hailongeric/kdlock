// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Per-CPU slot reservation, KD physical acquisition and private tail helpers.
 * Private implementation included only by kd_mutex.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* --------------------------------------------------------------------------
 * Tail encoding (same scheme as qspinlock: cpu+idx packed into u32)
 * -------------------------------------------------------------------------- */
static inline u32 kd_mutex_encode_tail(int cpu, int idx)
{
	return (cpu + 1) << KD_MUTEX_TAIL_CPU_OFFSET |
	       idx << KD_MUTEX_TAIL_IDX_OFFSET;
}

static inline struct kd_mutex_node *kd_mutex_decode_tail(u32 tail)
{
	int cpu = (tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1;
	int idx = (tail >> KD_MUTEX_TAIL_IDX_OFFSET) & KD_MUTEX_TAIL_IDX_MASK;
	return per_cpu_ptr(&kd_mutex_nodes[idx], cpu);
}

static inline u32 kd_mutex_xchg_tail(struct kd_mutex *lock, u32 tail)
{
	return xchg(&lock->delegation_tail, tail);
}

/* --------------------------------------------------------------------------
 * Small helpers
 * -------------------------------------------------------------------------- */
static __always_inline void
kd_mutex_clear_locked_set_completed(struct kd_mutex_node *node)
{
	WRITE_ONCE(node->completed, KD_MUTEX_WAITER_PROCESSED);
	smp_store_release(&node->locked, 0);
}

static __always_inline void kd_mutex_set_locked(struct kd_mutex *lock)
{
	kd_mutex_gate_set(lock, KD_MUTEX_GATE_HELD);
}

static void kd_mutex_update_max_waiters(int active)
{
	int old = this_cpu_read(kd_mutex_max_waiters);

	while (active > old) {
		int previous =
			this_cpu_cmpxchg(kd_mutex_max_waiters, old, active);

		if (previous == old)
			break;
		old = previous;
	}
}

static void kd_mutex_waiter_enter(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	/* This is an origin-CPU balance, not a queue publication primitive.
	 * The tail exchange/link and result release/acquire keep their ordering. */
	int active = this_cpu_inc_return(kd_mutex_active_waiters);

	kd_mutex_count_enter(lock, node);
	kd_mutex_update_max_waiters(active);
}

static void kd_mutex_waiter_exit(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	kd_mutex_count_exit(lock, node);
	if (unlikely(this_cpu_dec_return(kd_mutex_active_waiters) < 0)) {
		this_cpu_write(kd_mutex_active_waiters, 0);
		this_cpu_inc(kd_mutex_frame_failure_count);
		KD_PR_ERR("kd_mutex active waiter count underflow\n");
	}
}

/* Enter on the reserved shadow stack with preemption disabled. Packet/count
 * publication is finished before INIT becomes READY. A role-exchanged origin
 * may already be READY/CLAIMED, withdrawn, or completed when it reaches here.
 * Never rearm WAIT: cancellation may have won before this invocation entered.
 * Every return retains exactly the caller's original one preemption pin. */
static void kd_mutex_wait_for_result(struct kd_mutex_node *node)
{
	unsigned int budget = KDLOCK_MUTEX_SPIN_BUDGET;
	u8 state;
	KD_MUTEX_PIN_WAIT_ENTER();

	state = cmpxchg(&node->locked, KD_MUTEX_QUEUE_INIT, KD_MUTEX_PROXY_READY);
	BUG_ON(state != KD_MUTEX_QUEUE_INIT && state != KD_MUTEX_PROXY_READY &&
	       state != KD_MUTEX_PROXY_CLAIMED && state != KD_MUTEX_WAIT && state);
	for (;;) {
		state = smp_load_acquire(&node->locked);
		if (!state) {
			KD_MUTEX_PIN_INITIAL_FINISH(true);
			return;
		}
		if (state == KD_MUTEX_WAIT) {
			KD_MUTEX_PIN_FORCED_CANCEL();
			goto withdrawn;
		}
		BUG_ON(state != KD_MUTEX_PROXY_READY && state != KD_MUTEX_PROXY_CLAIMED);
		cpu_relax();
		if (budget) {
			if (!--budget)
				KD_MUTEX_PIN_BUDGET_EXPIRED();
			else
				continue;
		}
		/* A claimed origin cannot abandon its pin. The spent budget remains
		 * spent, including after a lost claim/withdraw race. */
		if (state != KD_MUTEX_PROXY_READY)
			continue;
		KD_MUTEX_PIN_EXPIRY_CHECK();
		if (!need_resched())
			continue;
		/* The reservation excludes a new epoch before touching READY. An
		 * active epoch or another withdrawing origin is a failed attempt,
		 * never a reason to wait here or abandon this origin's pin. */
		if (!kd_mutex_gate_try_withdraw(node->lock))
			continue;
		KD_MUTEX_PIN_WITHDRAW_RESERVED();
		state = cmpxchg(&node->locked, KD_MUTEX_PROXY_READY, KD_MUTEX_WAIT);
		kd_mutex_gate_end_withdraw(node->lock);
		if (state == KD_MUTEX_PROXY_READY) {
			KD_MUTEX_PIN_WITHDRAW();
			goto withdrawn;
		}
		BUG_ON(state != KD_MUTEX_PROXY_CLAIMED && state != KD_MUTEX_WAIT && state);
	}
withdrawn:
	/* Withdrawal won against claim, or the executor ended every origin
	 * access before publishing WAIT. A concurrent result zero must survive:
	 * no store or rearm follows this point. This is runnable scheduling,
	 * not a new parked delegation producer or a new sleep/wake protocol. */
	KD_MUTEX_PIN_INITIAL_FINISH(false);
	preempt_enable();
	while ((state = smp_load_acquire(&node->locked))) {
		BUG_ON(state != KD_MUTEX_WAIT);
		cpu_relax();
		if (need_resched())
			cond_resched();
	}
	preempt_disable();
}

/* The exact physical owner has closed withdrawal for this proxy epoch.
 * Its READY load can therefore precede a plain CLAIMED publication: no origin
 * can concurrently withdraw and no other executor owns this queue. The caller
 * also checks its private epoch and exact invocation generation. */
static __always_inline bool kd_mutex_proxy_request(struct kd_mutex *lock,
						 struct kd_mutex_node *node)
{
	BUG_ON(!kd_mutex_delegation_owned(lock, current) ||
	       kd_mutex_gate_read(lock) != KD_MUTEX_GATE_COMBINER);
	if ((node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1 == raw_smp_processor_id())
		return false;
	if (smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_READY)
		return false;
	smp_store_release(&node->locked, KD_MUTEX_PROXY_CLAIMED);
	return true;
}

/* This checks an already-acquired pin. No normal proxy path waits for READY
 * or retries a claim. The exact node/generation descriptor is checked too. */
static __always_inline void kd_mutex_proxy_assert_claimed(struct kd_mutex_node *node)
{
	BUG_ON(smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_CLAIMED);
}

/* ACQUIRING reserves the gate while physical acquisition can sleep. HELD
 * becomes visible only after current has acquired the authoritative owner word. */
static void kd_mutex_claim_origin_node(struct kd_mutex *lock,
				       struct kd_mutex_node *node)
{
	BUG_ON(kd_mutex_gate_read(lock) != KD_MUTEX_GATE_ACQUIRING);
	kd_mutex_local_lock_node(lock, node);
	kd_mutex_gate_set(lock, KD_MUTEX_GATE_HELD);
	this_cpu_inc(kd_mutex_origin_acquires);
}

static void kd_mutex_claim_origin(struct kd_mutex *lock)
{
	kd_mutex_claim_origin_node(lock, NULL);
}

static void kd_mutex_wait_and_lock_node(struct kd_mutex *lock,
					struct kd_mutex_node *node)
{
	/* A queue head is waiting for physical ownership, not being proxied.
	 * Keep it schedulable until acquisition and preserve the caller's pin. */
	preempt_enable();
	for (;;) {
		while (kd_mutex_gate_read(lock)) {
			cpu_relax();
			if (need_resched())
				cond_resched();
		}
		if (kd_mutex_gate_trylock(lock)) {
			/* This request now owns the gate and cannot be delegated.
			 * Only the real mutex owner may execute/release its body. */
			kd_mutex_claim_origin_node(lock, node);
			preempt_disable();
			return;
		}
		cpu_relax();
	}
}

static void kd_mutex_wait_and_lock(struct kd_mutex *lock)
{
	kd_mutex_wait_and_lock_node(lock, NULL);
}

/* Reservation is serialized by preemption disable on this migration-pinned
 * CPU. An executor can later sleep acquiring the real mutex; its reserved
 * stack must survive that sleep. The slot also survives a preemptible queue wait. */
/* A reserved local predecessor may have enabled preemption while acquiring
 * the KD physical mutex. A later selected pin on its CPU
 * could prevent that predecessor from resuming. Refuse before publication;
 * the new caller can sleep on the KD physical mutex without exposing GS state. */
static bool kd_mutex_has_local_predecessor(struct kd_mutex *lock)
{
	struct kd_mutex_cpu_state *shadow = this_cpu_ptr(&kd_mutex_shadows);
	unsigned long slots = READ_ONCE(shadow->node_slots);
	int idx;

	for (idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
		if ((slots & BIT(idx)) &&
		    READ_ONCE(this_cpu_ptr(&kd_mutex_nodes[idx])->lock) == lock)
			return true;
	}
	return false;
}

static struct kd_mutex_node *kd_mutex_reserve_node(void)
{
	struct kd_mutex_cpu_state *shadow = this_cpu_ptr(&kd_mutex_shadows);
	unsigned long slots = READ_ONCE(shadow->node_slots);
	int idx;

	for (idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
		struct kd_mutex_node *node;

		if (slots & BIT(idx))
			continue;
		node = this_cpu_ptr(&kd_mutex_nodes[idx]);
		if (!node->shadow_stack_base)
			continue;
		WRITE_ONCE(shadow->node_slots, slots | BIT(idx));
		if (slots)
			this_cpu_inc(kd_mutex_multi_slot_count);
		this_cpu_inc(kd_mutex_reserved_nodes);
		return node;
	}

	return NULL;
}

static void kd_mutex_release_node(struct kd_mutex_node *node)
{
	struct kd_mutex_cpu_state *shadow = this_cpu_ptr(&kd_mutex_shadows);
	unsigned long slots = READ_ONCE(shadow->node_slots);
	unsigned long bit;

	if (unlikely(!node || node->slot < 0 ||
		     node->slot >= KD_MUTEX_MAX_NODES))
		goto invalid;
	bit = BIT(node->slot);
	if (unlikely(!(slots & bit)))
		goto invalid;
	/* Count retirement precedes node reuse. Never reset its version: cold
	 * observations must distinguish a later invocation in this same slot. */
	BUG_ON(READ_ONCE(node->counted_lock) || (READ_ONCE(node->count_seq) & 1));
	BUG_ON(READ_ONCE(node->osq.locked) != KD_MUTEX_OSQ_IDLE);

	node->next = NULL;
	node->lock = NULL;
	node->task_struct_ptr = NULL;
	node->gsbase = 0;
	WRITE_ONCE(shadow->node_slots, slots & ~bit);
	if (unlikely(this_cpu_dec_return(kd_mutex_reserved_nodes) < 0))
		goto invalid;
	return;

invalid:
	this_cpu_inc(kd_mutex_frame_failure_count);
	KD_PR_ERR("kd_mutex invalid waiter slot release node=%px slots=%lx\n",
		  node, slots);
}

/* These temporary native reservations never survive preemption enable.
 * Borrowed delegation heads bypass get/put and retain their original slot,
 * waiter record, packet and shadow stack throughout physical acquisition. */
struct kd_mutex_osq_node *kd_mutex_osq_node_get(struct kd_mutex *lock)
{
	struct kd_mutex_node *node = kd_mutex_reserve_node();

	if (!node)
		return NULL;
	BUG_ON(READ_ONCE(node->osq.locked) != KD_MUTEX_OSQ_IDLE);
	node->lock = lock;
	node->task_struct_ptr = current;
	return &node->osq;
}

void kd_mutex_osq_node_put(struct kd_mutex_osq_node *osq)
{
	struct kd_mutex_node *node = container_of(osq, struct kd_mutex_node, osq);

	BUG_ON(READ_ONCE(osq->locked) != KD_MUTEX_OSQ_IDLE);
	kd_mutex_release_node(node);
}
