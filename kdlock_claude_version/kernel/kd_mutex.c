// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock mutex.
 *
 * ->q.locked is the lock. There are two kinds of waiter:
 *
 *  - Spinning waiters stay pinned in the MCS queue behind ->q while the
 *    holder is running (the role the optimistic-spin queue has in the
 *    native mutex). In plain mode they wait on their own stack and each
 *    takes the lock itself when it reaches the queue head. In delegation
 *    mode (kd_core.c, "adaptive delegation") they publish their
 *    continuation, and the queue head, once it owns the mutex, executes
 *    their critical sections before its own (kd_wait_sleepable /
 *    kd_session in kd_core.c).
 *
 *  - Parked waiters sleep on ->waiters. A spinning waiter becomes a parked
 *    one by withdrawing from the queue first, so a task is never executed
 *    by a combiner and by itself.
 *
 * Acquisition is by cmpxchg on the lock byte for everyone, so parked
 * waiters, the queue head and new callers may compete, as with the native
 * mutex. A parked waiter that keeps losing sets KD_QF_HANDOFF; the next
 * release then passes ownership to the first parked waiter directly and a
 * running session stops early.
 *
 * A delegated section must not sleep on the combiner. The translator turns
 * every call that can sleep into an exit, so a mutex section that blocks is
 * handed back to its origin at that call and the origin continues as the
 * ordinary owner.
 */
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/sched/wake_q.h>
#include <linux/ww_mutex.h>
#include <linux/preempt.h>
#include <linux/irqflags.h>
#include "kd_internal.h"

struct kd_mutex_waiter {
	struct list_head	list;
	struct task_struct	*task;
	struct ww_acquire_ctx	*ww_ctx;	/* acquire context of a ww waiter, else NULL */
	bool			granted;	/* ownership was handed to this waiter */
};

/* ---- internal wait lock ----------------------------------------------------- */

static __always_inline unsigned long kd_wait_lock(struct kd_mutex *m)
{
	unsigned long flags;

	local_irq_save(flags);
	preempt_disable();
	if (unlikely(!kd_q_trylock_fifo(&m->wait_lock)))
		kd_q_lock_plain(&m->wait_lock);
	return flags;
}

static __always_inline void kd_wait_unlock(struct kd_mutex *m, unsigned long flags)
{
	kd_q_unlock(&m->wait_lock);
	local_irq_restore(flags);
	preempt_enable();
}

/* ---- spinning policy -------------------------------------------------------- */

/*
 * Keep spinning only while it can pay off: nobody else wants this CPU and
 * the logical owner is on a CPU. The owner pointer may be stale; the task
 * structure is RCU-freed and the caller has preemption disabled.
 */
bool kd_mutex_can_spin(struct kd_mutex *m)
{
	struct task_struct *owner;

	if (need_resched())
		return false;
	owner = READ_ONCE(m->owner);
	return !owner || owner_on_cpu(owner);
}

/* ---- acquisition ------------------------------------------------------------ */

bool kd_mutex_trylock_as(struct kd_mutex *m, struct task_struct *t)
{
	if (!kd_q_trylock(&m->q))
		return false;
	WRITE_ONCE(m->owner, t);
	return true;
}

int kd_mutex_trylock(struct kd_mutex *m)
{
	return kd_mutex_trylock_as(m, kd_logical_current());
}
EXPORT_SYMBOL(kd_mutex_trylock);

/*
 * First parked waiter: spin while the owner runs, as the native mutex does
 * for its first waiter. Returns when the lock looks free or was handed to
 * @w, or when spinning stops paying off; the caller rechecks under the wait
 * lock. The handoff request is honoured while this task still runs, so the
 * new owner is on a CPU and the queued spinners keep spinning. Granting to
 * a sleeping task instead makes every spinner see an off-CPU owner, leave
 * the queue and park (a convoy).
 */
static void kd_mutex_spin_first(struct kd_mutex *m, struct kd_mutex_waiter *w)
{
	preempt_disable();
	while (!READ_ONCE(w->granted) && READ_ONCE(m->q.locked) &&
	       kd_mutex_can_spin(m))
		cpu_relax();
	preempt_enable();
}

/*
 * Sleeping acquisition. Also the complete lock path for callers that never
 * spin (rwsem readers queueing behind writers, ww mutexes).
 *
 * @ww: the caller acquires for a ww acquire context; it returns -EDEADLK
 * instead of waiting on when kd_ww_must_back_off() says so.
 */
int kd_mutex_sleep(struct kd_mutex *m, unsigned int state, struct kd_ww_wait *ww)
{
	struct kd_mutex_waiter w = { .task = current, .ww_ctx = ww ? ww->ctx : NULL };
	unsigned long flags;
	bool asked_handoff = false;
	int tries = 0, ret = 0;

	if (kd_mutex_trylock_as(m, current))
		return 0;

	flags = kd_wait_lock(m);
	list_add_tail(&w.list, &m->waiters);
	/* Full barrier: pairs with the release in kd_mutex_unlock(). */
	atomic_or(KD_QF_SLEEPERS << KD_QF_SHIFT, &m->q.val);

	for (;;) {
		bool first;

		if (w.granted)
			break;
		if (kd_mutex_trylock_as(m, current))
			break;
		if (signal_pending_state(state, current)) {
			ret = -EINTR;
			break;
		}
		if (ww && kd_ww_must_back_off(ww)) {
			ret = -EDEADLK;
			break;
		}
		first = list_first_entry(&m->waiters, struct kd_mutex_waiter, list) == &w;
		if (++tries > 2 && !asked_handoff && first) {
			atomic_or(KD_QF_HANDOFF << KD_QF_SHIFT, &m->q.val);
			asked_handoff = true;
			/* The holder may have released just before the flag. */
			if (kd_mutex_trylock_as(m, current))
				break;
		}
		if (first && tries > 1 && kd_mutex_can_spin(m)) {
			/*
			 * Woken at least once: spin instead of sleeping again.
			 * Always recheck from the top afterwards: the grant may
			 * have been made, and its wakeup spent, while this task
			 * was running, so sleeping now would never end. When
			 * spinning stopped for need_resched(), the next pass does
			 * not spin (kd_mutex_can_spin() is false) and sleeps.
			 */
			kd_wait_unlock(m, flags);
			kd_mutex_spin_first(m, &w);
			flags = kd_wait_lock(m);
			continue;
		}
		set_current_state(state);
		kd_wait_unlock(m, flags);
		raw_cpu_inc(kd_cpu.stat[KD_STAT_PARKED]);	/* approximate */
		schedule();
		flags = kd_wait_lock(m);
	}
	__set_current_state(TASK_RUNNING);

	list_del(&w.list);
	/*
	 * A handoff request that was not consumed by a release must not
	 * outlive its requester, or the lock byte would never be cleared for
	 * an empty list.
	 */
	if (asked_handoff && !w.granted)
		atomic_andnot(KD_QF_HANDOFF << KD_QF_SHIFT, &m->q.val);
	if (list_empty(&m->waiters))
		atomic_andnot(KD_QF_SLEEPERS << KD_QF_SHIFT, &m->q.val);
	kd_wait_unlock(m, flags);
	return ret;
}

static void kd_mutex_set_owner(void *root, struct task_struct *t)
{
	struct kd_mutex *m = root;

	WRITE_ONCE(m->owner, t);
}

static const struct kd_family kd_mutex_family = {
	.set_owner	= kd_mutex_set_owner,
};

/*
 * Slow path of the delegable entries, called by the entry stub on the
 * caller's own stack; @site is the caller's return address.
 *
 * Plain mode: spin in the queue while the holder runs, then park; nothing
 * is published and the caller's stack is never left. Returns 0 or -EINTR.
 *
 * Delegation mode, and this caller can publish: returns KD_SLOW_OFFER with
 * preemption still disabled; the stub then stores the continuation and
 * calls kd_mutex_wait() on the wait stack.
 */
static __always_inline int __kd_mutex_lock_slow(struct kd_mutex *m, unsigned long site,
						unsigned int state)
{
	int ret;

	might_sleep();
	preempt_disable();
	if (kd_qs_deleg_mode(&m->q) && kd_can_offer(site))
		return KD_SLOW_OFFER;
	ret = kd_wait_sleepable(m, m, &kd_mutex_family, NULL, NULL, false);
	preempt_enable();
	if (ret == KD_WAIT_LOCAL)
		return 0;
	return kd_mutex_sleep(m, state, NULL);
}

int kd_mutex_lock_slow(struct kd_mutex *m, unsigned long site)
{
	return __kd_mutex_lock_slow(m, site, TASK_UNINTERRUPTIBLE);
}

int kd_mutex_lock_slow_interruptible(struct kd_mutex *m, unsigned long site)
{
	return __kd_mutex_lock_slow(m, site, TASK_INTERRUPTIBLE);
}

int kd_mutex_lock_slow_killable(struct kd_mutex *m, unsigned long site)
{
	return __kd_mutex_lock_slow(m, site, TASK_KILLABLE);
}

/*
 * mutex_lock_io(): the caller counts as waiting for I/O while it sleeps
 * for the mutex. Spinning and a delegated section involve no sleep, so
 * only the parked wait is bracketed.
 */
int kd_mutex_lock_slow_io(struct kd_mutex *m, unsigned long site)
{
	int ret, token;

	might_sleep();
	preempt_disable();
	if (kd_qs_deleg_mode(&m->q) && kd_can_offer(site))
		return KD_SLOW_OFFER;
	ret = kd_wait_sleepable(m, m, &kd_mutex_family, NULL, NULL, false);
	preempt_enable();
	if (ret == KD_WAIT_LOCAL)
		return 0;
	token = io_schedule_prepare();
	ret = kd_mutex_sleep(m, TASK_UNINTERRUPTIBLE, NULL);
	io_schedule_finish(token);
	return ret;
}

/* Called by the entry stub on the wait stack. */
int kd_mutex_wait(struct kd_mutex *m)
{
	int ret = kd_wait_sleepable(m, m, &kd_mutex_family, NULL, NULL, true);

	if (ret == KD_WAIT_RESUMED)
		kd_finish_resume(1);
	return ret;
}

/*
 * kd_mutex_lock*() reached inside a section. The executor spins in the
 * queue, with the continuation published while the mutex is in delegation
 * mode, exactly as a top-level waiter would. It cannot go on to sleep: if
 * spinning stops paying off the origin gets the continuation back with the
 * call still pending.
 */
int kd_mutex_nested(struct kd_mutex *m, struct kd_regs *r, void *entry)
{
	int ret;

	if (kd_mutex_trylock_as(m, r->task))
		return KD_WAIT_LOCAL;
	if (!kd_qs_deleg_mode(&m->q))
		entry = NULL;
	ret = kd_wait_sleepable(m, m, &kd_mutex_family, r, entry, true);
	if (ret == KD_WAIT_LOCAL)
		WRITE_ONCE(m->owner, r->task);
	return ret;
}

/* Tail-called by the entry stubs on the task's own stack, unpinned. */
int kd_mutex_lock_sleep(struct kd_mutex *m, int why)
{
	might_sleep();
	return kd_mutex_sleep(m, TASK_UNINTERRUPTIBLE, NULL);
}

int kd_mutex_lock_sleep_interruptible(struct kd_mutex *m, int why)
{
	might_sleep();
	return kd_mutex_sleep(m, TASK_INTERRUPTIBLE, NULL);
}

int kd_mutex_lock_sleep_killable(struct kd_mutex *m, int why)
{
	might_sleep();
	return kd_mutex_sleep(m, TASK_KILLABLE, NULL);
}

int kd_mutex_lock_sleep_io(struct kd_mutex *m, int why)
{
	int ret, token;

	might_sleep();
	token = io_schedule_prepare();
	ret = kd_mutex_sleep(m, TASK_UNINTERRUPTIBLE, NULL);
	io_schedule_finish(token);
	return ret;
}

/*
 * The task recorded as running with the mutex, or 0. During a combining
 * session that is the combiner (see kd_exec_one()). For diagnostics only.
 */
unsigned long kd_mutex_get_owner(struct kd_mutex *m)
{
	return (unsigned long)READ_ONCE(m->owner);
}
EXPORT_SYMBOL(kd_mutex_get_owner);

/* ---- release ---------------------------------------------------------------- */

/*
 * A parked waiter asked for the lock (KD_QF_HANDOFF): ownership goes to
 * the first parked waiter directly, the lock byte stays set. Returns false
 * if nobody is parked any more; the caller then releases normally.
 */
static noinline bool kd_mutex_handoff(struct kd_mutex *m)
{
	struct kd_mutex_waiter *w;
	DEFINE_WAKE_Q(wake_q);
	unsigned long flags;

	flags = kd_wait_lock(m);
	atomic_andnot(KD_QF_HANDOFF << KD_QF_SHIFT, &m->q.val);
	w = list_first_entry_or_null(&m->waiters, struct kd_mutex_waiter, list);
	if (w) {
		raw_cpu_inc(kd_cpu.stat[KD_STAT_HANDOFF]);
		w->granted = true;
		WRITE_ONCE(m->owner, w->task);
		wake_q_add(&wake_q, w->task);
	}
	kd_wait_unlock(m, flags);
	wake_up_q(&wake_q);
	return w != NULL;
}

static noinline void kd_mutex_wake_first(struct kd_mutex *m)
{
	struct kd_mutex_waiter *w;
	DEFINE_WAKE_Q(wake_q);
	unsigned long flags;

	flags = kd_wait_lock(m);
	w = list_first_entry_or_null(&m->waiters, struct kd_mutex_waiter, list);
	if (w)
		wake_q_add(&wake_q, w->task);
	kd_wait_unlock(m, flags);
	wake_up_q(&wake_q);
}

/* Wake every parked waiter for which @fn holds; see kd_ww_mutex.c. */
void kd_mutex_wake_matching(struct kd_mutex *m,
			    bool (*fn)(struct ww_acquire_ctx *waiter, void *arg),
			    void *arg)
{
	struct kd_mutex_waiter *w;
	DEFINE_WAKE_Q(wake_q);
	unsigned long flags;

	flags = kd_wait_lock(m);
	list_for_each_entry(w, &m->waiters, list) {
		if (w->ww_ctx && fn(w->ww_ctx, arg))
			wake_q_add(&wake_q, w->task);
	}
	kd_wait_unlock(m, flags);
	wake_up_q(&wake_q);
}

/*
 * One atomic operation, as for the native mutex, whether or not spinners
 * are queued: the lock byte is cleared by a locked subtraction that also
 * returns the flags as they were. A waiter that parks sets KD_QF_SLEEPERS
 * with a full barrier and then tries the lock, so either this release
 * sees the flag or that waiter sees the lock free. Nothing is read after
 * the release: by then the next holder owns the line, and a read would
 * take it away again.
 */
void kd_mutex_unlock(struct kd_mutex *m)
{
	u8 flags = READ_ONCE(m->q.flags);
	int old;

	WRITE_ONCE(m->owner, NULL);
	if (unlikely(flags & KD_QF_HANDOFF) && kd_mutex_handoff(m))
		return;
	old = atomic_fetch_sub_release(KD_Q_LOCKED, &m->q.val);
	if (unlikely(old & (KD_QF_SLEEPERS << KD_QF_SHIFT)))
		kd_mutex_wake_first(m);
}
EXPORT_SYMBOL(kd_mutex_unlock);
