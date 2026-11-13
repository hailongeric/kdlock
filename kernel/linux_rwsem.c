// SPDX-License-Identifier: GPL-2.0-only
/* Generic rebuilt Linux rwsem binding; every selected API uses one KD gate. */
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/rwsem.h>
#include <linux/sched.h>

#include "../include/kd_linux_rwsem.h"
#include "mutex_api.h"
#include "rw_native.h"
#include "rw_local.h"

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

static bool source_root_ready(void)
{
	struct kd_task_root_context *root = native_root();

	return root && !root->source_closing;
}

bool kd_linux_rwsem_source_ready(const struct kd_linux_rwsem_binding *binding)
{
	return binding->source_calls && source_root_ready();
}

static struct kd_source_grant *managed_grant(
		struct kd_rwsem *lock, bool read)
{
	struct kd_task_root_context *root = native_root();
	struct kd_source_grant *grant;
	const void *credit;

	if (!root)
		return NULL;
	grant = kd_state_find_operation_grant(&root->core,
		kd_state_current_binding(&root->core), &lock->core.queue,
		read ? KD_OPERATION_RWSEM_UP_READ : KD_OPERATION_RWSEM_UP_WRITE);
	if (IS_ERR(grant))
		return NULL;
	if (read && grant->mode == KD_GRANT_MODE_READ) {
		/* The current original task retains its own still-held credit across
		 * this snapshot. No other actor may consume an owned read grant.
		 */
		if (kd_rw_last_owned_read(&lock->core, current, &credit) !=
		    KD_RW_READ_MANAGED || credit != grant->read_credit)
			return NULL;
	}
	return grant;
}

static bool fast_read_grant(struct kd_rwsem *lock)
{
	struct kd_task_root_context *root = native_root();
	const void *credit;
	enum kd_rw_read_kind kind;

	if (!root)
		return false;
	kind = kd_rw_last_owned_read(&lock->core, current, &credit);
	return kind == KD_RW_READ_ORDINARY || kind == KD_RW_READ_FAST;
}

bool kd_linux_rwsem_source_release(const struct kd_linux_rwsem_binding *binding,
		bool read)
{
	return (read && fast_read_grant(binding->lock)) ||
		(!read && kd_rw_local_native_writer(&binding->lock->core)) ||
		managed_grant(binding->lock, read) != NULL;
}

/* Reached generic aliases use the current borrowed S_W, not the physical
 * executor's native root. Its source/grant users retain origin and root while
 * this read-only pre-operation decision is made; occupied auxiliary control is
 * expected here. A declined operation keeps its source CALL/cursor unchanged.
 */
bool kd_linux_rwsem_source_operation_ready(struct kd_thread_state *state,
		struct kd_execution_binding *binding, unsigned long target)
{
	struct kd_task_root_context *root;
	struct kd_source_grant *grant;
	struct kd_rwsem *lock;
	const void *credit;
	enum kd_operation_kind operation;

	if (target == (unsigned long)kd_linux_rwsem_down_read_entry_asm)
		operation = KD_OPERATION_RWSEM_DOWN_READ;
	else if (target == (unsigned long)kd_linux_rwsem_up_read_entry_asm)
		operation = KD_OPERATION_RWSEM_UP_READ;
	else if (target == (unsigned long)kd_linux_rwsem_down_write_entry_asm)
		operation = KD_OPERATION_RWSEM_DOWN_WRITE;
	else if (target == (unsigned long)kd_linux_rwsem_up_write_entry_asm)
		operation = KD_OPERATION_RWSEM_UP_WRITE;
	else if (target == (unsigned long)kd_linux_rwsem_downgrade_write_entry_asm)
		operation = KD_OPERATION_RWSEM_DOWNGRADE_WRITE;
	else
		return true;
	if (!state || !kd_state_is_jit_current(state, binding))
		return false;
	root = smp_load_acquire(&state->origin->kd_root_context);
	if (!root || !root->attached || root->task != state->origin ||
	    &root->core != state || !root->mutex_resources ||
	    root->mutex_resources->config.family != KD_LOCK_FAMILY_RWSEM)
		return false;
	if (kd_operation_is_lock(operation))
		return !root->source_closing && list_empty(&root->native_grants);
	lock = (struct kd_rwsem *)state->regs.di;
	if (!lock)
		return false;
	grant = kd_state_find_operation_grant(state, binding, &lock->core.queue,
		operation);
	if (IS_ERR(grant))
		return false;
	if (grant->mode == KD_GRANT_MODE_READ)
		return kd_rw_last_owned_read(&lock->core, state->origin, &credit) ==
			KD_RW_READ_MANAGED && credit == grant->read_credit;
	return true;
}

/* The source macro selects an immutable source-enabled binding before this
 * target. Only original-task assembly executes these C helpers; borrowed source
 * reaches the distinct typed target and uses its explicit node/S_W instead.
 * An unprepared or source-closed acquisition remains native on the same gate.
 */
struct kd_mutex_entry *kd_linux_rwsem_prepare_down_read_current(struct kd_rwsem *lock)
{
	if (source_root_ready())
		return kd_rwsem_prepare_source_current(lock, KD_OPERATION_RWSEM_DOWN_READ,
			(unsigned long)kd_linux_rwsem_down_read_entry_asm);
	(void)kd_rw_native_read_lock(&lock->core, TASK_UNINTERRUPTIBLE, false);
	return NULL;
}

struct kd_mutex_entry *kd_linux_rwsem_prepare_down_write_current(struct kd_rwsem *lock)
{
	if (source_root_ready())
		return kd_rwsem_prepare_source_current(lock, KD_OPERATION_RWSEM_DOWN_WRITE,
			(unsigned long)kd_linux_rwsem_down_write_entry_asm);
	(void)kd_rw_native_write_lock(&lock->core, TASK_UNINTERRUPTIBLE);
	return NULL;
}

/* The explicit cold binding opt-in reaches this integer clobber entry. Legacy
 * bindings retain the callable path; unprepared tasks still use the same native
 * pool and gate with an explicit integer result.
 */
struct kd_source_prepare_result kd_linux_rwsem_prepare_down_write_killable_current(
		struct kd_rwsem *lock)
{
	if (source_root_ready())
		return (struct kd_source_prepare_result) {
			.entry = kd_rwsem_prepare_source_current(lock,
				KD_OPERATION_RWSEM_DOWN_WRITE_KILLABLE,
				(unsigned long)kd_linux_rwsem_down_write_killable_entry_asm),
			.result = 0,
		};
	return (struct kd_source_prepare_result) {
		.entry = NULL,
		.result = (unsigned int)kd_rw_native_write_lock(&lock->core, TASK_KILLABLE),
	};
}

/* Original-task queries use their actual C CALL/RET and return a physical
 * predicate. They create no source request or grant and never lend a stack.
 * A borrowed typed query is serviced by the current node/S_W driver instead.
 */
struct kd_source_prepare_result kd_linux_rwsem_prepare_is_locked_current(struct kd_rwsem *lock)
{
	return (struct kd_source_prepare_result) {
		.entry = NULL, .result = kd_rw_native_is_locked(lock ? &lock->core : NULL),
	};
}

struct kd_source_prepare_result kd_linux_rwsem_prepare_is_write_locked_current(struct kd_rwsem *lock)
{
	return (struct kd_source_prepare_result) {
		.entry = NULL, .result = kd_rw_native_is_write_locked(lock ? &lock->core : NULL),
	};
}

struct kd_mutex_entry *kd_linux_rwsem_prepare_up_read_current(struct kd_rwsem *lock)
{
	if (fast_read_grant(lock) || managed_grant(lock, true))
		return kd_rwsem_prepare_source_current(lock, KD_OPERATION_RWSEM_UP_READ,
			(unsigned long)kd_linux_rwsem_up_read_entry_asm);
	(void)kd_rw_native_read_unlock(&lock->core, false);
	return NULL;
}

struct kd_mutex_entry *kd_linux_rwsem_prepare_up_write_current(struct kd_rwsem *lock)
{
	if (managed_grant(lock, false))
		return kd_rwsem_prepare_source_current(lock, KD_OPERATION_RWSEM_UP_WRITE,
			(unsigned long)kd_linux_rwsem_up_write_entry_asm);
	(void)kd_rw_native_write_unlock(&lock->core);
	return NULL;
}

struct kd_mutex_entry *kd_linux_rwsem_prepare_downgrade_write_current(struct kd_rwsem *lock)
{
	if (managed_grant(lock, false))
		return kd_rwsem_prepare_source_current(lock, KD_OPERATION_RWSEM_DOWNGRADE_WRITE,
			(unsigned long)kd_linux_rwsem_downgrade_write_entry_asm);
	(void)kd_rw_native_downgrade_write(&lock->core);
	return NULL;
}

static int bind_source(struct rw_semaphore *object,
		struct kd_linux_rwsem_binding *binding, struct kd_rwsem *lock,
		bool source_calls, bool killable_source_calls)
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
	binding->killable_source_calls = killable_source_calls;
	smp_store_release(&object->kd_binding, binding);
	return 0;
}

int kd_linux_rwsem_bind(struct rw_semaphore *object,
		struct kd_linux_rwsem_binding *binding, struct kd_rwsem *lock,
		bool source_calls)
{
	return bind_source(object, binding, lock, source_calls, false);
}

int kd_linux_rwsem_bind_killable_source(struct rw_semaphore *object,
		struct kd_linux_rwsem_binding *binding, struct kd_rwsem *lock)
{
	return bind_source(object, binding, lock, true, true);
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

	if (fast_read_grant(binding->lock)) {
		/* Callable release consumes the same latest owned credit. This exact
		 * native unlock needs no capture or generated-call clobber contract.
		 */
		(void)kd_rwsem_prepare_source_current(binding->lock, KD_OPERATION_RWSEM_UP_READ,
			(unsigned long)kd_linux_rwsem_up_read_entry_asm);
		return;
	}
	if (managed_grant(binding->lock, true)) {
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

	if (managed_grant(binding->lock, false)) {
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

	if (managed_grant(binding->lock, false)) {
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
	(unsigned long)kd_linux_rwsem_source_operation_ready,
	(unsigned long)kd_linux_rwsem_prepare_down_read_current,
	(unsigned long)kd_linux_rwsem_prepare_up_read_current,
	(unsigned long)kd_linux_rwsem_prepare_down_write_current,
	(unsigned long)kd_linux_rwsem_prepare_up_write_current,
	(unsigned long)kd_linux_rwsem_prepare_downgrade_write_current,
	(unsigned long)kd_rwsem_prepare_source_current,
	(unsigned long)kd_linux_rwsem_prepare_down_write_killable_current,
	(unsigned long)kd_rwsem_prepare_down_write_killable_current,
	(unsigned long)kd_linux_rwsem_bind_killable_source,
	(unsigned long)kd_linux_rwsem_prepare_is_locked_current,
	(unsigned long)kd_linux_rwsem_prepare_is_write_locked_current,
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
