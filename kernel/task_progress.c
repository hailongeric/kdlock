// SPDX-License-Identifier: GPL-2.0-only
/* Native task progress without source execution or a drain-wait policy. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "task_progress.h"
#include "task_state.h"
#include "jit.h"
#include "owner_progress.h"
#include "request_pool.h"
#include "episode.h"

/* The entry task owns its native binding while its auxiliary stack is idle.
 * Compare a caller-retained endpoint when supplied. A typed mutex entry can
 * load its own endpoint once after checking that the root is not borrowed.
 */
static inline int native_status(struct kd_task_root_context *root,
				struct kd_task_root_context *attached,
				struct kd_execution_binding *expected)
{
	struct kd_thread_state *state;
	struct kd_execution_binding *binding;
	struct kd_request_pool *pool;

	if (!in_task() || (in_atomic() && !root->owners.atomic_spin) || irqs_disabled() ||
	    READ_ONCE(current->__state) != TASK_RUNNING)
		return -EWOULDBLOCK;
	if (root != attached || !root->attached || root->task != current)
		return -EPERM;
	if (root->aux_entry)
		return -EBUSY;
	state = &root->core;
	binding = smp_load_acquire(&state->binding);
	if (!binding || (expected && binding != expected) ||
	    binding->kind != KD_EXECUTION_NATIVE || binding->state != state ||
	    binding->task != current || state->origin != current)
		return -EPERM;
	if (state->exit_image || state->exit_use || state->exit_holder ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	pool = state->requests;
	if (!pool || pool->state != state || root->owners.task != current ||
	    (root->mutex_resources && root->mutex_resources->pool != pool))
		return -EUCLEAN;
	return 0;
}

int kd_task_validate_native(struct kd_task_root_context *root,
			    struct kd_execution_binding *expected_native)
{
	if (!root || !expected_native)
		return -EINVAL;
	return native_status(root, kd_task_root_context_current(), expected_native);
}

struct kd_task_root_context *kd_task_mutex_fast_root(bool acquire)
{
	struct kd_task_root_context *root = smp_load_acquire(&current->kd_root_context);

	if (!root || root->aux_entry || !root->mutex_resources ||
	    root->mutex_resources->config.family != KD_LOCK_FAMILY_MUTEX ||
	    root->owners.atomic_spin || native_status(root, root, NULL))
		return NULL;
	/* A matching local release remains legal during close or with nested
	 * grants. Only a new top-level acquisition needs an unused fast head.
	 */
	if (acquire && (root->source_closing || root->mutex_fast.lock || root->rwsem_fast.lock ||
			!list_empty(&root->core.grants) || !list_empty(&root->owners.batches) ||
			!list_empty(&root->native_grants)))
		return NULL;
	return root;
}

int kd_task_progress_native(struct kd_task_root_context *root,
			    struct kd_execution_binding *expected_native,
			    bool *pending)
{
	struct kd_thread_state *state;
	struct kd_request_pool *pool;
	bool blocked;
	int result;

	if (!pending)
		return -EINVAL;
	*pending = true;
	result = kd_task_validate_native(root, expected_native);
	if (result)
		return result;
	state = &root->core;
	pool = state->requests;

	/* Each operation ends its own guard before the next component is entered.
	 * A successful final drop/reap may make a containing control reusable;
	 * this helper keeps no node/item/grant pointer across those operations.
	 */
	result = kd_owner_progress_run(&root->owners, &blocked);
	if (result)
		return result;
	if (root->mutex_resources)
		result = kd_episode_collect(root->mutex_resources, expected_native);
	else
		result = kd_jit_collect_grants(state, expected_native);
	if (result)
		return result;
	result = kd_owner_progress_run(&root->owners, &blocked);
	if (result)
		return result;
	kd_request_pool_collect(pool);

	/* Exact memberships only, never an activity estimate or physical wait.
	 * In particular, a still-current native-return slot stays legitimately
	 * LIVE even though atomic task detach can revoke/reclaim it later.
	 */
	*pending = root->mutex_fast.lock || root->rwsem_fast.lock ||
		   !list_empty(&root->native_grants) || !list_empty(&root->rwsem_reads) ||
		   !list_empty(&root->owners.batches) ||
		   !list_empty(&state->grants) ||
		   !kd_request_pool_empty(pool);
	return 0;
}
