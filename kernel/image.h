/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_IMAGE_H
#define KDLOCK_IMAGE_H

#include <linux/list.h>
#include <linux/rcupdate.h>
#include <linux/spinlock.h>

struct kd_jit_image;
struct kd_thread_state;
struct kd_jit_image_slot;
struct kd_jit_image_update;

/* An exact referring user, not an aggregate activity estimate. */
enum kd_jit_image_use_kind {
	KD_JIT_IMAGE_USE_UNUSED,
	KD_JIT_IMAGE_USE_EXECUTION,
	KD_JIT_IMAGE_USE_RETURN,
	KD_JIT_IMAGE_USE_SOURCE,
};

/*
 * Preallocated caller storage. While linked, this exact record retains image,
 * its coherent code/metadata and the image's caller-established source holds.
 * state and holder identify the admitted episode/control; this component does
 * not grant source-execution or return-binding authority. A pending
 * state.exit_image or generated return dependency needs its own still-live use;
 * storing that image pointer alone is no retention. Fields are read-only
 * to callers until put completes. Keep this record, holder, state and slot
 * valid through every API/observer; never reuse it while an old observer lives.
 * Creation uses private initialized storage and is serialized by its caller.
 */
struct kd_jit_image_use {
	struct list_head slot_link;
	struct kd_jit_image_slot *slot;
	const struct kd_jit_image *image;
	struct kd_thread_state *state;
	const void *holder;
	/* Exact pending-exit consumer; protected solely by the slot guard. */
	const void *consumer;
	enum kd_jit_image_use_kind kind;
	bool linked;
};

enum kd_jit_image_update_phase {
	KD_JIT_IMAGE_UPDATE_PRIVATE,
	KD_JIT_IMAGE_UPDATE_CLOSING,
	KD_JIT_IMAGE_UPDATE_GRACE,
	KD_JIT_IMAGE_UPDATE_COMMITTED,
	KD_JIT_IMAGE_UPDATE_ABORTED,
};

/*
 * Persistent caller transaction. Initialize fresh private storage; retain its
 * address and fresh owner identity through all commit/abort/API observers.
 * Do not rewrite inputs, reinitialize it or reuse owner_identity while a stale
 * observer can still call an API. Exact transaction+owner checks prevent an
 * old operation from closing or aborting a later update.
 */
struct kd_jit_image_update {
	struct kd_jit_image_slot *slot;
	const struct kd_jit_image *expected_old;
	const struct kd_jit_image *candidate;
	const void *owner_identity;
	enum kd_jit_image_update_phase phase;
};

/*
 * One entry slot, initialized before publication and retained through all
 * lookup, use, update and grace-period users. Its raw guard protects metadata
 * only. No source execution, allocation, compilation or sleeping runs under it.
 * The exact users list, not a counter or RCU alone, retains sleeping/suspended
 * episodes and source/return dependencies. No capacity/default is selected.
 */
struct kd_jit_image_slot {
	raw_spinlock_t guard;
	const struct kd_jit_image __rcu *image;
	struct list_head users;
	struct kd_jit_image_update *update;
	bool closing;
};

/* Initial/candidate descriptors and their complete code/source/ABI/input maps
 * must be coherent, immutable and validated by the caller before publication.
 * An empty initial slot is allowed. No allocator or code upload is performed.
 */
void kd_jit_image_slot_init(struct kd_jit_image_slot *slot,
			    const struct kd_jit_image *initial);
void kd_jit_image_use_init(struct kd_jit_image_use *use);
void kd_jit_image_update_init(struct kd_jit_image_update *update);

/*
 * New-root lookup is nonblocking: -EAGAIN for closing/raced replacement,
 * -ENOENT for an empty slot. Within an RCU read section, the guard revalidates
 * the exact current pointer and registers use before leaving RCU. The caller
 * can then sleep/suspend while this exact record remains linked. Reading the
 * returned use->image confers no admission contract beyond that retention.
 */
int kd_jit_image_lookup(struct kd_jit_image_slot *slot,
			struct kd_jit_image_use *use,
			struct kd_thread_state *state, const void *holder,
			enum kd_jit_image_use_kind kind);

/*
 * Extend a LIVE already-admitted use to a child/return/source user of the SAME
 * state and image, including while closing. Reserve the child before dropping
 * the last parent; a dead parent cannot admit a new root during drain. The
 * caller proves current-state input/return compatibility and that this is an
 * admitted descendant, not a new root disguised as an extension.
 */
int kd_jit_image_use_extend(struct kd_jit_image_use *parent,
			    const void *parent_holder,
			    struct kd_jit_image_use *child,
			    const void *child_holder,
			    enum kd_jit_image_use_kind kind);
/*
 * Atomic EXECUTION-membership/state/holder validation and distinct SOURCE child
 * reservation before a JIT invocation. The child is claimed to state; ordinary
 * put cannot unlink it. No mutable state field is read under the image guard.
 * Caller owns current source execution and private initialized exit_use storage.
 */
int kd_jit_image_use_prepare_exit(struct kd_jit_image_use *execution,
				   const void *execution_holder,
				   struct kd_thread_state *state,
				   struct kd_jit_image_use *exit_use,
				   const void *exit_holder,
				   const struct kd_jit_image **image);
int kd_jit_image_use_check_exit(struct kd_jit_image_use *exit_use,
				 const void *exit_holder,
				 struct kd_thread_state *state,
				 const struct kd_jit_image **image);
/* Only the current source bridge finishes this exact claim, after its final
 * image access and after clearing the canonical pending pointers. Failure
 * leaves the claim/use intact so that bridge can preserve its control state.
 */
int kd_jit_image_use_finish_exit(struct kd_jit_image_use *exit_use,
				  const void *exit_holder,
				  struct kd_thread_state *state);

/* Close the user's final code, return, source and metadata access before put.
 * Exact unlink may immediately enable reclamation; this call then accesses
 * neither the image nor the use record. A raw saved return/pointer is no hold.
 * A claimed pending-exit use returns -EBUSY; finish_exit owns that exact drop.
 */
int kd_jit_image_use_put(struct kd_jit_image_use *use, const void *holder);

/*
 * Begin closes new-root lookup only after checking the actual current base.
 * Retain expected_old's descriptor/identity from baseline observation until
 * successful begin; a raw observed address cannot prevent descriptor-reuse ABA.
 * NULL names the empty baseline. A live SOURCE use can retain a build baseline.
 * Once begin closes the exact slot, that slot/transaction retain the old base;
 * drop any publisher SOURCE use before commit so it does not block its own drain.
 * A failed begin does not consume the caller's baseline hold.
 * A non-NULL candidate is a different immutable descriptor validated before
 * begin and retained through the transaction and its published users. NULL
 * retires an existing image to an empty slot through the same drain and grace
 * sequence; an already-empty NULL -> NULL update is refused.
 */
int kd_jit_image_update_begin(struct kd_jit_image_slot *slot,
			      struct kd_jit_image_update *update,
			      const struct kd_jit_image *expected_old,
			      const struct kd_jit_image *candidate,
			      const void *owner_identity);
/*
 * Sleepable publisher context only, outside protected source execution, any
 * RCU read-side section and this slot guard.
 * -EBUSY leaves the exact transaction closing while its users list is nonempty.
 * Successful commit assigns the RCU pointer only with no exact users, waits for
 * old lookup readers outside the guard, then reopens and returns retired once.
 * Caller frees retired only after this success and all separate shared-source,
 * other-slot or external users it owns have also ended. This component performs
 * no freeing or feedback ACK and establishes no execution/performance evidence.
 */
int kd_jit_image_update_try_commit(struct kd_jit_image_update *update,
				   const void *owner_identity,
				   const struct kd_jit_image **retired);
/* Abort only this exact pre-publication transaction; GRACE cannot roll back. */
int kd_jit_image_update_abort(struct kd_jit_image_update *update,
			      const void *owner_identity);

#endif
