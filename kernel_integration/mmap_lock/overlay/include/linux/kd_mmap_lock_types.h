/* SPDX-License-Identifier: GPL-2.0 */
#ifndef LINUX_KD_MMAP_LOCK_TYPES_H
#define LINUX_KD_MMAP_LOCK_TYPES_H

#include <linux/rwsem.h>
#include <linux/kd_mmap_rwsem_types.h>

/* Chosen once, before an mm is published. Neither contention nor a partial
 * critical section can change the backend. Both boot modes have this layout.
 * init_mm stays Native; dynamically initialized mms use the boot selection. */
struct kd_mmap_lock {
	union {
		struct rw_semaphore native;
		struct kd_mmap_rwsem kd;
	};
	bool use_kd;
};

#define KD_MMAP_LOCK_INITIALIZER(name) { \
	.native = __RWSEM_INITIALIZER(name.native), .use_kd = false, \
}

#endif
