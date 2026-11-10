/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_IMAGE_OWNER_H
#define KDLOCK_IMAGE_OWNER_H

#include "image_inputs.h"
#include "source_epoch.h"

struct kd_jit_image_owner;

typedef void (*kd_jit_image_code_release_fn)(void *code_lease);

enum kd_jit_image_owner_use_kind {
	KD_JIT_IMAGE_OWNER_USE_UNUSED,
	KD_JIT_IMAGE_OWNER_USE_EXTERNAL,
	KD_JIT_IMAGE_OWNER_USE_BASELINE,
	KD_JIT_IMAGE_OWNER_USE_PUBLISHED_SLOT,
};

enum kd_jit_image_owner_phase {
	KD_JIT_IMAGE_OWNER_OPEN,
	KD_JIT_IMAGE_OWNER_CLOSED,
	/* Claimed once, not proof that code release and source put have returned. */
	KD_JIT_IMAGE_OWNER_RELEASE_CLAIMED,
};

/* Exact caller-preallocated user; fields are read-only while linked. holder and
 * this record identify one reservation and cannot be reused while old observers
 * exist. Each caller serializes its record's operations and retains its backing
 * through final API return. A published-slot user has a separate exact retiring
 * transaction, never an aggregate published-image count or a saved phase alone.
 */
struct kd_jit_image_owner_use {
	struct list_head owner_link;
	struct kd_jit_image_owner *owner;
	const void *holder;
	enum kd_jit_image_owner_use_kind kind;
	struct kd_jit_image_slot *slot;
	struct kd_jit_image_update *retire_update;
	const void *retire_identity;
	bool linked;
};

/*
 * Lifetime envelope, not executable allocation or publication. image/inputs and
 * their complete immutable backing belong to the transferred code-provider
 * lease. The embedded IMAGE membership independently retains the actual source
 * epoch; do not manipulate that private membership outside this component.
 * guard protects these records only, never source work or provider callbacks.
 * No owner/slot/source guards are nested by this component.
 */
struct kd_jit_image_owner {
	raw_spinlock_t guard;
	struct list_head users;
	const struct kd_jit_image *image;
	const struct kd_jit_image_inputs *inputs;
	struct kd_jit_source_use source_use;
	void *code_lease;
	kd_jit_image_code_release_fn code_release;
	enum kd_jit_image_owner_phase phase;
	bool ever_published;
};

/*
 * Private, once per unreused owner. Caller retains a live exact BUILD membership
 * through return and already owns the supplied complete code-provider hold.
 * Validate image/inputs/source identity, ABI, exact version/GS input, decoded
 * site bytes and actual-address maps against that retained epoch snapshot.
 * configuration_identity/load_identity must name the caller's actual build
 * configuration and source load incarnation, not newly invented version tokens.
 * Numeric/coherence checks establish neither live-kernel snapshot validity nor
 * generated-code equivalence, executable permission/publication or coverage ACK.
 *
 * All input backing is valid, immutable and retained during these reads. On
 * success, one same-epoch IMAGE use is derived from BUILD and the code hold is
 * transferred. Failure leaves no IMAGE use and keeps code-release ownership with
 * the caller. Existing BUILD extension while the epoch is closed is retention
 * only; it grants no new source execution/publication admission.
 */
int kd_jit_image_owner_init(struct kd_jit_image_owner *owner,
		const struct kd_jit_image *image, const struct kd_jit_image_inputs *inputs,
		struct kd_jit_source_use *build, const void *build_holder,
		const void *configuration_identity, const void *load_identity,
		void *code_lease, kd_jit_image_code_release_fn code_release);
void kd_jit_image_owner_use_init(struct kd_jit_image_owner_use *use);

/* New direct EXTERNAL/BASELINE users require OPEN. Keep a BASELINE from exact
 * expected_old observation through successful update_begin. Owner memberships
 * do not enter an image slot's execution-users list or substitute its drain.
 * Finish all code/descriptor/input access before dropping the last such user.
 */
int kd_jit_image_owner_use_get(struct kd_jit_image_owner *owner,
		struct kd_jit_image_owner_use *use, const void *holder,
		enum kd_jit_image_owner_use_kind kind);
/* put never calls a provider; PUBLISHED_SLOT requires exact retirement instead. */
int kd_jit_image_owner_use_put(struct kd_jit_image_owner_use *use, const void *holder);

/*
 * Bind the actual published slot from a live EXTERNAL/BASELINE parent before
 * dropping that parent. The parent bridges initial publication/update completion
 * to this call; no unretained interval is allowed. The slot must actually point
 * at this image, with no pending update. A live admitted parent may finish this
 * retention binding while the owner is CLOSED; close cannot strand an already
 * published candidate. This is lifetime extension, not publication admission.
 * One exact owner membership per slot is allowed, including distinct slots.
 *
 * Caller serializes slot publication, this binding, retiring APIs and later
 * updates. In particular, no subsequent update starts before binding finishes.
 * Retain slot, owner, parent/use and publisher identities through all observers.
 * Initial slot publication and update publication both require this bridge.
 */
int kd_jit_image_owner_slot_get(struct kd_jit_image_owner_use *parent,
		const void *parent_holder, struct kd_jit_image_owner_use *published,
		const void *published_holder, struct kd_jit_image_slot *slot);

/*
 * After successful update_begin, bind this PUBLISHED_SLOT user to that exact
 * CLOSING transaction/owner/slot/expected_old before commit or abort. Caller
 * serializes these APIs with image_update APIs and retains update storage plus
 * owner identity through completion and every stale observer; do not reuse them.
 * NULL candidate is allowed when the actual update retires the last image to an
 * empty slot. No owner membership is created for that empty candidate.
 */
int kd_jit_image_owner_retire_prepare(struct kd_jit_image_owner_use *published,
		const void *published_holder, struct kd_jit_image_update *update,
		const void *update_identity);
/* Exact completed ABORTED transaction only: keep the published membership and
 * clear its retiring binding before any later slot update starts.
 */
int kd_jit_image_owner_retire_abort(struct kd_jit_image_owner_use *published,
		const void *published_holder, struct kd_jit_image_update *update,
		const void *update_identity);
/*
 * Call only after that exact successful try_commit returned its ACTUAL retired
 * pointer, after the old lookup grace. Pass that retained return value unchanged,
 * never synthesize it from expected_old or phase. Check exact prepared transaction
 * + owner + slot + expected_old + returned pointer, then unlink once. Completion
 * alone does not release code while another published slot/external user lives.
 * Finish this call before later slot updates or transaction reuse. No callbacks
 * run here; success ends all published-record/descriptor access by this caller.
 */
int kd_jit_image_owner_retire_finish(struct kd_jit_image_owner_use *published,
		const void *published_holder, struct kd_jit_image_update *update,
		const void *update_identity, const struct kd_jit_image *retired);

/* Private candidate cancellation never stands in for published retirement.
 * It refuses any owner that has ever bound a published slot. Close alone denies
 * new direct users; it neither closes image/root admission nor removes slots.
 * Existing users still retain storage and must finish before try_release.
 */
int kd_jit_image_owner_cancel_unpublished(struct kd_jit_image_owner *owner);
int kd_jit_image_owner_close(struct kd_jit_image_owner *owner);
/*
 * Serialized sleepable finalizer, outside source/RCU read sections and guards.
 * CLOSED+no users claims release once under guard; invoke cached code_release
 * outside guard, then drop the exact epoch IMAGE membership. No code/descriptor/
 * inputs access follows code_release. No owner access follows source put.
 * Code callback is complete, synchronous and nonfailing; it cannot mutate these
 * controls or release their active backing. Header/containing allocation,
 * embedded source-use backing and callback code/execution backing are separately
 * retained through finalizer return, even after code payload is gone.
 *
 * A source-put error violates the private IMAGE-use contract: code was already
 * released, source remains retained and that error is returned. Never replay the
 * code callback, infer complete retirement or free active control on that path.
 * RELEASE_CLAIMED/-EALREADY does not prove either final operation returned.
 * Source mutation/unload and arbitrary native suffix/return holds remain the
 * provider's independent duties under source_epoch.h; no allocator/module_get,
 * text freeze, feedback capacity, transport or runtime ACK is selected here.
 */
int kd_jit_image_owner_try_release(struct kd_jit_image_owner *owner);

#endif
