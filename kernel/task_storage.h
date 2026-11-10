/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_TASK_STORAGE_H
#define KDLOCK_TASK_STORAGE_H

#include <linux/types.h>

struct kd_episode_config;
struct kd_execution_binding;
struct kd_task_root_context;
struct kd_task_storage;
struct task_struct;

typedef void (*kd_task_native_release_fn)(void *lease);

/* Call-only description; copy it and config before allocation/attachment.
 * capacity is the exact nonzero request/frame count. auxiliary_bytes is an
 * explicit nonzero page multiple; required_control_bytes is the separately
 * proved complete recursive/control requirement. No deployment defaults,
 * stack-compatibility proof or per-mutex_lock allocation is introduced.
 *
 * config and callback/source/code/object backing remain externally retained.
 * config->stack must be NULL: this helper installs its own independently held
 * original-stack word adapter in the private copied configuration. Other config
 * fields, including image slot, feedback pool and classifiers, are unchanged.
 * origin_gs is explicit; no current_task offset or hardware-GS value is guessed.
 *
 * native_lease/release describe an ALREADY owned complete native-provider hold
 * spanning the entire declared source activity, including native suffix/return
 * and late observers, rather than an image/grant alone. Callback code, caller
 * return code and active finalizer backing survive callback return separately.
 * The synchronous nonfailing release callback advances no source and may release
 * the lease payload; no helper payload access follows it. Text immutability and
 * provider admission/mutation policy are not supplied by this allocation API.
 */
struct kd_task_storage_args {
	unsigned int capacity;
	size_t auxiliary_bytes;
	unsigned long required_control_bytes;
	unsigned long origin_gs;
	const struct kd_episode_config *config;
	void *native_lease;
	kd_task_native_release_fn native_release;
};

/* Current original task, ordinary sleepable TASK_RUNNING context, before first
 * source admission. out is separate writable caller backing, disjoint from
 * args/config and retained controls. On success, *out owns all allocated storage
 * and the native lease. On error with *out == NULL, storage was safely unwound
 * and native lease ownership remains with the caller. A non-NULL error output
 * instead transfers that lease into retained storage whose setup failed to
 * detach: do not admit source or free/reinitialize it; later stop requires the
 * exact endpoint and full drain proof. There is no automatic error retry.
 */
int kd_task_storage_start_current(const struct kd_task_storage_args *args,
				 struct kd_task_storage **out);

/* Managed-parent cold construction for a fresh unpublished child only.
 * Child kernel stack/task refs already exist, copied root alias was cleared,
 * and no actor/lookup has escaped. Args carry the parent's SAME immutable
 * admitted provider configuration and a newly acquired child native lease.
 * New child receives its own core, request pool and auxiliary storage. Initial
 * GS is an explicit uncaptured seed; no source offer precedes first real capture.
 * Output/native-lease failure ownership is identical to start_current.
 */
int kd_task_storage_prepare_unpublished(const struct kd_task_storage_args *args,
		struct task_struct *child, struct kd_task_storage **out);
/* Clone failure cleanup before any child publication/execution, never a live
 * foreign-task teardown. End child holds before kernel drops its stack/task.
 */
int kd_task_storage_abort_unpublished(struct kd_task_storage *storage,
				      struct task_struct *child);

/* Pointer lookup only under the caller's existing retained storage ownership.
 * It neither reads an active borrowed packet nor acquires a reference/right.
 */
struct kd_task_root_context *kd_task_storage_root(struct kd_task_storage *storage);

/* Caller has closed new source admission and ended every escaped callback,
 * owner/control, grant, return/image, notifier, binding, lookup and abandoned
 * auxiliary-frame observer, including accesses through returned root pointers.
 * expected_native is the retained EXACT current endpoint, possibly inside the
 * request array about to be freed. All calls are serialized on original current
 * in ordinary sleepable native context. No borrowed/source actor remains.
 *
 * One existing task-progress/teardown pass attempts atomic detach. Error leaves
 * every allocation/stack/native hold intact for later explicit resolution. On
 * success, release stack retention and free backing only after that caller
 * last-user proof, then invoke the cached native-provider callback last. No access to
 * storage/root/endpoint follows freeing; caller discards every old pointer.
 * pending is the pre-detach metadata report and may be true on success: it is
 * neither a wait condition nor a full drain proof. It is separate caller storage.
 * No global exit hook, fork allocator, drain loop or task-exit policy is added.
 */
int kd_task_storage_stop_current(struct kd_task_storage *storage,
		struct kd_execution_binding *expected_native, bool *pending);

#endif
