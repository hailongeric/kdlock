// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock rwlock.
 *
 * Count word as in qrwlock: writer byte, writer-waiting bit, reader count.
 * ->wait orders slow-path readers and writers.
 *
 * Writers are delegable. A queued writer that reaches the queue head takes
 * the writer byte and then, as combiner, keeps both the byte and ->wait
 * while it executes the writers queued behind it. Queued readers are not
 * delegable, so a session stops at the first reader and FIFO order between
 * readers and writers is preserved.
 *
 * Readers always run on their own task; reader concurrency is unchanged.
 *
 * Releasing the write lock clears the writer byte and nothing else. After
 * a handback the origin therefore releases with the ordinary call, while
 * the combiner still holds ->wait and reacquires the byte as next writer.
 */
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/preempt.h>
#include <linux/bottom_half.h>
#include <linux/irqflags.h>
#include <linux/hardirq.h>
#include "kd_internal.h"

/* Queue head holds ->wait: wait for readers and a fast-path writer to leave. */
static bool kd_rw_post(void *root)
{
	struct kd_rwlock *rw = root;
	int c;

	atomic_or(KD_RW_WWAIT, &rw->cnts);
	do {
		c = atomic_cond_read_relaxed(&rw->cnts, VAL == KD_RW_WWAIT);
	} while (!atomic_try_cmpxchg_acquire(&rw->cnts, &c, KD_RW_WLOCKED));
	return true;
}

static void kd_rw_release_wait(void *root)
{
	struct kd_rwlock *rw = root;

	kd_q_unlock(&rw->wait);
}

static const struct kd_family kd_rw_family = {
	.post		= kd_rw_post,
	.release	= kd_rw_release_wait,
	.keeps_q	= true,
};

/* Called by the entry stub on the wait stack. */
int kd_write_wait(struct kd_rwlock *rw)
{
	int ret = kd_wait_spin(&rw->wait, rw, &kd_rw_family, NULL, NULL);

	if (ret == KD_WAIT_RESUMED)
		kd_finish_resume(0);
	return ret;
}

/* Contended kd_write_lock*() inside a section; see kd_nested_acquire(). */
int kd_write_nested(struct kd_rwlock *rw, struct kd_regs *r, void *entry)
{
	return kd_wait_spin(&rw->wait, rw, &kd_rw_family, r, entry);
}

/* Tail-called by the entry stub when this CPU cannot publish. */
void kd_write_lock_plain(struct kd_rwlock *rw)
{
	kd_q_lock_plain(&rw->wait);
	kd_rw_post(rw);
	kd_q_unlock(&rw->wait);
}

int kd_write_trylock(struct kd_rwlock *rw)
{
	int c = 0;

	preempt_disable();
	if (atomic_try_cmpxchg_acquire(&rw->cnts, &c, KD_RW_WLOCKED))
		return 1;
	preempt_enable();
	return 0;
}
EXPORT_SYMBOL(kd_write_trylock);

void kd_write_unlock(struct kd_rwlock *rw)
{
	smp_store_release(&rw->wlocked, 0);
	preempt_enable();
}
EXPORT_SYMBOL(kd_write_unlock);

void kd_write_unlock_irq(struct kd_rwlock *rw)
{
	smp_store_release(&rw->wlocked, 0);
	local_irq_enable();
	preempt_enable();
}
EXPORT_SYMBOL(kd_write_unlock_irq);

void kd_write_unlock_irqrestore(struct kd_rwlock *rw, unsigned long flags)
{
	smp_store_release(&rw->wlocked, 0);
	local_irq_restore(flags);
	preempt_enable();
}
EXPORT_SYMBOL(kd_write_unlock_irqrestore);

void kd_write_unlock_bh(struct kd_rwlock *rw)
{
	smp_store_release(&rw->wlocked, 0);
	__local_bh_enable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET);
}
EXPORT_SYMBOL(kd_write_unlock_bh);

/* ---- readers ---------------------------------------------------------------- */

static noinline void kd_read_lock_slow(struct kd_rwlock *rw)
{
	/*
	 * A reader in interrupt context may be nested inside a reader of the
	 * same lock on this CPU. It must not queue behind a waiting writer;
	 * it keeps its count and only waits for an active writer.
	 */
	if (unlikely(in_interrupt())) {
		atomic_cond_read_acquire(&rw->cnts, !(VAL & KD_RW_WLOCKED));
		return;
	}
	atomic_sub(KD_RW_RBIAS, &rw->cnts);

	kd_q_lock_plain(&rw->wait);
	atomic_add(KD_RW_RBIAS, &rw->cnts);
	/* Holding ->wait excludes queued writers; a trylock writer may be active. */
	atomic_cond_read_acquire(&rw->cnts, !(VAL & KD_RW_WLOCKED));
	kd_q_unlock(&rw->wait);
}

static __always_inline void __kd_read_lock(struct kd_rwlock *rw)
{
	int c = atomic_add_return_acquire(KD_RW_RBIAS, &rw->cnts);

	if (unlikely(c & KD_RW_WMASK))
		kd_read_lock_slow(rw);
}

void kd_read_lock(struct kd_rwlock *rw)
{
	preempt_disable();
	__kd_read_lock(rw);
}
EXPORT_SYMBOL(kd_read_lock);

void kd_read_lock_irq(struct kd_rwlock *rw)
{
	local_irq_disable();
	preempt_disable();
	__kd_read_lock(rw);
}
EXPORT_SYMBOL(kd_read_lock_irq);

unsigned long kd_read_lock_irqsave(struct kd_rwlock *rw)
{
	unsigned long flags;

	local_irq_save(flags);
	preempt_disable();
	__kd_read_lock(rw);
	return flags;
}
EXPORT_SYMBOL(kd_read_lock_irqsave);

void kd_read_lock_bh(struct kd_rwlock *rw)
{
	__local_bh_disable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET);
	__kd_read_lock(rw);
}
EXPORT_SYMBOL(kd_read_lock_bh);

int kd_read_trylock(struct kd_rwlock *rw)
{
	int c;

	preempt_disable();
	c = atomic_read(&rw->cnts);
	if (likely(!(c & KD_RW_WMASK))) {
		c = atomic_add_return_acquire(KD_RW_RBIAS, &rw->cnts);
		if (likely(!(c & KD_RW_WMASK)))
			return 1;
		atomic_sub(KD_RW_RBIAS, &rw->cnts);
	}
	preempt_enable();
	return 0;
}
EXPORT_SYMBOL(kd_read_trylock);

static __always_inline void __kd_read_unlock(struct kd_rwlock *rw)
{
	(void)atomic_sub_return_release(KD_RW_RBIAS, &rw->cnts);
}

void kd_read_unlock(struct kd_rwlock *rw)
{
	__kd_read_unlock(rw);
	preempt_enable();
}
EXPORT_SYMBOL(kd_read_unlock);

void kd_read_unlock_irq(struct kd_rwlock *rw)
{
	__kd_read_unlock(rw);
	local_irq_enable();
	preempt_enable();
}
EXPORT_SYMBOL(kd_read_unlock_irq);

void kd_read_unlock_irqrestore(struct kd_rwlock *rw, unsigned long flags)
{
	__kd_read_unlock(rw);
	local_irq_restore(flags);
	preempt_enable();
}
EXPORT_SYMBOL(kd_read_unlock_irqrestore);

void kd_read_unlock_bh(struct kd_rwlock *rw)
{
	__kd_read_unlock(rw);
	__local_bh_enable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET);
}
EXPORT_SYMBOL(kd_read_unlock_bh);
