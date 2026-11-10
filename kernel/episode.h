/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_EPISODE_H
#define KDLOCK_EPISODE_H

#include "request_pool.h"

struct kd_episode_frame;

/* Immutable caller configuration and source/code holds precede admission.
 * report is synchronous, does not mutate source/control or retain raw pointers,
 * and cannot wait for compilation. image may be NULL when no image was admitted
 * at an empty/closing root. io == NULL means no source exit occurred;
 * entry_result then describes the no-source entry refusal. Non-NULL image/io
 * remain valid only through callback return and confer no publication/ACK.
 */
struct kd_episode_config {
	struct kd_jit_image_slot *image_slot;
	const struct kd_source_stack_ops *stack;
	kd_jit_resolve_operation_fn resolve;
	void *resolve_context;
	unsigned int proxy_limit;
	void (*report)(void *context, const struct kd_jit_image *image,
		       unsigned long source_ip, int entry_result,
		       const struct kd_jit_io *io);
	void *report_context;
};

/* One frame per supplied pool slot, with no packet or saved source cursor.
 * All arrays/backing are caller-provisioned outside both source/auxiliary stacks
 * and retained through every observer. capacity is the exact shared array extent.
 */
struct kd_episode_resources {
	struct kd_request_pool *pool;
	struct kd_episode_frame *frames;
	unsigned int capacity;
	struct kd_episode_config config;
};

struct kd_episode_frame {
	struct kd_episode_resources *resources;
	struct kd_request_slot *slot;
	const void *claim;
	struct task_struct *origin;
	struct kd_episode_frame *root;
	struct kd_episode_frame *parent;
	enum kd_operation_kind operation;

	struct list_head children;
	struct list_head child_link;
	struct list_head deferred;
	struct list_head deferred_link;
	struct kd_episode_frame *deferred_host;

	struct kd_request_user control_user;
	struct kd_request_user image_user;
	struct kd_request_user grant_user;
	struct kd_request_user binding_user;
	struct kd_request_user native_user;
	struct kd_request_user notifier_user;
	struct kd_request_user deferred_user;
	struct kd_request_user auxiliary_user;
	/* grant/source/image flags belong to the current source actor. Parent
	 * return flags are set before child offer and cleared after child result
	 * acquire. Exported metadata cleanup finishes before each MCS result store;
	 * transfer_origin alone does not wake W. No old actor mutates these flags
	 * after root result publication. Exact users retain storage separately.
	 */
	bool control_held;
	bool image_held;
	bool grant_held;
	bool binding_held;
	bool native_held;
	bool notifier_held;
	bool deferred_held;
	bool auxiliary_held;
	bool source_image;
	bool return_image;
	bool execution_image;
	bool exit_pending;
	bool parent_return;
	bool parent_linked;
	bool grant_started;
	bool source_closed;
	bool flush_deferred;
	bool result_consumed;
	char return_identity;
};

int kd_episode_resources_init(struct kd_episode_resources *resources,
		 struct kd_request_pool *pool, struct kd_episode_frame *frames,
		 unsigned int capacity, const struct kd_episode_config *config);
/* Private setup before any source capture, lending or queue publication. */
int kd_episode_prepare_root(struct kd_episode_resources *resources,
		 struct kd_execution_binding *native_binding,
		 enum kd_operation_kind operation, struct kd_episode_frame **frame);
/* Current source owner only; closes completed source/image/grant actors without
 * restoring source registers or changing its current binding. Collection and
 * frame flag mutation follow the exact offer/result ordering: no origin source
 * wake precedes the root MCS result publication after exported callbacks and
 * parent child-return cleanup. An observed native pointer alone is not proof.
 */
int kd_episode_collect(struct kd_episode_resources *resources,
		       struct kd_execution_binding *binding);
int kd_episode_cancel_root(struct kd_episode_frame *frame,
			   struct kd_execution_binding *native_binding);
int kd_episode_acquire_root(struct kd_episode_frame *frame,
		 struct kd_execution_binding *native_binding, struct kd_mutex *lock,
		 unsigned long source_sp, unsigned long continuation_ip,
		 unsigned long source_bp, unsigned long api_target,
		 enum kd_mutex_outcome *outcome);
struct kd_execution_binding *kd_episode_native_binding(struct kd_episode_frame *frame);
/* Result/controller completion precedes final native resume. The separate
 * auxiliary actor stays through every final entry/binding read.
 */
int kd_episode_root_done(struct kd_episode_frame *frame);
void kd_episode_native_done(void *context);
/* Ordinary original-W hardware CALL/RET path. No new slot, source lending,
 * stale packet import or virtual CALL/RET is needed to unlock an existing grant.
 */
int kd_episode_unlock_native(struct kd_episode_resources *resources,
		 struct kd_task_root_context *root,
		 struct kd_execution_binding *native_binding, struct kd_mutex *lock);

#endif
