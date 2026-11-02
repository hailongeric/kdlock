/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_TYPES_H
#define KD_RWSEM_TYPES_H

#include "kd_mutex_types.h"
#include "kd_wait_queue.h"

/* Each condition has its own topology, but all topology/state operations use
 * gate.wait_lock. Keep the old wait-head footprint while admission migration
 * is in progress; request generations come from the shared queue namespace. */
struct kd_rwsem_condition {
	struct kd_wait_node *head;
	u64 reserved[2];
};

static inline bool
kd_rwsem_condition_active(const struct kd_rwsem_condition *condition)
{
	return READ_ONCE(condition->head) != NULL;
}

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
	struct kd_rwsem_condition phase_wait __aligned(64);
	struct kd_rwsem_condition reader_drain __aligned(64);
	/* Serialize optimistic read admission, never the reader payload. Fits in
	 * the final cacheline without moving the existing counters/waitqueues. */
	struct optimistic_spin_queue reader_osq;
};

#define KD_RWSEM_INITIALIZER(name) { \
	.gate = KD_MUTEX_INITIALIZER(name.gate), \
	.prepared_writes = 0, \
	.readers = ATOMIC_LONG_INIT(0), \
	.admission = ATOMIC_LONG_INIT(0), \
	.phase_wait = { .head = NULL, .reserved = { 0, 0 } }, \
	.reader_drain = { .head = NULL, .reserved = { 0, 0 } }, \
	.reader_osq = OSQ_LOCK_UNLOCKED, \
}
#define DECLARE_KD_RWSEM(name) \
	struct kd_rwsem name = KD_RWSEM_INITIALIZER(name)
#define DEFINE_KD_RWSEM(name) \
	struct kd_rwsem name = KD_RWSEM_INITIALIZER(name)

#endif
