/* SPDX-License-Identifier: GPL-2.0 */
/*
 * kdlock public lock API.
 *
 * Every lock operation is an out-of-line call. That is a protocol
 * requirement, not a style choice: generated code recognises lock
 * operations by their call target, so an inlined release would let a
 * delegated critical section run past its end.
 *
 * "Delegable" entries are assembly stubs (kd_entry.S). A contended caller
 * records its continuation, and the lock holder may run the caller's
 * critical section from generated code. All other entries execute on the
 * calling task.
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
	/* A queue or a pending waiter (KD_QF_PENDING), as for qspinlock. */
	return READ_ONCE(l->q.tail) != 0 || READ_ONCE(l->q.flags) != 0;
}

/* ---- rwlock ----------------------------------------------------------- */

/* Delegable writers. */
void kd_write_lock(struct kd_rwlock *rw);
void kd_write_lock_irq(struct kd_rwlock *rw);
unsigned long kd_write_lock_irqsave(struct kd_rwlock *rw);
void kd_write_lock_bh(struct kd_rwlock *rw);

int kd_write_trylock(struct kd_rwlock *rw);
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

/* ---- mutex ------------------------------------------------------------ */

/* Delegable. */
void kd_mutex_lock(struct kd_mutex *m);
int kd_mutex_lock_interruptible(struct kd_mutex *m);
int kd_mutex_lock_killable(struct kd_mutex *m);

int kd_mutex_trylock(struct kd_mutex *m);
void kd_mutex_unlock(struct kd_mutex *m);

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

#endif /* _KDLOCK_KD_API_H */
