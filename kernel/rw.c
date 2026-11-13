// SPDX-License-Identifier: GPL-2.0-only
/* Concurrent shared credits and a separately queued exclusive writer gate. */
#include <linux/bug.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <asm/processor.h>

#include "rw.h"
#include "state.h"
#include "observation.h"

static void rw_init(struct kd_rw *lock)
{
	kd_mutex_init(&lock->queue);
	raw_spin_lock_init(&lock->guard);
	init_waitqueue_head(&lock->changed);
	lock->readers = 0;
	INIT_LIST_HEAD(&lock->active_reads);
	lock->writer_pending = false;
	lock->writer = NULL;
	lock->native_pool = NULL;
}

void kd_rwsem_init(struct kd_rwsem *lock) { rw_init(&lock->core); }
void kd_rwlock_init(struct kd_rwlock *lock) { rw_init(&lock->core); }

void kd_rw_read_credit_init(struct kd_rw_read_credit *credit)
{
	INIT_LIST_HEAD(&credit->active_read.link);
	credit->active_read.logical_owner = NULL;
	credit->active_read.kind = KD_RW_READ_MANAGED;
	credit->active_read.credit = credit;
	raw_spin_lock_init(&credit->guard);
	credit->lock = NULL;
	credit->state = NULL;
	credit->acquisition = NULL;
	credit->user = NULL;
	credit->active = false;
	credit->released = false;
	credit->atomic_wait = false;
}

static bool rw_context(bool atomic_wait)
{
	return in_task() && !irqs_disabled() && (atomic_wait ? in_atomic() : !in_atomic());
}

void kd_rw_fast_read_init(struct kd_rw_read_credit *credit, struct kd_thread_state *state)
{
	/* Cold attached-root preparation; no additional packet or task reference. */
	kd_rw_read_credit_init(credit);
	credit->active_read.kind = KD_RW_READ_FAST;
	credit->active_read.logical_owner = state->origin;
	credit->state = state;
	credit->acquisition = credit;
	credit->user = credit;
}

static int prepare_credit(struct kd_rw *lock, struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, struct kd_execution_binding *binding,
		const void *acquisition, const void *user, bool atomic_wait)
{
	if (!lock || !credit || !state || !acquisition || !user)
		return -EINVAL;
	if (!state || !kd_state_is_current(state, binding))
		return -EPERM;
	if (credit->lock || credit->state || credit->acquisition || credit->user ||
	    credit->active || credit->released)
		return -EALREADY;
	credit->lock = lock;
	credit->state = state;
	credit->active_read.logical_owner = state->origin;
	credit->acquisition = acquisition;
	credit->user = user;
	credit->atomic_wait = atomic_wait;
	return 0;
}

static bool credit_matches(struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, const void *acquisition, const void *user)
{
	return credit->state == state && acquisition && credit->acquisition == acquisition &&
	       user && credit->user == user;
}

int kd_rw_read_credit_check(struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, const void *acquisition,
		const void *user, bool require_active)
{
	int result = 0;

	if (!credit || !credit->lock)
		return -EINVAL;
	raw_spin_lock(&credit->guard);
	if (!credit_matches(credit, state, acquisition, user) ||
	    (require_active ? (!credit->active || credit->released) :
			     (credit->active || !credit->released)))
		result = -ESTALE;
	raw_spin_unlock(&credit->guard);
	return result;
}

int kd_rw_read_credit_unlink(struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, const void *acquisition, const void *user)
{
	/* The canonical grant/node actor owns the containing-storage hold. Keep
	 * historical scalar fields so a later actor-drop failure remains retryable.
	 * This call never reacquires a reader credit or invokes a finalizer.
	 */
	return kd_rw_read_credit_check(credit, state, acquisition, user, false);
}

static int rw_progress(bool atomic_wait, const struct kd_rw_wait_ops *ops,
		       void *context, bool *blocked)
{
	if (!atomic_wait)
		__set_current_state(TASK_RUNNING);
	*blocked = false;
	return ops && ops->progress ? ops->progress(context, blocked) : 0;
}

int kd_rw_read_acquire(struct kd_rw *lock, struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, struct kd_execution_binding *binding,
		const void *acquisition, const void *user, bool atomic_wait,
		const struct kd_rw_wait_ops *ops, void *context)
{
	DEFINE_WAIT(wait);
	int result;

	if (!rw_context(atomic_wait) || (ops && (!!ops->progress != !!ops->ready)))
		return -EPERM;
	result = prepare_credit(lock, credit, state, binding, acquisition, user, atomic_wait);
	if (result)
		return result;
	for (;;) {
		bool blocked;
		bool acquired = false;

		result = rw_progress(atomic_wait, ops, context, &blocked);
		if (result || !kd_state_is_current(state, binding)) {
			if (!result)
				result = -ESTALE;
			break;
		}
		if (!atomic_wait)
			prepare_to_wait(&lock->changed, &wait, TASK_UNINTERRUPTIBLE);
		raw_spin_lock(&lock->guard);
		if (!blocked && !lock->writer_pending && !lock->writer) {
			/* Live credits come from finite caller-preallocated records. */
			lock->readers++;
			raw_spin_lock(&credit->guard);
			credit->active = true;
			list_add_tail(&credit->active_read.link, &lock->active_reads);
			raw_spin_unlock(&credit->guard);
			kd_observe(KD_OBS_READ_ACQUIRE, .state = (unsigned long)state,
				.origin = (unsigned long)state->origin,
				.acquisition = (unsigned long)acquisition,
				.object = (unsigned long)lock, .related = (unsigned long)credit,
				.cursor = lock->readers, .phase = KD_GRANT_PHYSICAL_READ,
				.source_user = (unsigned long)user);
			acquired = true;
		}
		raw_spin_unlock(&lock->guard);
		if (acquired)
			break;
		if (atomic_wait)
			cpu_relax();
		else if (!ops || !ops->ready || !ops->ready(context))
			schedule();
	}
	if (!atomic_wait)
		finish_wait(&lock->changed, &wait);
	if (result)
		kd_rw_read_credit_init(credit);
	return result;
}

int kd_rw_read_release(struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, struct kd_execution_binding *binding,
		const void *acquisition, const void *user)
{
	struct kd_rw *lock;
	int result = 0;

	if (!kd_state_is_current(state, binding))
		return -EPERM;
	if (!credit)
		return -EINVAL;
	if (!rw_context(credit->atomic_wait))
		return -EPERM;
	/* The active credit retains the lock through its final physical release
	 * access. Failed/repeated completion checks use only credit metadata.
	 */
	raw_spin_lock(&credit->guard);
	if (!credit_matches(credit, state, acquisition, user) ||
	    !credit->active || credit->released) {
		raw_spin_unlock(&credit->guard);
		return -ESTALE;
	}
	lock = credit->lock;
	raw_spin_unlock(&credit->guard);
	raw_spin_lock(&lock->guard);
	raw_spin_lock(&credit->guard);
	if (!credit_matches(credit, state, acquisition, user) ||
	    !credit->active || credit->released || !lock->readers)
		result = -ESTALE;
	else {
		lock->readers--;
		list_del_init(&credit->active_read.link);
		credit->active = false;
		credit->released = true;
		kd_observe(KD_OBS_READ_RELEASE, .state = (unsigned long)state,
			.origin = (unsigned long)state->origin,
			.acquisition = (unsigned long)acquisition,
			.object = (unsigned long)lock, .related = (unsigned long)credit,
			.cursor = lock->readers, .phase = KD_GRANT_PHYSICAL_READ,
			.source_user = (unsigned long)user,
			.flags = credit->active_read.kind == KD_RW_READ_FAST ? KD_OBS_FLAG_FAST_READ : 0);
	}
	raw_spin_unlock(&credit->guard);
	if (!result)
		wake_up_all(&lock->changed);
	/* A draining writer cannot acquire the family guard until this final
	 * lock-object access ends. No object read follows this publication.
	 */
	raw_spin_unlock(&lock->guard);
	return result;
}

bool kd_rw_fast_read_trylock(struct kd_rw *lock, struct kd_rw_read_credit *credit)
{
	bool acquired = false;
	struct kd_thread_state *state = credit->state;

	/* Native entry already validated context, exact binding and idle duties.
	 * Only the original task can publish or consume this root-owned credit.
	 */
	BUG_ON(!lock || !state || state->origin != current || credit->lock || credit->active ||
	       credit->active_read.kind != KD_RW_READ_FAST || credit->acquisition != credit ||
	       credit->user != credit || !list_empty(&credit->active_read.link));
	raw_spin_lock(&lock->guard);
	/* Never take the shortcut across a queued writer or closed admission.
	 * A writer arriving after this check still takes this guard before it
	 * can drain/admit, and therefore observes this exact reader credit.
	 */
	if (!lock->writer_pending && !lock->writer && !READ_ONCE(lock->queue.tail)) {
		raw_spin_lock(&credit->guard);
		credit->lock = lock;
		credit->active = true;
		credit->released = false;
		lock->readers++;
		list_add_tail(&credit->active_read.link, &lock->active_reads);
		raw_spin_unlock(&credit->guard);
		kd_observe(KD_OBS_READ_ACQUIRE, .state = (unsigned long)state,
			.origin = (unsigned long)state->origin,
			.acquisition = (unsigned long)credit, .object = (unsigned long)lock,
			.related = (unsigned long)credit, .cursor = lock->readers,
			.phase = KD_GRANT_PHYSICAL_READ, .source_user = (unsigned long)credit,
			.flags = KD_OBS_FLAG_FAST_READ);
		acquired = true;
	}
	raw_spin_unlock(&lock->guard);
	/* Failure publishes no credit and consumes no source operation. */
	return acquired;
}

bool kd_rw_fast_read_is_last(struct kd_rw_read_credit *credit,
		struct kd_rw *lock, struct task_struct *task)
{
	const void *last;

	/* Owned recursive reads can place a managed/native credit after this one.
	 * Object equality alone must never consume the older fast acquisition.
	 */
	return credit && lock && credit->lock == lock &&
		kd_rw_last_owned_read(lock, task, &last) == KD_RW_READ_FAST && last == credit;
}

int kd_rw_fast_read_release(struct kd_rw_read_credit *credit,
		struct kd_thread_state *state, struct kd_execution_binding *binding)
{
	struct kd_rw *lock;
	int result;

	if (!credit || !state || state->origin != current ||
	    !kd_rw_fast_read_is_last(credit, credit->lock, current))
		return -ESTALE;
	lock = credit->lock;
	result = kd_rw_read_release(credit, state, binding, credit, credit);
	if (result)
		return result;
	/* The common release has completed wakeup and its final object unlock.
	 * Keep only scalar object identity: another owner may already destroy it.
	 * Same-task serialization and attachment retain this private credit.
	 */
	credit->lock = NULL;
	kd_observe(KD_OBS_FAST_READ_DONE, .state = (unsigned long)state,
		.origin = (unsigned long)state->origin, .acquisition = (unsigned long)credit,
		.object = (unsigned long)lock, .related = (unsigned long)credit,
		.flags = KD_OBS_FLAG_FAST_READ);
	return 0;
}

int kd_rw_write_prepare(struct kd_rw *lock, struct kd_mutex_node *node,
		       bool atomic_wait)
{
	if (!lock || !node || node->enqueued || node->shared_read || node->rw ||
	    atomic_read(&node->selection) != KD_MUTEX_PRIVATE)
		return -EINVAL;
	if (node->wait_state != TASK_UNINTERRUPTIBLE &&
	    (node->wait_state != TASK_KILLABLE || atomic_wait ||
	     node->requester != node->state->origin))
		return -EOPNOTSUPP;
	if (node->wait_state == TASK_KILLABLE)
		atomic_set(&node->cancel_users, KD_MUTEX_CANCEL_QUEUE | KD_MUTEX_CANCEL_RESULT);
	node->rw = lock;
	node->atomic_spin = atomic_wait;
	node->service_policy = KD_MUTEX_SERVICE_WRITER_COHORT;
	node->synchronous_outer = true;
	return 0;
}

int kd_rw_write_acquire(struct kd_rw *lock, struct kd_mutex_node *node,
		struct kd_mutex_batch *batch, unsigned int proxy_limit,
		enum kd_mutex_outcome *outcome)
{
	if (!lock || !node || node->rw != lock ||
	    node->service_policy != KD_MUTEX_SERVICE_WRITER_COHORT)
		return -EINVAL;
	return kd_mutex_acquire(&lock->queue, node, batch, proxy_limit, outcome);
}

/* C's canceled acquisition stays ungranted while it finishes its current W.
 * The workload excludes R retaining a read until C's error while W waits R;
 * this metadata request introduces no special handling for that pattern.
 */
static void note_candidate_cancel(struct kd_mutex_batch *batch)
{
	struct kd_mutex_node *candidate = batch->candidate;

	if (candidate && candidate->wait_state == TASK_KILLABLE &&
	    candidate->admission == KD_MUTEX_ADMISSION_PENDING &&
	    fatal_signal_pending(candidate->state->origin)) {
		candidate->cancel_requested = true;
		candidate->admission = KD_MUTEX_ADMISSION_CANCELLED;
	}
}

int kd_rw_writer_enter(struct kd_rw *lock, struct kd_mutex_batch *batch,
			struct kd_mutex_node *waiter)
{
	DEFINE_WAIT(wait);
	bool atomic_wait = waiter->atomic_spin;
	bool registered = false;
	bool wait_prepared = false;
	bool cancelled = false;

	BUG_ON(!rw_context(atomic_wait));
	raw_spin_lock(&lock->guard);
	BUG_ON(lock->writer_pending || lock->writer);
	lock->writer_pending = true;
	if (waiter->wait_state == TASK_KILLABLE) {
		BUG_ON(waiter->cancel_waiter);
		get_task_struct(current);
		waiter->cancel_waiter = current;
		registered = true;
	}
	raw_spin_unlock(&lock->guard);
	for (;;) {
		bool blocked = false;
		bool acquired = false;
		unsigned int sleep_state = TASK_UNINTERRUPTIBLE;

		if (!atomic_wait)
			__set_current_state(TASK_RUNNING);
		if (waiter->ops && waiter->ops->wait_progress) {
			int result = waiter->ops->wait_progress(waiter, waiter->context, &blocked);

			BUG_ON(result);
		}
		raw_spin_lock(&lock->guard);
		/* The MCS turn and owner progress already precede this admission.
		 * Only the first ordinary probe can avoid a wait entry; a later
		 * iteration must retain its registered wait and final cleanup.
		 * Cohort candidates retain their existing cancellation checks.
		 */
		if (!atomic_wait && !wait_prepared &&
		    waiter->wait_state == TASK_UNINTERRUPTIBLE && !batch->candidate &&
		    waiter->admission == KD_MUTEX_ADMISSION_PENDING && !blocked && !lock->readers) {
			lock->writer = batch;
			waiter->admission = KD_MUTEX_ADMISSION_GRANTED;
			atomic_set(&waiter->cancel_users, 0);
			lock->writer_pending = false;
			raw_spin_unlock(&lock->guard);
			return 0;
		}
		if (waiter->wait_state == TASK_KILLABLE && waiter->requester == current &&
		    !waiter->cancel_requested)
			sleep_state = TASK_KILLABLE;
		if (batch->candidate && batch->candidate->wait_state == TASK_KILLABLE &&
		    batch->candidate->admission == KD_MUTEX_ADMISSION_PENDING)
			sleep_state = TASK_KILLABLE;
		raw_spin_unlock(&lock->guard);
		/* Publish the physical wait before checking origin's request. A fatal
		 * signal on W either wakes this registered task or precedes this check.
		 */
		if (!atomic_wait) {
			prepare_to_wait(&lock->changed, &wait, sleep_state);
			wait_prepared = true;
		}
		raw_spin_lock(&lock->guard);
		note_candidate_cancel(batch);
		if (waiter->admission == KD_MUTEX_ADMISSION_CANCELLED) {
			cancelled = true;
		} else if (!blocked && !lock->readers) {
			/* Actual admission wins over a still-pending signal request. */
			lock->writer = batch;
			waiter->admission = KD_MUTEX_ADMISSION_GRANTED;
			atomic_set(&waiter->cancel_users, 0);
			acquired = true;
		} else if (waiter->wait_state == TASK_KILLABLE &&
			   (waiter->cancel_requested || fatal_signal_pending(waiter->state->origin))) {
			waiter->cancel_requested = true;
			waiter->admission = KD_MUTEX_ADMISSION_CANCELLED;
			cancelled = true;
		}
		if (acquired || cancelled) {
			lock->writer_pending = false;
			if (registered)
				waiter->cancel_waiter = NULL;
			if (cancelled)
				wake_up_all(&lock->changed);
		}
		raw_spin_unlock(&lock->guard);
		if (acquired || cancelled)
			break;
		if (atomic_wait)
			cpu_relax();
		else if (!waiter->ops || !waiter->ops->wait_ready ||
			 !waiter->ops->wait_ready(waiter, waiter->context))
			schedule();
	}
	if (!atomic_wait)
		finish_wait(&lock->changed, &wait);
	if (registered)
		put_task_struct(current);
	return cancelled ? -EINTR : 0;
}

int kd_rw_write_grant(struct kd_rw *lock, struct kd_mutex_batch *batch,
		struct kd_mutex_node *node)
{
	int result = 0;

	raw_spin_lock(&lock->guard);
	if (lock->writer != batch || node->rw != lock)
		result = -ESTALE;
	else if (node->admission == KD_MUTEX_ADMISSION_CANCELLED)
		result = -EINTR;
	else {
		node->admission = KD_MUTEX_ADMISSION_GRANTED;
		atomic_set(&node->cancel_users, 0);
	}
	raw_spin_unlock(&lock->guard);
	return result;
}

void kd_rw_writer_exit(struct kd_rw *lock, struct kd_mutex_batch *batch,
			struct kd_rw_read_credit *conversion)
{
	raw_spin_lock(&lock->guard);
	BUG_ON(lock->writer != batch || lock->writer_pending || lock->readers);
	if (conversion) {
		raw_spin_lock(&conversion->guard);
		BUG_ON(conversion->lock != lock || !conversion->state ||
		       !conversion->acquisition || !conversion->user ||
		       conversion->active || conversion->released);
		/* No zero-protection interval: credit exists before writer exit. */
		lock->readers = 1;
		conversion->active = true;
		list_add_tail(&conversion->active_read.link, &lock->active_reads);
		raw_spin_unlock(&conversion->guard);
	}
	lock->writer = NULL;
	if (conversion)
		kd_observe(KD_OBS_WRITE_DOWNGRADE_REAL,
			.state = (unsigned long)conversion->state,
			.origin = (unsigned long)conversion->state->origin,
			.acquisition = (unsigned long)conversion->acquisition,
			.owner = (unsigned long)&batch->release_owner,
			.owner_task = (unsigned long)batch->release_owner.task,
			.object = (unsigned long)lock, .related = (unsigned long)conversion,
			.cursor = lock->readers, .phase = KD_GRANT_PHYSICAL_READ,
			.source_user = (unsigned long)conversion->user);
	wake_up_all(&lock->changed);
	raw_spin_unlock(&lock->guard);
}

int kd_rw_write_held(struct kd_mutex_node *node, struct kd_thread_state *state)
{
	struct kd_mutex_release_owner *owner;
	int result = 0;

	if (!node || !node->rw || node->state != state || !node->source_granted ||
	    !node->batch || !(owner = node->release.owner))
		return -EINVAL;
	raw_spin_lock(&owner->guard);
	if (owner->phase != KD_MUTEX_OWNER_OPEN || owner->close_requested ||
	    node->release.state != state || node->release.phase != KD_MUTEX_UNLOCK_HELD)
		result = -ESTALE;
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_rw_write_downgrade(struct kd_mutex_node *node,
		struct kd_rw_read_credit *credit, struct kd_thread_state *state,
		struct kd_execution_binding *binding,
		const void *acquisition, const void *user)
{
	struct kd_mutex_release_owner *owner;
	enum kd_mutex_unlock_action action;
	int result;

	if (!node || !node->rw || node->acquisition != acquisition)
		return -EINVAL;
	if (node->atomic_spin)
		return -EOPNOTSUPP;
	result = kd_rw_write_held(node, state);
	if (result)
		return result;
	result = prepare_credit(node->rw, credit, state, binding, acquisition, user, false);
	if (result)
		return result;
	owner = node->release.owner;
	raw_spin_lock(&owner->guard);
	if (owner->phase != KD_MUTEX_OWNER_OPEN || owner->close_requested ||
	    node->release.phase != KD_MUTEX_UNLOCK_HELD || node->batch->conversion)
		result = -ESTALE;
	else
		node->batch->conversion = credit;
	raw_spin_unlock(&owner->guard);
	if (result) {
		kd_rw_read_credit_init(credit);
		return result;
	}
	result = kd_mutex_source_release_sync(node, state, &action);
	if (result) {
		raw_spin_lock(&owner->guard);
		node->batch->conversion = NULL;
		raw_spin_unlock(&owner->guard);
		kd_rw_read_credit_init(credit);
		return result;
	}
	return kd_rw_read_credit_check(credit, state, acquisition, user, true);
}

/* The caller's own grant retains the returned control. No lookup creates a
 * lifetime hold or authorizes releasing an unrelated or nonowner credit.
 */
enum kd_rw_read_kind kd_rw_last_owned_read(struct kd_rw *lock,
		struct task_struct *logical_task, const void **credit)
{
	struct kd_rw_read_link *entry;
	enum kd_rw_read_kind kind = KD_RW_READ_NONE;

	if (credit)
		*credit = NULL;
	if (!lock || !logical_task || !credit)
		return kind;
	raw_spin_lock(&lock->guard);
	list_for_each_entry_reverse(entry, &lock->active_reads, link) {
		if (entry->kind != KD_RW_READ_NON_OWNER &&
		    entry->logical_owner == logical_task) {
			kind = entry->kind;
			*credit = entry->credit;
			break;
		}
	}
	raw_spin_unlock(&lock->guard);
	return kind;
}
