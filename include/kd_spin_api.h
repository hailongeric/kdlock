/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_SPIN_API_H
#define KDLOCK_SPIN_API_H

#ifndef __ASSEMBLY__
#include "../kernel/mutex.h"
#include "kd_mutex_api.h"

/* Distinct source object with the common MCS queue as its first member. */
struct kd_spinlock {
	struct kd_mutex queue;
};

#define KD_SPINLOCK_INITIALIZER { .queue = KD_MUTEX_INITIALIZER }

void kd_spin_init(struct kd_spinlock *lock);
void kd_spin_lock_entry_asm(struct kd_spinlock *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_spin_unlock_entry_asm(struct kd_spinlock *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);

/* Plain spin pair in an attached spin runtime. Source runs in task context
 * with IRQs enabled and preemption disabled from acquisition through unlock.
 * The caller provisions all request/control storage before the first call.
 */
#define kd_spin_lock(object) \
	KD_SOURCE_CALL((object), struct kd_spinlock, kd_spin_lock_entry_asm)
#define kd_spin_unlock(object) \
	KD_SOURCE_CALL((object), struct kd_spinlock, kd_spin_unlock_entry_asm)
#endif
#endif
