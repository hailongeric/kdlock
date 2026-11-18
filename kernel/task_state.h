/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_TASK_STATE_H
#define KDLOCK_TASK_STATE_H

#include <linux/types.h>
#include "state.h"
#include "owner_progress.h"
#include "mutex.h"
#include "rw.h"

struct task_struct;
struct kd_mutex_entry;
struct kd_request_pool;
struct kd_request_slot;
struct kd_episode_resources;
struct kd_task_storage;
struct kd_task_lifecycle_context;
struct kd_request_user;

/* Preallocated per-frame allocation actor, separate from the pool membership.
 * storage.guard owns this record while linked. The exact queue user retains
 * the frame through actor_finish's last pool API; a task/node reference alone
 * does not retain the containing allocation. No source packet is stored here.
 */
struct kd_task_cancel_actor {
	struct list_head link;
	struct kd_task_storage *storage;
	struct kd_request_slot *slot;
	const void *claim;
	struct kd_request_user *queue_user;
	const void *identity;
	bool linked;
};

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
	/* Exact owned native compatibility grants, no source-state backing. */
	struct list_head native_grants;
	/* Exact source-ordered owned rwsem reads; source ownership serializes it. */
	struct list_head rwsem_reads;
	/* Native mutex ownership depth and contention sampling phase. */
	struct kd_mutex_fast mutex_fast;
	/* One local rwsem read, ordered with every managed/native read credit. */
	struct kd_rw_read_credit rwsem_fast;
	/* Own native-entry configuration, never an active borrowed S_W. */
	struct kd_episode_resources *mutex_resources;
	unsigned long mutex_control_bytes;
	/* Preemption references belonging to this task's materialized spin
	 * grants. A prepared spin entry holds one additional control reference.
	 */
	unsigned int native_spin_depth;
	unsigned long aux_low;
	unsigned long aux_high;
	unsigned long aux_current;
	/* Exact prepared native control entry occupying the auxiliary cursor. */
	struct kd_mutex_entry *aux_entry;
	bool attached;
	/* Own cold lifecycle/configuration, never active borrowed source state. */
	const struct kd_task_lifecycle_context *lifecycle;
	struct kd_task_storage *storage;
	bool source_closing;
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
 * nonzero count covering every simultaneously retained request/control, not
 * only lock depth. They and the header survive all final users. Attach reserves
 * no per-lock storage and captures no source registers. No capacity default or
 * public void-lock allocation-error route is supplied.
 * The initial endpoint must not be reinitialized/reused while any old observer
 * remains. Later native handbacks use fresh caller-reserved binding records.
 */
int kd_task_root_attach(struct kd_task_root_context *context,
		       unsigned long origin_gs, unsigned long aux_low,
		       unsigned long aux_high, unsigned long aux_current,
		       struct kd_request_pool *pool,
		       struct kd_request_slot *slots, unsigned int capacity);

/* Parent-owned fresh unpublished child only, after dup_task_struct initialized
 * task/stack references. No actor or lookup observer may escape. The initial
 * endpoint belongs to child, not current. origin_gs is an uncaptured seed only;
 * first native capture must refresh actual kernel GS before any source offer.
 */
int kd_task_root_attach_unpublished(struct kd_task_root_context *context,
		struct task_struct *child, unsigned long origin_gs,
		unsigned long aux_low, unsigned long aux_high, unsigned long aux_current,
		struct kd_request_pool *pool, struct kd_request_slot *slots,
		unsigned int capacity);
/* Fresh-child failure cleanup only: exact untouched initial endpoint, empty
 * pool/no grant/owner/exit/operation/auxiliary actors. This never relaxes current
 * owner requirements of normal detach or authorizes foreign-task live cleanup.
 */
int kd_task_root_detach_unpublished(struct kd_task_root_context *context,
				    struct task_struct *child);

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
 * pending exit, empty physical-owner progress and operation IDLE/RESUMABLE.
 * Otherwise finished pool storage may still retain the exact current native
 * endpoint; final close revokes that binding and reclaims it atomically.
 * Detach revokes binding/task lookup
 * and drops its task reference after the final header access, without freeing
 * storage or clearing the packet. Exit/stack release and reuse require success
 * AND the caller's full last-user proof. No allocator/drain-wait policy is added.
 */
int kd_task_root_detach(struct kd_task_root_context *context,
		       struct kd_execution_binding *native_binding);

/* Current original native task only, with every executable/source/native and
 * physical duty ended. Under the caller's storage guard, permit ONLY the exact
 * canceled, ungranted queue actors on actors to remain. Revoke the endpoint and
 * task anchor once, retaining the root/task/pool backing for metadata retirement.
 * This does not drop the attach task reference or clear the canonical packet.
 */
int kd_task_root_revoke_cancelled(struct kd_task_root_context *context,
		struct kd_execution_binding *native_binding, struct list_head *actors);

#endif
