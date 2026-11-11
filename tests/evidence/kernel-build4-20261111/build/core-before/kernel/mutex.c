// SPDX-License-Identifier: GPL-2.0-only
/*
 * Sleepable MCS exclusion and optional source-request combining.
 * Queue exchange/link and successor handoff follow the relevant MCS mechanics
 * in TCLocks bbfb9f00a12af51dff6ca291cb9829a82960c2ef. No native waiter-stack
 * engine, fixed task fields or old-kernel integration is imported.
 *
 * Queue ownership and source-grant lifetime are separate. Removing an offered
 * node from the MCS chain does not retire its release, state or result users.
 * No source runs under an atomic operation or the release-control guard.
 */
#include <linux/bug.h>
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <asm/cmpxchg.h>
#include <asm/processor.h>

#include "mutex.h"
#include "observation.h"
#include "state.h"

static unsigned long node_observation_flags(struct kd_mutex_node *node)
{
	return (READ_ONCE(node->enqueued) ? KD_OBS_FLAG_ENQUEUED : 0) |
		(READ_ONCE(node->source_granted) ? KD_OBS_FLAG_SOURCE_GRANTED : 0) |
		(smp_load_acquire(&node->queue_done) ? KD_OBS_FLAG_QUEUE_DONE : 0) |
		(smp_load_acquire(&node->result_ready) ? KD_OBS_FLAG_RESULT_READY : 0) |
		(READ_ONCE(node->result_user) ? KD_OBS_FLAG_RESULT_USER_PRESENT : 0);
}

/* These node/control fields remain retained through each call. origin is
 * immutable lifecycle metadata; no register packet or current binding is read.
 */
static void observe_node(unsigned long kind, struct kd_mutex_node *node,
		struct kd_mutex_batch *batch, const void *related,
		unsigned long phase, unsigned long result)
{
	kd_observe(kind, .state = (unsigned long)node->state,
		.origin = (unsigned long)node->state->origin,
		.node = (unsigned long)node, .acquisition = (unsigned long)node->acquisition,
		.owner = batch ? (unsigned long)&batch->release_owner : 0,
		.owner_task = batch ? (unsigned long)batch->release_owner.task : 0,
		.object = (unsigned long)node->lock, .related = (unsigned long)related,
		.phase = phase, .result = result, .flags = node_observation_flags(node));
}

/*
 * Capture an independent task reference before the final condition store.
 * A receiver may complete its remaining lifecycle while wakeup still runs;
 * wakeup therefore never reads the node again after publication. Observing
 * turn/result alone does not permit reuse before the other exact users end.
 */
static void publish_condition(struct kd_mutex_node *node, int *condition)
{
	struct task_struct *task = node->requester;

	get_task_struct(task);
	smp_store_release(condition, 1);
	wake_up_process(task);
	put_task_struct(task);
}

static struct task_struct *retain_owner_task(struct kd_mutex_node *node)
{
	struct task_struct *task = node->batch->release_owner.task;

	/* The caller's exact result/core/return/notifier user retains the batch. */
	get_task_struct(task);
	return task;
}

static void wake_retained_task(struct task_struct *task)
{
	wake_up_process(task);
	put_task_struct(task);
}

/*
 * A producer that exchanged tail can be between exchange and link publication.
 * There is no sleep-until-wakeup here: its release store is the producer's LAST
 * predecessor-node access, so no embedded wake state extends that reference.
 * Preemptible link polling yields when needed, outside any atomic obligation.
 */
static struct kd_mutex_node *wait_link(struct kd_mutex_node *node)
{
	struct kd_mutex_node *next;

	for (;;) {
		next = smp_load_acquire(&node->next);
		if (next)
			return next;
		cpu_relax();
		cond_resched();
	}
}

static bool progress_wait(struct kd_mutex_node *node)
{
	bool blocked = false;
	int result;

	/* Callbacks can reschedule or finish backend release; never run them
	 * with an artificial sleep state inherited from the wait loop.
	 */
	__set_current_state(TASK_RUNNING);
	if (node->ops && node->ops->wait_progress) {
		BUG_ON(!node->ops->wait_ready);
		result = node->ops->wait_progress(node, node->context, &blocked);
		BUG_ON(result);
	}
	return blocked;
}

static bool progress_ready(struct kd_mutex_node *node)
{
	return node->ops && node->ops->wait_ready &&
	       node->ops->wait_ready(node, node->context);
}

static void wait_request(struct kd_mutex_node *node)
{
	for (;;) {
		bool blocked = progress_wait(node);

		set_current_state(TASK_UNINTERRUPTIBLE);
		if (!blocked && (smp_load_acquire(&node->turn) ||
		    smp_load_acquire(&node->result_ready)))
			break;
		/* A release notification before sleep publication is seen here;
		 * one afterward wakes the published state. No notification is lost.
		 */
		if (progress_ready(node))
			continue;
		schedule();
	}
	__set_current_state(TASK_RUNNING);
}

/* Actual normal backend release, bound to this mutex at batch initialization. */
static void mcs_physical_unlock(void *object)
{
	struct kd_mutex *lock = object;
	struct kd_mutex_batch *batch = READ_ONCE(lock->owner);
	struct kd_mutex_node *head;
	struct kd_mutex_node *next;
	int selection;

	BUG_ON(!batch || batch->release_owner.task != current);
	head = batch->head;
	BUG_ON(!head);
	next = smp_load_acquire(&head->next);
	WRITE_ONCE(lock->owner, NULL);
	if (!next && cmpxchg(&lock->tail, head, NULL) == head) {
		/* No producer can still hold head as its predecessor. */
		smp_store_release(&head->queue_done, 1);
		observe_node(KD_OBS_QUEUE_DONE, head, batch, NULL,
			     KD_MUTEX_SELECTED_LOCAL, 0);
		return;
	}
	/* No lock-object access follows the tail operation/owner clear above. */
	if (!next)
		next = wait_link(head);
	selection = atomic_cmpxchg(&next->selection, KD_MUTEX_OFFERED,
				  KD_MUTEX_SELECTED_LOCAL);
	BUG_ON(selection != KD_MUTEX_OFFERED &&
	       selection != KD_MUTEX_SELECTED_LOCAL);
	smp_store_release(&head->queue_done, 1);
	observe_node(KD_OBS_QUEUE_DONE, head, batch, next,
		     KD_MUTEX_SELECTED_LOCAL, 0);
	/* Turn is actual MCS handoff, not an offered request or source result. */
	publish_condition(next, &next->turn);
}

void kd_mutex_init(struct kd_mutex *lock)
{
	WRITE_ONCE(lock->tail, NULL);
	WRITE_ONCE(lock->owner, NULL);
}

void kd_mutex_batch_init(struct kd_mutex_batch *batch)
{
	batch->lock = NULL;
	batch->head = NULL;
	batch->serving = NULL;
	batch->proxy_limit = 0;
	batch->proxy_served = 0;
	batch->initialized = false;
	batch->head_retired = false;
}

int kd_mutex_node_init(struct kd_mutex_node *node,
		       struct kd_thread_state *state,
		       const void *acquisition, const void *operation,
		       const void *grant_user, const void *result_user,
		       bool ready, const struct kd_mutex_ops *ops, void *context)
{
	if (!state || !acquisition || !operation || !grant_user || !result_user)
		return -EINVAL;
	if (ready && (!ops || !ops->selected_local || !ops->execute_proxy))
		return -EINVAL;
	if (ops && (!!ops->wait_progress != !!ops->wait_ready))
		return -EINVAL;
	/* Private fresh storage, or previous node retirement has completed. */
	node->next = NULL;
	atomic_set(&node->selection, KD_MUTEX_PRIVATE);
	node->turn = 0;
	node->queue_done = 0;
	node->result_ready = 0;
	node->retirable = 0;
	node->enqueued = false;
	node->wait_started = false;
	node->source_granted = false;
	node->ready = ready;
	node->requester = current;
	get_task_struct(node->requester);
	node->state = state;
	node->acquisition = acquisition;
	node->operation = operation;
	node->grant_user = grant_user;
	node->result_user = result_user;
	node->ops = ops;
	node->context = context;
	node->lock = NULL;
	node->batch = NULL;
	node->outcome = KD_MUTEX_OUTCOME_UNSET;
	node->release.owner = NULL;
	return 0;
}

int kd_mutex_node_discard(struct kd_mutex_node *node)
{
	struct task_struct *task;

	if (node->requester != current)
		return -EPERM;
	if (node->enqueued || atomic_read(&node->selection) != KD_MUTEX_PRIVATE)
		return -EBUSY;
	task = node->requester;
	node->requester = NULL;
	node->result_user = NULL;
	observe_node(KD_OBS_NODE_RETIRE_READY, node, NULL, NULL, KD_MUTEX_PRIVATE, 0);
	smp_store_release(&node->retirable, 1);
	put_task_struct(task);
	return 0;
}

int kd_mutex_enqueue(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	struct kd_mutex_node *previous;

	if (node->requester != current)
		return -EPERM;
	if (!lock)
		return -EINVAL;
	if (node->enqueued || atomic_read(&node->selection) != KD_MUTEX_PRIVATE)
		return -EALREADY;
	node->lock = lock;
	node->enqueued = true;
	atomic_set(&node->selection, node->ready ? KD_MUTEX_OFFERED :
		   KD_MUTEX_SELECTED_LOCAL);
	previous = xchg(&lock->tail, node);
	if (previous) {
		/* Final previous-node access: the consumer may detach after this. */
		smp_store_release(&previous->next, node);
	} else {
		smp_store_release(&node->turn, 1);
	}
	/* The producer's final predecessor-link access has completed. */
	observe_node(KD_OBS_ENQUEUE, node, NULL, previous,
		     node->ready ? KD_MUTEX_OFFERED : KD_MUTEX_SELECTED_LOCAL, 0);
	return 0;
}

bool kd_mutex_choose_local(struct kd_mutex_node *node)
{
	int selection;

	if (node->requester != current || !node->enqueued ||
	    smp_load_acquire(&node->result_ready) ||
	    smp_load_acquire(&node->retirable))
		return false;
	selection = atomic_cmpxchg(&node->selection, KD_MUTEX_OFFERED,
				  KD_MUTEX_SELECTED_LOCAL);
	return selection == KD_MUTEX_OFFERED ||
	       selection == KD_MUTEX_SELECTED_LOCAL;
}

/* Remove a uniquely proxy-selected successor while keeping head's MCS turn. */
static void detach_proxy(struct kd_mutex_batch *batch, struct kd_mutex_node *node)
{
	struct kd_mutex_node *head = batch->head;
	struct kd_mutex_node *next = smp_load_acquire(&node->next);

	BUG_ON(smp_load_acquire(&head->next) != node);
	if (!next) {
		/*
		 * Clear BEFORE replacing tail: a later producer can then link to
		 * head without its new link being overwritten by this consumer.
		 */
		WRITE_ONCE(head->next, NULL);
		if (cmpxchg(&batch->lock->tail, node, head) == node) {
			smp_store_release(&node->queue_done, 1);
			observe_node(KD_OBS_QUEUE_DONE, node, batch, head,
				     KD_MUTEX_SELECTED_PROXY, 0);
			return;
		}
		next = wait_link(node);
	}
	WRITE_ONCE(head->next, next);
	/* Observing next proves its producer's final node access completed. */
	smp_store_release(&node->queue_done, 1);
	observe_node(KD_OBS_QUEUE_DONE, node, batch, head,
		     KD_MUTEX_SELECTED_PROXY, 0);
}

static enum kd_mutex_unlock_phase release_phase(struct kd_mutex_node *node)
{
	struct kd_mutex_release_owner *owner = &node->batch->release_owner;
	enum kd_mutex_unlock_phase phase;

	raw_spin_lock(&owner->guard);
	phase = node->release.phase;
	raw_spin_unlock(&owner->guard);
	return phase;
}

/* A live grant blocks the next source grant, even after a proxy outcome. */
static void wait_owner_handled(struct kd_mutex_node *node)
{
	struct kd_mutex_node *head = node->batch->head;

	for (;;) {
		enum kd_mutex_unlock_phase phase;
		bool blocked = progress_wait(head);
		int result;

		set_current_state(TASK_UNINTERRUPTIBLE);
		phase = release_phase(node);
		if (phase == KD_MUTEX_UNLOCK_REQUESTED ||
		    phase == KD_MUTEX_UNLOCK_UNWIND_READY) {
			result = kd_mutex_release_owner_handle(&node->release);
			BUG_ON(result && result != -EAGAIN);
			if (!result)
				phase = KD_MUTEX_UNLOCK_OWNER_HANDLED;
		}
		if (phase == KD_MUTEX_UNLOCK_OWNER_HANDLED && !blocked)
			break;
		if (progress_ready(head))
			continue;
		schedule();
	}
	__set_current_state(TASK_RUNNING);
}

static void bind_grant(struct kd_mutex_batch *batch, struct kd_mutex_node *node)
{
	int result;

	node->batch = batch;
	result = kd_mutex_release_bind(&batch->release_owner, &node->release,
				       node->state, node->acquisition, node->grant_user);
	BUG_ON(result);
	WRITE_ONCE(node->source_granted, true);
	observe_node(KD_OBS_GRANT, node, batch, &node->release,
		     KD_MUTEX_UNLOCK_HELD, 0);
}

int kd_mutex_combine(struct kd_mutex_batch *batch, unsigned int proxy_limit,
		     unsigned int *served)
{
	struct kd_mutex_node *head;
	unsigned int count = 0;

	might_sleep();
	if (!batch->initialized || batch->release_owner.task != current)
		return -EPERM;
	if (!served)
		return -EINVAL;
	if (batch->release_owner.phase != KD_MUTEX_OWNER_OPEN || batch->serving)
		return -EBUSY;
	head = batch->head;
	if (head->source_granted &&
	    release_phase(head) != KD_MUTEX_UNLOCK_OWNER_HANDLED)
		return -EBUSY;
	while (count < proxy_limit && batch->proxy_served < batch->proxy_limit) {
		struct kd_mutex_node *node = smp_load_acquire(&head->next);
		struct task_struct *origin;
		struct kd_thread_state *state;
		enum kd_mutex_outcome outcome;

		if (!node)
			break;
		/* Never skip a local-only or already locally selected successor. */
		if (atomic_cmpxchg(&node->selection, KD_MUTEX_OFFERED,
				   KD_MUTEX_SELECTED_PROXY) != KD_MUTEX_OFFERED)
			break;
		observe_node(KD_OBS_SELECT_PROXY, node, batch, head,
			     KD_MUTEX_SELECTED_PROXY, 0);
		BUG_ON(!node->ready || !node->ops || !node->ops->execute_proxy);
		detach_proxy(batch, node);
		bind_grant(batch, node);
		batch->serving = node;
		batch->proxy_served++;
		/* Terminal source export may let W advance before this callback
		 * returns. Cache only immutable identities beforehand.
		 */
		state = node->state;
		origin = state->origin;
		outcome = node->ops->execute_proxy(node, node->context);
		BUG_ON(outcome < KD_MUTEX_PROXY_OPERATION_DONE ||
		       outcome > KD_MUTEX_PROXY_UNWIND_PARENT);
		BUG_ON(batch->release_owner.phase != KD_MUTEX_OWNER_OPEN);
		node->outcome = outcome;
		kd_observe(KD_OBS_PROXY_RETURN, .state = (unsigned long)state,
			.origin = (unsigned long)origin, .node = (unsigned long)node,
			.acquisition = (unsigned long)node->acquisition,
			.owner = (unsigned long)&batch->release_owner,
			.owner_task = (unsigned long)batch->release_owner.task,
			.object = (unsigned long)batch->lock, .related = (unsigned long)head,
			.phase = KD_MUTEX_SELECTED_PROXY, .result = outcome,
			.flags = node_observation_flags(node));
		/*
		 * The requester may now follow current S_W, but result alone is
		 * neither source-grant release nor permission to reuse this node.
		 */
		publish_condition(node, &node->result_ready);
		wait_owner_handled(node);
		batch->serving = NULL;
		count++;
	}
	*served = count;
	return 0;
}

int kd_mutex_await(struct kd_mutex_node *node, struct kd_mutex_batch *batch,
		   unsigned int proxy_limit, enum kd_mutex_outcome *outcome)
{
	int selection;
	int result;
	unsigned int served;

	might_sleep();
	if (!outcome || !batch || !node->enqueued || node->wait_started)
		return -EINVAL;
	if (batch->initialized)
		return -EBUSY;
	if (node->requester != current)
		return -EPERM;
	node->wait_started = true;
	wait_request(node);
	if (smp_load_acquire(&node->result_ready)) {
		BUG_ON(atomic_read(&node->selection) != KD_MUTEX_SELECTED_PROXY);
		*outcome = node->outcome;
		return 0;
	}
	selection = atomic_cmpxchg(&node->selection, KD_MUTEX_OFFERED,
				  KD_MUTEX_SELECTED_LOCAL);
	BUG_ON(selection != KD_MUTEX_OFFERED &&
	       selection != KD_MUTEX_SELECTED_LOCAL);
	batch->lock = node->lock;
	batch->head = node;
	batch->serving = NULL;
	batch->proxy_limit = proxy_limit;
	batch->proxy_served = 0;
	batch->head_retired = false;
	result = kd_mutex_release_owner_init(&batch->release_owner,
					     mcs_physical_unlock, batch->lock);
	BUG_ON(result || READ_ONCE(batch->lock->owner));
	WRITE_ONCE(batch->lock->owner, batch);
	batch->initialized = true;
	node->batch = batch;
	/* Actual MCS turn and physical-owner publication, not a local preclaim. */
	observe_node(KD_OBS_SELECT_LOCAL, node, batch, node,
		     KD_MUTEX_SELECTED_LOCAL, 0);
	if (node->ops && node->ops->selected_local) {
		result = node->ops->selected_local(node, node->context);
		BUG_ON(result);
	}
	/* Its local source acquisition remains pending while it serves others. */
	result = kd_mutex_combine(batch, proxy_limit, &served);
	BUG_ON(result);
	bind_grant(batch, node);
	node->outcome = KD_MUTEX_LOCAL_GRANTED;
	smp_store_release(&node->result_ready, 1);
	*outcome = KD_MUTEX_LOCAL_GRANTED;
	return 0;
}

int kd_mutex_acquire(struct kd_mutex *lock, struct kd_mutex_node *node,
		     struct kd_mutex_batch *batch, unsigned int proxy_limit,
		     enum kd_mutex_outcome *outcome)
{
	int result;

	if (!batch || !outcome)
		return -EINVAL;
	if (batch->initialized)
		return -EBUSY;
	result = kd_mutex_enqueue(lock, node);
	if (result)
		return result;
	return kd_mutex_await(node, batch, proxy_limit, outcome);
}

int kd_mutex_source_unlock(struct kd_mutex_node *node,
			   struct kd_thread_state *state,
			   struct kd_mutex_batch *active_batch,
			   const void *notifier,
			   enum kd_mutex_unlock_action *action)
{
	enum kd_mutex_unlock_route route;
	int result;

	if (!action || !READ_ONCE(node->source_granted) || node->state != state)
		return -EINVAL;
	route = active_batch == node->batch ? KD_MUTEX_UNLOCK_ROUTE_OWNER :
		KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER;
	if (route == KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER && !notifier)
		return -EINVAL;
	result = kd_mutex_release_request(&node->release, state,
					 node->acquisition, route);
	if (result)
		return result;
	if (route == KD_MUTEX_UNLOCK_ROUTE_OWNER) {
		result = kd_mutex_release_owner_handle(&node->release);
		BUG_ON(result);
		*action = node == active_batch->head ? KD_MUTEX_UNLOCK_BATCH_HEAD :
			KD_MUTEX_UNLOCK_BATCH_BODY;
	} else {
		result = kd_mutex_release_defer(&node->release, notifier);
		BUG_ON(result);
		*action = KD_MUTEX_UNLOCK_DEFERRED_PARENT;
	}
	return 0;
}

int kd_mutex_publish_outer_unwind(struct kd_mutex_node *node,
				   const void *notifier,
				   struct kd_mutex_release_owner **target)
{
	struct task_struct *task;
	int result = kd_mutex_release_publish_unwind(&node->release, notifier, target);

	if (result)
		return result;
	/* notifier still retains target/control until notification_done. */
	task = (*target)->task;
	get_task_struct(task);
	wake_retained_task(task);
	return 0;
}

int kd_mutex_outer_notification_done(struct kd_mutex_node *node,
				      const void *notifier)
{
	struct task_struct *task;
	int result;

	if (!notifier || READ_ONCE(node->release.notifier) != notifier)
		return -ESTALE;
	task = retain_owner_task(node);
	result = kd_mutex_release_notification_done(&node->release, notifier);
	wake_retained_task(task);
	return result;
}

int kd_mutex_hold_return(struct kd_mutex_node *node, const void *return_user)
{
	return kd_mutex_release_hold_return(&node->release, return_user);
}

int kd_mutex_drop_return(struct kd_mutex_node *node, const void *return_user)
{
	struct task_struct *task;
	int result;

	if (!return_user || READ_ONCE(node->release.return_user) != return_user)
		return -ESTALE;
	task = retain_owner_task(node);
	result = kd_mutex_release_drop_return(&node->release, return_user);
	wake_retained_task(task);
	return result;
}

int kd_mutex_result_consumed(struct kd_mutex_node *node, const void *result_user)
{
	struct task_struct *task;

	if (!result_user || node->requester != current)
		return -EPERM;
	if (!smp_load_acquire(&node->result_ready))
		return -EAGAIN;
	if (READ_ONCE(node->result_user) != result_user)
		return -ESTALE;
	task = retain_owner_task(node);
	if (cmpxchg(&node->result_user, result_user, NULL) != result_user) {
		wake_retained_task(task);
		return -ESTALE;
	}
	/* No node access after dropping this result user. */
	wake_retained_task(task);
	return 0;
}

int kd_mutex_grant_unlinked(struct kd_mutex_node *node, const void *grant_user)
{
	struct task_struct *task;
	int result;

	if (!grant_user || READ_ONCE(node->release.source_user) != grant_user)
		return -ESTALE;
	if (release_phase(node) != KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED)
		return -EAGAIN;
	task = retain_owner_task(node);
	result = kd_mutex_release_drop_source(&node->release, grant_user);
	wake_retained_task(task);
	return result;
}

int kd_mutex_finish_batch(struct kd_mutex_batch *batch)
{
	int result;

	if (!batch->initialized || !batch->head->source_granted)
		return -EINVAL;
	if (batch->serving)
		return -EBUSY;
	result = kd_mutex_release_finish_physical(&batch->release_owner);
	if (!result)
		batch->lock = NULL;
	/* Actual release completed; caller retains batch until reap succeeds. */
	return result;
}

static void publish_retirable(struct kd_mutex_node *node)
{
	struct task_struct *task = node->requester;
	struct kd_mutex_batch *batch = node->batch;

	/* Transfer the node's persistent task reference before final node access. */
	kd_observe(KD_OBS_NODE_RETIRE_READY, .state = (unsigned long)node->state,
		.origin = (unsigned long)node->state->origin,
		.node = (unsigned long)node, .acquisition = (unsigned long)node->acquisition,
		.owner = (unsigned long)&batch->release_owner,
		.owner_task = (unsigned long)batch->release_owner.task,
		.object = (unsigned long)node->lock, .related = (unsigned long)&node->release,
		.phase = node->release.phase, .flags = node_observation_flags(node),
		.source_user = (unsigned long)node->release.source_user,
		.return_user = (unsigned long)node->release.return_user,
		.notifier = (unsigned long)node->release.notifier);
	smp_store_release(&node->retirable, 1);
	wake_up_process(task);
	put_task_struct(task);
}

int kd_mutex_reap_batch(struct kd_mutex_batch *batch)
{
	struct kd_mutex_release_owner *owner = &batch->release_owner;
	struct kd_mutex_node *head;
	int result;

	if (!batch->initialized || owner->task != current)
		return -EPERM;
	if (owner->phase != KD_MUTEX_OWNER_PHYSICALLY_RELEASED)
		return -EAGAIN;
	head = batch->head;
	for (;;) {
		struct kd_mutex_release *release;
		struct kd_mutex_node *node = NULL;

		raw_spin_lock(&owner->guard);
		list_for_each_entry(release, &owner->obligations, owner_link) {
			struct kd_mutex_node *candidate =
				container_of(release, struct kd_mutex_node, release);

			BUG_ON(candidate->batch != batch);
			if (!smp_load_acquire(&candidate->queue_done) ||
			    smp_load_acquire(&candidate->result_user) ||
			    release->source_user || release->return_user || release->notifier)
				continue;
			node = candidate;
			break;
		}
		raw_spin_unlock(&owner->guard);
		if (!node)
			break;
		/* Only this actual owner task can remove an obligation. */
		result = kd_mutex_release_retire(&node->release);
		if (result)
			return result;
		if (node == head)
			batch->head_retired = true;
		else
			publish_retirable(node);
	}
	result = kd_mutex_release_owner_retire(owner);
	if (result)
		return result;
	BUG_ON(!batch->head_retired);
	batch->head = NULL;
	batch->initialized = false;
	/* Head storage can also contain batch: no later access to either. */
	publish_retirable(head);
	return 0;
}

void kd_mutex_wait_retirable(struct kd_mutex_node *node)
{
	might_sleep();
	for (;;) {
		set_current_state(TASK_UNINTERRUPTIBLE);
		if (smp_load_acquire(&node->retirable))
			break;
		schedule();
	}
	__set_current_state(TASK_RUNNING);
}
