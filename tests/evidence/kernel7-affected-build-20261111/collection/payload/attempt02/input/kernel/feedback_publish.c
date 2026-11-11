// SPDX-License-Identifier: GPL-2.0-only
/* Exact committed-image receipts and separate acknowledgement of claimed facts. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/string.h>

#include "feedback_publish.h"

static bool array_valid(const void *array, unsigned int count, size_t size)
{
	unsigned long start = (unsigned long)array;
	size_t bytes;

	if (!count)
		return true;
	if (!array || (size_t)count > (size_t)-1 / size)
		return false;
	bytes = (size_t)count * size;
	return bytes - 1 <= ~0UL - start;
}

struct candidate_input {
	struct kd_jit_image_owner *owner;
	const struct kd_jit_image *image;
	const struct kd_jit_image_inputs *inputs;
	struct kd_jit_source_epoch *epoch;
};

static int candidate_get(struct kd_jit_image_owner_use *use, const void *holder,
		struct candidate_input *input)
{
	struct kd_jit_image_owner *owner;
	int result = 0;

	if (!use || !holder)
		return -EINVAL;
	owner = READ_ONCE(use->owner);
	if (!owner)
		return -ESTALE;
	raw_spin_lock(&owner->guard);
	if (use->owner != owner || !use->linked || use->holder != holder ||
	    (use->kind != KD_JIT_IMAGE_OWNER_USE_EXTERNAL &&
	     use->kind != KD_JIT_IMAGE_OWNER_USE_BASELINE) ||
	    (owner->phase != KD_JIT_IMAGE_OWNER_OPEN && owner->phase != KD_JIT_IMAGE_OWNER_CLOSED) ||
	    !owner->image || !owner->inputs || !owner->source_use.linked ||
	    owner->source_use.kind != KD_JIT_SOURCE_USE_IMAGE ||
	    owner->source_use.holder != owner || !owner->source_use.epoch) {
		result = -ESTALE;
	} else {
		input->owner = owner;
		input->image = owner->image;
		input->inputs = owner->inputs;
		input->epoch = owner->source_use.epoch;
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

static bool transfer_kind_valid(enum kd_jit_feedback_transfer_kind kind)
{
	return kind == KD_JIT_FEEDBACK_TRANSFER_CALL || kind == KD_JIT_FEEDBACK_TRANSFER_JUMP;
}

static bool outcome_valid(enum kd_jit_feedback_emission_outcome outcome)
{
	return outcome == KD_JIT_FEEDBACK_EMISSION_EMITTED ||
	       outcome == KD_JIT_FEEDBACK_EMISSION_SOURCE_NOT_EMITTED ||
	       outcome == KD_JIT_FEEDBACK_EMISSION_TARGET_NOT_EMITTED ||
	       outcome == KD_JIT_FEEDBACK_EMISSION_DISPATCH_NOT_EMITTED;
}

static bool emitted_sites_match(const struct kd_jit_image *image,
		const struct kd_jit_feedback_emission *emission)
{
	bool source = false, target = false;
	unsigned int index;

	for (index = 0; index < image->source_count; ++index) {
		const struct kd_jit_source_site *site = &image->source_sites[index];

		if (site->ip == emission->source_ip)
			source = site->kind == (emission->kind == KD_JIT_FEEDBACK_TRANSFER_CALL ?
					       KD_JIT_SITE_CALL : KD_JIT_SITE_JUMP);
		if (site->ip == emission->target)
			target = true;
	}
	return source && target;
}

static bool emission_valid(const struct kd_jit_feedback_emission_receipt *receipt,
		const struct candidate_input *candidate)
{
	unsigned int index, other;

	if (!receipt || receipt->inputs != candidate->inputs ||
	    candidate->inputs->image != candidate->image ||
	    candidate->image->source_identity != candidate->epoch ||
	    !array_valid(receipt->observations, receipt->observation_count,
			 sizeof(*receipt->observations)))
		return false;
	for (index = 0; index < receipt->observation_count; ++index) {
		const struct kd_jit_feedback_emission *item = &receipt->observations[index];

		if (!transfer_kind_valid(item->kind) || !outcome_valid(item->outcome) ||
		    (item->outcome == KD_JIT_FEEDBACK_EMISSION_EMITTED &&
		     !emitted_sites_match(candidate->image, item)))
			return false;
		for (other = 0; other < index; ++other) {
			const struct kd_jit_feedback_emission *previous = &receipt->observations[other];

			if (item->source_ip == previous->source_ip && item->target == previous->target &&
			    item->kind == previous->kind)
				return false;
		}
	}
	return true;
}

static bool fact_kind(const struct kd_jit_feedback_fact *fact,
		enum kd_jit_feedback_transfer_kind *kind)
{
	if (fact->entry_result || fact->kind != KD_JIT_EXIT_COVERAGE_MISS ||
	    fact->classification != KD_JIT_FEEDBACK_ORDINARY)
		return false;
	if (fact->phase == KD_JIT_PHASE_TARGET_READY) {
		if (fact->cursor != fact->source_ip)
			return false;
		*kind = KD_JIT_FEEDBACK_TRANSFER_CALL;
		return true;
	}
	if (fact->cursor != fact->target)
		return false;
	if (fact->phase == KD_JIT_PHASE_CALL_STAGED)
		*kind = KD_JIT_FEEDBACK_TRANSFER_CALL;
	else if (fact->phase == KD_JIT_PHASE_JUMP_RESOLVED)
		*kind = KD_JIT_FEEDBACK_TRANSFER_JUMP;
	else
		return false;
	return true;
}

static bool fact_emitted(const struct kd_jit_feedback_fact *fact,
		const struct kd_jit_feedback_emission_receipt *receipt)
{
	enum kd_jit_feedback_transfer_kind kind;
	unsigned int index;

	if (!fact_kind(fact, &kind))
		return false;
	for (index = 0; index < receipt->observation_count; ++index) {
		const struct kd_jit_feedback_emission *item = &receipt->observations[index];

		if (item->source_ip == fact->source_ip && item->target == fact->target &&
		    item->kind == kind)
			return item->outcome == KD_JIT_FEEDBACK_EMISSION_EMITTED;
	}
	/* No receipt outcome means it was not an input observation of this image. */
	return false;
}

static bool update_matches(struct kd_jit_feedback_publication *publication,
		enum kd_jit_image_update_phase phase)
{
	struct kd_jit_image_slot *slot = publication->slot;
	struct kd_jit_image_update *update = publication->update;
	const struct kd_jit_image *current_image;
	bool valid;

	raw_spin_lock(&slot->guard);
	current_image = rcu_dereference_protected(slot->image, lockdep_is_held(&slot->guard));
	valid = update->slot == slot && update->owner_identity == publication->update_identity &&
		update->expected_old == publication->expected_old &&
		update->candidate == publication->candidate && update->phase == phase;
	if (phase == KD_JIT_IMAGE_UPDATE_CLOSING)
		valid = valid && slot->closing && slot->update == update &&
			current_image == publication->expected_old;
	else
		valid = valid && !slot->closing && !slot->update &&
			current_image == (phase == KD_JIT_IMAGE_UPDATE_COMMITTED ?
					 publication->candidate : publication->expected_old);
	raw_spin_unlock(&slot->guard);
	return valid;
}

static bool candidate_matches(struct kd_jit_feedback_publication *publication)
{
	struct candidate_input candidate;

	return !candidate_get(publication->candidate_use, publication->candidate_holder, &candidate) &&
		candidate.owner == publication->candidate_owner &&
		candidate.image == publication->candidate && candidate.inputs == publication->inputs &&
		candidate.epoch == publication->epoch;
}

void kd_jit_feedback_publication_init(struct kd_jit_feedback_publication *publication)
{
	/* Private constructor; receipt fields are readable only after their phase. */
	publication->holder = NULL;
	publication->phase = KD_JIT_FEEDBACK_PUBLICATION_PRIVATE;
}

int kd_jit_feedback_publication_prepare(struct kd_jit_feedback_publication *publication,
		const void *holder, struct kd_jit_feedback_claim *claim,
		const void *claim_holder, const struct kd_jit_feedback_claim_item *included,
		unsigned int included_count, struct kd_jit_feedback_claim_item *ack_items,
		unsigned int ack_capacity, struct kd_jit_image_owner_use *candidate_use,
		const void *candidate_holder, const struct kd_jit_feedback_emission_receipt *emission,
		struct kd_jit_image_update *update, const void *update_identity)
{
	struct candidate_input candidate;
	struct kd_jit_image_slot *slot;
	const struct kd_jit_image *expected_old;
	unsigned int index, other, ack_count = 0;
	bool valid;
	int result;

	if (!publication || !holder || !claim || !claim_holder || !update || !update_identity ||
	    ack_capacity < included_count ||
	    !array_valid(included, included_count, sizeof(*included)) ||
	    !array_valid(ack_items, ack_capacity, sizeof(*ack_items)) ||
	    (included_count && (ack_items == included || ack_items == claim->items)))
		return -EINVAL;
	if (publication->phase != KD_JIT_FEEDBACK_PUBLICATION_PRIVATE)
		return -EALREADY;
	result = candidate_get(candidate_use, candidate_holder, &candidate);
	if (result)
		return result;
	if (!emission_valid(emission, &candidate))
		return -EINVAL;
	result = kd_jit_feedback_claim_check(claim, claim_holder, included, included_count);
	if (result)
		return result;
	if (claim->epoch != candidate.epoch)
		return -ESTALE;
	/* Membership validation above precedes every record dereference. Facts are
	 * immutable through claim_end, which the caller serializes with this ticket.
	 */
	for (index = 0; index < included_count; ++index) {
		const struct kd_jit_feedback_fact *fact = &included[index].record->fact;

		if (fact->epoch != candidate.epoch || fact->identity != included[index].identity ||
		    fact->incarnation != included[index].incarnation ||
		    !fact->producer_identity ||
		    fact->version_length != candidate.inputs->source_version_length || !fact->version ||
		    memcmp(fact->version, candidate.inputs->source_version, fact->version_length))
			return -ESTALE;
		for (other = 0; other < index; ++other)
			if (included[index].record == included[other].record)
				return -EINVAL;
	}
	slot = READ_ONCE(update->slot);
	if (!slot)
		return -ESTALE;
	raw_spin_lock(&slot->guard);
	expected_old = update->expected_old;
	valid = update->slot == slot && update->owner_identity == update_identity &&
		update->candidate == candidate.image && update->candidate != expected_old &&
		update->phase == KD_JIT_IMAGE_UPDATE_CLOSING && slot->closing && slot->update == update &&
		rcu_dereference_protected(slot->image, lockdep_is_held(&slot->guard)) == expected_old;
	raw_spin_unlock(&slot->guard);
	if (!valid)
		return -ESTALE;
	for (index = 0; index < included_count; ++index)
		if (fact_emitted(&included[index].record->fact, emission))
			ack_items[ack_count++] = included[index];

	publication->holder = holder;
	publication->claim = claim;
	publication->claim_holder = claim_holder;
	publication->included = included;
	publication->included_count = included_count;
	publication->ack_items = ack_items;
	publication->ack_count = ack_count;
	publication->candidate_use = candidate_use;
	publication->candidate_holder = candidate_holder;
	publication->candidate_owner = candidate.owner;
	publication->candidate = candidate.image;
	publication->inputs = candidate.inputs;
	publication->epoch = candidate.epoch;
	publication->emission = emission;
	publication->update = update;
	publication->slot = slot;
	publication->update_identity = update_identity;
	publication->expected_old = expected_old;
	publication->committed.identity = NULL;
	publication->acknowledged.identity = NULL;
	publication->phase = KD_JIT_FEEDBACK_PUBLICATION_PREPARED;
	return 0;
}

int kd_jit_feedback_publication_commit(struct kd_jit_feedback_publication *publication,
		const void *holder, const struct kd_jit_image *retired)
{
	int result;

	if (!publication || !holder)
		return -EINVAL;
	if (publication->holder != holder || publication->phase != KD_JIT_FEEDBACK_PUBLICATION_PREPARED)
		return -ESTALE;
	if (retired != publication->expected_old || !candidate_matches(publication) ||
	    !update_matches(publication, KD_JIT_IMAGE_UPDATE_COMMITTED))
		return -ESTALE;
	result = kd_jit_feedback_claim_check(publication->claim, publication->claim_holder,
					    publication->included, publication->included_count);
	if (result)
		return result;
	publication->committed.claim = publication->claim;
	publication->committed.claim_holder = publication->claim_holder;
	publication->committed.included = publication->included;
	publication->committed.included_count = publication->included_count;
	publication->committed.slot = publication->slot;
	publication->committed.update = publication->update;
	publication->committed.update_identity = publication->update_identity;
	publication->committed.expected_old_image_identity = (unsigned long)publication->expected_old;
	publication->committed.candidate_image_identity = (unsigned long)publication->candidate;
	publication->committed.returned_old_image_identity = (unsigned long)retired;
	publication->committed.epoch = publication->epoch;
	publication->committed.emission = publication->emission;
	publication->committed.identity = &publication->committed;
	publication->phase = KD_JIT_FEEDBACK_PUBLICATION_COMMITTED;
	return 0;
}

int kd_jit_feedback_publication_ack(struct kd_jit_feedback_publication *publication,
		const void *holder)
{
	int result;

	if (!publication || !holder)
		return -EINVAL;
	if (publication->holder != holder || publication->phase != KD_JIT_FEEDBACK_PUBLICATION_COMMITTED)
		return -ESTALE;
	if (!candidate_matches(publication) || !update_matches(publication, KD_JIT_IMAGE_UPDATE_COMMITTED))
		return -ESTALE;
	result = kd_jit_feedback_claim_check(publication->claim, publication->claim_holder,
					    publication->included, publication->included_count);
	if (result)
		return result;
	result = kd_jit_feedback_claim_ack(publication->claim, publication->claim_holder,
					  publication->ack_items, publication->ack_count);
	if (result)
		return result;
	publication->acknowledged.publication = &publication->committed;
	publication->acknowledged.claim = publication->claim;
	publication->acknowledged.claim_holder = publication->claim_holder;
	publication->acknowledged.items = publication->ack_items;
	publication->acknowledged.count = publication->ack_count;
	publication->acknowledged.identity = &publication->acknowledged;
	publication->phase = KD_JIT_FEEDBACK_PUBLICATION_ACKNOWLEDGED;
	return 0;
}

int kd_jit_feedback_publication_abort(struct kd_jit_feedback_publication *publication,
		const void *holder)
{
	if (!publication || !holder)
		return -EINVAL;
	if (publication->holder != holder || publication->phase != KD_JIT_FEEDBACK_PUBLICATION_PREPARED)
		return -ESTALE;
	if (!candidate_matches(publication) || !update_matches(publication, KD_JIT_IMAGE_UPDATE_ABORTED))
		return -ESTALE;
	publication->phase = KD_JIT_FEEDBACK_PUBLICATION_ABORTED;
	return 0;
}
