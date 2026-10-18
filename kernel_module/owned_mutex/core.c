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
#include "kd_owned_mutex_cabi.h"

/*
 * Owned objects never mix Linux waiters. Their fourth low owner bit is valid
 * only when the actual kernel task type guarantees all four bits are free.
 */
static_assert(__alignof__(struct task_struct) >= 16);

/*
 * The kernel helper is not exported, and MODULE undefines its scheduler-only
 * macro. These are precisely its non-RT preempt-count operations. All callers
 * hold one preemption disable and no wait_lock/OSQ; migration may stay pinned.
 */
static void kd_owned_mutex_schedule(void)
{
	barrier();
	preempt_count_dec();
	schedule();
	preempt_disable();
}

/*
 * Private copy of scheduler __wake_q_add/wake_q_add. A queued task reference
 * survives wait-list removal and is consumed by the exported wake_up_q().
 */
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
	WRITE_ONCE(lock->adaptive_hot, false);
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

/*
 * Returns the owning task on failure, NULL on acquisition. A queued first
 * SELF waiter can request HANDOFF; only the designated owner consumes PICKUP.
 * Flag updates can race, so every failed CAS refreshes the whole owner word.
 */
static __always_inline struct task_struct *
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

/*
 * The owner cannot lose the lock while a detached delegation prefix exists.
 * Thus only the actual next owner can remove itself and clear the last flags;
 * batch detachment/rejoin must not call this acquisition-only helper.
 */
static void kd_owned_mutex_remove_waiter(struct kd_mutex *lock,
				       struct kd_owned_mutex_waiter *waiter)
{
	BUG_ON(!kd_owned_mutex_owned(lock, current));
	list_del_init(&waiter->list);
	if (list_empty(&lock->wait_list))
		atomic_long_andnot(KD_OWNED_MUTEX_FLAGS, &lock->owner);
}

static __always_inline void kd_owned_mutex_add_waiter(struct kd_mutex *lock,
				    struct kd_owned_mutex_waiter *waiter)
{
	if (waiter->kind == KD_OWNED_MUTEX_DELEGATE) {
		unsigned long guard = KD_OWNED_MUTEX_FLAG_WAITERS |
				      KD_OWNED_MUTEX_FLAG_DELEGATION;

		/*
		 * Flag the possible delegate before linking it. A racing unguarded
		 * release either wins first (publish retries acquisition), or its
		 * whole-word CAS fails and it must retain ownership for slow release.
		 * Never infer absence of private batches from public-list emptiness.
		 */
		if ((atomic_long_read(&lock->owner) & guard) != guard) {
			atomic_long_or(guard, &lock->owner);
			smp_mb__after_atomic();
		}
		list_add_tail(&waiter->list, &lock->wait_list);
		return;
	}
	list_add_tail(&waiter->list, &lock->wait_list);
	/*
	 * Publish list insertion before an owner can observe WAITERS and enter
	 * the slow unlock. This is also harmless when a private prefix exists.
	 */
	if (!(atomic_long_read(&lock->owner) & KD_OWNED_MUTEX_FLAG_WAITERS))
		atomic_long_or(KD_OWNED_MUTEX_FLAG_WAITERS, &lock->owner);
}

bool kd_owned_mutex_publish(struct kd_mutex *lock,
			    struct kd_owned_mutex_waiter *waiter)
{
	bool acquired;

	BUG_ON(waiter->task != current ||
	       waiter->kind > KD_OWNED_MUTEX_DELEGATE || !waiter->outcome);
	INIT_LIST_HEAD(&waiter->list);
	WRITE_ONCE(*waiter->outcome, KD_OWNED_MUTEX_QUEUED);
	raw_spin_lock(&lock->wait_lock);
	acquired = !kd_owned_mutex_trylock_common(lock, false);
	if (!acquired) {
		kd_owned_mutex_add_waiter(lock, waiter);
		/*
		 * Fast release can win before WAITERS is set. SELF's sleeping loop
		 * retries after enqueue; a DELEGATE needs the same retry here or
		 * there may be no owner left to grant or execute its request. The
		 * wait_lock keeps this transient entry invisible to a batch.
		 */
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
	unsigned long owner;

	BUG_ON(waiter->task != current);
	if (smp_load_acquire(waiter->outcome) != KD_OWNED_MUTEX_GRANTED)
		return false;
	/* The releaser unlinked this delegated node before publishing GRANTED.
	 * PICKUP excludes every other acquirer until this exact task consumes it.
	 * Producers may now reuse their node even while release holds wait_lock.
	 */
	owner = atomic_long_read(&lock->owner);
	for (;;) {
		if ((owner & ~KD_OWNED_MUTEX_FLAGS) != (unsigned long)current ||
		    !(owner & KD_OWNED_MUTEX_FLAG_PICKUP))
			return false;
		if (atomic_long_try_cmpxchg_acquire(&lock->owner, &owner,
						  owner & ~KD_OWNED_MUTEX_FLAG_PICKUP))
			return true;
	}
}

/*
 * Speculative task dereferences retain Linux's owner recheck and compiler
 * barrier under preemption disable (the corresponding RCU read-side period).
 */
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

/*
 * Bounded queue/owner polling before delegation resources/capture. The initial
 * retry preserves Linux acquisition of ownerless WAITERS, but an occupied
 * directed handoff state does not recruit another optimistic spinner. WAITERS
 * alone permits bounded spinning, as in the ordinary Linux owner-spin path. A zero
 * budget disables this retry entirely. Queue cancellation and OSQ unlock retain
 * their mandatory stabilization waits; this is not a wall-time bound.
 */
enum kd_owned_mutex_preflight_result
kd_owned_mutex_try_optimistic_pinned(struct kd_mutex *lock, unsigned int spins,
				   bool queued)
{
	enum kd_owned_mutex_preflight_result result =
		KD_OWNED_MUTEX_PREFLIGHT_BUSY;
	struct task_struct *owner;
	unsigned int i;

	lockdep_assert_preemption_disabled();
	if (!spins)
		return result;
	owner = kd_owned_mutex_trylock_common(lock, false);
	if (!owner)
		return KD_OWNED_MUTEX_PREFLIGHT_ACQUIRED;
	if (need_resched())
		return KD_OWNED_MUTEX_PREFLIGHT_SELF;
	/* Never dereference a stale speculative owner without the recheck. */
	if (kd_owned_mutex_owner(lock) == owner) {
		barrier();
		if (!owner_on_cpu(owner))
			return KD_OWNED_MUTEX_PREFLIGHT_SELF;
	}
	if (atomic_long_read(&lock->owner) &
	    (KD_OWNED_MUTEX_FLAG_HANDOFF | KD_OWNED_MUTEX_FLAG_PICKUP))
		return result;
	if (queued ? !kd_owned_osq_lock_bounded(&lock->osq, &spins) :
		     !kd_owned_osq_trylock(&lock->osq))
		return result;

	for (i = 0; i < spins; i++) {
		owner = kd_owned_mutex_trylock_common(lock, false);
		if (!owner) {
			result = KD_OWNED_MUTEX_PREFLIGHT_ACQUIRED;
			break;
		}
		if (need_resched()) {
			result = KD_OWNED_MUTEX_PREFLIGHT_SELF;
			break;
		}
		if (atomic_long_read(&lock->owner) &
		    (KD_OWNED_MUTEX_FLAG_HANDOFF | KD_OWNED_MUTEX_FLAG_PICKUP))
			break;
		if (kd_owned_mutex_owner(lock) == owner) {
			barrier();
			if (!owner_on_cpu(owner)) {
				result = KD_OWNED_MUTEX_PREFLIGHT_SELF;
				break;
			}
		}
		cpu_relax();
	}
	kd_owned_osq_unlock(&lock->osq);
	return result;
}

static __always_inline bool kd_owned_mutex_optimistic_spin(struct kd_mutex *lock,
					 struct kd_owned_mutex_waiter *waiter)
{
	unsigned int reuse_spins = waiter ? 0 : READ_ONCE(owned_mutex_reuse_spins);

	if (!waiter) {
		if (!kd_owned_mutex_can_spin(lock) ||
		    !kd_owned_osq_lock(&lock->osq))
			goto fail;
	}
	for (;;) {
		struct task_struct *owner =
			kd_owned_mutex_trylock_common(lock, false);

		if (!owner)
			break;
		if (!kd_owned_mutex_spin_on_owner(lock, owner))
			goto fail_unlock;
		/*
		 * Offer the releasing owner one short opportunity to reuse the
		 * protected line. Consume this budget once, never per transition;
		 * queued/handoff/delegation states and first waiters keep Linux's
		 * prompt retry. No owner identity or additional lock state survives.
		 */
		if (reuse_spins && !atomic_long_read(&lock->owner)) {
			do {
				if (need_resched())
					goto fail_unlock;
				cpu_relax();
			} while (--reuse_spins);
		} else {
			cpu_relax();
		}
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

/*
 * The ordinary C-ABI outer entry reaches this before admission, capture or
 * request resources. Match Linux's unbounded owner-running OSQ path, including
 * its reschedule on spin failure. A final exact retry observes a release during
 * OSQ cleanup or that reschedule before offering delegation instead of sleep.
 * Owner flags do not veto spinning; trylock_common alone consumes PICKUP.
 * The caller retains its one pin and can continue directly into SELF waiting.
 */
static __always_inline bool
kd_owned_mutex_try_local_pinned(struct kd_mutex *lock)
{
	lockdep_assert_preemption_disabled();
	if (!kd_owned_mutex_trylock_common(lock, false) ||
	    kd_owned_mutex_optimistic_spin(lock, NULL))
		return true;
	return !kd_owned_mutex_trylock_common(lock, false);
}

/*
 * ABI4 follows the Linux local acquisition path before any KD work. The
 * optional adaptive policy offers capture earlier when contention is high.
 * Unlike ABI2's entry-ratio policy, neither fast nor optimistic SELF
 * acquisitions update heat history. Exact source/task eligibility is checked
 * once after capture, before resources.
 *
 * Return zero only to request late capture. Every other return owns L, and
 * there is no stack waiter, OSQ ownership, pin or routing lease on return.
 */
__attribute__((noipa)) noinline notrace unsigned long
kd_owned_mutex_outer_cabi_gate(struct kd_mutex *lock, unsigned long return_ip)
{
	(void)return_ip; /* Passed from the actual outer CALL, never a C helper PC. */
	preempt_disable();
	/*
	 * Preserve local acquisition for short queues. With a crowded OSQ, offer
	 * delegation before entering its unbounded optimistic wait. Only observed
	 * crowding starts this mode; a small cohort's scheduler-induced delegate
	 * must not turn every arrival into a delegate. Draining the wait list ends
	 * this advisory mode. Exact capture/admission still happens later;
	 * this observation grants no source lease or execution permission.
	 */
	if (owned_mutex_adaptive && !owned_mutex_self_route) {
		if (READ_ONCE(lock->adaptive_hot)) {
			if (atomic_long_read(&lock->owner)) {
				preempt_enable();
				return 0;
			}
			WRITE_ONCE(lock->adaptive_hot, false);
		}
		if (kd_owned_osq_crowded(&lock->osq)) {
			WRITE_ONCE(lock->adaptive_hot, true);
			preempt_enable();
			return 0;
		}
	}
	if (kd_owned_mutex_try_local_pinned(lock))
		goto acquired;
	if (!owned_mutex_self_route) {
		preempt_enable();
		return 0;
	}
	/*
	 * Diagnostic refusal joins SELF under the same pin, without another
	 * initial optimistic pass or a stack waiter surviving this C call.
	 */
	kd_owned_mutex_lock_wait_pinned(lock);
acquired:
	preempt_enable();
	return (unsigned long)current;
}

/*
 * The caller supplies the preemption pin. Both the ordinary slow path and
 * committed local-first SELF continuation share this exact sleeping loop.
 */
noinline void kd_owned_mutex_lock_wait_pinned(struct kd_mutex *lock)
{
	struct kd_owned_mutex_waiter waiter;

	lockdep_assert_preemption_disabled();
	INIT_LIST_HEAD(&waiter.list);
	waiter.task = current;
	waiter.kind = KD_OWNED_MUTEX_SELF;
	waiter.state = KD_OWNED_MUTEX_QUEUED;
	waiter.outcome = &waiter.state;
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
}

static noinline void kd_owned_mutex_lock_slow(struct kd_mutex *lock)
{
	preempt_disable();
	if (!kd_owned_mutex_trylock_common(lock, false) ||
	    kd_owned_mutex_optimistic_spin(lock, NULL))
		goto done;
	kd_owned_mutex_lock_wait_pinned(lock);
done:
	preempt_enable();
}

void kd_owned_mutex_lock_self_wait(struct kd_mutex *lock)
{
	might_sleep();
	preempt_disable();
	/*
	 * Match the Linux spin-failure reschedule before attempting acquisition,
	 * while avoiding a second initial optimistic pass after the C gate.
	 */
	if (need_resched()) {
		__set_current_state(TASK_RUNNING);
		kd_owned_mutex_schedule();
	}
	kd_owned_mutex_lock_wait_pinned(lock);
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

/*
 * Unlike Linux's untyped queue, the tagged head must be inspected before
 * clearing owner: a DELEGATE polls a grant/result and cannot race for a free
 * owner word. The wait_lock therefore precedes release on this slow path.
 * SELF retains Linux's wake-before-handoff behavior; directed release is used
 * for a delegated head, an explicit batch boundary, or a HANDOFF request.
 */
static void kd_owned_mutex_release_common(struct kd_mutex *lock, bool directed)
{
	struct kd_owned_mutex_waiter *waiter = NULL;
	u32 *outcome = NULL;
	DEFINE_WAKE_Q(wake_q);
	unsigned long owner, next;
	bool grant, delegated = false;

	raw_spin_lock(&lock->wait_lock);
	if (!list_empty(&lock->wait_list)) {
		waiter = list_first_entry(&lock->wait_list,
					  struct kd_owned_mutex_waiter, list);
		delegated = waiter->kind == KD_OWNED_MUTEX_DELEGATE;
		directed |= delegated;
		outcome = waiter->outcome;
		/*
		 * Hold the wake reference before either result publication or removal
		 * permits the producer to retire/reuse its request. No packet access
		 * is allowed after the release-store to the producer's outcome.
		 */
		kd_owned_mutex_wake_q_add(&wake_q, waiter->task);
		if (delegated) {
			list_del_init(&waiter->list);
			WRITE_ONCE(waiter->kind, KD_OWNED_MUTEX_SELF);
		}
	}
	/* A drained queue ends the advisory combining episode. A racing hint
	 * may be lost; exact ownership/grants remain entirely in owner/wait_list. */
	if (list_empty(&lock->wait_list) && READ_ONCE(lock->adaptive_hot))
		WRITE_ONCE(lock->adaptive_hot, false);
	owner = atomic_long_read(&lock->owner);
	for (;;) {
		BUG_ON((owner & ~KD_OWNED_MUTEX_FLAGS) !=
			       (unsigned long)current ||
		       (owner & KD_OWNED_MUTEX_FLAG_PICKUP));
		grant = waiter &&
			(directed || (owner & KD_OWNED_MUTEX_FLAG_HANDOFF));
		next = list_empty(&lock->wait_list) ? 0 :
			KD_OWNED_MUTEX_FLAG_WAITERS | (owner & KD_OWNED_MUTEX_FLAG_DELEGATION);
		if (grant)
			next |= (unsigned long)waiter->task | KD_OWNED_MUTEX_FLAG_PICKUP;
		if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, next))
			break;
	}
	if (grant)
		smp_store_release(outcome, KD_OWNED_MUTEX_GRANTED);
	raw_spin_unlock(&lock->wait_lock);
	wake_up_q(&wake_q);
}

void kd_owned_mutex_release(struct kd_mutex *lock)
{
	kd_owned_mutex_release_common(lock, true);
}

static void kd_owned_mutex_release_noncombining(struct kd_mutex *lock)
{
	DEFINE_WAKE_Q(wake_q);
	unsigned long owner;

	owner = atomic_long_read(&lock->owner);
	for (;;) {
		BUG_ON((owner & ~KD_OWNED_MUTEX_FLAGS) !=
			       (unsigned long)current ||
		       (owner & KD_OWNED_MUTEX_FLAG_PICKUP));
		if (owner & (KD_OWNED_MUTEX_FLAG_HANDOFF | KD_OWNED_MUTEX_FLAG_DELEGATION)) {
			kd_owned_mutex_release_common(lock, false);
			return;
		}
		/*
		 * A publisher's guard update races this entire word, never a store
		 * that could lose a flag. Success permanently gives up authority.
		 */
		if (atomic_long_try_cmpxchg_release(&lock->owner, &owner,
						  owner & KD_OWNED_MUTEX_FLAG_WAITERS)) {
			if (!(owner & KD_OWNED_MUTEX_FLAG_WAITERS))
				return;
			break;
		}
	}
	/* A newer owner may already be executing, publishing delegates or asking
	 * for HANDOFF. This former owner only wakes the current public head; it
	 * must never interpret newer flags as permission for another handoff.
	 */
	raw_spin_lock(&lock->wait_lock);
	if (!list_empty(&lock->wait_list)) {
		struct kd_owned_mutex_waiter *waiter = list_first_entry(
			&lock->wait_list, struct kd_owned_mutex_waiter, list);

		kd_owned_mutex_wake_q_add(&wake_q, waiter->task);
	}
	raw_spin_unlock(&lock->wait_lock);
	wake_up_q(&wake_q);
}

static __always_inline bool
kd_owned_mutex_unlock_borrowed(struct kd_mutex *lock, unsigned long owner)
{
	/*
	 * A FULL continuation may be running on its logical caller while the
	 * executor still physically owns this nested mutex. Its unlock is an
	 * owner-ACK request, never permission to change another task's owner word.
	 * Such a borrower differs from the physical owner, so its CAS fails
	 * without writing. Ordinary owners need no task-routing lookup.
	 */
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
	if (!(owner & KD_OWNED_MUTEX_FLAG_DELEGATION)) {
		kd_owned_mutex_release_noncombining(lock);
		return;
	}
	if (!kd_owned_mutex_combine(lock))
		kd_owned_mutex_release_noncombining(lock);
}

EXPORT_SYMBOL_GPL(kd_owned_mutex_outer_unlock_v1);

void kd_owned_mutex_unlock_v1(struct kd_mutex *lock)
{
	unsigned long owner = (unsigned long)current;

	/*
	 * Borrowed FULL unlocks have no native acquisition marker on the logical
	 * task. Their physical owner consumes its own marker when servicing ACK.
	 */
	if (kd_owned_mutex_owned(lock, current))
		kd_owned_mutex_task_leave();
	if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, 0))
		return;
	/*
	 * The last tracked ordinary lock may still be nested inside an untracked
	 * explicit outer acquisition. Combining here could execute a waiter that
	 * needs that outer lock while its owner is blocked inside this unlock.
	 * Only the explicit outer API establishes a safe batching boundary.
	 */
	if (!kd_owned_mutex_unlock_borrowed(lock, owner))
		kd_owned_mutex_release_noncombining(lock);
}

EXPORT_SYMBOL_GPL(kd_owned_mutex_unlock_v1);
