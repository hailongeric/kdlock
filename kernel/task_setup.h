/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_TASK_SETUP_H
#define KDLOCK_TASK_SETUP_H

#include "episode.h"

/*
 * Call-only setup description. This record and config may live on the original
 * task stack; their small pointer/scalar contents are copied before any output
 * initialization and are never retained. They must not overlap initialized
 * backing. resources owns its own immutable configuration copy afterward.
 *
 * root/pool/slots/resources/frames are exclusive fresh private storage, or have
 * an independently completed prior detach AND every old observer has ended.
 * No constructor can infer that ownership from a raw address. In particular,
 * do not pass another task's live root or reset an unknown attached allocation.
 * Every retained object/array is outside both original source and auxiliary
 * stacks, correctly aligned and mutually disjoint. image_slot and config.stack
 * are already initialized, caller-retained shared records, also outside those
 * regions. The helper validates their known extents without resetting them.
 *
 * capacity is the explicit nonzero common slot/frame array extent. The caller
 * supplies that storage; this helper allocates nothing and selects no default
 * count. Extent checks do not prove mapping or writability.
 *
 * Callback code, opaque contexts, source/code/module/object backing and all
 * referenced allocations remain caller-retained through their true last users.
 * Their extents are not guessed from a pointer. Auxiliary context, guards,
 * scheduler/IRQ/unwinder compatibility and the complete recursive control-stack
 * requirement are separate caller admission proofs; numerical bounds establish
 * none of them. origin_gs is an explicit initial input; source capture refreshes
 * the actual publication's kernel GS under its existing contract.
 */
struct kd_task_setup_args {
	struct kd_task_root_context *root;
	struct kd_request_pool *pool;
	struct kd_request_slot *slots;
	struct kd_episode_resources *resources;
	struct kd_episode_frame *frames;
	unsigned int capacity;
	unsigned long origin_gs;
	unsigned long aux_low;
	unsigned long aux_high;
	unsigned long aux_current;
	unsigned long required_control_bytes;
	const struct kd_episode_config *config;
};

/*
 * Current original task, TASK_RUNNING and ordinary sleepable context only,
 * before its first declared source call. No source admission, lookup escape or
 * unsupported reentry is allowed during setup. Existing current-task attachment
 * returns -EEXIST before any initialization; no live root is silently replaced.
 * Validate first, then initialize root, attach, initialize resources and bind.
 * Source admission may begin only after success. There is no source execution,
 * image lookup/publication or per-request construction in this helper.
 *
 * A later setup failure detaches the exact unused initial-native endpoint; all
 * slot/frame/image/source users are still absent. Successful unwind returns the
 * original setup error. A detach error is returned instead and the caller keeps
 * all backing/holds: failure never authorizes freeing a still-attached root or
 * blindly retrying its constructor. Under valid private/admission preconditions
 * no actor can make that unused-root unwind busy.
 */
int kd_task_setup_current(const struct kd_task_setup_args *args);

/*
 * Caller closes new source admission and independently drains every escaped
 * user/control, callback, image/return/notifier/binding observer and abandoned
 * auxiliary frame first. Current must retain the exact current NATIVE endpoint.
 * Make one task-progress pass and then attempt exact atomic root detach. Never
 * loop/wait on pending: the current native endpoint itself can keep a finished
 * pool slot occupied until detach revokes it. pending reports the progress pass
 * BEFORE detach and may be true even on successful detach; it is not a full
 * drain proof. Its storage is caller-retained and must not alias control backing.
 *
 * Errors preserve the still-attached backing for explicit later progress/drain;
 * they do not permit task exit or storage/stack release. Success ends every
 * access to root, expected_native and their backing inside this helper. It
 * supplies no fork hook, global exit policy, allocation or freeing mechanism.
 */
int kd_task_teardown_current(struct kd_task_root_context *root,
			     struct kd_execution_binding *expected_native,
			     bool *pending);

#endif
