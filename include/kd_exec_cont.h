/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_EXEC_CONT_H
#define KD_EXEC_CONT_H

#include "kd_exec.h"
#include "kd_wait_queue.h"

enum kd_exec_cont_state {
	KD_CONT_UNUSED,
	KD_CONT_READY,
	KD_CONT_BOUND,
	KD_CONT_SUSPENDED,
	KD_CONT_RETURNED,
	KD_CONT_RETIRED,
	KD_CONT_FINISHING,
};

enum kd_exec_cont_wait {
	KD_CONT_WAIT_NONE,
	KD_CONT_WAIT_CHILD,
	KD_CONT_WAIT_SERVICE,
};

struct kd_exec_continuation;

enum kd_exec_service_api {
	KD_SERVICE_NONE,
	KD_SERVICE_MUTEX_LOCK,
	KD_SERVICE_MUTEX_LOCK_INTERRUPTIBLE,
	KD_SERVICE_MUTEX_LOCK_KILLABLE,
	KD_SERVICE_MUTEX_UNLOCK,
	KD_SERVICE_RWSEM_WRITE,
	KD_SERVICE_RWSEM_WRITE_INTERRUPTIBLE,
	KD_SERVICE_RWSEM_WRITE_KILLABLE,
	KD_SERVICE_RWSEM_UP_WRITE,
	KD_SERVICE_RWSEM_DOWNGRADE,
	KD_SERVICE_RWSEM_UP_READ,
};

struct kd_exec_service_call {
	enum kd_exec_service_api api;
	unsigned long object;
	unsigned int wait_state;
	bool acquire;
	bool may_delegate;
	bool returns_integer;
	struct kd_call_state call;
	const struct kd_wait_request *child;
	void *child_identity;
	u64 child_generation;
};

/* These are read-only queries over root-owned retained acquisition records.
 * They must not acquire an object lock, schedule or touch a released object. */
struct kd_exec_service_ops {
	bool (*validate)(const void *scope, const struct kd_exec_continuation *cont);
	bool (*all_released)(const void *scope);
	bool (*outer_released)(const void *scope);
	bool (*has_nested)(const void *scope);
	unsigned int (*depth)(const void *scope);
};

struct kd_exec_capture_lease {
	struct task_struct *origin;
	unsigned long stack_base;
	void (*stack_put)(struct task_struct *task);
	bool held;
};

/* These callbacks inspect a separately retained acquisition record, never an
 * object whose public unlock already permitted destruction. They do not grant
 * physical ownership and must not sleep. The caller retains that record until
 * every reference and physical release acknowledgment has finished. */
struct kd_exec_owner_ops {
	bool (*valid)(const void *identity, u64 generation);
	bool (*released)(const void *identity, u64 generation);
};

struct kd_exec_owner_ref {
	struct list_head link;
	struct list_head borrowers;
	struct list_head borrow_link;
	struct list_head storage_link;
	struct kd_exec_continuation *continuation;
	struct kd_exec_continuation *storage_owner;
	struct kd_exec_owner_ref *source;
	const struct kd_exec_owner_ops *ops;
	const void *identity;
	u64 generation;
};

/* Retained alongside a capture slot, never in a helper frame below captured
 * SP. The common request is the only acquisition/cancellation authority. This
 * state describes execution custody, not another grant election. The frame is
 * stable storage; its parent/depth describe only a current physical binding. */
struct kd_exec_continuation {
	struct kd_wait_request *request;
	u64 generation;
	struct kd_exec_frame frame;
	struct kd_regs *packet;
	struct kd_exec_continuation *parent;
	u64 parent_generation;
	struct kd_exec_continuation *root;
	u64 root_generation;
	unsigned int logical_depth;
	struct list_head children;
	struct list_head child_link;
	struct list_head owners;
	/* References created here may move to a continuing parent. Their creator
	 * anchor cannot retire until those exact reference nodes are released. */
	struct list_head storage_owners;
	/* Root guard serializes only retained metadata/token changes, never queue
	 * grant, body execution, callbacks, physical release or wake delivery. */
	raw_spinlock_t guard;
	/* Post-grant request lifecycle guard, after the queue adapter's explicit
	 * old-guard access retirement/ACK. It is not the root metadata guard. */
	raw_spinlock_t lifecycle_guard;
	struct kd_exec_continuation *packet_owner;
	struct task_struct *executor;
	struct task_struct *resume_executor;
	void *service_scope;
	const struct kd_exec_service_ops *service_ops;
	struct kd_exec_service_call service_call;
	struct kd_call_state pending_call;
	unsigned long stack_base;
	void (*stack_put)(struct task_struct *task);
	enum kd_exec_cont_state state;
	enum kd_exec_cont_wait wait;
	int result;
	bool source_lease;
	bool stack_lease;
};

int kd_exec_capture_lease_get(struct kd_exec_capture_lease *lease,
	struct task_struct *origin);
void kd_exec_capture_lease_put(struct kd_exec_capture_lease *lease);
int kd_exec_cont_adopt_acquired(struct kd_exec_continuation *continuation,
	struct kd_wait_request *request, struct kd_regs *packet,
	unsigned long entry_ip, unsigned long lock, unsigned long gsbase,
	unsigned int entry_abi, struct kd_exec_capture_lease *lease);
int kd_exec_cont_set_service(struct kd_exec_continuation *continuation,
	void *scope, const struct kd_exec_service_ops *ops);
int kd_exec_cont_service_prepare(struct kd_exec_frame *frame,
	enum kd_exec_service_api api, unsigned long object, unsigned int wait_state,
	bool acquire, bool may_delegate, bool returns_integer);
int kd_exec_cont_service_child(struct kd_exec_continuation *continuation,
	const struct kd_wait_request *child);
/* Returns KD_EXE_RUN_TO_UNLOCK at the final release without consuming that
 * source CALL word; the ordinary origin restoration consumes it exactly once.
 * Other results advance the CALL and return zero for retained-image resume. */
int kd_exec_cont_service_complete(struct kd_exec_continuation *continuation,
	const struct kd_wait_request *child, int result);

/* Internal errors never become new public lock results. Callers reserve the
 * anchor and capture resources before publication. Parent is optional; a child
 * shares its root packet/leases and must subsequently use child_begin. */
int kd_exec_cont_init(struct kd_exec_continuation *continuation,
	struct kd_wait_request *request, struct kd_regs *packet,
	unsigned long entry_ip, unsigned long lock, unsigned long gsbase,
	unsigned int entry_abi, struct kd_exec_continuation *parent);
struct kd_exec_frame *kd_exec_cont_bind(struct kd_exec_continuation *continuation,
	struct kd_mutex *lock, struct kd_exec_outer_unlock *hook);
int kd_exec_cont_suspend(struct kd_exec_continuation *continuation,
	enum kd_exec_cont_wait reason);
struct kd_exec_frame *kd_exec_cont_resume(struct kd_exec_continuation *continuation);
int kd_exec_cont_child_begin(struct kd_exec_continuation *parent,
	struct kd_exec_continuation *child, const struct kd_call_state *pending);
int kd_exec_cont_child_acquired(struct kd_exec_continuation *child);
/* local_grant returns just the acquisition result to the submitting executor;
 * a proxy child returns only after its body endpoint. No child is enabled by
 * these storage helpers, and old fixed-size ledgers remain unchanged. */
int kd_exec_cont_child_return(struct kd_exec_continuation *child, int result,
	bool local_grant);
int kd_exec_cont_owner_get(struct kd_exec_continuation *continuation,
	struct kd_exec_owner_ref *reference, const void *identity, u64 generation,
	const struct kd_exec_owner_ops *ops);
void kd_exec_owner_ref_init(struct kd_exec_owner_ref *reference);
int kd_exec_cont_owner_borrow(struct kd_exec_continuation *continuation,
	struct kd_exec_owner_ref *reference, struct kd_exec_owner_ref *source);
int kd_exec_cont_owner_put(struct kd_exec_owner_ref *reference);
int kd_exec_cont_return(struct kd_exec_continuation *continuation, int result);
int kd_exec_cont_retire(struct kd_exec_continuation *continuation);

#endif /* KD_EXEC_CONT_H */
