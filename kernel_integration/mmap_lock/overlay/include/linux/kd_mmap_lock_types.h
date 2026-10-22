/* SPDX-License-Identifier: GPL-2.0 */
#ifndef LINUX_KD_MMAP_LOCK_TYPES_H
#define LINUX_KD_MMAP_LOCK_TYPES_H

#include <linux/rwsem.h>
#include <linux/kd_mmap_rwsem_types.h>

/* Fault callers retain their own mmap read share. This independent KD service
 * gate serializes only opted-in write-fault installation requests; acquiring
 * the mmap writer gate here would wait for those callers and deadlock. */
struct kd_mmap_fault_state {
	struct kd_mmap_mutex gate;
	unsigned long start, end;
	bool enabled, native_only;
	atomic64_t calls, supported, delegated, native, post_ban;
	atomic64_t handbacks, acks, cancelled, refused;
};

/* Chosen once, before an mm is published. Neither contention nor a partial
 * critical section can change the backend. Both boot modes have this layout.
 * init_mm stays Native; dynamically initialized mms use the boot selection. */
struct kd_mmap_lock {
	union {
		struct rw_semaphore native;
		struct kd_mmap_rwsem kd;
	};
	bool use_kd;
	/* Opt-in typed in-tree body. No arbitrary callback or generated image is
	 * admitted. Refusal is sticky for this mm until its final destruction. */
	bool body_enabled, body_native_only;
	u64 body_calls, body_supported, body_delegated, body_handbacks;
	u64 body_native, body_post_ban, body_cancelled, body_acks;
	struct kd_mmap_fault_state fault;
};

#define KD_MMAP_LOCK_INITIALIZER(name) { \
	.native = __RWSEM_INITIALIZER(name.native), .use_kd = false, \
}

#endif
