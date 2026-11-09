// SPDX-License-Identifier: GPL-2.0
/* Shared guarded topology and request election. Lock adapters own the physical
 * acquisition, scheduling policy, execution context and exact owner cleanup. */
#include <linux/bug.h>
#include <linux/limits.h>
#include <linux/percpu.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include "kd_wait_queue.h"

static DEFINE_PER_CPU(u64, kd_wait_local_sequence);

static void kd_wait_local_identity(void **identity, u64 *generation)
{
	unsigned long flags;
	u64 *sequence;

	preempt_disable();
	local_irq_save(flags);
	sequence = this_cpu_ptr(&kd_wait_local_sequence);
	BUG_ON(*sequence == U64_MAX);
	*generation = ++*sequence;
	*identity = sequence;
	local_irq_restore(flags);
	preempt_enable();
}

static void kd_wait_assert_queue(const struct kd_wait_queue *queue)
{
	BUG_ON(!queue || !queue->guard || !queue->head);
	lockdep_assert_held(queue->guard);
}

static void kd_wait_assert_request(const struct kd_wait_request *request)
{
	BUG_ON(!request || !request->guard);
	lockdep_assert_held(request->guard);
}

void kd_wait_request_init(struct kd_wait_request *request, void *identity,
			  u64 generation, struct task_struct *logical_origin,
			  struct task_struct *physical_waiter,
			  unsigned int wait_state, bool may_delegate, void *context)
{
	BUG_ON(!request || !logical_origin || !physical_waiter ||
	       (!identity && generation) || (identity && !generation));
	if (!identity)
		kd_wait_local_identity(&identity, &generation);
	request->identity = identity;
	request->generation = generation;
	request->logical_origin = logical_origin;
	request->physical_waiter = physical_waiter;
	request->wait_state = wait_state;
	request->may_delegate = may_delegate;
	request->state = KD_WAIT_PRIVATE;
	request->guard = NULL;
	request->acquisition = NULL;
	request->memberships = NULL;
	request->selection = NULL;
	request->local_selection.request = NULL;
	request->local_selection.generation = 0;
	request->local_selection.executor = NULL;
	request->cleanup = NULL;
	request->admission = NULL;
	request->terminal_guard = NULL;
	request->context = context;
}

void kd_wait_node_init(struct kd_wait_node *node, struct kd_wait_request *request,
		       enum kd_wait_member_kind kind)
{
	BUG_ON(!node || !request ||
	       (kind != KD_WAIT_ACQUISITION && kind != KD_WAIT_CONDITION));
	node->next = NULL;
	node->prev = NULL;
	node->request_next = NULL;
	node->request_prev = NULL;
	node->queue_head = NULL;
	node->request = request;
	node->generation = request->generation;
	node->kind = kind;
}

void kd_wait_link_locked(const struct kd_wait_queue *queue, struct kd_wait_node *node)
{
	struct kd_wait_request *request;
	struct kd_wait_node *head;

	kd_wait_assert_queue(queue);
	BUG_ON(!node || node->queue_head || node->next || node->prev ||
	       node->request_next || node->request_prev);
	request = node->request;
	BUG_ON(!request || node->generation != request->generation ||
	       request->state == KD_WAIT_CANCEL_ACK || request->state == KD_WAIT_RETIRED);
	BUG_ON(request->guard && request->guard != queue->guard);
	request->guard = queue->guard;
	head = *queue->head;
	if (head) {
		node->next = head;
		node->prev = head->prev;
		head->prev->next = node;
		head->prev = node;
	} else {
		node->next = node;
		node->prev = node;
		WRITE_ONCE(*queue->head, node);
	}
	node->queue_head = queue->head;
	head = request->memberships;
	if (head) {
		node->request_next = head;
		node->request_prev = head->request_prev;
		head->request_prev->request_next = node;
		head->request_prev = node;
	} else {
		node->request_next = node;
		node->request_prev = node;
		request->memberships = node;
	}
}

void kd_wait_unlink_locked(const struct kd_wait_queue *queue, struct kd_wait_node *node)
{
	struct kd_wait_request *request;

	kd_wait_assert_queue(queue);
	BUG_ON(!node || node->queue_head != queue->head || !node->next || !node->prev);
	request = node->request;
	BUG_ON(!request || request->guard != queue->guard ||
	       node->generation != request->generation || !request->memberships);
	if (node->next == node) {
		BUG_ON(*queue->head != node || node->prev != node);
		WRITE_ONCE(*queue->head, NULL);
	} else {
		node->prev->next = node->next;
		node->next->prev = node->prev;
		if (*queue->head == node)
			WRITE_ONCE(*queue->head, node->next);
	}
	if (node->request_next == node) {
		BUG_ON(request->memberships != node || node->request_prev != node);
		request->memberships = NULL;
	} else {
		node->request_prev->request_next = node->request_next;
		node->request_next->request_prev = node->request_prev;
		if (request->memberships == node)
			request->memberships = node->request_next;
	}
	if (request->acquisition == node)
		request->acquisition = NULL;
	node->queue_head = NULL;
	node->next = NULL;
	node->prev = NULL;
	node->request_next = NULL;
	node->request_prev = NULL;
}

void kd_wait_publish_locked(const struct kd_wait_queue *queue, struct kd_wait_node *node)
{
	struct kd_wait_request *request = node->request;

	kd_wait_assert_queue(queue);
	BUG_ON(node->kind != KD_WAIT_ACQUISITION || !request ||
	       request->state != KD_WAIT_PRIVATE || request->acquisition);
	kd_wait_link_locked(queue, node);
	request->acquisition = node;
	smp_store_release(&request->state, KD_WAIT_QUEUED);
}

void kd_wait_move_before_locked(const struct kd_wait_queue *queue,
			       struct kd_wait_node *node, struct kd_wait_node *before)
{
	kd_wait_assert_queue(queue);
	BUG_ON(!node || !before || node->queue_head != queue->head ||
	       before->queue_head != queue->head || !node->next || !node->prev ||
	       !before->next || !before->prev);
	if (node == before)
		return;
	if (node->next == before) {
		/* The circular tail is adjacent to the head, but moving it before
		 * that head still changes which invocation is selected first. */
		if (*queue->head == before)
			WRITE_ONCE(*queue->head, node);
		return;
	}
	node->prev->next = node->next;
	node->next->prev = node->prev;
	if (*queue->head == node)
		WRITE_ONCE(*queue->head, node->next);
	node->next = before;
	node->prev = before->prev;
	before->prev->next = node;
	before->prev = node;
	if (*queue->head == before)
		WRITE_ONCE(*queue->head, node);
}

struct kd_wait_node *kd_wait_first_locked(const struct kd_wait_queue *queue)
{
	kd_wait_assert_queue(queue);
	return *queue->head;
}

struct kd_wait_node *kd_wait_next_locked(const struct kd_wait_queue *queue,
				       const struct kd_wait_node *node)
{
	kd_wait_assert_queue(queue);
	BUG_ON(!node || node->queue_head != queue->head);
	return node->next == *queue->head ? NULL : node->next;
}

struct kd_wait_request *kd_wait_find_locked(const struct kd_wait_queue *queue,
					  void *identity, u64 generation)
{
	struct kd_wait_node *node = kd_wait_first_locked(queue);

	while (node) {
		struct kd_wait_request *request = node->request;

		if (node->kind == KD_WAIT_ACQUISITION && request->identity == identity &&
		    request->generation == generation && node->generation == generation)
			return request;
		node = kd_wait_next_locked(queue, node);
	}
	return NULL;
}

bool kd_wait_select_locked(const struct kd_wait_queue *queue,
			   struct kd_wait_request *request,
			   struct kd_wait_selection *selection,
			   struct task_struct *executor)
{
	kd_wait_assert_queue(queue);
	BUG_ON(!request || request->guard != queue->guard || !selection || !executor);
	if (request->state != KD_WAIT_QUEUED || !request->acquisition ||
	    request->acquisition->queue_head != queue->head)
		return false;
	if (!request->may_delegate && executor != request->physical_waiter)
		return false;
	BUG_ON(request->selection || selection->request);
	selection->request = request;
	selection->generation = request->generation;
	selection->executor = executor;
	request->selection = selection;
	smp_store_release(&request->state, KD_WAIT_SELECTED_DRAINING);
	return true;
}

bool kd_wait_cancel_ack_locked(struct kd_wait_request *request)
{
	kd_wait_assert_request(request);
	if (request->state == KD_WAIT_CANCEL_ACK)
		return true;
	BUG_ON(request->state != KD_WAIT_CANCELING);
	if (request->selection || request->cleanup || request->memberships || request->acquisition ||
	    (request->terminal_guard && request->guard != request->terminal_guard))
		return false;
	smp_store_release(&request->state, KD_WAIT_CANCEL_ACK);
	return true;
}

void kd_wait_cleanup_take_locked(struct kd_wait_request *request,
				 struct kd_wait_cleanup *cleanup, void *owner)
{
	kd_wait_assert_request(request);
	BUG_ON(!cleanup || !owner || request->cleanup || cleanup->request ||
	       (request->state != KD_WAIT_QUEUED && request->state != KD_WAIT_SELECTED_DRAINING));
	cleanup->request = request;
	cleanup->generation = request->generation;
	cleanup->owner = owner;
	request->cleanup = cleanup;
}

void kd_wait_cleanup_drop_locked(struct kd_wait_request *request,
				 struct kd_wait_cleanup *cleanup)
{
	kd_wait_assert_request(request);
	BUG_ON(!cleanup || request->cleanup != cleanup || cleanup->request != request ||
	       cleanup->generation != request->generation);
	request->cleanup = NULL;
	cleanup->request = NULL;
	cleanup->generation = 0;
	cleanup->owner = NULL;
}

raw_spinlock_t *kd_wait_cancel_rebind_locked(struct kd_wait_request *request,
					    raw_spinlock_t *retained_guard)
{
	raw_spinlock_t *old_guard;

	kd_wait_assert_request(request);
	BUG_ON(!retained_guard || request->state != KD_WAIT_CANCELING ||
	       request->selection || request->memberships || request->acquisition ||
	       request->terminal_guard != retained_guard);
	old_guard = request->guard;
	smp_store_release(&request->guard, retained_guard);
	return old_guard;
}

enum kd_wait_decision
kd_wait_decide_locked(const struct kd_wait_queue *queue,
		      struct kd_wait_request *request, u64 generation,
		      kd_wait_grant_fn grant, void *argument)
{
	kd_wait_assert_queue(queue);
	if (!request || request->generation != generation || request->guard != queue->guard)
		return KD_WAIT_STALE;
	switch (request->state) {
	case KD_WAIT_ACQUIRED:
	case KD_WAIT_EXECUTING:
	case KD_WAIT_RELEASED:
	case KD_WAIT_RETURN_ACK:
		return KD_WAIT_GRANTED;
	case KD_WAIT_CANCEL_ACK:
		return KD_WAIT_CANCELED;
	case KD_WAIT_CANCELING:
		return kd_wait_cancel_ack_locked(request) ? KD_WAIT_CANCELED :
							 KD_WAIT_CLEANUP_REQUIRED;
	case KD_WAIT_QUEUED:
	case KD_WAIT_SELECTED_DRAINING:
		break;
	default:
		return KD_WAIT_STALE;
	}
	BUG_ON(!request->acquisition ||
	       request->acquisition->queue_head != queue->head);
	BUG_ON(!grant);
	/* Actual ownership must be attempted before the origin's pending signal.
	 * A selected/draining request is still cancellable until this succeeds. */
	if (grant(request, argument)) {
		kd_wait_unlink_locked(queue, request->acquisition);
		smp_store_release(&request->state, KD_WAIT_ACQUIRED);
		return KD_WAIT_GRANTED;
	}
	if (!signal_pending_state(request->wait_state, request->logical_origin))
		return KD_WAIT_PENDING;
	kd_wait_unlink_locked(queue, request->acquisition);
	smp_store_release(&request->state, KD_WAIT_CANCELING);
	return kd_wait_cancel_ack_locked(request) ? KD_WAIT_CANCELED :
						 KD_WAIT_CLEANUP_REQUIRED;
}

void kd_wait_selection_drop_locked(struct kd_wait_request *request,
				   struct kd_wait_selection *selection)
{
	kd_wait_assert_request(request);
	BUG_ON(!selection || request->selection != selection ||
	       selection->request != request || selection->generation != request->generation);
	BUG_ON(request->state != KD_WAIT_SELECTED_DRAINING &&
	       request->state != KD_WAIT_CANCELING && request->state != KD_WAIT_ACQUIRED &&
	       request->state != KD_WAIT_EXECUTING && request->state != KD_WAIT_RELEASED);
	request->selection = NULL;
	selection->request = NULL;
	selection->generation = 0;
	selection->executor = NULL;
	if (request->state == KD_WAIT_SELECTED_DRAINING)
		smp_store_release(&request->state, KD_WAIT_QUEUED);
	else if (request->state == KD_WAIT_CANCELING)
		kd_wait_cancel_ack_locked(request);
}

void kd_wait_finish_local_locked(struct kd_wait_request *request)
{
	kd_wait_assert_request(request);
	BUG_ON(request->state != KD_WAIT_ACQUIRED);
	/* The physical acquisition remains live outside this returned request. */
	kd_wait_handoff_locked(request);
}

void kd_wait_move_acquired_locked(struct kd_wait_request *source,
				 struct kd_wait_request *destination)
{
	kd_wait_assert_request(source);
	BUG_ON(!destination || source == destination ||
	       destination->guard != source->guard ||
	       destination->state != KD_WAIT_PRIVATE ||
	       source->state != KD_WAIT_ACQUIRED ||
	       source->identity != destination->identity ||
	       source->generation != destination->generation ||
	       source->logical_origin != destination->logical_origin ||
	       source->physical_waiter != destination->physical_waiter ||
	       source->wait_state != destination->wait_state ||
	       source->may_delegate != destination->may_delegate ||
	       source->selection || source->cleanup || source->memberships || source->acquisition ||
	       destination->selection || destination->cleanup ||
	       destination->memberships || destination->acquisition);
	/* Publish destination custody before the source result/storage retires.
	 * No public acquisition is newly committed by this storage move. */
	smp_store_release(&destination->state, KD_WAIT_ACQUIRED);
	kd_wait_handoff_locked(source);
	kd_wait_set_state_locked(source, KD_WAIT_RETIRED);
}

void kd_wait_handoff_locked(struct kd_wait_request *request)
{
	kd_wait_assert_request(request);
	BUG_ON((request->state != KD_WAIT_ACQUIRED && request->state != KD_WAIT_EXECUTING) ||
	       request->selection || request->cleanup || request->memberships || request->acquisition);
	smp_store_release(&request->state, KD_WAIT_RETURN_ACK);
}

raw_spinlock_t *kd_wait_rebind_locked(struct kd_wait_request *request,
				     raw_spinlock_t *retained_guard)
{
	raw_spinlock_t *old_guard;

	kd_wait_assert_request(request);
	BUG_ON(!retained_guard ||
	       (request->state != KD_WAIT_ACQUIRED && request->state != KD_WAIT_EXECUTING) ||
	       request->selection || request->cleanup || request->memberships || request->acquisition);
	old_guard = request->guard;
	/* Only the transport's sole lifecycle token can establish the absence of
	 * actors which cached old_guard. This store does not revoke such a pointer
	 * and cannot replace the origin/selector access-retirement acknowledgment. */
	smp_store_release(&request->guard, retained_guard);
	return old_guard;
}

void kd_wait_set_state_locked(struct kd_wait_request *request,
			     enum kd_wait_state state)
{
	bool valid = false;

	kd_wait_assert_request(request);
	switch (request->state) {
	case KD_WAIT_PRIVATE:
		/* A condition-only invocation owns no public acquisition election. */
		valid = state == KD_WAIT_RETIRED;
		break;
	case KD_WAIT_ACQUIRED:
		valid = state == KD_WAIT_EXECUTING;
		break;
	case KD_WAIT_EXECUTING:
		valid = state == KD_WAIT_RELEASED;
		break;
	case KD_WAIT_RELEASED:
		valid = state == KD_WAIT_RETURN_ACK;
		break;
	case KD_WAIT_RETURN_ACK:
	case KD_WAIT_CANCEL_ACK:
		valid = state == KD_WAIT_RETIRED;
		break;
	default:
		break;
	}
	BUG_ON(!valid);
	if (state == KD_WAIT_RETURN_ACK || state == KD_WAIT_RETIRED)
		BUG_ON(request->selection || request->cleanup || request->memberships || request->acquisition);
	smp_store_release(&request->state, state);
}

/* wake_q_add is not an exported module service on the maintained kernel. This
 * is the same task-reference protocol already used by the KD physical mutex.
 * The task-owned wake link, not a queue node, survives dropping the guard. */
static void kd_wait_wake_add(struct wake_q_head *wake, struct task_struct *task)
{
	struct wake_q_node *node = &task->wake_q;

	smp_mb__before_atomic();
	if (cmpxchg_relaxed(&node->next, NULL, WAKE_Q_TAIL))
		return;
	get_task_struct(task);
	*wake->lastp = node;
	wake->lastp = &node->next;
}

void kd_wait_collect_request_wake_locked(struct kd_wait_request *request,
					 struct wake_q_head *wake)
{
	kd_wait_assert_request(request);
	BUG_ON(!wake || !request->physical_waiter);
	kd_wait_wake_add(wake, request->physical_waiter);
}

void kd_wait_collect_wake_locked(const struct kd_wait_queue *queue,
				 struct wake_q_head *wake)
{
	struct kd_wait_node *node = kd_wait_first_locked(queue);

	while (node) {
		kd_wait_collect_request_wake_locked(node->request, wake);
		node = kd_wait_next_locked(queue, node);
	}
}
