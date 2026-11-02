/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_H
#define KD_RWSEM_H

#include "kd_rwsem_types.h"
#include "kd_mutex.h"

/* Task-context sleeping reader/writer object. Admission is separate from the
 * unchanged KD mutex protocol: 0 admits readers and -1 closes one selected
 * writer phase. Queued requests carry no reusable reader-drain result.
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
/* Provider-only request/phase operations. The transport retains the record and
 * origin through completion, and unqueues only after its queue is retired.
 * Local selection passes NULL; it never owns an unselected reservation. */
void kd_rwsem_request_init(struct kd_rwsem_request *request,
			   struct kd_rwsem *sem, struct task_struct *origin,
			   void *identity, u64 sequence);
void kd_rwsem_request_unqueue(struct kd_rwsem_request *request);
/* The executor already owns the physical gate and is schedulable. On failure,
 * selected distinguishes interruption before selection from a drain rollback.
 * A selected rollback releases its gate/ACK before release_write. Signal state
 * applies to current, not to an independently published origin's cancellation. */
int kd_rwsem_select_write(struct kd_rwsem *sem,
			  struct kd_rwsem_request *request,
			  unsigned int state, bool *selected);
/* A request's logical writer endpoint may retain executor gate custody for a
 * next selection. Local release follows its actual physical unlock/ACK. */
void kd_rwsem_release_write(struct kd_rwsem *sem,
			    struct kd_rwsem_request *request);
/* begin publishes one read credit. The caller releases the physical gate/ACK
 * before finish reopens admission. Neither operation completes the request. */
void kd_rwsem_begin_downgrade(struct kd_rwsem *sem,
			      struct kd_rwsem_request *request);
void kd_rwsem_finish_downgrade(struct kd_rwsem *sem,
			       struct kd_rwsem_request *request);
/* Consume the exact read credit once; completion is published only after the
 * fully ordered decrement. No physical unlock or post-decrement object access. */
void kd_rwsem_finish_read(struct kd_rwsem_request *request);
/* Quiescent inspection after stopping/joining every user, not admission. */
bool kd_rwsem_is_idle(struct kd_rwsem *sem);

#endif /* KD_RWSEM_H */
