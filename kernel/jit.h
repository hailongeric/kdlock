/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_JIT_H
#define KDLOCK_JIT_H

#include "mutex.h"
#include "state.h"
#include "task_state.h"

/* All addresses describe one retained source/configuration identity. */
enum kd_jit_site_kind {
	KD_JIT_SITE_CALL,
	KD_JIT_SITE_JUMP,
	KD_JIT_SITE_OTHER,
};

struct kd_jit_source_site {
	unsigned long ip;
	unsigned long next_ip;
	enum kd_jit_site_kind kind;
};

/*
 * A caller-retained, coherent entry and its source metadata. This describes
 * inputs to invocation, not a publication/reclamation policy or coverage ACK.
 * The owner retains code, source, metadata and return dependencies through all
 * their actual users; an address/version comparison cannot supply that hold.
 */
struct kd_jit_image {
	const void *source_identity;
	unsigned int abi_version;
	unsigned int packet_size;
	unsigned int io_size;
	kd_jit_entry_fn entry;
	const unsigned long *entry_sites;
	unsigned int entry_count;
	const struct kd_jit_source_site *source_sites;
	unsigned int source_count;
};

/*
 * The current wrapper runs on a distinct executor task/stack. Origin W's wait
 * control must already be separated from the source stack lent to generated
 * code. The caller proves that separation, valid source stack accesses and
 * sleepable physical context before enabling this route. current == W is
 * refused; an instruction budget alone does not prevent stack overlap.
 */
/* A pending exit retains this exact image until explicit consumption. */
int kd_jit_enter(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding);

/* Exact registered API target lookup, never a name-substring classification. */
typedef enum kd_operation_kind (*kd_jit_resolve_operation_fn)(
		void *context, unsigned long target);

/*
 * Classify a retained target once, then materialize precisely the unperformed
 * source CALL transition. The canonical io is consumed before nested work can
 * overwrite it. A CALL_STAGED miss already pushed its real return word; an API
 * entry/JMP uses the existing source frame. No operand is evaluated again.
 * -ENOENT leaves an ordinary coverage/frontier result for the forward route;
 * an unsupported recognized operation must also use that exact forward route.
 */
int kd_jit_prepare_operation(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding, const void *identity,
		 kd_jit_resolve_operation_fn resolve, void *context,
		 const struct kd_source_stack_ops *stack);

/* Consume/report the pending exit before admitting another image or native
 * suffix. TARGET_READY first needs exact operation handling or forward staging.
 * The caller records required learning/disposition data before consumption;
 * this helper is not a coverage ACK or a feedback-capacity policy.
 */
int kd_jit_consume_exit(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding);

/* Stage an ordinary/unsupported-operation CALL once for native forward work. */
int kd_jit_stage_forward_call(const struct kd_jit_image *image,
		 struct kd_thread_state *state,
		 struct kd_execution_binding *binding,
		 const struct kd_source_stack_ops *stack);
/* No source access follows success until the original task receives control. */
int kd_jit_transfer_origin(struct kd_thread_state *state,
		 struct kd_execution_binding *binding,
		 struct kd_execution_binding *origin_binding);

/* Only original W may consume its exact fresh native endpoint. Success
 * abandons old control frames and resumes regs.ip with final SP == regs.sp.
 * All task active-scope/control cleanup must already precede this final call.
 */
int kd_jit_resume_origin(struct kd_thread_state *state,
		 struct kd_execution_binding *native_binding);

struct kd_jit_mutex_call;

struct kd_jit_mutex_driver {
	/*
	 * Execute fragments and serial recursive operations on this same S_W.
	 * Update *binding only to a retained, known exact current endpoint. On a
	 * continuing result the callback stops/exports and returns its current
	 * binding; this adapter transfers to call.returned before notification.
	 * ORIGIN_SUFFIX must already have transferred to the driver's retained
	 * origin_binding, closing old source rights. No old packet is restored.
	 * The callback cannot finish/reenter combining of call.node.batch.
	 */
	enum kd_mutex_outcome (*run)(struct kd_jit_mutex_call *call,
				      struct kd_execution_binding **binding,
				      void *context);
	const struct kd_source_stack_ops *stack;
	/* Fresh native endpoint for this episode, retained through all users.
	 * Do not reuse the original native binding across an outstanding offer.
	 */
	struct kd_execution_binding *origin_binding;
	void *context;
};

/*
 * One persistent referring call/control, not another W packet. Storage is
 * reserved before effects and retained through node retirement AND all binding
 * observers. Direct task anchors are selected. Allocation, depth bounds and
 * native wait/control stack reservation remain open, without hidden defaults.
 */
struct kd_jit_mutex_call {
	struct kd_mutex_node node;
	struct kd_mutex_batch possible_batch;
	struct kd_source_grant grant;
	struct kd_execution_binding offer;
	struct kd_execution_binding execution;
	struct kd_execution_binding returned;
	struct kd_task_borrow_scope borrow_scope;
	const struct kd_jit_mutex_driver *driver;
	char acquisition_identity;
	char unlock_identity;
	char result_identity;
};

/*
 * Init is private and precedes prepare_operation with acquisition_identity.
 * ready=false permits local arbitration without proxy eligibility, while still
 * accepting this JIT bridge's stopped offer at the actual local MCS win.
 */
int kd_jit_mutex_call_init(struct kd_jit_mutex_call *call,
		 struct kd_thread_state *state,
		 const struct kd_jit_mutex_driver *driver, bool ready);
/* Root compiler-clobber entry, called only after W's wait control is on an
 * admitted disjoint stack. Captures its declared SP/IP/BP inputs, not guessed
 * source GPRs. capture_binding is a fresh retained endpoint distinct from all
 * this call's published endpoints and remains live through its last observer.
 */
int kd_jit_capture_mutex_lock(struct kd_jit_mutex_call *call,
		 struct kd_execution_binding *native_binding,
		 struct kd_execution_binding *capture_binding, struct kd_mutex *lock,
		 unsigned long source_sp, unsigned long continuation_ip,
		 unsigned long source_bp, unsigned long api_target);
int kd_jit_mutex_acquire(struct kd_jit_mutex_call *call,
		 struct kd_mutex *lock, struct kd_execution_binding **binding,
		 unsigned int proxy_limit, enum kd_mutex_outcome *outcome);

/* Local winners close this role only after their episode is stopped/exported;
 * the proxy adapter closes its own role before publishing its result.
 */
int kd_jit_mutex_leave(struct kd_jit_mutex_call *call);

/*
 * Find the exact logical grant for regs.di before preparing its unlock using
 * that call's unlock_identity. The active batch identifies actual execution
 * context; task equality does not identify a nested responsible outer owner.
 */
int kd_jit_mutex_unlock(struct kd_jit_mutex_call *call,
		 struct kd_execution_binding *binding,
		 struct kd_mutex_batch *active_batch, const void *notifier,
		 enum kd_mutex_unlock_action *action);

/*
 * Current canonical-state owner collects only logically closed, physically
 * completed grants. Result/binding observers are a separate referring user.
 * Before result_done, move the current binding off this call and finish every
 * observer of offer/execution/returned. A successful drop may permit reaping;
 * do not access that call after the last user is dropped.
 */
int kd_jit_collect_grants(struct kd_thread_state *state,
		 struct kd_execution_binding *binding);
int kd_jit_mutex_result_done(struct kd_jit_mutex_call *call);

#endif
