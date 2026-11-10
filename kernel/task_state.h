/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_TASK_STATE_H
#define KDLOCK_TASK_STATE_H

#include <linux/types.h>
#include "state.h"
#include "owner_progress.h"

struct task_struct;
struct kd_mutex_entry;
struct kd_request_pool;
struct kd_request_slot;
struct kd_episode_resources;

/*
 * One stable task-owned root/auxiliary header, never another borrowed packet.
 * The source-rebuilt task_struct stores only kd_root_context pointing here.
 * Every active borrowed/nested request instead names S_W through node->state;
 * no registry or active-S_W task field exists. Caller-provided auxiliary stack
 * storage is disjoint from this header and from any lent source stack.
 */
struct kd_task_root_context {
	struct kd_thread_state core;
	struct kd_execution_binding initial_native;
	struct task_struct *task;
	/* Physical owners stay with this task even when their source moves. */
	struct kd_owner_progress owners;
	/* Exact native-local owners outside borrowed source execution. */
	struct list_head held_local;
	/* Own native-entry configuration, never an active borrowed S_W. */
	struct kd_episode_resources *mutex_resources;
	unsigned long mutex_control_bytes;
	unsigned long aux_low;
	unsigned long aux_high;
	unsigned long aux_current;
	/* Exact prepared native control entry occupying the auxiliary cursor. */
	struct kd_mutex_entry *aux_entry;
	bool attached;
};

/* Constructor only, before publication or any retained user. No regs clear. */
void kd_task_root_context_init(struct kd_task_root_context *context);

/*
 * Current-task root lookup for native entry, auxiliary preflight and original
 * W handback. NULL means no prepared root context. Lookup reads only the task
 * anchor/header pointer, not the own packet while borrowed source executes.
 * The current-task-only attach/detach lifecycle and caller backing retain the
 * returned pointer through its last use; lookup acquires no new reference or
 * execution right. Every escaped user must be retained and drained separately.
 */
struct kd_task_root_context *kd_task_root_context_current(void);
struct kd_thread_state *kd_task_state_own(void);

/*
 * Attach private initialized caller storage on current in ordinary task
 * context. [aux_low, aux_high) is supplied writable control-stack storage;
 * aux_current is its initial cursor, not a selected capacity or allocation.
 * Attach initializes the one core and initial_native endpoint, retains current
 * and publishes the single task pointer. A live aux_entry blocks attach and
 * detach; it names control-storage occupancy, never active borrowed S_W.
 * pool and slots are caller-provisioned task-owned backing, with an explicit
 * count covering every simultaneously retained delegation request/control, not
 * only lock depth. They and the header survive all final users. Attach reserves
 * no per-lock storage and captures no source registers. No capacity default or
 * public void-lock allocation-error route is supplied. An explicit zero count
 * permits local execution without persistent delegation records. The native
 * fallback keeps a temporary waiter only through its queue admission and uses
 * stable object-owned queue storage afterward.
 * The initial endpoint must not be reinitialized/reused while any old observer
 * remains. Later native handbacks use fresh caller-reserved binding records.
 */
int kd_task_root_attach(struct kd_task_root_context *context,
		       unsigned long origin_gs, unsigned long aux_low,
		       unsigned long aux_high, unsigned long aux_current,
		       struct kd_request_pool *pool,
		       struct kd_request_slot *slots, unsigned int capacity);

/*
 * Constructor hook before a copied child is published or cleanup consumes the
 * field. The copied alias acquired no reference; clear it without touching the
 * parent's context. Never use this to reset a live task or source core.
 */
void kd_task_root_reset_unpublished(struct task_struct *task);

/*
 * Before detach, close admission and drain all source, auxiliary-frame, queue,
 * grant, code, return, notification, binding and lookup users of this context,
 * the original task and its stacks. Do not call during borrowed execution or
 * from a retained auxiliary frame. An idle cursor or empty grant list cannot
 * prove that drain. current must be the exact origin/native owner, with no
 * pending exit, empty physical-owner/local-held indexes and operation
 * IDLE/RESUMABLE.
 * Otherwise finished pool storage may still retain the exact current native
 * endpoint; final close revokes that binding and reclaims it atomically.
 * Detach revokes binding/task lookup
 * and drops its task reference after the final header access, without freeing
 * storage or clearing the packet. Exit/stack release and reuse require success
 * AND the caller's full last-user proof. No allocator/drain-wait policy is added.
 */
int kd_task_root_detach(struct kd_task_root_context *context,
		       struct kd_execution_binding *native_binding);

#endif
