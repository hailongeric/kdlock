// SPDX-License-Identifier: GPL-2.0-only
/* Concurrent shared credits and a separately queued exclusive writer gate. */
#include <linux/bug.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/preempt.h>
#include <linux/sched.h>
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
	lock->writer_pending = false;
	lock->writer = NULL;
}

void kd_rwsem_init(struct kd_rwsem *lock) { rw_init(&lock->core); }
void kd_rwlock_init(struct kd_rwlock *lock) { rw_init(&lock->core); }

void kd_rw_read_credit_init(struct kd_rw_read_credit *credit)
{
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
		credit->active = false;
		credit->released = true;
		kd_observe(KD_OBS_READ_RELEASE, .state = (unsigned long)state,
			.origin = (unsigned long)state->origin,
			.acquisition = (unsigned long)acquisition,
			.object = (unsigned long)lock, .related = (unsigned long)credit,
			.cursor = lock->readers, .phase = KD_GRANT_PHYSICAL_READ,
			.source_user = (unsigned long)user);
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

int kd_rw_write_prepare(struct kd_rw *lock, struct kd_mutex_node *node,
		       bool atomic_wait)
{
	if (!lock || !node || node->enqueued || node->shared_read || node->rw ||
	    atomic_read(&node->selection) != KD_MUTEX_PRIVATE)
		return -EINVAL;
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

void kd_rw_writer_enter(struct kd_rw *lock, struct kd_mutex_batch *batch,
			struct kd_mutex_node *waiter)
{
	DEFINE_WAIT(wait);
	bool atomic_wait = waiter->atomic_spin;

	BUG_ON(!rw_context(atomic_wait));
	raw_spin_lock(&lock->guard);
	BUG_ON(lock->writer_pending || lock->writer);
	lock->writer_pending = true;
	raw_spin_unlock(&lock->guard);
	for (;;) {
		bool blocked = false;
		bool acquired = false;

		if (!atomic_wait)
			__set_current_state(TASK_RUNNING);
		if (waiter->ops && waiter->ops->wait_progress) {
			int result = waiter->ops->wait_progress(waiter, waiter->context, &blocked);

			BUG_ON(result);
		}
		if (!atomic_wait)
			prepare_to_wait(&lock->changed, &wait, TASK_UNINTERRUPTIBLE);
		raw_spin_lock(&lock->guard);
		if (!blocked && !lock->readers) {
			lock->writer = batch;
			lock->writer_pending = false;
			acquired = true;
		}
		raw_spin_unlock(&lock->guard);
		if (acquired)
			break;
		if (atomic_wait)
			cpu_relax();
		else if (!waiter->ops || !waiter->ops->wait_ready ||
			 !waiter->ops->wait_ready(waiter, waiter->context))
			schedule();
	}
	if (!atomic_wait)
		finish_wait(&lock->changed, &wait);
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
