// SPDX-License-Identifier: GPL-2.0
/*
 * KD physical exclusion. Ordinary non-RT mutex and OSQ algorithms derived from
 * captured Linux 6.1.159 kernel/locking/mutex.c; see mutex/linux-source.json.
 * This owns no Linux mutex and calls no Linux mutex API. Delegation admission
 * happens before this path; the legacy delegation queue is unchanged.
 *
 * WAITERS/HANDOFF/PICKUP serialize sleeping callers and prevent a designated
 * handoff from being stolen or cancelled without pickup. wait_lock orders
 * cancellation against unlock, and the wake queue retains the task reference.
 */
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/kallsyms.h>
#include <linux/sched/task.h>
#include <linux/sched/wake_q.h>
#include "kd_mutex.h"
#include "kd_mutex_local.h"

#if defined(CONFIG_PREEMPT_RT) || defined(CONFIG_DEBUG_MUTEXES) || defined(CONFIG_DEBUG_LOCK_ALLOC)
#error "KD mutex currently supports the captured non-RT, non-lockdep configuration"
#endif

#define KD_WAITERS 1UL
#define KD_HANDOFF 2UL
#define KD_PICKUP 4UL
#define KD_FLAGS 7UL
static_assert(__alignof__(struct task_struct) >= 8);

/* Scheduler helpers are not exports in the captured external-module kernel.
 * Resolve once during provider initialization, before publishing any caller.
 * These are I/O accounting helpers, not mutex operations or object adapters.
 */
static int (*kd_io_prepare)(void);
static void (*kd_io_finish)(int);
int kd_mutex_local_runtime_init(void)
{
	kd_io_prepare = (void *)kallsyms_lookup_name("io_schedule_prepare");
	kd_io_finish = (void *)kallsyms_lookup_name("io_schedule_finish");
	return kd_io_prepare && kd_io_finish ? kd_mutex_osq_init() : -ENOENT;
}

void kd_mutex_local_runtime_exit(void)
{
	kd_mutex_osq_exit();
}

struct kd_local_waiter {
	struct list_head list;
	struct task_struct *task;
};

static struct task_struct *kd_owner(struct kd_mutex *lock)
{
	return (void *)(atomic_long_read(&lock->owner) & ~KD_FLAGS);
}

static __always_inline struct task_struct *kd_try_common(struct kd_mutex *lock, bool handoff)
{
	unsigned long owner = atomic_long_read(&lock->owner);
	unsigned long curr = (unsigned long)current;

	for (;;) {
		unsigned long flags = owner & KD_FLAGS;
		unsigned long task = owner & ~KD_FLAGS;

		if (task) {
			if (flags & KD_PICKUP) {
				if (task != curr)
					break;
				flags &= ~KD_PICKUP;
			} else if (handoff) {
				if (flags & KD_HANDOFF)
					break;
				flags |= KD_HANDOFF;
			} else {
				break;
			}
		} else {
			BUG_ON(flags & (KD_HANDOFF | KD_PICKUP));
			task = curr;
		}
		if (atomic_long_try_cmpxchg_acquire(&lock->owner, &owner, task | flags)) {
			if (task == curr)
				return NULL;
			break;
		}
	}
	return (void *)(owner & ~KD_FLAGS);
}

/* schedule_preempt_disabled and wake_q_add are not module exports. */
static void kd_local_schedule(void)
{
	barrier();
	preempt_count_dec();
	schedule();
	preempt_disable();
}

static void kd_local_wake_add(struct wake_q_head *head, struct task_struct *task)
{
	struct wake_q_node *node = &task->wake_q;

	smp_mb__before_atomic();
	if (cmpxchg_relaxed(&node->next, NULL, WAKE_Q_TAIL))
		return;
	get_task_struct(task);
	*head->lastp = node;
	head->lastp = &node->next;
}

static __always_inline bool kd_local_spin(struct kd_mutex *lock, bool waiter)
{
	struct task_struct *owner;
	bool acquired = false;

	if (!waiter) {
		if (need_resched())
			goto fail;
		owner = kd_owner(lock);
		if (owner && !owner_on_cpu(owner))
			goto fail;
		if (!kd_mutex_osq_lock(&lock->osq))
			goto fail;
	}
	for (;;) {
		owner = kd_try_common(lock, false);
		if (!owner) {
			acquired = true;
			break;
		}
		while (kd_owner(lock) == owner) {
			/* Preemption pins the RCU lifetime; recheck before dereference. */
			barrier();
			if (!owner_on_cpu(owner) || need_resched())
				goto done;
			cpu_relax();
		}
		/* Match the captured legacy optimistic-spin retry: after the owner
		 * changes, relax before trying the shared owner word again. */
		cpu_relax();
	}
done:
	if (!waiter)
		kd_mutex_osq_unlock(&lock->osq);
	if (acquired)
		return true;
fail:
	if (need_resched()) {
		__set_current_state(TASK_RUNNING);
		kd_local_schedule();
	}
	return false;
}

/* These are internal wait-list spinlocks. Use native raw-spin functions,
 * bypassing the captured kernel's public caller-clobber macro wrappers. */
static noinline int kd_local_lock_slow(struct kd_mutex *lock, unsigned int state)
{
	struct kd_local_waiter waiter = { .task = current };
	int ret = 0;

	preempt_disable();
	if (!kd_try_common(lock, false) || kd_local_spin(lock, false))
		goto out;
	_raw_spin_lock(&lock->wait_lock);
	if (!kd_try_common(lock, false))
		goto unlock;
	list_add_tail(&waiter.list, &lock->wait_list);
	if (lock->wait_list.next == &waiter.list)
		atomic_long_or(KD_WAITERS, &lock->owner);
	set_current_state(state);
	for (;;) {
		bool first;

		/* A handoff must be picked up before inspecting pending signals. */
		if (!kd_try_common(lock, false))
			break;
		if (signal_pending_state(state, current)) {
			ret = -EINTR;
			break;
		}
		_raw_spin_unlock(&lock->wait_lock);
		kd_local_schedule();
		first = READ_ONCE(lock->wait_list.next) == &waiter.list;
		set_current_state(state);
		if (!kd_try_common(lock, first) ||
		    (first && kd_local_spin(lock, true))) {
			_raw_spin_lock(&lock->wait_lock);
			break;
		}
		_raw_spin_lock(&lock->wait_lock);
	}
	__set_current_state(TASK_RUNNING);
	list_del(&waiter.list);
	if (list_empty(&lock->wait_list))
		atomic_long_andnot(KD_FLAGS, &lock->owner);
unlock:
	_raw_spin_unlock(&lock->wait_lock);
out:
	preempt_enable();
	return ret;
}

static int kd_local_lock_state(struct kd_mutex *lock, unsigned int state)
{
	unsigned long zero = 0;

	might_sleep();
	BUG_ON(kd_owner(lock) == current);
	if (!atomic_long_read(&lock->owner) &&
	    atomic_long_try_cmpxchg_acquire(&lock->owner, &zero, (unsigned long)current))
		return 0;
	return kd_local_lock_slow(lock, state);
}

void kd_mutex_local_lock(struct kd_mutex *lock)
{
	kd_local_lock_state(lock, TASK_UNINTERRUPTIBLE);
}
EXPORT_SYMBOL_GPL(kd_mutex_local_lock);

int kd_mutex_lock_interruptible(struct kd_mutex *lock)
{
	return kd_local_lock_state(lock, TASK_INTERRUPTIBLE);
}
EXPORT_SYMBOL_GPL(kd_mutex_lock_interruptible);

int kd_mutex_lock_killable(struct kd_mutex *lock)
{
	return kd_local_lock_state(lock, TASK_KILLABLE);
}
EXPORT_SYMBOL_GPL(kd_mutex_lock_killable);

void kd_mutex_lock_io(struct kd_mutex *lock)
{
	int old = kd_io_prepare();

	kd_mutex_local_lock(lock);
	kd_io_finish(old);
}
EXPORT_SYMBOL_GPL(kd_mutex_lock_io);

int kd_atomic_dec_and_mutex_lock(atomic_t *count, struct kd_mutex *lock)
{
	if (atomic_add_unless(count, -1, 1))
		return 0;
	kd_mutex_local_lock(lock);
	if (atomic_dec_and_test(count))
		return 1;
	kd_mutex_local_unlock(lock);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_atomic_dec_and_mutex_lock);

int kd_mutex_trylock(struct kd_mutex *lock)
{
	return !kd_try_common(lock, false);
}
EXPORT_SYMBOL_GPL(kd_mutex_trylock);

static noinline void kd_local_unlock_slow(struct kd_mutex *lock)
{
	unsigned long owner = atomic_long_read(&lock->owner);
	struct task_struct *next = NULL;
	DEFINE_WAKE_Q(wake_q);

	for (;;) {
		BUG_ON((owner & ~KD_FLAGS) != (unsigned long)current || (owner & KD_PICKUP));
		if (owner & KD_HANDOFF)
			break;
		if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, owner & KD_FLAGS)) {
			if (owner & KD_WAITERS)
				break;
			return;
		}
	}
	_raw_spin_lock(&lock->wait_lock);
	if (!list_empty(&lock->wait_list)) {
		next = list_first_entry(&lock->wait_list, struct kd_local_waiter, list)->task;
		kd_local_wake_add(&wake_q, next);
	}
	/* Use the saved releasing owner: a new acquirer may already own the word. */
	if (owner & KD_HANDOFF) {
		owner = atomic_long_read(&lock->owner);
		for (;;) {
			unsigned long new = (owner & KD_WAITERS) | (unsigned long)next;

			BUG_ON((owner & ~KD_FLAGS) != (unsigned long)current);
			if (next)
				new |= KD_PICKUP;
			if (atomic_long_try_cmpxchg_release(&lock->owner, &owner, new))
				break;
		}
	}
	_raw_spin_unlock(&lock->wait_lock);
	wake_up_q(&wake_q);
}

void kd_mutex_local_unlock(struct kd_mutex *lock)
{
	unsigned long owner = (unsigned long)current;

	if (!atomic_long_try_cmpxchg_release(&lock->owner, &owner, 0))
		kd_local_unlock_slow(lock);
}
EXPORT_SYMBOL_GPL(kd_mutex_local_unlock);

bool kd_mutex_is_locked(struct kd_mutex *lock)
{
	return kd_owner(lock) != NULL;
}
EXPORT_SYMBOL_GPL(kd_mutex_is_locked);

/* Call only after callers have stopped and joined, never as admission. */
bool kd_mutex_is_idle(struct kd_mutex *lock)
{
	return !atomic_long_read(&lock->owner) && !atomic_read(&lock->osq.tail) &&
		list_empty(&lock->wait_list) && !raw_spin_is_locked(&lock->wait_lock) &&
		!READ_ONCE(lock->tail) && !READ_ONCE(lock->physical_owner) &&
		!atomic_read(&lock->state) && !atomic_read(&lock->waiter_count);
}
EXPORT_SYMBOL_GPL(kd_mutex_is_idle);

void kd_mutex_destroy(struct kd_mutex *lock)
{
	WARN_ON_ONCE(!kd_mutex_is_idle(lock));
}
EXPORT_SYMBOL_GPL(kd_mutex_destroy);
