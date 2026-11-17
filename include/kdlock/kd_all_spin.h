/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Whole-kernel switch (CONFIG_KDLOCK_ALL): spinlock_t and rwlock_t.
 *
 * Included by linux/spinlock.h after its native spinlock_t operations and
 * before its lock guard classes, so that the guards expand to these macros
 * too. The lock types keep their native layout: a kd spinlock is a queued
 * spinlock word with the same fields, and a kd rwlock is a qrwlock (count
 * word plus wait lock) with the same reader bias and writer bits
 * (static_assert in kernel/kd_all.c).
 *
 * Every operation on a spinlock_t or rwlock_t becomes a call to the kd
 * entry, made from the code that holds the lock: the acquisition is a
 * delegation site, and the release is the direct call that ends a
 * delegated section. raw_spinlock_t is not redefined here. Its operations
 * keep the generic layer (kernel/locking/spinlock.c), which reaches the
 * kd queue algorithm through the arch_spin_*() level (asm-generic/
 * qspinlock.h and qrwlock.h, also changed by integration/apply_all.py),
 * and never publish a continuation. A raw operation on the raw lock
 * inside a spinlock_t (&lock->rlock) therefore follows the same queue
 * protocol as the spinlock_t operations.
 *
 * Without the translator every entry below is a plain queued lock.
 */
#ifndef _KDLOCK_KD_ALL_SPIN_H
#define _KDLOCK_KD_ALL_SPIN_H

#include <linux/typecheck.h>
#include <kdlock/kd_api.h>

static __always_inline struct kd_spinlock *__kd_all_sl(spinlock_t *lock)
{
	return (struct kd_spinlock *)&lock->rlock.raw_lock;
}

static __always_inline struct kd_rwlock *__kd_all_rw(rwlock_t *lock)
{
	return (struct kd_rwlock *)&lock->raw_lock;
}

/* ---- spinlock_t ------------------------------------------------------------ */

#define spin_lock(lock)			kd_spin_lock(__kd_all_sl(lock))
#define spin_lock_bh(lock)		kd_spin_lock_bh(__kd_all_sl(lock))
#define spin_lock_irq(lock)		kd_spin_lock_irq(__kd_all_sl(lock))
#undef spin_lock_irqsave
#define spin_lock_irqsave(lock, flags)					\
do {									\
	typecheck(unsigned long, flags);				\
	(flags) = kd_spin_lock_irqsave(__kd_all_sl(lock));		\
} while (0)

/* The subclass and the outer lock are lockdep annotations only. */
#undef spin_lock_nested
#define spin_lock_nested(lock, subclass)				\
do {									\
	(void)(subclass);						\
	spin_lock(lock);						\
} while (0)
#undef spin_lock_nest_lock
#define spin_lock_nest_lock(lock, nest_lock)				\
do {									\
	(void)(nest_lock);						\
	spin_lock(lock);						\
} while (0)
#undef spin_lock_irqsave_nested
#define spin_lock_irqsave_nested(lock, flags, subclass)			\
do {									\
	(void)(subclass);						\
	spin_lock_irqsave(lock, flags);					\
} while (0)

#define spin_trylock(lock)		kd_spin_trylock(__kd_all_sl(lock))
#define spin_trylock_bh(lock)		kd_spin_trylock_bh(__kd_all_sl(lock))
#define spin_trylock_irq(lock)		kd_spin_trylock_irq(__kd_all_sl(lock))
#undef spin_trylock_irqsave
#define spin_trylock_irqsave(lock, flags)				\
	kd_spin_trylock_irqsave(__kd_all_sl(lock), &(flags))

#define spin_unlock(lock)		kd_spin_unlock(__kd_all_sl(lock))
#define spin_unlock_bh(lock)		kd_spin_unlock_bh(__kd_all_sl(lock))
#define spin_unlock_irq(lock)		kd_spin_unlock_irq(__kd_all_sl(lock))
#define spin_unlock_irqrestore(lock, flags)				\
	kd_spin_unlock_irqrestore(__kd_all_sl(lock), flags)

/*
 * spin_lock_init(), spin_is_locked(), spin_is_contended(),
 * assert_spin_locked() and spin_needbreak() keep their native definitions:
 * the zero word is the unlocked state of both locks, and the native state
 * tests read the same fields.
 */

/* ---- rwlock_t ---------------------------------------------------------------
 *
 * Writers use the delegable entries, readers always run locally.
 */
#undef read_lock
#define read_lock(lock)			kd_read_lock(__kd_all_rw(lock))
#undef read_lock_bh
#define read_lock_bh(lock)		kd_read_lock_bh(__kd_all_rw(lock))
#undef read_lock_irq
#define read_lock_irq(lock)		kd_read_lock_irq(__kd_all_rw(lock))
#undef read_lock_irqsave
#define read_lock_irqsave(lock, flags)					\
do {									\
	typecheck(unsigned long, flags);				\
	(flags) = kd_read_lock_irqsave(__kd_all_rw(lock));		\
} while (0)
#undef read_trylock
#define read_trylock(lock)		kd_read_trylock(__kd_all_rw(lock))
#undef read_unlock
#define read_unlock(lock)		kd_read_unlock(__kd_all_rw(lock))
#undef read_unlock_bh
#define read_unlock_bh(lock)		kd_read_unlock_bh(__kd_all_rw(lock))
#undef read_unlock_irq
#define read_unlock_irq(lock)		kd_read_unlock_irq(__kd_all_rw(lock))
#undef read_unlock_irqrestore
#define read_unlock_irqrestore(lock, flags)				\
do {									\
	typecheck(unsigned long, flags);				\
	kd_read_unlock_irqrestore(__kd_all_rw(lock), flags);		\
} while (0)

#undef write_lock
#define write_lock(lock)		kd_write_lock(__kd_all_rw(lock))
#undef write_lock_nested
#define write_lock_nested(lock, subclass)				\
do {									\
	(void)(subclass);						\
	write_lock(lock);						\
} while (0)
#undef write_lock_bh
#define write_lock_bh(lock)		kd_write_lock_bh(__kd_all_rw(lock))
#undef write_lock_irq
#define write_lock_irq(lock)		kd_write_lock_irq(__kd_all_rw(lock))
#undef write_lock_irqsave
#define write_lock_irqsave(lock, flags)					\
do {									\
	typecheck(unsigned long, flags);				\
	(flags) = kd_write_lock_irqsave(__kd_all_rw(lock));		\
} while (0)
#undef write_trylock
#define write_trylock(lock)		kd_write_trylock(__kd_all_rw(lock))
#undef write_trylock_irqsave
#define write_trylock_irqsave(lock, flags)				\
	kd_write_trylock_irqsave(__kd_all_rw(lock), &(flags))
#undef write_unlock
#define write_unlock(lock)		kd_write_unlock(__kd_all_rw(lock))
#undef write_unlock_bh
#define write_unlock_bh(lock)		kd_write_unlock_bh(__kd_all_rw(lock))
#undef write_unlock_irq
#define write_unlock_irq(lock)		kd_write_unlock_irq(__kd_all_rw(lock))
#undef write_unlock_irqrestore
#define write_unlock_irqrestore(lock, flags)				\
do {									\
	typecheck(unsigned long, flags);				\
	kd_write_unlock_irqrestore(__kd_all_rw(lock), flags);		\
} while (0)

/* rwlock_init() and rwlock_is_contended() keep their native definitions. */

#endif /* _KDLOCK_KD_ALL_SPIN_H */
