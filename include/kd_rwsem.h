/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_H
#define KD_RWSEM_H

#include <linux/wait.h>
#include "kd_mutex.h"

/* Task-context sleeping reader/writer object. The selected KD physical mutex
 * gates admission; it never publishes a delegated request. Readers retain only
 * their count and writers retain the gate until release or downgrade. Every
 * participant must use this API, and callers must not access the embedded gate.
 */
struct kd_rwsem {
	struct kd_mutex gate;
	atomic_long_t readers __aligned(64);
	wait_queue_head_t drain;
};

#define KD_RWSEM_INITIALIZER(name) { \
	.gate = KD_MUTEX_INITIALIZER(name.gate), \
	.readers = ATOMIC_LONG_INIT(0), \
	.drain = __WAIT_QUEUE_HEAD_INITIALIZER(name.drain), \
}
#define DEFINE_KD_RWSEM(name) \
	struct kd_rwsem name = KD_RWSEM_INITIALIZER(name)

void kd_rwsem_init(struct kd_rwsem *sem);
void kd_down_read(struct kd_rwsem *sem);
int kd_down_read_interruptible(struct kd_rwsem *sem);
int kd_down_read_killable(struct kd_rwsem *sem);
int kd_down_read_trylock(struct kd_rwsem *sem);
void kd_up_read(struct kd_rwsem *sem);
void kd_down_write(struct kd_rwsem *sem);
int kd_down_write_interruptible(struct kd_rwsem *sem);
int kd_down_write_killable(struct kd_rwsem *sem);
int kd_down_write_trylock(struct kd_rwsem *sem);
void kd_up_write(struct kd_rwsem *sem);
void kd_downgrade_write(struct kd_rwsem *sem);
/* Quiescent inspection after stopping/joining every user, not admission. */
bool kd_rwsem_is_idle(struct kd_rwsem *sem);

#endif /* KD_RWSEM_H */
