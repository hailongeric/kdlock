// SPDX-License-Identifier: GPL-2.0-only
/* Original-backend invocation and exact typed source-operation bridges. */
#include <linux/bug.h>
#include <linux/compiler.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/sched.h>
#include <linux/preempt.h>
#include <asm/msr.h>
#include <asm/msr-index.h>

#include "jit.h"

static bool image_valid(const struct kd_jit_image *image)
{
	return image && image->source_identity && image->feedback_producer && image->entry &&
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

static int pending_image(struct kd_thread_state *state,
			 struct kd_execution_binding *binding,
			 const struct kd_jit_image *expected,
			 const struct kd_jit_image **image)
{
	const struct kd_jit_image *producer;
	int result;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!expected || !state->exit_image || !state->exit_use || !state->exit_holder)
		return -ESTALE;
	result = kd_jit_image_use_check_exit(state->exit_use, state->exit_holder,
					    state, &producer);
	if (result)
		return result;
	if (producer != expected || producer != state->exit_image)
		return -ESTALE;
	*image = producer;
	return 0;
}

static int drop_pending_exit(struct kd_thread_state *state,
			     struct kd_execution_binding *binding)
{
	const struct kd_jit_image *image;
	struct kd_jit_image_use *use;
	const void *holder;
	int result;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	result = pending_image(state, binding, state->exit_image, &image);
	if (result)
		return result;
	use = state->exit_use;
	holder = state->exit_holder;
	/* Close canonical observers before the exact final image user is dropped.
	 * No image/use access may follow success. Failure did not unlink anything.
	 */
	state->exit_image = NULL;
	state->exit_use = NULL;
	state->exit_holder = NULL;
	result = kd_jit_image_use_finish_exit(use, holder, state);
	if (result) {
		state->exit_image = image;
		state->exit_use = use;
		state->exit_holder = holder;
	}
	return result;
}

int kd_jit_enter(struct kd_jit_image_use *execution_use,
		 const void *execution_holder,
		 struct kd_jit_image_use *exit_use, const void *exit_holder,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding)
{
	const struct kd_jit_image *image;
	unsigned int i;
	int result, drop_result;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (current == state->origin)
		return -EXDEV;
	if (state->exit_image || state->exit_use || state->exit_holder ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	result = kd_jit_image_use_prepare_exit(execution_use, execution_holder,
					      state, exit_use, exit_holder, &image);
	if (result)
		return result;
	state->exit_image = image;
	state->exit_use = exit_use;
	state->exit_holder = exit_holder;
	if (!image_valid(image)) {
		result = -EINVAL;
		goto refused;
	}
	for (i = 0; i < image->entry_count; i++)
		if (image->entry_sites[i] == state->regs.ip)
			break;
	if (i == image->entry_count) {
		result = -ENOENT;
		goto refused;
	}

	state->io.origin_gs = state->origin_gs;
	state->io.origin_task = (unsigned long)state->origin;
	state->io.kind = KD_JIT_EXIT_NONE;
	state->io.detail = KD_JIT_DETAIL_NONE;
	state->io.source_ip = 0;
	state->io.target = 0;
	state->io.phase = KD_JIT_PHASE_BEFORE_INSTRUCTION;
	/* The distinct claimed child retains code across this call and the exit.
	 * No image guard or RCU read-side section spans source execution.
	 */
	image->entry(&state->regs, &state->io);
	if (!kd_state_is_jit_current(state, binding))
		return -ESTALE;
	if (state->io.kind < KD_JIT_EXIT_LOCK_OPERATION ||
	    state->io.kind > KD_JIT_EXIT_INVARIANT_FAILURE ||
	    state->io.phase > KD_JIT_PHASE_JUMP_RESOLVED)
		return -EUCLEAN;
	return 0;
refused:
	/* No source instruction ran. Preserve the exact claim if its drop fails. */
	drop_result = drop_pending_exit(state, binding);
	return drop_result ? drop_result : result;
}

int kd_jit_prepare_operation(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding, const void *identity,
		 kd_jit_resolve_operation_fn resolve, void *context,
		 const struct kd_source_stack_ops *stack)
{
	const struct kd_jit_source_site *site;
	const struct kd_jit_image *producer;
	enum kd_operation_form form;
	enum kd_operation_kind kind;
	unsigned long target, return_ip = 0;
	int result;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!resolve || !identity)
		return -EINVAL;
	result = pending_image(state, binding, image, &producer);
	if (result)
		return result;
	image = producer;
	if (!image_valid(image))
		return -EINVAL;
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
	/* A resolver cannot transfer source rights; revalidate before IO reads. */
	if (!kd_state_is_jit_current(state, binding))
		return -ESTALE;
	if (kind == KD_OPERATION_NONE)
		return -ENOENT;
	if (!kd_operation_is_lock(kind) && !kd_operation_is_unlock(kind) &&
	    !kd_operation_is_mode_change(kind))
		return -EOPNOTSUPP;
	if (state->io.kind == KD_JIT_EXIT_LOCK_OPERATION &&
	    ((state->io.detail == KD_JIT_OP_LOCK && !kd_operation_is_lock(kind)) ||
	     (state->io.detail == KD_JIT_OP_UNLOCK && !kd_operation_is_unlock(kind)) ||
	     (state->io.detail == KD_JIT_OP_MODE_CHANGE && !kd_operation_is_mode_change(kind))))
		return -EOPNOTSUPP;
	result = kd_operation_begin(state, binding, identity, kind, form,
				    state->io.source_ip, target, return_ip);
	if (result)
		return result;
	/* The single operation descriptor now retains every required scalar.
	 * Finish all image metadata access before releasing the pending use.
	 */
	result = drop_pending_exit(state, binding);
	if (result)
		return result;
	state->io.kind = KD_JIT_EXIT_NONE;
	state->io.phase = KD_JIT_PHASE_BEFORE_INSTRUCTION;
	if (form == KD_OPERATION_NEW_CALL)
		return kd_operation_stage_call(state, binding, identity, stack);
	return 0;
}

int kd_jit_consume_exit(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding)
{
	const struct kd_jit_image *producer;
	int result = pending_image(state, binding, image, &producer);

	if (result)
		return result;
	if (state->io.phase == KD_JIT_PHASE_TARGET_READY)
		return -EBUSY;
	result = drop_pending_exit(state, binding);
	if (result)
		return result;
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
	const struct kd_jit_image *producer;
	unsigned long source_sp, return_ip;
	int result;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!stack || !stack->write_word)
		return -EINVAL;
	result = pending_image(state, binding, image, &producer);
	if (result)
		return result;
	image = producer;
	if (!image_valid(image))
		return -EINVAL;
	if (state->operation.phase != KD_OPERATION_IDLE &&
	    state->operation.phase != KD_OPERATION_RESUMABLE)
		return -EBUSY;
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
	return_ip = site->next_ip;
	source_sp = state->regs.sp - sizeof(unsigned long);
	stack->write_word(stack->context, source_sp, return_ip);
	state->regs.sp = source_sp;
	state->regs.ip = state->io.target;
	state->io.phase = KD_JIT_PHASE_CALL_STAGED;
	/* No metadata read or repeated target evaluation follows the one push. */
	return drop_pending_exit(state, binding);
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
	if (state->exit_image || state->exit_use || state->exit_holder ||
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
	if (kd_task_state_own() != state)
		return -ESTALE;
	if (state->exit_image || state->exit_use || state->exit_holder ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	kd_native_resume(&state->regs);
}

static int drop_grant(void *control, const void *user)
{
	struct kd_jit_mutex_call *call = control;
	struct kd_mutex_node *node = &call->node;
	struct kd_rw_read_credit *credit = call->grant.read_credit;
	struct kd_thread_state *state = node->state;
	const void *acquisition = call->grant.acquisition;
	int result;

	if (credit) {
		/* Released-credit validation owns no hidden finalizer. Its immutable
		 * history remains if the exact node source-user drop reports failure.
		 */
		result = kd_rw_read_credit_unlink(credit, state, acquisition, user);
		if (result)
			return result;
	}
	/* Success can permit call retirement; do not access call afterward. */
	return kd_mutex_grant_unlinked(node, user);
}

struct kd_jit_mutex_call *kd_jit_mutex_grant_call(const struct kd_source_grant *grant)
{
	struct kd_jit_mutex_call *call;

	/* A generic grant may belong to another provider. Prove the constructor
	 * relationship before interpreting its containing allocation as a call.
	 * The retained grant's immutable provider/control fields supply this type.
	 */
	if (!grant || grant->drop != drop_grant || !grant->control)
		return ERR_PTR(-EOPNOTSUPP);
	call = grant->control;
	if (&call->grant != grant || call->node.state != grant->state ||
	    grant->release != &call->node.release ||
	    grant->acquisition != &call->acquisition_identity ||
	    call->node.acquisition != grant->acquisition ||
	    grant->user != grant || call->node.grant_user != grant ||
	    (grant->read_credit && grant->read_credit != &call->read_credit))
		return ERR_PTR(-ESTALE);
	return call;
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
	return kd_state_accept(node->state, &call->offer, &call->execution);
}

static int accept_local(struct kd_mutex_node *node, void *context)
{
	struct kd_jit_mutex_call *call = context;
	int result = accept_selected(node, context);

	if (result || !call->driver->selected_local)
		return result;
	return call->driver->selected_local(call, call->driver->context);
}

static int progress_wait(struct kd_mutex_node *node, void *context,
			 bool *blocked)
{
	struct kd_jit_mutex_call *call = context;

	if (node != &call->node)
		return -ESTALE;
	*blocked = false;
	if (!call->driver->wait_progress)
		return 0;
	return call->driver->wait_progress(call, call->driver->context, blocked);
}

static bool progress_ready(struct kd_mutex_node *node, void *context)
{
	struct kd_jit_mutex_call *call = context;

	return node == &call->node && call->driver->wait_ready &&
	       call->driver->wait_ready(call, call->driver->context);
}

static int finish_acquisition(struct kd_jit_mutex_call *call,
			       struct kd_execution_binding *binding)
{
	struct kd_thread_state *state = call->node.state;
	int result;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!kd_operation_is_lock(state->operation.kind) ||
	    kd_operation_family(state->operation.kind) != call->grant.family ||
	    kd_operation_is_read(state->operation.kind) != (call->grant.mode == KD_GRANT_MODE_READ) ||
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

int kd_jit_mutex_drive(struct kd_jit_mutex_call *call,
		 struct kd_execution_binding **binding, enum kd_mutex_outcome *outcome)
{
	enum kd_mutex_outcome stopped;
	int result;

	if (!call || !binding || !outcome)
		return -EPERM;
	if (call->drive_started)
		return -EALREADY;
	if (!kd_state_is_jit_current(call->node.state, *binding))
		return -EPERM;
	/* One immutable returned endpoint belongs to exactly this run attempt. */
	call->drive_started = true;
	stopped = call->driver->run(call, binding, call->driver->context);
	if (stopped < KD_MUTEX_PROXY_OPERATION_DONE ||
	    stopped > KD_MUTEX_PROXY_UNWIND_PARENT)
		return -EUCLEAN;
	if (stopped != KD_MUTEX_PROXY_ORIGIN_SUFFIX) {
		/* The callback stopped source; export current state, never old state.
		 * This return endpoint has not been used for an earlier episode.
		 */
		result = kd_state_transfer(call->node.state, *binding, &call->returned);
		if (result)
			return result;
		*binding = &call->returned;
	} else {
		/* The terminal route was transferred before run returned. The old
		 * control must not sample the now-native source packet or binding.
		 */
		*binding = NULL;
	}
	if (call->driver->exported) {
		result = call->driver->exported(call, stopped, call->driver->context);
		if (result)
			return result;
	}
	*outcome = stopped;
	return 0;
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
	/* Register a newly owned physical head once. A later cohort request
	 * belongs to that existing head and must not register unused storage.
	 */
	if (node->batch && node->batch->head == node && call->driver->selected_local) {
		result = call->driver->selected_local(call, call->driver->context);
		BUG_ON(result);
	}
	result = finish_acquisition(call, binding);
	BUG_ON(result);
	result = kd_jit_mutex_drive(call, &binding, &outcome);
	BUG_ON(result);
	return outcome;
}

static const struct kd_mutex_ops source_ops = {
	.selected_local = accept_local,
	.execute_proxy = execute_selected,
	.wait_progress = progress_wait,
	.wait_ready = progress_ready,
};

int kd_jit_mutex_call_init(struct kd_jit_mutex_call *call,
		 struct kd_thread_state *state,
		 const struct kd_jit_mutex_driver *driver, bool ready)
{
	enum kd_lock_family family;
	bool atomic_context;
	int result;

	if (!call || !state || !driver)
		return -EINVAL;
	family = driver->family;
	if (family == KD_LOCK_FAMILY_MUTEX && driver->atomic_spin)
		family = KD_LOCK_FAMILY_SPIN;
	atomic_context = kd_lock_family_is_atomic(family);
	if ((unsigned int)family >= KD_LOCK_FAMILY_COUNT ||
	    (driver->mode != KD_GRANT_MODE_WRITE && driver->mode != KD_GRANT_MODE_READ) ||
	    (driver->mode == KD_GRANT_MODE_READ && family != KD_LOCK_FAMILY_RWSEM &&
	     family != KD_LOCK_FAMILY_RWLOCK) ||
	    !driver->run || !driver->stack ||
	    (!!driver->wait_progress != !!driver->wait_ready) ||
	    (atomic_context && (!driver->selected_local || !driver->wait_progress ||
	     !driver->exported)) ||
	    !driver->stack->read_word || !driver->stack->write_word ||
	    !driver->origin_binding || driver->origin_binding->state != state ||
	    driver->origin_binding->task != state->origin ||
	    driver->origin_binding->kind != KD_EXECUTION_NATIVE)
		return -EINVAL;
	if (!kd_task_state_own())
		return -ENOENT;
	call->driver = driver;
	call->drive_started = false;
	kd_mutex_batch_init(&call->possible_batch);
	kd_rw_read_credit_init(&call->read_credit);
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
	call->grant.family = family;
	call->grant.mode = driver->mode;
	call->grant.physical = driver->mode == KD_GRANT_MODE_READ ?
		KD_GRANT_PHYSICAL_READ : KD_GRANT_PHYSICAL_WRITE;
	call->grant.read_credit = driver->mode == KD_GRANT_MODE_READ ? &call->read_credit : NULL;
	result = kd_mutex_node_init(&call->node, state, &call->acquisition_identity,
		&call->acquisition_identity, &call->grant, &call->result_identity,
		ready, &source_ops, call);
	if (!result) {
		call->node.atomic_spin = atomic_context;
		call->node.possible_batch = &call->possible_batch;
	}
	return result;
}

static int capture_mutex_operation(struct kd_jit_mutex_call *call,
		 const void *identity, enum kd_operation_kind kind,
		 struct kd_execution_binding *native_binding,
		 struct kd_execution_binding *capture_binding, void *object,
		 unsigned long source_sp, unsigned long continuation_ip,
		 unsigned long source_bp, unsigned long api_target)
{
	struct kd_thread_state *state = call->node.state;
	unsigned long origin_gs;
	int result;

	if (!kd_state_is_current(state, native_binding) ||
	    native_binding->kind != KD_EXECUTION_NATIVE || current != state->origin)
		return -EPERM;
	if (kd_task_state_own() != state)
		return -ESTALE;
	if (!identity || (!kd_operation_is_lock(kind) && !kd_operation_is_unlock(kind)) ||
	    kd_operation_family(kind) != call->grant.family || !capture_binding || !object ||
	    !api_target || !continuation_ip ||
	    call->node.enqueued || call->node.requester != current ||
	    capture_binding == native_binding ||
	    capture_binding == call->driver->origin_binding ||
	    capture_binding == &call->offer || capture_binding == &call->execution ||
	    capture_binding == &call->returned)
		return -EINVAL;
	if (state->exit_image || state->exit_use || state->exit_holder ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	result = kd_execution_binding_init(capture_binding, state, current, call,
					   KD_EXECUTION_JIT);
	if (result)
		return result;
	/* Capture this publication's active kernel GS, not attachment-time CPU
	 * state. This short non-sleeping interval ends before lock arbitration;
	 * it grants no episode-wide migration or per-CPU exclusion guarantee.
	 */
	preempt_disable();
	rdmsrl(MSR_GS_BASE, origin_gs);
	result = kd_state_transfer(state, native_binding, capture_binding);
	if (result) {
		preempt_enable();
		return result;
	}
	/* The compiler-clobber prefix declares SP/IP/BP and DI object. Other
	 * source GPRs are not reconstructed from the executor's registers.
	 */
	state->origin_gs = origin_gs;
	state->regs.sp = source_sp;
	state->regs.ip = continuation_ip;
	state->regs.bp = source_bp;
	state->regs.di = (unsigned long)object;
	result = kd_operation_begin(state, capture_binding, identity, kind,
		KD_OPERATION_CAPTURED_CONTINUATION, 0, api_target, continuation_ip);
	preempt_enable();
	return result;
}

int kd_jit_capture_lock(struct kd_jit_mutex_call *call,
		struct kd_execution_binding *native_binding,
		struct kd_execution_binding *capture_binding, void *object,
		enum kd_operation_kind operation, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp,
		unsigned long api_target)
{
	if (!call || !kd_operation_is_lock(operation) ||
	    kd_operation_is_read(operation) != (call->grant.mode == KD_GRANT_MODE_READ))
		return -EINVAL;
	return capture_mutex_operation(call, &call->acquisition_identity, operation,
		native_binding, capture_binding, object, source_sp, continuation_ip,
		source_bp, api_target);
}

int kd_jit_capture_mutex_lock(struct kd_jit_mutex_call *call,
		 struct kd_execution_binding *native_binding,
		 struct kd_execution_binding *capture_binding, struct kd_mutex *lock,
		 unsigned long source_sp, unsigned long continuation_ip,
		 unsigned long source_bp, unsigned long api_target)
{
	return kd_jit_capture_lock(call, native_binding, capture_binding, lock,
		call->node.atomic_spin ? KD_OPERATION_SPIN_LOCK : KD_OPERATION_MUTEX_LOCK,
		source_sp, continuation_ip, source_bp, api_target);
}

int kd_jit_capture_mutex_unlock(struct kd_jit_mutex_call *control,
		 struct kd_jit_mutex_call *acquisition,
		 struct kd_execution_binding *native_binding,
		 struct kd_execution_binding *capture_binding, struct kd_mutex *lock,
		 unsigned long source_sp, unsigned long continuation_ip,
		 unsigned long source_bp, unsigned long api_target)
{
	if (!control || !acquisition || control == acquisition ||
	    control->node.state != acquisition->node.state)
		return -EINVAL;
	return capture_mutex_operation(control, &acquisition->unlock_identity,
		control->node.atomic_spin ? KD_OPERATION_SPIN_UNLOCK : KD_OPERATION_MUTEX_UNLOCK,
		native_binding, capture_binding, lock,
		source_sp, continuation_ip, source_bp, api_target);
}

static struct kd_rw *call_rw(struct kd_jit_mutex_call *call, void *object)
{
	if (call->grant.family == KD_LOCK_FAMILY_RWSEM)
		return &((struct kd_rwsem *)object)->core;
	if (call->grant.family == KD_LOCK_FAMILY_RWLOCK)
		return &((struct kd_rwlock *)object)->core;
	return NULL;
}

static int read_progress(void *context, bool *blocked)
{
	struct kd_jit_mutex_call *call = context;

	return progress_wait(&call->node, call, blocked);
}

static bool read_ready(void *context)
{
	struct kd_jit_mutex_call *call = context;

	return progress_ready(&call->node, call);
}

static const struct kd_rw_wait_ops read_wait_ops = {
	.progress = read_progress,
	.ready = read_ready,
};

int kd_jit_acquire(struct kd_jit_mutex_call *call, void *object,
		struct kd_execution_binding **binding, unsigned int proxy_limit,
		enum kd_mutex_outcome *outcome)
{
	struct kd_thread_state *state;
	struct kd_rw *rw;
	int result;

	if (!call || !binding || !outcome || !object)
		return -EINVAL;
	state = call->node.state;
	if (!kd_state_is_jit_current(state, *binding))
		return -EPERM;
	if (call->node.enqueued || call->node.source_granted ||
	    (void *)state->regs.di != object ||
	    state->operation.identity != &call->acquisition_identity ||
	    !kd_operation_is_lock(state->operation.kind) ||
	    kd_operation_family(state->operation.kind) != call->grant.family ||
	    kd_operation_is_read(state->operation.kind) != (call->grant.mode == KD_GRANT_MODE_READ))
		return -EINVAL;
	rw = call_rw(call, object);
	if (call->grant.mode == KD_GRANT_MODE_READ && !rw)
		return -EINVAL;
	if (rw && call->grant.mode == KD_GRANT_MODE_WRITE) {
		result = kd_rw_write_prepare(rw, &call->node, call->node.atomic_spin);
		if (result)
			return result;
	}
	result = kd_operation_enter(state, *binding, &call->acquisition_identity);
	if (result)
		return result;
	call->grant.object = object;
	if (call->grant.mode == KD_GRANT_MODE_READ) {
		/* Shared acquisition stays on the current executor. There is no
		 * reader MCS offer or invented exclusive physical owner.
		 */
		result = kd_rw_read_acquire(rw, &call->read_credit, state, *binding,
			&call->acquisition_identity, &call->grant, call->node.atomic_spin,
			&read_wait_ops, call);
		if (result)
			return result;
		result = kd_mutex_read_granted(&call->node);
		BUG_ON(result);
		result = kd_execution_binding_init(&call->execution, state, current,
			call, KD_EXECUTION_JIT);
		BUG_ON(result);
		result = kd_state_transfer(state, *binding, &call->execution);
		BUG_ON(result);
		*binding = &call->execution;
		result = finish_acquisition(call, *binding);
		if (!result)
			*outcome = KD_MUTEX_LOCAL_GRANTED;
		return result;
	}
	result = kd_state_publish(state, *binding, &call->offer);
	BUG_ON(result);
	/* All storage/forward-route resources preceded this stopped offer. */
	result = rw ? kd_rw_write_acquire(rw, &call->node, &call->possible_batch,
					proxy_limit, outcome) :
		kd_mutex_acquire(object, &call->node, &call->possible_batch, proxy_limit, outcome);
	BUG_ON(result);
	if (*outcome == KD_MUTEX_LOCAL_GRANTED) {
		*binding = &call->execution;
		return finish_acquisition(call, *binding);
	}
	if (*outcome == KD_MUTEX_PROXY_ORIGIN_SUFFIX) {
		*binding = NULL;
		return 0;
	}
	/* A proxy may already have completed newer source operations. */
	*binding = &call->returned;
	return kd_state_is_jit_current(state, *binding) ? 0 : -ESTALE;
}

int kd_jit_mutex_acquire(struct kd_jit_mutex_call *call,
		 struct kd_mutex *lock, struct kd_execution_binding **binding,
		 unsigned int proxy_limit, enum kd_mutex_outcome *outcome)
{
	return kd_jit_acquire(call, lock, binding, proxy_limit, outcome);
}

static int release_grant(struct kd_jit_mutex_call *call,
		struct kd_execution_binding *binding, enum kd_operation_kind operation,
		struct kd_mutex_batch *active_batch, const void *notifier,
		enum kd_mutex_unlock_action *action)
{
	struct kd_thread_state *state = call->node.state;
	struct kd_source_grant *grant;
	int result;

	if (!action || !kd_state_is_current(state, binding))
		return -EPERM;
	if (!kd_operation_is_unlock(operation) || kd_operation_family(operation) != call->grant.family)
		return -ESTALE;
	grant = kd_state_find_operation_grant(state, binding, call->grant.object, operation);
	if (IS_ERR(grant))
		return PTR_ERR(grant);
	if (grant != &call->grant)
		return -ESTALE;
	if (grant->physical == KD_GRANT_PHYSICAL_READ) {
		result = kd_rw_read_release(grant->read_credit, state, binding,
			grant->acquisition, grant->user);
		if (result)
			return result;
		*action = kd_operation_is_atomic(operation) ? KD_MUTEX_UNLOCK_ATOMIC : KD_MUTEX_UNLOCK_SYNC;
	} else if (grant->mode == KD_GRANT_MODE_RETAINED_READ) {
		/* Matching retained up_read ends this writer episode. Close the
		 * cohort and observe its physical ACK before terminal W handback,
		 * including when this callback is the active physical owner.
		 */
		result = kd_mutex_source_release_sync(&call->node, state, action);
		if (result)
			return result;
	} else {
		result = kd_mutex_source_unlock(&call->node, state, active_batch, notifier, action);
		if (result)
			return result;
	}
	return kd_state_close_grant(state, binding, grant);
}

int kd_jit_unlock(struct kd_jit_mutex_call *call,
		struct kd_execution_binding *binding,
		struct kd_mutex_batch *active_batch, const void *notifier,
		enum kd_mutex_unlock_action *action)
{
	struct kd_thread_state *state;
	int result;

	if (!call || !action)
		return -EINVAL;
	state = call->node.state;
	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (state->operation.identity != &call->unlock_identity ||
	    !kd_operation_is_unlock(state->operation.kind) ||
	    kd_operation_family(state->operation.kind) != call->grant.family ||
	    (void *)state->regs.di != call->grant.object)
		return -ESTALE;
	result = kd_operation_enter(state, binding, &call->unlock_identity);
	if (result)
		return result;
	result = release_grant(call, binding, state->operation.kind, active_batch, notifier, action);
	if (result)
		return result;
	result = kd_operation_complete(state, binding, &call->unlock_identity);
	if (result)
		return result;
	return kd_operation_return(state, binding, &call->unlock_identity, call->driver->stack);
}

int kd_jit_mutex_unlock(struct kd_jit_mutex_call *call,
		 struct kd_execution_binding *binding,
		 struct kd_mutex_batch *active_batch, const void *notifier,
		 enum kd_mutex_unlock_action *action)
{
	return kd_jit_unlock(call, binding, active_batch, notifier, action);
}

int kd_jit_unlock_native(struct kd_jit_mutex_call *call,
		struct kd_execution_binding *native_binding,
		enum kd_operation_kind operation, const void *notifier,
		enum kd_mutex_unlock_action *action)
{
	struct kd_mutex_batch *active = NULL;
	struct kd_mutex_release_owner *owner;

	if (!call || !kd_state_is_current(call->node.state, native_binding) ||
	    native_binding->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	if (call->grant.physical == KD_GRANT_PHYSICAL_WRITE) {
		owner = READ_ONCE(call->node.release.owner);
		if (!owner)
			return -ESTALE;
		if (owner->task == current)
			active = call->node.batch;
	}
	/* The actual native source CALL/RET and registers remain untouched. */
	return release_grant(call, native_binding, operation, active, notifier, action);
}

static int downgrade_grant(struct kd_jit_mutex_call *call,
		struct kd_execution_binding *binding, bool retained)
{
	struct kd_thread_state *state = call->node.state;
	struct kd_source_grant *grant;
	int result;

	grant = kd_state_find_grant_typed(state, binding, call->grant.object,
		KD_LOCK_FAMILY_RWSEM, KD_GRANT_MODE_WRITE);
	if (IS_ERR(grant))
		return PTR_ERR(grant);
	if (grant != &call->grant || grant->physical != KD_GRANT_PHYSICAL_WRITE)
		return -ESTALE;
	if (retained)
		result = kd_rw_write_held(&call->node, state);
	else
		result = kd_rw_write_downgrade(&call->node, &call->read_credit, state, binding,
			grant->acquisition, grant->user);
	if (result)
		return result;
	return kd_state_downgrade_grant(state, binding, grant,
		retained ? NULL : &call->read_credit, retained);
}

int kd_jit_downgrade(struct kd_jit_mutex_call *call,
		struct kd_execution_binding *binding, bool retained)
{
	struct kd_thread_state *state;
	int result;

	if (!call)
		return -EINVAL;
	state = call->node.state;
	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (state->operation.identity != &call->mode_identity ||
	    state->operation.kind != KD_OPERATION_RWSEM_DOWNGRADE_WRITE ||
	    (void *)state->regs.di != call->grant.object)
		return -ESTALE;
	result = kd_operation_enter(state, binding, &call->mode_identity);
	if (result)
		return result;
	result = downgrade_grant(call, binding, retained);
	if (result)
		return result;
	result = kd_operation_complete(state, binding, &call->mode_identity);
	if (result)
		return result;
	return kd_operation_return(state, binding, &call->mode_identity, call->driver->stack);
}

int kd_jit_downgrade_native(struct kd_jit_mutex_call *call,
		struct kd_execution_binding *native_binding)
{
	if (!call || !kd_state_is_current(call->node.state, native_binding) ||
	    native_binding->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	return downgrade_grant(call, native_binding, false);
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
	/* Observe result publication before sampling its final binding route. */
	binding = kd_state_current_binding(state);
	/* The caller has closed all other binding observers before this drop. */
	if (binding == &call->offer || binding == &call->execution ||
	    binding == &call->returned)
		return -EBUSY;
	return kd_mutex_result_consumed(&call->node, &call->result_identity);
}
