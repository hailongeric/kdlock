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
	if (!root || !expected_native)
		return -EINVAL;
	if (!in_task() || in_atomic() || irqs_disabled() ||
	    READ_ONCE(current->__state) != TASK_RUNNING)
		return -EWOULDBLOCK;
	/* Reject an own-root auxiliary/borrowed role before any own-core read. */
	if (kd_task_root_context_current() != root || !root->attached ||
	    root->task != current)
		return -EPERM;
	if (root->aux_entry)
		return -EBUSY;
	state = &root->core;
	/* expected_native is caller-retained, never an arbitrary sampled pointer. */
	if (!kd_state_is_current(state, expected_native) ||
	    expected_native->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	if (state->exit_image || state->exit_use || state->exit_holder ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	pool = state->requests;
	if (!pool || pool->state != state || root->owners.task != current ||
	    (root->mutex_resources && root->mutex_resources->pool != pool))
		return -EUCLEAN;

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
	*pending = !list_empty(&root->owners.batches) ||
		   !list_empty(&state->grants) ||
		   !kd_request_pool_empty(pool);
	return 0;
}
