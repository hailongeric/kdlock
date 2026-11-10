/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_FEEDBACK_PUBLISH_H
#define KDLOCK_FEEDBACK_PUBLISH_H

#include "feedback.h"
#include "image_owner.h"

/* Emitted with the descriptor from its actual compiler EmissionReceipt. These
 * are construction outcomes, not runtime execution or publication evidence.
 */
enum kd_jit_feedback_transfer_kind {
	KD_JIT_FEEDBACK_TRANSFER_CALL,
	KD_JIT_FEEDBACK_TRANSFER_JUMP,
};

enum kd_jit_feedback_emission_outcome {
	KD_JIT_FEEDBACK_EMISSION_EMITTED,
	KD_JIT_FEEDBACK_EMISSION_SOURCE_NOT_EMITTED,
	KD_JIT_FEEDBACK_EMISSION_TARGET_NOT_EMITTED,
	KD_JIT_FEEDBACK_EMISSION_DISPATCH_NOT_EMITTED,
};

struct kd_jit_feedback_emission {
	unsigned long source_ip;
	unsigned long target;
	enum kd_jit_feedback_transfer_kind kind;
	enum kd_jit_feedback_emission_outcome outcome;
};

struct kd_jit_feedback_emission_receipt {
	const struct kd_jit_image_inputs *inputs;
	const struct kd_jit_feedback_emission *observations;
	unsigned int observation_count;
};

enum kd_jit_feedback_publication_phase {
	KD_JIT_FEEDBACK_PUBLICATION_PRIVATE,
	KD_JIT_FEEDBACK_PUBLICATION_PREPARED,
	KD_JIT_FEEDBACK_PUBLICATION_COMMITTED,
	KD_JIT_FEEDBACK_PUBLICATION_ACKNOWLEDGED,
	KD_JIT_FEEDBACK_PUBLICATION_ABORTED,
};

/* Identities below name the ACTUAL verified update, not a boolean supplied by a
 * compiler. Numeric image identities are compared/mapped only, never dereferenced
 * after code retirement. A NULL old image is represented by zero. Transport must
 * preserve the exact held-object mapping rather than inventing identity strings.
 */
struct kd_jit_feedback_commit_receipt {
	const void *identity;
	struct kd_jit_feedback_claim *claim;
	const void *claim_holder;
	const struct kd_jit_feedback_claim_item *included;
	unsigned int included_count;
	struct kd_jit_image_slot *slot;
	struct kd_jit_image_update *update;
	const void *update_identity;
	unsigned long expected_old_image_identity;
	unsigned long candidate_image_identity;
	unsigned long returned_old_image_identity;
	struct kd_jit_source_epoch *epoch;
	const struct kd_jit_feedback_emission_receipt *emission;
};

struct kd_jit_feedback_ack_receipt {
	const void *identity;
	const struct kd_jit_feedback_commit_receipt *publication;
	struct kd_jit_feedback_claim *claim;
	const void *claim_holder;
	const struct kd_jit_feedback_claim_item *items;
	unsigned int count;
};

/* Caller-preallocated, serialized publication/ACK control, not a new publisher,
 * fact pool or source packet. Initialize fresh private storage and never reuse
 * its address/holder/receipts while any old API or transport observer lives.
 * All referenced controls, immutable arrays, code/source holds and callback code
 * survive their actual final observers. Mutable ticket/ACK scratch are disjoint
 * from all referenced controls and immutable input/claim/receipt backing.
 */
struct kd_jit_feedback_publication {
	enum kd_jit_feedback_publication_phase phase;
	const void *holder;
	struct kd_jit_feedback_claim *claim;
	const void *claim_holder;
	const struct kd_jit_feedback_claim_item *included;
	unsigned int included_count;
	struct kd_jit_feedback_claim_item *ack_items;
	unsigned int ack_count;
	struct kd_jit_image_owner_use *candidate_use;
	const void *candidate_holder;
	struct kd_jit_image_owner *candidate_owner;
	const struct kd_jit_image *candidate;
	const struct kd_jit_image_inputs *inputs;
	struct kd_jit_source_epoch *epoch;
	const struct kd_jit_feedback_emission_receipt *emission;
	struct kd_jit_image_update *update;
	struct kd_jit_image_slot *slot;
	const void *update_identity;
	const struct kd_jit_image *expected_old;
	struct kd_jit_feedback_commit_receipt committed;
	struct kd_jit_feedback_ack_receipt acknowledged;
};

void kd_jit_feedback_publication_init(struct kd_jit_feedback_publication *publication);
/*
 * Claim/source snapshot and included-item selection precede update_begin while
 * the existing image remains available. Build/load/validate the entire candidate
 * and this coordinated generated receipt before entering CLOSING. This function
 * binds that actual CLOSING transaction; it never closes admission itself.
 * Caller proves this generated receipt and its arrays belong to that actual
 * candidate construction and code lease; equal inputs pointers alone do not
 * establish that relationship. Producer exit-template and indirect-flow matching
 * use the retained producer mapping in the host adapter, not a late old-code read.
 *
 * included is the exact frozen host-adapter-validated MERGED input selection
 * from this claim, never the whole copied claim by default. Old producer
 * exit-template, indirect-flow and source-binding validation belong to that
 * actual retained host mapping. Raw scalar and receipt tuple checks here do not
 * independently prove it. Nonobservations, late and invalid producer facts stay
 * claimed but excluded, even if another valid fact has the same source/target.
 * Every claimed fact remains immutable through claim_end; later facts are not selected.
 * Only ordinary coverage CALL/JMP facts appearing as EMITTED in this candidate's
 * exact receipt enter ACK scratch. Missing/non-emitted/nonobservation facts remain
 * pending; receipt presence alone is not runtime coverage or an ACK.
 *
 * ack_capacity >= included_count, with caller-provisioned writable scratch.
 * Only this component writes scratch; it stays immutable after prepare. No
 * allocator, capacity default, saturation/reset or transport policy is chosen.
 * candidate_use is an exact live EXTERNAL/BASELINE owner user protecting image,
 * inputs and receipt code backing. claim, both holders and candidate_use remain
 * live/unchanged through commit/ACK/abort; this component never puts/ends them.
 * Serialize these APIs with claim_end, owner-use put, update APIs, slot-owner
 * binding/retirement, all later slot updates and transaction/record reuse.
 * Expected-old identity was retained through actual update_begin independently.
 */
int kd_jit_feedback_publication_prepare(struct kd_jit_feedback_publication *publication,
		const void *holder, struct kd_jit_feedback_claim *claim,
		const void *claim_holder, const struct kd_jit_feedback_claim_item *included,
		unsigned int included_count, struct kd_jit_feedback_claim_item *ack_items,
		unsigned int ack_capacity, struct kd_jit_image_owner_use *candidate_use,
		const void *candidate_holder, const struct kd_jit_feedback_emission_receipt *emission,
		struct kd_jit_image_update *update, const void *update_identity);
/* Call only after actual try_commit returned success and its retired value.
 * Validate exact stored slot/update/owner/old/new and current candidate after RCU
 * grace. NULL retired is valid only for an initially empty baseline. On success
 * committed is an immutable actual publication receipt; this performs NO ACK.
 * Do not synthesize retired from expected_old, phase or an integer generation.
 */
int kd_jit_feedback_publication_commit(struct kd_jit_feedback_publication *publication,
		const void *holder, const struct kd_jit_image *retired);
/* After real commit only: atomically ACK the precomputed exact included emitted
 * subset through the feedback pool API. No source effects or code publication.
 * Later/uncovered facts stay pending; claim_end remains the caller's later duty.
 * Successful acknowledged identifies that actual ACK and exact returned subset,
 * not all input facts or graph-attached observations. Failure keeps COMMITTED
 * and the exact claim/ticket live for resolution, with no code rollback.
 */
int kd_jit_feedback_publication_ack(struct kd_jit_feedback_publication *publication,
		const void *holder);
/* Actual exact ABORTED transaction only, never GRACE/COMMITTED rollback. No ACK.
 * End/unclaim the retained claim separately; unacknowledged facts stay pending.
 */
int kd_jit_feedback_publication_abort(struct kd_jit_feedback_publication *publication,
		const void *holder);

#endif
