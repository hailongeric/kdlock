/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_RWSEM_API_H
#define KDLOCK_RWSEM_API_H

#ifndef __ASSEMBLY__
#include "../kernel/rw.h"
#include "kd_mutex_api.h"

void kd_rwsem_down_read_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_rwsem_up_read_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_rwsem_down_write_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_rwsem_up_write_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);
void kd_rwsem_downgrade_write_entry_asm(struct kd_rwsem *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);

/* Ordinary sleepable source APIs on an attached, provisioned task root. Each
 * reached operation ends its fragment before the operation. Exact target lookup
 * selects reader, writer or downgrade handling through the shared source-call
 * bridge. Simultaneous and repeated reader grants retain distinct credits.
 * A selected proxy downgrade retains its writer acquisition through the matching
 * logical up_read; a local downgrade establishes a real shared read credit.
 * Signalable, trylock, IRQ and RT variants require their own contracts.
 */
#define kd_rwsem_down_read(object) \
	KD_SOURCE_CALL((object), struct kd_rwsem, kd_rwsem_down_read_entry_asm)
#define kd_rwsem_up_read(object) \
	KD_SOURCE_CALL((object), struct kd_rwsem, kd_rwsem_up_read_entry_asm)
#define kd_rwsem_down_write(object) \
	KD_SOURCE_CALL((object), struct kd_rwsem, kd_rwsem_down_write_entry_asm)
#define kd_rwsem_up_write(object) \
	KD_SOURCE_CALL((object), struct kd_rwsem, kd_rwsem_up_write_entry_asm)
#define kd_rwsem_downgrade_write(object) \
	KD_SOURCE_CALL((object), struct kd_rwsem, kd_rwsem_downgrade_write_entry_asm)
#endif
#endif
