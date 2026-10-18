// SPDX-License-Identifier: GPL-2.0
/* Sleeping reader admission using the selected KD-only physical mutex. */
#include <linux/module.h>
#include "kd_rwsem.h"
#include "kd_lock.h"

void kd_rwsem_init(struct kd_rwsem *sem)
{
	kd_mutex_init(&sem->gate);
	atomic_long_set(&sem->readers, 0);
	init_waitqueue_head(&sem->drain);
}
EXPORT_SYMBOL_GPL(kd_rwsem_init);

void kd_up_read(struct kd_rwsem *sem)
{
	/* Full ordering pairs with the writer's enqueue/condition check, including
	 * this lockless waitqueue_active test: the final reader cannot lose wakeup.
	 */
	if (atomic_long_dec_and_test(&sem->readers) &&
	    waitqueue_active(&sem->drain))
		wake_up_all(&sem->drain);
}
EXPORT_SYMBOL_GPL(kd_up_read);

int kd_down_read_trylock(struct kd_rwsem *sem)
{
	if (atomic_long_read(&sem->gate.owner))
		return 0;
	/* Publish before rechecking the whole owner word, including waiter flags.
	 * This full barrier and the writer's barrier prohibit both sides missing
	 * each other. Failed speculation touches no protected payload.
	 */
	atomic_long_inc_return(&sem->readers);
	if (!atomic_long_read_acquire(&sem->gate.owner))
		return 1;
	kd_up_read(sem);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_read_trylock);

static void kd_rwsem_admit_reader(struct kd_rwsem *sem)
{
	atomic_long_inc(&sem->readers);
	kd_mutex_local_unlock(&sem->gate);
}

void kd_down_read(struct kd_rwsem *sem)
{
	might_sleep();
	if (kd_down_read_trylock(sem))
		return;
	kd_mutex_local_lock(&sem->gate);
	kd_rwsem_admit_reader(sem);
}
EXPORT_SYMBOL_GPL(kd_down_read);

int kd_down_read_interruptible(struct kd_rwsem *sem)
{
	int ret;

	might_sleep();
	if (kd_down_read_trylock(sem))
		return 0;
	ret = kd_mutex_lock_interruptible(&sem->gate);
	if (!ret)
		kd_rwsem_admit_reader(sem);
	return ret;
}
EXPORT_SYMBOL_GPL(kd_down_read_interruptible);

int kd_down_read_killable(struct kd_rwsem *sem)
{
	int ret;

	might_sleep();
	if (kd_down_read_trylock(sem))
		return 0;
	ret = kd_mutex_lock_killable(&sem->gate);
	if (!ret)
		kd_rwsem_admit_reader(sem);
	return ret;
}
EXPORT_SYMBOL_GPL(kd_down_read_killable);

void kd_down_write(struct kd_rwsem *sem)
{
	kd_mutex_local_lock(&sem->gate);
	smp_mb();
	wait_event(sem->drain, !atomic_long_read_acquire(&sem->readers));
}
EXPORT_SYMBOL_GPL(kd_down_write);

int kd_down_write_interruptible(struct kd_rwsem *sem)
{
	int ret = kd_mutex_lock_interruptible(&sem->gate);

	if (ret)
		return ret;
	smp_mb();
	ret = wait_event_interruptible(sem->drain,
				       !atomic_long_read_acquire(&sem->readers));
	if (ret) {
		/* No write acquisition was granted. Remove the gate ownership before
		 * reporting cancellation so later readers/writers can make progress.
		 */
		kd_mutex_local_unlock(&sem->gate);
		return -EINTR;
	}
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_write_interruptible);

int kd_down_write_killable(struct kd_rwsem *sem)
{
	int ret = kd_mutex_lock_killable(&sem->gate);

	if (ret)
		return ret;
	smp_mb();
	ret = wait_event_killable(sem->drain,
				 !atomic_long_read_acquire(&sem->readers));
	if (ret) {
		kd_mutex_local_unlock(&sem->gate);
		return -EINTR;
	}
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_write_killable);

int kd_down_write_trylock(struct kd_rwsem *sem)
{
	if (!kd_mutex_trylock(&sem->gate))
		return 0;
	smp_mb();
	if (!atomic_long_read_acquire(&sem->readers))
		return 1;
	kd_mutex_local_unlock(&sem->gate);
	return 0;
}
EXPORT_SYMBOL_GPL(kd_down_write_trylock);

void kd_up_write(struct kd_rwsem *sem)
{
	kd_mutex_local_unlock(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_up_write);

void kd_downgrade_write(struct kd_rwsem *sem)
{
	BUG_ON(!kd_origin_mutex_owned(&sem->gate, current));
	/* Count this reader before making the gate available. A successor writer
	 * must observe the count and wait; no writer can enter during conversion.
	 */
	atomic_long_inc(&sem->readers);
	kd_mutex_local_unlock(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_downgrade_write);

bool kd_rwsem_is_idle(struct kd_rwsem *sem)
{
	return !atomic_long_read(&sem->readers) &&
		!waitqueue_active(&sem->drain) && kd_mutex_is_idle(&sem->gate);
}
EXPORT_SYMBOL_GPL(kd_rwsem_is_idle);
