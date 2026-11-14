// SPDX-License-Identifier: GPL-2.0-only
/* One admission word; the family guard is confined to registered slow waits. */
#include <linux/bug.h>
#include <linux/errno.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>

#include "rw_admission.h"
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
#include "rw_wait_diag.h"
#endif

struct kd_rw_read_wait {
	struct list_head link;
	bool charged;
	bool granted;
};

static unsigned long admission(struct kd_rw *lock)
{
	return (unsigned long)atomic_long_read(&lock->admission);
}

static void admission_add_checked(struct kd_rw *lock, unsigned long add,
		unsigned long mask)
{
	unsigned long old;

	for (;;) {
		old = admission(lock);
		BUG_ON((old & mask) == mask);
		if ((unsigned long)atomic_long_cmpxchg(&lock->admission, old, old + add) == old)
			return;
	}
}

bool kd_rw_admission_waking(struct kd_rw *lock)
{
	return lock->atomic_admission && (admission(lock) & KD_RW_ADMIT_WAKE);
}

unsigned long kd_rw_admission_readers(struct kd_rw *lock)
{
	return lock->atomic_admission ?
		(admission(lock) & KD_RW_ADMIT_READ_MASK) / KD_RW_ADMIT_READ : lock->readers;
}

bool kd_rw_admission_read_try(struct kd_rw *lock)
{
	unsigned long old = admission(lock);

	for (;;) {
		if (old & (KD_RW_ADMIT_WRITE | KD_RW_ADMIT_WAKE | KD_RW_ADMIT_QUEUE_MASK))
			return false;
		BUG_ON((old & KD_RW_ADMIT_READ_MASK) == KD_RW_ADMIT_READ_MASK);
		if ((unsigned long)atomic_long_cmpxchg_acquire(&lock->admission, old,
				old + KD_RW_ADMIT_READ) == old)
			return true;
		old = admission(lock);
	}
}

bool kd_rw_admission_write_try(struct kd_rw *lock, bool queued)
{
	unsigned long old = admission(lock);

	for (;;) {
		/* An ordinary writer cannot pass any registered waiter. The exact
		 * MCS head may claim after admitted readers and a wake actor drain.
		 */
		if (queued ? (old & (KD_RW_ADMIT_WRITE | KD_RW_ADMIT_WAKE | KD_RW_ADMIT_READ_MASK)) : old) {
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
			if (queued) {
				struct kd_rw_wait_diag_row *diag = kd_rw_wait_diag_current(lock);
				/* These masks describe this refused probe, not a later load. */
				kd_rw_wait_diag_add(diag, KD_RW_DIAG_WRITE_REFUSE_READ, !!(old & KD_RW_ADMIT_READ_MASK));
				kd_rw_wait_diag_add(diag, KD_RW_DIAG_WRITE_REFUSE_WRITE, !!(old & KD_RW_ADMIT_WRITE));
				kd_rw_wait_diag_add(diag, KD_RW_DIAG_WRITE_REFUSE_WAKE, !!(old & KD_RW_ADMIT_WAKE));
			}
#endif
			return false;
		}
		if ((unsigned long)atomic_long_cmpxchg_acquire(&lock->admission, old,
				old | KD_RW_ADMIT_WRITE) == old)
			return true;
		old = admission(lock);
	}
}

/* WAKE retains the final object access while waking waiters. New admissions
 * cannot complete until its release-clear. A woken waiter seeing WAKE retries
 * instead of sleeping again: the wake deliberately precedes the final clear.
 */
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
static void finish_wake(struct kd_rw *lock, bool reader_phase,
		struct kd_rw_wait_diag_row *diag, enum kd_rw_wait_diag_counter reason)
#else
static void finish_wake(struct kd_rw *lock, bool reader_phase)
#endif
{
	struct kd_rw_read_wait *waiter, *next;
	unsigned long readers = 0;

	raw_spin_lock(&lock->guard);
	if (reader_phase) {
		list_for_each_entry_safe(waiter, next, &lock->read_waiters, link) {
			list_del_init(&waiter->link);
			waiter->charged = false;
			waiter->granted = true;
			readers++;
		}
		/* Reserve this complete waiting reader phase before a queued writer
		 * can drain it. Later readers wait for a subsequent writer boundary.
		 */
		if (readers) {
			BUG_ON(readers > KD_RW_ADMIT_MAX_READERS - kd_rw_admission_readers(lock));
			atomic_long_add(readers * (KD_RW_ADMIT_READ - KD_RW_ADMIT_WAIT), &lock->admission);
		}
	}
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
	kd_rw_wait_diag_add(diag, KD_RW_DIAG_READ_RESERVED, readers);
	kd_rw_wait_diag_wake(diag, &lock->changed, reason);
#else
	wake_up_all(&lock->changed);
#endif
	raw_spin_unlock(&lock->guard);
	/* Final lock-object access, including the guard and wait queue. */
	atomic_long_fetch_andnot_release(KD_RW_ADMIT_WAKE, &lock->admission);
}

static void admission_put(struct kd_rw *lock, unsigned long remove,
		unsigned long add, bool end_writer)
{
	unsigned long old, next;
	bool wake, readers;
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
	struct kd_rw_wait_diag_row *diag = NULL;
	bool diag_checked = false;
#endif

	for (;;) {
		old = admission(lock);
		if (old & KD_RW_ADMIT_WAKE) {
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
			if (!diag_checked) {
				diag = kd_rw_wait_diag_current(lock);
				diag_checked = true;
			}
			kd_rw_wait_diag_add(diag, KD_RW_DIAG_RELEASE_WAKE_RETRY, 1);
#endif
			cond_resched();
			continue;
		}
		next = old - remove + add;
		readers = !(next & KD_RW_ADMIT_WRITE) &&
			(end_writer || !(next & KD_RW_ADMIT_QUEUE_MASK));
		wake = (readers && (next & KD_RW_ADMIT_WAIT_MASK)) ||
			(!(next & (KD_RW_ADMIT_WRITE | KD_RW_ADMIT_READ_MASK)) &&
			 (next & KD_RW_ADMIT_QUEUE_MASK));
		if (wake)
			next |= KD_RW_ADMIT_WAKE;
		if ((unsigned long)atomic_long_cmpxchg_release(&lock->admission, old, next) == old)
			break;
	}
	if (wake) {
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
		enum kd_rw_wait_diag_counter reason = remove == KD_RW_ADMIT_READ ? KD_RW_DIAG_WAKE_READ :
			remove == KD_RW_ADMIT_WRITE ? KD_RW_DIAG_WAKE_WRITE :
			remove == KD_RW_ADMIT_QUEUE ? KD_RW_DIAG_WAKE_QUEUE : KD_RW_DIAG_WAKE_WAIT;

		/* WAKE still retains the object. Non-waking releases need no lookup. */
		if (!diag_checked)
			diag = kd_rw_wait_diag_current(lock);
		finish_wake(lock, readers, diag, reason);
#else
		finish_wake(lock, readers);
#endif
	}
	/* A successful non-waking CAS is itself the final object access. */
}

void kd_rw_admission_read_put(struct kd_rw *lock)
{
	admission_put(lock, KD_RW_ADMIT_READ, 0, false);
}

void kd_rw_admission_write_put(struct kd_rw *lock, bool downgrade)
{
	admission_put(lock, KD_RW_ADMIT_WRITE, downgrade ? KD_RW_ADMIT_READ : 0, true);
}

void kd_rw_admission_queue_get(struct kd_rw *lock)
{
	if (lock && lock->atomic_admission)
		admission_add_checked(lock, KD_RW_ADMIT_QUEUE, KD_RW_ADMIT_QUEUE_MASK);
}

void kd_rw_admission_queue_put(struct kd_rw *lock)
{
	if (lock && lock->atomic_admission)
		admission_put(lock, KD_RW_ADMIT_QUEUE, 0, false);
}

int kd_rw_admission_read(struct kd_rw *lock, unsigned int wait_state,
		const struct kd_rw_wait_ops *ops, void *context)
{
	struct kd_rw_read_wait waiter;
	DEFINE_WAIT(wait);
	bool charged;
	int result = 0;
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
	struct kd_rw_wait_diag_row *diag = kd_rw_wait_diag_current(lock);
	bool diag_registered = false;

	kd_rw_wait_diag_add(diag, KD_RW_DIAG_READ_BEGIN, 1);
#endif

	INIT_LIST_HEAD(&waiter.link);
	waiter.charged = false;
	waiter.granted = false;
	for (;;) {
		bool blocked = false, waking;

		__set_current_state(TASK_RUNNING);
		if (ops && ops->progress)
			result = ops->progress(context, &blocked);
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
		kd_rw_wait_diag_prepare(diag, false, &diag_registered, &lock->changed, &wait, wait_state);
#else
		prepare_to_wait(&lock->changed, &wait, wait_state);
#endif
		raw_spin_lock(&lock->guard);
		waking = kd_rw_admission_waking(lock);
		if (!result && !blocked && !waking && !waiter.granted &&
		    list_empty(&waiter.link) && kd_rw_admission_read_try(lock)) {
			waiter.granted = true;
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
			kd_rw_wait_diag_add(diag, KD_RW_DIAG_READ_DIRECT, 1);
#endif
		}
		/* Readiness wins over a pending signal. A progress failure still
		 * rolls back a reserved phase grant before leaving this helper.
		 */
		if (result || (!waking && waiter.granted && !blocked)) {
			raw_spin_unlock(&lock->guard);
			break;
		}
		if (!waiter.granted && signal_pending_state(wait_state, current)) {
			result = -EINTR;
			raw_spin_unlock(&lock->guard);
			break;
		}
		if (!waking && !blocked && !waiter.granted && list_empty(&waiter.link)) {
			admission_add_checked(lock, KD_RW_ADMIT_WAIT, KD_RW_ADMIT_WAIT_MASK);
			waiter.charged = true;
			list_add_tail(&waiter.link, &lock->read_waiters);
			/* The previous failed probe did not serialize with a lock-free
			 * writer release. Publication must precede this second probe:
			 * either that release sees WAIT and wakes us, or this probe sees
			 * its completed release. A later writer cannot pass our charge.
			 */
			if (kd_rw_admission_read_try(lock)) {
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
				kd_rw_wait_diag_add(diag, KD_RW_DIAG_READ_DIRECT, 1);
#endif
				list_del_init(&waiter.link);
				waiter.granted = true;
				raw_spin_unlock(&lock->guard);
				break;
			}
		}
		raw_spin_unlock(&lock->guard);
		if (waking || (ops && ops->ready && ops->ready(context))) {
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
			kd_rw_wait_diag_add(diag, waking ? KD_RW_DIAG_READ_WAKE_RETRY : KD_RW_DIAG_READ_PROGRESS_RETRY, 1);
#endif
			__set_current_state(TASK_RUNNING);
			cond_resched();
		} else {
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
			kd_rw_wait_diag_add(diag, KD_RW_DIAG_READ_SCHEDULE, 1);
#endif
			schedule();
		}
	}
	raw_spin_lock(&lock->guard);
	list_del_init(&waiter.link);
	charged = waiter.charged;
	raw_spin_unlock(&lock->guard);
	finish_wait(&lock->changed, &wait);
	/* The waiter charge or admitted read survives finish_wait's last access. */
	if (charged)
		admission_put(lock, KD_RW_ADMIT_WAIT, 0, false);
	if (result && waiter.granted)
		kd_rw_admission_read_put(lock);
#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
	/* Only independent row/local scalars follow the final admission release. */
	kd_rw_wait_diag_add(diag, KD_RW_DIAG_READ_ROLLBACK, !!(result && waiter.granted));
	kd_rw_wait_diag_add(diag, !result ? KD_RW_DIAG_READ_RETURN :
		result == -EINTR ? KD_RW_DIAG_READ_CANCEL : KD_RW_DIAG_READ_ERROR, 1);
#endif
	return result;
}
