/* SPDX-License-Identifier: GPL-2.0 */
/*
 * The mm_struct mmap lock as a kdlock rwsem (CONFIG_KDLOCK_MM).
 *
 * Each mm chooses its backend once, before it is published, from the
 * kd_mm parameter: the native rw_semaphore or a struct kd_rwsem. The
 * choice never changes afterwards, so every user of one mm follows one
 * protocol. Static mms (init_mm, efi_mm, ...) are native.
 *
 * Choosing per mm makes the native control and kdlock run on the same
 * kernel and boot: a process created after the parameter changed gets the
 * other backend.
 */
#ifndef _KDLOCK_KD_MM_TYPES_H
#define _KDLOCK_KD_MM_TYPES_H

#include <linux/rwsem.h>
#include <kdlock/kd_types.h>

struct kd_mm_lock {
	union {
		struct rw_semaphore	native;
		struct kd_rwsem		kd;	/* first member: &lock->kd == lock */
	};
	bool			use_kd;
};

#define KD_MM_LOCK_INITIALIZER(name) {					\
	.native = __RWSEM_INITIALIZER((name).native),			\
	.use_kd = false,						\
}

#endif /* _KDLOCK_KD_MM_TYPES_H */
