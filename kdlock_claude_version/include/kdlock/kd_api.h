/* SPDX-License-Identifier: GPL-2.0 */
/*
 * kdlock public lock API.
 *
 * Every lock operation is an out-of-line call. That is a protocol
 * requirement, not a style choice: generated code recognises lock
 * operations by their call target, so an inlined release would let a
 * delegated critical section run past its end.
 *
 * "Delegable" entries are assembly stubs (kd_entry.S). While their lock is
 * in delegation mode, a contended caller records its continuation and the
 * lock holder may run the caller's critical section from generated code.
 * All other entries always execute on the calling task.
 *
 * The API covers every variant the Linux 7.0 headers declare for
 * spinlock_t, raw_spinlock_t, rwlock_t, struct mutex, struct ww_mutex and
 * struct rw_semaphore; integration/kd_linux_map.h lists the mapping. The
 * lockdep-only variants (_nested, _nest_lock) have no counterpart here:
 * without lockdep they are the plain operations.
 */
#ifndef _KDLOCK_KD_API_H
#define _KDLOCK_KD_API_H

#include <kdlock/kd_types.h>

/* ---- spinlock --------------------------------------------------------- */

/* Delegable. */
void kd_spin_lock(struct kd_spinlock *l);
void kd_spin_lock_irq(struct kd_spinlock *l);
unsigned long kd_spin_lock_irqsave(struct kd_spinlock *l);
void kd_spin_lock_bh(struct kd_spinlock *l);

/* Never delegated: for raw_spinlock_t users (scheduler, timers, lock internals). */
void kd_raw_spin_lock(struct kd_spinlock *l);
void kd_raw_spin_lock_irq(struct kd_spinlock *l);
unsigned long kd_raw_spin_lock_irqsave(struct kd_spinlock *l);
void kd_raw_spin_lock_bh(struct kd_spinlock *l);

int kd_spin_trylock(struct kd_spinlock *l);
int kd_spin_trylock_bh(struct kd_spinlock *l);
int kd_spin_trylock_irq(struct kd_spinlock *l);
int kd_spin_trylock_irqsave(struct kd_spinlock *l, unsigned long *flags);
void kd_spin_unlock(struct kd_spinlock *l);
void kd_spin_unlock_irq(struct kd_spinlock *l);
void kd_spin_unlock_irqrestore(struct kd_spinlock *l, unsigned long flags);
void kd_spin_unlock_bh(struct kd_spinlock *l);

static inline void kd_spin_lock_init(struct kd_spinlock *l)
{
	atomic_set(&l->q.val, 0);
}

static inline int kd_spin_is_locked(struct kd_spinlock *l)
{
	return READ_ONCE(l->q.locked) != 0;
}

static inline int kd_spin_is_contended(struct kd_spinlock *l)
{
	/* A queue or a pending waiter, as for the native queued spinlock. */
	return (atomic_read(&l->q.val) & ~KD_Q_LOCKED_MASK) != 0;
}

/*
 * arch_spin_*() level, for the few callers that manage preemption
 * themselves. Never delegated; the preempt count is not touched.
 */
void kd_arch_spin_lock(struct kd_spinlock *l);

static inline int kd_arch_spin_trylock(struct kd_spinlock *l)
{
	int old = 0;

	return atomic_try_cmpxchg_acquire(&l->q.val, &old, KD_Q_LOCKED);
}

static inline void kd_arch_spin_unlock(struct kd_spinlock *l)
{
	smp_store_release(&l->q.locked, 0);
}

/* ---- rwlock ----------------------------------------------------------- */

/* Delegable writers. */
void kd_write_lock(struct kd_rwlock *rw);
void kd_write_lock_irq(struct kd_rwlock *rw);
unsigned long kd_write_lock_irqsave(struct kd_rwlock *rw);
void kd_write_lock_bh(struct kd_rwlock *rw);

int kd_write_trylock(struct kd_rwlock *rw);
int kd_write_trylock_irqsave(struct kd_rwlock *rw, unsigned long *flags);
void kd_write_unlock(struct kd_rwlock *rw);
void kd_write_unlock_irq(struct kd_rwlock *rw);
void kd_write_unlock_irqrestore(struct kd_rwlock *rw, unsigned long flags);
void kd_write_unlock_bh(struct kd_rwlock *rw);

/* Readers always execute on their own task. */
void kd_read_lock(struct kd_rwlock *rw);
void kd_read_lock_irq(struct kd_rwlock *rw);
unsigned long kd_read_lock_irqsave(struct kd_rwlock *rw);
void kd_read_lock_bh(struct kd_rwlock *rw);
int kd_read_trylock(struct kd_rwlock *rw);
void kd_read_unlock(struct kd_rwlock *rw);
void kd_read_unlock_irq(struct kd_rwlock *rw);
void kd_read_unlock_irqrestore(struct kd_rwlock *rw, unsigned long flags);
void kd_read_unlock_bh(struct kd_rwlock *rw);

static inline void kd_rwlock_init(struct kd_rwlock *rw)
{
	atomic_set(&rw->cnts, 0);
	atomic_set(&rw->wait.val, 0);
}

/* Somebody is in the slow path, as arch_rwlock_is_contended(). */
static inline int kd_rwlock_is_contended(struct kd_rwlock *rw)
{
	return atomic_read(&rw->wait.val) != 0;
}

/* arch_read/write_*() level: the caller manages preemption. */
void kd_arch_read_lock(struct kd_rwlock *rw);
void kd_arch_write_lock(struct kd_rwlock *rw);

static inline int kd_arch_read_trylock(struct kd_rwlock *rw)
{
	int c = atomic_read(&rw->cnts);

	if (likely(!(c & KD_RW_WMASK))) {
		c = atomic_add_return_acquire(KD_RW_RBIAS, &rw->cnts);
		if (likely(!(c & KD_RW_WMASK)))
			return 1;
		atomic_sub(KD_RW_RBIAS, &rw->cnts);
	}
	return 0;
}

static inline int kd_arch_write_trylock(struct kd_rwlock *rw)
{
	int c = 0;

	return atomic_try_cmpxchg_acquire(&rw->cnts, &c, KD_RW_WLOCKED);
}

static inline void kd_arch_read_unlock(struct kd_rwlock *rw)
{
	(void)atomic_sub_return_release(KD_RW_RBIAS, &rw->cnts);
}

static inline void kd_arch_write_unlock(struct kd_rwlock *rw)
{
	smp_store_release(&rw->wlocked, 0);
}

/* ---- mutex ------------------------------------------------------------ */

/*
 * Delegable. A delegated acquisition returns 0; signals are observed only
 * once the caller parks.
 */
void kd_mutex_lock(struct kd_mutex *m);
int kd_mutex_lock_interruptible(struct kd_mutex *m);
int kd_mutex_lock_killable(struct kd_mutex *m);
void kd_mutex_lock_io(struct kd_mutex *m);

int kd_mutex_trylock(struct kd_mutex *m);
void kd_mutex_unlock(struct kd_mutex *m);
unsigned long kd_mutex_get_owner(struct kd_mutex *m);

static inline void kd_mutex_init(struct kd_mutex *m)
{
	atomic_set(&m->q.val, 0);
	atomic_set(&m->wait_lock.val, 0);
	m->owner = NULL;
	INIT_LIST_HEAD(&m->waiters);
}

static inline bool kd_mutex_is_locked(struct kd_mutex *m)
{
	return READ_ONCE(m->q.locked) != 0;
}

/* ---- ww_mutex --------------------------------------------------------- */

/*
 * Wound/wait mutexes, with the kernel's own acquire context and class
 * (linux/ww_mutex.h). Never delegated. Every class is handled with the
 * wait-die rule: a younger context that already holds a lock backs off
 * (-EDEADLK) instead of waiting for an older one. Callers handle that
 * result the same way for both native algorithms.
 */
void kd_ww_mutex_init(struct kd_ww_mutex *lock, struct ww_class *ww_class);
int kd_ww_mutex_lock(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
int kd_ww_mutex_lock_interruptible(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
void kd_ww_mutex_lock_slow(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
int kd_ww_mutex_lock_slow_interruptible(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
int kd_ww_mutex_trylock(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
void kd_ww_mutex_unlock(struct kd_ww_mutex *lock);

static inline bool kd_ww_mutex_is_locked(struct kd_ww_mutex *lock)
{
	return kd_mutex_is_locked(&lock->base);
}

/* ---- rwsem ------------------------------------------------------------ */

/* Delegable writers. */
void kd_down_write(struct kd_rwsem *sem);
int kd_down_write_killable(struct kd_rwsem *sem);

int kd_down_write_trylock(struct kd_rwsem *sem);
void kd_up_write(struct kd_rwsem *sem);
void kd_downgrade_write(struct kd_rwsem *sem);

void kd_down_read(struct kd_rwsem *sem);
int kd_down_read_interruptible(struct kd_rwsem *sem);
int kd_down_read_killable(struct kd_rwsem *sem);
int kd_down_read_trylock(struct kd_rwsem *sem);
void kd_up_read(struct kd_rwsem *sem);

static inline void kd_rwsem_init(struct kd_rwsem *sem)
{
	atomic_long_set(&sem->count, 0);
	kd_mutex_init(&sem->m);
}

static inline int kd_rwsem_is_locked(struct kd_rwsem *sem)
{
	return (atomic_long_read(&sem->count) & ~(KD_RWSEM_WWAIT | KD_RWSEM_NEEDWAKE)) != 0;
}

/* Held for writing (rwsem_assert_held_write()). */
static inline int kd_rwsem_is_write_locked(struct kd_rwsem *sem)
{
	return (atomic_long_read(&sem->count) & KD_RWSEM_WLOCKED) != 0;
}

/* Somebody waits in the slow path, as rwsem_is_contended(). */
static inline int kd_rwsem_is_contended(struct kd_rwsem *sem)
{
	return atomic_read(&sem->m.q.val) != 0 || !list_empty(&sem->m.waiters);
}

#endif /* _KDLOCK_KD_API_H */
