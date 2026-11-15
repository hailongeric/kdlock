/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Mapping of the Linux lock API onto kdlock (Linux 7.0, x86_64, !PREEMPT_RT).
 *
 * This header is the reference for the kernel patch described in
 * README.md in this directory; it is not included by the kdlock core.
 * Each block names the native header whose definitions it replaces, and
 * covers every operation that header declares in Linux 7.0. The lockdep
 * variants (_nested, _nest_lock) take a subclass or an outer lock only for
 * lockdep, which CONFIG_KDLOCK excludes, so they map to the plain call.
 *
 * Two rules decide every mapping:
 *
 *  1. Every lock operation is an out-of-line call to a kd_ symbol. No
 *     inline fast paths, including releases: generated code recognises
 *     lock operations by call target.
 *
 *  2. spinlock_t, rwlock_t, struct mutex and struct rw_semaphore users get
 *     the delegable entries. raw_spinlock_t users get the kd_raw_ entries,
 *     which never publish a continuation: raw locks protect the scheduler
 *     and interrupt paths whose sections must stay on their own CPU.
 */
#ifndef KD_LINUX_MAP_H
#define KD_LINUX_MAP_H

#include <kdlock/kd_api.h>

/* ---- asm/spinlock_types.h, asm-generic/qspinlock_types.h ------------------ */

typedef struct kd_spinlock arch_spinlock_t;
#define __ARCH_SPIN_LOCK_UNLOCKED	__KD_SPIN_UNLOCKED

typedef struct kd_rwlock arch_rwlock_t;
#define __ARCH_RW_LOCK_UNLOCKED		__KD_RW_UNLOCKED

/* ---- asm/spinlock.h: arch_ operations -------------------------------------
 *
 * Used directly only by code that manages preemption itself (for example
 * arch_spin_lock() in tracing and printk). Those callers are never
 * delegated; note that the kd_raw_ entries include the preempt count
 * change that the arch_ level traditionally leaves to its caller, so the
 * few remaining arch_ users need the adjustment shown in the README.
 */
#define arch_spin_is_locked(l)		kd_spin_is_locked(l)
#define arch_spin_is_contended(l)	kd_spin_is_contended(l)
#define arch_spin_value_unlocked(l)	(!atomic_read(&(l).q.val))
#define arch_spin_lock(l)		kd_arch_spin_lock(l)
#define arch_spin_trylock(l)		kd_arch_spin_trylock(l)
#define arch_spin_unlock(l)		kd_arch_spin_unlock(l)

/* ---- asm-generic/qrwlock.h: arch_ operations (preemption left to the caller) */
#define arch_read_lock(l)		kd_arch_read_lock(l)
#define arch_read_trylock(l)		kd_arch_read_trylock(l)
#define arch_read_unlock(l)		kd_arch_read_unlock(l)
#define arch_write_lock(l)		kd_arch_write_lock(l)
#define arch_write_trylock(l)		kd_arch_write_trylock(l)
#define arch_write_unlock(l)		kd_arch_write_unlock(l)
#define arch_rwlock_is_contended(l)	kd_rwlock_is_contended(l)

/* ---- linux/spinlock_api_smp.h: raw_spinlock_t ----------------------------- */

#define _raw_spin_lock(lock)		kd_raw_spin_lock(&(lock)->raw_lock)
#define _raw_spin_lock_irq(lock)	kd_raw_spin_lock_irq(&(lock)->raw_lock)
#define _raw_spin_lock_irqsave(lock)	kd_raw_spin_lock_irqsave(&(lock)->raw_lock)
#define _raw_spin_lock_bh(lock)		kd_raw_spin_lock_bh(&(lock)->raw_lock)
#define _raw_spin_lock_nested(lock, subclass)	kd_raw_spin_lock(&(lock)->raw_lock)
#define _raw_spin_lock_nest_lock(lock, map)	kd_raw_spin_lock(&(lock)->raw_lock)
#define _raw_spin_lock_irqsave_nested(lock, subclass) \
	kd_raw_spin_lock_irqsave(&(lock)->raw_lock)
#define _raw_spin_trylock(lock)		kd_spin_trylock(&(lock)->raw_lock)
#define _raw_spin_trylock_bh(lock)	kd_spin_trylock_bh(&(lock)->raw_lock)
#define _raw_spin_trylock_irq(lock)	kd_spin_trylock_irq(&(lock)->raw_lock)
#define _raw_spin_trylock_irqsave(lock, flags) \
	kd_spin_trylock_irqsave(&(lock)->raw_lock, flags)
#define _raw_spin_unlock(lock)		kd_spin_unlock(&(lock)->raw_lock)
#define _raw_spin_unlock_irq(lock)	kd_spin_unlock_irq(&(lock)->raw_lock)
#define _raw_spin_unlock_irqrestore(lock, flags) \
	kd_spin_unlock_irqrestore(&(lock)->raw_lock, flags)
#define _raw_spin_unlock_bh(lock)	kd_spin_unlock_bh(&(lock)->raw_lock)

/* ---- linux/spinlock.h: spinlock_t (delegable) ------------------------------
 *
 * spin_lock() and friends normally forward to raw_spin_lock(&lock->rlock).
 * They are redirected here instead so that only spinlock_t users publish
 * continuations. Releases are shared with the raw API: the release of a
 * lock that is not a session root is an ordinary native call.
 */
#define kd_map_spin_lock(lock)		kd_spin_lock(&(lock)->rlock.raw_lock)
#define kd_map_spin_lock_irq(lock)	kd_spin_lock_irq(&(lock)->rlock.raw_lock)
#define kd_map_spin_lock_irqsave(lock, flags) \
	do { (flags) = kd_spin_lock_irqsave(&(lock)->rlock.raw_lock); } while (0)
#define kd_map_spin_lock_bh(lock)	kd_spin_lock_bh(&(lock)->rlock.raw_lock)
#define kd_map_spin_lock_nested(lock, subclass)	kd_map_spin_lock(lock)
#define kd_map_spin_lock_nest_lock(lock, outer)	kd_map_spin_lock(lock)
#define kd_map_spin_lock_irqsave_nested(lock, flags, subclass) \
	kd_map_spin_lock_irqsave(lock, flags)
/*
 * spin_trylock*(), spin_unlock*(), spin_is_locked(), spin_is_contended(),
 * spin_needbreak(), assert_spin_locked() and atomic_dec_and_lock*() keep
 * their generic definitions, which reach the _raw_ layer above.
 */

/* ---- linux/rwlock_api_smp.h ------------------------------------------------ */

#define _raw_read_lock(lock)		kd_read_lock(&(lock)->raw_lock)
#define _raw_read_lock_irq(lock)	kd_read_lock_irq(&(lock)->raw_lock)
#define _raw_read_lock_irqsave(lock)	kd_read_lock_irqsave(&(lock)->raw_lock)
#define _raw_read_lock_bh(lock)		kd_read_lock_bh(&(lock)->raw_lock)
#define _raw_read_trylock(lock)		kd_read_trylock(&(lock)->raw_lock)
#define _raw_read_unlock(lock)		kd_read_unlock(&(lock)->raw_lock)
#define _raw_read_unlock_irq(lock)	kd_read_unlock_irq(&(lock)->raw_lock)
#define _raw_read_unlock_irqrestore(lock, flags) \
	kd_read_unlock_irqrestore(&(lock)->raw_lock, flags)
#define _raw_read_unlock_bh(lock)	kd_read_unlock_bh(&(lock)->raw_lock)

#define _raw_write_lock(lock)		kd_write_lock(&(lock)->raw_lock)
#define _raw_write_lock_irq(lock)	kd_write_lock_irq(&(lock)->raw_lock)
#define _raw_write_lock_irqsave(lock)	kd_write_lock_irqsave(&(lock)->raw_lock)
#define _raw_write_lock_bh(lock)	kd_write_lock_bh(&(lock)->raw_lock)
#define _raw_write_lock_nested(lock, subclass)	kd_write_lock(&(lock)->raw_lock)
#define _raw_write_trylock(lock)	kd_write_trylock(&(lock)->raw_lock)
#define _raw_write_trylock_irqsave(lock, flags) \
	kd_write_trylock_irqsave(&(lock)->raw_lock, flags)
#define _raw_write_unlock(lock)		kd_write_unlock(&(lock)->raw_lock)
#define _raw_write_unlock_irq(lock)	kd_write_unlock_irq(&(lock)->raw_lock)
#define _raw_write_unlock_irqrestore(lock, flags) \
	kd_write_unlock_irqrestore(&(lock)->raw_lock, flags)
#define _raw_write_unlock_bh(lock)	kd_write_unlock_bh(&(lock)->raw_lock)

/* ---- linux/mutex_types.h, linux/mutex.h ------------------------------------
 *
 * struct mutex becomes a wrapper with the same 32 bytes:
 *
 *	struct mutex { struct kd_mutex kd; };
 */
#define kd_map_mutex_init(m)			kd_mutex_init(&(m)->kd)
#define kd_map_mutex_lock(m)			kd_mutex_lock(&(m)->kd)
#define kd_map_mutex_lock_interruptible(m)	kd_mutex_lock_interruptible(&(m)->kd)
#define kd_map_mutex_lock_killable(m)		kd_mutex_lock_killable(&(m)->kd)
#define kd_map_mutex_lock_io(m)			kd_mutex_lock_io(&(m)->kd)
#define kd_map_mutex_trylock(m)			kd_mutex_trylock(&(m)->kd)
#define kd_map_mutex_unlock(m)			kd_mutex_unlock(&(m)->kd)
#define kd_map_mutex_is_locked(m)		kd_mutex_is_locked(&(m)->kd)
#define kd_map_mutex_get_owner(m)		kd_mutex_get_owner(&(m)->kd)
#define kd_map_mutex_destroy(m)			do { } while (0)
#define kd_map_mutex_lock_nested(m, subclass)	kd_map_mutex_lock(m)
#define kd_map_mutex_lock_interruptible_nested(m, subclass) \
	kd_map_mutex_lock_interruptible(m)
#define kd_map_mutex_lock_killable_nested(m, subclass) \
	kd_map_mutex_lock_killable(m)
#define kd_map_mutex_lock_io_nested(m, subclass)	kd_map_mutex_lock_io(m)
#define kd_map_mutex_lock_nest_lock(m, outer)	kd_map_mutex_lock(m)
#define kd_map_mutex_lock_killable_nest_lock(m, outer) \
	kd_map_mutex_lock_killable(m)
#define kd_map_mutex_trylock_nest_lock(m, outer)	kd_map_mutex_trylock(m)
/*
 * atomic_dec_and_mutex_lock(), devm_mutex_init() and the guard classes
 * (mutex, mutex_try, mutex_intr) keep their generic definitions.
 */

/* ---- linux/ww_mutex.h ------------------------------------------------------
 *
 *	struct ww_mutex { struct kd_ww_mutex kd; };
 *
 * struct ww_acquire_ctx, struct ww_class and ww_acquire_init/done/fini()
 * stay as they are.
 */
#define kd_map_ww_mutex_init(l, cls)		kd_ww_mutex_init(&(l)->kd, cls)
#define kd_map_ww_mutex_lock(l, ctx)		kd_ww_mutex_lock(&(l)->kd, ctx)
#define kd_map_ww_mutex_lock_interruptible(l, ctx) \
	kd_ww_mutex_lock_interruptible(&(l)->kd, ctx)
#define kd_map_ww_mutex_lock_slow(l, ctx)	kd_ww_mutex_lock_slow(&(l)->kd, ctx)
#define kd_map_ww_mutex_lock_slow_interruptible(l, ctx) \
	kd_ww_mutex_lock_slow_interruptible(&(l)->kd, ctx)
#define kd_map_ww_mutex_trylock(l, ctx)		kd_ww_mutex_trylock(&(l)->kd, ctx)
#define kd_map_ww_mutex_unlock(l)		kd_ww_mutex_unlock(&(l)->kd)
#define kd_map_ww_mutex_is_locked(l)		kd_ww_mutex_is_locked(&(l)->kd)
#define kd_map_ww_mutex_destroy(l)		do { } while (0)

/* ---- linux/rwsem.h -----------------------------------------------------------
 *
 *	struct rw_semaphore { struct kd_rwsem kd; };	(40 bytes, as native)
 */
#define kd_map_init_rwsem(s)			kd_rwsem_init(&(s)->kd)
#define kd_map_down_read(s)			kd_down_read(&(s)->kd)
#define kd_map_down_read_interruptible(s)	kd_down_read_interruptible(&(s)->kd)
#define kd_map_down_read_killable(s)		kd_down_read_killable(&(s)->kd)
#define kd_map_down_read_trylock(s)		kd_down_read_trylock(&(s)->kd)
#define kd_map_up_read(s)			kd_up_read(&(s)->kd)
#define kd_map_down_write(s)			kd_down_write(&(s)->kd)
#define kd_map_down_write_killable(s)		kd_down_write_killable(&(s)->kd)
#define kd_map_down_write_trylock(s)		kd_down_write_trylock(&(s)->kd)
#define kd_map_up_write(s)			kd_up_write(&(s)->kd)
#define kd_map_downgrade_write(s)		kd_downgrade_write(&(s)->kd)
#define kd_map_rwsem_is_locked(s)		kd_rwsem_is_locked(&(s)->kd)
#define kd_map_rwsem_is_contended(s)		kd_rwsem_is_contended(&(s)->kd)
#define kd_map_rwsem_assert_held(s)		WARN_ON(!kd_rwsem_is_locked(&(s)->kd))
#define kd_map_rwsem_assert_held_write(s) \
	WARN_ON(!kd_rwsem_is_write_locked(&(s)->kd))
/* No owner is recorded for readers, so the non-owner forms are the plain ones. */
#define kd_map_down_read_non_owner(s)		kd_map_down_read(s)
#define kd_map_up_read_non_owner(s)		kd_map_up_read(s)
#define kd_map_down_read_nested(s, subclass)	kd_map_down_read(s)
#define kd_map_down_read_killable_nested(s, subclass) \
	kd_map_down_read_killable(s)
#define kd_map_down_write_nested(s, subclass)	kd_map_down_write(s)
#define kd_map_down_write_killable_nested(s, subclass) \
	kd_map_down_write_killable(s)
#define kd_map_down_write_nest_lock(s, outer)	kd_map_down_write(s)

#endif /* KD_LINUX_MAP_H */
