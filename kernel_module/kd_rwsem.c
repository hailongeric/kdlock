// SPDX-License-Identifier: GPL-2.0
/* Reader/ordinary-writer/delegated-writer phases around an unchanged KD mutex. */
#include <linux/module.h>
#include <linux/limits.h>
#include "kd_rwsem.h"
#include "kd_lock.h"

#define KD_RWSEM_LOCAL_WRITER (-1L)
#define KD_RWSEM_POLL_PROBES 1024

/* Short holders often finish before a task can enqueue and be woken. Poll only
 * before publication, with preemption enabled and at most 1024 condition probes;
 * an individual predicate retains its existing atomic retry loop. Sleeping or
 * colocated holders still get the ordinary wait_event scheduling fallback.
 * A successful condition may acquire a reservation, so never evaluate it again
 * after success. The wait macro retains its enqueue/recheck ordering. */
#define kd_rwsem_wait(queue, condition) do { \
	unsigned int kd_rwsem_budget = KD_RWSEM_POLL_PROBES; \
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
	if (!kd_rwsem_ready) \
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

static void kd_rwsem_wake(wait_queue_head_t *queue)
{
	/* Call only after a fully ordered count/phase RMW. Each predicate keeps
	 * its own queue: reader drainage cannot enable a closed admission phase.
	 * The RMW pairs with enqueue/recheck, including this lockless test. */
	if (waitqueue_active(queue))
		wake_up_all(queue);
}

void kd_up_read(struct kd_rwsem *sem)
{
	if (atomic_long_dec_and_test(&sem->readers))
		kd_rwsem_wake(&sem->reader_drain);
}
EXPORT_SYMBOL_GPL(kd_up_read);

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

/* One stack waiter carries one exact read reservation into down_read return;
 * its caller then retains that reservation until up_read. Both the waker and
 * caller grant under phase_wait.lock, with no second increment after a grant.
 */
struct kd_rwsem_reader_wait {
	wait_queue_entry_t wait;
	struct kd_rwsem *sem;
	bool granted;
};

static bool kd_rwsem_grant_reader_locked(struct kd_rwsem_reader_wait *reader)
{
	if (smp_load_acquire(&reader->granted))
		return true;
	if (!kd_down_read_trylock(reader->sem))
		return false;
	/* Publish the acquired reader count and its memory ordering before wakeup.
	 * A later writer must drain this count even before the reader runs again.
	 */
	smp_store_release(&reader->granted, true);
	return true;
}

static int kd_rwsem_reader_wake(wait_queue_entry_t *wait, unsigned int mode,
			       int wake_flags, void *key)
{
	struct kd_rwsem_reader_wait *reader =
		container_of(wait, struct kd_rwsem_reader_wait, wait);

	/* wake_up_all holds phase_wait.lock. A failed speculative read may wake
	 * reader_drain, but no reader_drain callback acquires phase_wait.lock.
	 */
	if (!(mode & TASK_UNINTERRUPTIBLE) ||
	    !kd_rwsem_grant_reader_locked(reader))
		return 0;
	/* A zero wake result does not undo the grant: an already-running caller
	 * observes it and removes its entry through finish_wait. Do not touch the
	 * stack waiter after autoremove, which can let that caller return at once.
	 */
	return autoremove_wake_function(wait, mode, wake_flags, key);
}

static noinline void kd_rwsem_down_read_slow(struct kd_rwsem *sem)
{
	struct kd_rwsem_reader_wait reader;
	unsigned long flags;
	bool granted;

	init_wait_entry(&reader.wait, 0);
	reader.wait.func = kd_rwsem_reader_wake;
	reader.sem = sem;
	WRITE_ONCE(reader.granted, false);
	for (;;) {
		(void)prepare_to_wait_event(&sem->phase_wait, &reader.wait,
					    TASK_UNINTERRUPTIBLE);
		/* Native queue locking avoids the captured public spin-clobber
		 * wrappers. Serialize every post-enqueue grant with the callback.
		 */
		flags = _raw_spin_lock_irqsave(spinlock_check(&sem->phase_wait.lock));
		granted = kd_rwsem_grant_reader_locked(&reader);
		_raw_spin_unlock_irqrestore(spinlock_check(&sem->phase_wait.lock), flags);
		if (granted)
			break;
		schedule();
	}
	/* The stack entry and its grant stay live through removal; this is the
	 * only exit and it transfers the exact read count to the ordinary caller.
	 */
	finish_wait(&sem->phase_wait, &reader.wait);
}

void kd_down_read(struct kd_rwsem *sem)
{
	unsigned int budget = KD_RWSEM_POLL_PROBES;

	might_sleep();
	do {
		if (kd_down_read_trylock(sem))
			return;
		if (need_resched())
			break;
		cpu_relax();
	} while (--budget);
	kd_rwsem_down_read_slow(sem);
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
	kd_rwsem_wake(&sem->phase_wait);
}

void kd_down_write(struct kd_rwsem *sem)
{
	might_sleep();
	kd_rwsem_wait(sem->phase_wait, kd_rwsem_reserve_local(sem));
	kd_mutex_local_lock(&sem->gate);
	kd_rwsem_wait(sem->reader_drain, !atomic_long_read_acquire(&sem->readers));
}
EXPORT_SYMBOL_GPL(kd_down_write);

int kd_down_write_interruptible(struct kd_rwsem *sem)
{
	int ret;

	might_sleep();
	ret = wait_event_interruptible(sem->phase_wait, kd_rwsem_reserve_local(sem));
	if (ret)
		return -EINTR;
	ret = kd_mutex_lock_interruptible(&sem->gate);
	if (!ret) {
		ret = wait_event_interruptible(sem->reader_drain,
					       !atomic_long_read_acquire(&sem->readers));
		if (!ret)
			return 0;
		kd_mutex_local_unlock(&sem->gate);
	}
	/* Wait macros remove their waiter before rollback reopens admission. */
	kd_rwsem_release_local(sem);
	return -EINTR;
}
EXPORT_SYMBOL_GPL(kd_down_write_interruptible);

int kd_down_write_killable(struct kd_rwsem *sem)
{
	int ret;

	might_sleep();
	ret = wait_event_killable(sem->phase_wait, kd_rwsem_reserve_local(sem));
	if (ret)
		return -EINTR;
	ret = kd_mutex_lock_killable(&sem->gate);
	if (!ret) {
		ret = wait_event_killable(sem->reader_drain,
					 !atomic_long_read_acquire(&sem->readers));
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
	kd_rwsem_wait(sem->reader_drain, !atomic_long_read_acquire(&sem->readers));
}
EXPORT_SYMBOL_GPL(kd_rwsem_delegate_enter);

void kd_rwsem_delegate_exit(struct kd_rwsem *sem)
{
	long remaining = atomic_long_dec_return(&sem->admission);

	BUG_ON(remaining < 0);
	if (!remaining)
		kd_rwsem_wake(&sem->phase_wait);
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
