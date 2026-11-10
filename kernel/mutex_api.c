// SPDX-License-Identifier: GPL-2.0-only
/* Ordinary native entry and the common serial source-operation driver. */
#include <linux/bug.h>
#include <linux/errno.h>
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

static void run_native(struct kd_mutex_entry *entry, struct kd_mutex *lock,
		       unsigned long source_sp, unsigned long continuation_ip,
		       unsigned long source_bp)
{
	struct kd_episode_frame *frame = entry->context;
	struct kd_execution_binding *native;
	enum kd_mutex_outcome outcome;
	int result;

	/* The original native endpoint was retained by the source controller
	 * before this exact prepared entry switched to its own auxiliary stack.
	 */
	native = kd_state_current_binding(frame->slot->pool->state);
	BUG_ON(frame->operation != KD_OPERATION_MUTEX_LOCK);
	result = kd_episode_acquire_root(frame, native, lock, source_sp,
		continuation_ip, source_bp,
		(unsigned long)kd_mutex_lock_entry_asm, &outcome);
	BUG_ON(result || outcome != KD_MUTEX_PROXY_ORIGIN_SUFFIX);
	/* Typed terminal propagation, not a snapshot of a possibly advanced
	 * packet, identifies the immutable native destination for this root.
	 */
	native = kd_episode_native_binding(frame);
	result = kd_episode_root_done(frame);
	BUG_ON(result);
	kd_mutex_resume_entry(entry, native, kd_episode_native_done, frame);
}

static struct kd_mutex_entry *prepare_current(struct kd_mutex *lock,
					      enum kd_operation_kind operation)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_execution_binding *native;
	struct kd_episode_frame *frame;
	bool pending;
	int result;

	/* This bootstrap is native source only. A borrowed execution reaches a
	 * typed operation boundary and the explicit node/frame driver instead.
	 * A waiting origin's live aux_entry rejects reentry before own-core reads.
	 */
	BUG_ON(!root || !root->attached || root->task != current || !lock ||
	       root->aux_entry || !root->mutex_resources);
	native = kd_state_current_binding(&root->core);
	BUG_ON(!kd_state_is_current(&root->core, native) ||
	       native->kind != KD_EXECUTION_NATIVE);
	result = kd_task_progress_native(root, native, &pending);
	BUG_ON(result);
	if (operation == KD_OPERATION_MUTEX_UNLOCK) {
		result = kd_episode_unlock_native(root->mutex_resources,
						  root, native, lock);
		BUG_ON(result);
		return NULL;
	}
	result = kd_episode_prepare_root(root->mutex_resources, native,
					 operation, &frame);
	BUG_ON(result);
	result = kd_mutex_prepare_entry(&frame->slot->entry, native, run_native,
					frame, root->mutex_control_bytes);
	BUG_ON(result);
	return &frame->slot->entry;
}

struct kd_mutex_entry *kd_mutex_prepare_lock_current(struct kd_mutex *lock)
{
	return prepare_current(lock, KD_OPERATION_MUTEX_LOCK);
}

struct kd_mutex_entry *kd_mutex_prepare_unlock_current(struct kd_mutex *lock)
{
	return prepare_current(lock, KD_OPERATION_MUTEX_UNLOCK);
}
