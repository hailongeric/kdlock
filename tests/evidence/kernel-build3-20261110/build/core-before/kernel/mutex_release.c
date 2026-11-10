// SPDX-License-Identifier: GPL-2.0-only
/*
 * Retained owner control for the selected ordinary-mutex deferred unlock.
 * The protocol idea follows TCLocks bbfb9f00a12af51dff6ca291cb9829a82960c2ef,
 * src/kernel/linux-5.14.16/kernel/locking/mutex.c:809-855,475-491,295-333.
 * Its native stack switching, task fields, queue and lock word are not used.
 *
 * All helpers run in the declared sleepable task-context lane. The short guard
 * protects control records, with no source execution or scheduling under it.
 * A caller must already retain any record before accessing it or registering
 * another user. Reinitialization requires the previous exact last users to end.
 * Private error returns describe control preconditions, not mutex API results.
 */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/sched.h>

#include "mutex_release.h"

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
				kd_mutex_backend_unlock_fn unlock, void *object)
{
	if (!unlock || !object)
		return -EINVAL;
	raw_spin_lock_init(&owner->guard);
	owner->task = current;
	owner->unlock = unlock;
	owner->object = object;
	INIT_LIST_HEAD(&owner->obligations);
	owner->phase = KD_MUTEX_OWNER_OPEN;
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
		release->phase = KD_MUTEX_UNLOCK_HELD;
		release->route = KD_MUTEX_UNLOCK_ROUTE_UNSET;
		release->deferred = false;
		list_add_tail(&release->owner_link, &owner->obligations);
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
		 route != KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER)
		result = -EINVAL;
	else if (route == KD_MUTEX_UNLOCK_ROUTE_OWNER && owner->task != current)
		result = -EPERM;
	else if (release->phase != KD_MUTEX_UNLOCK_HELD)
		result = -EALREADY;
	else {
		release->route = route;
		release->phase = KD_MUTEX_UNLOCK_REQUESTED;
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
	else
		release->notifier = NULL;
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
		  release->route == KD_MUTEX_UNLOCK_ROUTE_OWNER) ||
		 (release->phase == KD_MUTEX_UNLOCK_UNWIND_READY &&
		  release->route == KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER))
		release->phase = KD_MUTEX_UNLOCK_OWNER_HANDLED;
	else
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
	else
		release->return_user = NULL;
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
	else
		release->source_user = NULL;
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

static int mark_physical(struct kd_mutex_release_owner *owner)
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
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_mutex_release_finish_physical(struct kd_mutex_release_owner *owner)
{
	kd_mutex_backend_unlock_fn unlock;
	void *object;
	int result = prepare_physical(owner, &unlock, &object);

	if (result)
		return result;
	unlock(object);
	/* All later accesses are to independently retained control, not object. */
	return mark_physical(owner);
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
		 release->source_user || release->return_user || release->notifier)
		result = -EBUSY;
	else {
		list_del_init(&release->owner_link);
		release->state = NULL;
		release->phase = KD_MUTEX_UNLOCK_RETIRED;
		WRITE_ONCE(release->owner, NULL);
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
	else
		owner->phase = KD_MUTEX_OWNER_RETIRED;
	raw_spin_unlock(&owner->guard);
	return result;
}
