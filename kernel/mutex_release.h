/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_MUTEX_RELEASE_H
#define KDLOCK_MUTEX_RELEASE_H

#include <linux/list.h>
#include <linux/spinlock.h>

struct task_struct;
struct kd_thread_state;

typedef void (*kd_mutex_backend_unlock_fn)(void *object);

/* Private control records, not a public mutex or register-packet layout. */
enum kd_mutex_owner_phase {
	KD_MUTEX_OWNER_OPEN,
	KD_MUTEX_OWNER_RELEASE_PREPARED,
	KD_MUTEX_OWNER_PHYSICALLY_RELEASED,
	KD_MUTEX_OWNER_RETIRED,
};

enum kd_mutex_unlock_route {
	KD_MUTEX_UNLOCK_ROUTE_UNSET,
	KD_MUTEX_UNLOCK_ROUTE_OWNER,
	KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER,
};

enum kd_mutex_unlock_phase {
	KD_MUTEX_UNLOCK_HELD,
	KD_MUTEX_UNLOCK_REQUESTED,
	KD_MUTEX_UNLOCK_DEFERRED,
	KD_MUTEX_UNLOCK_UNWIND_READY,
	KD_MUTEX_UNLOCK_OWNER_HANDLED,
	KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED,
	KD_MUTEX_UNLOCK_RETIRED,
};

/*
 * One already acquired physical batch, retained on its actual owner's task.
 * obligations contains exact live acquisition records, not an aggregate count.
 * The guard orders release control only; it is not mutex family arbitration.
 */
struct kd_mutex_release_owner {
	raw_spinlock_t guard;
	struct task_struct *task;
	kd_mutex_backend_unlock_fn unlock;
	void *object;
	struct list_head obligations;
	enum kd_mutex_owner_phase phase;
};

/*
 * One logical acquisition within that physical batch. All records refer
 * directly to the original thread's one canonical state; no packet lives here.
 * Non-NULL source_user, return_user and notifier are exact outstanding users.
 * acquisition names this live acquisition, not a lock address or source site.
 * The caller keeps their identities, this record, the owner and state alive.
 */
struct kd_mutex_release {
	struct list_head owner_link;
	struct kd_mutex_release_owner *owner;
	struct kd_thread_state *state;
	const void *acquisition;
	const void *source_user;
	const void *return_user;
	const void *notifier;
	enum kd_mutex_unlock_phase phase;
	enum kd_mutex_unlock_route route;
	bool deferred;
};

/*
 * Initialize private storage only. The caller has already acquired physical
 * exclusion, retains the task/context, and must not return/free the context
 * until owner retirement succeeds. Owner/control storage and its containing
 * allocation must remain valid after the object's final release access too.
 * Bind the same backend/object that was acquired. No backend is acquired here;
 * initialization failure leaves its existing release duty with the caller.
 */
int kd_mutex_release_owner_init(struct kd_mutex_release_owner *owner,
				kd_mutex_backend_unlock_fn unlock, void *object);
int kd_mutex_release_bind(struct kd_mutex_release_owner *owner,
			 struct kd_mutex_release *release,
			 struct kd_thread_state *state,
			 const void *acquisition, const void *source_user);

/*
 * Only the exclusive current S_W executor may submit its source operation.
 * Resolve route from the exact active combiner/operation relationship first;
 * current == owner->task alone cannot identify same-task nested outer unlocks.
 * The route is published with REQUESTED, so an owner cannot consume an outer
 * request as a normal unlock before its deferred marker is installed.
 */
int kd_mutex_release_request(struct kd_mutex_release *release,
			    struct kd_thread_state *state,
			    const void *acquisition,
			    enum kd_mutex_unlock_route route);
int kd_mutex_release_defer(struct kd_mutex_release *release,
			  const void *notifier);

/*
 * Materialize the current S_W and stop its old executor before publishing
 * unwind readiness. The retained notifier then signals/unwinds to *target.
 * Finish every notification access before notification_done drops that user.
 * The helper does not switch execution, advance a cursor or release the mutex.
 */
int kd_mutex_release_publish_unwind(struct kd_mutex_release *release,
				    const void *notifier,
				    struct kd_mutex_release_owner **target);
int kd_mutex_release_notification_done(struct kd_mutex_release *release,
				       const void *notifier);
int kd_mutex_release_owner_handle(struct kd_mutex_release *release);

/* One structured child return binding at a time; bind before publishing it. */
int kd_mutex_release_hold_return(struct kd_mutex_release *release,
				 const void *return_user);
int kd_mutex_release_drop_return(struct kd_mutex_release *release,
				 const void *return_user);

/* Dropping a user is not source-unlock completion or permission to resume. */
int kd_mutex_release_drop_source(struct kd_mutex_release *release,
				 const void *source_user);

/*
 * The actual owner calls finish only at the normal batch-release point.
 * It requires all obligations handled, closes the batch, takes/clears the bound
 * backend/object and calls that complete ordinary unlock once outside guard.
 * Only after the callback returns does it record physical completion. The
 * callback must synchronously finish actual backend release and final object
 * access, without failure or mutation of these control records; merely leaving
 * the combiner role or submitting another deferred source unlock is insufficient.
 * No later helper dereferences the object.
 * Its provider/code retention and memory/context effects are caller duties.
 * A marker, owner_handle or dropped user is not physical completion. This API
 * chooses no source-resumption/object-lifetime policy for the deferred period.
 */
int kd_mutex_release_finish_physical(struct kd_mutex_release_owner *owner);
/* Only the actual owner task retires records and then its empty context. */
int kd_mutex_release_retire(struct kd_mutex_release *release);
int kd_mutex_release_owner_retire(struct kd_mutex_release_owner *owner);

#endif
