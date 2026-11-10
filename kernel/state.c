// SPDX-License-Identifier: GPL-2.0-only
/* Canonical state, exact source-call effects and referring grant lifetimes. */
#include <linux/atomic.h>
#include <linux/compiler.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/sched.h>

#include "state.h"

int kd_execution_binding_init(struct kd_execution_binding *binding,
			      struct kd_thread_state *state,
			      struct task_struct *task, const void *control,
			      enum kd_execution_kind kind)
{
	if (!state || !control ||
	    (kind != KD_EXECUTION_NATIVE && kind != KD_EXECUTION_JIT &&
	     kind != KD_EXECUTION_OFFER) ||
	    (kind == KD_EXECUTION_OFFER ? task != NULL : task == NULL))
		return -EINVAL;
	binding->state = state;
	binding->task = task;
	binding->control = control;
	binding->kind = kind;
	return 0;
}

int kd_state_init(struct kd_thread_state *state, struct task_struct *origin,
		  unsigned long origin_gs,
		  struct kd_execution_binding *native_binding)
{
	if (!state || !origin || !native_binding || native_binding->state != state ||
	    native_binding->task != origin ||
	    native_binding->kind != KD_EXECUTION_NATIVE)
		return -EINVAL;
	state->origin = origin;
	state->origin_gs = origin_gs;
	state->io.origin_gs = origin_gs;
	state->io.origin_task = (unsigned long)origin;
	state->io.kind = KD_JIT_EXIT_NONE;
	state->io.detail = KD_JIT_DETAIL_NONE;
	state->io.source_ip = 0;
	state->io.target = 0;
	state->io.phase = KD_JIT_PHASE_BEFORE_INSTRUCTION;
	state->exit_image = NULL;
	state->operation.identity = NULL;
	state->operation.kind = KD_OPERATION_NONE;
	state->operation.form = KD_OPERATION_NEW_CALL;
	state->operation.phase = KD_OPERATION_IDLE;
	state->operation.source_site = 0;
	state->operation.target = 0;
	state->operation.return_ip = 0;
	INIT_LIST_HEAD(&state->grants);
	/* The canonical regs are captured by the selected entry, not cleared. */
	smp_store_release(&state->binding, native_binding);
	return 0;
}

struct kd_execution_binding *kd_state_current_binding(struct kd_thread_state *state)
{
	return smp_load_acquire(&state->binding);
}

bool kd_state_is_current(struct kd_thread_state *state,
			 struct kd_execution_binding *binding)
{
	if (!binding || kd_state_current_binding(state) != binding)
		return false;
	return binding->state == state && binding->task == current &&
	       binding->kind != KD_EXECUTION_OFFER &&
	       (binding->kind != KD_EXECUTION_NATIVE || binding->task == state->origin);
}

bool kd_state_is_jit_current(struct kd_thread_state *state,
			     struct kd_execution_binding *binding)
{
	return kd_state_is_current(state, binding) &&
	       binding->kind == KD_EXECUTION_JIT;
}

int kd_state_publish(struct kd_thread_state *state,
		     struct kd_execution_binding *from,
		     struct kd_execution_binding *offer)
{
	if (!kd_state_is_current(state, from))
		return -EPERM;
	if (!offer || offer == from || offer->state != state ||
	    offer->kind != KD_EXECUTION_OFFER || offer->task)
		return -EINVAL;
	return cmpxchg_release(&state->binding, from, offer) == from ? 0 : -ESTALE;
}

int kd_state_accept(struct kd_thread_state *state,
		    struct kd_execution_binding *offer,
		    struct kd_execution_binding *execution)
{
	if (!offer || !execution || offer == execution ||
	    offer->state != state || execution->state != state ||
	    offer->kind != KD_EXECUTION_OFFER || execution->task != current ||
	    execution->control != offer->control ||
	    (execution->kind != KD_EXECUTION_JIT &&
	     execution->kind != KD_EXECUTION_NATIVE) ||
	    (execution->kind == KD_EXECUTION_NATIVE && execution->task != state->origin))
		return -EINVAL;
	/* The MCS claim already chose this endpoint; no source work precedes it. */
	return cmpxchg_acquire(&state->binding, offer, execution) == offer ? 0 : -ESTALE;
}

int kd_state_transfer(struct kd_thread_state *state,
		      struct kd_execution_binding *from,
		      struct kd_execution_binding *destination)
{
	if (!kd_state_is_current(state, from))
		return -EPERM;
	if (!destination || destination == from || destination->state != state ||
	    !destination->task ||
	    (destination->kind != KD_EXECUTION_JIT &&
	     destination->kind != KD_EXECUTION_NATIVE) ||
	    (destination->kind == KD_EXECUTION_NATIVE && destination->task != state->origin))
		return -EINVAL;
	return cmpxchg_release(&state->binding, from, destination) == from ? 0 : -ESTALE;
}

static int operation_matches(struct kd_thread_state *state,
			     struct kd_execution_binding *binding,
			     const void *identity)
{
	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!identity || state->operation.identity != identity)
		return -ESTALE;
	return 0;
}

int kd_operation_begin(struct kd_thread_state *state,
		       struct kd_execution_binding *binding,
		       const void *identity, enum kd_operation_kind kind,
		       enum kd_operation_form form, unsigned long source_site,
		       unsigned long target, unsigned long return_ip)
{
	struct kd_source_operation *operation = &state->operation;

	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (!identity || !target ||
	    (kind != KD_OPERATION_MUTEX_LOCK && kind != KD_OPERATION_MUTEX_UNLOCK) ||
	    (form != KD_OPERATION_NEW_CALL && form != KD_OPERATION_EXISTING_CALL &&
	     form != KD_OPERATION_EXISTING_FRAME &&
	     form != KD_OPERATION_CAPTURED_CONTINUATION))
		return -EINVAL;
	if (operation->phase != KD_OPERATION_IDLE &&
	    operation->phase != KD_OPERATION_RESUMABLE)
		return -EBUSY;
	if ((form == KD_OPERATION_NEW_CALL && state->regs.ip != source_site) ||
	    (form == KD_OPERATION_CAPTURED_CONTINUATION &&
	     state->regs.ip != return_ip) ||
	    ((form == KD_OPERATION_EXISTING_CALL || form == KD_OPERATION_EXISTING_FRAME) &&
	     state->regs.ip != target))
		return -ESTALE;
	operation->identity = identity;
	operation->kind = kind;
	operation->form = form;
	operation->source_site = source_site;
	operation->target = target;
	operation->return_ip = return_ip;
	operation->phase = form == KD_OPERATION_NEW_CALL ?
		KD_OPERATION_TARGET_READY : KD_OPERATION_API_READY;
	return 0;
}

int kd_operation_stage_call(struct kd_thread_state *state,
			    struct kd_execution_binding *binding,
			    const void *identity,
			    const struct kd_source_stack_ops *stack)
{
	unsigned long source_sp;
	int result = operation_matches(state, binding, identity);

	if (result)
		return result;
	if (!stack || !stack->write_word)
		return -EINVAL;
	if (state->operation.phase != KD_OPERATION_TARGET_READY ||
	    state->operation.form != KD_OPERATION_NEW_CALL)
		return -EALREADY;
	source_sp = state->regs.sp - sizeof(unsigned long);
	stack->write_word(stack->context, source_sp, state->operation.return_ip);
	state->regs.sp = source_sp;
	state->regs.ip = state->operation.target;
	state->operation.phase = KD_OPERATION_API_READY;
	return 0;
}

int kd_operation_enter(struct kd_thread_state *state,
		       struct kd_execution_binding *binding,
		       const void *identity)
{
	int result = operation_matches(state, binding, identity);

	if (result)
		return result;
	if (state->operation.phase != KD_OPERATION_API_READY)
		return -EALREADY;
	state->operation.phase = KD_OPERATION_ENTERED;
	return 0;
}

int kd_operation_complete(struct kd_thread_state *state,
			  struct kd_execution_binding *binding,
			  const void *identity)
{
	int result = operation_matches(state, binding, identity);

	if (result)
		return result;
	if (state->operation.phase != KD_OPERATION_ENTERED)
		return -EALREADY;
	/* A deferred source unlock may complete while physical duty stays live. */
	state->operation.phase = KD_OPERATION_DONE;
	return 0;
}

int kd_operation_return(struct kd_thread_state *state,
			struct kd_execution_binding *binding,
			const void *identity,
			const struct kd_source_stack_ops *stack)
{
	unsigned long target;
	int result = operation_matches(state, binding, identity);

	if (result)
		return result;
	if (!stack || !stack->read_word)
		return -EINVAL;
	if (state->operation.phase != KD_OPERATION_DONE)
		return -EALREADY;
	if (state->operation.form != KD_OPERATION_CAPTURED_CONTINUATION) {
		target = stack->read_word(stack->context, state->regs.sp);
		state->regs.sp += sizeof(unsigned long);
		state->regs.ip = target;
	}
	state->operation.phase = KD_OPERATION_RESUMABLE;
	/* The handled operation consumed the old exit, including its target. */
	state->exit_image = NULL;
	state->io.kind = KD_JIT_EXIT_NONE;
	state->io.phase = KD_JIT_PHASE_BEFORE_INSTRUCTION;
	return 0;
}

void kd_source_grant_init(struct kd_source_grant *grant,
			  struct kd_thread_state *state, void *object,
			  const void *acquisition,
			  struct kd_mutex_release *release, const void *user,
			  int (*drop)(void *, const void *), void *control)
{
	INIT_LIST_HEAD(&grant->state_link);
	grant->state = state;
	grant->object = object;
	grant->acquisition = acquisition;
	grant->release = release;
	grant->user = user;
	grant->drop = drop;
	grant->control = control;
	grant->linked = false;
	grant->logical_open = false;
}

int kd_state_link_grant(struct kd_thread_state *state,
			struct kd_execution_binding *binding,
			struct kd_source_grant *grant)
{
	struct kd_source_grant *existing;
	struct kd_mutex_release_owner *owner;
	int result = 0;

	if (!kd_state_is_current(state, binding))
		return -EPERM;
	if (!grant || grant->state != state || !grant->object || !grant->acquisition ||
	    !grant->release || !grant->user || !grant->drop || grant->linked)
		return -EINVAL;
	list_for_each_entry(existing, &state->grants, state_link) {
		if (existing->acquisition == grant->acquisition ||
		    (existing->object == grant->object && existing->logical_open))
			return -EEXIST;
	}
	owner = READ_ONCE(grant->release->owner);
	if (!owner)
		return -ESTALE;
	raw_spin_lock(&owner->guard);
	if (grant->release->owner != owner || grant->release->state != state ||
	    grant->release->acquisition != grant->acquisition ||
	    grant->release->source_user != grant->user ||
	    grant->release->phase != KD_MUTEX_UNLOCK_HELD)
		result = -ESTALE;
	raw_spin_unlock(&owner->guard);
	if (result)
		return result;
	list_add_tail(&grant->state_link, &state->grants);
	grant->linked = true;
	grant->logical_open = true;
	return 0;
}

struct kd_source_grant *kd_state_find_grant(struct kd_thread_state *state,
					   struct kd_execution_binding *binding,
					   void *object)
{
	struct kd_source_grant *grant, *found = NULL;

	if (!kd_state_is_current(state, binding))
		return ERR_PTR(-EPERM);
	list_for_each_entry(grant, &state->grants, state_link) {
		if (grant->object != object || !grant->logical_open)
			continue;
		if (found)
			return ERR_PTR(-EUCLEAN);
		found = grant;
	}
	return found ? found : ERR_PTR(-ENOENT);
}

int kd_state_close_grant(struct kd_thread_state *state,
			 struct kd_execution_binding *binding,
			 struct kd_source_grant *grant)
{
	struct kd_mutex_release_owner *owner;
	enum kd_mutex_unlock_phase phase;
	enum kd_mutex_unlock_route route;

	if (!kd_state_is_current(state, binding))
		return -EPERM;
	if (!grant || grant->state != state || !grant->linked || !grant->logical_open)
		return -ESTALE;
	owner = READ_ONCE(grant->release->owner);
	if (!owner)
		return -ESTALE;
	raw_spin_lock(&owner->guard);
	phase = grant->release->phase;
	route = grant->release->route;
	raw_spin_unlock(&owner->guard);
	if (!((route == KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER &&
	       (phase == KD_MUTEX_UNLOCK_DEFERRED ||
		phase == KD_MUTEX_UNLOCK_UNWIND_READY)) ||
	      phase == KD_MUTEX_UNLOCK_OWNER_HANDLED ||
	      phase == KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED))
		return -EAGAIN;
	grant->logical_open = false;
	return 0;
}

int kd_state_unlink_grant(struct kd_thread_state *state,
			  struct kd_execution_binding *binding,
			  struct kd_source_grant *grant)
{
	struct kd_mutex_release_owner *owner;
	bool physical;
	int result;

	if (!kd_state_is_current(state, binding))
		return -EPERM;
	if (!grant || grant->state != state || !grant->linked || grant->logical_open)
		return -ESTALE;
	owner = READ_ONCE(grant->release->owner);
	if (!owner)
		return -ESTALE;
	raw_spin_lock(&owner->guard);
	physical = grant->release->phase == KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED;
	raw_spin_unlock(&owner->guard);
	if (!physical)
		return -EAGAIN;
	list_del_init(&grant->state_link);
	grant->linked = false;
	/* Success can allow owner reaping: no later grant access is permitted. */
	result = grant->drop(grant->control, grant->user);
	if (result) {
		/* Failure must retain that exact user, so the record is still valid. */
		list_add_tail(&grant->state_link, &state->grants);
		grant->linked = true;
	}
	return result;
}
