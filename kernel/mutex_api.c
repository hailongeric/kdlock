// SPDX-License-Identifier: GPL-2.0-only
/* Ordinary native entry and the common serial source-operation driver. */
#include <linux/bug.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/kernel.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "mutex_api.h"
#include "native_entry.h"
#include "task_progress.h"

int kd_mutex_bind_current(struct kd_episode_resources *resources,
			 unsigned long required_control_bytes)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_execution_binding *native;

	if (!root || !root->attached || root->task != current || !resources ||
	    required_control_bytes < sizeof(unsigned long))
		return -EINVAL;
	if (root->aux_entry || root->mutex_resources)
		return -EBUSY;
	if (resources->pool != root->core.requests ||
	    !kd_request_pool_empty(root->core.requests))
		return -EINVAL;
	/* Setup owns the original task/core before any source publication. */
	native = kd_state_current_binding(&root->core);
	if (!kd_state_is_current(&root->core, native) ||
	    native->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	root->mutex_control_bytes = required_control_bytes;
	root->mutex_resources = resources;
	root->owners.atomic_spin = resources->config.atomic_spin;
	return 0;
}

enum kd_operation_kind kd_mutex_resolve_entry_operation(void *context,
						unsigned long target)
{
	(void)context;
	if (target == (unsigned long)kd_mutex_lock_entry_asm)
		return KD_OPERATION_MUTEX_LOCK;
	if (target == (unsigned long)kd_mutex_unlock_entry_asm)
		return KD_OPERATION_MUTEX_UNLOCK;
	return KD_OPERATION_NONE;
}

enum kd_operation_kind kd_spin_resolve_entry_operation(unsigned long target)
{
	if (target == (unsigned long)kd_spin_lock_entry_asm)
		return KD_OPERATION_SPIN_LOCK;
	if (target == (unsigned long)kd_spin_unlock_entry_asm)
		return KD_OPERATION_SPIN_UNLOCK;
	return KD_OPERATION_NONE;
}

struct rw_entry {
	enum kd_operation_kind kind;
	unsigned long target;
};

static const struct rw_entry rw_entries[] = {
	{ KD_OPERATION_RWSEM_DOWN_READ, (unsigned long)kd_rwsem_down_read_entry_asm },
	{ KD_OPERATION_RWSEM_UP_READ, (unsigned long)kd_rwsem_up_read_entry_asm },
	{ KD_OPERATION_RWSEM_DOWN_WRITE, (unsigned long)kd_rwsem_down_write_entry_asm },
	{ KD_OPERATION_RWSEM_UP_WRITE, (unsigned long)kd_rwsem_up_write_entry_asm },
	{ KD_OPERATION_RWSEM_DOWNGRADE_WRITE, (unsigned long)kd_rwsem_downgrade_write_entry_asm },
	{ KD_OPERATION_RWSEM_DOWN_READ, (unsigned long)kd_linux_rwsem_down_read_entry_asm },
	{ KD_OPERATION_RWSEM_UP_READ, (unsigned long)kd_linux_rwsem_up_read_entry_asm },
	{ KD_OPERATION_RWSEM_DOWN_WRITE, (unsigned long)kd_linux_rwsem_down_write_entry_asm },
	{ KD_OPERATION_RWSEM_UP_WRITE, (unsigned long)kd_linux_rwsem_up_write_entry_asm },
	{ KD_OPERATION_RWSEM_DOWNGRADE_WRITE, (unsigned long)kd_linux_rwsem_downgrade_write_entry_asm },
	{ KD_OPERATION_RWSEM_DOWN_WRITE_KILLABLE, (unsigned long)kd_rwsem_down_write_killable_entry_asm },
	{ KD_OPERATION_RWSEM_DOWN_WRITE_KILLABLE, (unsigned long)kd_linux_rwsem_down_write_killable_entry_asm },
	{ KD_OPERATION_RWSEM_IS_LOCKED, (unsigned long)kd_linux_rwsem_is_locked_entry_asm },
	{ KD_OPERATION_RWSEM_IS_WRITE_LOCKED, (unsigned long)kd_linux_rwsem_is_write_locked_entry_asm },
	{ KD_OPERATION_RWLOCK_READ_LOCK, (unsigned long)kd_rwlock_read_lock_entry_asm },
	{ KD_OPERATION_RWLOCK_READ_UNLOCK, (unsigned long)kd_rwlock_read_unlock_entry_asm },
	{ KD_OPERATION_RWLOCK_WRITE_LOCK, (unsigned long)kd_rwlock_write_lock_entry_asm },
	{ KD_OPERATION_RWLOCK_WRITE_UNLOCK, (unsigned long)kd_rwlock_write_unlock_entry_asm },
};

enum kd_operation_kind kd_rw_resolve_entry_operation(unsigned long target)
{
	unsigned int index;

	for (index = 0; index < ARRAY_SIZE(rw_entries); ++index)
		if (rw_entries[index].target == target)
			return rw_entries[index].kind;
	return KD_OPERATION_NONE;
}

static enum kd_operation_kind resolve_source_target(unsigned long target)
{
	enum kd_operation_kind operation = kd_mutex_resolve_entry_operation(NULL, target);

	if (operation == KD_OPERATION_NONE)
		operation = kd_spin_resolve_entry_operation(target);
	if (operation == KD_OPERATION_NONE)
		operation = kd_rw_resolve_entry_operation(target);
	return operation;
}

void kd_spin_init(struct kd_spinlock *lock)
{
	kd_mutex_init(&lock->queue);
}

static void run_native(struct kd_mutex_entry *entry, struct kd_mutex *lock,
		       unsigned long source_sp, unsigned long continuation_ip,
		       unsigned long source_bp)
{
	struct kd_episode_frame *frame = entry->context;
	struct kd_execution_binding *native;
	unsigned long api_target;
	enum kd_mutex_outcome outcome;
	int result;

	/* The original native endpoint was retained by the source controller
	 * before this exact prepared entry switched to its own auxiliary stack.
	 */
	native = kd_state_current_binding(frame->slot->pool->state);
	BUG_ON(!kd_operation_is_lock(frame->operation));
	api_target = frame->source_target;
	BUG_ON(!api_target || resolve_source_target(api_target) != frame->operation);
	result = kd_episode_acquire_root(frame, native, lock, source_sp,
		continuation_ip, source_bp, api_target, &outcome);
	BUG_ON(result || outcome != KD_MUTEX_PROXY_ORIGIN_SUFFIX);
	/* Typed terminal propagation, not a snapshot of a possibly advanced
	 * packet, identifies the immutable native destination for this root.
	 */
	native = kd_episode_native_binding(frame);
	result = kd_episode_root_done(frame);
	BUG_ON(result);
	kd_mutex_resume_entry(entry, native, kd_episode_native_done, frame);
}

static bool mutex_fast_eligible(struct kd_task_root_context *root,
				enum kd_operation_kind operation)
{
	struct kd_thread_state *state = &root->core;

	/* Called only after the ordinary native-root and source-target checks.
	 * Finished request storage may still retain the current native endpoint;
	 * it stays retained until normal collection/detach, without per-call use.
	 */
	return operation == KD_OPERATION_MUTEX_LOCK && !root->mutex_fast.lock &&
		in_task() && !irqs_disabled() && !in_atomic() &&
		READ_ONCE(current->__state) == TASK_RUNNING &&
		list_empty(&state->grants) && list_empty(&root->owners.batches) &&
		list_empty(&root->native_grants) &&
		!state->exit_image && !state->exit_use && !state->exit_holder &&
		(state->operation.phase == KD_OPERATION_IDLE ||
		 state->operation.phase == KD_OPERATION_RESUMABLE);
}

static struct kd_mutex_entry *prepare_current(struct kd_mutex *lock,
					      enum kd_operation_kind operation,
					      unsigned long api_target)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_execution_binding *native;
	struct kd_episode_frame *frame;
	bool atomic_context = kd_operation_is_atomic(operation);
	bool pending;
	int result;

	/* This bootstrap is native source only. A borrowed execution reaches a
	 * typed operation boundary and the explicit node/frame driver instead.
	 * A waiting origin's live aux_entry rejects reentry before own-core reads.
	 */
	BUG_ON(!root || !root->attached || root->task != current || !lock ||
	       root->aux_entry || !root->mutex_resources ||
	       (kd_operation_is_lock(operation) && root->source_closing) ||
	       kd_operation_family(operation) != root->mutex_resources->config.family ||
	       root->owners.atomic_spin != atomic_context ||
	       !api_target || resolve_source_target(api_target) != operation);
	if (atomic_context) {
		BUG_ON(!in_task() || irqs_disabled() ||
		       preempt_count() != root->native_spin_depth * PREEMPT_OFFSET);
		if (kd_operation_is_lock(operation)) {
			BUG_ON(root->native_spin_depth >= PREEMPT_MASK / PREEMPT_OFFSET);
			preempt_disable();
		} else {
			BUG_ON(!root->native_spin_depth);
		}
	}
	native = kd_state_current_binding(&root->core);
	BUG_ON(!kd_state_is_current(&root->core, native) ||
	       native->kind != KD_EXECUTION_NATIVE);
	if (operation == KD_OPERATION_MUTEX_UNLOCK && root->mutex_fast.lock == lock) {
		result = kd_task_validate_native(root, native);
		BUG_ON(result);
		kd_mutex_fast_unlock(&root->mutex_fast);
		return NULL;
	}
	if (mutex_fast_eligible(root, operation)) {
		result = kd_task_validate_native(root, native);
		BUG_ON(result);
		if (kd_mutex_fast_trylock(lock, &root->mutex_fast))
			return NULL;
	}
	result = kd_task_progress_native(root, native, &pending);
	BUG_ON(result);
	if (kd_operation_is_unlock(operation)) {
		result = kd_episode_unlock_native(root->mutex_resources,
						  root, native, lock, operation);
		BUG_ON(result);
		if (atomic_context) {
			root->native_spin_depth--;
			preempt_enable();
		}
		return NULL;
	}
	if (kd_operation_is_mode_change(operation)) {
		result = kd_episode_downgrade_native(root->mutex_resources, root, native,
						   lock, operation);
		BUG_ON(result);
		return NULL;
	}
	result = kd_episode_prepare_root(root->mutex_resources, native,
					 operation, &frame);
	BUG_ON(result);
	frame->source_target = api_target;
	result = kd_mutex_prepare_entry(&frame->slot->entry, native, run_native,
					frame, root->mutex_control_bytes);
	BUG_ON(result);
	return &frame->slot->entry;
}

struct kd_mutex_entry *kd_mutex_prepare_lock_current(struct kd_mutex *lock)
{
	return prepare_current(lock, KD_OPERATION_MUTEX_LOCK,
		(unsigned long)kd_mutex_lock_entry_asm);
}

struct kd_mutex_entry *kd_mutex_prepare_unlock_current(struct kd_mutex *lock)
{
	return prepare_current(lock, KD_OPERATION_MUTEX_UNLOCK,
		(unsigned long)kd_mutex_unlock_entry_asm);
}

struct kd_mutex_entry *kd_spin_prepare_lock_current(struct kd_spinlock *lock)
{
	return prepare_current(lock ? &lock->queue : NULL, KD_OPERATION_SPIN_LOCK,
		(unsigned long)kd_spin_lock_entry_asm);
}

struct kd_mutex_entry *kd_spin_prepare_unlock_current(struct kd_spinlock *lock)
{
	return prepare_current(lock ? &lock->queue : NULL, KD_OPERATION_SPIN_UNLOCK,
		(unsigned long)kd_spin_unlock_entry_asm);
}

struct kd_mutex_entry *kd_rwsem_prepare_source_current(struct kd_rwsem *lock,
		enum kd_operation_kind operation, unsigned long api_target)
{
	BUG_ON(kd_operation_family(operation) != KD_LOCK_FAMILY_RWSEM);
	return prepare_current(lock ? &lock->core.queue : NULL, operation, api_target);
}

struct kd_mutex_entry *kd_rwsem_prepare_down_read_current(struct kd_rwsem *lock)
{
	return prepare_current(lock ? &lock->core.queue : NULL, KD_OPERATION_RWSEM_DOWN_READ,
		(unsigned long)kd_rwsem_down_read_entry_asm);
}

struct kd_mutex_entry *kd_rwsem_prepare_up_read_current(struct kd_rwsem *lock)
{
	return prepare_current(lock ? &lock->core.queue : NULL, KD_OPERATION_RWSEM_UP_READ,
		(unsigned long)kd_rwsem_up_read_entry_asm);
}

struct kd_mutex_entry *kd_rwsem_prepare_down_write_current(struct kd_rwsem *lock)
{
	return prepare_current(lock ? &lock->core.queue : NULL, KD_OPERATION_RWSEM_DOWN_WRITE,
		(unsigned long)kd_rwsem_down_write_entry_asm);
}

struct kd_source_prepare_result kd_rwsem_prepare_down_write_killable_current(
		struct kd_rwsem *lock)
{
	return (struct kd_source_prepare_result) {
		.entry = prepare_current(lock ? &lock->core.queue : NULL,
			KD_OPERATION_RWSEM_DOWN_WRITE_KILLABLE,
			(unsigned long)kd_rwsem_down_write_killable_entry_asm),
		.result = 0,
	};
}

struct kd_mutex_entry *kd_rwsem_prepare_up_write_current(struct kd_rwsem *lock)
{
	return prepare_current(lock ? &lock->core.queue : NULL, KD_OPERATION_RWSEM_UP_WRITE,
		(unsigned long)kd_rwsem_up_write_entry_asm);
}

struct kd_mutex_entry *kd_rwsem_prepare_downgrade_write_current(struct kd_rwsem *lock)
{
	return prepare_current(lock ? &lock->core.queue : NULL, KD_OPERATION_RWSEM_DOWNGRADE_WRITE,
		(unsigned long)kd_rwsem_downgrade_write_entry_asm);
}

struct kd_mutex_entry *kd_rwlock_prepare_read_lock_current(struct kd_rwlock *lock)
{
	return prepare_current(lock ? &lock->core.queue : NULL, KD_OPERATION_RWLOCK_READ_LOCK,
		(unsigned long)kd_rwlock_read_lock_entry_asm);
}

struct kd_mutex_entry *kd_rwlock_prepare_read_unlock_current(struct kd_rwlock *lock)
{
	return prepare_current(lock ? &lock->core.queue : NULL, KD_OPERATION_RWLOCK_READ_UNLOCK,
		(unsigned long)kd_rwlock_read_unlock_entry_asm);
}

struct kd_mutex_entry *kd_rwlock_prepare_write_lock_current(struct kd_rwlock *lock)
{
	return prepare_current(lock ? &lock->core.queue : NULL, KD_OPERATION_RWLOCK_WRITE_LOCK,
		(unsigned long)kd_rwlock_write_lock_entry_asm);
}

struct kd_mutex_entry *kd_rwlock_prepare_write_unlock_current(struct kd_rwlock *lock)
{
	return prepare_current(lock ? &lock->core.queue : NULL, KD_OPERATION_RWLOCK_WRITE_UNLOCK,
		(unsigned long)kd_rwlock_write_unlock_entry_asm);
}
