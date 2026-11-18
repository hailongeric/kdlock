// SPDX-License-Identifier: GPL-2.0-only
/* Native task progress without source execution or a drain-wait policy. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "task_progress.h"
#include "native_status.h"
#include "task_state.h"
#include "jit.h"
#include "owner_progress.h"
#include "request_pool.h"
#include "episode.h"

int kd_task_validate_native(struct kd_task_root_context *root,
			    struct kd_execution_binding *expected_native)
{
	if (!root || !expected_native)
		return -EINVAL;
	return kd_task_native_status(root, kd_task_root_context_current(), expected_native);
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
	*pending = root->mutex_fast.held || root->rwsem_fast.lock ||
		   !list_empty(&root->native_grants) || !list_empty(&root->rwsem_reads) ||
		   !list_empty(&root->owners.batches) ||
		   !list_empty(&state->grants) ||
		   !kd_request_pool_empty(pool);
	return 0;
}
