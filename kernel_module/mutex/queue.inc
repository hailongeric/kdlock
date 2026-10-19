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

/* Called with preemption disabled from before request publication. Keep the
 * origin task on its CPU while another CPU executes GS accesses on its behalf.
 * The acquire pairs with completion/native-handoff publication; PAUSE is only
 * a polling hint and does not supply that ordering or disable interrupts. */
static void kd_mutex_wait_for_result(struct kd_mutex_node *node)
{
	while (smp_load_acquire(&node->locked))
		cpu_relax();
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
	for (;;) {
		while (kd_mutex_gate_read(lock))
			cpu_relax();
		if (kd_mutex_gate_trylock(lock)) {
			/* This request now owns the gate and cannot be delegated.
			 * Only the real mutex owner may execute/release its body. */
			preempt_enable();
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
 * stack must survive that sleep. Published delegation waiters never schedule. */
/* A reserved local predecessor may have enabled preemption while acquiring
 * the KD physical mutex. Publishing another non-scheduling waiter on its CPU
 * would prevent that predecessor from ever resuming. Refuse before publication;
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
