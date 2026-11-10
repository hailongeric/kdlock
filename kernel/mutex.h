/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_MUTEX_H
#define KDLOCK_MUTEX_H

#include <linux/atomic.h>
#include "mutex_release.h"

struct kd_thread_state;
struct kd_mutex_node;
struct kd_mutex_batch;
struct task_struct;

/* Private source-rebuilt object layout; no old binary/layout compatibility. */
struct kd_mutex {
	struct kd_mutex_node *tail;
	struct kd_mutex_batch *owner;
};

#define KD_MUTEX_INITIALIZER { .tail = NULL, .owner = NULL }

enum kd_mutex_selection {
	KD_MUTEX_PRIVATE,
	KD_MUTEX_OFFERED,
	KD_MUTEX_SELECTED_LOCAL,
	KD_MUTEX_SELECTED_PROXY,
};

/*
 * LOCAL_GRANTED leaves source CALL/RET completion to the requester bridge.
 * Every PROXY outcome refers to current S_W and never authorizes completion
 * of the old acquisition CALL again. OPERATION_DONE alone does not end its
 * logical grant; the owner waits for its exact source unlock before serving
 * another request. All outcomes need the root bridge's exact binding/phase
 * validation before it mutates S_W or resumes source.
 */
enum kd_mutex_outcome {
	KD_MUTEX_OUTCOME_UNSET,
	KD_MUTEX_LOCAL_GRANTED,
	KD_MUTEX_PROXY_OPERATION_DONE,
	KD_MUTEX_PROXY_EPISODE_DONE,
	KD_MUTEX_PROXY_ORIGIN_SUFFIX,
	KD_MUTEX_PROXY_UNWIND_PARENT,
};

/* Positive pre-enqueue disposition; this is not a grant or queue membership. */
enum kd_mutex_acquire_disposition {
	KD_MUTEX_QUEUE_PATH_READY = 0,
	KD_MUTEX_UNSUPPORTED_DEFERRED_REACQUIRE,
};

/*
 * Snapshot for node.retained_prior from the common source-grant lookup. The
 * caller retains that prior and its core grant user through every attempt.
 * owner/phase/route are diagnostic observations, valid when owner is non-NULL;
 * they confer no physical authority and acquire no independent storage user.
 * Read/dereference these pointers only while that exact prior user remains held;
 * a successful enqueue does not itself retain the prior control or owner.
 */
struct kd_mutex_retained_gate {
	struct kd_mutex_release_owner *owner;
	enum kd_mutex_owner_phase owner_phase;
	enum kd_mutex_unlock_phase unlock_phase;
	enum kd_mutex_unlock_route route;
};

enum kd_mutex_unlock_action {
	KD_MUTEX_UNLOCK_BATCH_BODY,
	KD_MUTEX_UNLOCK_BATCH_HEAD,
	KD_MUTEX_UNLOCK_DEFERRED_PARENT,
};

struct kd_mutex_ops {
	/*
	 * Accept the exact stopped offer for this local physical winner.
	 * Optional for a raw local-only request; if supplied it also runs when
	 * ready is false. Proxy eligibility does not decide local bridge needs.
	 */
	int (*selected_local)(struct kd_mutex_node *node, void *context);
	/*
	 * An actual logical grant is already bound in node->release. Accept its
	 * exact source offer, finish the source acquisition CALL/RET once, then
	 * execute admitted fragments/recursive operations or a valid handback.
	 * Export/stop the old executor and establish the result's current-state
	 * route before returning. This synchronous callback runs outside atomics
	 * and must not finish or reenter combining of its own batch. A live-grant
	 * result must enable a retained origin/outer actor to reach its unlock and
	 * publish unwind readiness; it cannot strand the owner waiting for itself.
	 */
	enum kd_mutex_outcome (*execute_proxy)(struct kd_mutex_node *node,
					     void *context);
};

/*
 * Caller-preallocated storage. Queue links/selection and long-lived release
 * control are distinct subrecords; neither contains a W register packet.
 * state always points directly to the original canonical S_W.
 *
 * Initialization takes one requester-task reference through node retirement.
 * Storage and its containing allocation remain valid through retirable.
 * It is private/fresh or its prior retirable publication was observed.
 * ready publication requires captured/materialized S_W, stopped source and
 * retained source/code/binding/control inputs. An unprepared request remains
 * local-only and needs no source register capture merely to queue. Its stable
 * thread core pointer and caller-owned node/context must still exist.
 */
struct kd_mutex_node {
	struct kd_mutex_node *next;
	atomic_t selection;
	int turn;
	int queue_done;
	int result_ready;
	int retirable;
	bool enqueued;
	bool wait_started;
	bool source_granted;
	bool ready;
	struct task_struct *requester;
	struct kd_thread_state *state;
	const void *acquisition;
	const void *operation;
	const void *grant_user;
	const void *result_user;
	const struct kd_mutex_ops *ops;
	void *context;
	struct kd_mutex *lock;
	struct kd_mutex_batch *batch;
	enum kd_mutex_outcome outcome;
	struct kd_mutex_release release;
	struct kd_mutex_node *retained_prior;
	struct kd_mutex_retained_gate retained_gate;
};

/*
 * One physical MCS owner/batch. This storage survives finish_physical until
 * reap succeeds, even if the originating source scope or C frame has ended.
 * The physical head node remains retained until the whole context retires.
 * Batch storage may be embedded in its own head request or retained separately,
 * never in another node allocation that may become reusable sooner.
 * Its obligations are exclusively embedded node.release records bound by this
 * component. Do not insert foreign release records or retire these embedded
 * records directly: reap owns their final queue/task-reference publication.
 */
struct kd_mutex_batch {
	struct kd_mutex_release_owner release_owner;
	struct kd_mutex *lock;
	struct kd_mutex_node *head;
	struct kd_mutex_node *serving;
	unsigned int proxy_limit;
	unsigned int proxy_served;
	bool initialized;
	bool head_retired;
};

void kd_mutex_init(struct kd_mutex *lock);
/* Private fresh storage only; this cannot reset an unreaped owner context. */
void kd_mutex_batch_init(struct kd_mutex_batch *batch);
/* Private preparation may start with retained_prior=NULL and update the field
 * while the node remains PRIVATE. Before preflight/enqueue, NULL means the
 * caller's exact node->state lookup found no matching retained grant or checked
 * every matching grant as ordinary-queue eligible. Otherwise it names a distinct
 * same-state/object acquisition with its exact core grant user held. Scan all
 * matching grants, not merely released history.
 * No registry lookup or source-packet copy belongs to this component.
 */
int kd_mutex_node_init(struct kd_mutex_node *node,
		       struct kd_thread_state *state,
		       struct kd_mutex_node *retained_prior,
		       const void *acquisition, const void *operation,
		       const void *grant_user, const void *result_user,
		       bool ready, const struct kd_mutex_ops *ops, void *context);
/* Release private initialized storage that was never enqueued; no cancellation. */
int kd_mutex_node_discard(struct kd_mutex_node *node);

/*
 * Check before source operation ENTERED/publication as well as before enqueue.
 * 0 permits the ordinary queue path. A positive
 * KD_MUTEX_UNSUPPORTED_DEFERRED_REACQUIRE reports an earlier same-object
 * logical unlock that was deferred while its old physical batch remains OPEN.
 * This pattern is outside the selected workload scope; do not resolve/enable
 * it or synthesize a successful source mutex_lock result. The exact prior/gate
 * snapshot remains available with no queue, selection, grant or source effect.
 * Consume the observation before changing the retained prior.
 * A still-live source acquisition is -EDEADLK, not a new nonrecursive grant.
 * Negative identity/lifetime errors are not ordinary queue eligibility.
 *
 * A normal OWNER_HANDLED unlock with OWNER route and no deferred history is
 * ordinary-queue eligible even while that prior batch holds the physical gate.
 * Source continued after a completed normal proxy callback may acquire the
 * object again; a retained batch alone does not make it the excluded case.
 * A release already committed to RELEASE_PREPARED may complete normally; a
 * PHYSICALLY_RELEASED prior no longer obstructs the ordinary queue path.
 * This helper adds no special delegation path, regrant, mailbox, owner polling,
 * forced physical release or transfer of release authority.
 */
int kd_mutex_preflight(struct kd_mutex *lock, struct kd_mutex_node *node);

/*
 * Split enqueue/await permits a ready publisher to claim local before a
 * combiner wins the same atomic selection. choose_local reserves execution,
 * not physical exclusion: it must still wait for its MCS turn. A published
 * request cannot be discarded or treated as a failed native acquisition.
 * enqueue/acquire propagate the positive preflight disposition before any
 * physical queue effect; raw callers must handle it separately from success.
 * Split enqueue callers receive the same check and cannot skip this boundary.
 * Reserve a freshly initialized or successfully reaped possible-local batch
 * before enqueue, even when this request may ultimately be served by a proxy.
 * Turn/result waiting uses ordinary TASK_UNINTERRUPTIBLE sleep/wakeup in this
 * task-context lane. Short predecessor-link publication waits poll with
 * cond_resched, because the producer's link store must be its final previous-
 * node access. Neither wait strategy is a performance qualification.
 */
int kd_mutex_enqueue(struct kd_mutex *lock, struct kd_mutex_node *node);
bool kd_mutex_choose_local(struct kd_mutex_node *node);
int kd_mutex_await(struct kd_mutex_node *node, struct kd_mutex_batch *batch,
		   unsigned int proxy_limit, enum kd_mutex_outcome *outcome);
int kd_mutex_acquire(struct kd_mutex *lock, struct kd_mutex_node *node,
		     struct kd_mutex_batch *batch, unsigned int proxy_limit,
		     enum kd_mutex_outcome *outcome);

/*
 * Explicit caller-selected per-call bound, also capped by the total batch
 * proxy_limit fixed at await. Counts successful proxy grants, not returned
 * bodies or physical chain measurements. This may run before the head's own
 * logical acquisition, or after its source unlock is owner-handled. It cannot
 * interleave another grant with a live head grant or a still-running proxy
 * callback. Immediate local-only/locally selected successors are never bypassed.
 */
int kd_mutex_combine(struct kd_mutex_batch *batch, unsigned int proxy_limit,
		     unsigned int *served);

/*
 * Source effects/CALL words and cursor advancement belong to the state bridge.
 * Every call already retains its exact node/control user; unregistered stale
 * pointers are not made live by an identity check. DEFERRED_PARENT records a
 * marker only: publish_outer_unwind is a later export/stop/notification step.
 */
int kd_mutex_source_unlock(struct kd_mutex_node *node,
			   struct kd_thread_state *state,
			   struct kd_mutex_batch *active_batch,
			   const void *notifier,
			   enum kd_mutex_unlock_action *action);
int kd_mutex_publish_outer_unwind(struct kd_mutex_node *node,
				   const void *notifier,
				   struct kd_mutex_release_owner **target);
int kd_mutex_outer_notification_done(struct kd_mutex_node *node,
				      const void *notifier);
int kd_mutex_hold_return(struct kd_mutex_node *node, const void *return_user);
int kd_mutex_drop_return(struct kd_mutex_node *node, const void *return_user);

/*
 * The requester acknowledges only after its last outcome/binding read. This
 * does NOT drop the core's grant-list reference in release.source_user.
 * grant_unlinked is separate and requires that exact physically completed
 * grant already be removed from its canonical core's live/custody index.
 */
int kd_mutex_result_consumed(struct kd_mutex_node *node, const void *result_user);
int kd_mutex_grant_unlinked(struct kd_mutex_node *node, const void *grant_user);

/*
 * finish performs actual MCS physical release, not merely batch-role exit.
 * It does not wait for core collection or retire context. reap is owner-only,
 * returns -EBUSY while exact result/core/return/notifier users remain, and must
 * be retried while the context stays retained. It never dereferences lock.
 */
int kd_mutex_finish_batch(struct kd_mutex_batch *batch);
int kd_mutex_reap_batch(struct kd_mutex_batch *batch);
/* Owner reaping must make progress independently; do not self-wait on it. */
void kd_mutex_wait_retirable(struct kd_mutex_node *node);

#endif
