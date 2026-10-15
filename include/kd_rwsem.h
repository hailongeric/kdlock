/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_H
#define KD_RWSEM_H

#include <linux/wait.h>
#include <linux/errno.h>
#include "kd_owned_mutex_direct.h"

/* Sleeping reader/writer companion to kd_rwlock. The owned mutex is an
 * admission gate, not a Linux rwsem: every consumer must use this API.
 * Readers run locally. Only explicit outer writers may delegate.
 */
struct kd_rwsem {
	struct kd_mutex gate;
	atomic_long_t readers __aligned(64);
	wait_queue_head_t drain;
};

#define __KD_RWSEM_INITIALIZER(name) { \
	.gate = __KD_MUTEX_INITIALIZER(name.gate), \
	.readers = ATOMIC_LONG_INIT(0), \
	.drain = __WAIT_QUEUE_HEAD_INITIALIZER(name.drain), \
}
#define DEFINE_KD_RWSEM(name) \
	struct kd_rwsem name = __KD_RWSEM_INITIALIZER(name)

void kd_rwsem_init(struct kd_rwsem *sem);
void kd_down_read(struct kd_rwsem *sem);
void kd_up_read(struct kd_rwsem *sem);
int kd_down_read_trylock(struct kd_rwsem *sem);
void kd_down_write(struct kd_rwsem *sem);
void kd_up_write(struct kd_rwsem *sem);
int kd_down_write_trylock(struct kd_rwsem *sem);
/* Downgrade is paired with ordinary down_write/trylock, then up_read.
 * Delegating outer writers must use their matching outer unlock instead. */
void kd_downgrade_write(struct kd_rwsem *sem);
bool kd_rwsem_is_idle(struct kd_rwsem *sem);

/* Native physical writer only. Entry to a batch is possible only from a
 * writer that has already drained readers while retaining this same gate. */
void kd_rwsem_wait_readers(struct kd_rwsem *sem);

static inline int kd_rwsem_prepare(struct kd_rwsem *sem, unsigned long ip,
				  unsigned int abi)
{
	return sem ? kd_owned_mutex_prepare(&sem->gate, ip, abi) : -EINVAL;
}

/* Synthetic entry has owner=0 and inherits the physical writer's reader
 * exclusion. Slow readers acquire the gate through ordinary SELF and release
 * without combining. Thus no admitted reader can appear inside a batch.
 * Keep the native wait outside the delegated path: it may schedule.
 */
#define KD_RWSEM_OUTER_WRITE_LOCK(sem, cookie, continuation) do { \
	struct kd_rwsem *kd_rwsem_acquire = (sem); \
	KD_OWNED_MUTEX_OUTER_LOCK(&kd_rwsem_acquire->gate, cookie, continuation); \
	if (READ_ONCE((cookie).owner)) \
		kd_rwsem_wait_readers(kd_rwsem_acquire); \
} while (0)

#define KD_RWSEM_OUTER_WRITE_UNLOCK(sem, cookie) \
	KD_OWNED_MUTEX_OUTER_UNLOCK(&(sem)->gate, cookie)

#endif /* KD_RWSEM_H */
