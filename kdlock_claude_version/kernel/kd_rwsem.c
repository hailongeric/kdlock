// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock rwsem.
 *
 * ->count holds the writer bit, a writer-waiting bit and the reader count,
 * as in the rwlock. ->m is a kdlock mutex used as the ordering queue for
 * everything that cannot take the fast path. Only the task holding ->m
 * ever waits on ->count, so ->m.owner names the single task a release may
 * have to wake (KD_RWSEM_NEEDWAKE).
 *
 * Writers are delegable. A writer that reaches the head of ->m takes the
 * writer bit and then, as combiner, keeps the bit and ->m while executing
 * the writers queued behind it. Readers queue on ->m without publishing a
 * continuation, so a session ends at the first queued reader.
 *
 * Releasing the write side clears the writer bit and wakes the holder of
 * ->m if it sleeps; it never touches ->m. That makes the release identical
 * for a fast-path writer, a combiner after its session and an origin that
 * got its section handed back.
 *
 * Readers always run on their own task.
 */
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/rcupdate.h>
#include <linux/preempt.h>
#include "kd_internal.h"

#define KD_RWSEM_SPIN	1024	/* iterations a queue head spins for count before sleeping */

static __always_inline bool kd_rwsem_readers(long c)
{
	return (c >> KD_RWSEM_RSHIFT) != 0;
}

/* Wake the holder of ->m if it sleeps on ->count. */
static void kd_rwsem_wake(struct kd_rwsem *sem)
{
	struct task_struct *t;

	rcu_read_lock();
	t = READ_ONCE(sem->m.owner);
	if (t)
		wake_up_process(t);
	rcu_read_unlock();
}

/* Writer holding ->m: take the writer bit if no reader and no writer is in. */
static __always_inline bool kd_rwsem_write_try(struct kd_rwsem *sem)
{
	long c = atomic_long_read(&sem->count);

	while (!(c & KD_RWSEM_WLOCKED) && !kd_rwsem_readers(c)) {
		if (atomic_long_try_cmpxchg_acquire(&sem->count, &c,
				(c & ~KD_RWSEM_WWAIT) | KD_RWSEM_WLOCKED))
			return true;
	}
	return false;
}

/*
 * Queue head (pinned, on the wait stack) obtains the writer bit. Returns
 * false when the current holders do not leave within the spin budget; the
 * caller then continues in kd_down_write_sleep() with ->m still held and
 * KD_RWSEM_WWAIT still set.
 */
static bool kd_rwsem_post(void *root)
{
	struct kd_rwsem *sem = root;
	int i;

	atomic_long_or(KD_RWSEM_WWAIT, &sem->count);
	for (i = 0; i < KD_RWSEM_SPIN; i++) {
		if (kd_rwsem_write_try(sem))
			return true;
		if (need_resched())
			break;
		cpu_relax();
	}
	return false;
}

static void kd_rwsem_release_queue(void *root)
{
	struct kd_rwsem *sem = root;

	kd_mutex_unlock(&sem->m);
}

static const struct kd_family kd_rwsem_family = {
	.post		= kd_rwsem_post,
	.release	= kd_rwsem_release_queue,
	.keeps_q	= true,
	.always_deleg	= true,
};

/* Called by the entry stub on the wait stack. */
int kd_down_write_wait(struct kd_rwsem *sem)
{
	int ret = kd_wait_sleepable(&sem->m, sem, &kd_rwsem_family, NULL, NULL, true);

	if (ret == KD_WAIT_RESUMED)
		kd_finish_resume(1);
	return ret;
}

/*
 * kd_down_write*() reached inside a section; see kd_mutex_nested(). If the
 * executor got the queue mutex but the count holders do not leave within
 * the spin budget, it gives the queue up again before handing back.
 */
int kd_down_write_nested(struct kd_rwsem *sem, struct kd_regs *r, void *entry)
{
	int ret;

	if (kd_down_write_trylock_raw(sem))
		return KD_WAIT_LOCAL;
	ret = kd_wait_sleepable(&sem->m, sem, &kd_rwsem_family, r, entry, true);
	if (ret == KD_WAIT_SLEEP_HELD) {
		atomic_long_andnot(KD_RWSEM_WWAIT, &sem->count);
		kd_mutex_unlock(&sem->m);
		ret = KD_WAIT_SLEEP;
	}
	return ret;
}

/*
 * Sleep on ->count as the holder of ->m until @cond holds. Returns
 * -EINTR if a signal permitted by @state arrives first.
 *
 * NEEDWAKE is set with a full-barrier atomic before the condition is
 * re-read, and releasers change ->count with an atomic before testing
 * NEEDWAKE, so one side always sees the other.
 */
#define kd_rwsem_sleep_on(sem, state, cond)				\
({									\
	int __ret = 0;							\
	atomic_long_or(KD_RWSEM_NEEDWAKE, &(sem)->count);		\
	for (;;) {							\
		set_current_state(state);				\
		if (cond)						\
			break;						\
		if (signal_pending_state(state, current)) {		\
			__ret = -EINTR;					\
			break;						\
		}							\
		schedule();						\
	}								\
	__set_current_state(TASK_RUNNING);				\
	atomic_long_andnot(KD_RWSEM_NEEDWAKE, &(sem)->count);		\
	__ret;								\
})

static int __kd_down_write_sleep(struct kd_rwsem *sem, int why, unsigned int state)
{
	int ret;

	might_sleep();
	if (why != KD_WAIT_SLEEP_HELD) {
		ret = kd_mutex_sleep(&sem->m, state, NULL);
		if (ret)
			return ret;
		atomic_long_or(KD_RWSEM_WWAIT, &sem->count);
	}
	ret = kd_rwsem_sleep_on(sem, state, kd_rwsem_write_try(sem));
	if (ret) {
		/* Give up: let queued readers use the fast path again. */
		atomic_long_andnot(KD_RWSEM_WWAIT, &sem->count);
	}
	kd_mutex_unlock(&sem->m);
	return ret;
}

/* Tail-called by the entry stubs on the task's own stack, unpinned. */
int kd_down_write_sleep(struct kd_rwsem *sem, int why)
{
	return __kd_down_write_sleep(sem, why, TASK_UNINTERRUPTIBLE);
}

int kd_down_write_sleep_killable(struct kd_rwsem *sem, int why)
{
	return __kd_down_write_sleep(sem, why, TASK_KILLABLE);
}

/*
 * Slow path of the delegable write entries, on the caller's own stack; see
 * __kd_mutex_lock_slow(). A contended writer publishes its continuation
 * whenever it can (kd_family.always_deleg).
 */
static __always_inline int __kd_down_write_slow(struct kd_rwsem *sem, unsigned long site,
						unsigned int state)
{
	int ret;

	might_sleep();
	preempt_disable();
	if (kd_can_offer(site))
		return KD_SLOW_OFFER;
	ret = kd_wait_sleepable(&sem->m, sem, &kd_rwsem_family, NULL, NULL, false);
	preempt_enable();
	if (ret == KD_WAIT_LOCAL)
		return 0;
	return __kd_down_write_sleep(sem, ret, state);
}

int kd_down_write_slow(struct kd_rwsem *sem, unsigned long site)
{
	return __kd_down_write_slow(sem, site, TASK_UNINTERRUPTIBLE);
}

int kd_down_write_slow_killable(struct kd_rwsem *sem, unsigned long site)
{
	return __kd_down_write_slow(sem, site, TASK_KILLABLE);
}

bool kd_down_write_trylock_raw(struct kd_rwsem *sem)
{
	long c = 0;

	return atomic_long_try_cmpxchg_acquire(&sem->count, &c, KD_RWSEM_WLOCKED);
}

int kd_down_write_trylock(struct kd_rwsem *sem)
{
	return kd_down_write_trylock_raw(sem);
}
EXPORT_SYMBOL(kd_down_write_trylock);

void kd_up_write(struct kd_rwsem *sem)
{
	/* The writer bit is set, so subtracting it clears it: one locked add. */
	long c = atomic_long_fetch_sub_release(KD_RWSEM_WLOCKED, &sem->count);

	if (unlikely(c & KD_RWSEM_NEEDWAKE))
		kd_rwsem_wake(sem);
}
EXPORT_SYMBOL(kd_up_write);

/*
 * Write to read without a window: one atomic adds the reader and removes
 * the writer bit. Inside a delegated section this call is always handed
 * back, because the read-side remainder belongs to the origin.
 */
void kd_downgrade_write(struct kd_rwsem *sem)
{
	long c = atomic_long_fetch_add(KD_RWSEM_RBIAS - KD_RWSEM_WLOCKED, &sem->count);

	if (unlikely(c & KD_RWSEM_NEEDWAKE))
		kd_rwsem_wake(sem);
}
EXPORT_SYMBOL(kd_downgrade_write);

/* ---- readers ---------------------------------------------------------------- */

static __always_inline void kd_rwsem_read_undo(struct kd_rwsem *sem)
{
	long c = atomic_long_sub_return(KD_RWSEM_RBIAS, &sem->count);

	if (unlikely((c & KD_RWSEM_NEEDWAKE) && !kd_rwsem_readers(c)))
		kd_rwsem_wake(sem);
}

bool kd_down_read_trylock_raw(struct kd_rwsem *sem)
{
	long c = atomic_long_read(&sem->count);

	while (!(c & KD_RWSEM_WMASK)) {
		if (atomic_long_try_cmpxchg_acquire(&sem->count, &c, c + KD_RWSEM_RBIAS))
			return true;
	}
	return false;
}

int kd_down_read_trylock(struct kd_rwsem *sem)
{
	return kd_down_read_trylock_raw(sem);
}
EXPORT_SYMBOL(kd_down_read_trylock);

/*
 * Before queueing on ->m, wait a bounded time for the writer side to clear.
 * Write sections are usually short, and the queue path costs at least one
 * sleep and wakeup per reader, in sequence: the holder of ->m sleeps on
 * ->count, and the next reader sleeps behind it. Readers waiting here do
 * not hold back writers: a queued writer's KD_RWSEM_WWAIT keeps them out
 * until it has had its turn.
 */
static bool kd_down_read_spin(struct kd_rwsem *sem)
{
	long c;
	int i;

	for (i = 0; i < KD_RWSEM_SPIN; i++) {
		c = atomic_long_read(&sem->count);
		if (!(c & KD_RWSEM_WMASK)) {
			if (atomic_long_try_cmpxchg_acquire(&sem->count, &c, c + KD_RWSEM_RBIAS))
				return true;
			continue;
		}
		if (need_resched())
			break;
		cpu_relax();
	}
	return false;
}

static noinline int kd_down_read_slow(struct kd_rwsem *sem, unsigned int state)
{
	int ret, i;

	kd_rwsem_read_undo(sem);
	if (kd_down_read_spin(sem))
		return 0;

	/* Queue behind earlier writers and readers. */
	ret = kd_mutex_sleep(&sem->m, state, NULL);
	if (ret)
		return ret;
	/*
	 * Holding ->m keeps queued writers out. Register as reader first so
	 * a fast-path or trylock writer cannot slip in, then wait for an
	 * active writer to leave.
	 */
	atomic_long_add(KD_RWSEM_RBIAS, &sem->count);
	/*
	 * The writer still inside is usually a combiner running its own
	 * section right after releasing ->m, which takes nanoseconds. Spin
	 * for it before sleeping: a holder of ->m that sleeps makes every
	 * queued writer see an off-CPU owner and park. Measured (A/B in one
	 * boot): w20 at 20 workers +16-33%, no change elsewhere; the larger
	 * high-worker-count rwsem loss has other causes (readers serialise
	 * through ->m), see docs/DIFFERENCES.md D11.
	 */
	for (i = 0; i < KD_RWSEM_SPIN &&
		    (atomic_long_read(&sem->count) & KD_RWSEM_WLOCKED); i++) {
		if (need_resched())
			break;
		cpu_relax();
	}
	ret = kd_rwsem_sleep_on(sem, state,
				!(atomic_long_read(&sem->count) & KD_RWSEM_WLOCKED));
	if (ret)
		atomic_long_sub(KD_RWSEM_RBIAS, &sem->count);
	kd_mutex_unlock(&sem->m);
	return ret;
}

static __always_inline int __kd_down_read(struct kd_rwsem *sem, unsigned int state)
{
	long c;

	might_sleep();
	c = atomic_long_add_return_acquire(KD_RWSEM_RBIAS, &sem->count);
	if (likely(!(c & KD_RWSEM_WMASK)))
		return 0;
	return kd_down_read_slow(sem, state);
}

void kd_down_read(struct kd_rwsem *sem)
{
	__kd_down_read(sem, TASK_UNINTERRUPTIBLE);
}
EXPORT_SYMBOL(kd_down_read);

int kd_down_read_interruptible(struct kd_rwsem *sem)
{
	return __kd_down_read(sem, TASK_INTERRUPTIBLE);
}
EXPORT_SYMBOL(kd_down_read_interruptible);

int kd_down_read_killable(struct kd_rwsem *sem)
{
	return __kd_down_read(sem, TASK_KILLABLE);
}
EXPORT_SYMBOL(kd_down_read_killable);

void kd_up_read(struct kd_rwsem *sem)
{
	long c = atomic_long_sub_return_release(KD_RWSEM_RBIAS, &sem->count);

	if (unlikely((c & KD_RWSEM_NEEDWAKE) && !kd_rwsem_readers(c)))
		kd_rwsem_wake(sem);
}
EXPORT_SYMBOL(kd_up_read);
