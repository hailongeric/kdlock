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

int kd_task_storage_start_current(const struct kd_task_storage_args *args,
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
	if (!args)
		return -EINVAL;
	input = *args;
	if (!native_context())
		return -EWOULDBLOCK;
	if (kd_task_root_context_current())
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
	result = kd_source_stack_acquire_current(&storage->source);
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
	result = kd_task_setup_current(&setup);
	if (result) {
		/* Setup reports a failed post-attach unwind by leaving the exact
		 * root attached. Do not free it or release its native provider hold.
		 */
		if (storage->root.attached ||
		    kd_task_root_context_current() == &storage->root) {
			*out = storage;
			return result;
		}
		goto fail;
	}
	*out = storage;
	return 0;
fail:
	free_private(storage);
	return result;
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
