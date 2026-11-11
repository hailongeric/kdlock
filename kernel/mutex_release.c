// SPDX-License-Identifier: GPL-2.0-only
/*
 * Retained owner control for the selected ordinary-mutex deferred unlock.
 * The protocol idea follows TCLocks bbfb9f00a12af51dff6ca291cb9829a82960c2ef,
 * src/kernel/linux-5.14.16/kernel/locking/mutex.c:809-855,475-491,295-333.
 * Its native stack switching, task fields, queue and lock word are not used.
 *
 * The short guard protects mutex and atomic spin release records. Source
 * execution and scheduling take place outside it.
 * A caller must already retain any record before accessing it or registering
 * another user. Reinitialization requires the previous exact last users to end.
 * Private error returns describe control preconditions, not mutex API results.
 */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/sched.h>
#include <linux/sched/task.h>

#include "mutex_release.h"
#include "observation.h"

/* Called only with the existing owner guard held. User fields identify the
 * current membership, or the exact consumed token for a *_DROP/NOTIFY_DONE.
 * Generic release controls need not be embedded in a mutex queue node.
 */
static void observe_release(unsigned long kind, struct kd_mutex_release *release,
		struct kd_mutex_release_owner *owner, const void *source_user,
		const void *return_user, const void *notifier)
{
	kd_observe(kind, .state = (unsigned long)release->state,
		.acquisition = (unsigned long)release->acquisition,
		.owner = (unsigned long)owner, .owner_task = (unsigned long)owner->task,
		.object = (unsigned long)owner->object, .related = (unsigned long)release,
		.phase = release->phase, .result = release->route,
		.source_user = (unsigned long)source_user,
		.return_user = (unsigned long)return_user,
		.notifier = (unsigned long)notifier);
}

static int release_lock(struct kd_mutex_release *release,
			struct kd_mutex_release_owner **owner_out)
{
	struct kd_mutex_release_owner *owner = READ_ONCE(release->owner);

	if (!owner)
		return -ESTALE;
	raw_spin_lock(&owner->guard);
	if (release->owner != owner || owner->phase == KD_MUTEX_OWNER_RETIRED) {
		raw_spin_unlock(&owner->guard);
		return -ESTALE;
	}
	*owner_out = owner;
	return 0;
}

int kd_mutex_release_owner_init(struct kd_mutex_release_owner *owner,
				kd_mutex_backend_unlock_fn unlock, void *object,
				bool atomic_spin)
{
	if (!unlock || !object)
		return -EINVAL;
	raw_spin_lock_init(&owner->guard);
	owner->task = current;
	owner->unlock = unlock;
	owner->object = object;
	INIT_LIST_HEAD(&owner->obligations);
	owner->phase = KD_MUTEX_OWNER_OPEN;
	owner->atomic_spin = atomic_spin;
	owner->single_grant = atomic_spin;
	owner->early_release = atomic_spin;
	owner->close_requested = false;
	return 0;
}

int kd_mutex_release_bind(struct kd_mutex_release_owner *owner,
			 struct kd_mutex_release *release,
			 struct kd_thread_state *state,
			 const void *acquisition, const void *source_user)
{
	struct kd_mutex_release *existing;
	int result = 0;

	if (!state || !acquisition || !source_user)
		return -EINVAL;
	raw_spin_lock(&owner->guard);
	if (owner->task != current)
		result = -EPERM;
	else if (owner->phase != KD_MUTEX_OWNER_OPEN)
		result = -EBUSY;
	else if (owner->close_requested ||
		 (owner->single_grant && !list_empty(&owner->obligations)))
		result = -EBUSY;
	else {
		list_for_each_entry(existing, &owner->obligations, owner_link) {
			if (existing == release ||
			    existing->acquisition == acquisition) {
				result = -EEXIST;
				goto out;
			}
		}
		/* release is private fresh storage or has completed retirement. */
		INIT_LIST_HEAD(&release->owner_link);
		release->owner = owner;
		release->state = state;
		release->acquisition = acquisition;
		release->source_user = source_user;
		release->return_user = NULL;
		release->notifier = NULL;
		release->ack_task = NULL;
		release->phase = KD_MUTEX_UNLOCK_HELD;
		release->route = KD_MUTEX_UNLOCK_ROUTE_UNSET;
		release->deferred = false;
		list_add_tail(&release->owner_link, &owner->obligations);
		observe_release(KD_OBS_RELEASE_BIND, release, owner, release->source_user,
				release->return_user, release->notifier);
	}
out:
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_request(struct kd_mutex_release *release,
			    struct kd_thread_state *state,
			    const void *acquisition,
			    enum kd_mutex_unlock_route route)
{
	struct kd_mutex_release_owner *owner;
	int result = release_lock(release, &owner);

	if (result)
		return result;
	if (release->state != state || release->acquisition != acquisition)
		result = -ESTALE;
	else if (route != KD_MUTEX_UNLOCK_ROUTE_OWNER &&
		 route != KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER &&
		 route != KD_MUTEX_UNLOCK_ROUTE_ATOMIC_SYNC &&
		 route != KD_MUTEX_UNLOCK_ROUTE_SYNC)
		result = -EINVAL;
	else if ((route == KD_MUTEX_UNLOCK_ROUTE_ATOMIC_SYNC &&
		  (!owner->atomic_spin || !owner->single_grant)) ||
		 (route == KD_MUTEX_UNLOCK_ROUTE_SYNC && !owner->early_release) ||
		 (owner->single_grant && route != KD_MUTEX_UNLOCK_ROUTE_ATOMIC_SYNC))
		result = -EINVAL;
	else if (route == KD_MUTEX_UNLOCK_ROUTE_OWNER && owner->task != current)
		result = -EPERM;
	else if (release->phase != KD_MUTEX_UNLOCK_HELD)
		result = -EALREADY;
	else {
		release->route = route;
		release->phase = KD_MUTEX_UNLOCK_REQUESTED;
		if (route == KD_MUTEX_UNLOCK_ROUTE_SYNC && !owner->atomic_spin) {
			get_task_struct(current);
			release->ack_task = current;
		}
		if (route == KD_MUTEX_UNLOCK_ROUTE_SYNC ||
		    route == KD_MUTEX_UNLOCK_ROUTE_ATOMIC_SYNC)
			owner->close_requested = true;
		observe_release(KD_OBS_RELEASE_REQUEST, release, owner, release->source_user,
				release->return_user, release->notifier);
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_defer(struct kd_mutex_release *release,
			  const void *notifier)
{
	struct kd_mutex_release_owner *owner;
	int result;

	if (!notifier)
		return -EINVAL;
	result = release_lock(release, &owner);
	if (result)
		return result;
	if (release->route != KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER)
		result = -EINVAL;
	else if (release->phase != KD_MUTEX_UNLOCK_REQUESTED)
		result = -EALREADY;
	else {
		release->notifier = notifier;
		release->deferred = true;
		release->phase = KD_MUTEX_UNLOCK_DEFERRED;
		observe_release(KD_OBS_RELEASE_DEFER, release, owner, release->source_user,
				release->return_user, release->notifier);
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_publish_unwind(struct kd_mutex_release *release,
				    const void *notifier,
				    struct kd_mutex_release_owner **target)
{
	struct kd_mutex_release_owner *owner;
	int result;

	if (!target || !notifier)
		return -EINVAL;
	result = release_lock(release, &owner);
	if (result)
		return result;
	if (release->notifier != notifier)
		result = -ESTALE;
	else if (release->phase != KD_MUTEX_UNLOCK_DEFERRED)
		result = -EALREADY;
	else {
		/* Unlocking the guard publishes the completed export/stop first. */
		release->phase = KD_MUTEX_UNLOCK_UNWIND_READY;
		*target = owner;
		observe_release(KD_OBS_RELEASE_UNWIND, release, owner, release->source_user,
				release->return_user, release->notifier);
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_notification_done(struct kd_mutex_release *release,
				       const void *notifier)
{
	struct kd_mutex_release_owner *owner;
	int result = release_lock(release, &owner);

	if (result)
		return result;
	if (!notifier || release->notifier != notifier)
		result = -ESTALE;
	else if (release->phase == KD_MUTEX_UNLOCK_DEFERRED)
		result = -EAGAIN;
	else {
		release->notifier = NULL;
		observe_release(KD_OBS_RELEASE_NOTIFY_DONE, release, owner,
				release->source_user, release->return_user, notifier);
	}
	/* No record/notification access follows this final guard unlock. */
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_owner_handle(struct kd_mutex_release *release)
{
	struct kd_mutex_release_owner *owner;
	int result = release_lock(release, &owner);

	if (result)
		return result;
	if (owner->task != current)
		result = -EPERM;
	else if ((release->phase == KD_MUTEX_UNLOCK_REQUESTED &&
		  (release->route == KD_MUTEX_UNLOCK_ROUTE_OWNER ||
		   release->route == KD_MUTEX_UNLOCK_ROUTE_ATOMIC_SYNC ||
		   release->route == KD_MUTEX_UNLOCK_ROUTE_SYNC)) ||
		 (release->phase == KD_MUTEX_UNLOCK_UNWIND_READY &&
		  release->route == KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER)) {
		release->phase = KD_MUTEX_UNLOCK_OWNER_HANDLED;
		observe_release(KD_OBS_RELEASE_HANDLED, release, owner, release->source_user,
				release->return_user, release->notifier);
	} else
		result = -EAGAIN;
	/* OPEN remains OPEN: owner handling may continue its normal batch. */
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_hold_return(struct kd_mutex_release *release,
				 const void *return_user)
{
	struct kd_mutex_release_owner *owner;
	int result;

	if (!return_user)
		return -EINVAL;
	result = release_lock(release, &owner);
	if (result)
		return result;
	if (release->phase != KD_MUTEX_UNLOCK_HELD || release->return_user)
		result = -EBUSY;
	else
		release->return_user = return_user;
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_drop_return(struct kd_mutex_release *release,
				 const void *return_user)
{
	struct kd_mutex_release_owner *owner;
	int result = release_lock(release, &owner);

	if (result)
		return result;
	if (!return_user || release->return_user != return_user)
		result = -ESTALE;
	else {
		release->return_user = NULL;
		observe_release(KD_OBS_RELEASE_RETURN_DROP, release, owner,
				release->source_user, return_user, release->notifier);
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_drop_source(struct kd_mutex_release *release,
				 const void *source_user)
{
	struct kd_mutex_release_owner *owner;
	int result = release_lock(release, &owner);

	if (result)
		return result;
	if (!source_user || release->source_user != source_user)
		result = -ESTALE;
	else if (release->phase == KD_MUTEX_UNLOCK_HELD)
		result = -EAGAIN;
	else {
		release->source_user = NULL;
		observe_release(KD_OBS_RELEASE_SOURCE_DROP, release, owner,
				source_user, release->return_user, release->notifier);
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

static int prepare_physical(struct kd_mutex_release_owner *owner,
			    kd_mutex_backend_unlock_fn *unlock, void **object)
{
	struct kd_mutex_release *release;
	int result = 0;

	raw_spin_lock(&owner->guard);
	if (owner->task != current)
		result = -EPERM;
	else if (owner->phase != KD_MUTEX_OWNER_OPEN)
		result = -EALREADY;
	else {
		list_for_each_entry(release, &owner->obligations, owner_link) {
			if (release->phase != KD_MUTEX_UNLOCK_OWNER_HANDLED) {
				result = -EBUSY;
				break;
			}
		}
		if (!result) {
			*unlock = owner->unlock;
			*object = owner->object;
			owner->unlock = NULL;
			owner->object = NULL;
			owner->phase = KD_MUTEX_OWNER_RELEASE_PREPARED;
		}
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

static int mark_physical(struct kd_mutex_release_owner *owner,
			 kd_mutex_backend_unlock_fn unlock, void *object)
{
	struct kd_mutex_release *release;
	int result = 0;

	raw_spin_lock(&owner->guard);
	if (owner->task != current)
		result = -EPERM;
	else if (owner->phase != KD_MUTEX_OWNER_RELEASE_PREPARED)
		result = -EALREADY;
	else {
		/* The caller's actual normal backend unlock has already finished. */
		owner->phase = KD_MUTEX_OWNER_PHYSICALLY_RELEASED;
		list_for_each_entry(release, &owner->obligations, owner_link)
			release->phase = KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED;
		kd_observe(KD_OBS_PHYSICAL_END, .owner = (unsigned long)owner,
			.owner_task = (unsigned long)owner->task, .object = (unsigned long)object,
			.related = (unsigned long)unlock, .phase = owner->phase);
	}
	raw_spin_unlock(&owner->guard);
	/* Wake the exact synchronous executor, not an origin inferred from a
	 * queue node. Cache and clear each retained task before its final wake.
	 */
	if (!result) {
		for (;;) {
			struct task_struct *task = NULL;

			raw_spin_lock(&owner->guard);
			list_for_each_entry(release, &owner->obligations, owner_link) {
				if (release->ack_task) {
					task = release->ack_task;
					release->ack_task = NULL;
					break;
				}
			}
			raw_spin_unlock(&owner->guard);
			if (!task)
				break;
			wake_up_process(task);
			put_task_struct(task);
		}
	}
	return result;
}

int kd_mutex_release_finish_physical(struct kd_mutex_release_owner *owner)
{
	kd_mutex_backend_unlock_fn unlock;
	void *object;
	int result = prepare_physical(owner, &unlock, &object);

	if (result)
		return result;
	kd_observe(KD_OBS_PHYSICAL_BEGIN, .owner = (unsigned long)owner,
		.owner_task = (unsigned long)owner->task, .object = (unsigned long)object,
		.related = (unsigned long)unlock, .phase = KD_MUTEX_OWNER_RELEASE_PREPARED);
	unlock(object);
	/* All later accesses are to independently retained control, not object. */
	return mark_physical(owner, unlock, object);
}

int kd_mutex_release_retire(struct kd_mutex_release *release)
{
	struct kd_mutex_release_owner *owner;
	int result = release_lock(release, &owner);

	if (result)
		return result;
	if (owner->task != current)
		result = -EPERM;
	else if (release->phase != KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED ||
		 release->source_user || release->return_user || release->notifier ||
		 release->ack_task)
		result = -EBUSY;
	else {
		struct kd_thread_state *state = release->state;

		list_del_init(&release->owner_link);
		release->state = NULL;
		release->phase = KD_MUTEX_UNLOCK_RETIRED;
		WRITE_ONCE(release->owner, NULL);
		kd_observe(KD_OBS_RELEASE_RETIRE, .state = (unsigned long)state,
			.acquisition = (unsigned long)release->acquisition,
			.owner = (unsigned long)owner, .owner_task = (unsigned long)owner->task,
			.related = (unsigned long)release, .phase = release->phase,
			.result = release->route, .source_user = (unsigned long)release->source_user,
			.return_user = (unsigned long)release->return_user,
			.notifier = (unsigned long)release->notifier);
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_owner_retire(struct kd_mutex_release_owner *owner)
{
	int result = 0;

	raw_spin_lock(&owner->guard);
	if (owner->task != current)
		result = -EPERM;
	else if (owner->phase != KD_MUTEX_OWNER_PHYSICALLY_RELEASED ||
		 !list_empty(&owner->obligations))
		result = -EBUSY;
	else {
		owner->phase = KD_MUTEX_OWNER_RETIRED;
		kd_observe(KD_OBS_OWNER_RETIRE, .owner = (unsigned long)owner,
			.owner_task = (unsigned long)owner->task, .phase = owner->phase);
	}
	raw_spin_unlock(&owner->guard);
	return result;
}
