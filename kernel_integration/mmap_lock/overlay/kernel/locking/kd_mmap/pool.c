// SPDX-License-Identifier: GPL-2.0
#include <linux/sched.h>
#include <linux/kd_mmap_rwsem_types.h>
#include "kd_mmap_mutex_local.h"

/* This builtin has no JIT/delegation entry. Keep the production packet/node
 * geometry and independent OSQ links; no shadow stack or executable image is
 * published. Reservations remain on one CPU until OSQ retirement, so early
 * boot and allocation failure need no dynamic pool initialization. */
DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_mmap_mutex_node,
			     kd_mmap_mutex_nodes[KD_MMAP_MUTEX_MAX_NODES]);
static DEFINE_PER_CPU(unsigned long, kd_mmap_slots);

/* Borrowed optimistic nodes can enter the physical mutex's common queue.
 * Their membership storage shares the existing slot's exact reservation; no
 * continuation, shadow stack or proxy capability is added to this builtin. */
struct kd_mmap_local_member {
	struct kd_mmap_wait_request request;
	struct kd_mmap_wait_node member;
};
static DEFINE_PER_CPU(struct kd_mmap_local_member,
		     kd_mmap_local_members[KD_MMAP_MUTEX_MAX_NODES]);

struct kd_mmap_wait_node *
kd_mmap_mutex_request_member(struct kd_mmap_mutex_node *node)
{
	struct kd_mmap_local_member *record;

	lockdep_assert_preemption_disabled();
	BUG_ON(!node || node->slot < 0 || node->slot >= KD_MMAP_MUTEX_MAX_NODES ||
	       node != this_cpu_ptr(&kd_mmap_mutex_nodes[node->slot]) ||
	       node->task_struct_ptr != current || !node->lock);
	record = this_cpu_ptr(&kd_mmap_local_members[node->slot]);
	if (!record->member.request) {
		kd_mmap_wait_request_init(&record->request, NULL, 0, current,
					 current, TASK_UNINTERRUPTIBLE, false, node);
		kd_mmap_wait_node_init(&record->member, &record->request,
				      KD_MMAP_WAIT_ACQUISITION);
	}
	return &record->member;
}

struct kd_mmap_mutex_osq_node *kd_mmap_mutex_osq_node_get(struct kd_mmap_mutex *lock)
{
	unsigned long slots = this_cpu_read(kd_mmap_slots);
	int slot;

	lockdep_assert_preemption_disabled();
	BUILD_BUG_ON(sizeof(struct kd_mmap_mutex) != 32);
	BUILD_BUG_ON(sizeof(struct kd_mmap_rwsem) != 320);
	BUILD_BUG_ON(sizeof(struct kd_mmap_mutex_node) != 320);
	for (slot = 0; slot < KD_MMAP_MUTEX_MAX_NODES; slot++) {
		struct kd_mmap_mutex_node *node;

		if (slots & BIT(slot))
			continue;
		node = this_cpu_ptr(&kd_mmap_mutex_nodes[slot]);
		BUG_ON(READ_ONCE(node->lock));
		node->slot = slot;
		node->osq.tail = ((smp_processor_id() + 1) << KD_MMAP_MUTEX_TAIL_CPU_OFFSET) |
			(slot << KD_MMAP_MUTEX_TAIL_IDX_OFFSET);
		node->osq.locked = KD_MMAP_MUTEX_OSQ_IDLE;
		node->lock = lock;
		node->task_struct_ptr = current;
		this_cpu_write(kd_mmap_slots, slots | BIT(slot));
		return &node->osq;
	}
	return NULL;
}

void kd_mmap_mutex_osq_node_put(struct kd_mmap_mutex_osq_node *osq)
{
	struct kd_mmap_mutex_node *node = container_of(osq, struct kd_mmap_mutex_node, osq);
	struct kd_mmap_local_member *record;
	unsigned long slots = this_cpu_read(kd_mmap_slots);

	lockdep_assert_preemption_disabled();
	BUG_ON(node->slot < 0 || node->slot >= KD_MMAP_MUTEX_MAX_NODES);
	BUG_ON(node != this_cpu_ptr(&kd_mmap_mutex_nodes[node->slot]));
	BUG_ON(!(slots & BIT(node->slot)) || !node->lock || node->task_struct_ptr != current);
	BUG_ON(READ_ONCE(osq->locked) != KD_MMAP_MUTEX_OSQ_IDLE || osq->next || osq->prev);
	record = this_cpu_ptr(&kd_mmap_local_members[node->slot]);
	if (record->member.request) {
		unsigned long flags = _raw_spin_lock_irqsave(&node->lock->wait_lock);
		struct kd_mmap_wait_request *request = &record->request;

		BUG_ON(record->member.queue_head || request->memberships || request->selection);
		if (!request->guard)
			request->guard = &node->lock->wait_lock;
		if (request->state == KD_MMAP_WAIT_ACQUIRED)
			kd_mmap_wait_finish_local_locked(request);
		kd_mmap_wait_set_state_locked(request, KD_MMAP_WAIT_RETIRED);
		record->member.request = NULL;
		_raw_spin_unlock_irqrestore(&node->lock->wait_lock, flags);
	}
	node->task_struct_ptr = NULL;
	WRITE_ONCE(node->lock, NULL);
	this_cpu_write(kd_mmap_slots, slots & ~BIT(node->slot));
}

/* Used only after users have stopped; each slot holds an exact object identity,
 * independently of any aggregate observation or statistics counter. */
bool kd_mmap_mutex_waiters_idle(struct kd_mmap_mutex *lock)
{
	int cpu, slot;

	for_each_possible_cpu(cpu)
		for (slot = 0; slot < KD_MMAP_MUTEX_MAX_NODES; slot++)
			if (READ_ONCE(per_cpu(kd_mmap_mutex_nodes[slot], cpu).lock) == lock)
				return false;
	return true;
}
