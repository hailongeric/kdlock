// SPDX-License-Identifier: GPL-2.0-only
/* Physical-local Linux rwsem compatibility on the existing KD family gate. */
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <asm/processor.h>

#include "rw_native.h"
#include "task_state.h"
#include "observation.h"

static bool native_context(void)
{
	return in_task() && !in_atomic() && !irqs_disabled();
}

static bool read_wait_state(unsigned int state)
{
	return state == TASK_UNINTERRUPTIBLE || state == TASK_INTERRUPTIBLE ||
	       state == TASK_KILLABLE;
}

/* pool->guard owns control users and reuse. It is independent of the lock
 * object's physical guard, so no lock-object access follows final handoff.
 * When both are needed, family guard precedes pool guard, never the reverse.
 */
static struct task_struct *record_free_locked(struct kd_rw_native_record *record)
{
	struct task_struct *task;

	if (record->caller_user || record->grant_user || record->queue_user)
		return NULL;
	task = record->task;
	record->task = NULL;
	record->phase = KD_RW_NATIVE_FREE;
	return task;
}

static void caller_done(struct kd_rw_native_record *record)
{
	struct kd_rw_native_pool *pool = record->pool;
	struct task_struct *task;

	raw_spin_lock(&pool->guard);
	record->caller_user = false;
	task = record_free_locked(record);
	raw_spin_unlock(&pool->guard);
	if (task)
		put_task_struct(task);
}

static int reserve_record(struct kd_rw *lock, enum kd_rw_native_phase phase,
		bool non_owner, struct kd_rw_native_record **out)
{
	struct kd_rw_native_pool *pool;
	struct kd_rw_native_record *record;
	unsigned int i;
	int result = -ENOSPC;

	if (!lock || !out)
		return -EINVAL;
	*out = NULL;
	if (!native_context())
		return -EPERM;
	pool = READ_ONCE(lock->native_pool);
	if (!pool || pool->lock != lock)
		return -ENODEV;
	raw_spin_lock(&pool->guard);
	for (i = 0; i < pool->capacity; ++i) {
		record = &pool->records[i];
		if (record->phase != KD_RW_NATIVE_FREE)
			continue;
		record->task = current;
		get_task_struct(current);
		record->phase = phase;
		record->non_owner = non_owner;
		record->caller_user = true;
		record->grant_user = false;
		record->queue_user = false;
		record->turn_owned = false;
		record->native_root = NULL;
		INIT_LIST_HEAD(&record->task_link);
		INIT_LIST_HEAD(&record->active_read.link);
		record->active_read.logical_owner = current;
		record->active_read.kind = non_owner ? KD_RW_READ_NON_OWNER : KD_RW_READ_NATIVE;
		record->active_read.credit = record;
		*out = record;
		result = 0;
		break;
	}
	raw_spin_unlock(&pool->guard);
	/* Availability is provisioned before use, including canceled queue users.
	 * This error is not a void-lock fallback, wait-for-storage or new assertion.
	 */
	return result;
}

int kd_rw_native_pool_init(struct kd_rw *lock, struct kd_rw_native_pool *pool,
		struct kd_rw_native_record *records, unsigned int capacity)
{
	unsigned int i;

	if (!lock || !pool || !records || !capacity)
		return -EINVAL;
	raw_spin_lock(&lock->guard);
	if (lock->native_pool || lock->readers || lock->writer_pending || lock->writer ||
	    READ_ONCE(lock->queue.tail)) {
		raw_spin_unlock(&lock->guard);
		return -EBUSY;
	}
	raw_spin_lock_init(&pool->guard);
	pool->lock = lock;
	pool->records = records;
	pool->capacity = capacity;
	for (i = 0; i < capacity; ++i) {
		records[i].pool = pool;
		records[i].task = NULL;
		records[i].phase = KD_RW_NATIVE_FREE;
		records[i].caller_user = false;
		records[i].grant_user = false;
		records[i].queue_user = false;
		records[i].turn_owned = false;
		records[i].non_owner = false;
		records[i].native_root = NULL;
		INIT_LIST_HEAD(&records[i].task_link);
		INIT_LIST_HEAD(&records[i].active_read.link);
	}
	WRITE_ONCE(lock->native_pool, pool);
	raw_spin_unlock(&lock->guard);
	return 0;
}

bool kd_rw_native_pool_idle(struct kd_rw_native_pool *pool)
{
	struct kd_rw *lock;
	unsigned int i;
	bool idle = true;

	if (!pool || !(lock = pool->lock))
		return false;
	raw_spin_lock(&lock->guard);
	raw_spin_lock(&pool->guard);
	if (lock->readers || lock->writer || lock->writer_pending ||
	    READ_ONCE(lock->queue.tail))
		idle = false;
	for (i = 0; idle && i < pool->capacity; ++i)
		idle = pool->records[i].phase == KD_RW_NATIVE_FREE;
	raw_spin_unlock(&pool->guard);
	raw_spin_unlock(&lock->guard);
	return idle;
}

/* Owned native grants keep the exact attached physical task root alive. Only
 * that current task links/unlinks its own list; nonowner credits never do so.
 * Attachment before the first owned selected grant is a caller precondition.
 */
static void native_grant_link(struct kd_rw_native_record *record)
{
	if (!record->non_owner) {
		record->native_root = kd_task_root_context_current();
		if (record->native_root)
			list_add_tail(&record->task_link, &record->native_root->native_grants);
	}
}

static void native_grant_unlink(struct kd_rw_native_record *record)
{
	if (record->native_root) {
		list_del_init(&record->task_link);
		record->native_root = NULL;
	}
}

static void observe_native(unsigned long kind, struct kd_rw *lock,
		struct kd_rw_native_record *record, bool writer,
		unsigned long phase, long result)
{
	kd_observe(kind, .origin = (unsigned long)record->task,
		.node = writer ? (unsigned long)&record->node : 0,
		.acquisition = (unsigned long)record,
		.owner = writer && record->batch.initialized ?
			(unsigned long)&record->batch.release_owner : 0,
		.owner_task = (unsigned long)record->task,
		.object = (unsigned long)&lock->queue, .related = (unsigned long)record,
		.cursor = lock->readers, .phase = phase, .result = (unsigned long)result);
}

static void grant_read_locked(struct kd_rw *lock, struct kd_rw_native_record *record,
		int result)
{
	lock->readers++;
	record->phase = KD_RW_NATIVE_READ_HELD;
	record->grant_user = true;
	list_add_tail(&record->active_read.link, &lock->active_reads);
	native_grant_link(record);
	observe_native(KD_OBS_NATIVE_READ_ACQUIRE, lock, record, false,
		KD_GRANT_PHYSICAL_READ, result);
}

static int read_lock_common(struct kd_rw *lock, unsigned int wait_state,
		bool non_owner, bool try_only)
{
	struct kd_rw_native_record *record;
	struct kd_rw_native_pool *pool;
	DEFINE_WAIT(wait);
	int result;

	if (!read_wait_state(wait_state))
		return -EINVAL;
	result = reserve_record(lock, KD_RW_NATIVE_READ_WAIT, non_owner, &record);
	if (result)
		return result;
	pool = record->pool;
	for (;;) {
		if (!try_only)
			prepare_to_wait(&lock->changed, &wait, wait_state);
		raw_spin_lock(&lock->guard);
		raw_spin_lock(&pool->guard);
		/* Serialize physical admission before signal cancellation. */
		if (!lock->writer_pending && !lock->writer) {
			grant_read_locked(lock, record, try_only ? 1 : 0);
			result = try_only ? 1 : 0;
		} else if (try_only) {
			observe_native(KD_OBS_NATIVE_TRY_MISS, lock, record, false,
				KD_GRANT_PHYSICAL_READ, 0);
			result = 0;
		} else if (signal_pending_state(wait_state, current)) {
			record->phase = KD_RW_NATIVE_CANCELLED;
			observe_native(KD_OBS_NATIVE_CANCEL, lock, record, false,
				KD_GRANT_PHYSICAL_READ, -EINTR);
			result = -EINTR;
		} else {
			raw_spin_unlock(&pool->guard);
			raw_spin_unlock(&lock->guard);
			schedule();
			continue;
		}
		raw_spin_unlock(&pool->guard);
		raw_spin_unlock(&lock->guard);
		break;
	}
	if (!try_only)
		finish_wait(&lock->changed, &wait);
	caller_done(record);
	return result;
}

int kd_rw_native_read_lock(struct kd_rw *lock, unsigned int wait_state, bool non_owner)
{
	return read_lock_common(lock, wait_state, non_owner, false);
}

int kd_rw_native_read_trylock(struct kd_rw *lock, bool non_owner)
{
	return read_lock_common(lock, TASK_UNINTERRUPTIBLE, non_owner, true);
}

int kd_rw_native_read_unlock(struct kd_rw *lock, bool non_owner)
{
	struct kd_rw_native_pool *pool;
	struct kd_rw_native_record *record = NULL;
	struct kd_rw_read_link *entry;

	if (!lock || !native_context())
		return -EPERM;
	pool = READ_ONCE(lock->native_pool);
	if (!pool)
		return -ENODEV;
	raw_spin_lock(&lock->guard);
	if (non_owner) {
		/* Linux supplies no transfer token; choose one exact eligible held
		 * nonowner credit, oldest first, rather than decrementing a count.
		 */
		list_for_each_entry(entry, &lock->active_reads, link) {
			if (entry->kind == KD_RW_READ_NON_OWNER) {
				record = (void *)entry->credit;
				break;
			}
		}
	} else {
		list_for_each_entry_reverse(entry, &lock->active_reads, link) {
			if (entry->kind != KD_RW_READ_NON_OWNER && entry->logical_owner == current) {
				if (entry->kind == KD_RW_READ_NATIVE)
					record = (void *)entry->credit;
				break;
			}
		}
	}
	if (!record) {
		raw_spin_unlock(&lock->guard);
		return -ESTALE;
	}
	raw_spin_lock(&pool->guard);
	if (record->pool != pool || record->phase != KD_RW_NATIVE_READ_HELD ||
	    !record->grant_user || record->caller_user || !lock->readers) {
		raw_spin_unlock(&pool->guard);
		raw_spin_unlock(&lock->guard);
		return -ESTALE;
	}
	record->caller_user = true;
	list_del_init(&record->active_read.link);
	native_grant_unlink(record);
	lock->readers--;
	record->grant_user = false;
	record->phase = KD_RW_NATIVE_RELEASING;
	observe_native(KD_OBS_NATIVE_READ_RELEASE, lock, record, false,
		KD_GRANT_PHYSICAL_READ, 0);
	raw_spin_unlock(&pool->guard);
	wake_up_all(&lock->changed);
	raw_spin_unlock(&lock->guard);
	/* The independent control pool is the only backing touched after this. */
	caller_done(record);
	return 0;
}

bool kd_rw_native_select_turn(struct kd_rw_native_record *record)
{
	struct kd_rw_native_pool *pool = record->pool;
	bool selected;

	raw_spin_lock(&pool->guard);
	selected = record->queue_user && record->phase == KD_RW_NATIVE_WRITE_WAIT;
	if (selected)
		record->turn_owned = true;
	raw_spin_unlock(&pool->guard);
	return selected;
}

void kd_rw_native_queue_depart(struct kd_rw_native_record *record)
{
	struct kd_rw_native_pool *pool = record->pool;
	struct task_struct *task;

	raw_spin_lock(&pool->guard);
	record->queue_user = false;
	task = record_free_locked(record);
	raw_spin_unlock(&pool->guard);
	if (task)
		put_task_struct(task);
}

static int native_start(struct kd_rw_native_record *record)
{
	while (!smp_load_acquire(&record->node.turn)) {
		cpu_relax();
		cond_resched();
	}
	return kd_mutex_native_start(&record->node, &record->batch);
}

static int write_lock_common(struct kd_rw *lock, unsigned int wait_state, bool try_only)
{
	struct kd_rw_native_record *record;
	struct kd_rw_native_pool *pool;
	DEFINE_WAIT(wait);
	bool cancel = false;
	int result;

	if (wait_state != TASK_UNINTERRUPTIBLE && wait_state != TASK_KILLABLE)
		return -EINVAL;
	result = reserve_record(lock, KD_RW_NATIVE_WRITE_WAIT, false, &record);
	if (result)
		return result;
	pool = record->pool;
	kd_mutex_batch_init(&record->batch);
	result = kd_mutex_native_node_init(&record->node, record);
	if (result) {
		caller_done(record);
		return result;
	}
	if (try_only) {
		raw_spin_lock(&lock->guard);
		raw_spin_lock(&pool->guard);
		if (lock->writer_pending || lock->writer || lock->readers) {
			result = 0;
		} else {
			record->queue_user = true;
			result = kd_mutex_native_enqueue(&lock->queue, &record->node, true);
			if (result == 1) {
				record->turn_owned = true;
				result = kd_mutex_native_start(&record->node, &record->batch);
				if (!result) {
					lock->writer = &record->batch;
					record->phase = KD_RW_NATIVE_WRITE_HELD;
					record->grant_user = true;
					native_grant_link(record);
					observe_native(KD_OBS_NATIVE_WRITE_ACQUIRE, lock, record, true,
						KD_GRANT_PHYSICAL_WRITE, 1);
					result = 1;
				}
			} else {
				record->queue_user = false;
			}
		}
		if (!result)
			observe_native(KD_OBS_NATIVE_TRY_MISS, lock, record, true,
				KD_GRANT_PHYSICAL_WRITE, 0);
		raw_spin_unlock(&pool->guard);
		raw_spin_unlock(&lock->guard);
		if (result >= 0)
			caller_done(record);
		return result;
	}
	/* Publish the queue's persistent storage user before its first link. */
	raw_spin_lock(&pool->guard);
	record->queue_user = true;
	raw_spin_unlock(&pool->guard);
	result = kd_mutex_native_enqueue(&lock->queue, &record->node, false);
	if (result != 1)
		return result; /* Unexpected protocol error retains controls. */
	for (;;) {
		bool start = false;
		bool acquired = false;

		prepare_to_wait(&lock->changed, &wait, wait_state);
		raw_spin_lock(&lock->guard);
		raw_spin_lock(&pool->guard);
		if (smp_load_acquire(&record->node.turn))
			record->turn_owned = true;
		if (record->turn_owned && !record->batch.initialized) {
			start = true;
		} else if (record->turn_owned) {
			lock->writer_pending = true;
			if (!lock->readers) {
				lock->writer = &record->batch;
				lock->writer_pending = false;
				record->phase = KD_RW_NATIVE_WRITE_HELD;
				record->grant_user = true;
				native_grant_link(record);
				observe_native(KD_OBS_NATIVE_WRITE_ACQUIRE, lock, record, true,
					KD_GRANT_PHYSICAL_WRITE, 0);
				acquired = true;
			}
		}
		/* A granted operation wins. Once cancellation wins, only the exact
		 * turn owner or predecessor may remove its queue user.
		 */
		if (!acquired && !start && signal_pending_state(wait_state, current)) {
			record->phase = KD_RW_NATIVE_CANCELLED;
			if (record->turn_owned)
				lock->writer_pending = false;
			cancel = true;
			observe_native(KD_OBS_NATIVE_CANCEL, lock, record, true,
				KD_GRANT_PHYSICAL_WRITE, -EINTR);
			wake_up_all(&lock->changed);
		}
		raw_spin_unlock(&pool->guard);
		raw_spin_unlock(&lock->guard);
		if (start) {
			__set_current_state(TASK_RUNNING);
			result = native_start(record);
			if (result) {
				finish_wait(&lock->changed, &wait);
				return result;
			}
			continue;
		}
		if (acquired || cancel)
			break;
		schedule();
	}
	finish_wait(&lock->changed, &wait);
	if (cancel && record->turn_owned) {
		result = kd_mutex_native_finish(&record->node, &record->batch);
		if (result)
			return result;
	}
	caller_done(record);
	return cancel ? -EINTR : 0;
}

int kd_rw_native_write_lock(struct kd_rw *lock, unsigned int wait_state)
{
	return write_lock_common(lock, wait_state, false);
}

int kd_rw_native_write_trylock(struct kd_rw *lock)
{
	return write_lock_common(lock, TASK_UNINTERRUPTIBLE, true);
}

static struct kd_rw_native_record *owned_writer_locked(struct kd_rw *lock)
{
	struct kd_mutex_batch *batch = lock->writer;
	struct kd_rw_native_record *record;

	if (!batch || !batch->head || !(record = batch->head->native_local) ||
	    record->task != current || record->phase != KD_RW_NATIVE_WRITE_HELD ||
	    !record->grant_user || record->caller_user)
		return NULL;
	return record;
}

static int finish_writer(struct kd_rw *lock, bool downgrade)
{
	struct kd_rw_native_pool *pool;
	struct kd_rw_native_record *record;
	int result;

	if (!lock || !native_context())
		return -EPERM;
	pool = READ_ONCE(lock->native_pool);
	if (!pool)
		return -ENODEV;
	raw_spin_lock(&lock->guard);
	raw_spin_lock(&pool->guard);
	record = owned_writer_locked(lock);
	if (!record) {
		raw_spin_unlock(&pool->guard);
		raw_spin_unlock(&lock->guard);
		return -ESTALE;
	}
	record->caller_user = true;
	if (downgrade) {
		/* A real credit exists before writer publication ends; the same
		 * owned root/control user continues through matching read unlock.
		 */
		lock->readers++;
		record->phase = KD_RW_NATIVE_READ_HELD;
		list_add_tail(&record->active_read.link, &lock->active_reads);

	} else {
		record->grant_user = false;
		record->phase = KD_RW_NATIVE_RELEASING;
		native_grant_unlink(record);
	}
	lock->writer = NULL;
	observe_native(downgrade ? KD_OBS_NATIVE_DOWNGRADE : KD_OBS_NATIVE_WRITE_RELEASE,
		lock, record, true, downgrade ? KD_GRANT_PHYSICAL_READ :
		KD_GRANT_PHYSICAL_WRITE, 0);
	raw_spin_unlock(&pool->guard);
	wake_up_all(&lock->changed);
	raw_spin_unlock(&lock->guard);
	result = kd_mutex_native_finish(&record->node, &record->batch);
	if (result)
		return result;
	caller_done(record);
	return 0;
}

int kd_rw_native_write_unlock(struct kd_rw *lock)
{
	return finish_writer(lock, false);
}

int kd_rw_native_downgrade_write(struct kd_rw *lock)
{
	return finish_writer(lock, true);
}

bool kd_rw_native_is_write_locked(struct kd_rw *lock)
{
	bool held;

	if (!lock)
		return false;
	raw_spin_lock(&lock->guard);
	held = lock->writer != NULL;
	raw_spin_unlock(&lock->guard);
	return held;
}

bool kd_rw_native_is_reader_owned(struct kd_rw *lock)
{
	bool held;

	if (!lock)
		return false;
	raw_spin_lock(&lock->guard);
	held = lock->readers != 0;
	raw_spin_unlock(&lock->guard);
	return held;
}

bool kd_rw_native_is_locked(struct kd_rw *lock)
{
	bool held;

	if (!lock)
		return false;
	raw_spin_lock(&lock->guard);
	held = lock->writer || lock->writer_pending || lock->readers ||
	       READ_ONCE(lock->queue.tail);
	raw_spin_unlock(&lock->guard);
	return held;
}

bool kd_rw_native_is_contended(struct kd_rw *lock)
{
	struct kd_mutex_batch *owner;
	struct kd_rw_native_pool *pool;
	struct kd_mutex_node *tail;
	unsigned int i;
	bool waiting;

	if (!lock)
		return false;
	raw_spin_lock(&lock->guard);
	owner = lock->writer;
	tail = READ_ONCE(lock->queue.tail);
	/* Lockless diagnostic only. Wait preparation drops its waitqueue lock
	 * before taking the family guard; no reverse lock acquisition occurs.
	 */
	waiting = waitqueue_active(&lock->changed) || lock->writer_pending ||
		  (tail && (!owner || tail != owner->head));
	pool = lock->native_pool;
	if (!waiting && pool) {
		raw_spin_lock(&pool->guard);
		for (i = 0; i < pool->capacity; ++i)
			if (pool->records[i].phase == KD_RW_NATIVE_READ_WAIT) {
				waiting = true;
				break;
			}
		raw_spin_unlock(&pool->guard);
	}
	raw_spin_unlock(&lock->guard);
	return waiting;
}

struct task_struct *kd_rw_native_owner_task(struct kd_rw *lock)
{
	struct kd_rw_read_link *entry;
	struct task_struct *task = NULL;

	if (!lock)
		return NULL;
	raw_spin_lock(&lock->guard);
	if (lock->writer)
		task = lock->writer->release_owner.task;
	else if (!list_empty(&lock->active_reads)) {
		entry = list_last_entry(&lock->active_reads, struct kd_rw_read_link, link);
		task = entry->logical_owner;
	}
	raw_spin_unlock(&lock->guard);
	return task;
}
