/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_TASK_STATE_H
#define KDLOCK_TASK_STATE_H

#include <linux/types.h>

struct task_struct;
struct kd_thread_state;
struct kd_execution_binding;

/*
 * The source-rebuilt task_struct has only kd_own_state and kd_active_state
 * pointers. kd_active_state names a borrowed origin only; NULL selects own.
 * These current-task lookups return retained anchors, not execution permission
 * or a new storage reference. The caller still validates its exact binding.
 */
struct kd_thread_state *kd_task_state_own(void);
struct kd_thread_state *kd_task_state_active(void);

/*
 * Private constructor hook, before a copied child can be published or any
 * child cleanup can consume these fields. Copying task_struct took no core
 * reference: clear the two inherited aliases without modifying/freeing the
 * parent's core. Never use this to reset a live task or retained source state.
 */
void kd_task_state_reset_unpublished(struct task_struct *task);

/*
 * Caller supplies fresh canonical core and an initialized native binding for
 * current; no allocator, packet copy or capacity is selected here. Attach calls
 * kd_state_init and publishes that exact core. Capture of declared source input
 * values remains the entry bridge's duty; initialization does not clear regs.
 */
int kd_task_state_attach(struct kd_thread_state *state, unsigned long origin_gs,
			 struct kd_execution_binding *native_binding);

/*
 * Before detach, close source admission and drain every queue, code, grant,
 * return, notification, binding and borrowed-pointer user of this core and the
 * original task/stack. Those escaped last users are not inferred from an empty
 * grant list. current must be the origin, have no active borrowed anchor, and
 * own the supplied exact native binding; no pending image exit may remain and
 * only IDLE/RESUMABLE is quiescent here.
 * Detach revokes the anchor/binding, but neither frees nor clears the packet.
 * Task exit/stack release and caller-owned storage reuse must wait for success
 * AND the caller's full last-user proof. -EBUSY is not permission to exit or
 * abandon a retained duty. No drain-wait, allocator or C05 stack policy is added.
 */
int kd_task_state_detach(struct kd_thread_state *state,
			 struct kd_execution_binding *native_binding);

/*
 * Small caller-supplied role control; it contains no source registers/packet.
 * Keep the scope and previous/entered cores retained through leave. Initialize
 * private storage once, then enter/leave serially in strict LIFO order. With
 * only two task anchor pointers, same-state nested scopes cannot detect every
 * out-of-order close; structured LIFO is an explicit caller obligation, not a
 * counter/extra task-field mechanism or a selected control-stack allocation.
 */
struct kd_task_borrow_scope {
	struct task_struct *task;
	struct kd_thread_state *previous;
	struct kd_thread_state *entered;
	bool active;
};

void kd_task_borrow_scope_init(struct kd_task_borrow_scope *scope);
/* Enter only a foreign origin under the retained current JIT binding. */
int kd_task_borrow_enter(struct kd_task_borrow_scope *scope,
			 struct kd_thread_state *state,
			 struct kd_execution_binding *binding);
/*
 * Materialize/stop or transfer the entered source before leaving. Leave only
 * restores the prior active pointer: it does not import an old packet, transfer
 * binding authority or authorize the outer source. A terminal W may already be
 * advancing elsewhere, so the entered binding need not still be current here.
 * The next source step separately validates its retained current binding.
 */
int kd_task_borrow_leave(struct kd_task_borrow_scope *scope);

#endif
