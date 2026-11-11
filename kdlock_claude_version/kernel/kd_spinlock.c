// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock spinlock.
 *
 * The lock is the queue word itself: FIFO MCS queue, no pending bit. The
 * delegable acquire entries live in kd_entry.S; this file has their slow
 * paths, the raw (never delegated) acquires, trylock and release.
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

/* Called by the entry stub on the wait stack; see kd_entry.S. */
int kd_spin_wait(struct kd_spinlock *l)
{
	int ret = kd_wait_spin(&l->q, l, NULL, NULL, NULL);

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
