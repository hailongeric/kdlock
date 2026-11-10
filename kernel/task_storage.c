// SPDX-License-Identifier: GPL-2.0-only
/* Cold task provisioning and exact final storage release around native source. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/overflow.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <asm/page.h>

#include "task_storage.h"
#include "task_setup.h"
#include "source_stack.h"

struct kd_task_storage {
	struct kd_task_root_context root;
	struct kd_request_pool pool;
	struct kd_episode_resources resources;
	struct kd_source_stack source;
	struct kd_request_slot *slots;
	struct kd_episode_frame *frames;
	void *auxiliary;
	void *native_lease;
	kd_task_native_release_fn native_release;
	bool stack_held;
};

static bool native_context(void)
{
	return in_task() && !in_atomic() && !irqs_disabled() &&
		READ_ONCE(current->__state) == TASK_RUNNING;
}

/* Private storage with no published root or remaining observer. No native lease
 * is released here: NULL-output allocation/setup failure leaves it with caller.
 */
static void free_private(struct kd_task_storage *storage)
{
	if (storage->stack_held)
		kd_source_stack_release(&storage->source);
	vfree(storage->auxiliary);
	kvfree(storage->frames);
	kvfree(storage->slots);
	kfree(storage);
}

static int start_task(const struct kd_task_storage_args *args,
		     struct task_struct *task, bool unpublished,
		     struct kd_task_storage **out)
{
	struct kd_task_storage_args input;
	struct kd_episode_config config;
	struct kd_task_setup_args setup;
	struct kd_task_storage *storage;
	unsigned long auxiliary_low, auxiliary_high;
	size_t checked_bytes;
	int result;

	if (!out)
		return -EINVAL;
	*out = NULL;
	if (!args || !task || (unpublished && task == current))
		return -EINVAL;
	input = *args;
	if (!native_context())
		return -EWOULDBLOCK;
	if (smp_load_acquire(&task->kd_root_context))
		return -EEXIST;
	if (!input.capacity || !input.auxiliary_bytes ||
	    (input.auxiliary_bytes & (PAGE_SIZE - 1)) ||
	    input.required_control_bytes < sizeof(unsigned long) ||
	    input.required_control_bytes > input.auxiliary_bytes ||
	    !input.config || !input.native_lease || !input.native_release)
		return -EINVAL;
	config = *input.config;
	if (config.stack)
		return -EINVAL;
	if (check_mul_overflow((size_t)input.capacity,
			      sizeof(*storage->slots), &checked_bytes) ||
	    check_mul_overflow((size_t)input.capacity,
			      sizeof(*storage->frames), &checked_bytes))
		return -EOVERFLOW;

	storage = kmalloc(sizeof(*storage), GFP_KERNEL);
	if (!storage)
		return -ENOMEM;
	/* Initialize metadata only. The one canonical packet is never cleared. */
	kd_task_root_context_init(&storage->root);
	storage->slots = NULL;
	storage->frames = NULL;
	storage->auxiliary = NULL;
	storage->native_lease = input.native_lease;
	storage->native_release = input.native_release;
	storage->stack_held = false;
	storage->slots = kvmalloc_array(input.capacity, sizeof(*storage->slots), GFP_KERNEL);
	storage->frames = kvmalloc_array(input.capacity, sizeof(*storage->frames), GFP_KERNEL);
	storage->auxiliary = vmalloc(input.auxiliary_bytes);
	if (!storage->slots || !storage->frames || !storage->auxiliary) {
		result = -ENOMEM;
		goto fail;
	}
	auxiliary_low = (unsigned long)storage->auxiliary;
	if (check_add_overflow(auxiliary_low, (unsigned long)input.auxiliary_bytes,
			       &auxiliary_high)) {
		result = -EOVERFLOW;
		goto fail;
	}
	result = unpublished ? kd_source_stack_acquire_unpublished(&storage->source, task) :
		kd_source_stack_acquire_current(&storage->source);
	if (result)
		goto fail;
	storage->stack_held = true;
	config.stack = &storage->source.ops;
	setup.root = &storage->root;
	setup.pool = &storage->pool;
	setup.slots = storage->slots;
	setup.resources = &storage->resources;
	setup.frames = storage->frames;
	setup.capacity = input.capacity;
	setup.origin_gs = input.origin_gs;
	setup.aux_low = auxiliary_low;
	setup.aux_high = auxiliary_high;
	setup.aux_current = auxiliary_high;
	setup.required_control_bytes = input.required_control_bytes;
	setup.config = &config;
	if (!unpublished) {
		result = kd_task_setup_current(&setup);
	} else {
		/* All backing is freshly allocated, parent-owned and outside both
		 * stacks. The inherited immutable provider configuration was already
		 * admitted by the managed parent and remains independently retained.
		 */
		result = kd_task_root_attach_unpublished(&storage->root, task,
			input.origin_gs, auxiliary_low, auxiliary_high, auxiliary_high,
			&storage->pool, storage->slots, input.capacity);
		if (!result) {
			result = kd_episode_resources_init(&storage->resources, &storage->pool,
				storage->frames, input.capacity, &config);
			if (!result) {
				storage->root.mutex_resources = &storage->resources;
				storage->root.mutex_control_bytes = input.required_control_bytes;
			} else {
				int unwind = kd_task_root_detach_unpublished(&storage->root, task);

				if (unwind)
					result = unwind;
			}
		}
	}
	if (result) {
		/* Setup reports a failed post-attach unwind by leaving the exact
		 * root attached. Do not free it or release its native provider hold.
		 */
		if (storage->root.attached ||
		    smp_load_acquire(&task->kd_root_context) == &storage->root) {
			storage->root.storage = storage;
			*out = storage;
			return result;
		}
		goto fail;
	}
	storage->root.storage = storage;
	*out = storage;
	return 0;
fail:
	free_private(storage);
	return result;
}

int kd_task_storage_start_current(const struct kd_task_storage_args *args,
				 struct kd_task_storage **out)
{
	return start_task(args, current, false, out);
}

int kd_task_storage_prepare_unpublished(const struct kd_task_storage_args *args,
		struct task_struct *child, struct kd_task_storage **out)
{
	return start_task(args, child, true, out);
}

int kd_task_storage_abort_unpublished(struct kd_task_storage *storage,
				      struct task_struct *child)
{
	kd_task_native_release_fn release;
	void *lease;
	int result;

	if (!storage || !child || child == current || !native_context())
		return -EINVAL;
	release = storage->native_release;
	lease = storage->native_lease;
	result = kd_task_root_detach_unpublished(&storage->root, child);
	if (result)
		return result;
	free_private(storage);
	release(lease);
	return 0;
}

struct kd_task_root_context *kd_task_storage_root(struct kd_task_storage *storage)
{
	return storage ? &storage->root : NULL;
}

int kd_task_storage_stop_current(struct kd_task_storage *storage,
		struct kd_execution_binding *expected_native, bool *pending)
{
	kd_task_native_release_fn release;
	void *lease;
	int result;

	if (!storage || !expected_native || !pending)
		return -EINVAL;
	if (!native_context())
		return -EWOULDBLOCK;
	if (kd_task_root_context_current() != &storage->root ||
	    !storage->root.attached || storage->root.task != current)
		return -EPERM;
	/* Cache only independent finalizer inputs before detach can revoke and
	 * reclaim the slot containing expected_native. Never read it afterward.
	 */
	release = storage->native_release;
	lease = storage->native_lease;
	result = kd_task_teardown_current(&storage->root, expected_native, pending);
	if (result)
		return result;
	free_private(storage);
	/* All storage/stack accesses finished; native/provider lease is last. */
	release(lease);
	return 0;
}
