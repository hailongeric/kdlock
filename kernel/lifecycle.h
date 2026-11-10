/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_LIFECYCLE_H
#define KDLOCK_LIFECYCLE_H

#include "episode.h"
#include "task_storage.h"

/* Stable immutable managed-task configuration, normally embedded in the runtime
 * whose exact native users retain it. No source packet or task registry lives
 * here. Native begin creates a distinct enclosing provider/runtime hold for
 * every original task, including each child. Config/callback/context backing
 * survives every task and the final native-release callback return separately.
 */
struct kd_task_lifecycle_context {
	struct kd_episode_config config;
	unsigned int capacity;
	size_t auxiliary_bytes;
	unsigned long required_control_bytes;
	void *native_context;
	int (*native_begin)(void *context, void **lease);
	kd_task_native_release_fn native_release;
};

int kd_task_lifecycle_context_init(struct kd_task_lifecycle_context *context,
		const struct kd_episode_config *config, unsigned int capacity,
		size_t auxiliary_bytes, unsigned long required_control_bytes,
		void *native_context, int (*native_begin)(void *, void **),
		kd_task_native_release_fn native_release);
/* Explicit initial managed parent, before its first declared source operation.
 * Native-hold and retained-error ownership follow task_storage_start_current.
 * A failed retained setup remains source-closed until explicit cleanup.
 */
int kd_task_lifecycle_start_current(const struct kd_task_lifecycle_context *context,
		unsigned long origin_gs, struct kd_task_storage **storage);
/* copy_process hook immediately after successful dup_task_struct, before child
 * publication. Always clear copied root alias; only an actual managed parent
 * supplies the immutable context. Child receives independent core/pool/auxiliary
 * and stack/native holds, never copied grants or continuation. Its initial GS
 * zero is explicitly UNCAPTURED: mandatory first native capture refreshes real
 * kernel GS before any source offer. Errors may fail clone before publication.
 */
int kd_task_lifecycle_prepare_unpublished(struct task_struct *child);
/* Clone-failure hook before kernel drops the unpublished child stack/task.
 * Failure is an invariant/refusal: caller must not proceed to free child state.
 */
int kd_task_lifecycle_abort_unpublished(struct task_struct *child);
/* Managed do_exit hook before task/stack teardown, ordinary original native
 * context only. Close per-task admission, reject borrowed/auxiliary execution,
 * pending operations and logical-open grants; never fabricate unlocks. Pump
 * exact owner/grant/pool metadata with cond_resched until atomic detach succeeds.
 * No wait on pending==false, source execution, timeout or forced reclamation.
 * Managed callers permit no UNTRACKED raw root/storage/config observer across
 * exit; exact tracked users remain retained until proved ended. Callback/module
 * and caller-return backing survive their final native release independently.
 * Error refuses exit; the integration hook must diagnose rather than free state.
 * Unmanaged tasks stay outside this lane and return without changing behavior.
 */
int kd_task_lifecycle_exit_current(void);

#endif
