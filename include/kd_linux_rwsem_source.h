/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_LINUX_RWSEM_SOURCE_H
#define KDLOCK_LINUX_RWSEM_SOURCE_H

#include "kd_linux_rwsem.h"
#include "kd_mutex_api.h"

/* No private layout dependency in Linux's public rwsem header. */
void kd_rwsem_down_read_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);
void kd_rwsem_up_read_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);
void kd_rwsem_down_write_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);
void kd_rwsem_up_write_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);
void kd_rwsem_downgrade_write_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);

/* Callable symbols, including constructors expanded earlier in rwsem.h, route
 * selected objects on the same KD gate. Only these ordinary source forms use
 * the existing clobber-entry contract. Evaluate the original object once.
 */
#define KD_LINUX_RWSEM_SOURCE(object, eligible, symbol, native_symbol) \
	({ \
		struct rw_semaphore *kd_linux_object = (object); \
		struct kd_linux_rwsem_binding *kd_linux_binding = \
			READ_ONCE(kd_linux_object->kd_binding); \
		if (kd_linux_binding && (eligible)) \
			KD_SOURCE_CALL(kd_linux_binding->lock, struct kd_rwsem, symbol); \
		else \
			(native_symbol)(kd_linux_object); \
		(void)0; \
	})

#define down_read(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_source_ready(kd_linux_binding), \
		kd_rwsem_down_read_entry_asm, down_read)
#define down_write(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_source_ready(kd_linux_binding), \
		kd_rwsem_down_write_entry_asm, down_write)
#define up_read(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_source_release(kd_linux_binding, true), \
		kd_rwsem_up_read_entry_asm, up_read)
#define up_write(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_source_release(kd_linux_binding, false), \
		kd_rwsem_up_write_entry_asm, up_write)
#define downgrade_write(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_source_release(kd_linux_binding, false), \
		kd_rwsem_downgrade_write_entry_asm, downgrade_write)
#endif
