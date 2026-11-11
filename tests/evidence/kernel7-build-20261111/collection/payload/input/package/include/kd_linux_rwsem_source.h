/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_LINUX_RWSEM_SOURCE_H
#define KDLOCK_LINUX_RWSEM_SOURCE_H

#include "kd_linux_rwsem.h"
#include "kd_mutex_api.h"

/* No private layout dependency in Linux's public rwsem header. */
void kd_linux_rwsem_down_read_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);
void kd_linux_rwsem_up_read_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);
void kd_linux_rwsem_down_write_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);
/* Exact registration for the explicit cold killable-source opt-in. Legacy
 * bindings retain the callable native path and integer result ABI.
 */
int kd_linux_rwsem_down_write_killable_entry_asm(struct kd_rwsem *, unsigned long,
		unsigned long, unsigned long);
void kd_linux_rwsem_up_write_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);
void kd_linux_rwsem_downgrade_write_entry_asm(struct kd_rwsem *, unsigned long, unsigned long, unsigned long);

/* The immutable binding selects these ordinary void source forms. Native
 * eligibility and exact managed/native credit routing occur in the bootstrap
 * before source lending. Generated operations use their current node's S_W.
 * Callable, other signal/try and query APIs keep their native frontiers. The
 * separate killable writer opt-in below requires complete managed resources.
 * This header supplies no task/source enrollment.
 * Acquire the published binding before reading its immutable fields, evaluate
 * the original object once and pass the actual KD lock as DI.
 */
#define KD_LINUX_RWSEM_SOURCE(object, symbol, native_symbol) \
	({ \
		struct rw_semaphore *kd_linux_object = (object); \
		struct kd_linux_rwsem_binding *kd_linux_binding = \
			smp_load_acquire(&kd_linux_object->kd_binding); \
		if (kd_linux_binding && kd_linux_binding->source_calls) \
			KD_SOURCE_CALL(kd_linux_binding->lock, struct kd_rwsem, symbol); \
		else \
			(native_symbol)(kd_linux_object); \
		(void)0; \
	})

/* Killable capture has an independent immutable opt-in. Existing bindings and
 * unprepared callers retain the ordinary local integer ABI on the same gate.
 * A borrowed nested call is handed to W before operation preparation.
 */
#define KD_LINUX_RWSEM_SOURCE_INT(object, symbol, native_symbol) \
	({ \
		struct rw_semaphore *kd_linux_object = (object); \
		struct kd_linux_rwsem_binding *kd_linux_binding = \
			smp_load_acquire(&kd_linux_object->kd_binding); \
		int kd_linux_result; \
		if (kd_linux_binding && kd_linux_binding->killable_source_calls) \
			kd_linux_result = KD_SOURCE_CALL_INT(kd_linux_binding->lock, \
				struct kd_rwsem, symbol); \
		else \
			kd_linux_result = (native_symbol)(kd_linux_object); \
		kd_linux_result; \
	})

#define down_write_killable(sem) \
	KD_LINUX_RWSEM_SOURCE_INT((sem), \
		kd_linux_rwsem_down_write_killable_entry_asm, down_write_killable)

#define down_read(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_down_read_entry_asm, \
		down_read)
#define down_write(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_down_write_entry_asm, \
		down_write)
#define up_read(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_up_read_entry_asm, \
		up_read)
#define up_write(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_up_write_entry_asm, \
		up_write)
#define downgrade_write(sem) \
	KD_LINUX_RWSEM_SOURCE((sem), kd_linux_rwsem_downgrade_write_entry_asm, \
		downgrade_write)
#endif
