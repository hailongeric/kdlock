// SPDX-License-Identifier: GPL-2.0-only
/* Serial source episodes over one canonical packet and retained request slots. */
#include <linux/bug.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "episode.h"
#include "observation.h"

static enum kd_mutex_outcome run(struct kd_jit_mutex_call *call,
		struct kd_execution_binding **binding, void *context);
static int exported(struct kd_jit_mutex_call *call,
		enum kd_mutex_outcome outcome, void *context);

static int finish_user(struct kd_request_user *user, bool *held)
{
	int result;

	if (!*held)
		return 0;

	*held = false;
	/* Success ends access; failure consumed nothing and restores the flag. */
	result = kd_request_user_finish(user, user);
	if (result)
		*held = true;
	return result;
}

static int hold_user(struct kd_episode_frame *frame, struct kd_request_user *user,
		     bool *held, enum kd_request_user_kind kind)
{
	int result = kd_request_user_hold(frame->slot, frame->claim, user, user, kind);

	if (!result)
		*held = true;
	return result;
}

static void frame_init(struct kd_episode_frame *frame,
		       struct kd_episode_resources *resources,
		       struct kd_request_slot *slot, struct kd_episode_frame *parent)
{
	frame->resources = resources;
	frame->slot = slot;
	frame->claim = &slot->call.acquisition_identity;
	frame->origin = resources->pool->state->origin;
	frame->root = parent ? parent->root : frame;
	frame->parent = parent;
	frame->operation = KD_OPERATION_MUTEX_LOCK;
	INIT_LIST_HEAD(&frame->children);
	INIT_LIST_HEAD(&frame->child_link);
	INIT_LIST_HEAD(&frame->deferred);
	INIT_LIST_HEAD(&frame->deferred_link);
	frame->deferred_host = NULL;
	kd_request_user_init(&frame->control_user);
	kd_request_user_init(&frame->image_user);
	kd_request_user_init(&frame->grant_user);
	kd_request_user_init(&frame->binding_user);
	kd_request_user_init(&frame->native_user);
	kd_request_user_init(&frame->notifier_user);
	kd_request_user_init(&frame->deferred_user);
	kd_request_user_init(&frame->auxiliary_user);
	frame->control_held = false;
	frame->image_held = false;
	frame->grant_held = false;
	frame->binding_held = false;
	frame->native_held = false;
	frame->notifier_held = false;
	frame->deferred_held = false;
	frame->auxiliary_held = false;
	frame->source_image = false;
	frame->return_image = false;
	frame->execution_image = false;
	frame->exit_pending = false;
	frame->parent_return = false;
	frame->parent_linked = false;
	frame->grant_started = false;
	frame->source_closed = false;
	frame->flush_deferred = false;
	frame->result_consumed = false;
}

int kd_episode_resources_init(struct kd_episode_resources *resources,
		 struct kd_request_pool *pool, struct kd_episode_frame *frames,
		 unsigned int capacity, const struct kd_episode_config *config)
{
	unsigned int index;

	if (!resources || !pool || !pool->state || !config || capacity != pool->capacity ||
	    (capacity && (!frames || !config->image_slot || !config->feedback || !config->stack ||
	     !config->stack->read_word || !config->stack->write_word ||
	     !config->resolve || !config->classify_target || !config->report)))
		return -EINVAL;
	/* Private setup only; no live frame or previous observer may exist. */
	resources->pool = pool;
	resources->frames = frames;
	resources->capacity = capacity;
	resources->config = *config;
	for (index = 0; index < capacity; ++index)
		frame_init(&frames[index], resources, &pool->slots[index], NULL);
	return 0;
}

static struct kd_owner_progress *owners(void)
{
	struct kd_task_root_context *root = kd_task_root_context_current();

	return root && root->attached && root->task == current ? &root->owners : NULL;
}

static int selected_local(struct kd_jit_mutex_call *call, void *context)
{
	struct kd_episode_frame *frame = context;
	struct kd_owner_progress *progress = owners();

	if (call != &frame->slot->call || !progress)
		return -ESTALE;
	return kd_owner_progress_track(progress, &frame->slot->owner_batch,
				       &call->possible_batch);
}

static int wait_progress(struct kd_jit_mutex_call *call, void *context, bool *blocked)
{
	struct kd_episode_frame *frame = context;
	struct kd_owner_progress *progress = owners();

	if (call != &frame->slot->call || !progress)
		return -ESTALE;
	return kd_owner_progress_run(progress, blocked);
}

static bool wait_ready(struct kd_jit_mutex_call *call, void *context)
{
	struct kd_episode_frame *frame = context;
	struct kd_owner_progress *progress = owners();

	return call == &frame->slot->call && progress && kd_owner_progress_ready(progress);
}

/* Frame/control users retain these identities for this synchronous snapshot.
 * Only call sites with current stopped source rights add cursor/IO values.
 */
#define observe_frame(_frame, _kind, ...) \
	kd_observe(_kind, \
	 .state = (unsigned long)(_frame)->resources->pool->state, \
	 .origin = (unsigned long)(_frame)->origin, \
	 .node = (unsigned long)&(_frame)->slot->call.node, \
	 .acquisition = (unsigned long)&(_frame)->slot->call.acquisition_identity, \
	 .parent = (unsigned long)((_frame)->parent ? \
	  &(_frame)->parent->slot->call.node : NULL), __VA_ARGS__)

static int pump(void)
{
	struct kd_owner_progress *progress = owners();
	bool blocked;
	int result;

	if (!progress)
		return -ENOENT;
	for (;;) {
		__set_current_state(TASK_RUNNING);
		result = kd_owner_progress_run(progress, &blocked);
		if (result || !blocked)
			return result;
		set_current_state(TASK_UNINTERRUPTIBLE);
		if (!kd_owner_progress_ready(progress))
			schedule();
	}
}

static int put_image(struct kd_episode_frame *frame,
		     struct kd_jit_image_use *use, bool *held)
{
	int result;

	if (!*held)
		return 0;
	result = kd_jit_image_use_put(use, &frame->image_user);
	if (!result)
		*held = false;
	return result;
}

static int finish_image_actor(struct kd_episode_frame *frame)
{
	if (frame->source_image || frame->return_image || frame->execution_image ||
	    frame->exit_pending)
		return 0;
	return finish_user(&frame->image_user, &frame->image_held);
}

/* Current source owner only. Owner pumps never inspect or change this index. */
int kd_episode_collect(struct kd_episode_resources *resources,
		   struct kd_execution_binding *binding)
{
	unsigned int index;
	int result;

	if (!resources || !resources->pool)
		return -EINVAL;
	result = kd_jit_collect_grants(resources->pool->state, binding);
	if (result)
		return result;
	for (index = 0; index < resources->capacity; ++index) {
		struct kd_episode_frame *frame = &resources->frames[index];

		/* This exact actor holds the frame until its final finish below. */
		if (!frame->grant_held || !frame->grant_started ||
		    frame->slot->call.grant.linked)
			continue;
		result = put_image(frame, &frame->slot->source_use, &frame->source_image);
		if (result)
			return result;
		result = finish_image_actor(frame);
		if (result)
			return result;
		/* No access to this frame follows the last grant-actor finish. */
		result = finish_user(&frame->grant_user, &frame->grant_held);
		if (result)
			return result;
	}
	kd_request_pool_collect(resources->pool);
	return 0;
}

static int drop_return(struct kd_episode_frame *child)
{
	struct kd_episode_frame *parent = child->parent;
	int result;

	if (!child->parent_return)
		return 0;
	result = kd_mutex_drop_return(&parent->slot->call.node, &child->return_identity);
	if (result)
		return result;
	child->parent_return = false;
	result = put_image(parent, &parent->slot->return_use, &parent->return_image);
	if (result)
		return result;
	return finish_image_actor(parent);
}

/* Only after a known fresh transfer ended the old child endpoint. No S_W read
 * is needed, including when native W has already advanced after a terminal hop.
 */
static int close_children(struct kd_episode_frame *frame)
{
	while (!list_empty(&frame->children)) {
		struct kd_episode_frame *child = list_first_entry(&frame->children,
						struct kd_episode_frame, child_link);
		int result;

		list_del_init(&child->child_link);
		result = drop_return(child);
		if (result)
			return result;
		if (!child->result_consumed) {
			result = kd_mutex_result_consumed(&child->slot->call.node,
						 &child->slot->call.result_identity);
			if (result)
				return result;
			child->result_consumed = true;
		}
		child->parent = NULL;
		child->parent_linked = false;
		result = kd_request_slot_drop_parent(child->slot, child->claim);
		if (result)
			return result;
		result = finish_user(&child->native_user, &child->native_held);
		if (result)
			return result;
		result = finish_user(&child->binding_user, &child->binding_held);
		if (result)
			return result;
		result = finish_image_actor(child);
		if (result)
			return result;
		/* Source/image actors may retain this acquisition after C return. */
		result = finish_user(&child->control_user, &child->control_held);
		if (result)
			return result;
	}
	return 0;
}

static int queue_deferred(struct kd_episode_frame *host,
			  struct kd_episode_frame *target)
{
	bool new_host = !host->deferred_held;
	int result;

	if (target->deferred_host || target->notifier_held ||
	    !list_empty(&target->deferred_link))
		return -EALREADY;
	if (!host->deferred_held) {
		result = hold_user(host, &host->deferred_user, &host->deferred_held,
				   KD_REQUEST_USER_NOTIFIER);
		if (result)
			return result;
	}
	result = hold_user(target, &target->notifier_user, &target->notifier_held,
			   KD_REQUEST_USER_NOTIFIER);
	if (result) {
		if (new_host) {
			int drop = finish_user(&host->deferred_user, &host->deferred_held);
			if (drop)
				return drop;
		}
		return result;
	}
	target->deferred_host = host;
	list_add_tail(&target->deferred_link, &host->deferred);
	return 0;
}

/* A declined API recipe has not submitted its release or staged a word. */
static int unqueue_deferred(struct kd_episode_frame *host,
			    struct kd_episode_frame *target)
{
	int result;

	list_del_init(&target->deferred_link);
	target->deferred_host = NULL;
	result = finish_user(&target->notifier_user, &target->notifier_held);
	if (result || !list_empty(&host->deferred))
		return result;
	return finish_user(&host->deferred_user, &host->deferred_held);
}

static int flush_deferred(struct kd_episode_frame *frame)
{
	while (!list_empty(&frame->deferred)) {
		struct kd_episode_frame *target = list_first_entry(&frame->deferred,
						 struct kd_episode_frame, deferred_link);
		struct kd_mutex_release_owner *owner;
		int result;

		/* Detach all referring fields before the target's final user drops. */
		list_del_init(&target->deferred_link);
		target->deferred_host = NULL;
		result = kd_mutex_publish_outer_unwind(&target->slot->call.node,
						      &target->notifier_user, &owner);
		if (result)
			return result;
		result = kd_mutex_outer_notification_done(&target->slot->call.node,
							 &target->notifier_user);
		if (result)
			return result;
		result = finish_user(&target->notifier_user, &target->notifier_held);
		if (result)
			return result;
	}
	return finish_user(&frame->deferred_user, &frame->deferred_held);
}

static int cancel_private(struct kd_episode_frame *frame, bool prepared)
{
	struct kd_request_slot *slot = frame->slot;
	const void *claim = frame->claim;
	int result;

	if (prepared) {
		result = kd_request_slot_discard(slot, claim);
		if (result)
			return result;
	}
	result = drop_return(frame);
	if (result)
		return result;
	if (frame->parent_linked) {
		frame->parent = NULL;
		frame->parent_linked = false;
		result = kd_request_slot_drop_parent(slot, claim);
		if (result)
			return result;
	}
	result = put_image(frame, &slot->source_use, &frame->source_image);
	if (result)
		return result;
	result = finish_user(&frame->image_user, &frame->image_held);
	if (result)
		return result;
	result = finish_user(&frame->grant_user, &frame->grant_held);
	if (result)
		return result;
	result = finish_user(&frame->binding_user, &frame->binding_held);
	if (result)
		return result;
	result = finish_user(&frame->native_user, &frame->native_held);
	if (result)
		return result;
	result = finish_user(&frame->auxiliary_user, &frame->auxiliary_held);
	if (result)
		return result;
	result = finish_user(&frame->control_user, &frame->control_held);
	if (result || prepared)
		return result;
	/* RESERVED remains private/noncollectable; cancel is its final visit. */
	return kd_request_slot_cancel(slot, claim);
}

static int prepare(struct kd_episode_resources *resources,
		   struct kd_execution_binding *binding,
		   struct kd_episode_frame *parent, struct kd_episode_frame **result)
{
	struct kd_request_slot *slot;
	struct kd_episode_frame *frame;
	struct kd_jit_mutex_driver driver;
	bool prepared = false;
	int error, unwind;

	*result = NULL;
	error = kd_request_slot_reserve_owned(resources->pool, binding, &slot);
	if (error)
		return error;
	frame = &resources->frames[slot - resources->pool->slots];
	frame_init(frame, resources, slot, parent);
	error = hold_user(frame, &frame->control_user, &frame->control_held,
			  KD_REQUEST_USER_CONTROL);
	if (error)
		goto failed;
	error = hold_user(frame, &frame->image_user, &frame->image_held,
			  KD_REQUEST_USER_IMAGE);
	if (error)
		goto failed;
	error = hold_user(frame, &frame->grant_user, &frame->grant_held,
			  KD_REQUEST_USER_CONTROL);
	if (error)
		goto failed;
	if (parent) {
		error = kd_request_slot_set_parent(slot, frame->claim,
						  parent->slot, parent->claim);
		if (error)
			goto failed;
		frame->parent_linked = true;
		error = hold_user(frame, &frame->binding_user, &frame->binding_held,
				  KD_REQUEST_USER_BINDING);
		if (error)
			goto failed;
		error = kd_request_user_hold(frame->root->slot, frame->root->claim,
					     &frame->native_user, &frame->native_user,
					     KD_REQUEST_USER_BINDING);
		if (error)
			goto failed;
		frame->native_held = true;
	} else {
		error = hold_user(frame, &frame->auxiliary_user, &frame->auxiliary_held,
				  KD_REQUEST_USER_AUXILIARY);
		if (error)
			goto failed;
	}
	/* Image absence/closing declines proxy eligibility, not the unified
	 * persistent local queue path. Descendants extend their admitted image.
	 */
	if (parent)
		error = kd_jit_image_use_extend(&parent->slot->source_use, &parent->image_user,
			&slot->source_use, &frame->image_user, KD_JIT_IMAGE_USE_SOURCE);
	else
		error = kd_jit_image_lookup(resources->config.image_slot, &slot->source_use,
			resources->pool->state, &frame->image_user, KD_JIT_IMAGE_USE_SOURCE);
	if (!error)
		frame->source_image = true;
	else if (parent || (error != -ENOENT && error != -EAGAIN))
		goto failed;
	driver = (struct kd_jit_mutex_driver) {
		.selected_local = selected_local, .wait_progress = wait_progress,
		.wait_ready = wait_ready, .run = run, .exported = exported,
		.stack = resources->config.stack,
		.origin_binding = &frame->root->slot->native_return, .context = frame,
	};
	error = kd_request_slot_prepare(slot, frame->claim, binding, &driver,
					frame->source_image);
	if (error)
		goto failed;
	prepared = true;
	observe_frame(frame, KD_OBS_FRAME_PREPARE,
		.image = (unsigned long)(frame->source_image ? slot->source_use.image : NULL),
		.related = (unsigned long)binding, .phase = slot->phase);
	*result = frame;
	return 0;
failed:
	unwind = cancel_private(frame, prepared);
	return unwind ? unwind : error;
}

int kd_episode_prepare_root(struct kd_episode_resources *resources,
		 struct kd_execution_binding *native_binding,
		 enum kd_operation_kind operation, struct kd_episode_frame **frame)
{
	int result;

	if (!resources || !frame || operation != KD_OPERATION_MUTEX_LOCK)
		return -EINVAL;
	*frame = NULL;
	if (!kd_state_is_current(resources->pool->state, native_binding) ||
	    native_binding->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	result = kd_episode_collect(resources, native_binding);
	if (result)
		return result;
	return prepare(resources, native_binding, NULL, frame);
}

int kd_episode_cancel_root(struct kd_episode_frame *frame,
			   struct kd_execution_binding *native_binding)
{
	if (!frame || frame->parent ||
	    !kd_state_is_current(frame->resources->pool->state, native_binding) ||
	    native_binding->kind != KD_EXECUTION_NATIVE ||
	    frame->slot->call.node.enqueued ||
	    frame->slot->entry.phase != KD_MUTEX_ENTRY_PRIVATE)
		return -EPERM;
	return cancel_private(frame, true);
}

static struct kd_episode_frame *grant_frame(struct kd_source_grant *grant)
{
	struct kd_jit_mutex_call *call = kd_jit_mutex_grant_call(grant);
	struct kd_episode_frame *frame;

	if (IS_ERR(call))
		return ERR_CAST(call);
	if (!call->driver || call->driver->run != run)
		return ERR_PTR(-EOPNOTSUPP);
	frame = call->driver->context;
	return frame && &frame->slot->call == call ? frame : ERR_PTR(-ESTALE);
}

static unsigned int local_service_limit(struct kd_episode_resources *resources,
					struct kd_execution_binding *binding)
{
	struct kd_thread_state *state = resources->pool->state;
	struct kd_source_grant *grant;

	BUG_ON(!kd_state_is_current(state, binding));
	/* Do not start unrelated inner source batching before the new local
	 * head's grant while this source still holds another logical mutex.
	 * Remote selection and the unified MCS queue remain unchanged.
	 */
	list_for_each_entry(grant, &state->grants, state_link)
		if (grant->logical_open)
			return 0;
	return resources->config.proxy_limit;
}

struct cached_operation {
	unsigned long target;
	enum kd_operation_kind kind;
};

static enum kd_operation_kind cached_resolve(void *context, unsigned long target)
{
	struct cached_operation *cached = context;

	return cached->target == target ? cached->kind : KD_OPERATION_NONE;
}

static bool operation_declined(int result, struct kd_thread_state *state,
			       struct kd_execution_binding *binding)
{
	return (result == -ENOENT || result == -EOPNOTSUPP) &&
	       kd_state_is_jit_current(state, binding) &&
	       (state->operation.phase == KD_OPERATION_IDLE ||
		state->operation.phase == KD_OPERATION_RESUMABLE);
}

static void report(struct kd_episode_frame *frame, const struct kd_jit_image *image,
		   struct kd_thread_state *state, int entry_result, bool pending)
{
	frame->resources->config.report(frame->resources->config.report_context,
		image, state->regs.ip, entry_result, pending ? &state->io : NULL);
}

static enum kd_mutex_outcome forward(struct kd_episode_frame *frame,
		struct kd_execution_binding **binding, const struct kd_jit_image *image,
		int entry_result)
{
	struct kd_thread_state *state = frame->resources->pool->state;
	int result;

	report(frame, image, state, entry_result, state->exit_image != NULL);
	if (!kd_state_is_jit_current(state, *binding))
		return KD_MUTEX_OUTCOME_UNSET;
	observe_frame(frame, KD_OBS_FORWARD, .image = (unsigned long)image,
		.ip = state->io.source_ip, .cursor = state->regs.ip,
		.related = state->io.target, .phase = state->io.phase,
		.result = (unsigned long)(long)entry_result, .flags = state->io.kind);
	if (state->exit_image) {
		if (state->io.phase == KD_JIT_PHASE_TARGET_READY)
			result = kd_jit_stage_forward_call(image, state, *binding,
						  frame->resources->config.stack);
		else
			result = kd_jit_consume_exit(image, state, *binding);
		if (result)
			return KD_MUTEX_OUTCOME_UNSET;
		frame->exit_pending = false;
	}
	result = kd_jit_transfer_origin(state, *binding,
				       &frame->root->slot->native_return);
	BUG_ON(result);
	/* No state/binding sample follows this terminal source transfer. */
	*binding = NULL;
	return KD_MUTEX_PROXY_ORIGIN_SUFFIX;
}

static enum kd_mutex_outcome run(struct kd_jit_mutex_call *call,
		struct kd_execution_binding **binding, void *context)
{
	struct kd_episode_frame *frame = context;
	struct kd_episode_resources *resources = frame->resources;
	struct kd_thread_state *state = resources->pool->state;
	int result;

	BUG_ON(call != &frame->slot->call);
	frame->grant_started = true;
	for (;;) {
		const struct kd_jit_image *image;
		struct cached_operation cached;
		bool operation_exit;
		enum kd_jit_feedback_target_class classification;

		result = kd_episode_collect(resources, *binding);
		BUG_ON(result);
		result = pump();
		BUG_ON(result);
		if (frame->source_closed) {
			enum kd_mutex_outcome completed = list_empty(&frame->deferred) ?
				KD_MUTEX_PROXY_EPISODE_DONE : KD_MUTEX_PROXY_UNWIND_PARENT;

			frame->flush_deferred = true;
			if (trace_kdlock_observe_tp_enabled()) {
				bool owned = kd_state_is_jit_current(state, *binding);

				/* Collection may already have dropped the last image use.
				 * Join earlier JIT_EXIT/accepted-unlock records by this
				 * retained acquisition; do not dereference retired code.
				 */
				observe_frame(frame, KD_OBS_EPISODE_DONE,
					.cursor = owned ? state->regs.ip : 0,
					.related = (unsigned long)*binding,
					.result = completed,
					.flags = KD_OBS_FLAG_SOURCE_CLOSED |
						(owned ? KD_OBS_FLAG_CURRENT_JIT : 0));
			}
			return completed;
		}
		if (!frame->source_image || current == frame->origin)
			return forward(frame, binding,
				frame->source_image ? frame->slot->source_use.image : NULL,
				frame->source_image ? -EXDEV : -ENOENT);
		result = kd_jit_image_use_extend(&frame->slot->source_use, &frame->image_user,
			&frame->slot->execution_use, &frame->image_user, KD_JIT_IMAGE_USE_EXECUTION);
		BUG_ON(result);
		frame->execution_image = true;
		image = frame->slot->execution_use.image;
		observe_frame(frame, KD_OBS_JIT_ENTER, .image = (unsigned long)image,
			.cursor = state->regs.ip, .related = (unsigned long)*binding);
		result = kd_jit_enter(&frame->slot->execution_use, &frame->image_user,
			&frame->slot->exit_use, &frame->image_user, state, *binding);
		{
			int drop = put_image(frame, &frame->slot->execution_use, &frame->execution_image);
			BUG_ON(drop);
		}
		if (result) {
			if (result != -ENOENT && result != -EINVAL)
				return KD_MUTEX_OUTCOME_UNSET;
			return forward(frame, binding, image, result);
		}
		frame->exit_pending = true;
		image = state->exit_image;
		observe_frame(frame, KD_OBS_JIT_EXIT, .image = (unsigned long)image,
			.ip = state->io.source_ip, .cursor = state->regs.ip,
			.related = state->io.target, .phase = state->io.phase,
			.result = state->io.kind, .flags = state->io.detail);
		operation_exit = ((state->io.kind == KD_JIT_EXIT_LOCK_OPERATION &&
		       (state->io.phase == KD_JIT_PHASE_BEFORE_INSTRUCTION ||
			state->io.phase == KD_JIT_PHASE_TARGET_READY ||
			state->io.phase == KD_JIT_PHASE_JUMP_RESOLVED)) ||
		      (state->io.kind == KD_JIT_EXIT_COVERAGE_MISS &&
		       (state->io.phase == KD_JIT_PHASE_TARGET_READY ||
			state->io.phase == KD_JIT_PHASE_CALL_STAGED ||
			state->io.phase == KD_JIT_PHASE_JUMP_RESOLVED)));
		classification = KD_JIT_FEEDBACK_UNCLASSIFIED;
		cached.kind = KD_OPERATION_NONE;
		if (operation_exit) {
			cached.target = state->io.phase == KD_JIT_PHASE_BEFORE_INSTRUCTION ?
				state->regs.ip : state->io.target;
			cached.kind = resources->config.resolve(resources->config.resolve_context,
							       cached.target);
			if (!kd_state_is_jit_current(state, *binding))
				return KD_MUTEX_OUTCOME_UNSET;
			classification = cached.kind == KD_OPERATION_NONE ?
				resources->config.classify_target(resources->config.classify_context,
								  cached.target) : KD_JIT_FEEDBACK_SOURCE_API;
			if (!kd_state_is_jit_current(state, *binding))
				return KD_MUTEX_OUTCOME_UNSET;
		}
		/* Record this exact phase before a nested operation or forward CALL
		 * can consume/change it. No old code is pinned by the copied fact.
		 */
		if (state->io.kind == KD_JIT_EXIT_COVERAGE_MISS) {
			result = kd_jit_feedback_record_exit(resources->config.feedback, image,
				state->regs.ip, 0, &state->io, classification);
			if (result)
				return KD_MUTEX_OUTCOME_UNSET;
		}
		if (state->io.kind == KD_JIT_EXIT_INVARIANT_FAILURE)
			return KD_MUTEX_OUTCOME_UNSET;
		if (!operation_exit)
			return forward(frame, binding, image, 0);
		if (cached.kind == KD_OPERATION_MUTEX_LOCK) {
			struct kd_episode_frame *child;
			struct kd_execution_binding *child_binding = *binding;
			enum kd_mutex_outcome outcome;
			unsigned long operation_ip = state->io.source_ip;
			unsigned long object = state->regs.di;

			result = prepare(resources, *binding, frame, &child);
			BUG_ON(result);
			result = kd_mutex_hold_return(&call->node, &child->return_identity);
			BUG_ON(result);
			child->parent_return = true;
			result = kd_jit_image_use_extend(&frame->slot->source_use, &frame->image_user,
				&frame->slot->return_use, &frame->image_user, KD_JIT_IMAGE_USE_RETURN);
			BUG_ON(result);
			frame->return_image = true;
			result = kd_jit_prepare_operation(image, state, *binding,
				&child->slot->call.acquisition_identity, cached_resolve, &cached,
				resources->config.stack);
			if (result) {
				int unwind;

				if (!operation_declined(result, state, *binding))
					return KD_MUTEX_OUTCOME_UNSET;
				unwind = cancel_private(child, true);
				BUG_ON(unwind);
				return forward(frame, binding, image, result);
			}
			frame->exit_pending = false;
			observe_frame(frame, KD_OBS_JIT_OPERATION,
				.image = (unsigned long)image, .ip = operation_ip,
				.cursor = state->regs.ip, .object = object,
				.related = (unsigned long)&child->slot->call.node,
				.phase = state->operation.phase, .result = KD_OPERATION_MUTEX_LOCK);
			result = kd_jit_mutex_acquire(&child->slot->call,
				(struct kd_mutex *)state->regs.di, &child_binding,
				local_service_limit(resources, child_binding), &outcome);
			BUG_ON(result);
			if (outcome == KD_MUTEX_LOCAL_GRANTED) {
				result = kd_jit_mutex_drive(&child->slot->call, &child_binding, &outcome);
				BUG_ON(result);
			}
			/* A terminal source transfer may already let W advance. Only
			 * successful structured returns still permit canonical reads.
			 */
			if (trace_kdlock_observe_tp_enabled()) {
				bool owned = outcome != KD_MUTEX_PROXY_ORIGIN_SUFFIX &&
					kd_state_is_jit_current(state, child_binding);

				observe_frame(frame, KD_OBS_CHILD_RETURN,
					.related = (unsigned long)&child->slot->call.node,
					.result = outcome, .cursor = owned ? state->regs.ip : 0,
					.return_user = (unsigned long)child_binding,
					.source_user = (unsigned long)*binding,
					.flags = owned ? KD_OBS_FLAG_CURRENT_JIT : 0);
			}
			result = drop_return(child);
			BUG_ON(result);
			/* The newly published child/native route closed every old child
			 * endpoint. Keep the new endpoint's separate observer below.
			 */
			result = close_children(frame);
			BUG_ON(result);
			list_add_tail(&child->child_link, &frame->children);
			if (outcome == KD_MUTEX_PROXY_ORIGIN_SUFFIX) {
				*binding = NULL;
				return outcome;
			}
			*binding = child_binding;
			continue;
		}
		if (cached.kind == KD_OPERATION_MUTEX_UNLOCK) {
			struct kd_source_grant *grant = kd_state_find_grant(state, *binding,
								 (void *)state->regs.di);
			struct kd_episode_frame *target;
			struct kd_mutex_batch *active = call->node.batch;
			enum kd_mutex_unlock_action action;
			bool deferred;
			unsigned long operation_ip = state->io.source_ip;
			unsigned long object = state->regs.di;

			BUG_ON(IS_ERR(grant));
			target = grant_frame(grant);
			BUG_ON(IS_ERR(target));
			deferred = active != target->slot->call.node.batch;
			if (deferred) {
				result = queue_deferred(frame, target);
				BUG_ON(result);
			}
			result = kd_jit_prepare_operation(image, state, *binding,
				&target->slot->call.unlock_identity, cached_resolve, &cached,
				resources->config.stack);
			if (result) {
				if (!operation_declined(result, state, *binding))
					return KD_MUTEX_OUTCOME_UNSET;
				if (deferred) {
					int unwind = unqueue_deferred(frame, target);
					BUG_ON(unwind);
				}
				return forward(frame, binding, image, result);
			}
			frame->exit_pending = false;
			result = kd_jit_mutex_unlock(&target->slot->call, *binding, active,
				deferred ? &target->notifier_user : NULL, &action);
			BUG_ON(result);
			target->source_closed = true;
			observe_frame(frame, KD_OBS_JIT_OPERATION,
				.image = (unsigned long)image, .ip = operation_ip,
				.cursor = state->regs.ip, .object = object,
				.related = (unsigned long)&target->slot->call.node,
				.phase = action, .result = KD_OPERATION_MUTEX_UNLOCK);
			continue;
		}
		return forward(frame, binding, image, 0);
	}
}

static int exported(struct kd_jit_mutex_call *call,
		enum kd_mutex_outcome outcome, void *context)
{
	struct kd_episode_frame *frame = context;
	int result;

	/* Only persistent control flags are read after returned/native export. */
	if (call != &frame->slot->call)
		return -ESTALE;
	if (call->possible_batch.initialized &&
	    !frame->slot->owner_batch.control_stopped) {
		result = kd_owner_progress_control_stopped(&frame->slot->owner_batch,
			outcome == KD_MUTEX_PROXY_ORIGIN_SUFFIX && current != frame->origin);
		if (result)
			return result;
	}
	if (frame->flush_deferred) {
		result = flush_deferred(frame);
		if (result)
			return result;
	}
	return close_children(frame);
}

int kd_episode_acquire_root(struct kd_episode_frame *frame,
		 struct kd_execution_binding *native_binding, struct kd_mutex *lock,
		 unsigned long source_sp, unsigned long continuation_ip,
		 unsigned long source_bp, unsigned long api_target,
		 enum kd_mutex_outcome *outcome)
{
	struct kd_execution_binding *binding;
	int result;

	if (!frame || !outcome || frame->parent)
		return -EINVAL;
	binding = &frame->slot->capture;
	result = kd_jit_capture_mutex_lock(&frame->slot->call, native_binding, binding,
		lock, source_sp, continuation_ip, source_bp, api_target);
	if (result)
		return result;
	result = kd_jit_mutex_acquire(&frame->slot->call, lock, &binding,
				    local_service_limit(frame->resources, binding), outcome);
	if (result)
		return result;
	if (*outcome == KD_MUTEX_LOCAL_GRANTED) {
		result = kd_jit_mutex_drive(&frame->slot->call, &binding, outcome);
		if (result)
			return result;
	}
	if (*outcome != KD_MUTEX_PROXY_ORIGIN_SUFFIX) {
		/* The delegated episode already completed acquisition/source work.
		 * Transfer its current returned packet once; never drive it again.
		 */
		result = kd_jit_transfer_origin(frame->resources->pool->state, binding,
					       &frame->slot->native_return);
		if (result)
			return result;
		*outcome = KD_MUTEX_PROXY_ORIGIN_SUFFIX;
	}
	return 0;
}

struct kd_execution_binding *kd_episode_native_binding(struct kd_episode_frame *frame)
{
	if (!frame || frame->root != frame || !frame->auxiliary_held)
		return NULL;
	return &frame->slot->native_return;
}

int kd_episode_root_done(struct kd_episode_frame *frame)
{
	int result;

	if (!frame || frame->root != frame || !frame->auxiliary_held)
		return -EINVAL;
	if (!kd_state_is_current(frame->resources->pool->state,
				 &frame->slot->native_return))
		return -ESTALE;
	result = close_children(frame);
	if (result)
		return result;
	result = kd_mutex_result_consumed(&frame->slot->call.node,
					 &frame->slot->call.result_identity);
	if (result)
		return result;
	frame->result_consumed = true;
	/* The source/grant image actor may survive this root's native suffix. */
	result = finish_image_actor(frame);
	if (result)
		return result;
	return finish_user(&frame->control_user, &frame->control_held);
}

void kd_episode_native_done(void *context)
{
	struct kd_episode_frame *frame = context;
	int result = finish_user(&frame->auxiliary_user, &frame->auxiliary_held);

	/* No frame/slot/user read follows the final auxiliary actor finish. */
	BUG_ON(result);
}

int kd_episode_unlock_native(struct kd_episode_resources *resources,
		 struct kd_task_root_context *root,
		 struct kd_execution_binding *native_binding, struct kd_mutex *lock)
{
	struct kd_source_grant *grant;
	struct kd_episode_frame *frame;
	struct kd_request_user user;
	struct kd_mutex_release_owner *owner;
	struct kd_mutex_batch *active;
	enum kd_mutex_unlock_action action;
	int result;

	if (!root || !root->attached || root != kd_task_root_context_current() ||
	    root->task != current || root->aux_entry ||
	    !in_task() || in_atomic() || irqs_disabled() ||
	    !kd_state_is_current(&root->core, native_binding) ||
	    native_binding->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	grant = kd_state_find_grant(&root->core, native_binding, lock);
	if (IS_ERR(grant))
		return PTR_ERR(grant);
	frame = grant_frame(grant);
	if (IS_ERR(frame))
		return PTR_ERR(frame);
	if (resources && resources != frame->resources)
		return -ESTALE;
	resources = frame->resources;
	kd_request_user_init(&user);
	result = kd_request_user_hold(frame->slot, frame->claim, &user, &user,
				      KD_REQUEST_USER_CONTROL);
	if (result)
		return result;
	owner = frame->slot->call.node.release.owner;
	active = owner->task == current ? frame->slot->call.node.batch : NULL;
	result = kd_mutex_source_unlock(&frame->slot->call.node, &root->core,
					active, &user, &action);
	BUG_ON(result);
	result = kd_state_close_grant(&root->core, native_binding, grant);
	BUG_ON(result);
	frame->source_closed = true;
	observe_frame(frame, KD_OBS_NATIVE_UNLOCK, .object = (unsigned long)lock,
		.related = (unsigned long)native_binding, .phase = action,
		.flags = KD_OBS_FLAG_SOURCE_CLOSED);
	if (action == KD_MUTEX_UNLOCK_DEFERRED_PARENT) {
		result = kd_mutex_publish_outer_unwind(&frame->slot->call.node, &user, &owner);
		BUG_ON(result);
		result = kd_mutex_outer_notification_done(&frame->slot->call.node, &user);
		BUG_ON(result);
	}
	/* A native actor has already received the terminal source handoff. The
	 * original JIT B's deferred list can now close when B itself unlocks.
	 */
	result = flush_deferred(frame);
	BUG_ON(result);
	result = pump();
	BUG_ON(result);
	result = kd_episode_collect(resources, native_binding);
	BUG_ON(result);
	/* Hardware CALL/RET completes this ordinary source operation. Canonical
	 * regs.ip/SP may be old native materialization and are never imported.
	 * This temporary actor's stack is never lent while its user is linked.
	 */
	return kd_request_user_finish(&user, &user);
}
