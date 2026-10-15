// SPDX-License-Identifier: GPL-2.0
/* Sleeping reader admission around the owned-mutex writer queue. */
#include <linux/module.h>
#include "kd_rwsem.h"
#include "kd_owned_mutex_internal.h"

void kd_rwsem_init(struct kd_rwsem *sem)
{
	kd_mutex_init(&sem->gate);
	atomic_long_set(&sem->readers, 0);
	init_waitqueue_head(&sem->drain);
}
EXPORT_SYMBOL_GPL(kd_rwsem_init);

void kd_up_read(struct kd_rwsem *sem)
{
	/* The fully ordered decrement pairs with the writer's enqueue/condition
	 * check, including the lockless waitqueue_active test. */
	if (atomic_long_dec_and_test(&sem->readers) &&
	    waitqueue_active(&sem->drain))
		wake_up_all(&sem->drain);
}
EXPORT_SYMBOL_GPL(kd_up_read);

int kd_down_read_trylock(struct kd_rwsem *sem)
{
	if (atomic_long_read(&sem->gate.owner))
		return 0;
	/* Publish before rechecking the entire owner word, including waiter
	 * flags. Together with the writer barrier this forbids both sides from
	 * missing the other's acquisition. A failed speculation accesses no
	 * protected payload, even if it briefly overlaps an executing writer. */
	atomic_long_inc_return(&sem->readers);
	if (!atomic_long_read_acquire(&sem->gate.owner))
		return 1;
	kd_up_read(sem);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_trylock);

void kd_down_read(struct kd_rwsem *sem)
{
	might_sleep();
	if (kd_down_read_trylock(sem))
		return;
	/* SELF readers are queue boundaries: never delegate their acquisition
	 * or combine from their unlock while an admitted reader is live. */
	kd_mutex_lock(&sem->gate);
	atomic_long_inc(&sem->readers);
	kd_mutex_unlock(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_down_read);

void kd_rwsem_wait_readers(struct kd_rwsem *sem)
{
	might_sleep();
	BUG_ON(!kd_owned_mutex_owned(&sem->gate, current));
	smp_mb();
	wait_event(sem->drain, !atomic_long_read(&sem->readers));
}
EXPORT_SYMBOL_GPL(kd_rwsem_wait_readers);

void kd_down_write(struct kd_rwsem *sem)
{
	kd_mutex_lock(&sem->gate);
	kd_rwsem_wait_readers(sem);
}
EXPORT_SYMBOL_GPL(kd_down_write);

void kd_up_write(struct kd_rwsem *sem)
{
	kd_mutex_unlock(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_up_write);

int kd_down_write_trylock(struct kd_rwsem *sem)
{
	if (!kd_mutex_trylock(&sem->gate))
		return 0;
	smp_mb();
	if (!atomic_long_read(&sem->readers))
		return 1;
	kd_mutex_unlock(&sem->gate);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_write_trylock);

void kd_downgrade_write(struct kd_rwsem *sem)
{
	BUG_ON(!kd_owned_mutex_owned(&sem->gate, current));
	/* Become a reader before publishing the gate as available. A successor
	 * writer must observe this count and sleep; no writer can intervene. */
	atomic_long_inc(&sem->readers);
	kd_mutex_unlock(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_downgrade_write);

bool kd_rwsem_is_idle(struct kd_rwsem *sem)
{
	/* Quiescent inspection only: callers must first stop and join users. */
	return !atomic_long_read(&sem->readers) &&
		!waitqueue_active(&sem->drain) && kd_owned_mutex_is_idle(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_rwsem_is_idle);
