// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Per-CPU slot reservation, native mutex acquisition and private tail helpers.
 * Private implementation included only by kd_mutex.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* --------------------------------------------------------------------------
 * Tail encoding (same scheme as qspinlock: cpu+idx packed into u32)
 * -------------------------------------------------------------------------- */
#define KD_MUTEX_TAIL_IDX_OFFSET 2
#define KD_MUTEX_TAIL_IDX_BITS 2
#define KD_MUTEX_TAIL_IDX_MASK ((1U << KD_MUTEX_TAIL_IDX_BITS) - 1)
#define KD_MUTEX_TAIL_CPU_OFFSET \
	(KD_MUTEX_TAIL_IDX_OFFSET + KD_MUTEX_TAIL_IDX_BITS)

static inline u32 encode_tail(int cpu, int idx)
{
	return (cpu + 1) << KD_MUTEX_TAIL_CPU_OFFSET |
	       idx << KD_MUTEX_TAIL_IDX_OFFSET;
}

static inline struct kd_mutex_node *decode_tail(u32 tail)
{
	int cpu = (tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1;
	int idx = (tail >> KD_MUTEX_TAIL_IDX_OFFSET) & KD_MUTEX_TAIL_IDX_MASK;
	return per_cpu_ptr(&kd_mutex_nodes[idx], cpu);
}

static inline u32 xchg_tail(struct kd_mutex *lock, u32 tail)
{
	return xchg(&lock->tail, tail);
}

/* --------------------------------------------------------------------------
 * Small helpers
 * -------------------------------------------------------------------------- */
static __always_inline void
clear_locked_set_completed(struct kd_mutex_node *node)
{
	WRITE_ONCE(node->completed, KD_MUTEX_WAITER_PROCESSED);
	smp_store_release(&node->locked, 0);
}

static __always_inline void set_locked(struct kd_mutex *lock)
{
	smp_store_release(&lock->locked, _Q_LOCKED_VAL);
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

static void kd_mutex_waiter_enter(struct kd_mutex *lock)
{
	int active = atomic_inc_return(&kd_mutex_active_waiters);

	atomic_inc(&lock->waiter_count);
	kd_mutex_update_max_waiters(active);
}

static void kd_mutex_waiter_exit(struct kd_mutex *lock)
{
	if (unlikely(atomic_dec_return(&lock->waiter_count) < 0)) {
		atomic_set(&lock->waiter_count, 0);
		this_cpu_inc(kd_mutex_frame_failure_count);
		KD_PR_ERR("kd_mutex lock waiter count underflow lock=%px\n",
			  lock);
	}
	if (unlikely(atomic_dec_return(&kd_mutex_active_waiters) < 0)) {
		atomic_set(&kd_mutex_active_waiters, 0);
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

/* The scheduling gate cannot authorize a CS without the original mutex. */
static void kd_mutex_claim_origin(struct kd_mutex *lock)
{
	BUG_ON(READ_ONCE(lock->physical_owner));
	kd_origin_mutex_lock((struct mutex *)lock->origin_mutex_addr);
	WRITE_ONCE(lock->physical_owner, current);
	this_cpu_inc(kd_mutex_origin_acquires);
}

static void kd_mutex_wait_and_lock(struct kd_mutex *lock)
{
	for (;;) {
		while (smp_load_acquire(&lock->locked))
			cpu_relax();
		if (cmpxchg(&lock->locked, 0, _Q_LOCKED_VAL) == 0) {
			/* This request now owns the gate and cannot be delegated.
			 * Only the real mutex owner may execute/release its body. */
			preempt_enable();
			kd_mutex_claim_origin(lock);
			preempt_disable();
			return;
		}
		cpu_relax();
	}
}

/* Reservation is serialized by preemption disable on this migration-pinned
 * CPU. An executor can later sleep acquiring the real mutex; its reserved
 * stack must survive that sleep. Published delegation waiters never schedule. */
/* A reserved local predecessor may have enabled preemption while acquiring
 * the original mutex. Publishing another non-scheduling waiter on its CPU
 * would prevent that predecessor from ever resuming. Refuse before publication;
 * the new caller can sleep on the original mutex without exposing GS state. */
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
		atomic_inc(&kd_mutex_reserved_nodes);
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

	node->next = NULL;
	node->lock = NULL;
	node->task_struct_ptr = NULL;
	node->gsbase = 0;
	WRITE_ONCE(shadow->node_slots, slots & ~bit);
	atomic_dec(&kd_mutex_reserved_nodes);
	return;

invalid:
	this_cpu_inc(kd_mutex_frame_failure_count);
	KD_PR_ERR("kd_mutex invalid waiter slot release node=%px slots=%lx\n",
		  node, slots);
}
