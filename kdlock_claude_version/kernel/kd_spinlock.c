// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock spinlock.
 *
 * The lock is the queue word itself, with the layout and, as long as the
 * lock is in plain mode, the algorithm of the native queued spinlock: fast
 * path, one pending waiter, then an MCS queue whose head takes the lock.
 * A contended caller then waits on its own stack and publishes nothing.
 *
 * In delegation mode (kd_core.c, "adaptive delegation") a contended caller
 * of a delegable entry publishes its continuation instead, and the queue
 * head executes the sections of the waiters behind it. The delegable
 * acquire entries live in kd_entry.S; this file has their slow paths, the
 * raw (never delegated) acquires, trylock and release.
 *
 * Release is a byte store. A waiter whose section was handed back owns the
 * lock like anyone else; its release additionally takes the queue head
 * role over from the combiner that handed it back (kd_release_combine()).
 */
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/preempt.h>
#include <linux/bottom_half.h>
#include <linux/irqflags.h>
#include "kd_internal.h"

/* Nothing family specific: the queue word is the whole lock. */
static const struct kd_family kd_spin_family = { };

/*
 * Release the lock byte. A holder with an offer to answer (role exchange,
 * kd_core.c) first serves the queue; if a section is handed back during
 * that, the lock went with it and stays held. The test reads this CPU's
 * own state, not the lock word.
 */
static __always_inline void kd_spin_release(struct kd_spinlock *l)
{
	if (unlikely(raw_cpu_read(kd_cpu.xcount)) &&
	    kd_release_combine(&l->q, NULL, l, &kd_spin_family))
		return;
	kd_q_unlock(&l->q);
}

/* The entry stubs pass the lock where kd_q_lock_slow() takes the queue word. */
static_assert(offsetof(struct kd_spinlock, q) == 0);

/* Called by the entry stub on the wait stack; see kd_entry.S. */
int kd_spin_wait(struct kd_spinlock *l)
{
	int ret = kd_wait_spin(&l->q, l, &kd_spin_family, NULL, NULL);

	if (ret == KD_WAIT_RESUMED)
		kd_finish_resume(0);
	return ret;
}

/* Contended kd_spin_lock*() inside a section; see kd_nested_acquire(). */
int kd_spin_nested(struct kd_spinlock *l, struct kd_regs *r, void *entry)
{
	u32 val;

	if (kd_q_pending(&l->q, &val))
		return KD_WAIT_LOCAL;
	if (!entry || !kd_q_deleg_mode(&l->q, val)) {
		kd_q_queue(&l->q, true);
		return KD_WAIT_LOCAL;
	}
	return kd_wait_spin(&l->q, l, &kd_spin_family, r, entry);
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

/*
 * arch_spin_*() level: the caller manages preemption itself (tracing,
 * printk, architecture code). Never delegated.
 */
void kd_arch_spin_lock(struct kd_spinlock *l)
{
	__kd_raw_spin_lock(l);
}
EXPORT_SYMBOL(kd_arch_spin_lock);

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

int kd_spin_trylock_irq(struct kd_spinlock *l)
{
	local_irq_disable();
	if (kd_spin_trylock(l))
		return 1;
	local_irq_enable();
	return 0;
}
EXPORT_SYMBOL(kd_spin_trylock_irq);

int kd_spin_trylock_irqsave(struct kd_spinlock *l, unsigned long *flags)
{
	local_irq_save(*flags);
	if (kd_spin_trylock(l))
		return 1;
	local_irq_restore(*flags);
	return 0;
}
EXPORT_SYMBOL(kd_spin_trylock_irqsave);

void kd_spin_unlock(struct kd_spinlock *l)
{
	kd_spin_release(l);
	preempt_enable();
}
EXPORT_SYMBOL(kd_spin_unlock);

void kd_spin_unlock_irq(struct kd_spinlock *l)
{
	kd_spin_release(l);
	local_irq_enable();
	preempt_enable();
}
EXPORT_SYMBOL(kd_spin_unlock_irq);

void kd_spin_unlock_irqrestore(struct kd_spinlock *l, unsigned long flags)
{
	kd_spin_release(l);
	local_irq_restore(flags);
	preempt_enable();
}
EXPORT_SYMBOL(kd_spin_unlock_irqrestore);

void kd_spin_unlock_bh(struct kd_spinlock *l)
{
	kd_spin_release(l);
	__local_bh_enable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET);
}
EXPORT_SYMBOL(kd_spin_unlock_bh);
