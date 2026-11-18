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
#include <linux/sched/signal.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <asm/cmpxchg.h>
#include <asm/processor.h>

#include "mutex.h"
#include "observation.h"
#include "state.h"
#include "rw.h"
#include "rw_native.h"
#include "rw_admission.h"

static void rw_queue_get(struct kd_mutex_node *node)
{
	if (node->rw && node->rw->atomic_admission && !node->rw_admission_queued) {
		kd_rw_admission_queue_get(node->rw);
		node->rw_admission_queued = true;
	}
}

static void rw_queue_put(struct kd_mutex_node *node)
{
	if (node->rw_admission_queued) {
		node->rw_admission_queued = false;
		kd_rw_admission_queue_put(node->rw);
	}
}

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
		.origin = node->state ? (unsigned long)node->state->origin : 0,
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
	struct task_struct *task;

	if (node->atomic_spin) {
		smp_store_release(condition, 1);
		return;
	}
	task = node->requester;

	get_task_struct(task);
	smp_store_release(condition, 1);
	wake_up_process(task);
	put_task_struct(task);
}

/* These are exact final-user bits. Cache independent callback/task inputs
 * before dropping this actor; another actor may publish final retirement.
 */
static void cancel_actor_done(struct kd_mutex_node *node, unsigned int actor)
{
	struct task_struct *task = node->requester;
	void (*departed)(struct kd_mutex_node *, void *) =
		node->ops ? node->ops->cancel_departed : NULL;
	void *context = node->context;
	int previous = atomic_fetch_andnot(actor, &node->cancel_users);

	BUG_ON(!(previous & actor));
	if (previous != actor)
		return;
	BUG_ON(READ_ONCE(node->admission) != KD_MUTEX_ADMISSION_CANCELLED);
	node->grant_user = NULL;
	observe_node(KD_OBS_NODE_RETIRE_READY, node, NULL, NULL,
		KD_MUTEX_SELECTED_CANCELLED, 0);
	smp_store_release(&node->retirable, 1);
	wake_up_process(task);
	put_task_struct(task);
	/* The configured independent canceled-control hold retains this call.
	 * Its completion may free backing; no node/context access follows.
	 */
	if (departed)
		departed(node, context);
}

static void cancel_queue_depart(struct kd_mutex_node *node)
{
	if (!smp_load_acquire(&node->queue_done)) {
		rw_queue_put(node);
		smp_store_release(&node->queue_done, 1);
		observe_node(KD_OBS_QUEUE_DONE, node, NULL, NULL,
			KD_MUTEX_SELECTED_CANCELLED, 0);
	}
	cancel_actor_done(node, KD_MUTEX_CANCEL_QUEUE);
}

/* Claim one result publication under the same guard as admission. Result is
 * source completion only; an unlinked/canceled queue actor can remain retained.
 */
static void complete_cancel(struct kd_mutex_node *node)
{
	bool publish = false;

	raw_spin_lock(&node->rw->guard);
	if (node->admission == KD_MUTEX_ADMISSION_CANCELLED &&
	    !node->borrow_active && !node->cancel_result_claimed &&
	    (!node->turn_owned || smp_load_acquire(&node->queue_done))) {
		node->cancel_result_claimed = true;
		node->outcome = KD_MUTEX_ACQUIRE_CANCELLED;
		publish = true;
	}
	raw_spin_unlock(&node->rw->guard);
	if (publish)
		publish_condition(node, &node->result_ready);
}

static bool request_cancel(struct kd_mutex_node *node)
{
	struct task_struct *waiter = NULL;
	bool cancelled;

	if (node->wait_state != TASK_KILLABLE)
		return false;
	raw_spin_lock(&node->rw->guard);
	if (node->admission == KD_MUTEX_ADMISSION_PENDING &&
	    fatal_signal_pending(node->state->origin)) {
		int selection;

		node->cancel_requested = true;
		if (smp_load_acquire(&node->turn))
			node->turn_owned = true;
		if (node->borrow_active) {
			/* Only this ungranted C is canceled. Current W still finishes. */
			node->admission = KD_MUTEX_ADMISSION_CANCELLED;
		} else if (!node->turn_owned) {
			selection = atomic_cmpxchg(&node->selection, KD_MUTEX_OFFERED,
				KD_MUTEX_SELECTED_CANCELLED);
			if (selection == KD_MUTEX_SELECTED_LOCAL)
				selection = atomic_cmpxchg(&node->selection,
					KD_MUTEX_SELECTED_LOCAL, KD_MUTEX_SELECTED_CANCELLED);
			if (selection == KD_MUTEX_OFFERED || selection == KD_MUTEX_SELECTED_LOCAL ||
			    selection == KD_MUTEX_SELECTED_CANCELLED)
				node->admission = KD_MUTEX_ADMISSION_CANCELLED;
		}
		if (node->cancel_waiter) {
			waiter = node->cancel_waiter;
			get_task_struct(waiter);
		}
	}
	cancelled = node->admission == KD_MUTEX_ADMISSION_CANCELLED;
	raw_spin_unlock(&node->rw->guard);
	if (waiter) {
		wake_up_process(waiter);
		put_task_struct(waiter);
	}
	if (cancelled)
		complete_cancel(node);
	return cancelled;
}

/* A predecessor's turn claim prevents cancellation from returning before that
 * predecessor finishes its actual turn store. A canceled unclaimed node is
 * detached by this queue actor, not by its already-returned source caller.
 */
static bool select_managed_turn(struct kd_mutex_node *node)
{
	bool selected;

	if (node->wait_state != TASK_KILLABLE)
		return true;
	raw_spin_lock(&node->rw->guard);
	selected = node->admission != KD_MUTEX_ADMISSION_CANCELLED;
	if (selected)
		node->turn_owned = true;
	raw_spin_unlock(&node->rw->guard);
	return selected;
}

static unsigned int cohort_sleep_state(struct kd_mutex_batch *batch)
{
	struct kd_mutex_node *candidate = batch->candidate;

	if (!candidate || candidate->wait_state != TASK_KILLABLE)
		return TASK_UNINTERRUPTIBLE;
	if (request_cancel(candidate))
		return TASK_UNINTERRUPTIBLE;
	return TASK_KILLABLE;
}

static struct task_struct *retain_owner_task(struct kd_mutex_node *node)
{
	struct task_struct *task;

	/* Spin owners poll the release record directly. */
	if (node->atomic_spin)
		return NULL;
	task = node->batch->release_owner.task;

	/* The caller's exact result/core/return/notifier user retains the batch. */
	get_task_struct(task);
	return task;
}

static void wake_retained_task(struct task_struct *task)
{
	if (!task)
		return;
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
		if (!node->atomic_spin)
			cond_resched();
	}
}

void kd_mutex_fast_init(struct kd_mutex_fast *fast, struct task_struct *task,
		       struct kd_thread_state *state)
{
	/* Cold, unpublished root storage only. No general node constructor or
	 * extra task reference: root attachment already retains the exact task.
	 * Only next is exposed to producers; the remaining node is not an offer.
	 */
	fast->lock = NULL;
	fast->head.next = NULL;
	fast->head.atomic_spin = false;
	fast->head.requester = task;
	fast->head.state = state;
}

static void observe_fast(unsigned long kind, struct kd_mutex_fast *fast,
			 unsigned long object, unsigned long next, unsigned long flags)
{
	kd_observe(kind, .state = (unsigned long)fast->head.state,
		.origin = (unsigned long)fast->head.requester,
		.node = (unsigned long)&fast->head, .acquisition = (unsigned long)fast,
		.owner = (unsigned long)fast, .owner_task = (unsigned long)fast->head.requester,
		.object = object, .related = next, .phase = KD_MUTEX_SELECTED_LOCAL,
		.flags = flags);
}

bool kd_mutex_fast_trylock(struct kd_mutex *lock, struct kd_mutex_fast *fast)
{
	BUG_ON(!lock || fast->lock || fast->head.requester != current);
	/* The empty-tail claim is both execution selection and physical grant.
	 * On failure this head was never published; the ordinary path starts
	 * with the same unfinished source operation and its own persistent node.
	 */
	if (cmpxchg(&lock->tail, NULL, &fast->head))
		return false;
	fast->lock = lock;
	observe_fast(KD_OBS_FAST_ACQUIRE, fast, (unsigned long)lock, 0,
		     KD_OBS_FLAG_ENQUEUED);
	return true;
}

void kd_mutex_fast_unlock(struct kd_mutex_fast *fast)
{
	struct kd_mutex *lock = fast->lock;
	struct kd_mutex_node *next;
	unsigned long successor = 0;
	int selection;

	BUG_ON(!lock || fast->head.requester != current || READ_ONCE(lock->owner));
	next = smp_load_acquire(&fast->head.next);
	if (next || cmpxchg(&lock->tail, &fast->head, NULL) != &fast->head) {
		/* A producer can be preempted between exchange and link. Its final
		 * release store must precede reuse of our task-owned head.
		 */
		if (!next)
			next = wait_link(&fast->head);
		BUG_ON(next->native_local || next->atomic_spin || next->rw ||
		       next->wait_state != TASK_UNINTERRUPTIBLE);
		selection = atomic_cmpxchg(&next->selection, KD_MUTEX_OFFERED,
					  KD_MUTEX_SELECTED_LOCAL);
		BUG_ON(selection != KD_MUTEX_OFFERED && selection != KD_MUTEX_SELECTED_LOCAL);
		successor = (unsigned long)next;
		/* The producer's final link store has been acquired. Restore the
		 * idle head here so an empty-queue claim needs no link reset.
		 */
		WRITE_ONCE(fast->head.next, NULL);
		publish_condition(next, &next->turn);
		/* No successor access follows turn publication. */
	}
	/* No object access follows tail removal or turn publication: the next
	 * owner may already have released and destroyed it. Only scalar identity
	 * and this still-attached task's private header remain accessible.
	 */
	fast->lock = NULL;
	observe_fast(KD_OBS_FAST_RELEASE, fast, (unsigned long)lock, successor,
		     KD_OBS_FLAG_QUEUE_DONE | KD_OBS_FLAG_NODE_RETIRABLE);
}

static bool progress_wait(struct kd_mutex_node *node)
{
	bool blocked = false;
	int result;

	/* Callbacks can reschedule or finish backend release; never run them
	 * with an artificial sleep state inherited from the wait loop.
	 */
	if (!node->atomic_spin)
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
	if (node->atomic_spin) {
		while (progress_wait(node) ||
		       !(smp_load_acquire(&node->turn) || smp_load_acquire(&node->result_ready)))
			cpu_relax();
		return;
	}
	for (;;) {
		bool blocked = progress_wait(node);
		unsigned int wait_state = TASK_UNINTERRUPTIBLE;

		if (node->wait_state == TASK_KILLABLE) {
			request_cancel(node);
			raw_spin_lock(&node->rw->guard);
			if (node->admission == KD_MUTEX_ADMISSION_PENDING && !node->cancel_requested)
				wait_state = TASK_KILLABLE;
			raw_spin_unlock(&node->rw->guard);
		}
		set_current_state(wait_state);
		if (!blocked && (smp_load_acquire(&node->turn) ||
		    smp_load_acquire(&node->result_ready)))
			break;
		/* Origin fatal publication either wakes this task or is sampled
		 * before its next sleep. A sent request waits for its exact decision
		 * uninterruptibly; a granted source cannot retroactively cancel.
		 */
		if (progress_ready(node))
			continue;
		schedule();
	}
	__set_current_state(TASK_RUNNING);
}

/* Actual normal backend release, bound to this mutex at batch initialization. */
static void detach_proxy(struct kd_mutex_batch *batch, struct kd_mutex_node *node);

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
	if (batch->rw)
		kd_rw_writer_exit(batch->rw, batch, batch->conversion);
	WRITE_ONCE(lock->owner, NULL);
	for (;;) {
		next = smp_load_acquire(&head->next);
		if (!next && cmpxchg(&lock->tail, head, NULL) == head) {
			rw_queue_put(head);
			smp_store_release(&head->queue_done, 1);
			observe_node(KD_OBS_QUEUE_DONE, head, batch, NULL,
				     atomic_read(&head->selection), 0);
			return;
		}
		if (!next)
			next = wait_link(head);
		if (next->native_local ? kd_rw_native_select_turn(next->native_local) :
		    select_managed_turn(next))
			break;
		/* A canceled native caller can already have returned. Its persistent
		 * queue user survives until this exact unlink's final node access.
		 */
		if (next->native_local) {
			struct kd_rw_native_record *record = next->native_local;

			detach_proxy(batch, next);
			smp_store_release(&next->retirable, 1);
			kd_rw_native_queue_depart(record);
		} else {
			detach_proxy(batch, next);
			cancel_queue_depart(next);
		}
	}
	BUG_ON(head->atomic_spin != next->atomic_spin);
	selection = atomic_cmpxchg(&next->selection, KD_MUTEX_OFFERED,
				  KD_MUTEX_SELECTED_LOCAL);
	BUG_ON(selection != KD_MUTEX_OFFERED &&
	       selection != KD_MUTEX_SELECTED_LOCAL);
	rw_queue_put(head);
	smp_store_release(&head->queue_done, 1);
	observe_node(KD_OBS_QUEUE_DONE, head, batch, next,
		     atomic_read(&head->selection), 0);
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
	batch->cohort_active = false;
	batch->candidate = NULL;
	batch->rw = NULL;
	batch->conversion = NULL;
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
	node->native_local = NULL;
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
	node->atomic_spin = false;
	node->wait_state = TASK_UNINTERRUPTIBLE;
	node->admission = KD_MUTEX_ADMISSION_PENDING;
	node->cancel_requested = false;
	node->cancel_result_claimed = false;
	node->turn_owned = false;
	node->borrow_active = false;
	node->cancel_waiter = NULL;
	atomic_set(&node->cancel_users, 0);
	node->service_policy = KD_MUTEX_SERVICE_DEFAULT;
	node->synchronous_outer = false;
	node->rw = NULL;
	node->rw_admission_queued = false;
	node->shared_read = false;
	atomic_set(&node->read_users, 0);
	node->read_return_user = NULL;
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
	node->possible_batch = NULL;
	node->outcome = KD_MUTEX_OUTCOME_UNSET;
	node->release.owner = NULL;
	return 0;
}

int kd_mutex_node_discard(struct kd_mutex_node *node)
{
	struct task_struct *task;

	if (node->requester != current)
		return -EPERM;
	if (node->shared_read || node->enqueued ||
	    atomic_read(&node->selection) != KD_MUTEX_PRIVATE)
		return -EBUSY;
	task = node->requester;
	node->requester = NULL;
	node->result_user = NULL;
	observe_node(KD_OBS_NODE_RETIRE_READY, node, NULL, NULL, KD_MUTEX_PRIVATE, 0);
	smp_store_release(&node->retirable, 1);
	put_task_struct(task);
	return 0;
}

int kd_mutex_read_granted(struct kd_mutex_node *node)
{
	if (!node || node->requester != current || node->enqueued ||
	    node->shared_read || node->source_granted ||
	    atomic_read(&node->selection) != KD_MUTEX_PRIVATE)
		return -EINVAL;
	node->shared_read = true;
	node->source_granted = true;
	atomic_set(&node->read_users, 2);
	node->outcome = KD_MUTEX_LOCAL_GRANTED;
	smp_store_release(&node->result_ready, 1);
	return 0;
}

static bool spin_context(void)
{
	return in_task() && !irqs_disabled() && in_atomic();
}

static void link_request(struct kd_mutex *lock, struct kd_mutex_node *node,
			 enum kd_mutex_selection selection)
{
	struct kd_mutex_node *previous;

	/* Close reader admission before the first externally visible link. */
	rw_queue_get(node);
	previous = xchg(&lock->tail, node);
	if (previous) {
		/* Final previous-node access: the consumer may detach after this. */
		smp_store_release(&previous->next, node);
	} else {
		smp_store_release(&node->turn, 1);
	}
	/* The producer's final predecessor-link access has completed. */
	observe_node(KD_OBS_ENQUEUE, node, NULL, previous, selection, 0);
}

int kd_mutex_enqueue(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	enum kd_mutex_selection selection;

	if (node->native_local || node->requester != current || (node->atomic_spin && !spin_context()))
		return -EPERM;
	if (node->wait_state != TASK_UNINTERRUPTIBLE &&
	    (node->wait_state != TASK_KILLABLE || node->atomic_spin || !node->rw ||
	     node->requester != node->state->origin ||
	     node->service_policy != KD_MUTEX_SERVICE_WRITER_COHORT))
		return -EOPNOTSUPP;
	if (!lock || ((node->atomic_spin ||
	    node->service_policy == KD_MUTEX_SERVICE_WRITER_COHORT) && !node->possible_batch))
		return -EINVAL;
	if ((node->atomic_spin || node->service_policy == KD_MUTEX_SERVICE_WRITER_COHORT) &&
	    node->possible_batch->initialized)
		return -EBUSY;
	if (node->enqueued || atomic_read(&node->selection) != KD_MUTEX_PRIVATE)
		return -EALREADY;
	node->lock = lock;
	node->enqueued = true;
	selection = node->ready ? KD_MUTEX_OFFERED : KD_MUTEX_SELECTED_LOCAL;
	atomic_set(&node->selection, selection);
	link_request(lock, node, selection);
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
			rw_queue_put(node);
			smp_store_release(&node->queue_done, 1);
			observe_node(KD_OBS_QUEUE_DONE, node, batch, head,
				     node->native_local ? KD_MUTEX_SELECTED_LOCAL : KD_MUTEX_SELECTED_PROXY, 0);
			return;
		}
		next = wait_link(node);
	}
	WRITE_ONCE(head->next, next);
	/* Observing next proves its producer's final node access completed. */
	rw_queue_put(node);
	smp_store_release(&node->queue_done, 1);
	observe_node(KD_OBS_QUEUE_DONE, node, batch, head,
		     node->native_local ? KD_MUTEX_SELECTED_LOCAL : KD_MUTEX_SELECTED_PROXY, 0);
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

	if (batch->rw) {
		result = kd_rw_write_grant(batch->rw, batch, node);
		BUG_ON(result);
	}
	node->batch = batch;
	result = kd_mutex_release_bind(&batch->release_owner, &node->release,
				       node->state, node->acquisition, node->grant_user);
	BUG_ON(result);
	WRITE_ONCE(node->source_granted, true);
	observe_node(KD_OBS_GRANT, node, batch, &node->release,
		     KD_MUTEX_UNLOCK_HELD, 0);
}

static int start_batch(struct kd_mutex_node *node, struct kd_mutex_batch *batch,
			unsigned int proxy_limit, struct kd_mutex_node *candidate)
{
	int result;

	BUG_ON(batch->initialized);
	batch->lock = node->lock;
	batch->head = node;
	batch->serving = NULL;
	batch->proxy_limit = proxy_limit;
	batch->proxy_served = 0;
	batch->head_retired = false;
	batch->rw = node->rw;
	batch->conversion = NULL;
	batch->candidate = candidate;
	/* Constructor writes remain private until writer_enter publishes the
	 * physical family grant; diagnostics then see fully initialized control.
	 */
	result = kd_mutex_release_owner_init(&batch->release_owner,
					     mcs_physical_unlock, batch->lock,
					     node->atomic_spin);
	BUG_ON(result);
	batch->release_owner.single_grant = node->atomic_spin &&
		node->service_policy == KD_MUTEX_SERVICE_DEFAULT;
	batch->release_owner.early_release = node->atomic_spin || node->synchronous_outer;
	if (batch->rw) {
		result = kd_rw_writer_enter(batch->rw, batch, node);
		if (result)
			return result;
	}
	BUG_ON(READ_ONCE(batch->lock->owner));
	WRITE_ONCE(batch->lock->owner, batch);
	batch->initialized = true;
	node->batch = batch;
	return 0;
}

/* No physical writer was admitted. Pass this empty MCS turn normally without
 * running rw_writer_exit or fabricating any source release obligation.
 */
static void finish_cancelled_turn(struct kd_mutex_node *node, struct kd_mutex_batch *batch)
{
	int result;

	BUG_ON(batch->initialized || READ_ONCE(node->lock->owner));
	batch->rw = NULL;
	batch->candidate = NULL;
	node->batch = batch;
	WRITE_ONCE(node->lock->owner, batch);
	batch->initialized = true;
	result = kd_mutex_release_finish_physical(&batch->release_owner);
	BUG_ON(result);
	result = kd_mutex_release_owner_retire(&batch->release_owner);
	BUG_ON(result);
	batch->initialized = false;
	batch->head = NULL;
	batch->lock = NULL;
	node->batch = NULL;
	complete_cancel(node);
	/* Exact queue actor's last visit, including its temporary owner control. */
	cancel_queue_depart(node);
}

/*
 * The immediate successor's link store ended its use of our old head.
 * Its node becomes the physical head while we run its source. Our own
 * source offer stays stopped and ungranted until we rejoin for a new turn.
 */
static bool spin_serve_successor(struct kd_mutex_node *local)
{
	struct kd_mutex_node *node = smp_load_acquire(&local->next);
	struct kd_mutex_batch *batch;
	struct task_struct *origin;
	struct kd_thread_state *state;
	enum kd_mutex_outcome outcome;

	if (!node || !node->atomic_spin ||
	    atomic_cmpxchg(&node->selection, KD_MUTEX_OFFERED,
			   KD_MUTEX_SELECTED_PROXY) != KD_MUTEX_OFFERED)
		return false;
	BUG_ON(!node->ready || !node->ops || !node->ops->execute_proxy ||
	       !node->possible_batch || node->lock != local->lock);
	WRITE_ONCE(local->next, NULL);
	WRITE_ONCE(local->turn, 0);
	batch = node->possible_batch;
	BUG_ON(start_batch(node, batch, 0, NULL));
	observe_node(KD_OBS_SELECT_PROXY, node, batch, local,
		     KD_MUTEX_SELECTED_PROXY, 0);
	bind_grant(batch, node);
	batch->serving = node;
	state = node->state;
	origin = state->origin;
	outcome = node->ops->execute_proxy(node, node->context);
	BUG_ON(outcome < KD_MUTEX_PROXY_OPERATION_DONE ||
	       outcome > KD_MUTEX_PROXY_UNWIND_PARENT);
	node->outcome = outcome;
	kd_observe(KD_OBS_PROXY_RETURN, .state = (unsigned long)state,
		.origin = (unsigned long)origin, .node = (unsigned long)node,
		.acquisition = (unsigned long)node->acquisition,
		.owner = (unsigned long)&batch->release_owner,
		.owner_task = (unsigned long)batch->release_owner.task,
		.object = (unsigned long)node->lock, .related = (unsigned long)local,
		.phase = KD_MUTEX_SELECTED_PROXY, .result = outcome,
		.flags = node_observation_flags(node));
	batch->serving = NULL;
	/* The requester may need to run its native suffix to unlock this grant. */
	publish_condition(node, &node->result_ready);
	/* Stay off the queue while the native suffix can still need this task
	 * to release a borrowed grant. W may release this lock and acquire it
	 * again before unlocking another grant owned here.
	 */
	while (progress_wait(local))
		cpu_relax();
	link_request(local->lock, local, KD_MUTEX_SELECTED_LOCAL);
	return true;
}

static bool cohort_open(struct kd_mutex_batch *batch)
{
	struct kd_mutex_release_owner *owner = &batch->release_owner;
	bool open;

	raw_spin_lock(&owner->guard);
	open = owner->phase == KD_MUTEX_OWNER_OPEN && !owner->close_requested;
	raw_spin_unlock(&owner->guard);
	return open;
}

/* A source callback may return with a live native tail. Publish that result
 * before waiting, and keep the ungranted candidate off the writer queue.
 * Each wait also services this physical task's unrelated exact owner duties.
 */
static void wait_cohort_release(struct kd_mutex_node *node)
{
	struct kd_mutex_node *head = node->batch->head;

	for (;;) {
		bool blocked = progress_wait(head);
		enum kd_mutex_unlock_phase phase = release_phase(node);

		if ((phase == KD_MUTEX_UNLOCK_OWNER_HANDLED ||
		     phase == KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED) && !blocked)
			break;
		if (head->atomic_spin) {
			cpu_relax();
			continue;
		}
		set_current_state(cohort_sleep_state(node->batch));
		phase = release_phase(node);
		if ((phase == KD_MUTEX_UNLOCK_OWNER_HANDLED ||
		     phase == KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED) && !blocked)
			break;
		if (!progress_ready(head))
			schedule();
	}
	if (!head->atomic_spin)
		__set_current_state(TASK_RUNNING);
}

/* Unlike a mutex head, the candidate has no pending physical grant of its
 * own. First W supplies persistent cohort storage and becomes the MCS head.
 * An outer synchronous release closes this cohort even during a later body;
 * no following writer is granted after that closure. Each callback has its
 * own result/source users, while cohort_active retains the overall driver.
 */
static bool serve_writer_cohort(struct kd_mutex_node *local, unsigned int limit)
{
	struct kd_mutex_node *node = smp_load_acquire(&local->next);
	struct kd_mutex_batch *batch;
	unsigned int served = 0;
	int result;

	if (request_cancel(local) ||
	    (local->wait_state == TASK_KILLABLE && READ_ONCE(local->cancel_requested)))
		return false;
	if (!node || node->service_policy != KD_MUTEX_SERVICE_WRITER_COHORT ||
	    atomic_cmpxchg(&node->selection, KD_MUTEX_OFFERED,
			   KD_MUTEX_SELECTED_PROXY) != KD_MUTEX_OFFERED)
		return false;
	BUG_ON(!node->ready || !node->possible_batch || !node->ops ||
	       !node->ops->execute_proxy || node->lock != local->lock ||
	       node->atomic_spin != local->atomic_spin || node->rw != local->rw);
	/* The acquired successor link ended its producer's final local access.
	 * The driver actor now retains withdrawn C through current W and ACKs.
	 */
	raw_spin_lock(&local->rw->guard);
	local->borrow_active = true;
	local->turn_owned = false;
	if (local->wait_state == TASK_KILLABLE)
		atomic_or(KD_MUTEX_CANCEL_COHORT, &local->cancel_users);
	raw_spin_unlock(&local->rw->guard);
	WRITE_ONCE(local->next, NULL);
	WRITE_ONCE(local->turn, 0);
	batch = node->possible_batch;
	result = start_batch(node, batch, limit, local);
	if (result == -EINTR) {
		finish_cancelled_turn(node, batch);
		goto stopped;
	}
	BUG_ON(result);
	batch->cohort_active = true;
	for (;;) {
		struct kd_thread_state *state = node->state;
		struct task_struct *origin = state->origin;
		enum kd_mutex_outcome outcome;

		observe_node(KD_OBS_SELECT_PROXY, node, batch, local,
			     KD_MUTEX_SELECTED_PROXY, 0);
		bind_grant(batch, node);
		batch->serving = node;
		batch->proxy_served++;
		outcome = node->ops->execute_proxy(node, node->context);
		BUG_ON(outcome < KD_MUTEX_PROXY_OPERATION_DONE ||
		       outcome > KD_MUTEX_PROXY_UNWIND_PARENT);
		node->outcome = outcome;
		kd_observe(KD_OBS_PROXY_RETURN, .state = (unsigned long)state,
			.origin = (unsigned long)origin, .node = (unsigned long)node,
			.acquisition = (unsigned long)node->acquisition,
			.owner = (unsigned long)&batch->release_owner,
			.owner_task = (unsigned long)batch->release_owner.task,
			.object = (unsigned long)node->lock, .related = (unsigned long)local,
			.phase = KD_MUTEX_SELECTED_PROXY, .result = outcome,
			.flags = node_observation_flags(node));
		batch->serving = NULL;
		publish_condition(node, &node->result_ready);
		wait_cohort_release(node);
		served++;
		if (request_cancel(local) || served == limit || !cohort_open(batch))
			break;
		node = smp_load_acquire(&batch->head->next);
		if (!node || node->service_policy != KD_MUTEX_SERVICE_WRITER_COHORT ||
		    atomic_cmpxchg(&node->selection, KD_MUTEX_OFFERED,
				   KD_MUTEX_SELECTED_PROXY) != KD_MUTEX_OFFERED)
			break;
		detach_proxy(batch, node);
	}
	if (batch->release_owner.phase == KD_MUTEX_OWNER_OPEN) {
		result = kd_mutex_finish_batch(batch);
		BUG_ON(result);
	}
	batch->candidate = NULL;
	/* No batch/head access follows the last backend actor's departure. */
	batch->cohort_active = false;
stopped:
	while (progress_wait(local)) {
		cpu_relax();
		if (!local->atomic_spin)
			cond_resched();
	}
	/* Source cannot return until the current W's physical duty and driver
	 * stopped. R-read-until-C-error while this W waits R is excluded usage.
	 */
	request_cancel(local);
	raw_spin_lock(&local->rw->guard);
	local->borrow_active = false;
	raw_spin_unlock(&local->rw->guard);
	if (READ_ONCE(local->admission) == KD_MUTEX_ADMISSION_CANCELLED) {
		complete_cancel(local);
		cancel_queue_depart(local);
		cancel_actor_done(local, KD_MUTEX_CANCEL_COHORT);
	} else {
		if (local->wait_state == TASK_KILLABLE)
			cancel_actor_done(local, KD_MUTEX_CANCEL_COHORT);
		link_request(local->lock, local, KD_MUTEX_SELECTED_LOCAL);
	}
	return true;
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
	if (head->atomic_spin || head->service_policy != KD_MUTEX_SERVICE_DEFAULT)
		return -EINVAL;
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

	if (node->native_local || !outcome || !batch || !node->enqueued || node->wait_started)
		return -EINVAL;
	if (node->atomic_spin) {
		if (!spin_context() || node->possible_batch != batch)
			return -EINVAL;
	} else {
		might_sleep();
		if (node->service_policy == KD_MUTEX_SERVICE_WRITER_COHORT) {
			/* Enqueue published this exact prechecked possible batch. A
			 * predecessor may initialize it before the requester reaches
			 * await; result/selection publication now governs progress.
			 */
			if (node->possible_batch != batch)
				return -EINVAL;
		} else if (batch->initialized)
			return -EBUSY;
	}
	if (node->requester != current)
		return -EPERM;
	node->wait_started = true;
	wait_request(node);
	if (smp_load_acquire(&node->result_ready))
		goto returned;
	selection = atomic_cmpxchg(&node->selection, KD_MUTEX_OFFERED,
				  KD_MUTEX_SELECTED_LOCAL);
	BUG_ON(selection != KD_MUTEX_OFFERED && selection != KD_MUTEX_SELECTED_LOCAL);
	if (node->service_policy == KD_MUTEX_SERVICE_WRITER_COHORT && proxy_limit &&
	    serve_writer_cohort(node, proxy_limit))
		wait_request(node);
	else if (node->atomic_spin && node->service_policy == KD_MUTEX_SERVICE_DEFAULT &&
		 proxy_limit && spin_serve_successor(node))
		wait_request(node);
	if (smp_load_acquire(&node->result_ready))
		goto returned;
	result = start_batch(node, batch, node->atomic_spin ? 0 : proxy_limit, NULL);
	if (result == -EINTR) {
		finish_cancelled_turn(node, batch);
		*outcome = KD_MUTEX_ACQUIRE_CANCELLED;
		return 0;
	}
	BUG_ON(result);
	/* Actual MCS turn and physical-owner publication, not a local preclaim. */
	observe_node(KD_OBS_SELECT_LOCAL, node, batch, node, KD_MUTEX_SELECTED_LOCAL, 0);
	if (node->ops && node->ops->selected_local) {
		result = node->ops->selected_local(node, node->context);
		BUG_ON(result);
	}
	if (!node->atomic_spin && node->service_policy == KD_MUTEX_SERVICE_DEFAULT) {
		result = kd_mutex_combine(batch, proxy_limit, &served);
		BUG_ON(result);
	}
	bind_grant(batch, node);
	node->outcome = KD_MUTEX_LOCAL_GRANTED;
	smp_store_release(&node->result_ready, 1);
	*outcome = KD_MUTEX_LOCAL_GRANTED;
	return 0;
returned:
	if (node->outcome != KD_MUTEX_ACQUIRE_CANCELLED)
		BUG_ON(atomic_read(&node->selection) != KD_MUTEX_SELECTED_PROXY);
	*outcome = node->outcome;
	return 0;
}

int kd_mutex_acquire(struct kd_mutex *lock, struct kd_mutex_node *node,
		     struct kd_mutex_batch *batch, unsigned int proxy_limit,
		     enum kd_mutex_outcome *outcome)
{
	int result;

	if (!batch || !outcome ||
	    ((node->atomic_spin || node->service_policy == KD_MUTEX_SERVICE_WRITER_COHORT) &&
	     node->possible_batch != batch))
		return -EINVAL;
	if (batch->initialized)
		return -EBUSY;
	result = kd_mutex_enqueue(lock, node);
	if (result)
		return result;
	return kd_mutex_await(node, batch, proxy_limit, outcome);
}

static int spin_source_unlock(struct kd_mutex_node *node,
			      struct kd_thread_state *state,
			      enum kd_mutex_unlock_action *action)
{
	struct kd_mutex_batch *batch = node->batch;
	int result;

	if (!spin_context())
		return -EPERM;
	if (!batch || batch->head != node)
		return -EINVAL;
	result = kd_mutex_release_request(&node->release, state, node->acquisition,
					 KD_MUTEX_UNLOCK_ROUTE_ATOMIC_SYNC);
	if (result)
		return result;
	if (batch->release_owner.task == current) {
		result = kd_mutex_release_owner_handle(&node->release);
		BUG_ON(result);
		result = kd_mutex_finish_batch(batch);
		BUG_ON(result);
	} else {
		/* Other physical duties can become ready while this owner polls. */
		while (release_phase(node) != KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED) {
			progress_wait(node);
			cpu_relax();
		}
	}
	*action = KD_MUTEX_UNLOCK_ATOMIC;
	return 0;
}

int kd_mutex_source_release_sync(struct kd_mutex_node *node,
		struct kd_thread_state *state, enum kd_mutex_unlock_action *action)
{
	struct kd_mutex_batch *batch;
	struct task_struct *task;
	int result;

	if (!node || !action || !node->source_granted || node->state != state ||
	    !node->synchronous_outer || !node->batch)
		return -EINVAL;
	if (node->atomic_spin ? !spin_context() : !in_task() || irqs_disabled() || in_atomic())
		return -EPERM;
	batch = node->batch;
	result = kd_mutex_release_request(&node->release, state, node->acquisition,
					 KD_MUTEX_UNLOCK_ROUTE_SYNC);
	if (result)
		return result;
	if (batch->release_owner.task == current) {
		result = kd_mutex_release_owner_handle(&node->release);
		BUG_ON(result);
		result = kd_mutex_finish_batch(batch);
		BUG_ON(result);
	} else {
		task = retain_owner_task(node);
		wake_retained_task(task);
		for (;;) {
			progress_wait(node);
			if (release_phase(node) == KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED)
				break;
			if (node->atomic_spin) {
				cpu_relax();
				continue;
			}
			set_current_state(TASK_UNINTERRUPTIBLE);
			if (release_phase(node) == KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED)
				break;
			if (!progress_ready(node))
				schedule();
		}
		if (!node->atomic_spin)
			__set_current_state(TASK_RUNNING);
	}
	*action = KD_MUTEX_UNLOCK_SYNC;
	return 0;
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
	if (node->synchronous_outer && active_batch != node->batch)
		return kd_mutex_source_release_sync(node, state, action);
	if (node->atomic_spin && node->service_policy == KD_MUTEX_SERVICE_DEFAULT)
		return spin_source_unlock(node, state, action);
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

static void read_actor_finish(struct kd_mutex_node *node)
{
	struct task_struct *task = node->requester;
	bool wake = !node->atomic_spin;

	if (!atomic_dec_and_test(&node->read_users))
		return;
	kd_observe(KD_OBS_NODE_RETIRE_READY, .state = (unsigned long)node->state,
		.origin = (unsigned long)node->state->origin,
		.node = (unsigned long)node, .acquisition = (unsigned long)node->acquisition,
		.phase = KD_MUTEX_PRIVATE, .flags = node_observation_flags(node));
	smp_store_release(&node->retirable, 1);
	if (wake)
		wake_up_process(task);
	put_task_struct(task);
}

int kd_mutex_hold_return(struct kd_mutex_node *node, const void *return_user)
{
	if (node->shared_read) {
		if (!return_user || !READ_ONCE(node->grant_user))
			return -ESTALE;
		/* Current source custody retains the grant actor through this add. */
		atomic_inc(&node->read_users);
		if (cmpxchg(&node->read_return_user, NULL, return_user)) {
			read_actor_finish(node);
			return -EBUSY;
		}
		return 0;
	}
	return kd_mutex_release_hold_return(&node->release, return_user);
}

int kd_mutex_drop_return(struct kd_mutex_node *node, const void *return_user)
{
	struct task_struct *task;
	int result;

	if (node->shared_read) {
		if (!return_user || cmpxchg(&node->read_return_user, return_user, NULL) != return_user)
			return -ESTALE;
		read_actor_finish(node);
		return 0;
	}
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
	if (READ_ONCE(node->admission) == KD_MUTEX_ADMISSION_CANCELLED) {
		if (cmpxchg(&node->result_user, result_user, NULL) != result_user)
			return -ESTALE;
		cancel_actor_done(node, KD_MUTEX_CANCEL_RESULT);
		return 0;
	}
	task = node->shared_read ? NULL : retain_owner_task(node);
	if (cmpxchg(&node->result_user, result_user, NULL) != result_user) {
		wake_retained_task(task);
		return -ESTALE;
	}
	if (node->shared_read)
		read_actor_finish(node);
	/* No node access after dropping this result user. */
	wake_retained_task(task);
	return 0;
}

int kd_mutex_grant_unlinked(struct kd_mutex_node *node, const void *grant_user)
{
	struct task_struct *task;
	int result;

	if (node->shared_read) {
		if (!grant_user || cmpxchg(&node->grant_user, grant_user, NULL) != grant_user)
			return -ESTALE;
		read_actor_finish(node);
		return 0;
	}
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
	if (batch->serving &&
	    !(batch->release_owner.early_release && batch->release_owner.close_requested) &&
	    (!batch->head->atomic_spin || batch->serving != batch->head))
		return -EBUSY;
	if (batch->head->atomic_spin && !spin_context())
		return -EPERM;
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
	bool wake = !node->atomic_spin;

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
	if (wake)
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
	if (batch->serving || batch->cohort_active)
		return -EBUSY;
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
	if (node->atomic_spin) {
		while (!smp_load_acquire(&node->retirable))
			cpu_relax();
		return;
	}
	might_sleep();
	for (;;) {
		set_current_state(TASK_UNINTERRUPTIBLE);
		if (smp_load_acquire(&node->retirable))
			break;
		schedule();
	}
	__set_current_state(TASK_RUNNING);
}

/* These controls are scheduling/physical ownership only. No source packet,
 * execution endpoint, logical grant or release.source_user is manufactured.
 */
int kd_mutex_native_node_init(struct kd_mutex_node *node,
		struct kd_rw_native_record *record)
{
	if (!node || !record || !record->pool || !record->pool->lock)
		return -EINVAL;
	node->native_local = record;
	node->next = NULL;
	atomic_set(&node->selection, KD_MUTEX_SELECTED_LOCAL);
	node->turn = 0;
	node->queue_done = 0;
	node->result_ready = 0;
	node->retirable = 0;
	node->enqueued = false;
	node->wait_started = false;
	node->source_granted = false;
	node->ready = false;
	node->atomic_spin = false;
	node->wait_state = TASK_UNINTERRUPTIBLE;
	node->admission = KD_MUTEX_ADMISSION_PENDING;
	node->cancel_requested = false;
	node->cancel_result_claimed = false;
	node->turn_owned = false;
	node->borrow_active = false;
	node->cancel_waiter = NULL;
	atomic_set(&node->cancel_users, 0);
	node->service_policy = KD_MUTEX_SERVICE_WRITER_COHORT;
	node->synchronous_outer = true;
	node->rw = record->pool->lock;
	node->rw_admission_queued = false;
	node->shared_read = false;
	node->requester = current;
	node->state = NULL;
	node->acquisition = record;
	node->operation = NULL;
	node->grant_user = NULL;
	node->result_user = NULL;
	node->ops = NULL;
	node->context = NULL;
	node->lock = NULL;
	node->batch = NULL;
	node->possible_batch = NULL;
	node->outcome = KD_MUTEX_OUTCOME_UNSET;
	node->release.owner = NULL;
	return 0;
}

int kd_mutex_native_enqueue(struct kd_mutex *lock, struct kd_mutex_node *node,
		bool try_only)
{
	if (!lock || !node || !node->native_local || node->state ||
	    !node->rw || &node->rw->queue != lock ||
	    node->requester != current || node->enqueued)
		return -EINVAL;
	node->lock = lock;
	if (try_only) {
		rw_queue_get(node);
		if (cmpxchg(&lock->tail, NULL, node)) {
			rw_queue_put(node);
			return 0;
		}
		node->enqueued = true;
		smp_store_release(&node->turn, 1);
		observe_node(KD_OBS_ENQUEUE, node, NULL, NULL, KD_MUTEX_SELECTED_LOCAL, 0);
		return 1;
	}
	node->enqueued = true;
	link_request(lock, node, KD_MUTEX_SELECTED_LOCAL);
	return 1;
}

int kd_mutex_native_start(struct kd_mutex_node *node, struct kd_mutex_batch *batch)
{
	int result;

	if (!node || !node->native_local || node->state || !node->enqueued ||
	    node->requester != current || !smp_load_acquire(&node->turn) ||
	    batch->initialized || READ_ONCE(node->lock->owner))
		return -EINVAL;
	batch->lock = node->lock;
	batch->head = node;
	/* Native glue owns family admission/conversion, including the rwsem word. */
	batch->rw = NULL;
	result = kd_mutex_release_owner_init(&batch->release_owner,
			mcs_physical_unlock, node->lock, false);
	if (result)
		return result;
	node->batch = batch;
	WRITE_ONCE(node->lock->owner, batch);
	batch->initialized = true;
	observe_node(KD_OBS_SELECT_LOCAL, node, batch, node, KD_MUTEX_SELECTED_LOCAL, 0);
	return 0;
}

int kd_mutex_native_finish(struct kd_mutex_node *node, struct kd_mutex_batch *batch)
{
	int result;

	if (!node || !node->native_local || node->state || node->batch != batch ||
	    !batch->initialized || batch->release_owner.task != current)
		return -EINVAL;
	result = kd_mutex_release_finish_physical(&batch->release_owner);
	if (result)
		return result;
	result = kd_mutex_release_owner_retire(&batch->release_owner);
	if (result)
		return result;
	batch->initialized = false;
	batch->lock = NULL;
	smp_store_release(&node->retirable, 1);
	kd_rw_native_queue_depart(node->native_local);
	return 0;
}
