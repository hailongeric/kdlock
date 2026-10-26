// SPDX-License-Identifier: GPL-2.0
/* Reader/ordinary-writer/delegated-writer phases around an unchanged KD mutex. */
#include <linux/module.h>
#include <linux/limits.h>
#include "kd_rwsem.h"
#include "kd_lock.h"

#define KD_RWSEM_LOCAL_WRITER (-1L)

/* Short holders often finish before a task can enqueue and be woken. Poll only
 * before publication, with preemption enabled and at most 16384 condition probes;
 * an individual predicate retains its existing atomic retry loop. Sleeping or
 * colocated holders still get the ordinary wait_event scheduling fallback.
 * A successful condition may acquire a reservation, so never evaluate it again
 * after success. The wait macro retains its enqueue/recheck ordering. */
#define kd_rwsem_poll(condition) ({ \
	unsigned int kd_rwsem_budget = 16384; \
	bool kd_rwsem_ready = false; \
	do { \
		if (condition) { \
			kd_rwsem_ready = true; \
			break; \
		} \
		if (need_resched()) \
			break; \
		cpu_relax(); \
	} while (--kd_rwsem_budget); \
	kd_rwsem_ready; \
})

#define kd_rwsem_wait(queue, condition) do { \
	if (!kd_rwsem_poll(condition)) \
		wait_event(queue, condition); \
} while (0)

void kd_rwsem_init(struct kd_rwsem *sem)
{
	kd_mutex_init(&sem->gate);
	atomic_long_set(&sem->readers, 0);
	atomic_long_set(&sem->admission, 0);
	init_waitqueue_head(&sem->phase_wait);
	init_waitqueue_head(&sem->reader_drain);
}
EXPORT_SYMBOL_GPL(kd_rwsem_init);

static void kd_rwsem_wake_drain(struct kd_rwsem *sem)
{
	/* The fully ordered reader-count RMW pairs with enqueue/recheck,
	 * including this lockless test. Multiple delegation reservations may
	 * wait for the same drain, so all of them must be notified. */
	if (waitqueue_active(&sem->reader_drain))
		wake_up_all(&sem->reader_drain);
}

static void kd_rwsem_wake_phase(struct kd_rwsem *sem)
{
	/* Call after the fully ordered RMW that reopens admission; it pairs with
	 * enqueue/recheck, including this lockless test. Readers and delegation
	 * reservations remain nonexclusive, ahead of exclusive ordinary writers.
	 * Notify that prefix and one writer, which must still reserve admission. */
	if (waitqueue_active(&sem->phase_wait))
		wake_up(&sem->phase_wait);
}

void kd_up_read(struct kd_rwsem *sem)
{
	/* Trylock rollback and a matching read unlock may run under rq_lock.
	 * Never acquire a waitqueue/scheduler lock from that atomic context.
	 * Reader-drain waiters recheck on a timer, so omitting this wake cannot
	 * strand them. No deferred reference outlives this ordered decrement. */
	if (atomic_long_dec_and_test(&sem->readers) &&
	    !irqs_disabled() && !in_atomic())
		kd_rwsem_wake_drain(sem);
}
EXPORT_SYMBOL_GPL(kd_up_read);

static int kd_rwsem_drain_readers(struct kd_rwsem *sem, unsigned int state)
{
	long ret;

	if (state == TASK_UNINTERRUPTIBLE &&
	    kd_rwsem_poll(!atomic_long_read_acquire(&sem->readers)))
		return 0;
	/* An IRQ-disabled reader cannot safely wake a sleeping writer. Only
	 * schedulable, unpublished writers wait here; one-jiffy sleeps provide
	 * progress even when the last decrement omitted its wake. The timeout
	 * is a recheck, never permission to enter while a reader remains. */
	do {
		if (state == TASK_INTERRUPTIBLE)
			ret = wait_event_interruptible_timeout(sem->reader_drain,
				!atomic_long_read_acquire(&sem->readers), 1);
		else if (state == TASK_KILLABLE)
			ret = wait_event_killable_timeout(sem->reader_drain,
				!atomic_long_read_acquire(&sem->readers), 1);
		else
			ret = wait_event_timeout(sem->reader_drain,
				!atomic_long_read_acquire(&sem->readers), 1);
	} while (!ret);
	return ret < 0 ? -EINTR : 0;
}

int kd_down_read_trylock(struct kd_rwsem *sem)
{
	if (atomic_long_read(&sem->admission))
		return 0;
	/* Publish before checking the phase again. This full barrier and the
	 * writer's reservation RMW prohibit both missing each other's admission.
	 * A speculative count can overlap a writer, but cannot touch its payload. */
	atomic_long_inc_return(&sem->readers);
	if (!atomic_long_read_acquire(&sem->admission))
		return 1;
	kd_up_read(sem);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_trylock);

void kd_down_read(struct kd_rwsem *sem)
{
	might_sleep();
	kd_rwsem_wait(sem->phase_wait, kd_down_read_trylock(sem));
}
EXPORT_SYMBOL_GPL(kd_down_read);

int kd_down_read_interruptible(struct kd_rwsem *sem)
{
	might_sleep();
	return wait_event_interruptible(sem->phase_wait, kd_down_read_trylock(sem)) ? -EINTR : 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_interruptible);

int kd_down_read_killable(struct kd_rwsem *sem)
{
	might_sleep();
	return wait_event_killable(sem->phase_wait, kd_down_read_trylock(sem)) ? -EINTR : 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_killable);

static bool kd_rwsem_reserve_local(struct kd_rwsem *sem)
{
	if (atomic_long_read(&sem->admission))
		return false;
	return atomic_long_cmpxchg(&sem->admission, 0, KD_RWSEM_LOCAL_WRITER) == 0;
}

static void kd_rwsem_release_local(struct kd_rwsem *sem)
{
	/* Every ordinary writer retains this exclusive phase until after its
	 * physical unlock. No delegated producer can have passed reader drain. */
	BUG_ON(atomic_long_xchg(&sem->admission, 0) != KD_RWSEM_LOCAL_WRITER);
	kd_rwsem_wake_phase(sem);
}

void kd_down_write(struct kd_rwsem *sem)
{
	might_sleep();
	if (!kd_rwsem_poll(kd_rwsem_reserve_local(sem)))
		wait_event_exclusive_cmd(sem->phase_wait,
			kd_rwsem_reserve_local(sem), , );
	kd_mutex_local_lock(&sem->gate);
	kd_rwsem_drain_readers(sem, TASK_UNINTERRUPTIBLE);
}
EXPORT_SYMBOL_GPL(kd_down_write);

int kd_down_write_interruptible(struct kd_rwsem *sem)
{
	int ret;

	might_sleep();
	ret = wait_event_interruptible_exclusive(sem->phase_wait,
		kd_rwsem_reserve_local(sem));
	if (ret)
		return -EINTR;
	ret = kd_mutex_lock_interruptible(&sem->gate);
	if (!ret) {
		ret = kd_rwsem_drain_readers(sem, TASK_INTERRUPTIBLE);
		if (!ret)
			return 0;
		kd_mutex_local_unlock(&sem->gate);
	}
	/* Exclusive waits test the reservation before reporting a signal, so a
	 * selected writer cannot discard an open phase's wakeup on cancellation.
	 * They remove their waiter before rollback reopens admission. */
	kd_rwsem_release_local(sem);
	return -EINTR;
}
EXPORT_SYMBOL_GPL(kd_down_write_interruptible);

int kd_down_write_killable(struct kd_rwsem *sem)
{
	int ret;

	might_sleep();
	ret = wait_event_killable_exclusive(sem->phase_wait,
		kd_rwsem_reserve_local(sem));
	if (ret)
		return -EINTR;
	ret = kd_mutex_lock_killable(&sem->gate);
	if (!ret) {
		ret = kd_rwsem_drain_readers(sem, TASK_KILLABLE);
		if (!ret)
			return 0;
		kd_mutex_local_unlock(&sem->gate);
	}
	kd_rwsem_release_local(sem);
	return -EINTR;
}
EXPORT_SYMBOL_GPL(kd_down_write_killable);

int kd_down_write_trylock(struct kd_rwsem *sem)
{
	if (!kd_rwsem_reserve_local(sem))
		return 0;
	if (kd_mutex_trylock(&sem->gate)) {
		if (!atomic_long_read_acquire(&sem->readers))
			return 1;
		kd_mutex_local_unlock(&sem->gate);
	}
	kd_rwsem_release_local(sem);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_write_trylock);

void kd_up_write(struct kd_rwsem *sem)
{
	BUG_ON(atomic_long_read(&sem->admission) != KD_RWSEM_LOCAL_WRITER);
	kd_mutex_local_unlock(&sem->gate);
	kd_rwsem_release_local(sem);
}
EXPORT_SYMBOL_GPL(kd_up_write);

void kd_downgrade_write(struct kd_rwsem *sem)
{
	BUG_ON(atomic_long_read(&sem->admission) != KD_RWSEM_LOCAL_WRITER ||
	       !kd_origin_mutex_owned(&sem->gate, current));
	/* Only the exclusive ordinary phase can downgrade. Publish this reader
	 * before reopening admission: any later D reservation must drain it while
	 * schedulable, before entering the legacy queue and pinning its producer. */
	atomic_long_inc(&sem->readers);
	kd_mutex_local_unlock(&sem->gate);
	kd_rwsem_release_local(sem);
}
EXPORT_SYMBOL_GPL(kd_downgrade_write);

static bool kd_rwsem_reserve_delegate(struct kd_rwsem *sem)
{
	long phase = atomic_long_read(&sem->admission);

	while (phase >= 0 && phase < LONG_MAX) {
		/* Exact reservations also close reader/ordinary-writer admission.
		 * Use a full barrier before inspecting admitted readers. */
		if (atomic_long_try_cmpxchg(&sem->admission, &phase, phase + 1))
			return true;
	}
	return false;
}

void kd_rwsem_delegate_enter(struct kd_rwsem *sem)
{
	might_sleep();
	kd_rwsem_wait(sem->phase_wait, kd_rwsem_reserve_delegate(sem));
	/* No producer has published yet. A sleeping reader can resume even when
	 * it shares this CPU. Positive admission prevents new accepted readers or
	 * ordinary downgrades throughout every reservation in the cohort. */
	kd_rwsem_drain_readers(sem, TASK_UNINTERRUPTIBLE);
}
EXPORT_SYMBOL_GPL(kd_rwsem_delegate_enter);

void kd_rwsem_delegate_exit(struct kd_rwsem *sem)
{
	long remaining = atomic_long_dec_return(&sem->admission);

	BUG_ON(remaining < 0);
	if (!remaining)
		kd_rwsem_wake_phase(sem);
}
EXPORT_SYMBOL_GPL(kd_rwsem_delegate_exit);

bool kd_rwsem_is_idle(struct kd_rwsem *sem)
{
	return !atomic_long_read(&sem->admission) &&
		!atomic_long_read(&sem->readers) &&
		!waitqueue_active(&sem->phase_wait) &&
		!waitqueue_active(&sem->reader_drain) && kd_mutex_is_idle(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_rwsem_is_idle);
