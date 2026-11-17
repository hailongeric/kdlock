// SPDX-License-Identifier: GPL-2.0
/*
 * Whole-kernel switch (CONFIG_KDLOCK_ALL): the native mutex, ww_mutex and
 * rw_semaphore function names.
 *
 * kernel/locking/mutex.c and rwsem.c are not built with the switch. An
 * ordinary call of a lock operation is a macro (include/kdlock/kd_all_*.h)
 * that calls the kd entry from the caller's own code, so these functions are
 * reached only where a caller needs a real symbol: an address taken
 * (function pointers, the inline ww_mutex helpers of linux/ww_mutex.h), the
 * init functions the native inline wrappers call, and the few operations
 * that have no macro. Each one is the kd operation on the same object, so
 * an object is always used with the one protocol.
 *
 * The kd entries are reached through a call here, so an acquisition made
 * through one of these functions has this file as its delegation site;
 * that only affects which image the translator would build, never the
 * lock's behaviour.
 */
#define KD_ALL_NO_MAP
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/sched/debug.h>
#include <linux/mutex.h>
#include <linux/ww_mutex.h>
#include <linux/rwsem.h>
#include <linux/spinlock.h>
#include <linux/atomic.h>
#include <kdlock/kd_api.h>

/*
 * The lock tracepoints are instantiated by kernel/locking/mutex.c natively;
 * semaphore, rt_mutex and percpu-rwsem fire them. The kd locks do not.
 */
#define CREATE_TRACE_POINTS
#include <trace/events/lock.h>
EXPORT_TRACEPOINT_SYMBOL_GPL(contention_begin);
EXPORT_TRACEPOINT_SYMBOL_GPL(contention_end);

/* The casts in kd_all_spin.h and below rely on these layouts. */
static_assert(sizeof(arch_spinlock_t) == sizeof(struct kd_spinlock));
static_assert(offsetof(struct qspinlock, locked) == offsetof(struct kd_qlock, locked));
static_assert(offsetof(struct qspinlock, tail) == offsetof(struct kd_qlock, tail));
static_assert(sizeof(arch_rwlock_t) == sizeof(struct kd_rwlock));
static_assert(offsetof(arch_rwlock_t, wait_lock) == offsetof(struct kd_rwlock, wait));
static_assert(_QW_LOCKED == KD_RW_WLOCKED && _QW_WAITING == KD_RW_WWAIT);
static_assert(_QR_BIAS == KD_RW_RBIAS);
static_assert(sizeof(struct mutex) == 32);
static_assert(sizeof(struct rw_semaphore) == 40);
static_assert(offsetof(struct ww_mutex, base) == offsetof(struct kd_ww_mutex, base));
static_assert(offsetof(struct ww_mutex, ctx) == offsetof(struct kd_ww_mutex, ctx));
static_assert(sizeof(struct ww_mutex) == sizeof(struct kd_ww_mutex));

/* ---- mutex ------------------------------------------------------------------ */

void mutex_init_generic(struct mutex *lock)
{
	kd_mutex_init(&lock->kd);
}
EXPORT_SYMBOL(mutex_init_generic);

void __sched mutex_lock(struct mutex *lock)
{
	kd_mutex_lock(&lock->kd);
}
EXPORT_SYMBOL(mutex_lock);

int __sched mutex_lock_interruptible(struct mutex *lock)
{
	return kd_mutex_lock_interruptible(&lock->kd);
}
EXPORT_SYMBOL(mutex_lock_interruptible);

int __sched mutex_lock_killable(struct mutex *lock)
{
	return kd_mutex_lock_killable(&lock->kd);
}
EXPORT_SYMBOL(mutex_lock_killable);

void __sched mutex_lock_io(struct mutex *lock)
{
	kd_mutex_lock_io(&lock->kd);
}
EXPORT_SYMBOL_GPL(mutex_lock_io);

int __sched mutex_trylock(struct mutex *lock)
{
	return kd_mutex_trylock(&lock->kd);
}
EXPORT_SYMBOL(mutex_trylock);

void __sched mutex_unlock(struct mutex *lock)
{
	kd_mutex_unlock(&lock->kd);
}
EXPORT_SYMBOL(mutex_unlock);

bool mutex_is_locked(struct mutex *lock)
{
	return kd_mutex_is_locked(&lock->kd);
}
EXPORT_SYMBOL(mutex_is_locked);

unsigned long mutex_get_owner(struct mutex *lock)
{
	return kd_mutex_get_owner(&lock->kd);
}

/*
 * As in kernel/locking/mutex.c: return holding the mutex if the count
 * dropped to zero, otherwise without it.
 */
int atomic_dec_and_mutex_lock(atomic_t *cnt, struct mutex *lock)
{
	/* dec if we can't possibly hit 0 */
	if (atomic_add_unless(cnt, -1, 1))
		return 0;
	/* we might hit 0, so take the lock */
	kd_mutex_lock(&lock->kd);
	if (!atomic_dec_and_test(cnt)) {
		/* when we actually did the dec, we didn't hit 0 */
		kd_mutex_unlock(&lock->kd);
		return 0;
	}
	/* we hit 0, and we hold the lock */
	return 1;
}
EXPORT_SYMBOL(atomic_dec_and_mutex_lock);

/* ---- ww_mutex ----------------------------------------------------------------
 *
 * ww_mutex_init() (inline) initialises the base through mutex_init_generic()
 * and clears ->ctx, which is the kd_ww_mutex initial state. kd_ww_mutex
 * applies the wait-die rule to every class (kd_api.h).
 */
static __always_inline struct kd_ww_mutex *__kd_ww(struct ww_mutex *lock)
{
	return (struct kd_ww_mutex *)lock;
}

int __sched ww_mutex_lock(struct ww_mutex *lock, struct ww_acquire_ctx *ctx)
{
	return kd_ww_mutex_lock(__kd_ww(lock), ctx);
}
EXPORT_SYMBOL(ww_mutex_lock);

int __sched ww_mutex_lock_interruptible(struct ww_mutex *lock, struct ww_acquire_ctx *ctx)
{
	return kd_ww_mutex_lock_interruptible(__kd_ww(lock), ctx);
}
EXPORT_SYMBOL(ww_mutex_lock_interruptible);

int ww_mutex_trylock(struct ww_mutex *lock, struct ww_acquire_ctx *ctx)
{
	return kd_ww_mutex_trylock(__kd_ww(lock), ctx);
}
EXPORT_SYMBOL(ww_mutex_trylock);

void __sched ww_mutex_unlock(struct ww_mutex *lock)
{
	kd_ww_mutex_unlock(__kd_ww(lock));
}
EXPORT_SYMBOL(ww_mutex_unlock);

/* ---- rw_semaphore ------------------------------------------------------------ */

void __init_rwsem(struct rw_semaphore *sem, const char *name, struct lock_class_key *key)
{
	kd_rwsem_init(&sem->kd);
}
EXPORT_SYMBOL(__init_rwsem);

void __sched down_read(struct rw_semaphore *sem)
{
	kd_down_read(&sem->kd);
}
EXPORT_SYMBOL(down_read);

int __sched down_read_interruptible(struct rw_semaphore *sem)
{
	return kd_down_read_interruptible(&sem->kd);
}
EXPORT_SYMBOL(down_read_interruptible);

int __sched down_read_killable(struct rw_semaphore *sem)
{
	return kd_down_read_killable(&sem->kd);
}
EXPORT_SYMBOL(down_read_killable);

int down_read_trylock(struct rw_semaphore *sem)
{
	return kd_down_read_trylock(&sem->kd);
}
EXPORT_SYMBOL(down_read_trylock);

void __sched down_write(struct rw_semaphore *sem)
{
	kd_down_write(&sem->kd);
}
EXPORT_SYMBOL(down_write);

int __sched down_write_killable(struct rw_semaphore *sem)
{
	return kd_down_write_killable(&sem->kd);
}
EXPORT_SYMBOL(down_write_killable);

int down_write_trylock(struct rw_semaphore *sem)
{
	return kd_down_write_trylock(&sem->kd);
}
EXPORT_SYMBOL(down_write_trylock);

void up_read(struct rw_semaphore *sem)
{
	kd_up_read(&sem->kd);
}
EXPORT_SYMBOL(up_read);

void up_write(struct rw_semaphore *sem)
{
	kd_up_write(&sem->kd);
}
EXPORT_SYMBOL(up_write);

void downgrade_write(struct rw_semaphore *sem)
{
	kd_downgrade_write(&sem->kd);
}
EXPORT_SYMBOL(downgrade_write);
