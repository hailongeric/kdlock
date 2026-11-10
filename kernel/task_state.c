// SPDX-License-Identifier: GPL-2.0-only
/* Task-owned native-root/core and auxiliary control-stack lifetime anchor. */
#include <linux/atomic.h>
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/sched.h>
#include <linux/sched/task.h>

#include "task_state.h"
#include "request_pool.h"

void kd_task_root_context_init(struct kd_task_root_context *context)
{
	/* Private constructor only; the canonical regs are captured, not cleared. */
	context->task = NULL;
	kd_owner_progress_init(&context->owners, NULL);
	context->mutex_resources = NULL;
	context->mutex_control_bytes = 0;
	context->aux_low = 0;
	context->aux_high = 0;
	context->aux_current = 0;
	context->aux_entry = NULL;
	context->attached = false;
}

struct kd_task_root_context *kd_task_root_context_current(void)
{
	return smp_load_acquire(&current->kd_root_context);
}

struct kd_thread_state *kd_task_state_own(void)
{
	struct kd_task_root_context *context = kd_task_root_context_current();

	/* A pointer calculation never reads the possibly borrowed task's packet. */
	return context ? &context->core : NULL;
}

int kd_task_root_attach(struct kd_task_root_context *context,
		       unsigned long origin_gs, unsigned long aux_low,
		       unsigned long aux_high, unsigned long aux_current,
		       struct kd_request_pool *pool,
		       struct kd_request_slot *slots, unsigned int capacity)
{
	unsigned long header_low = (unsigned long)context;
	unsigned long header_high = header_low + sizeof(*context);
	int result;

	if (!context || !pool || !slots || !capacity || aux_low >= aux_high ||
	    aux_current < aux_low ||
	    aux_current > aux_high || header_high < header_low ||
	    (aux_low < header_high && aux_high > header_low))
		return -EINVAL;
	if (kd_task_root_context_current())
		return -EEXIST;
	/* Private initialized storage cannot be shared/reused by another task. */
	if (context->attached || context->task || context->aux_entry)
		return -EBUSY;
	result = kd_execution_binding_init(&context->initial_native, &context->core,
					   current, context, KD_EXECUTION_NATIVE);
	if (result)
		return result;
	result = kd_state_init(&context->core, current, origin_gs,
			       &context->initial_native);
	if (result)
		return result;
	result = kd_request_pool_init(pool, &context->core, slots, capacity);
	if (result)
		return result;
	context->core.requests = pool;
	kd_owner_progress_init(&context->owners, current);
	get_task_struct(current);
	context->task = current;
	context->aux_low = aux_low;
	context->aux_high = aux_high;
	context->aux_current = aux_current;
	context->attached = true;
	/* Publish initialized header/core before native entry can find it. */
	smp_store_release(&current->kd_root_context, context);
	return 0;
}

void kd_task_root_reset_unpublished(struct task_struct *task)
{
	/* The copied alias owns no parent-context/core/stack reference. */
	WRITE_ONCE(task->kd_root_context, NULL);
}

int kd_task_root_detach(struct kd_task_root_context *context,
		       struct kd_execution_binding *native_binding)
{
	struct kd_thread_state *state;
	struct task_struct *task;

	if (!context || !native_binding)
		return -EINVAL;
	if (kd_task_root_context_current() != context)
		return -ESTALE;
	if (!context->attached || context->task != current)
		return -EPERM;
	if (context->aux_entry || !list_empty(&context->owners.batches))
		return -EBUSY;
	/* Caller has stopped/drained auxiliary and borrowed work before this
	 * first own-state access; neither a cursor nor task identity proves that.
	 */
	state = &context->core;
	if (state->origin != current)
		return -EPERM;
	/* Acquire and compare a retained endpoint before reading its fields. */
	if (kd_state_current_binding(state) != native_binding)
		return -ESTALE;
	if (native_binding->state != state || native_binding->task != current ||
	    native_binding->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	if (state->exit_image || state->exit_use || state->exit_holder ||
	    !list_empty(&state->grants) ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	if (!state->requests)
		return -EUCLEAN;
	kd_request_pool_collect(state->requests);
	/* Final close validates all otherwise finished requests and revokes the
	 * exact native binding under the pool metadata guard. No fallible cleanup
	 * remains after that revocation. Caller already drained every actor.
	 */
	{
		int result = kd_request_pool_detach(state->requests, native_binding);

		if (result)
			return result;
	}
	/* All escaped lookup/binding/control users already drained. The single
	 * task pointer, not a registry/borrowed-state field, is revoked here.
	 */
	smp_store_release(&current->kd_root_context, NULL);
	task = context->task;
	context->task = NULL;
	context->attached = false;
	context->mutex_resources = NULL;
	context->mutex_control_bytes = 0;
	state->requests = NULL;
	/* No context/core access follows the final retained task-key release. */
	put_task_struct(task);
	return 0;
}
