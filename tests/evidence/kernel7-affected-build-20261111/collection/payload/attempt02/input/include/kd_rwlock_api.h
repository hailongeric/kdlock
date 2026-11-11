/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_RWLOCK_API_H
#define KDLOCK_RWLOCK_API_H

#ifndef __ASSEMBLY__
#include "../kernel/rw.h"
#include "kd_mutex_api.h"

void kd_rwlock_read_lock_entry_asm(struct kd_rwlock *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_rwlock_read_unlock_entry_asm(struct kd_rwlock *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_rwlock_write_lock_entry_asm(struct kd_rwlock *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_rwlock_write_unlock_entry_asm(struct kd_rwlock *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);

/* Plain source pairs in IRQ-enabled task context. The physical task maintains
 * its own preemption pins through open read/write grants and their exact unlock
 * acknowledgements. Reader credits remain concurrent and individually retained.
 * Caller-provisioned request/control and auxiliary backing precede admission.
 * IRQ/BH, trylock, mixed-family and RT variants have separate scope.
 */
#define kd_rwlock_read_lock(object) \
	KD_SOURCE_CALL((object), struct kd_rwlock, kd_rwlock_read_lock_entry_asm)
#define kd_rwlock_read_unlock(object) \
	KD_SOURCE_CALL((object), struct kd_rwlock, kd_rwlock_read_unlock_entry_asm)
#define kd_rwlock_write_lock(object) \
	KD_SOURCE_CALL((object), struct kd_rwlock, kd_rwlock_write_lock_entry_asm)
#define kd_rwlock_write_unlock(object) \
	KD_SOURCE_CALL((object), struct kd_rwlock, kd_rwlock_write_unlock_entry_asm)
#endif
#endif
