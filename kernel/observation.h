/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_OBSERVATION_H
#define KDLOCK_OBSERVATION_H

#include <linux/sched.h>
#include <linux/tracepoint.h>

/* Scalar observations never hold source rights, references or a register bank.
 * A listener copies this call-only record without waiting or changing protocol
 * state. Register before admitting immutable source; unregister and synchronize
 * only after the listener's runtime/source users and callbacks have drained.
 * Pointer values identify retained objects at this event, not future references.
 * SLOT_RESERVE and SLOT_FREE delimit each request lifetime across address reuse.
 * JIT_EXIT: ip/source, cursor/current, related/target, phase/IO phase,
 * result/exit kind, flags/detail. JIT_OPERATION: related/operation request,
 * object/argument, result/operation kind, phase/lock recipe or unlock action.
 * CHILD_RETURN: related/child node, source_user/previous endpoint,
 * return_user/returned endpoint, result/raw outcome; CURRENT_JIT validates
 * the returned cursor. EPISODE_DONE is the original positive driver outcome,
 * before root normalization; it does not identify a whole C-function return.
 * Release events use related/release, phase/unlock phase, result/route and
 * exact current or consumed user tokens. SLOT_FREE uses cursor only for the
 * atomic binding identity, not source registers; its flags snapshot last users.
 */
enum kd_observation_kind {
	KD_OBS_SLOT_RESERVE = 1, KD_OBS_SLOT_FREE,
	KD_OBS_ENQUEUE, KD_OBS_SELECT_LOCAL, KD_OBS_SELECT_PROXY, KD_OBS_GRANT,
	KD_OBS_PROXY_RETURN, KD_OBS_QUEUE_DONE, KD_OBS_NODE_RETIRE_READY,
	KD_OBS_RELEASE_BIND, KD_OBS_RELEASE_REQUEST, KD_OBS_RELEASE_DEFER,
	KD_OBS_RELEASE_UNWIND, KD_OBS_RELEASE_NOTIFY_DONE, KD_OBS_RELEASE_HANDLED,
	KD_OBS_RELEASE_SOURCE_DROP, KD_OBS_RELEASE_RETURN_DROP,
	KD_OBS_PHYSICAL_BEGIN, KD_OBS_PHYSICAL_END, KD_OBS_RELEASE_RETIRE,
	KD_OBS_OWNER_RETIRE, KD_OBS_FRAME_PREPARE, KD_OBS_JIT_ENTER,
	KD_OBS_JIT_EXIT, KD_OBS_JIT_OPERATION, KD_OBS_CHILD_RETURN,
	KD_OBS_EPISODE_DONE, KD_OBS_FORWARD, KD_OBS_NATIVE_UNLOCK, KD_OBS_OWNER_STOP,
	KD_OBS_READ_ACQUIRE, KD_OBS_READ_RELEASE, KD_OBS_WRITE_DOWNGRADE_REAL,
	KD_OBS_WRITE_DOWNGRADE_RETAINED, KD_OBS_NATIVE_MODE,
};

#define KD_OBS_FLAG_ENQUEUED             (1UL << 0)
#define KD_OBS_FLAG_SOURCE_GRANTED       (1UL << 1)
#define KD_OBS_FLAG_QUEUE_DONE           (1UL << 2)
#define KD_OBS_FLAG_RESULT_READY         (1UL << 3)
#define KD_OBS_FLAG_RESULT_USER_PRESENT  (1UL << 4)
#define KD_OBS_FLAG_POOL_USERS_EMPTY     (1UL << 5)
#define KD_OBS_FLAG_COMPONENTS_IDLE      (1UL << 6)
#define KD_OBS_FLAG_CONTROL_STOPPED      (1UL << 7)
#define KD_OBS_FLAG_TERMINAL_FOREIGN     (1UL << 8)
#define KD_OBS_FLAG_SOURCE_CLOSED        (1UL << 9)
#define KD_OBS_FLAG_CURRENT_JIT          (1UL << 10)
#define KD_OBS_FLAG_NODE_RETIRABLE       (1UL << 11)
#define KD_OBS_FLAG_ATOMIC_CONTEXT       (1UL << 12)

struct kd_observation {
	unsigned long kind, task, state, origin, node, acquisition, parent;
	unsigned long owner, owner_task, object, image, ip, cursor, related;
	unsigned long phase, result, flags, source_user, return_user, notifier;
};

/* Linux 7 DECLARE_TRACE adds the _tp suffix to the generated interface. */
DECLARE_TRACE(kdlock_observe,
	TP_PROTO(const struct kd_observation *event), TP_ARGS(event));

#define kd_observe(_kind, ...) do { \
	if (trace_kdlock_observe_tp_enabled()) { \
	 const struct kd_observation kd_event = { \
	  .kind = (_kind), .task = (unsigned long)current, __VA_ARGS__ }; \
	 trace_kdlock_observe_tp(&kd_event); \
	} \
} while (0)

#endif
