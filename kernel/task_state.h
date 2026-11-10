/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_TASK_STATE_H
#define KDLOCK_TASK_STATE_H

#include <linux/list.h>
#include <linux/types.h>

struct task_struct;
struct kd_thread_state;
struct kd_execution_binding;

/*
 * Caller-supplied persistent registry storage, separate from the canonical
 * packet. Initialize only private storage. Attach/lookup/borrow/detach run on
 * the registered task in ordinary task context, never IRQ/NMI or concurrent
 * reentry. The registry retains task identity; the caller retains this anchor
 * and its own core through detach and every escaped lookup/scope/code user.
 * No allocation, anchor capacity or C05 control-stack policy is selected.
 */
struct kd_task_anchor {
	struct hlist_node registry_link;
	struct task_struct *task;
	struct kd_thread_state *own;
	struct kd_thread_state *borrowed;
};

void kd_task_anchor_init(struct kd_task_anchor *anchor);

/*
 * Explicit current-task lookup under the registry bucket guard. A registered
 * task cannot concurrently detach itself in this task-only interface; the
 * caller keeps registration/storage valid through its last lookup use and
 * drains all escaped users before detach. A returned pointer is therefore
 * retained by that lifecycle, not by a new reference acquired here. A borrowed
 * core additionally remains retained by its enclosing scope/runtime users.
 * NULL borrowed selects own. Neither lookup reads the own packet or grants
 * execution permission; the source bridge still validates its exact binding.
 */
struct kd_thread_state *kd_task_state_own(void);
struct kd_thread_state *kd_task_state_active(void);

/*
 * Caller supplies a private initialized anchor, fresh canonical core and an
 * initialized native binding for current. Attach calls kd_state_init, retains
 * current with get_task_struct, then publishes this registry entry. Capture of
 * source input values remains the entry bridge's duty; no packet is cleared.
 * Another registered task must not share or concurrently reuse this storage.
 */
int kd_task_state_attach(struct kd_task_anchor *anchor,
			 struct kd_thread_state *state, unsigned long origin_gs,
			 struct kd_execution_binding *native_binding);

/*
 * Before detach, close admission and drain every queue, code, grant, return,
 * notification, binding, lookup and borrowed-scope user of the anchor/core and
 * original task/stack. An empty grant list does not prove those last users.
 * current must be the origin with no active borrowed anchor, own the supplied
 * exact native endpoint, have no pending exit, and be IDLE/RESUMABLE.
 * Detach removes binding and registry membership and releases its task hold
 * only after the final anchor access. It neither frees nor clears the packet.
 * Exit/stack release and anchor/core reuse wait for success AND the complete
 * caller drain proof. -EBUSY is not permission to abandon a retained duty.
 */
int kd_task_state_detach(struct kd_thread_state *state,
			 struct kd_execution_binding *native_binding);

/*
 * Small referring role control, never another packet. Retain this scope, its
 * exact registered anchor and previous/entered cores through leave. Initialize
 * private storage once, then use strict serial LIFO scopes. Same-state nested
 * scopes cannot detect every out-of-order close from pointer identity alone;
 * structured LIFO remains a caller obligation, not an allocation/depth policy.
 */
struct kd_task_borrow_scope {
	struct task_struct *task;
	struct kd_task_anchor *anchor;
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
 * Materialize/stop or transfer source before leaving. Leave restores only the
 * saved active pointer; it imports no packet or earlier binding authority.
 * A terminal W may already advance elsewhere, so the entered binding need not
 * still be current. The next source step checks its retained current binding.
 */
int kd_task_borrow_leave(struct kd_task_borrow_scope *scope);

#endif
