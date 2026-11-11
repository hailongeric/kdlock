/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_RUNTIME_H
#define KDLOCK_RUNTIME_H

#include "channel.h"
#include "compiled_image.h"
#include "source_provider.h"
#include "task_storage.h"

/* Exported source-site boundary metadata; no callee-name inference. */
enum kd_jit_runtime_boundary_kind {
	KD_JIT_RUNTIME_LOCK = 1,
	KD_JIT_RUNTIME_UNLOCK = 2,
	KD_JIT_RUNTIME_MODE_CHANGE = 3,
	KD_JIT_RUNTIME_SPECIAL = 4,
};
struct kd_jit_runtime_boundary {
	unsigned long site;
	enum kd_jit_runtime_boundary_kind kind;
};

/* Cold caller configuration, no deployment defaults. All source/native/JIT
 * dependencies obey source_provider's immutable-text contract; every source
 * operation in exported text has exact boundary metadata. A target is ordinary
 * only within these retained regions under that complete-operation contract.
 * This is trusted-source input, not semantic/context analysis or added API lanes.
 *
 * Used cycle/image control addresses are never reused before shutdown and every
 * host-history/identity observer ends. Counts cover this entire retained finite
 * workload, not just concurrently open fds or live source depth. Actual code and
 * metadata are allocated by compiled_image; no per-mutex-call allocation occurs.
 * Callback/module/caller-return backing is independently valid through every API
 * and native finalizer return, including after the source lease is dropped.
 */
struct kd_jit_runtime_config {
	struct kd_jit_source_provider *source;
	unsigned int feedback_capacity;
	unsigned int cycle_capacity;
	unsigned int image_capacity;
	unsigned int claim_capacity;
	struct kd_jit_compiled_image_limits compiled;
	struct kd_jit_compiled_image_symbols symbols;
	const struct kd_jit_runtime_boundary *boundaries;
	unsigned int boundary_count;
	const char *channel_name;
	struct module *owner;
	size_t frame_capacity;
	unsigned int request_capacity;
	size_t auxiliary_bytes;
	unsigned long required_control_bytes;
	unsigned int proxy_limit;
};

struct kd_jit_runtime;
struct kd_episode_config;

int kd_jit_runtime_create(const struct kd_jit_runtime_config *config,
		struct kd_jit_runtime **runtime);
int kd_jit_runtime_native_begin(void *runtime, void **lease);
void kd_jit_runtime_native_release(void *lease);
int kd_jit_runtime_episode_config(struct kd_jit_runtime *runtime, struct kd_episode_config *config);
/* Explicit cold native scope before original source begins. One provider NATIVE
 * hold and exact runtime user live through task storage, source suffix/returns,
 * controls and final callback. No automatic fork/exit policy or task registry.
 * A non-NULL error storage retains that scope for explicit stop, as task_storage.
 */
int kd_jit_runtime_enter_current(struct kd_jit_runtime *runtime,
		unsigned long origin_gs, struct kd_task_storage **storage);
int kd_jit_runtime_leave_current(struct kd_task_storage *storage,
		struct kd_execution_binding *expected_native, bool *pending);
/* Caller ended all host history/transport and source admission first. A busy
 * result preserves actual controls; never discard facts or force module drain.
 * Runtime does not destroy its caller-owned source provider. Shutdown drops its
 * BUILD hold; a separate exact cold FEEDBACK user retains exported source data
 * until final channel/control teardown. Destroy drops that user only after its
 * final source access; provider destruction remains a separate duty.
 */
int kd_jit_runtime_destroy(struct kd_jit_runtime *runtime);

#endif
