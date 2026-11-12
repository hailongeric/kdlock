/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_RW_NATIVE_H
#define KDLOCK_RW_NATIVE_H

#include <linux/list.h>
#include "rw.h"

/* Physical-local compatibility has no source state or register backing. The
 * caller supplies finite storage covering held credits, native waiters and
 * canceled entries still retained by the shared MCS queue. Availability is a
 * supported-workload precondition, not an exhaustion recovery/fallback policy.
 * The lock object remains valid through every API/queue actor's final object
 * access, including canceled entries awaiting predecessor cleanup. Clearing
 * physical reader/writer state or waking a new reader does not permit free.
 * Cold unbind requires caller quiescence and pool_idle, not counts alone.
 * Pool/control backing and callback code outlive every API call and queue user,
 * including calls which already returned -EINTR. Quiescent teardown checks idle.
 */
enum kd_rw_native_phase {
	KD_RW_NATIVE_FREE,
	KD_RW_NATIVE_READ_WAIT,
	KD_RW_NATIVE_READ_HELD,
	KD_RW_NATIVE_WRITE_WAIT,
	KD_RW_NATIVE_WRITE_HELD,
	KD_RW_NATIVE_CANCELLED,
	KD_RW_NATIVE_RELEASING,
};

struct kd_rw_native_pool;
struct kd_task_root_context;
struct kd_rw_native_record {
	struct kd_rw_native_pool *pool;
	struct task_struct *task;
	struct kd_task_root_context *native_root;
	struct list_head task_link;
	struct kd_rw_read_link active_read;
	struct kd_mutex_node node;
	struct kd_mutex_batch batch;
	enum kd_rw_native_phase phase;
	bool non_owner;
	bool caller_user;
	bool grant_user;
	bool queue_user;
	bool turn_owned;
};

struct kd_rw_native_pool {
	raw_spinlock_t guard;
	struct kd_rw *lock;
	struct kd_rw_native_record *records;
	unsigned int capacity;
};

/* Cold private object initialization, before any source/native publication.
 * Records contain no packet. Pool backing remains independently retained after
 * the lock object's last physical access, until all control/API users end.
 */
int kd_rw_native_pool_init(struct kd_rw *lock, struct kd_rw_native_pool *pool,
		struct kd_rw_native_record *records, unsigned int capacity);
bool kd_rw_native_pool_idle(struct kd_rw_native_pool *pool);

/* Supported sleepable task context. Read wait_state is UNINTERRUPTIBLE,
 * INTERRUPTIBLE or KILLABLE; write is UNINTERRUPTIBLE or KILLABLE. Actual grant
 * wins before signal. Normal returns are0/-EINTR, and try returns1/0 without
 * queue publication on failure. Negative validation/storage errors describe a
 * violated provisioning/caller contract, never a successful lock operation.
 */
int kd_rw_native_read_lock(struct kd_rw *lock, unsigned int wait_state,
		bool non_owner);
int kd_rw_native_read_trylock(struct kd_rw *lock, bool non_owner);
int kd_rw_native_read_unlock(struct kd_rw *lock, bool non_owner);
int kd_rw_native_write_lock(struct kd_rw *lock, unsigned int wait_state);
int kd_rw_native_write_trylock(struct kd_rw *lock);
int kd_rw_native_write_unlock(struct kd_rw *lock);
int kd_rw_native_downgrade_write(struct kd_rw *lock);

/* Includes managed source grants as well as native grants. Diagnostic results
 * are observations only, never acquisition/release authority. owner_task is a
 * speculative task pointer value; the caller may not dereference it as a hold.
 */
bool kd_rw_native_is_locked(struct kd_rw *lock);
bool kd_rw_native_is_write_locked(struct kd_rw *lock);
bool kd_rw_native_is_contended(struct kd_rw *lock);
bool kd_rw_native_is_reader_owned(struct kd_rw *lock);
struct task_struct *kd_rw_native_owner_task(struct kd_rw *lock);

/* Private MCS hooks: turn/cancel selection uses pool->guard. A false selection
 * leaves an exact canceled queue user for the predecessor to detach. depart is
 * the last node/control access by that queue actor; no caller reads it later.
 */
bool kd_rw_native_select_turn(struct kd_rw_native_record *record);
void kd_rw_native_queue_depart(struct kd_rw_native_record *record);

#endif
