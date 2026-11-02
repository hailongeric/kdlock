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

static struct kd_mutex_wait_record *
kd_mutex_wait_record(struct kd_mutex_node *node)
{
	u32 tail = node->osq.tail;
	int cpu = (tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1;
	int idx = (tail >> KD_MUTEX_TAIL_IDX_OFFSET) & KD_MUTEX_TAIL_IDX_MASK;

	BUG_ON(cpu < 0 || cpu >= nr_cpu_ids || idx >= KD_MUTEX_MAX_NODES);
	BUG_ON(!kd_mutex_wait_pools);
	return &per_cpu_ptr(kd_mutex_wait_pools, cpu)->records[idx];
}

struct kd_wait_node *kd_mutex_request_member(struct kd_mutex_node *node)
{
	return &kd_mutex_wait_record(node)->member;
}

static void kd_mutex_request_prepare(struct kd_mutex_node *node)
{
	struct kd_mutex_wait_record *record = kd_mutex_wait_record(node);

	BUG_ON(record->invocation == U64_MAX);
	BUG_ON(record->request_live || record->member.queue_head ||
	       record->request.selection);
	kd_wait_request_init(&record->request, record, ++record->invocation,
			     current, current, TASK_UNINTERRUPTIBLE, true, node);
	kd_wait_node_init(&record->member, &record->request, KD_WAIT_ACQUISITION);
	record->request_live = true;
}

static void kd_mutex_queue_publish(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	struct kd_wait_queue queue = kd_mutex_wait_queue(lock);
	unsigned long flags = _raw_spin_lock_irqsave(&lock->wait_lock);

	kd_wait_publish_locked(&queue, kd_mutex_request_member(node));
	atomic_long_or(1UL, &lock->owner); /* KD_WAITERS */
	kd_mutex_wake_head_locked(lock);
	_raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
}

/* Only a captured member can be returned outside the guard here. During this
 * migration these requests are uninterruptible and retain their slot until
 * explicit completion/handoff. A local stack node is never dereferenced after
 * guard release and forms a service boundary. */
static struct kd_mutex_node *
kd_mutex_queue_first(struct kd_mutex *lock)
{
	struct kd_wait_queue queue = kd_mutex_wait_queue(lock);
	struct kd_wait_node *member;
	struct kd_mutex_node *node = NULL;
	unsigned long flags = _raw_spin_lock_irqsave(&lock->wait_lock);

	member = kd_wait_first_locked(&queue);
	if (member && !member->request->admission && member->request->may_delegate &&
	    member->request->state == KD_WAIT_QUEUED)
		node = member->request->context;
	_raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
	return node;
}

static struct kd_mutex_node *kd_mutex_queue_start_batch(struct kd_mutex *lock)
{
	struct kd_wait_queue queue = kd_mutex_wait_queue(lock);
	struct kd_wait_node *member;
	struct kd_mutex_node *node = NULL;
	unsigned long flags = _raw_spin_lock_irqsave(&lock->wait_lock);

	member = kd_wait_first_locked(&queue);
	if (member && !member->request->admission && member->request->may_delegate &&
	    member->request->state == KD_WAIT_QUEUED) {
		/* Publication uses this guard to promote a head for local pickup.
		 * Close that route before retaining any proxy candidate pointer. */
		kd_mutex_gate_set(lock, KD_MUTEX_GATE_COMBINER);
		node = member->request->context;
	}
	_raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
	return node;
}

static struct kd_mutex_node *
kd_mutex_queue_successor(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	struct kd_wait_queue queue = kd_mutex_wait_queue(lock);
	struct kd_wait_node *member = kd_mutex_request_member(node);
	struct kd_wait_node *next;
	struct kd_mutex_node *result = NULL;
	unsigned long flags = _raw_spin_lock_irqsave(&lock->wait_lock);

	if (member->queue_head) {
		next = kd_wait_next_locked(&queue, member);
		if (next && !next->request->admission && next->request->may_delegate &&
		    next->request->state == KD_WAIT_QUEUED)
			result = next->request->context;
	}
	_raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
	return result;
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

/* Select/wake under the guard; never retain a successor pointer across gate
 * release. A local stack head remains a boundary and is woken by real unlock. */
static void kd_mutex_queue_handoff(struct kd_mutex *lock)
{
	unsigned long flags = _raw_spin_lock_irqsave(&lock->wait_lock);

	kd_mutex_wake_head_locked(lock);
	_raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
}

/* A slow physical acquisition uses its already published member. It never
 * reserves a delegation gate while enqueueing behind another request. After
 * physical grant, an earlier releaser may still be publishing FREE; any racing
 * fast reservation must fail its physical try and release that reservation. */
static void kd_mutex_wait_and_lock_node(struct kd_mutex *lock,
					struct kd_mutex_node *node)
{
	preempt_enable();
	kd_mutex_local_lock_node(lock, node);
	while (!kd_mutex_gate_trylock(lock)) {
		cpu_relax();
		cond_resched();
	}
	kd_mutex_gate_set(lock, KD_MUTEX_GATE_HELD);
	preempt_disable();
	this_cpu_inc(kd_mutex_origin_acquires);
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

	BUG_ON(kd_mutex_request_member(node)->queue_head ||
	       kd_mutex_wait_record(node)->request.selection);
	if (kd_mutex_wait_record(node)->request_live) {
		struct kd_wait_request *request = &kd_mutex_wait_record(node)->request;
		unsigned long flags = _raw_spin_lock_irqsave(request->guard);

		if (request->state == KD_WAIT_ACQUIRED)
			kd_wait_finish_local_locked(request);
		if (request->state == KD_WAIT_RETURN_ACK ||
		    request->state == KD_WAIT_CANCEL_ACK)
			kd_wait_set_state_locked(request, KD_WAIT_RETIRED);
		BUG_ON(request->state != KD_WAIT_RETIRED);
		_raw_spin_unlock_irqrestore(request->guard, flags);
		kd_mutex_wait_record(node)->request_live = false;
	}
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
