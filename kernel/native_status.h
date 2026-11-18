/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_NATIVE_STATUS_H
#define KDLOCK_NATIVE_STATUS_H

#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "task_state.h"
#include "episode.h"

/* The entry task owns its native binding while its auxiliary stack is idle.
 * Compare a caller-retained endpoint when supplied. A typed mutex entry can
 * load its own endpoint once after checking that the root is not borrowed.
 */
static __always_inline int kd_task_native_status(struct kd_task_root_context *root,
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

#endif
