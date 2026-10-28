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
	/* Quiescent, monotonic preparation policy; not acquisition authority.
	 * Fits the gate cacheline's existing padding, away from reader updates. */
	unsigned int prepared_writes;
	atomic_long_t readers __aligned(64);
	atomic_long_t admission __aligned(64);
	wait_queue_head_t phase_wait __aligned(64);
	wait_queue_head_t reader_drain __aligned(64);
	/* Serialize optimistic read admission, never the reader payload. Fits in
	 * the final cacheline without moving the existing counters/waitqueues. */
	struct optimistic_spin_queue reader_osq;
};

#define KD_RWSEM_INITIALIZER(name) { \
	.gate = KD_MUTEX_INITIALIZER(name.gate), \
	.prepared_writes = 0, \
	.readers = ATOMIC_LONG_INIT(0), \
	.admission = ATOMIC_LONG_INIT(0), \
	.phase_wait = __WAIT_QUEUE_HEAD_INITIALIZER(name.phase_wait), \
	.reader_drain = __WAIT_QUEUE_HEAD_INITIALIZER(name.reader_drain), \
	.reader_osq = OSQ_LOCK_UNLOCKED, \
}
#define DECLARE_KD_RWSEM(name) \
	struct kd_rwsem name = KD_RWSEM_INITIALIZER(name)
#define DEFINE_KD_RWSEM(name) \
	struct kd_rwsem name = KD_RWSEM_INITIALIZER(name)

#endif
