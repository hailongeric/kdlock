/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KD_OWNED_MUTEX_INTERNAL_H
#define KD_OWNED_MUTEX_INTERNAL_H

#include "kd_mutex.h"

void kd_owned_mutex_lock_self(struct kd_mutex *lock);
#include <linux/sched.h>

#define KD_OWNED_MUTEX_FLAG_WAITERS 0x01UL
#define KD_OWNED_MUTEX_FLAG_HANDOFF 0x02UL
#define KD_OWNED_MUTEX_FLAG_PICKUP  0x04UL
#define KD_OWNED_MUTEX_FLAGS   0x07UL

enum kd_owned_mutex_waiter_kind {
	KD_OWNED_MUTEX_SELF = 0,
	KD_OWNED_MUTEX_DELEGATE = 1,
};

enum kd_owned_mutex_waiter_state {
	KD_OWNED_MUTEX_QUEUED = 0,
	KD_OWNED_MUTEX_GRANTED = 1,
};

/* Stack SELF waiters and persistent delegation requests share only this
 * prefix. The wait_lock protects membership, kind changes and grant state.
 * A GRANTED release store also notifies a pinned producer's polling loop. */
struct kd_owned_mutex_waiter {
	struct list_head list;
	struct task_struct *task;
	u32 kind;
	u32 state;
};
static_assert(sizeof(struct kd_owned_mutex_waiter) == 32);
static_assert(offsetof(struct kd_owned_mutex_waiter, list) == 0);

static __always_inline struct task_struct *
kd_owned_mutex_owner(struct kd_mutex *lock)
{
	return (struct task_struct *)(atomic_long_read(&lock->owner) &
				     ~KD_OWNED_MUTEX_FLAGS);
}

static __always_inline bool
kd_owned_mutex_owned(struct kd_mutex *lock, struct task_struct *task)
{
	return kd_owned_mutex_owner(lock) == task;
}

static __always_inline bool kd_owned_mutex_trylock_fast(struct kd_mutex *lock)
{
	unsigned long zero = 0;

	return atomic_long_try_cmpxchg_acquire(&lock->owner, &zero,
					     (unsigned long)current);
}

/* Publish is called before any body executes. The caller supplies task=current
 * and kind. True acquires ownership without queueing; false publishes a waiter.
 * Pickup accepts only that waiter's directed grant and consumes it once. */
bool kd_owned_mutex_publish(struct kd_mutex *lock,
			    struct kd_owned_mutex_waiter *waiter);
bool kd_owned_mutex_pickup(struct kd_mutex *lock,
			   struct kd_owned_mutex_waiter *waiter);

/* No combining: release to the exact FIFO head, converting an unstarted
 * DELEGATE to SELF. Any detached prefix must have been rejoined first. */
void kd_owned_mutex_release(struct kd_mutex *lock);

/* Protocol implementation: true means physical ownership was released;
 * false must leave ownership and the complete public queue intact. It must
 * refuse non-sleepable contexts and occupied execution frames. */
bool kd_owned_mutex_combine(struct kd_mutex *lock);

bool kd_owned_osq_lock(struct optimistic_spin_queue *lock);
void kd_owned_osq_unlock(struct optimistic_spin_queue *lock);

#endif /* KD_OWNED_MUTEX_INTERNAL_H */
