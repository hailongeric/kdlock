// SPDX-License-Identifier: GPL-2.0-only
/* Current-task composition over explicit caller-owned persistent backing. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/overflow.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/sched/task_stack.h>
#include <asm/page.h>

#include "task_setup.h"
#include "mutex_api.h"
#include "task_progress.h"

struct setup_range {
	unsigned long low;
	unsigned long high;
};

enum setup_object {
	SETUP_ROOT,
	SETUP_POOL,
	SETUP_SLOTS,
	SETUP_RESOURCES,
	SETUP_FRAMES,
	SETUP_IMAGE_SLOT,
	SETUP_STACK_OPS,
	SETUP_FEEDBACK_POOL,
	SETUP_FEEDBACK_RECORDS,
	SETUP_OBJECTS,
};

static int object_range(struct setup_range *range, const void *object,
			size_t bytes, unsigned long alignment)
{
	unsigned long low = (unsigned long)object;

	if (!object || !bytes || low % alignment)
		return -EINVAL;
	if (check_add_overflow(low, (unsigned long)bytes, &range->high))
		return -EOVERFLOW;
	range->low = low;
	return 0;
}

static bool overlaps(const struct setup_range *first,
		     const struct setup_range *second)
{
	return first->low < second->high && second->low < first->high;
}

static int validate(const struct kd_task_setup_args *args,
		    const struct kd_episode_config *config,
		    const struct setup_range *input,
		    const struct setup_range *config_input)
{
	struct setup_range ranges[SETUP_OBJECTS];
	struct setup_range source, auxiliary;
	unsigned long source_sp;
	size_t slot_bytes, frame_bytes, feedback_bytes;
	unsigned int index, other;
	int result;

	if (!args->capacity || args->aux_low >= args->aux_high ||
	    args->aux_current <= args->aux_low ||
	    args->aux_current > args->aux_high || (args->aux_current & 15) ||
	    args->required_control_bytes < sizeof(unsigned long) ||
	    args->required_control_bytes > args->aux_current - args->aux_low)
		return -EINVAL;
	if (check_mul_overflow((size_t)args->capacity, sizeof(*args->slots),
			       &slot_bytes) ||
	    check_mul_overflow((size_t)args->capacity, sizeof(*args->frames),
			       &frame_bytes))
		return -EOVERFLOW;

#define SETUP_RANGE(which, pointer, bytes, type) \
	do { \
		result = object_range(&ranges[which], pointer, bytes, \
				      __alignof__(type)); \
		if (result) \
			return result; \
	} while (0)
	SETUP_RANGE(SETUP_ROOT, args->root, sizeof(*args->root),
		    struct kd_task_root_context);
	SETUP_RANGE(SETUP_POOL, args->pool, sizeof(*args->pool), struct kd_request_pool);
	SETUP_RANGE(SETUP_SLOTS, args->slots, slot_bytes, struct kd_request_slot);
	SETUP_RANGE(SETUP_RESOURCES, args->resources, sizeof(*args->resources),
		    struct kd_episode_resources);
	SETUP_RANGE(SETUP_FRAMES, args->frames, frame_bytes, struct kd_episode_frame);
	SETUP_RANGE(SETUP_IMAGE_SLOT, config->image_slot, sizeof(*config->image_slot),
		    struct kd_jit_image_slot);
	SETUP_RANGE(SETUP_STACK_OPS, config->stack, sizeof(*config->stack),
		    struct kd_source_stack_ops);
	SETUP_RANGE(SETUP_FEEDBACK_POOL, config->feedback, sizeof(*config->feedback),
		    struct kd_jit_feedback_pool);
	/* The pool was privately initialized before setup; its immutable extent
	 * may be shared, but never aliases source/task control or either stack.
	 */
	if (!config->feedback->capacity ||
	    check_mul_overflow((size_t)config->feedback->capacity,
			       sizeof(*config->feedback->records), &feedback_bytes))
		return -EINVAL;
	SETUP_RANGE(SETUP_FEEDBACK_RECORDS, config->feedback->records, feedback_bytes,
		    struct kd_jit_feedback_record);
#undef SETUP_RANGE

	result = object_range(&source, task_stack_page(current), THREAD_SIZE,
			       sizeof(unsigned long));
	if (result)
		return result;
	asm volatile("movq %%rsp, %0" : "=r"(source_sp));
	if (source_sp < source.low + sizeof(unsigned long) ||
	    source_sp > source.high || (source_sp & (sizeof(unsigned long) - 1)))
		return -EINVAL;
	auxiliary.low = args->aux_low;
	auxiliary.high = args->aux_high;
	if (overlaps(&source, &auxiliary))
		return -EINVAL;
	for (index = 0; index < SETUP_OBJECTS; ++index) {
		if (overlaps(&ranges[index], &source) ||
		    overlaps(&ranges[index], &auxiliary) ||
		    overlaps(&ranges[index], input) ||
		    overlaps(&ranges[index], config_input))
			return -EINVAL;
		for (other = 0; other < index; ++other)
			if (overlaps(&ranges[index], &ranges[other]))
				return -EINVAL;
	}
	/* Only now dereference the independently retained stack-ops record.
	 * No callback/context/code extent can be inferred from its address.
	 */
	if (!config->stack->read_word || !config->stack->write_word ||
	    !config->resolve || !config->classify_target || !config->report)
		return -EINVAL;
	return 0;
}

int kd_task_setup_current(const struct kd_task_setup_args *args)
{
	struct kd_task_setup_args inputs;
	struct kd_episode_config config;
	struct setup_range input_range, config_range;
	int result, unwind;

	if (!in_task() || in_atomic() || irqs_disabled() ||
	    READ_ONCE(current->__state) != TASK_RUNNING)
		return -EWOULDBLOCK;
	if (kd_task_root_context_current())
		return -EEXIST;
	result = object_range(&input_range, args, sizeof(*args),
			       __alignof__(struct kd_task_setup_args));
	if (result)
		return result;
	inputs = *args;
	result = object_range(&config_range, inputs.config, sizeof(config),
			       __alignof__(struct kd_episode_config));
	if (result)
		return result;
	config = *inputs.config;
	result = validate(&inputs, &config, &input_range, &config_range);
	if (result)
		return result;

	/* The private-ownership precondition, not a guessed old root field,
	 * authorizes this constructor. Source admission stays closed throughout.
	 */
	kd_task_root_context_init(inputs.root);
	result = kd_task_root_attach(inputs.root, inputs.origin_gs, inputs.aux_low,
		inputs.aux_high, inputs.aux_current, inputs.pool, inputs.slots,
		inputs.capacity);
	if (result)
		return result;
	result = kd_episode_resources_init(inputs.resources, inputs.pool, inputs.frames,
					   inputs.capacity, &config);
	if (!result)
		result = kd_mutex_bind_current(inputs.resources, inputs.required_control_bytes);
	if (!result)
		return 0;

	/* No request, image use, source execution or lookup escape exists. This
	 * is the exact native endpoint initialized by the successful attach.
	 */
	unwind = kd_task_root_detach(inputs.root, &inputs.root->initial_native);
	return unwind ? unwind : result;
}

int kd_task_teardown_current(struct kd_task_root_context *root,
			     struct kd_execution_binding *expected_native,
			     bool *pending)
{
	int result = kd_task_progress_native(root, expected_native, pending);

	if (result)
		return result;
	/* pending may include only the CURRENT endpoint. Exact detach owns that
	 * revocation; a pending-based wait could never discharge it. No control
	 * or endpoint is accessed after successful detach.
	 */
	return kd_task_root_detach(root, expected_native);
}
