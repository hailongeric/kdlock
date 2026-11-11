/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_STATE_H
#define KDLOCK_STATE_H

#include <linux/list.h>
#include "../include/kd_regs.h"
#include "mutex_release.h"

struct task_struct;
struct kd_thread_state;
struct kd_jit_image;
struct kd_jit_image_use;
struct kd_request_pool;

/* These small records live in existing request/role storage, never a packet. */
enum kd_execution_kind {
	KD_EXECUTION_NATIVE,
	KD_EXECUTION_JIT,
	KD_EXECUTION_OFFER,
};

struct kd_execution_binding {
	struct kd_thread_state *state;
	struct task_struct *task;
	const void *control;
	enum kd_execution_kind kind;
};

enum kd_operation_kind {
	KD_OPERATION_NONE,
	KD_OPERATION_MUTEX_LOCK,
	KD_OPERATION_MUTEX_UNLOCK,
	KD_OPERATION_MODE_CHANGE,
	KD_OPERATION_SPIN_LOCK,
	KD_OPERATION_SPIN_UNLOCK,
};

static inline bool kd_operation_is_lock(enum kd_operation_kind kind)
{
	return kind == KD_OPERATION_MUTEX_LOCK || kind == KD_OPERATION_SPIN_LOCK;
}

static inline bool kd_operation_is_unlock(enum kd_operation_kind kind)
{
	return kind == KD_OPERATION_MUTEX_UNLOCK || kind == KD_OPERATION_SPIN_UNLOCK;
}

static inline bool kd_operation_is_spin(enum kd_operation_kind kind)
{
	return kind == KD_OPERATION_SPIN_LOCK || kind == KD_OPERATION_SPIN_UNLOCK;
}

enum kd_operation_form {
	KD_OPERATION_NEW_CALL,
	KD_OPERATION_EXISTING_CALL,
	KD_OPERATION_EXISTING_FRAME,
	/* Compiler-clobber root already captured the post-call continuation. */
	KD_OPERATION_CAPTURED_CONTINUATION,
};

enum kd_operation_phase {
	KD_OPERATION_IDLE,
	KD_OPERATION_TARGET_READY,
	KD_OPERATION_API_READY,
	KD_OPERATION_ENTERED,
	KD_OPERATION_DONE,
	KD_OPERATION_RESUMABLE,
};

/* Pending operation metadata, not another source register/cursor snapshot. */
struct kd_source_operation {
	const void *identity;
	enum kd_operation_kind kind;
	enum kd_operation_form form;
	enum kd_operation_phase phase;
	unsigned long source_site;
	unsigned long target;
	unsigned long return_ip;
};

/*
 * A per-acquisition referring user. The MCS call/control may embed this record.
 * Drop is called only after unlink and must release exactly user, without any
 * later access to this record on success. It may then become reusable.
 */
struct kd_source_grant {
	struct list_head state_link;
	struct kd_thread_state *state;
	void *object;
	const void *acquisition;
	struct kd_mutex_release *release;
	const void *user;
	int (*drop)(void *control, const void *user);
	void *control;
	bool linked;
	bool logical_open;
};

/*
 * Exactly one canonical packet and current operation for original W. Every
 * request/role points directly here through its MCS node, including nested
 * requests. A task-owned root/auxiliary header supplies initial own backing;
 * request storage is provisioned with W and reused after exact final users. The
 * caller retains this core and origin task/stack through all queue, grant, return, notification and code users.
 */
struct kd_thread_state {
	struct kd_regs regs;
	struct kd_jit_io io;
	/* Exact producer and claimed referring use, never another cursor/packet.
	 * These three fields are installed/cleared together by current source.
	 */
	const struct kd_jit_image *exit_image;
	struct kd_jit_image_use *exit_use;
	const void *exit_holder;
	struct kd_source_operation operation;
	struct kd_execution_binding *binding;
	/* Immutable task-provisioned storage; nested executors use W's pool. */
	struct kd_request_pool *requests;
	struct task_struct *origin;
	unsigned long origin_gs;
	struct list_head grants;
};

/*
 * Initialize private records only. A binding becomes immutable before publish.
 * Offer, execution and return bindings need distinct addresses for each live
 * ownership episode; do not reuse an old endpoint while an observer retains it.
 * This prevents pointer ABA across A -> B -> A without a per-hop counter.
 */
int kd_execution_binding_init(struct kd_execution_binding *binding,
			      struct kd_thread_state *state,
			      struct task_struct *task, const void *control,
			      enum kd_execution_kind kind);
int kd_state_init(struct kd_thread_state *state, struct task_struct *origin,
		  unsigned long origin_gs,
		  struct kd_execution_binding *native_binding);
bool kd_state_is_current(struct kd_thread_state *state,
			 struct kd_execution_binding *binding);
bool kd_state_is_jit_current(struct kd_thread_state *state,
			     struct kd_execution_binding *binding);
/* Acquire is not a storage reference: compare to a retained expected binding.
 * Do not dereference an arbitrary observed endpoint without its lifetime proof.
 */
struct kd_execution_binding *kd_state_current_binding(struct kd_thread_state *state);

/*
 * Materialize resident values and stop source before publish/transfer. These
 * primitives publish the same packet; they do not capture registers or choose
 * a queue winner. Only the selected MCS endpoint may accept its exact offer.
 * The receiver observes the exact new binding with acquire ordering before
 * source work. Old bindings confer no right to restore an earlier packet.
 */
int kd_state_publish(struct kd_thread_state *state,
		     struct kd_execution_binding *from,
		     struct kd_execution_binding *offer);
int kd_state_accept(struct kd_thread_state *state,
		    struct kd_execution_binding *offer,
		    struct kd_execution_binding *execution);
int kd_state_transfer(struct kd_thread_state *state,
		      struct kd_execution_binding *from,
		      struct kd_execution_binding *destination);

/*
 * Exact operation identity differs for acquisition and unlock, even when both
 * belong to one MCS node. A resolved indirect target is passed once; no helper
 * rereads the operand. Existing CALL/frame forms have no new source push.
 * CAPTURED_CONTINUATION keeps the compiler-clobber root's pre-CALL SP and
 * post-call IP; its completion neither pushes nor pops a source return word.
 */
int kd_operation_begin(struct kd_thread_state *state,
		       struct kd_execution_binding *binding,
		       const void *identity, enum kd_operation_kind kind,
		       enum kd_operation_form form, unsigned long source_site,
		       unsigned long target, unsigned long return_ip);

/*
 * These callbacks access the retained original kernel stack synchronously.
 * Each word operation must complete without failure, source reentry or control
 * mutation. They supply no fault/fixup proof for arbitrary addresses. Reserve
 * this valid-stack route before delegated effects; no replay is possible after
 * an unknown partial memory effect. No general flags/SIMD handling is added.
 */
struct kd_source_stack_ops {
	void (*write_word)(void *context, unsigned long address, unsigned long value);
	unsigned long (*read_word)(void *context, unsigned long address);
	void *context;
};
int kd_operation_stage_call(struct kd_thread_state *state,
			    struct kd_execution_binding *binding,
			    const void *identity,
			    const struct kd_source_stack_ops *stack);
int kd_operation_enter(struct kd_thread_state *state,
		       struct kd_execution_binding *binding,
		       const void *identity);
int kd_operation_complete(struct kd_thread_state *state,
			  struct kd_execution_binding *binding,
			  const void *identity);
int kd_operation_return(struct kd_thread_state *state,
			struct kd_execution_binding *binding,
			const void *identity,
			const struct kd_source_stack_ops *stack);

/* Grant-list membership is written only by the current source executor. */
void kd_source_grant_init(struct kd_source_grant *grant,
			  struct kd_thread_state *state, void *object,
			  const void *acquisition,
			  struct kd_mutex_release *release, const void *user,
			  int (*drop)(void *, const void *), void *control);
int kd_state_link_grant(struct kd_thread_state *state,
			struct kd_execution_binding *binding,
			struct kd_source_grant *grant);
struct kd_source_grant *kd_state_find_grant(struct kd_thread_state *state,
					   struct kd_execution_binding *binding,
					   void *object);
int kd_state_close_grant(struct kd_thread_state *state,
			 struct kd_execution_binding *binding,
			 struct kd_source_grant *grant);
int kd_state_unlink_grant(struct kd_thread_state *state,
			  struct kd_execution_binding *binding,
			  struct kd_source_grant *grant);

#endif
