/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_TYPES_H
#define KD_RWSEM_TYPES_H

#include <linux/wait.h>
#include "kd_mutex_types.h"

struct task_struct;
struct kd_rwsem;

enum kd_rwsem_request_state {
	KD_RWSEM_REQUEST_IDLE,
	KD_RWSEM_REQUEST_QUEUED,
	KD_RWSEM_REQUEST_WRITE,
	KD_RWSEM_REQUEST_READ,
	KD_RWSEM_REQUEST_CONSUMING,
	KD_RWSEM_REQUEST_RELEASED,
};

/* A preallocated request record follows its exact publication, not a temporary
 * capture-helper stack. A downgraded record outlives the selected writer slot.
 * The transport owns identity/sequence and keeps the origin and record live. */
struct kd_rwsem_request {
	struct kd_rwsem *sem;
	struct task_struct *origin;
	struct task_struct *executor;
	unsigned long generation;
	void *identity;
	u64 sequence;
	unsigned int state;
};

enum kd_rwsem_selected_kind {
	KD_RWSEM_SELECTED_NONE,
	KD_RWSEM_SELECTED_LOCAL,
	KD_RWSEM_SELECTED_REQUEST,
};

/* Admission: 0 admits local readers, -1 closes a selected writer phase. Queued
 * requests do not close admission or carry a pre-publication reader drain.
 * Participants must never acquire the embedded gate independently. */
struct kd_rwsem {
	struct kd_mutex gate;
	/* Quiescent, monotonic preparation policy; not acquisition authority.
	 * Fits the gate cacheline's existing padding, away from reader updates. */
	unsigned int prepared_writes;
	unsigned int selected_kind;
	struct task_struct *selected_executor;
	struct kd_rwsem_request *selected_request;
	unsigned long phase_generation;
	atomic_long_t readers __aligned(64);
	atomic_long_t admission __aligned(64);
	wait_queue_head_t phase_wait __aligned(64);
	wait_queue_head_t reader_drain __aligned(64);
	/* Serialize optimistic read admission, never the reader payload. Fits in
	 * the final cacheline without moving the existing counters/waitqueues. */
	struct optimistic_spin_queue reader_osq;
	/* Only unselected publications; ownership is in the exact selected/read
	 * record. Selection or queue retirement consumes one reservation. */
	atomic_long_t queued;
};

#define KD_RWSEM_INITIALIZER(name) { \
	.gate = KD_MUTEX_INITIALIZER(name.gate), \
	.prepared_writes = 0, \
	.selected_kind = KD_RWSEM_SELECTED_NONE, \
	.selected_executor = NULL, .selected_request = NULL, .phase_generation = 0, \
	.readers = ATOMIC_LONG_INIT(0), \
	.admission = ATOMIC_LONG_INIT(0), \
	.phase_wait = __WAIT_QUEUE_HEAD_INITIALIZER(name.phase_wait), \
	.reader_drain = __WAIT_QUEUE_HEAD_INITIALIZER(name.reader_drain), \
	.reader_osq = OSQ_LOCK_UNLOCKED, \
	.queued = ATOMIC_LONG_INIT(0), \
}
#define DECLARE_KD_RWSEM(name) \
	struct kd_rwsem name = KD_RWSEM_INITIALIZER(name)
#define DEFINE_KD_RWSEM(name) \
	struct kd_rwsem name = KD_RWSEM_INITIALIZER(name)

#endif
