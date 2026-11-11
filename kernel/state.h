/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_STATE_H
#define KDLOCK_STATE_H

#include <linux/list.h>
#include "../include/kd_regs.h"
#include "mutex_release.h"

struct task_struct;
struct kd_thread_state;
struct kd_jit_image;
struct kd_jit_image_use;
struct kd_request_pool;
struct kd_rw_read_credit;

/* These small records live in existing request/role storage, never a packet. */
enum kd_execution_kind {
	KD_EXECUTION_NATIVE,
	KD_EXECUTION_JIT,
	KD_EXECUTION_OFFER,
};

struct kd_execution_binding {
	struct kd_thread_state *state;
	struct task_struct *task;
	const void *control;
	enum kd_execution_kind kind;
};

/* Existing operation IDs 0..5 remain stable. Source IO carries direction,
 * while exact registered targets select these family/API kinds in lock code.
 */
enum kd_operation_kind {
	KD_OPERATION_NONE = 0,
	KD_OPERATION_MUTEX_LOCK = 1,
	KD_OPERATION_MUTEX_UNLOCK = 2,
	KD_OPERATION_MODE_CHANGE = 3,
	KD_OPERATION_SPIN_LOCK = 4,
	KD_OPERATION_SPIN_UNLOCK = 5,
	KD_OPERATION_RWSEM_DOWN_READ,
	KD_OPERATION_RWSEM_UP_READ,
	KD_OPERATION_RWSEM_DOWN_WRITE,
	KD_OPERATION_RWSEM_UP_WRITE,
	KD_OPERATION_RWSEM_DOWNGRADE_WRITE,
	KD_OPERATION_RWLOCK_READ_LOCK,
	KD_OPERATION_RWLOCK_READ_UNLOCK,
	KD_OPERATION_RWLOCK_WRITE_LOCK,
	KD_OPERATION_RWLOCK_WRITE_UNLOCK,
};

enum kd_lock_family {
	KD_LOCK_FAMILY_MUTEX,
	KD_LOCK_FAMILY_SPIN,
	KD_LOCK_FAMILY_RWSEM,
	KD_LOCK_FAMILY_RWLOCK,
	KD_LOCK_FAMILY_COUNT,
};

/* RETAINED_READ is a logical read tail of the same delegated writer
 * acquisition. Its physical writer duty remains distinct from a READ credit.
 */
enum kd_grant_mode {
	KD_GRANT_MODE_WRITE,
	KD_GRANT_MODE_READ,
	KD_GRANT_MODE_RETAINED_READ,
};

enum kd_grant_physical {
	KD_GRANT_PHYSICAL_WRITE,
	KD_GRANT_PHYSICAL_READ,
};

static inline bool kd_operation_is_lock(enum kd_operation_kind kind)
{
	return kind == KD_OPERATION_MUTEX_LOCK || kind == KD_OPERATION_SPIN_LOCK ||
	       kind == KD_OPERATION_RWSEM_DOWN_READ || kind == KD_OPERATION_RWSEM_DOWN_WRITE ||
	       kind == KD_OPERATION_RWLOCK_READ_LOCK || kind == KD_OPERATION_RWLOCK_WRITE_LOCK;
}

static inline bool kd_operation_is_unlock(enum kd_operation_kind kind)
{
	return kind == KD_OPERATION_MUTEX_UNLOCK || kind == KD_OPERATION_SPIN_UNLOCK ||
	       kind == KD_OPERATION_RWSEM_UP_READ || kind == KD_OPERATION_RWSEM_UP_WRITE ||
	       kind == KD_OPERATION_RWLOCK_READ_UNLOCK || kind == KD_OPERATION_RWLOCK_WRITE_UNLOCK;
}

static inline bool kd_operation_is_mode_change(enum kd_operation_kind kind)
{
	return kind == KD_OPERATION_RWSEM_DOWNGRADE_WRITE;
}

static inline bool kd_operation_is_spin(enum kd_operation_kind kind)
{
	return kind == KD_OPERATION_SPIN_LOCK || kind == KD_OPERATION_SPIN_UNLOCK;
}

static inline enum kd_lock_family kd_operation_family(enum kd_operation_kind kind)
{
	switch (kind) {
	case KD_OPERATION_MUTEX_LOCK:
	case KD_OPERATION_MUTEX_UNLOCK:
		return KD_LOCK_FAMILY_MUTEX;
	case KD_OPERATION_SPIN_LOCK:
	case KD_OPERATION_SPIN_UNLOCK:
		return KD_LOCK_FAMILY_SPIN;
	case KD_OPERATION_RWSEM_DOWN_READ:
	case KD_OPERATION_RWSEM_UP_READ:
	case KD_OPERATION_RWSEM_DOWN_WRITE:
	case KD_OPERATION_RWSEM_UP_WRITE:
	case KD_OPERATION_RWSEM_DOWNGRADE_WRITE:
		return KD_LOCK_FAMILY_RWSEM;
	case KD_OPERATION_RWLOCK_READ_LOCK:
	case KD_OPERATION_RWLOCK_READ_UNLOCK:
	case KD_OPERATION_RWLOCK_WRITE_LOCK:
	case KD_OPERATION_RWLOCK_WRITE_UNLOCK:
		return KD_LOCK_FAMILY_RWLOCK;
	default:
		return KD_LOCK_FAMILY_COUNT;
	}
}

static inline bool kd_lock_family_is_atomic(enum kd_lock_family family)
{
	return family == KD_LOCK_FAMILY_SPIN || family == KD_LOCK_FAMILY_RWLOCK;
}

static inline bool kd_operation_is_atomic(enum kd_operation_kind kind)
{
	return kd_lock_family_is_atomic(kd_operation_family(kind));
}

static inline bool kd_operation_is_read(enum kd_operation_kind kind)
{
	return kind == KD_OPERATION_RWSEM_DOWN_READ || kind == KD_OPERATION_RWSEM_UP_READ ||
	       kind == KD_OPERATION_RWLOCK_READ_LOCK || kind == KD_OPERATION_RWLOCK_READ_UNLOCK;
}

enum kd_operation_form {
	KD_OPERATION_NEW_CALL,
	KD_OPERATION_EXISTING_CALL,
	KD_OPERATION_EXISTING_FRAME,
	/* Compiler-clobber root already captured the post-call continuation. */
	KD_OPERATION_CAPTURED_CONTINUATION,
};

enum kd_operation_phase {
	KD_OPERATION_IDLE,
	KD_OPERATION_TARGET_READY,
	KD_OPERATION_API_READY,
	KD_OPERATION_ENTERED,
	KD_OPERATION_DONE,
	KD_OPERATION_RESUMABLE,
};

/* Pending operation metadata, not another source register/cursor snapshot. */
struct kd_source_operation {
	const void *identity;
	enum kd_operation_kind kind;
	enum kd_operation_form form;
	enum kd_operation_phase phase;
	unsigned long source_site;
	unsigned long target;
	unsigned long return_ip;
};

/*
 * A per-acquisition referring user. The MCS call/control may embed this record.
 * Drop is called only after unlink and must release exactly user, without any
 * later access to this record on success. It may then become reusable.
 */
struct kd_source_grant {
	struct list_head state_link;
	struct kd_thread_state *state;
	void *object;
	const void *acquisition;
	struct kd_mutex_release *release;
	struct kd_rw_read_credit *read_credit;
	enum kd_lock_family family;
	enum kd_grant_mode mode;
	enum kd_grant_physical physical;
	const void *user;
	int (*drop)(void *control, const void *user);
	void *control;
	bool linked;
	bool logical_open;
};

/*
 * Exactly one canonical packet and current operation for original W. Every
 * request/role points directly here through its MCS node, including nested
 * requests. A task-owned root/auxiliary header supplies initial own backing;
 * request storage is provisioned with W and reused after exact final users. The
 * caller retains this core and origin task/stack through all queue, grant, return, notification and code users.
 */
struct kd_thread_state {
	struct kd_regs regs;
	struct kd_jit_io io;
	/* Exact producer and claimed referring use, never another cursor/packet.
	 * These three fields are installed/cleared together by current source.
	 */
	const struct kd_jit_image *exit_image;
	struct kd_jit_image_use *exit_use;
	const void *exit_holder;
	struct kd_source_operation operation;
	struct kd_execution_binding *binding;
	/* Immutable task-provisioned storage; nested executors use W's pool. */
	struct kd_request_pool *requests;
	struct task_struct *origin;
	unsigned long origin_gs;
	struct list_head grants;
};

/*
 * Initialize private records only. A binding becomes immutable before publish.
 * Offer, execution and return bindings need distinct addresses for each live
 * ownership episode; do not reuse an old endpoint while an observer retains it.
 * This prevents pointer ABA across A -> B -> A without a per-hop counter.
 */
int kd_execution_binding_init(struct kd_execution_binding *binding,
			      struct kd_thread_state *state,
			      struct task_struct *task, const void *control,
			      enum kd_execution_kind kind);
int kd_state_init(struct kd_thread_state *state, struct task_struct *origin,
		  unsigned long origin_gs,
		  struct kd_execution_binding *native_binding);
bool kd_state_is_current(struct kd_thread_state *state,
			 struct kd_execution_binding *binding);
bool kd_state_is_jit_current(struct kd_thread_state *state,
			     struct kd_execution_binding *binding);
/* Acquire is not a storage reference: compare to a retained expected binding.
 * Do not dereference an arbitrary observed endpoint without its lifetime proof.
 */
struct kd_execution_binding *kd_state_current_binding(struct kd_thread_state *state);

/*
 * Materialize resident values and stop source before publish/transfer. These
 * primitives publish the same packet; they do not capture registers or choose
 * a queue winner. Only the selected MCS endpoint may accept its exact offer.
 * The receiver observes the exact new binding with acquire ordering before
 * source work. Old bindings confer no right to restore an earlier packet.
 */
int kd_state_publish(struct kd_thread_state *state,
		     struct kd_execution_binding *from,
		     struct kd_execution_binding *offer);
int kd_state_accept(struct kd_thread_state *state,
		    struct kd_execution_binding *offer,
		    struct kd_execution_binding *execution);
int kd_state_transfer(struct kd_thread_state *state,
		      struct kd_execution_binding *from,
		      struct kd_execution_binding *destination);

/*
 * Exact operation identity differs for acquisition and unlock, even when both
 * belong to one MCS node. A resolved indirect target is passed once; no helper
 * rereads the operand. Existing CALL/frame forms have no new source push.
 * CAPTURED_CONTINUATION keeps the compiler-clobber root's pre-CALL SP and
 * post-call IP; its completion neither pushes nor pops a source return word.
 */
int kd_operation_begin(struct kd_thread_state *state,
		       struct kd_execution_binding *binding,
		       const void *identity, enum kd_operation_kind kind,
		       enum kd_operation_form form, unsigned long source_site,
		       unsigned long target, unsigned long return_ip);

/*
 * These callbacks access the retained original kernel stack synchronously.
 * Each word operation must complete without failure, source reentry or control
 * mutation. They supply no fault/fixup proof for arbitrary addresses. Reserve
 * this valid-stack route before delegated effects; no replay is possible after
 * an unknown partial memory effect. No general flags/SIMD handling is added.
 */
struct kd_source_stack_ops {
	void (*write_word)(void *context, unsigned long address, unsigned long value);
	unsigned long (*read_word)(void *context, unsigned long address);
	void *context;
};
int kd_operation_stage_call(struct kd_thread_state *state,
			    struct kd_execution_binding *binding,
			    const void *identity,
			    const struct kd_source_stack_ops *stack);
int kd_operation_enter(struct kd_thread_state *state,
		       struct kd_execution_binding *binding,
		       const void *identity);
int kd_operation_complete(struct kd_thread_state *state,
			  struct kd_execution_binding *binding,
			  const void *identity);
int kd_operation_return(struct kd_thread_state *state,
			struct kd_execution_binding *binding,
			const void *identity,
			const struct kd_source_stack_ops *stack);

/* Grant-list membership is written only by the current source executor. */
void kd_source_grant_init(struct kd_source_grant *grant,
			  struct kd_thread_state *state, void *object,
			  const void *acquisition,
			  struct kd_mutex_release *release, const void *user,
			  int (*drop)(void *, const void *), void *control);
int kd_state_link_grant(struct kd_thread_state *state,
			struct kd_execution_binding *binding,
			struct kd_source_grant *grant);
struct kd_source_grant *kd_state_find_grant(struct kd_thread_state *state,
					   struct kd_execution_binding *binding,
					   void *object);
/* READ lookup walks newest-first. READ matches ordinary and retained read
 * modes; their distinct physical custody remains in the returned exact grant.
 */
struct kd_source_grant *kd_state_find_grant_typed(struct kd_thread_state *state,
		struct kd_execution_binding *binding, void *object,
		enum kd_lock_family family, enum kd_grant_mode mode);
struct kd_source_grant *kd_state_find_operation_grant(struct kd_thread_state *state,
		struct kd_execution_binding *binding, void *object,
		enum kd_operation_kind operation);
/* Called after exact physical validation/conversion, while the original writer
 * acquisition and every existing user remain retained. It never changes cursor.
 */
int kd_state_downgrade_grant(struct kd_thread_state *state,
		struct kd_execution_binding *binding, struct kd_source_grant *grant,
		struct kd_rw_read_credit *credit, bool retained);
int kd_state_close_grant(struct kd_thread_state *state,
			 struct kd_execution_binding *binding,
			 struct kd_source_grant *grant);
int kd_state_unlink_grant(struct kd_thread_state *state,
			  struct kd_execution_binding *binding,
			  struct kd_source_grant *grant);

#endif
