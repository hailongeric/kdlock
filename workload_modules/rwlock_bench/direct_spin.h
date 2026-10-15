/* SPDX-License-Identifier: GPL-2.0 */
/* Proc snapshots retain their original exclusive, ordinary spin semantics.
 * Only the snapshot entry delegates in KD; mutations are native controls. */
#ifdef RB_KDLOCK
#include "kd_spin_direct.h"
static kd_spinlock_t rb_lock __aligned(64) = KD_SPINLOCK_INITIALIZER;
extern char rb_entry[];
#define RB_BACKEND 2
#define RB_READ_LOCK() KD_SPIN_DIRECT_LOCK(&rb_lock, kd_spin_direct_cookie, \
	".globl rb_entry\nrb_entry:\n\t" ANNOTATE_NOENDBR)
#define RB_READ_UNLOCK() KD_SPIN_DIRECT_UNLOCK(&rb_lock, kd_spin_direct_cookie)
#define RB_WRITE_LOCK() do { preempt_disable(); kd_spin_direct_native_lock_inline(&rb_lock); } while (0)
#define RB_WRITE_UNLOCK() do { kd_spin_direct_native_release_inline(&rb_lock); preempt_enable(); } while (0)
#elif defined(RB_TCLOCK)
void komb_spin_lock(struct qspinlock *lock);
void komb_spin_unlock(struct qspinlock *lock);
static spinlock_t rb_lock __aligned(64) = __SPIN_LOCK_UNLOCKED(rb_lock);
#define RB_BACKEND 1
#define RB_READ_LOCK() do { preempt_disable(); komb_spin_lock((void *)&rb_lock); } while (0)
#define RB_READ_UNLOCK() do { komb_spin_unlock((void *)&rb_lock); preempt_enable(); } while (0)
#define RB_WRITE_LOCK() RB_READ_LOCK()
#define RB_WRITE_UNLOCK() RB_READ_UNLOCK()
#else
static spinlock_t rb_lock __aligned(64) = __SPIN_LOCK_UNLOCKED(rb_lock);
#define RB_BACKEND 0
#define RB_READ_LOCK() __raw_spin_lock(&rb_lock.rlock)
#define RB_READ_UNLOCK() __raw_spin_unlock(&rb_lock.rlock)
#define RB_WRITE_LOCK() RB_READ_LOCK()
#define RB_WRITE_UNLOCK() RB_READ_UNLOCK()
#endif

static int rb_prepare(void)
{
#ifdef RB_KDLOCK
	return kd_spin_prepare(&rb_lock, (unsigned long)rb_entry, KD_ENTRY_ABI_SPIN_CLOBBER_V1);
#else
	return 0;
#endif
}

static void rb_lock_snapshot(struct rw_bench_snapshot *s)
{
	s->lock_addr = s->gate_addr = (unsigned long)&rb_lock;
#ifdef RB_KDLOCK
	s->entry = (unsigned long)rb_entry;
	s->gate = atomic_read(&rb_lock.val);
#else
	s->gate = atomic_read(&rb_lock.rlock.raw_lock.val);
#endif
}
