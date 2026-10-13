// SPDX-License-Identifier: GPL-2.0-only
/*
 * Owned KD mutex: Linux 6.1.159 owner/OSQ/SELF wait protocol, extended with
 * typed delegation waiters. Derived from kernel/locking/mutex.c:
 * Copyright (C) 2004, 2005, 2006 Red Hat, Inc., Ingo Molnar.
 * See linux-source.json for the exact captured sources and port boundaries.
 * There is no original mutex, shadow map, or original-mutex API fallback.
 */
#include <linux/export.h>
#include <linux/sched/task.h>
#include <linux/sched/wake_q.h>
#include "kd_exec.h"
#include "kd_lock.h"
#include "kd_owned_mutex_internal.h"

/* The kernel helper is not exported, and MODULE undefines its scheduler-only
 * macro. These are precisely its non-RT preempt-count operations. All callers
 * hold one preemption disable and no wait_lock/OSQ; migration may stay pinned. */
static void kd_owned_mutex_schedule(void)
{
	barrier();
	preempt_count_dec();
	schedule();
	preempt_disable();
}

/* Private copy of scheduler __wake_q_add/wake_q_add. A queued task reference
 * survives wait-list removal and is consumed by the exported wake_up_q(). */
static void kd_owned_mutex_wake_q_add(struct wake_q_head *head,
				    struct task_struct *task)
{
	struct wake_q_node *node = &task->wake_q;

	smp_mb__before_atomic();
	if (unlikely(cmpxchg_relaxed(&node->next, NULL, WAKE_Q_TAIL)))
		return;
	*head->lastp = node;
	head->lastp = &node->next;
	get_task_struct(task);
}

void kd_mutex_init(struct kd_mutex *lock)
{
	atomic_long_set(&lock->owner, 0);
	raw_spin_lock_init(&lock->wait_lock);
	atomic_set(&lock->osq.tail, OSQ_UNLOCKED_VAL);
	INIT_LIST_HEAD(&lock->wait_list);
}
EXPORT_SYMBOL_GPL(kd_mutex_init);

bool kd_mutex_is_locked(struct kd_mutex *lock)
{
	return kd_owned_mutex_owner(lock) != NULL;
}
EXPORT_SYMBOL_GPL(kd_mutex_is_locked);

bool kd_owned_mutex_is_idle(struct kd_mutex *lock)
{
	return !atomic_long_read(&lock->owner) &&
	       list_empty(&lock->wait_list) &&
	       atomic_read(&lock->osq.tail) == OSQ_UNLOCKED_VAL;
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_is_idle);

/* Returns the owning task on failure, NULL on acquisition. A queued first
 * SELF waiter can request HANDOFF; only the designated owner consumes PICKUP.
 * Flag updates can race, so every failed CAS refreshes the whole owner word. */
static struct task_struct *
kd_owned_mutex_trylock_common(struct kd_mutex *lock, bool handoff)
{
	unsigned long owner = atomic_long_read(&lock->owner);
	unsigned long curr = (unsigned long)current;

	for (;;) {
		unsigned long flags = owner & KD_OWNED_MUTEX_FLAGS;
		unsigned long task = owner & ~KD_OWNED_MUTEX_FLAGS;

		if (task) {
			if (flags & KD_OWNED_MUTEX_FLAG_PICKUP) {
				if (task != curr)
					break;
				flags &= ~KD_OWNED_MUTEX_FLAG_PICKUP;
			} else if (handoff) {
				if (flags & KD_OWNED_MUTEX_FLAG_HANDOFF)
					break;
				flags |= KD_OWNED_MUTEX_FLAG_HANDOFF;
			} else {
				break;
			}
		} else {
			BUG_ON(flags & (KD_OWNED_MUTEX_FLAG_HANDOFF |
					KD_OWNED_MUTEX_FLAG_PICKUP));
			task = curr;
		}

		if (atomic_long_try_cmpxchg_acquire(&lock->owner, &owner,
						  task | flags)) {
			if (task == curr)
				return NULL;
			break;
		}
	}
	return (struct task_struct *)(owner & ~KD_OWNED_MUTEX_FLAGS);
}

int kd_mutex_trylock(struct kd_mutex *lock)
{
	if (kd_owned_mutex_trylock_common(lock, false))
		return 0;
	kd_owned_mutex_task_enter();
	return 1;
}
EXPORT_SYMBOL_GPL(kd_mutex_trylock);

static bool kd_owned_mutex_waiter_first(struct kd_mutex *lock,
				      struct kd_owned_mutex_waiter *waiter)
{
	return READ_ONCE(lock->wait_list.next) == &waiter->list;
}

/* The owner cannot lose the lock while a detached delegation prefix exists.
 * Thus only the actual next owner can remove itself and clear the last flags;
 * batch detachment/rejoin must not call this acquisition-only helper. */
static void kd_owned_mutex_remove_waiter(struct kd_mutex *lock,
				       struct kd_owned_mutex_waiter *waiter)
{
	BUG_ON(!kd_owned_mutex_owned(lock, current));
	list_del_init(&waiter->list);
	if (list_empty(&lock->wait_list))
		atomic_long_andnot(KD_OWNED_MUTEX_FLAGS, &lock->owner);
}

static void kd_owned_mutex_add_waiter(struct kd_mutex *lock,
				    struct kd_owned_mutex_waiter *waiter)
{
	list_add_tail(&waiter->list, &lock->wait_list);
	/* Publish list insertion before an owner can observe WAITERS and enter
	 * the slow unlock. This is also harmless when a private prefix exists. */
	if (!(atomic_long_read(&lock->owner) & KD_OWNED_MUTEX_FLAG_WAITERS))
		atomic_long_or(KD_OWNED_MUTEX_FLAG_WAITERS, &lock->owner);
}

bool kd_owned_mutex_publish(struct kd_mutex *lock,
			    struct kd_owned_mutex_waiter *waiter)
{
	bool acquired;

	BUG_ON(waiter->task != current ||
	       waiter->kind > KD_OWNED_MUTEX_DELEGATE);
	INIT_LIST_HEAD(&waiter->list);
	WRITE_ONCE(waiter->state, KD_OWNED_MUTEX_QUEUED);
	raw_spin_lock(&lock->wait_lock);
	acquired = !kd_owned_mutex_trylock_common(lock, false);
	if (!acquired) {
		kd_owned_mutex_add_waiter(lock, waiter);
		/* Fast release can win before WAITERS is set. SELF's sleeping loop
		 * retries after enqueue; a DELEGATE needs the same retry here or
		 * there may be no owner left to grant or execute its request. The
		 * wait_lock keeps this transient entry invisible to a batch. */
		if (!kd_owned_mutex_trylock_common(lock, false)) {
			kd_owned_mutex_remove_waiter(lock, waiter);
			acquired = true;
		}
	}
	raw_spin_unlock(&lock->wait_lock);
	return acquired;
}

bool kd_owned_mutex_pickup(struct kd_mutex *lock,
			   struct kd_owned_mutex_waiter *waiter)
{
	bool acquired = false;
	unsigned long owner;

	BUG_ON(waiter->task != current);
	raw_spin_lock(&lock->wait_lock);
	owner = atomic_long_read(&lock->owner);
	if (READ_ONCE(waiter->state) == KD_OWNED_MUTEX_GRANTED &&
	    !list_empty(&waiter->list) &&
	    (owner & ~KD_OWNED_MUTEX_FLAGS) == (unsigned long)current &&
	    (owner & KD_OWNED_MUTEX_FLAG_PICKUP)) {
		BUG_ON(waiter->kind != KD_OWNED_MUTEX_SELF);
		acquired = !kd_owned_mutex_trylock_common(lock, false);
		BUG_ON(!acquired);
		kd_owned_mutex_remove_waiter(lock, waiter);
	}
	raw_spin_unlock(&lock->wait_lock);
	return acquired;
}

/* Speculative task dereferences retain Linux's owner recheck and compiler
 * barrier under preemption disable (the corresponding RCU read-side period). */
static noinline bool kd_owned_mutex_spin_on_owner(struct kd_mutex *lock,
						 struct task_struct *owner)
{
	lockdep_assert_preemption_disabled();
	while (kd_owned_mutex_owner(lock) == owner) {
		barrier();
		if (!owner_on_cpu(owner) || need_resched())
			return false;
		cpu_relax();
	}
	return true;
}

static bool kd_owned_mutex_can_spin(struct kd_mutex *lock)
{
	struct task_struct *owner;

	lockdep_assert_preemption_disabled();
	if (need_resched())
		return false;
	owner = kd_owned_mutex_owner(lock);
	return !owner || owner_on_cpu(owner);
}

static bool kd_owned_mutex_optimistic_spin(struct kd_mutex *lock,
					 struct kd_owned_mutex_waiter *waiter)
{
	if (!waiter) {
		if (!kd_owned_mutex_can_spin(lock) ||
		    !kd_owned_osq_lock(&lock->osq))
			goto fail;
	}
	for (;;) {
		struct task_struct *owner = kd_owned_mutex_trylock_common(lock, false);

		if (!owner)
			break;
		if (!kd_owned_mutex_spin_on_owner(lock, owner))
			goto fail_unlock;
		cpu_relax();
	}
	if (!waiter)
		kd_owned_osq_unlock(&lock->osq);
	return true;

fail_unlock:
	if (!waiter)
		kd_owned_osq_unlock(&lock->osq);
fail:
	if (need_resched()) {
		__set_current_state(TASK_RUNNING);
		kd_owned_mutex_schedule();
	}
	return false;
}

static noinline void kd_owned_mutex_lock_slow(struct kd_mutex *lock)
{
	struct kd_owned_mutex_waiter waiter;

	preempt_disable();
	if (!kd_owned_mutex_trylock_common(lock, false) ||
	    kd_owned_mutex_optimistic_spin(lock, NULL))
		goto done;

	INIT_LIST_HEAD(&waiter.list);
	waiter.task = current;
	waiter.kind = KD_OWNED_MUTEX_SELF;
	waiter.state = KD_OWNED_MUTEX_QUEUED;
	raw_spin_lock(&lock->wait_lock);
	if (!kd_owned_mutex_trylock_common(lock, false))
		goto unlock_wait;
	kd_owned_mutex_add_waiter(lock, &waiter);
	set_current_state(TASK_UNINTERRUPTIBLE);
	for (;;) {
		bool first;

		if (!kd_owned_mutex_trylock_common(lock, false))
			goto acquired;
		raw_spin_unlock(&lock->wait_lock);
		kd_owned_mutex_schedule();
		first = kd_owned_mutex_waiter_first(lock, &waiter);
		set_current_state(TASK_UNINTERRUPTIBLE);
		if (!kd_owned_mutex_trylock_common(lock, first))
			break;
		if (first && kd_owned_mutex_optimistic_spin(lock, &waiter))
			break;
		raw_spin_lock(&lock->wait_lock);
	}
	raw_spin_lock(&lock->wait_lock);
acquired:
	__set_current_state(TASK_RUNNING);
	kd_owned_mutex_remove_waiter(lock, &waiter);
unlock_wait:
	raw_spin_unlock(&lock->wait_lock);
done:
	preempt_enable();
}

void kd_owned_mutex_lock_self(struct kd_mutex *lock)
{
	might_sleep();
	if (!kd_owned_mutex_trylock_fast(lock))
		kd_owned_mutex_lock_slow(lock);
}

void kd_owned_mutex_lock_v1(struct kd_mutex *lock)
{
	kd_owned_mutex_task_enter();
	kd_owned_mutex_lock_self(lock);
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_lock_v1);

/* Unlike Linux's untyped queue, the tagged head must be inspected before
 * clearing owner: a DELEGATE polls a grant/result and cannot race for a free
 * owner word. The wait_lock therefore precedes release on this slow path.
 * SELF retains Linux's wake-before-handoff behavior; directed release is used
 * for a delegated head, an explicit batch boundary, or a HANDOFF request. */
static void kd_owned_mutex_release_common(struct kd_mutex *lock, bool directed)
{
	struct kd_owned_mutex_waiter *waiter = NULL;
	DEFINE_WAKE_Q(wake_q);
	unsigned long owner, next;
	bool grant;

	raw_spin_lock(&lock->wait_lock);
	if (!list_empty(&lock->wait_list)) {
		waiter = list_first_entry(&lock->wait_list,
					 struct kd_owned_mutex_waiter, list);
		directed |= waiter->kind == KD_OWNED_MUTEX_DELEGATE;
	}
	owner = atomic_long_read(&lock->owner);
	for (;;) {
		BUG_ON((owner & ~KD_OWNED_MUTEX_FLAGS) != (unsigned long)current ||
		       (owner & KD_OWNED_MUTEX_FLAG_PICKUP));
		grant = waiter && (directed || (owner & KD_OWNED_MUTEX_FLAG_HANDOFF));
		next = waiter ? KD_OWNED_MUTEX_FLAG_WAITERS : 0;
		if (grant)
			next |= (unsigned long)waiter->task | KD_OWNED_MUTEX_FLAG_PICKUP;
		if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, next))
			break;
	}
	if (waiter) {
		if (grant) {
			WRITE_ONCE(waiter->kind, KD_OWNED_MUTEX_SELF);
			smp_store_release(&waiter->state, KD_OWNED_MUTEX_GRANTED);
		}
		/* Pickup still needs wait_lock, so this task cannot retire before
		 * the wake queue acquires its independent task reference. */
		kd_owned_mutex_wake_q_add(&wake_q, waiter->task);
	}
	raw_spin_unlock(&lock->wait_lock);
	wake_up_q(&wake_q);
}

void kd_owned_mutex_release(struct kd_mutex *lock)
{
	kd_owned_mutex_release_common(lock, true);
}

static __always_inline bool
kd_owned_mutex_unlock_borrowed(struct kd_mutex *lock, unsigned long owner)
{
	/* A FULL continuation may be running on its logical caller while the
	 * executor still physically owns this nested mutex. Its unlock is an
	 * owner-ACK request, never permission to change another task's owner word.
	 * Such a borrower differs from the physical owner, so its CAS fails
	 * without writing. Ordinary owners need no task-routing lookup. */
	if ((owner & ~KD_OWNED_MUTEX_FLAGS) != (unsigned long)current) {
		if (kd_mutex_task_reroute(current) &&
		    kd_exec_native_unlock((unsigned long)lock, true))
			return true;
		BUG();
	}
	BUG_ON(owner & KD_OWNED_MUTEX_FLAG_PICKUP);
	return false;
}

void kd_owned_mutex_outer_unlock_v1(struct kd_mutex *lock)
{
	unsigned long owner = (unsigned long)current;

	if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, 0))
		return;
	if (kd_owned_mutex_unlock_borrowed(lock, owner))
		return;
	if (!kd_owned_mutex_combine(lock))
		kd_owned_mutex_release_common(lock, false);
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_outer_unlock_v1);

void kd_owned_mutex_unlock_v1(struct kd_mutex *lock)
{
	unsigned long owner = (unsigned long)current;

	/* Borrowed FULL unlocks have no native acquisition marker on the logical
	 * task. Their physical owner consumes its own marker when servicing ACK. */
	if (kd_owned_mutex_owned(lock, current))
		kd_owned_mutex_task_leave();
	if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, 0))
		return;
	/* The last tracked ordinary lock may still be nested inside an untracked
	 * explicit outer acquisition. Combining here could execute a waiter that
	 * needs that outer lock while its owner is blocked inside this unlock.
	 * Only the explicit outer API establishes a safe batching boundary. */
	if (!kd_owned_mutex_unlock_borrowed(lock, owner))
		kd_owned_mutex_release_common(lock, false);
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_unlock_v1);
