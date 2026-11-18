// SPDX-License-Identifier: GPL-2.0-only
/* Ordinary native admission uses task ownership records, without JIT setup. */
#include <linux/bug.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/sched.h>

#include "rw_local.h"
#include "rw_admission.h"
#include "task_state.h"
#include "task_progress.h"
#include "episode.h"
#include "observation.h"

void kd_rw_local_init(struct kd_rw_local *local, struct list_head *free)
{
	struct kd_rw_native_record *record = &local->record;

	raw_spin_lock_init(&local->pool.guard);
	local->pool.lock = NULL;
	local->pool.records = record;
	local->pool.capacity = 1;
	local->pool.ordinary_free = free;
	record->pool = &local->pool;
	record->phase = KD_RW_NATIVE_FREE;
	record->task = NULL;
	record->native_root = NULL;
	record->caller_user = false;
	record->grant_user = false;
	record->queue_user = false;
	record->turn_owned = false;
	record->non_owner = false;
	record->ordinary_write = false;
	record->ordinary_queued = false;
	INIT_LIST_HEAD(&record->task_link);
	kd_rw_read_link_init(&record->active_read);
	list_add_tail(&record->free_link, free);
}

struct kd_task_root_context *kd_rw_local_root(void)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_execution_binding *native;
	bool pending;

	/* Inspect header occupancy before the own core: a waiting origin must
	 * never read the packet currently borrowed by another physical task.
	 */
	if (!root || !root->attached || root->task != current || root->aux_entry ||
	    root->source_closing || !root->mutex_resources ||
	    root->mutex_resources->config.family != KD_LOCK_FAMILY_RWSEM ||
	    !in_task() || in_atomic() || irqs_disabled() ||
	    READ_ONCE(current->__state) != TASK_RUNNING)
		return NULL;
	native = kd_state_current_binding(&root->core);
	if (!kd_state_is_current(&root->core, native) || native->kind != KD_EXECUTION_NATIVE)
		return NULL;
	/* A previous native unlock can leave the exact owner awaiting its final
	 * source-user drop. Progress only when those duties are actually present.
	 * Open nested/retained grants keep the existing common source route.
	 */
	if (!list_empty(&root->owners.batches) || !list_empty(&root->core.grants)) {
		BUG_ON(kd_task_progress_native(root, native, &pending));
		if (!list_empty(&root->owners.batches) || !list_empty(&root->core.grants))
			return NULL;
	}
	if (root->mutex_fast.held || root->rwsem_fast.lock || root->core.exit_image ||
	    root->core.exit_use || root->core.exit_holder ||
	    (root->core.operation.phase != KD_OPERATION_IDLE &&
	     root->core.operation.phase != KD_OPERATION_RESUMABLE))
		return NULL;
	return root;
}

static struct kd_rw_native_record *reserve_local(struct kd_task_root_context *root,
		struct kd_rw *lock)
{
	struct kd_rw_native_record *record;

	/* The explicit finite resource capacity covers all simultaneous native
	 * records. As with persistent source storage, availability is a workload
	 * precondition, without a new per-operation allocator or recovery policy.
	 */
	record = list_first_entry(&root->mutex_resources->ordinary_free,
		struct kd_rw_native_record, free_link);
	list_del_init(&record->free_link);
	record->pool->lock = lock;
	record->task = current;
	record->native_root = NULL;
	record->active_read.logical_owner = current;
	record->active_read.credit = record;
	record->caller_user = false;
	record->grant_user = false;
	record->queue_user = false;
	record->turn_owned = false;
	record->ordinary_write = false;
	record->ordinary_queued = false;
	return record;
}

static void link_local(struct kd_rw_native_record *record, struct kd_task_root_context *root)
{
	record->native_root = root;
	record->grant_user = true;
	list_add_tail(&record->task_link, &root->native_grants);
}

static void free_local(struct kd_rw_native_record *record)
{
	list_del_init(&record->task_link);
	record->native_root = NULL;
	record->grant_user = false;
	record->phase = KD_RW_NATIVE_FREE;
	record->task = NULL;
	list_add(&record->free_link, record->pool->ordinary_free);
}

static void observe_local(unsigned long kind, struct kd_rw *lock,
		struct kd_rw_native_record *record, bool read)
{
	kd_observe(kind, .state = (unsigned long)kd_task_state_own(),
		.origin = (unsigned long)current, .acquisition = (unsigned long)record,
		.owner = read ? 0 : (unsigned long)record, .owner_task = (unsigned long)current,
		.object = (unsigned long)lock, .related = (unsigned long)record,
		.phase = read ? KD_GRANT_PHYSICAL_READ : KD_GRANT_PHYSICAL_WRITE,
		.source_user = (unsigned long)record, .flags = KD_OBS_FLAG_ORDINARY_RWSEM);
}

void kd_rw_local_done(struct kd_rw *lock, struct kd_rw_native_record *record)
{
	/* The object may already be gone; only its scalar address is used. */
	kd_observe(KD_OBS_ORDINARY_RWSEM_DONE, .state = (unsigned long)kd_task_state_own(),
		.origin = (unsigned long)current, .acquisition = (unsigned long)record,
		.object = (unsigned long)lock, .related = (unsigned long)record,
		.phase = record->ordinary_write ? KD_GRANT_PHYSICAL_WRITE : KD_GRANT_PHYSICAL_READ,
		.flags = KD_OBS_FLAG_ORDINARY_RWSEM |
			(record->ordinary_queued && smp_load_acquire(&record->node.queue_done) ?
			 KD_OBS_FLAG_QUEUE_DONE : 0) |
			(record->ordinary_queued && smp_load_acquire(&record->node.retirable) ?
			 KD_OBS_FLAG_NODE_RETIRABLE : 0));
}

bool kd_rw_local_read_lock(struct kd_rw *lock)
{
	struct kd_task_root_context *root = kd_rw_local_root();
	struct kd_rw_native_record *record;
	int result;

	if (!root || !lock || !lock->atomic_admission)
		return false;
	record = reserve_local(root, lock);
	if (!kd_rw_admission_read_try(lock)) {
		result = kd_rw_admission_read(lock, TASK_UNINTERRUPTIBLE, NULL, NULL);
		BUG_ON(result);
	}
	record->phase = KD_RW_NATIVE_ORDINARY_READ;
	record->active_read.kind = KD_RW_READ_ORDINARY;
	link_local(record, root);
	kd_rw_read_link_task(&record->active_read, lock);
	observe_local(KD_OBS_READ_ACQUIRE, lock, record, true);
	return true;
}

bool kd_rw_local_write_try(struct kd_rw *lock, struct kd_task_root_context *root)
{
	struct kd_rw_native_record *record;

	if (!kd_rw_admission_write_try(lock, false))
		return false;
	record = reserve_local(root, lock);
	record->phase = KD_RW_NATIVE_ORDINARY_WRITE;
	record->ordinary_write = true;
	link_local(record, root);
	WRITE_ONCE(lock->ordinary_writer, record);
	WRITE_ONCE(lock->ordinary_writer_task, current);
	observe_local(KD_OBS_NATIVE_WRITE_ACQUIRE, lock, record, false);
	return true;
}

int kd_rw_local_write_lock(struct kd_rw *lock, struct kd_task_root_context *root)
{
	struct kd_rw_native_record *record = reserve_local(root, lock);

	record->ordinary_write = true;
	record->ordinary_queued = true;
	record->active_read.kind = KD_RW_READ_NATIVE;
	return kd_rw_native_write_reserved(lock, record);
}

bool kd_rw_local_read_release(struct kd_rw *lock)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_rw_native_record *record;
	const void *last;

	if (!root || !root->attached || root->task != current || root->aux_entry ||
	    !in_task() || in_atomic() || irqs_disabled())
		return false;
	if (kd_rw_last_owned_read(lock, current, &last) != KD_RW_READ_ORDINARY)
		return false;
	record = (void *)last;
	BUG_ON(record->phase != KD_RW_NATIVE_ORDINARY_READ || !record->grant_user ||
	       record->task != current || record->pool->lock != lock);
	kd_rw_read_unlink_task(&record->active_read);
	observe_local(KD_OBS_READ_RELEASE, lock, record, true);
	kd_rw_admission_read_put(lock);
	/* Only independently task-owned metadata follows the final object access. */
	kd_rw_local_done(lock, record);
	free_local(record);
	return true;
}

bool kd_rw_local_write_release(struct kd_rw *lock, bool downgrade)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_rw_native_record *record;

	if (!root || !root->attached || root->task != current || root->aux_entry ||
	    !in_task() || in_atomic() || irqs_disabled())
		return false;
	list_for_each_entry_reverse(record, &root->native_grants, task_link) {
		if (record->pool->lock != lock || record->phase != KD_RW_NATIVE_ORDINARY_WRITE)
			continue;
		BUG_ON(READ_ONCE(lock->ordinary_writer) != record || record->task != current);
		WRITE_ONCE(lock->ordinary_writer, NULL);
		WRITE_ONCE(lock->ordinary_writer_task, NULL);
		if (downgrade) {
			record->phase = KD_RW_NATIVE_ORDINARY_READ;
			record->active_read.kind = KD_RW_READ_ORDINARY;
			kd_rw_read_link_task(&record->active_read, lock);
		}
		observe_local(downgrade ? KD_OBS_NATIVE_DOWNGRADE : KD_OBS_NATIVE_WRITE_RELEASE,
			lock, record, false);
		kd_rw_admission_write_put(lock, downgrade);
		if (!downgrade) {
			kd_rw_local_done(lock, record);
			free_local(record);
		}
		return true;
	}
	return false;
}

bool kd_rw_local_native_writer(struct kd_rw *lock)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_rw_native_record *record;

	if (!root || !root->attached || root->task != current || root->aux_entry)
		return false;
	list_for_each_entry_reverse(record, &root->native_grants, task_link)
		if (record->pool->lock == lock &&
		    (record->phase == KD_RW_NATIVE_WRITE_HELD ||
		     record->phase == KD_RW_NATIVE_ORDINARY_WRITE))
			return true;
	return false;
}

struct kd_rw_native_record *kd_rw_local_read_candidate(struct kd_task_root_context *root,
		struct kd_rw *inner)
{
	struct kd_rw_native_record *record;

	/* The caller just obtained this native root. Bound this first bridge to
	 * one ordinary read, no other owned credit and a distinct inner writer.
	 * Callable, nonowner, repeated and downgraded reads retain their routes.
	 */
	if (!root || !inner || !inner->atomic_admission ||
	    !list_empty(&root->core.grants) || !list_is_singular(&root->native_grants) ||
	    !list_is_singular(&root->rwsem_reads))
		return NULL;
	record = list_first_entry(&root->native_grants, struct kd_rw_native_record, task_link);
	if (record->phase != KD_RW_NATIVE_ORDINARY_READ || record->task != current ||
	    record->native_root != root || !record->grant_user || record->non_owner ||
	    record->caller_user || record->queue_user || record->ordinary_write ||
	    record->ordinary_queued || record->pool->lock == inner ||
	    !record->pool->lock->atomic_admission ||
	    record->pool->ordinary_free != &root->mutex_resources->ordinary_free ||
	    record->active_read.kind != KD_RW_READ_ORDINARY ||
	    record->active_read.object != record->pool->lock ||
	    record->active_read.root != root || record->active_read.credit != record ||
	    record->active_read.logical_owner != current ||
	    root->rwsem_reads.next != &record->active_read.task_link)
		return NULL;
	return record;
}

static int drop_promoted_read(void *control, const void *user)
{
	struct kd_rw_native_record *record = control;
	struct kd_source_grant *grant = &record->read_bridge.grant;
	int result;

	if (user != record || record->phase != KD_RW_NATIVE_PROMOTED_READ ||
	    !record->read_bridge.published || grant->linked || grant->logical_open ||
	    record->task != current || !record->grant_user)
		return -ESTALE;
	result = kd_rw_read_credit_unlink(&record->read_bridge.credit,
		grant->state, record, record);
	if (result)
		return result;
	/* Physical release ended all object accesses. The original task-owned
	 * record survives independently until this exact grant's final drop.
	 */
	kd_rw_local_done(record->pool->lock, record);
	free_local(record);
	return 0;
}

bool kd_rw_local_read_promoted(const struct kd_source_grant *grant)
{
	return grant && grant->drop == drop_promoted_read;
}

void kd_rw_local_read_rollback(struct kd_rw_native_record *record)
{
	struct kd_task_root_context *root = record->native_root;
	struct kd_source_grant *grant = &record->read_bridge.grant;
	struct kd_rw_read_credit *credit = &record->read_bridge.credit;
	struct kd_rw *lock = record->pool->lock;

	/* Private, before any source offer/auxiliary entry is published. This is
	 * a metadata transfer back to the same held read, never an unlock.
	 */
	BUG_ON(record->phase != KD_RW_NATIVE_PROMOTED_READ ||
	       record->read_bridge.published || record->task != current ||
	       !root || root->aux_entry || root != kd_task_root_context_current() ||
	       !credit->active || credit->released);
	if (grant->linked) {
		list_del_init(&grant->state_link);
		grant->linked = false;
		grant->logical_open = false;
	}
	raw_spin_lock(&lock->guard);
	BUG_ON(!lock->readers);
	lock->readers--;
	list_del_init(&credit->active_read.link);
	list_replace_init(&credit->active_read.task_link, &record->active_read.task_link);
	record->active_read.root = root;
	credit->active_read.root = NULL;
	credit->active = false;
	raw_spin_unlock(&lock->guard);
	record->phase = KD_RW_NATIVE_ORDINARY_READ;
	list_add_tail(&record->task_link, &root->native_grants);
}

int kd_rw_local_read_promote(struct kd_rw_native_record *record,
		struct kd_execution_binding *native)
{
	struct kd_task_root_context *root = record->native_root;
	struct kd_rw *lock = record->pool->lock;
	struct kd_rw_read_credit *credit = &record->read_bridge.credit;
	struct kd_source_grant *grant = &record->read_bridge.grant;
	int result;

	if (!root || record->task != current || native->kind != KD_EXECUTION_NATIVE ||
	    !kd_state_is_current(&root->core, native) ||
	    record->phase != KD_RW_NATIVE_ORDINARY_READ)
		return -EPERM;
	kd_rw_read_credit_init(credit);
	credit->lock = lock;
	credit->state = &root->core;
	credit->acquisition = record;
	credit->user = record;
	credit->active_read.logical_owner = record->task;
	credit->active_read.object = lock;
	kd_source_grant_init(grant, &root->core, &lock->queue, record, NULL,
		record, drop_promoted_read, record);
	grant->family = KD_LOCK_FAMILY_RWSEM;
	grant->mode = KD_GRANT_MODE_READ;
	grant->physical = KD_GRANT_PHYSICAL_READ;
	grant->read_credit = credit;
	record->read_bridge.published = false;
	/* The original atomic read remains continuously charged. Only the exact
	 * guarded credit index and current-source index change representation.
	 */
	raw_spin_lock(&lock->guard);
	lock->readers++;
	credit->active = true;
	list_add_tail(&credit->active_read.link, &lock->active_reads);
	list_replace_init(&record->active_read.task_link, &credit->active_read.task_link);
	credit->active_read.root = root;
	record->active_read.root = NULL;
	raw_spin_unlock(&lock->guard);
	list_del_init(&record->task_link);
	record->phase = KD_RW_NATIVE_PROMOTED_READ;
	result = kd_state_link_grant(&root->core, native, grant);
	if (result)
		kd_rw_local_read_rollback(record);
	return result;
}

void kd_rw_local_read_commit(struct kd_rw_native_record *record,
		struct kd_mutex_node *writer, const struct kd_jit_image *image)
{
	BUG_ON(record->phase != KD_RW_NATIVE_PROMOTED_READ ||
	       record->read_bridge.published || !record->read_bridge.grant.linked ||
	       !writer->ready || writer->enqueued || !image);
	record->read_bridge.published = true;
	kd_observe(KD_OBS_READ_PROMOTE, .state = (unsigned long)record->read_bridge.grant.state,
		.origin = (unsigned long)record->task, .acquisition = (unsigned long)record,
		.object = (unsigned long)record->pool->lock,
		.related = (unsigned long)&record->read_bridge.credit,
		.node = (unsigned long)writer, .parent = (unsigned long)writer->acquisition,
		.image = (unsigned long)image, .phase = KD_GRANT_PHYSICAL_READ,
		.source_user = (unsigned long)record, .flags = KD_OBS_FLAG_ORDINARY_RWSEM);
}

int kd_rw_local_read_release_promoted(struct kd_task_root_context *root,
		struct kd_execution_binding *native, struct kd_mutex *lock,
		enum kd_operation_kind operation)
{
	struct kd_source_grant *grant;
	struct kd_rw_native_record *record;
	const void *credit;
	int result;

	if (operation != KD_OPERATION_RWSEM_UP_READ)
		return -EOPNOTSUPP;
	if (!root || !root->attached || root != kd_task_root_context_current() ||
	    root->task != current || root->aux_entry || !in_task() || in_atomic() ||
	    irqs_disabled() || !kd_state_is_current(&root->core, native) ||
	    native->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	grant = kd_state_find_operation_grant(&root->core, native, lock, operation);
	if (IS_ERR(grant) || !kd_rw_local_read_promoted(grant))
		return -EOPNOTSUPP;
	record = grant->control;
	if (!record || &record->read_bridge.grant != grant || record->native_root != root ||
	    record->phase != KD_RW_NATIVE_PROMOTED_READ || !record->read_bridge.published ||
	    record->task != current || grant->acquisition != record || grant->user != record ||
	    grant->read_credit != &record->read_bridge.credit)
		return -ESTALE;
	if (kd_rw_last_owned_read(container_of(lock, struct kd_rw, queue), current, &credit) !=
	    KD_RW_READ_MANAGED || credit != grant->read_credit)
		return -ESTALE;
	result = kd_rw_read_release(grant->read_credit, &root->core, native,
		grant->acquisition, grant->user);
	if (result)
		return result;
	result = kd_state_close_grant(&root->core, native, grant);
	if (result)
		return result;
	/* Final drop returns the original record; no grant/control access follows. */
	return kd_state_unlink_grant(&root->core, native, grant);
}
