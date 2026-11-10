// SPDX-License-Identifier: GPL-2.0-only
/* Direct current-task anchors for one canonical core and borrowed origins. */
#include <linux/atomic.h>
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/sched.h>

#include "state.h"
#include "task_state.h"

struct kd_thread_state *kd_task_state_own(void)
{
	return smp_load_acquire(&current->kd_own_state);
}

struct kd_thread_state *kd_task_state_active(void)
{
	struct kd_thread_state *borrowed =
		smp_load_acquire(&current->kd_active_state);

	return borrowed ? borrowed : kd_task_state_own();
}

void kd_task_state_reset_unpublished(struct task_struct *task)
{
	/* Constructor-only: copied aliases did not acquire parent-core users. */
	WRITE_ONCE(task->kd_own_state, NULL);
	WRITE_ONCE(task->kd_active_state, NULL);
}

int kd_task_state_attach(struct kd_thread_state *state, unsigned long origin_gs,
			 struct kd_execution_binding *native_binding)
{
	int result;

	if (!state || !native_binding)
		return -EINVAL;
	if (smp_load_acquire(&current->kd_active_state))
		return -EBUSY;
	if (kd_task_state_own())
		return -EEXIST;
	result = kd_state_init(state, current, origin_gs, native_binding);
	if (result)
		return result;
	/* State initialization/canonical binding precede anchor publication. */
	smp_store_release(&current->kd_own_state, state);
	return 0;
}

int kd_task_state_detach(struct kd_thread_state *state,
			 struct kd_execution_binding *native_binding)
{
	if (!state || !native_binding)
		return -EINVAL;
	if (smp_load_acquire(&current->kd_active_state))
		return -EBUSY;
	if (kd_task_state_own() != state)
		return -ESTALE;
	if (state->origin != current)
		return -EPERM;
	/* Acquire and compare a retained endpoint before reading its fields. */
	if (kd_state_current_binding(state) != native_binding)
		return -ESTALE;
	if (native_binding->state != state || native_binding->task != current ||
	    native_binding->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	if (state->exit_image || !list_empty(&state->grants) ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	/* Caller has already excluded/drained every escaped observer, not merely
	 * the grant list. Neither old endpoint nor packet storage is reused here.
	 */
	if (cmpxchg_release(&state->binding, native_binding, NULL) != native_binding)
		return -ESTALE;
	smp_store_release(&current->kd_own_state, NULL);
	return 0;
}

void kd_task_borrow_scope_init(struct kd_task_borrow_scope *scope)
{
	scope->task = NULL;
	scope->previous = NULL;
	scope->entered = NULL;
	scope->active = false;
}

int kd_task_borrow_enter(struct kd_task_borrow_scope *scope,
			 struct kd_thread_state *state,
			 struct kd_execution_binding *binding)
{
	struct kd_thread_state *own;

	if (!scope || !state || !binding)
		return -EINVAL;
	if (scope->active)
		return -EBUSY;
	own = kd_task_state_own();
	if (!own)
		return -ENOENT;
	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	if (state == own || state->origin == current)
		return -EINVAL;
	scope->task = current;
	scope->previous = smp_load_acquire(&current->kd_active_state);
	scope->entered = state;
	scope->active = true;
	smp_store_release(&current->kd_active_state, state);
	return 0;
}

int kd_task_borrow_leave(struct kd_task_borrow_scope *scope)
{
	if (!scope || !scope->active)
		return -EINVAL;
	if (scope->task != current)
		return -EPERM;
	if (smp_load_acquire(&current->kd_active_state) != scope->entered)
		return -ESTALE;
	/* Pointer restoration only. The prior core's CURRENT state, never an old
	 * register snapshot, is used if its exact binding later permits source.
	 */
	smp_store_release(&current->kd_active_state, scope->previous);
	scope->active = false;
	scope->task = NULL;
	scope->previous = NULL;
	scope->entered = NULL;
	return 0;
}
