/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_WAIT_QUEUE_H
#define KD_WAIT_QUEUE_H

#include <linux/spinlock.h>
#include <linux/sched/wake_q.h>
#include <linux/types.h>

struct task_struct;
struct kd_wait_request;
struct kd_wait_node;
struct kd_admission;

/* A view, not embedded storage. Existing objects provide their guard and one
 * head word. Distinct condition heads can use the same object's guard. */
struct kd_wait_queue {
	raw_spinlock_t *guard;
	struct kd_wait_node **head;
};

enum kd_wait_state {
	KD_WAIT_PRIVATE,
	KD_WAIT_QUEUED,
	KD_WAIT_SELECTED_DRAINING,
	KD_WAIT_ACQUIRED,
	KD_WAIT_EXECUTING,
	KD_WAIT_RELEASED,
	KD_WAIT_RETURN_ACK,
	KD_WAIT_CANCELING,
	KD_WAIT_CANCEL_ACK,
	KD_WAIT_RETIRED,
};

enum kd_wait_member_kind {
	KD_WAIT_ACQUISITION,
	KD_WAIT_CONDITION,
};

enum kd_wait_decision {
	KD_WAIT_PENDING,
	KD_WAIT_GRANTED,
	KD_WAIT_CLEANUP_REQUIRED,
	KD_WAIT_CANCELED,
	KD_WAIT_STALE,
};

/* Tentative selection/cleanup custody is independent of a queue node or a
 * physical JIT frame. Its transport keeps this exact record and request live.
 * There is at most one selection for an invocation. */
struct kd_wait_selection {
	struct kd_wait_request *request;
	u64 generation;
	struct task_struct *executor;
};

/* Exact pending physical/phase cleanup custody, separate from selection.
 * A request cannot acknowledge cancellation while this token remains live. */
struct kd_wait_cleanup {
	struct kd_wait_request *request;
	u64 generation;
	void *owner;
};

/* The caller retains this record through all queue, selection and execution
 * obligations. Immutable inputs are initialized before any publication.
 * State and memberships are protected by guard. Out-of-guard state polling is
 * a notification hint only: result consumption and reuse also take the guard,
 * after the publishing operation and wake collection finish. Execution/source/packet
 * custody remains in the transport's retained context, never in a list link. */
struct kd_wait_request {
	void *identity;
	u64 generation;
	struct task_struct *logical_origin;
	struct task_struct *physical_waiter;
	unsigned int wait_state;
	bool may_delegate;
	enum kd_wait_state state;
	raw_spinlock_t *guard;
	struct kd_wait_node *acquisition;
	struct kd_wait_node *memberships;
	struct kd_wait_selection *selection;
	/* Local head promotion has the same exact selection lifetime, without
	 * borrowing a temporary selector's stack record. */
	struct kd_wait_selection local_selection;
	struct kd_wait_cleanup *cleanup;
	struct kd_admission *admission;
	raw_spinlock_t *terminal_guard;
	void *context;
};

struct kd_wait_node {
	struct kd_wait_node *next;
	struct kd_wait_node *prev;
	/* Separate links enumerate this request's simultaneous memberships. */
	struct kd_wait_node *request_next;
	struct kd_wait_node *request_prev;
	struct kd_wait_node **queue_head;
	struct kd_wait_request *request;
	u64 generation;
	enum kd_wait_member_kind kind;
};

typedef bool (*kd_wait_grant_fn)(struct kd_wait_request *request, void *argument);

static inline struct kd_wait_queue
kd_wait_queue_view(raw_spinlock_t *guard, struct kd_wait_node **head)
{
	struct kd_wait_queue queue = { .guard = guard, .head = head };

	return queue;
}

/* (identity == NULL, generation == 0) creates a local invocation identity from
 * a permanent per-CPU namespace and a nonreset sequence. Explicit transport
 * identities must provide a nonzero generation and remain unique on reuse. */
void kd_wait_request_init(struct kd_wait_request *request, void *identity,
			  u64 generation, struct task_struct *logical_origin,
			  struct task_struct *physical_waiter,
			  unsigned int wait_state, bool may_delegate, void *context);
void kd_wait_node_init(struct kd_wait_node *node, struct kd_wait_request *request,
		       enum kd_wait_member_kind kind);

/* All _locked operations require queue.guard with the caller's IRQ state
 * preserved. Link/unlink change only membership, not public acquisition state.
 * Condition adapters use these without another acquisition election. */
void kd_wait_link_locked(const struct kd_wait_queue *queue, struct kd_wait_node *node);
void kd_wait_unlink_locked(const struct kd_wait_queue *queue, struct kd_wait_node *node);
/* Reorder one live membership without withdrawal or request-state changes. */
void kd_wait_move_before_locked(const struct kd_wait_queue *queue,
			       struct kd_wait_node *node, struct kd_wait_node *before);
void kd_wait_publish_locked(const struct kd_wait_queue *queue, struct kd_wait_node *node);
struct kd_wait_node *kd_wait_first_locked(const struct kd_wait_queue *queue);
struct kd_wait_node *kd_wait_next_locked(const struct kd_wait_queue *queue,
				       const struct kd_wait_node *node);
struct kd_wait_request *kd_wait_find_locked(const struct kd_wait_queue *queue,
					  void *identity, u64 generation);

bool kd_wait_select_locked(const struct kd_wait_queue *queue,
			   struct kd_wait_request *request,
			   struct kd_wait_selection *selection,
			   struct task_struct *executor);
/* A selection record starts with request == NULL and is reusable only after
 * selection_drop. Other fields do not authorize selection or physical entry. */
/* grant is a bounded, nonblocking actual-grant operation under this guard.
 * It must enforce the lock's eligibility and physical/phase/reader conditions.
 * It runs before the logical origin's signal test; image or pin readiness is
 * not acquisition. No body, drainage, scheduling or wake delivery runs here. */
enum kd_wait_decision
kd_wait_decide_locked(const struct kd_wait_queue *queue,
		      struct kd_wait_request *request, u64 generation,
		      kd_wait_grant_fn grant, void *argument);
/* Drop only after the selection's exact tentative owner/phase cleanup, or
 * transfer to a retained acquired execution record. No automatic physical
 * unlock is performed. Cancellation ACK requires every membership gone. */
void kd_wait_selection_drop_locked(struct kd_wait_request *request,
				   struct kd_wait_selection *selection);
bool kd_wait_cancel_ack_locked(struct kd_wait_request *request);
void kd_wait_cleanup_take_locked(struct kd_wait_request *request,
				 struct kd_wait_cleanup *cleanup, void *owner);
void kd_wait_cleanup_drop_locked(struct kd_wait_request *request,
				 struct kd_wait_cleanup *cleanup);
/* A captured cancellation transfers to retained state before publishing ACK.
 * The caller proves sole actor custody, as for the postgrant rebind operation.
 * Return the old object guard for unlock. Only after unlocking it may the
 * caller take the retained guard and publish cancel_ack; no object access may
 * follow that acknowledgment. An independently retained cleanup token may
 * remain across this move; cancel_ack still refuses until its final release
 * and exact token drop under the retained guard. */
raw_spinlock_t *kd_wait_cancel_rebind_locked(struct kd_wait_request *request,
					    raw_spinlock_t *retained_guard);
void kd_wait_set_state_locked(struct kd_wait_request *request,
			     enum kd_wait_state state);
/* A conventional local call returns at acquisition, before its caller's body.
 * Its adapter first transfers exact acquisition authority to the physical
 * owner record. This acknowledges only the request's result, not lock release. */
void kd_wait_finish_local_locked(struct kd_wait_request *request);
/* Postgrant storage transfer, never another publication/election. Both exact
 * descriptors name the same invocation, and the old descriptor has no queue,
 * selection or cleanup users. The destination remains under the same guard. */
void kd_wait_move_acquired_locked(struct kd_wait_request *source,
				 struct kd_wait_request *destination);
/* Legacy continuation handoff first transfers ongoing packet/execution and
 * acquisition authority to an independently retained owner/frame record. This
 * acknowledges that transfer, not physical release or returned body completion.
 * Required-proxy execution must not use it as an implicit origin continuation. */
void kd_wait_handoff_locked(struct kd_wait_request *request);
/* Before the final public object release, its sole postgrant lifecycle owner
 * may move state serialization to independently retained request storage.
 * The caller holds the old guard and proves that all old-guard users, including
 * origins/selectors which could have cached it, have retired their access.
 * Empty memberships/selection are necessary, not that complete proof. Publish
 * no execution that can release the object before this handover is complete.
 * Return the old guard for unlock; never unlock request->guard after rebinding.
 * This changes no acquisition, cancellation result or physical owner. */
raw_spinlock_t *kd_wait_rebind_locked(struct kd_wait_request *request,
				     raw_spinlock_t *retained_guard);

/* Collection retains task references, never node pointers. Delivery is outside
 * the guard using wake_up_q(). Atomic release adapters may omit notification
 * and use their required timed predicate recheck. */
void kd_wait_collect_wake_locked(const struct kd_wait_queue *queue,
				 struct wake_q_head *wake);
void kd_wait_collect_request_wake_locked(struct kd_wait_request *request,
					 struct wake_q_head *wake);

#endif /* KD_WAIT_QUEUE_H */
