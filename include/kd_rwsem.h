/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_H
#define KD_RWSEM_H

#include "kd_rwsem_types.h"
#include "kd_mutex.h"

/* Task-context sleeping reader/writer object. Admission is separate from the
 * KD physical gate: 0 admits readers and -1 names one exact selected writer.
 * Queued requests retain no reusable reader-drain result or phase reservation.
 * Every participant must use this API; never access the embedded gate directly.
 */
void kd_rwsem_init(struct kd_rwsem *sem);
void __kd_init_rwsem(struct kd_rwsem *sem, const char *name, struct lock_class_key *key);
#define kd_init_rwsem(sem) kd_rwsem_init(sem)
/* Callable symbols acquire locally. Include kd_rwsem_api.h for the same public
 * names with an optional, explicitly prepared ordinary writer continuation. */
void kd_down_read(struct kd_rwsem *sem);
int kd_down_read_interruptible(struct kd_rwsem *sem);
int kd_down_read_killable(struct kd_rwsem *sem);
/* Nonblocking, allocation-free read try/unlock preserve IRQ/preemption state,
 * including IRQ-disabled/atomic callers. Sleeping acquisition remains task-only.
 * Atomic final release is observed by the writer's timed drain recheck. */
int kd_down_read_trylock(struct kd_rwsem *sem);
void kd_up_read(struct kd_rwsem *sem);
void kd_down_write(struct kd_rwsem *sem);
/* KD extension: the target Linux rwsem has killable, not interruptible, writes. */
int kd_down_write_interruptible(struct kd_rwsem *sem);
int kd_down_write_killable(struct kd_rwsem *sem);
int kd_down_write_trylock(struct kd_rwsem *sem);
void kd_up_write(struct kd_rwsem *sem);
void kd_downgrade_write(struct kd_rwsem *sem);
void kd_down_read_non_owner(struct kd_rwsem *sem);
void kd_up_read_non_owner(struct kd_rwsem *sem);
int kd_rwsem_is_locked(struct kd_rwsem *sem);
int kd_rwsem_is_contended(struct kd_rwsem *sem);
void kd_rwsem_assert_held(const struct kd_rwsem *sem);
void kd_rwsem_assert_held_write(const struct kd_rwsem *sem);
/* Quiescent inspection after stopping/joining every user, not admission. */
bool kd_rwsem_is_idle(struct kd_rwsem *sem);

#endif /* KD_RWSEM_H */
