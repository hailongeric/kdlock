// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock mutex.
 *
 * ->q.locked is the lock. There are two kinds of waiter:
 *
 *  - Spinning waiters stay pinned in the MCS queue behind ->q while the
 *    holder is running. They publish their continuation, and the queue
 *    head, once it owns the mutex, executes their critical sections before
 *    its own (kd_wait_sleepable / kd_session in kd_core.c).
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
#include <linux/preempt.h>
#include <linux/irqflags.h>
#include "kd_internal.h"

struct kd_mutex_waiter {
	struct list_head	list;
	struct task_struct	*task;
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
 * spin (rwsem readers queueing behind writers).
 */
int kd_mutex_sleep(struct kd_mutex *m, unsigned int state)
{
	struct kd_mutex_waiter w = { .task = current };
	unsigned long flags;
	bool asked_handoff = false;
	int tries = 0, ret = 0;

	if (kd_mutex_trylock_as(m, current))
		return 0;

	flags = kd_wait_lock(m);
	list_add_tail(&w.list, &m->waiters);
	/* Full barrier: pairs with the atomic release in kd_mutex_unlock_slow(). */
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

/* Called by the entry stub on the wait stack. */
static void kd_mutex_set_owner(void *root, struct task_struct *t)
{
	struct kd_mutex *m = root;

	WRITE_ONCE(m->owner, t);
}

static const struct kd_family kd_mutex_family = {
	.set_owner	= kd_mutex_set_owner,
};

int kd_mutex_wait(struct kd_mutex *m)
{
	int ret = kd_wait_sleepable(m, m, &kd_mutex_family, NULL, NULL);

	if (ret == KD_WAIT_RESUMED)
		kd_finish_resume(1);
	return ret;
}

/*
 * kd_mutex_lock*() reached inside a section. The executor spins in the
 * queue with the continuation published, exactly as a top-level waiter
 * would, but it cannot go on to sleep: if spinning stops paying off the
 * origin gets the continuation back with the call still pending.
 */
int kd_mutex_nested(struct kd_mutex *m, struct kd_regs *r, void *entry)
{
	int ret;

	if (kd_mutex_trylock_as(m, r->task))
		return KD_WAIT_LOCAL;
	ret = kd_wait_sleepable(m, m, &kd_mutex_family, r, entry);
	if (ret == KD_WAIT_LOCAL)
		WRITE_ONCE(m->owner, r->task);
	return ret;
}

/* Tail-called by the entry stubs on the task's own stack, unpinned. */
int kd_mutex_lock_sleep(struct kd_mutex *m, int why)
{
	might_sleep();
	return kd_mutex_sleep(m, TASK_UNINTERRUPTIBLE);
}

int kd_mutex_lock_sleep_interruptible(struct kd_mutex *m, int why)
{
	might_sleep();
	return kd_mutex_sleep(m, TASK_INTERRUPTIBLE);
}

int kd_mutex_lock_sleep_killable(struct kd_mutex *m, int why)
{
	might_sleep();
	return kd_mutex_sleep(m, TASK_KILLABLE);
}

/* ---- release ---------------------------------------------------------------- */

static noinline void kd_mutex_unlock_slow(struct kd_mutex *m)
{
	struct kd_mutex_waiter *w;
	DEFINE_WAKE_Q(wake_q);
	unsigned long flags;
	bool released = false;
	int old;

	if (!(READ_ONCE(m->q.flags) & KD_QF_HANDOFF)) {
		/*
		 * Atomic clear, not a byte store: the returned word tells
		 * whether a parked waiter registered before the release. One
		 * that registers after it sees the lock free and takes it.
		 */
		old = atomic_fetch_andnot_release(KD_Q_LOCKED, &m->q.val);
		if (!(old & (KD_QF_SLEEPERS << KD_QF_SHIFT)))
			return;
		released = true;
	}

	flags = kd_wait_lock(m);
	w = list_first_entry_or_null(&m->waiters, struct kd_mutex_waiter, list);
	if (!released) {
		/* Handoff: the lock byte stays set and changes owner. */
		atomic_andnot(KD_QF_HANDOFF << KD_QF_SHIFT, &m->q.val);
		if (w) {
			raw_cpu_inc(kd_cpu.stat[KD_STAT_HANDOFF]);
			w->granted = true;
			WRITE_ONCE(m->owner, w->task);
		} else {
			kd_q_unlock(&m->q);
		}
	}
	if (w)
		wake_q_add(&wake_q, w->task);
	kd_wait_unlock(m, flags);
	wake_up_q(&wake_q);
}

void kd_mutex_unlock(struct kd_mutex *m)
{
	int old = KD_Q_LOCKED;

	WRITE_ONCE(m->owner, NULL);
	if (likely(atomic_try_cmpxchg_release(&m->q.val, &old, 0)))
		return;
	kd_mutex_unlock_slow(m);
}
EXPORT_SYMBOL(kd_mutex_unlock);
