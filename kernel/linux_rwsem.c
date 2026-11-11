// SPDX-License-Identifier: GPL-2.0-only
/* Generic rebuilt Linux rwsem binding; every selected API uses one KD gate. */
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/rwsem.h>
#include <linux/sched.h>

#include "../include/kd_linux_rwsem.h"
#include "mutex_api.h"
#include "rw_native.h"

static struct kd_task_root_context *native_root(void)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_execution_binding *native;

	/* Header occupancy is checked before touching a possibly borrowed packet. */
	if (!root || !root->attached || root->task != current || root->aux_entry ||
	    !root->mutex_resources ||
	    root->mutex_resources->config.family != KD_LOCK_FAMILY_RWSEM)
		return NULL;
	native = kd_state_current_binding(&root->core);
	if (!kd_state_is_current(&root->core, native) ||
	    native->kind != KD_EXECUTION_NATIVE)
		return NULL;
	return root;
}

bool kd_linux_rwsem_source_ready(const struct kd_linux_rwsem_binding *binding)
{
	struct kd_task_root_context *root;

	if (!binding->source_calls)
		return false;
	root = native_root();
	return root && !root->source_closing && list_empty(&root->native_grants);
}

static struct kd_source_grant *managed_grant(
		const struct kd_linux_rwsem_binding *binding, bool read)
{
	struct kd_task_root_context *root = native_root();
	struct kd_source_grant *grant;
	const void *credit;

	if (!root)
		return NULL;
	grant = kd_state_find_operation_grant(&root->core,
		kd_state_current_binding(&root->core), &binding->lock->core.queue,
		read ? KD_OPERATION_RWSEM_UP_READ : KD_OPERATION_RWSEM_UP_WRITE);
	if (IS_ERR(grant))
		return NULL;
	if (read && grant->mode == KD_GRANT_MODE_READ) {
		/* The current original task retains its own still-held credit across
		 * this snapshot. No other actor may consume an owned read grant.
		 */
		if (kd_rw_last_owned_read(&binding->lock->core, current, &credit) !=
		    KD_RW_READ_MANAGED || credit != grant->read_credit)
			return NULL;
	}
	return grant;
}

bool kd_linux_rwsem_source_release(const struct kd_linux_rwsem_binding *binding,
		bool read)
{
	return managed_grant(binding, read) != NULL;
}

int kd_linux_rwsem_bind(struct rw_semaphore *object,
		struct kd_linux_rwsem_binding *binding, struct kd_rwsem *lock,
		bool source_calls)
{
	if (IS_ENABLED(CONFIG_DEBUG_LOCK_ALLOC) || IS_ENABLED(CONFIG_LOCKDEP) ||
	    IS_ENABLED(CONFIG_DEBUG_RWSEMS))
		return -EOPNOTSUPP;
	if (!object || !binding || !lock || !lock->core.native_pool)
		return -EINVAL;
	/* Caller already excluded all entry and observers. These are additional
	 * consistency checks, not a mechanism for establishing that exclusion.
	 */
	if (READ_ONCE(object->kd_binding) ||
	    atomic_long_read(&object->count) || !list_empty(&object->wait_list) ||
	    kd_rw_native_is_locked(&lock->core) ||
	    kd_rw_native_is_contended(&lock->core) ||
	    !kd_rw_native_pool_idle(lock->core.native_pool))
		return -EBUSY;
	binding->object = object;
	binding->lock = lock;
	binding->source_calls = source_calls;
	smp_store_release(&object->kd_binding, binding);
	return 0;
}

int kd_linux_rwsem_unbind(struct kd_linux_rwsem_binding *binding)
{
	struct kd_rw *lock;

	if (!binding || !binding->object || !binding->lock ||
	    READ_ONCE(binding->object->kd_binding) != binding)
		return -EINVAL;
	lock = &binding->lock->core;
	if (kd_rw_native_is_locked(lock) || kd_rw_native_is_contended(lock) ||
	    !kd_rw_native_pool_idle(lock->native_pool))
		return -EBUSY;
	/* The same complete caller-established last-user exclusion as bind is
	 * required; no later API may retain either object or binding after return.
	 */
	smp_store_release(&binding->object->kd_binding, NULL);
	return 0;
}

void kd_linux_rwsem_down_read(struct kd_linux_rwsem_binding *binding)
{
	(void)kd_rw_native_read_lock(&binding->lock->core, TASK_UNINTERRUPTIBLE, false);
}
int kd_linux_rwsem_down_read_interruptible(struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_read_lock(&binding->lock->core, TASK_INTERRUPTIBLE, false);
}
int kd_linux_rwsem_down_read_killable(struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_read_lock(&binding->lock->core, TASK_KILLABLE, false);
}
int kd_linux_rwsem_down_read_trylock(struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_read_trylock(&binding->lock->core, false);
}
void kd_linux_rwsem_down_write(struct kd_linux_rwsem_binding *binding)
{
	(void)kd_rw_native_write_lock(&binding->lock->core, TASK_UNINTERRUPTIBLE);
}
int kd_linux_rwsem_down_write_killable(struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_write_lock(&binding->lock->core, TASK_KILLABLE);
}
int kd_linux_rwsem_down_write_trylock(struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_write_trylock(&binding->lock->core);
}

void kd_linux_rwsem_up_read(struct kd_linux_rwsem_binding *binding)
{
	struct kd_task_root_context *root;

	if (managed_grant(binding, true)) {
		root = native_root();
		(void)kd_episode_unlock_native(root->mutex_resources, root,
			kd_state_current_binding(&root->core), &binding->lock->core.queue,
			KD_OPERATION_RWSEM_UP_READ);
		return;
	}
	(void)kd_rw_native_read_unlock(&binding->lock->core, false);
}
void kd_linux_rwsem_up_write(struct kd_linux_rwsem_binding *binding)
{
	struct kd_task_root_context *root;

	if (managed_grant(binding, false)) {
		root = native_root();
		(void)kd_episode_unlock_native(root->mutex_resources, root,
			kd_state_current_binding(&root->core), &binding->lock->core.queue,
			KD_OPERATION_RWSEM_UP_WRITE);
		return;
	}
	(void)kd_rw_native_write_unlock(&binding->lock->core);
}
void kd_linux_rwsem_downgrade_write(struct kd_linux_rwsem_binding *binding)
{
	struct kd_task_root_context *root;

	if (managed_grant(binding, false)) {
		root = native_root();
		(void)kd_episode_downgrade_native(root->mutex_resources, root,
			kd_state_current_binding(&root->core), &binding->lock->core.queue,
			KD_OPERATION_RWSEM_DOWNGRADE_WRITE);
		return;
	}
	(void)kd_rw_native_downgrade_write(&binding->lock->core);
}
void kd_linux_rwsem_down_read_non_owner(struct kd_linux_rwsem_binding *binding)
{
	(void)kd_rw_native_read_lock(&binding->lock->core, TASK_UNINTERRUPTIBLE, true);
}
void kd_linux_rwsem_up_read_non_owner(struct kd_linux_rwsem_binding *binding)
{
	(void)kd_rw_native_read_unlock(&binding->lock->core, true);
}

bool kd_linux_rwsem_is_locked(const struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_is_locked(&binding->lock->core);
}
bool kd_linux_rwsem_is_write_locked(const struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_is_write_locked(&binding->lock->core);
}
bool kd_linux_rwsem_is_contended(const struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_is_contended(&binding->lock->core);
}
bool kd_linux_rwsem_is_reader_owned(const struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_is_reader_owned(&binding->lock->core);
}
struct task_struct *kd_linux_rwsem_owner(const struct kd_linux_rwsem_binding *binding)
{
	return kd_rw_native_owner_task(&binding->lock->core);
}

/* Exact normal-ABI addresses never become typed clobber entries by name or
 * learning. Include query/routing helpers: they inspect actual native context.
 */
static const unsigned long native_targets[] = {
	(unsigned long)down_read, (unsigned long)down_read_interruptible,
	(unsigned long)down_read_killable, (unsigned long)down_read_trylock,
	(unsigned long)down_write, (unsigned long)down_write_killable,
	(unsigned long)down_write_trylock, (unsigned long)up_read,
	(unsigned long)up_write, (unsigned long)downgrade_write,
	(unsigned long)down_read_non_owner, (unsigned long)up_read_non_owner,
	(unsigned long)kd_linux_rwsem_down_read,
	(unsigned long)kd_linux_rwsem_down_read_interruptible,
	(unsigned long)kd_linux_rwsem_down_read_killable,
	(unsigned long)kd_linux_rwsem_down_read_trylock,
	(unsigned long)kd_linux_rwsem_down_write,
	(unsigned long)kd_linux_rwsem_down_write_killable,
	(unsigned long)kd_linux_rwsem_down_write_trylock,
	(unsigned long)kd_linux_rwsem_up_read, (unsigned long)kd_linux_rwsem_up_write,
	(unsigned long)kd_linux_rwsem_downgrade_write,
	(unsigned long)kd_linux_rwsem_down_read_non_owner,
	(unsigned long)kd_linux_rwsem_up_read_non_owner,
	(unsigned long)kd_linux_rwsem_is_locked,
	(unsigned long)kd_linux_rwsem_is_write_locked,
	(unsigned long)kd_linux_rwsem_is_contended,
	(unsigned long)kd_linux_rwsem_is_reader_owned,
	(unsigned long)kd_linux_rwsem_owner,
	(unsigned long)kd_linux_rwsem_source_ready,
	(unsigned long)kd_linux_rwsem_source_release,
#if defined(CONFIG_DEBUG_RWSEMS) || defined(CONFIG_DETECT_HUNG_TASK_BLOCKER)
	(unsigned long)rwsem_owner, (unsigned long)is_rwsem_reader_owned,
#endif
};

const unsigned long *kd_linux_rwsem_native_targets(unsigned int *count)
{
	*count = ARRAY_SIZE(native_targets);
	return native_targets;
}
bool kd_linux_rwsem_is_native_target(unsigned long target)
{
	unsigned int index;

	for (index = 0; index < ARRAY_SIZE(native_targets); ++index)
		if (native_targets[index] == target)
			return true;
	return false;
}
