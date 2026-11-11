// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock spinlock.
 *
 * The lock is the queue word itself: FIFO MCS queue plus, while no queue
 * exists, one pending waiter (kd_spin_pending()). The delegable acquire
 * entries live in kd_entry.S; this file has their slow paths, the raw
 * (never delegated) acquires, trylock and release.
 *
 * Release is a plain byte store for every owner. A waiter whose section
 * was handed back simply owns the lock and releases it like anyone else;
 * the combiner that handed it back waits as queue head in the meantime.
 */
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/preempt.h>
#include <linux/bottom_half.h>
#include <linux/irqflags.h>
#include "kd_internal.h"

#define KD_PENDING_SPIN		4096	/* bound on the pending waiter's spin */
#define KD_PENDING_HANDOVER	64	/* bound on waiting for pending -> locked */
#define KD_Q_LOCKED_MASK	0xff	/* the lock byte of the queue word */

/*
 * Pending waiter, as in qspinlock: with no queue, one contender waits on
 * the lock byte itself instead of saving its continuation, queueing and
 * passing the queue on. That is cheaper when only two CPUs contend, where
 * there is nobody to combine for anyway. The pending bit keeps the fast
 * path closed (it needs the whole word zero) so the pending waiter is not
 * overtaken by new arrivals; they queue instead. Once anyone queues, the
 * pending waiter queues too, so under real contention every waiter is in
 * the queue and can be delegated. It takes the lock with the same cmpxchg
 * on the lock byte as the queue head (kd_q_head_lock()), so exactly one of
 * them wins.
 */
static bool kd_spin_pending(struct kd_qlock *q)
{
	const int pend = KD_QF_PENDING << KD_QF_SHIFT;
	int i, v = atomic_read(&q->val);

	/*
	 * A pending waiter is about to take the free lock: let it finish
	 * instead of queueing behind it (bounded, as in qspinlock).
	 */
	for (i = 0; v == pend && i < KD_PENDING_HANDOVER; i++) {
		cpu_relax();
		v = atomic_read(&q->val);
	}
	if (v & ~KD_Q_LOCKED_MASK)
		return false;		/* a pending waiter or a queue exists */
	if (!atomic_try_cmpxchg_acquire(&q->val, &v, v ? v | pend : KD_Q_LOCKED))
		return false;
	if (!v)
		return true;		/* it was free: taken */
	for (i = 0; i < KD_PENDING_SPIN; i++) {
		v = atomic_read(&q->val);
		/*
		 * Pending to locked in one step, as in qspinlock: a CPU
		 * arriving in between must see either the pending bit or the
		 * lock held, never a free word. A free lock is taken even when
		 * a queue formed meanwhile; its head competes with the same
		 * cmpxchg on the lock byte.
		 */
		if (!(v & KD_Q_LOCKED)) {
			if (atomic_try_cmpxchg_acquire(&q->val, &v, (v & ~pend) | KD_Q_LOCKED))
				return true;
			continue;
		}
		if (v >> 16)
			break;		/* held, and somebody queued: join them */
		cpu_relax();
	}
	/* Only the pending waiter writes ->flags of a spinlock. */
	atomic_andnot(pend, &q->val);
	return false;
}

/* Called by the entry stub on the wait stack; see kd_entry.S. */
int kd_spin_wait(struct kd_spinlock *l)
{
	int ret;

	if (kd_spin_pending(&l->q))
		return KD_WAIT_LOCAL;
	ret = kd_wait_spin(&l->q, l, NULL, NULL, NULL);

	if (ret == KD_WAIT_RESUMED)
		kd_finish_resume(0);
	return ret;
}

/* Contended kd_spin_lock*() inside a section; see kd_nested_acquire(). */
int kd_spin_nested(struct kd_spinlock *l, struct kd_regs *r, void *entry)
{
	return kd_wait_spin(&l->q, l, NULL, r, entry);
}

/* Tail-called by the entry stub when this CPU cannot publish. */
void kd_spin_lock_plain(struct kd_spinlock *l)
{
	kd_q_lock_plain(&l->q);
}

static __always_inline void __kd_raw_spin_lock(struct kd_spinlock *l)
{
	if (unlikely(!kd_q_trylock_fifo(&l->q)))
		kd_q_lock_plain(&l->q);
}

void kd_raw_spin_lock(struct kd_spinlock *l)
{
	preempt_disable();
	__kd_raw_spin_lock(l);
}
EXPORT_SYMBOL(kd_raw_spin_lock);

void kd_raw_spin_lock_irq(struct kd_spinlock *l)
{
	local_irq_disable();
	preempt_disable();
	__kd_raw_spin_lock(l);
}
EXPORT_SYMBOL(kd_raw_spin_lock_irq);

unsigned long kd_raw_spin_lock_irqsave(struct kd_spinlock *l)
{
	unsigned long flags;

	local_irq_save(flags);
	preempt_disable();
	__kd_raw_spin_lock(l);
	return flags;
}
EXPORT_SYMBOL(kd_raw_spin_lock_irqsave);

void kd_raw_spin_lock_bh(struct kd_spinlock *l)
{
	__local_bh_disable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET);
	__kd_raw_spin_lock(l);
}
EXPORT_SYMBOL(kd_raw_spin_lock_bh);

int kd_spin_trylock(struct kd_spinlock *l)
{
	preempt_disable();
	if (kd_q_trylock_fifo(&l->q))
		return 1;
	preempt_enable();
	return 0;
}
EXPORT_SYMBOL(kd_spin_trylock);

int kd_spin_trylock_bh(struct kd_spinlock *l)
{
	__local_bh_disable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET);
	if (kd_q_trylock_fifo(&l->q))
		return 1;
	__local_bh_enable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET);
	return 0;
}
EXPORT_SYMBOL(kd_spin_trylock_bh);

void kd_spin_unlock(struct kd_spinlock *l)
{
	kd_q_unlock(&l->q);
	preempt_enable();
}
EXPORT_SYMBOL(kd_spin_unlock);

void kd_spin_unlock_irq(struct kd_spinlock *l)
{
	kd_q_unlock(&l->q);
	local_irq_enable();
	preempt_enable();
}
EXPORT_SYMBOL(kd_spin_unlock_irq);

void kd_spin_unlock_irqrestore(struct kd_spinlock *l, unsigned long flags)
{
	kd_q_unlock(&l->q);
	local_irq_restore(flags);
	preempt_enable();
}
EXPORT_SYMBOL(kd_spin_unlock_irqrestore);

void kd_spin_unlock_bh(struct kd_spinlock *l)
{
	kd_q_unlock(&l->q);
	__local_bh_enable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET);
}
EXPORT_SYMBOL(kd_spin_unlock_bh);
