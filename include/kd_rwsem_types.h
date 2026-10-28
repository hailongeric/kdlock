/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_TYPES_H
#define KD_RWSEM_TYPES_H

#include <linux/wait.h>
#include "kd_mutex_types.h"

/* Admission: 0 admits local readers, -1 reserves a local writer, positive
 * values retain exact delegated-writer reservations through their origin ACK.
 * Participants must never acquire the embedded gate independently. */
struct kd_rwsem {
	struct kd_mutex gate;
	atomic_long_t readers __aligned(64);
	atomic_long_t admission __aligned(64);
	wait_queue_head_t phase_wait __aligned(64);
	wait_queue_head_t reader_drain __aligned(64);
	/* Two NUMA-hashed optimistic admission queues, never reader payloads.
	 * Keep the original queue and all preceding fields at their offsets;
	 * place the other tail on a separate line. Colliding node IDs safely
	 * share a queue, so this bounded storage needs no per-node allocation. */
	struct optimistic_spin_queue reader_osq;
	struct optimistic_spin_queue reader_osq_alt __aligned(64);
};

#define KD_RWSEM_INITIALIZER(name) { \
	.gate = KD_MUTEX_INITIALIZER(name.gate), \
	.readers = ATOMIC_LONG_INIT(0), \
	.admission = ATOMIC_LONG_INIT(0), \
	.phase_wait = __WAIT_QUEUE_HEAD_INITIALIZER(name.phase_wait), \
	.reader_drain = __WAIT_QUEUE_HEAD_INITIALIZER(name.reader_drain), \
	.reader_osq = OSQ_LOCK_UNLOCKED, \
	.reader_osq_alt = OSQ_LOCK_UNLOCKED, \
}
#define DEFINE_KD_RWSEM(name) \
	struct kd_rwsem name = KD_RWSEM_INITIALIZER(name)

#endif
