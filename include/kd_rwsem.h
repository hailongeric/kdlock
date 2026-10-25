/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_H
#define KD_RWSEM_H

#include "kd_rwsem_types.h"
#include "kd_mutex.h"

/* Task-context sleeping reader/writer object. Admission is separate from the
 * unchanged KD mutex protocol: 0 admits readers, -1 reserves an ordinary writer,
 * and positive values count exact delegation-capable writer reservations.
 * Every participant must use this API; never access the embedded gate directly.
 */
void kd_rwsem_init(struct kd_rwsem *sem);
void kd_down_read(struct kd_rwsem *sem);
int kd_down_read_interruptible(struct kd_rwsem *sem);
int kd_down_read_killable(struct kd_rwsem *sem);
/* Nonblocking, allocation-free read try/unlock preserve IRQ/preemption state,
 * including IRQ-disabled/atomic callers. Sleeping acquisition remains task-only.
 * Atomic final release is observed by the writer's timed drain recheck. */
int kd_down_read_trylock(struct kd_rwsem *sem);
void kd_up_read(struct kd_rwsem *sem);
void kd_down_write(struct kd_rwsem *sem);
int kd_down_write_interruptible(struct kd_rwsem *sem);
int kd_down_write_killable(struct kd_rwsem *sem);
int kd_down_write_trylock(struct kd_rwsem *sem);
void kd_up_write(struct kd_rwsem *sem);
void kd_downgrade_write(struct kd_rwsem *sem);
/* Outer clobber wrappers only: reserve before publication and release on the
 * origin after the matching mutex unlock/ACK. Not nested JIT lock controls. */
void kd_rwsem_delegate_enter(struct kd_rwsem *sem);
void kd_rwsem_delegate_exit(struct kd_rwsem *sem);
/* Quiescent inspection after stopping/joining every user, not admission. */
bool kd_rwsem_is_idle(struct kd_rwsem *sem);

#endif /* KD_RWSEM_H */
