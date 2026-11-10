// SPDX-License-Identifier: GPL-2.0-only
/* Original-backend invocation and exact ordinary-mutex source-operation bridge. */
#include <linux/bug.h>
#include <linux/compiler.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/sched.h>

#include "jit.h"

static bool image_valid(const struct kd_jit_image *image)
{
	return image && image->source_identity && image->entry &&
	       image->abi_version == KD_JIT_ABI_VERSION &&
	       image->packet_size == sizeof(struct kd_regs) &&
	       image->io_size == sizeof(struct kd_jit_io) &&
	       image->entry_sites && image->entry_count &&
	       (!image->source_count || image->source_sites);
}

static const struct kd_jit_source_site *find_site(
		const struct kd_jit_image *image, unsigned long ip)
{
	const struct kd_jit_source_site *found = NULL;
	unsigned int i;

	for (i = 0; i < image->source_count; i++) {
		if (image->source_sites[i].ip != ip)
			continue;
		if (found)
			return ERR_PTR(-EUCLEAN);
		found = &image->source_sites[i];
	}
	return found;
}

int kd_jit_enter(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding)
{
	unsigned int i;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (current == state->origin)
		return -EXDEV;
	if (kd_task_state_active() != state)
		return -EPERM;
	if (!image_valid(image))
		return -EINVAL;
	if (state->exit_image ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	for (i = 0; i < image->entry_count; i++)
		if (image->entry_sites[i] == state->regs.ip)
			break;
	if (i == image->entry_count)
		return -ENOENT;

	state->io.origin_gs = state->origin_gs;
	state->io.origin_task = (unsigned long)state->origin;
	state->io.kind = KD_JIT_EXIT_NONE;
	state->io.detail = KD_JIT_DETAIL_NONE;
	state->io.source_ip = 0;
	state->io.target = 0;
	state->io.phase = KD_JIT_PHASE_BEFORE_INSTRUCTION;
	state->exit_image = image;
	image->entry(&state->regs, &state->io);
	/* Generated text returns only after materializing the same packet. */
	if (!kd_state_is_jit_current(state, binding))
		return -ESTALE;
	if (state->io.kind < KD_JIT_EXIT_LOCK_OPERATION ||
	    state->io.kind > KD_JIT_EXIT_INVARIANT_FAILURE ||
	    state->io.phase > KD_JIT_PHASE_JUMP_RESOLVED)
		return -EUCLEAN;
	return 0;
}

int kd_jit_prepare_operation(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding, const void *identity,
		 kd_jit_resolve_operation_fn resolve, void *context,
		 const struct kd_source_stack_ops *stack)
{
	const struct kd_jit_source_site *site;
	enum kd_operation_form form;
	enum kd_operation_kind kind;
	unsigned long target, return_ip = 0;
	int result;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!image_valid(image) || !resolve || !identity)
		return -EINVAL;
	if (state->exit_image != image)
		return -ESTALE;
	site = find_site(image, state->io.source_ip);
	if (IS_ERR(site))
		return PTR_ERR(site);
	switch (state->io.phase) {
	case KD_JIT_PHASE_TARGET_READY:
		if ((state->io.kind != KD_JIT_EXIT_LOCK_OPERATION &&
		     state->io.kind != KD_JIT_EXIT_COVERAGE_MISS) || !site ||
		    site->kind != KD_JIT_SITE_CALL ||
		    state->regs.ip != site->ip)
			return -EUCLEAN;
		target = state->io.target;
		return_ip = site->next_ip;
		form = KD_OPERATION_NEW_CALL;
		/* Reserve the no-failure source-stack route before any CALL push. */
		if (!stack || !stack->write_word || !stack->read_word)
			return -EINVAL;
		break;
	case KD_JIT_PHASE_CALL_STAGED:
		if (state->io.kind != KD_JIT_EXIT_COVERAGE_MISS || !site ||
		    site->kind != KD_JIT_SITE_CALL ||
		    state->regs.ip != state->io.target)
			return -EUCLEAN;
		target = state->io.target;
		return_ip = site->next_ip;
		form = KD_OPERATION_EXISTING_CALL;
		break;
	case KD_JIT_PHASE_JUMP_RESOLVED:
		if ((state->io.kind != KD_JIT_EXIT_COVERAGE_MISS &&
		     state->io.kind != KD_JIT_EXIT_LOCK_OPERATION) || !site ||
		    site->kind != KD_JIT_SITE_JUMP ||
		    state->regs.ip != state->io.target)
			return -ENOENT;
		target = state->io.target;
		form = KD_OPERATION_EXISTING_FRAME;
		break;
	case KD_JIT_PHASE_BEFORE_INSTRUCTION:
		/* A direct/tail edge can stop at the API entry itself. */
		if (state->io.kind != KD_JIT_EXIT_LOCK_OPERATION)
			return -ENOENT;
		target = state->regs.ip;
		form = KD_OPERATION_EXISTING_FRAME;
		break;
	default:
		/* A consumed RET is never staged or popped a second time. */
		return -ENOENT;
	}
	kind = resolve(context, target);
	if (kind == KD_OPERATION_NONE)
		return -ENOENT;
	if (kind != KD_OPERATION_MUTEX_LOCK && kind != KD_OPERATION_MUTEX_UNLOCK)
		return -EOPNOTSUPP;
	if (state->io.kind == KD_JIT_EXIT_LOCK_OPERATION &&
	    ((state->io.detail == KD_JIT_OP_LOCK && kind != KD_OPERATION_MUTEX_LOCK) ||
	     (state->io.detail == KD_JIT_OP_UNLOCK && kind != KD_OPERATION_MUTEX_UNLOCK) ||
	     state->io.detail == KD_JIT_OP_MODE_CHANGE))
		return -EOPNOTSUPP;
	result = kd_operation_begin(state, binding, identity, kind, form,
				    state->io.source_ip, target, return_ip);
	if (result)
		return result;
	if (form == KD_OPERATION_NEW_CALL) {
		result = kd_operation_stage_call(state, binding, identity, stack);
		if (result)
			return result;
	}
	/* The single operation descriptor now retains the exact transition. */
	state->exit_image = NULL;
	state->io.kind = KD_JIT_EXIT_NONE;
	state->io.phase = KD_JIT_PHASE_BEFORE_INSTRUCTION;
	return 0;
}

int kd_jit_consume_exit(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding)
{
	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!image || state->exit_image != image)
		return -ESTALE;
	if (state->io.phase == KD_JIT_PHASE_TARGET_READY)
		return -EBUSY;
	state->exit_image = NULL;
	state->io.kind = KD_JIT_EXIT_NONE;
	state->io.phase = KD_JIT_PHASE_BEFORE_INSTRUCTION;
	return 0;
}

int kd_jit_stage_forward_call(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding,
		 const struct kd_source_stack_ops *stack)
{
	const struct kd_jit_source_site *site;
	unsigned long source_sp;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!image_valid(image) || !stack || !stack->write_word)
		return -EINVAL;
	if (state->operation.phase != KD_OPERATION_IDLE &&
	    state->operation.phase != KD_OPERATION_RESUMABLE)
		return -EBUSY;
	if (state->exit_image != image)
		return -ESTALE;
	if ((state->io.kind != KD_JIT_EXIT_COVERAGE_MISS &&
	     state->io.kind != KD_JIT_EXIT_LOCK_OPERATION) ||
	    state->io.phase != KD_JIT_PHASE_TARGET_READY)
		return -EALREADY;
	site = find_site(image, state->io.source_ip);
	if (IS_ERR(site))
		return PTR_ERR(site);
	if (!site || site->kind != KD_JIT_SITE_CALL ||
	    state->regs.ip != site->ip)
		return -EUCLEAN;
	source_sp = state->regs.sp - sizeof(unsigned long);
	stack->write_word(stack->context, source_sp, site->next_ip);
	state->regs.sp = source_sp;
	state->regs.ip = state->io.target;
	state->io.phase = KD_JIT_PHASE_CALL_STAGED;
	/* Exact-image metadata is no longer needed after its one source push. */
	state->exit_image = NULL;
	return 0;
}

int kd_jit_transfer_origin(struct kd_thread_state *state,
		 struct kd_execution_binding *binding,
		 struct kd_execution_binding *origin_binding)
{
	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!origin_binding || origin_binding->state != state ||
	    origin_binding->kind != KD_EXECUTION_NATIVE ||
	    origin_binding->task != state->origin)
		return -EINVAL;
	if (state->exit_image ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	/* The caller has already staged any resolved but unperformed CALL.
	 * No readiness notification or source access may precede the transfer.
	 */
	return kd_state_transfer(state, binding, origin_binding);
}

extern void __noreturn kd_native_resume(struct kd_regs *regs);

int kd_jit_resume_origin(struct kd_thread_state *state,
		 struct kd_execution_binding *native_binding)
{
	if (!kd_state_is_current(state, native_binding) ||
	    native_binding->kind != KD_EXECUTION_NATIVE || current != state->origin)
		return -EPERM;
	if (kd_task_state_own() != state || kd_task_state_active() != state)
		return -ESTALE;
	if (state->exit_image ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	kd_native_resume(&state->regs);
}

static int drop_grant(void *control, const void *user)
{
	struct kd_jit_mutex_call *call = control;

	/* Success can permit call retirement; do not access call afterward. */
	return kd_mutex_grant_unlinked(&call->node, user);
}

static int accept_selected(struct kd_mutex_node *node, void *context)
{
	struct kd_jit_mutex_call *call = context;
	int result;

	if (node != &call->node)
		return -ESTALE;
	result = kd_execution_binding_init(&call->execution, node->state, current,
					   call, KD_EXECUTION_JIT);
	if (result)
		return result;
	result = kd_state_accept(node->state, &call->offer, &call->execution);
	if (result || current == node->state->origin)
		return result;
	return kd_task_borrow_enter(&call->borrow_scope, node->state, &call->execution);
}

static int finish_acquisition(struct kd_jit_mutex_call *call,
			       struct kd_execution_binding *binding)
{
	struct kd_thread_state *state = call->node.state;
	int result;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (state->operation.kind != KD_OPERATION_MUTEX_LOCK ||
	    state->operation.identity != &call->acquisition_identity ||
	    state->operation.phase != KD_OPERATION_ENTERED)
		return -ESTALE;
	result = kd_state_link_grant(state, binding, &call->grant);
	if (result)
		return result;
	result = kd_operation_complete(state, binding, &call->acquisition_identity);
	if (result)
		return result;
	return kd_operation_return(state, binding, &call->acquisition_identity,
				   call->driver->stack);
}

static enum kd_mutex_outcome execute_selected(struct kd_mutex_node *node,
					       void *context)
{
	struct kd_jit_mutex_call *call = context;
	struct kd_execution_binding *binding = &call->execution;
	enum kd_mutex_outcome outcome;
	int result;

	result = accept_selected(node, context);
	BUG_ON(result);
	result = finish_acquisition(call, binding);
	BUG_ON(result);
	outcome = call->driver->run(call, &binding, call->driver->context);
	BUG_ON(outcome < KD_MUTEX_PROXY_OPERATION_DONE ||
	       outcome > KD_MUTEX_PROXY_UNWIND_PARENT);
	if (outcome != KD_MUTEX_PROXY_ORIGIN_SUFFIX) {
		/* The callback stopped source; export current state, never old state. */
		result = kd_state_transfer(node->state, binding, &call->returned);
		BUG_ON(result);
	}
	result = kd_jit_mutex_leave(call);
	BUG_ON(result);
	return outcome;
}

static const struct kd_mutex_ops source_ops = {
	.selected_local = accept_selected,
	.execute_proxy = execute_selected,
};

int kd_jit_mutex_call_init(struct kd_jit_mutex_call *call,
		 struct kd_thread_state *state,
		 const struct kd_jit_mutex_driver *driver, bool ready)
{
	int result;

	if (!call || !state || !driver || !driver->run || !driver->stack ||
	    !driver->stack->read_word || !driver->stack->write_word ||
	    !driver->origin_binding || driver->origin_binding->state != state ||
	    driver->origin_binding->task != state->origin ||
	    driver->origin_binding->kind != KD_EXECUTION_NATIVE)
		return -EINVAL;
	if (!kd_task_state_own())
		return -ENOENT;
	call->driver = driver;
	kd_task_borrow_scope_init(&call->borrow_scope);
	kd_mutex_batch_init(&call->possible_batch);
	result = kd_execution_binding_init(&call->offer, state, NULL, call,
					   KD_EXECUTION_OFFER);
	if (result)
		return result;
	result = kd_execution_binding_init(&call->returned, state, current, call,
					   KD_EXECUTION_JIT);
	if (result)
		return result;
	kd_source_grant_init(&call->grant, state, NULL,
		&call->acquisition_identity, &call->node.release, &call->grant,
		drop_grant, call);
	return kd_mutex_node_init(&call->node, state, &call->acquisition_identity,
		&call->acquisition_identity, &call->grant, &call->result_identity,
		ready, &source_ops, call);
}

int kd_jit_capture_mutex_lock(struct kd_jit_mutex_call *call,
		 struct kd_execution_binding *native_binding,
		 struct kd_execution_binding *capture_binding, struct kd_mutex *lock,
		 unsigned long source_sp, unsigned long continuation_ip,
		 unsigned long source_bp, unsigned long api_target)
{
	struct kd_thread_state *state = call->node.state;
	int result;

	if (!kd_state_is_current(state, native_binding) ||
	    native_binding->kind != KD_EXECUTION_NATIVE || current != state->origin)
		return -EPERM;
	if (kd_task_state_own() != state || kd_task_state_active() != state)
		return -ESTALE;
	if (!capture_binding || !lock || !api_target || !continuation_ip ||
	    call->node.enqueued || call->node.requester != current ||
	    capture_binding == native_binding || capture_binding == &call->offer ||
	    capture_binding == &call->execution || capture_binding == &call->returned)
		return -EINVAL;
	if (state->exit_image ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	result = kd_execution_binding_init(capture_binding, state, current, call,
					   KD_EXECUTION_JIT);
	if (result)
		return result;
	result = kd_state_transfer(state, native_binding, capture_binding);
	if (result)
		return result;
	/* The compiler-clobber prefix declares only these source inputs. The
	 * C argument DI is the lock pointer for the source operation bridge.
	 * Other packet GPRs are not reconstructed from the executor's registers.
	 */
	state->regs.sp = source_sp;
	state->regs.ip = continuation_ip;
	state->regs.bp = source_bp;
	state->regs.di = (unsigned long)lock;
	return kd_operation_begin(state, capture_binding,
		&call->acquisition_identity, KD_OPERATION_MUTEX_LOCK,
		KD_OPERATION_CAPTURED_CONTINUATION, 0, api_target, continuation_ip);
}

int kd_jit_mutex_acquire(struct kd_jit_mutex_call *call,
		 struct kd_mutex *lock, struct kd_execution_binding **binding,
		 unsigned int proxy_limit, enum kd_mutex_outcome *outcome)
{
	struct kd_thread_state *state = call->node.state;
	int result;

	if (!binding || !kd_state_is_jit_current(state, *binding))
		return -EPERM;
	if (!outcome || !lock || call->node.enqueued ||
	    (void *)state->regs.di != lock ||
	    state->operation.identity != &call->acquisition_identity ||
	    state->operation.kind != KD_OPERATION_MUTEX_LOCK)
		return -EINVAL;
	result = kd_operation_enter(state, *binding, &call->acquisition_identity);
	if (result)
		return result;
	call->grant.object = lock;
	result = kd_state_publish(state, *binding, &call->offer);
	BUG_ON(result);
	/* All storage/forward-route resources were reserved before publication. */
	result = kd_mutex_acquire(lock, &call->node, &call->possible_batch,
				  proxy_limit, outcome);
	BUG_ON(result);
	if (*outcome == KD_MUTEX_LOCAL_GRANTED) {
		*binding = &call->execution;
		return finish_acquisition(call, *binding);
	}
	if (*outcome == KD_MUTEX_PROXY_ORIGIN_SUFFIX) {
		/* W may already advance after the terminal transfer. Its completed
		 * return protocol, not a later snapshot of state.binding, is proof.
		 */
		*binding = NULL;
		return 0;
	}
	/* Proxy source may have completed many newer operations. Never finish the
	 * old lock again or import its saved operation into the canonical core.
	 */
	*binding = &call->returned;
	return kd_state_is_jit_current(state, *binding) ? 0 : -ESTALE;
}

int kd_jit_mutex_leave(struct kd_jit_mutex_call *call)
{
	return call->borrow_scope.active ? kd_task_borrow_leave(&call->borrow_scope) : 0;
}

int kd_jit_mutex_unlock(struct kd_jit_mutex_call *call,
		 struct kd_execution_binding *binding,
		 struct kd_mutex_batch *active_batch, const void *notifier,
		 enum kd_mutex_unlock_action *action)
{
	struct kd_thread_state *state = call->node.state;
	struct kd_source_grant *grant;
	int result;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (state->operation.identity != &call->unlock_identity ||
	    state->operation.kind != KD_OPERATION_MUTEX_UNLOCK)
		return -ESTALE;
	grant = kd_state_find_grant(state, binding, (void *)state->regs.di);
	if (IS_ERR(grant))
		return PTR_ERR(grant);
	if (grant != &call->grant)
		return -ESTALE;
	result = kd_operation_enter(state, binding, &call->unlock_identity);
	if (result)
		return result;
	result = kd_mutex_source_unlock(&call->node, state, active_batch,
					notifier, action);
	if (result)
		return result;
	result = kd_state_close_grant(state, binding, grant);
	if (result)
		return result;
	result = kd_operation_complete(state, binding, &call->unlock_identity);
	if (result)
		return result;
	return kd_operation_return(state, binding, &call->unlock_identity,
				   call->driver->stack);
}

int kd_jit_collect_grants(struct kd_thread_state *state,
		 struct kd_execution_binding *binding)
{
	struct kd_source_grant *grant, *next;
	int result;

	if (!kd_state_is_current(state, binding))
		return -EPERM;
	list_for_each_entry_safe(grant, next, &state->grants, state_link) {
		if (grant->logical_open)
			continue;
		result = kd_state_unlink_grant(state, binding, grant);
		if (result && result != -EAGAIN)
			return result;
	}
	return 0;
}

int kd_jit_mutex_result_done(struct kd_jit_mutex_call *call)
{
	struct kd_thread_state *state = call->node.state;
	struct kd_execution_binding *binding;

	if (!smp_load_acquire(&call->node.result_ready))
		return -EAGAIN;
	if (call->borrow_scope.active)
		return -EBUSY;
	/* Observe result publication before sampling its final binding route. */
	binding = kd_state_current_binding(state);
	/* The caller has closed all other binding observers before this drop. */
	if (binding == &call->offer || binding == &call->execution ||
	    binding == &call->returned)
		return -EBUSY;
	return kd_mutex_result_consumed(&call->node, &call->result_identity);
}
