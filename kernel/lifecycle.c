// SPDX-License-Identifier: GPL-2.0-only
/* Managed native-task construction and exact fork/exit lifetime integration. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <asm/page.h>

#include "lifecycle.h"
#include "task_progress.h"

static bool native_context(void)
{
	return in_task() && !in_atomic() && !irqs_disabled() &&
		READ_ONCE(current->__state) == TASK_RUNNING;
}

int kd_task_lifecycle_context_init(struct kd_task_lifecycle_context *context,
		const struct kd_episode_config *config, unsigned int capacity,
		size_t auxiliary_bytes, unsigned long required_control_bytes,
		void *native_context, int (*native_begin)(void *, void **),
		kd_task_native_release_fn native_release)
{
	if (!context || !config || config->stack || !config->image_slot ||
	    !config->feedback || !config->resolve || !config->classify_target ||
	    !config->report || !capacity || !auxiliary_bytes ||
	    (auxiliary_bytes & (PAGE_SIZE - 1)) ||
	    required_control_bytes < sizeof(unsigned long) ||
	    required_control_bytes > auxiliary_bytes || !native_context ||
	    !native_begin || !native_release)
		return -EINVAL;
	/* Small immutable configuration only; no original source state is copied. */
	context->config = *config;
	context->capacity = capacity;
	context->auxiliary_bytes = auxiliary_bytes;
	context->required_control_bytes = required_control_bytes;
	context->native_context = native_context;
	context->native_begin = native_begin;
	context->native_release = native_release;
	return 0;
}

static int start_task(const struct kd_task_lifecycle_context *context,
		struct task_struct *child, unsigned long origin_gs,
		struct kd_task_storage **storage)
{
	struct kd_task_storage_args args;
	struct kd_task_root_context *root;
	void *lease = NULL;
	int result;

	if (!context || !storage)
		return -EINVAL;
	*storage = NULL;
	result = context->native_begin(context->native_context, &lease);
	if (result)
		return result;
	if (!lease)
		return -EUCLEAN;
	args = (struct kd_task_storage_args) {
		.capacity = context->capacity,
		.auxiliary_bytes = context->auxiliary_bytes,
		.required_control_bytes = context->required_control_bytes,
		.origin_gs = origin_gs,
		.config = &context->config,
		.native_lease = lease,
		.native_release = context->native_release,
	};
	result = child ? kd_task_storage_prepare_unpublished(&args, child, storage) :
		kd_task_storage_start_current(&args, storage);
	if (!*storage) {
		context->native_release(lease);
		return result;
	}
	root = kd_task_storage_root(*storage);
	root->lifecycle = context;
	/* Retained failed setup never admits source or a managed descendant. */
	root->source_closing = result != 0;
	return result;
}

int kd_task_lifecycle_start_current(const struct kd_task_lifecycle_context *context,
		unsigned long origin_gs, struct kd_task_storage **storage)
{
	if (!storage)
		return -EINVAL;
	*storage = NULL;
	if (!native_context())
		return -EWOULDBLOCK;
	return start_task(context, NULL, origin_gs, storage);
}

int kd_task_lifecycle_prepare_unpublished(struct task_struct *child)
{
	struct kd_task_root_context *parent;
	struct kd_task_storage *storage;
	struct kd_execution_binding *native;

	if (!child || child == current)
		return -EINVAL;
	/* A dup alias acquired no core/storage/provider reference. */
	kd_task_root_reset_unpublished(child);
	parent = kd_task_root_context_current();
	if (!parent || !parent->lifecycle)
		return 0;
	if (!native_context() || !parent->attached || parent->task != current ||
	    parent->aux_entry || parent->source_closing)
		return -EPERM;
	native = kd_state_current_binding(&parent->core);
	if (!kd_state_is_current(&parent->core, native) ||
	    native->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	/* No child source state exists before its first genuine native capture. */
	return start_task(parent->lifecycle, child, 0, &storage);
}

int kd_task_lifecycle_abort_unpublished(struct task_struct *child)
{
	struct kd_task_root_context *root;

	if (!child || child == current)
		return -EINVAL;
	root = smp_load_acquire(&child->kd_root_context);
	if (!root)
		return 0;
	if (!root->lifecycle || !root->storage || root->task != child)
		return -EUCLEAN;
	return kd_task_storage_abort_unpublished(root->storage, child);
}

int kd_task_lifecycle_exit_current(void)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_execution_binding *native;
	struct kd_task_storage *storage;
	struct kd_source_grant *grant;
	bool pending;
	int result;

	if (!root || !root->lifecycle)
		return 0;
	if (!native_context() || !root->attached || root->task != current ||
	    root->aux_entry || !root->storage)
		return -EPERM;
	/* Current native ownership and the pool's current-endpoint pin retain this
	 * endpoint; an arbitrary foreign lookup would provide no such proof.
	 */
	native = kd_state_current_binding(&root->core);
	if (!kd_state_is_current(&root->core, native) ||
	    native->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	root->source_closing = true;
	if (root->core.exit_image || root->core.exit_use || root->core.exit_holder ||
	    (root->core.operation.phase != KD_OPERATION_IDLE &&
	     root->core.operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	list_for_each_entry(grant, &root->core.grants, state_link)
		if (grant->logical_open)
			return -EDEADLK;
	storage = root->storage;
	for (;;) {
		/* Only metadata runs here. Source remains stopped/closed, so exact
		 * users can finish but no new actor or native endpoint can appear.
		 */
		result = kd_task_progress_native(root, native, &pending);
		if (result)
			return result;
		if (!list_empty(&root->owners.batches) || !list_empty(&root->core.grants)) {
			result = -EBUSY;
		} else {
			result = kd_request_pool_can_detach(root->core.requests, native);
			if (!result) {
				/* Exact internal drain plus the managed no-untracked-observer
				 * contract establish final-use proof before freeing storage.
				 */
				result = kd_task_storage_stop_current(storage, native, &pending);
				if (!result)
					return 0;
			}
		}
		if (result != -EBUSY && result != -EAGAIN)
			return result;
		/* pending may remain true solely for the current native slot. */
		cond_resched();
	}
}
