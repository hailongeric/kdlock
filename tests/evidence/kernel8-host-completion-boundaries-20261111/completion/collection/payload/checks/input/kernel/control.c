// SPDX-License-Identifier: GPL-2.0-only
/* Caller-driven compiler control; no source execution or packet ownership. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/string.h>

#include "control.h"

struct reader { const unsigned char *data; size_t left; };
struct writer { unsigned char *data; size_t used; };

static u64 decode64(const unsigned char *bytes)
{
	u64 value = 0;
	unsigned int index;

	for (index = 0; index < 8; ++index)
		value |= (u64)bytes[index] << (index * 8);
	return value;
}

static void encode64(unsigned char *bytes, u64 value)
{
	unsigned int index;

	for (index = 0; index < 8; ++index)
		bytes[index] = value >> (index * 8);
}

static bool take(struct reader *reader, u64 *value)
{
	if (reader->left < 8)
		return false;
	*value = decode64(reader->data);
	reader->data += 8;
	reader->left -= 8;
	return true;
}

static bool blob(struct reader *reader, struct kd_jit_control_bytes *value)
{
	u64 length;

	if (!take(reader, &length) || length > reader->left)
		return false;
	value->data = reader->data;
	value->length = length;
	reader->data += length;
	reader->left -= length;
	return true;
}

static void put(struct writer *writer, u64 value)
{
	encode64(writer->data + writer->used, value);
	writer->used += 8;
}

static void put_blob(struct writer *writer, const struct kd_jit_control_bytes *value)
{
	put(writer, value->length);
	if (value->length)
		memcpy(writer->data + writer->used, value->data, value->length);
	writer->used += value->length;
}

static bool room(size_t capacity, unsigned int fixed, unsigned int rows,
		unsigned int row_words, size_t blobs)
{
	size_t bytes = 32 + (size_t)fixed * 8;

	if (row_words && (size_t)rows > ((size_t)-1 - bytes) / ((size_t)row_words * 8))
		return false;
	bytes += (size_t)rows * row_words * 8;
	return blobs <= (size_t)-1 - bytes && bytes + blobs <= capacity;
}

static void start(struct writer *writer, void *output, unsigned long op, unsigned int rows)
{
	writer->data = output;
	writer->used = 0;
	put(writer, KD_JIT_CONTROL_ABI);
	put(writer, op);
	put(writer, 0);
	put(writer, rows);
}

static void finish(struct writer *writer, size_t *length)
{
	encode64(writer->data + 16, writer->used);
	*length = writer->used;
}

void kd_jit_control_image_init(struct kd_jit_control_image *image)
{
	kd_jit_image_owner_use_init(&image->published);
	image->producer_initialized = false;
	image->owner_initialized = false;
	image->published_live = false;
	image->owner_released = false;
	image->producer_closed = false;
	image->producer_released = false;
}

void kd_jit_control_storage_init(struct kd_jit_control_storage *storage,
		struct kd_jit_feedback_claim_item *claim_items,
		struct kd_jit_feedback_claim_item *included,
		struct kd_jit_feedback_claim_item *ack_items, unsigned int capacity)
{
	storage->claim_items = claim_items;
	storage->included = included;
	storage->ack_items = ack_items;
	storage->capacity = capacity;
	storage->included_count = 0;
	storage->claim_holder = NULL;
	kd_jit_feedback_claim_init(&storage->claim);
	kd_jit_source_use_init(&storage->build);
	kd_jit_image_owner_use_init(&storage->baseline);
	kd_jit_image_owner_use_init(&storage->candidate_use);
	kd_jit_image_update_init(&storage->update);
	kd_jit_feedback_publication_init(&storage->publication);
	storage->old = NULL;
	storage->expected_old = NULL;
	storage->retired = NULL;
	storage->build_live = false;
	storage->claim_live = false;
	storage->reserved = false;
	storage->baseline_live = false;
	storage->candidate_live = false;
	storage->loaded = false;
	storage->update_started = false;
	storage->old_prepared = false;
	storage->publication_prepared = false;
	storage->committed = false;
	storage->new_bound = false;
	storage->old_finished = false;
	storage->current_set = false;
	storage->old_reported = false;
	storage->published = false;
	storage->acknowledged = false;
	storage->aborted = false;
	storage->ending = false;
}

int kd_jit_control_session_init(struct kd_jit_control_session *session,
		struct kd_jit_feedback_pool *feedback, struct kd_jit_source_epoch *epoch,
		struct kd_jit_image_slot *slot, const struct kd_jit_control_provider_ops *ops,
		void *context)
{
	if (!session || !feedback || !epoch || !slot || !ops || !ops->allocate ||
	    !ops->release || !ops->get_published || !ops->reserve || !ops->load ||
	    !ops->published || !ops->retired || !ops->idle)
		return -EINVAL;
	session->feedback = feedback;
	session->epoch = epoch;
	session->slot = slot;
	session->ops = ops;
	session->context = context;
	session->storage = NULL;
	return 0;
}

bool kd_jit_control_session_idle(struct kd_jit_control_session *session)
{
	bool empty;

	if (!session || session->storage)
		return false;
	raw_spin_lock(&session->slot->guard);
	empty = !session->slot->closing && !session->slot->update &&
		!rcu_dereference_protected(session->slot->image,
					  lockdep_is_held(&session->slot->guard));
	raw_spin_unlock(&session->slot->guard);
	return empty && session->ops->idle(session->context);
}

int kd_jit_control_image_collect(struct kd_jit_control_image *image)
{
	int result;

	if (!image || image->published_live)
		return -EBUSY;
	if (image->owner_initialized && !image->owner_released) {
		if (image->owner.phase == KD_JIT_IMAGE_OWNER_OPEN) {
			result = kd_jit_image_owner_close(&image->owner);
			if (result)
				return result;
		}
		result = kd_jit_image_owner_try_release(&image->owner);
		if (result)
			return result;
		image->owner_released = true;
	}
	if (image->producer_initialized && !image->producer_released) {
		if (!image->producer_closed) {
			result = kd_jit_feedback_producer_close(&image->producer);
			if (result)
				return result;
			image->producer_closed = true;
		}
		result = kd_jit_feedback_producer_release(&image->producer);
		if (result)
			return result;
		image->producer_released = true;
	}
	return 0;
}

static int release_empty_cycle(struct kd_jit_control_session *session, int error)
{
	struct kd_jit_control_storage *storage = session->storage;
	int result;

	if (storage->build_live) {
		result = kd_jit_source_use_put(&storage->build, storage);
		if (result)
			return result;
		storage->build_live = false;
	}
	session->storage = NULL;
	session->ops->release(session->context, storage);
	return error;
}

static int claim_command(struct kd_jit_control_session *session, struct reader *input,
		u64 rows, void *output, size_t capacity, size_t *length)
{
	struct kd_jit_control_storage *storage = session->storage;
	struct kd_jit_control_bytes version;
	struct writer writer;
	u64 epoch, holder, maximum;
	unsigned int index;
	int result;

	if (rows || !take(input, &epoch) || !take(input, &holder) || !take(input, &maximum) ||
	    input->left || epoch != (unsigned long)session->epoch || !holder || !maximum || maximum > ~0U)
		return -EINVAL;
	version.data = session->epoch->description.version;
	version.length = session->epoch->description.version_length;
	if (version.length > (size_t)-1 - 8 || !room(capacity, 3, maximum, 12, version.length + 8))
		return -EMSGSIZE;
	if (!storage) {
		result = session->ops->allocate(session->context, &storage);
		if (result)
			return result;
		if (!storage || !storage->claim_items || !storage->included || !storage->ack_items ||
		    maximum > storage->capacity || storage->build_live || storage->claim_live) {
			if (storage)
				session->ops->release(session->context, storage);
			return -EINVAL;
		}
		session->storage = storage;
	}
	if (!storage->build_live) {
		result = kd_jit_source_use_get(session->epoch, &storage->build, storage,
					       KD_JIT_SOURCE_USE_BUILD);
		if (result)
			return release_empty_cycle(session, result);
		storage->build_live = true;
	}
	if (!storage->claim_live) {
		result = kd_jit_feedback_claim_begin(session->feedback, session->epoch, &storage->claim,
				storage->claim_items, maximum, (const void *)(unsigned long)holder);
		if (result)
			return release_empty_cycle(session, result);
		storage->claim_holder = (const void *)(unsigned long)holder;
		storage->claim_live = true;
	}
	if (storage->claim.holder != (const void *)(unsigned long)holder || storage->claim.count > maximum)
		return -ESTALE;
	start(&writer, output, KD_JIT_CONTROL_CLAIM, storage->claim.count);
	put(&writer, (unsigned long)&storage->claim);
	put(&writer, holder);
	put(&writer, epoch);
	for (index = 0; index < storage->claim.count; ++index) {
		const struct kd_jit_feedback_fact *fact = &storage->claim_items[index].record->fact;

		put(&writer, (unsigned long)fact->identity);
		put(&writer, fact->incarnation);
		put(&writer, (unsigned long)fact->producer_identity);
		put(&writer, fact->producer_image_identity);
		put(&writer, fact->kind);
		put(&writer, fact->detail);
		put(&writer, fact->source_ip);
		put(&writer, fact->target);
		put(&writer, fact->cursor);
		put(&writer, fact->phase);
		put(&writer, fact->classification);
		put(&writer, (u64)(s64)fact->entry_result);
	}
	put_blob(&writer, &version);
	finish(&writer, length);
	return 0;
}

static bool claim_matches(struct kd_jit_control_storage *storage, u64 claim, u64 holder)
{
	return storage && storage->claim_live && claim == (unsigned long)&storage->claim &&
		holder == (unsigned long)storage->claim_holder;
}

static size_t symbol_bytes(const struct kd_jit_control_candidate *candidate)
{
	const struct kd_jit_control_bytes *symbols[4] = { &candidate->descriptor_symbol,
		&candidate->source_symbol, &candidate->producer_symbol, &candidate->entry_symbol };
	size_t total = 32;
	unsigned int index;

	for (index = 0; index < 4; ++index) {
		if (!symbols[index]->data || !symbols[index]->length ||
		    symbols[index]->length > (size_t)-1 - total)
			return 0;
		total += symbols[index]->length;
	}
	return total;
}

static int build_command(struct kd_jit_control_session *session, struct reader *input,
		u64 rows, void *output, size_t capacity, size_t *length)
{
	struct kd_jit_control_storage *storage = session->storage;
	struct kd_jit_control_candidate *candidate;
	struct writer writer;
	u64 claim, holder, epoch, slot, old;
	size_t symbols;
	int result;

	if (rows || !take(input, &claim) || !take(input, &holder) || !take(input, &epoch) ||
	    !take(input, &slot) || !take(input, &old) || input->left ||
	    !claim_matches(storage, claim, holder) || epoch != (unsigned long)session->epoch ||
	    slot != (unsigned long)session->slot || storage->aborted)
		return -EINVAL;
	if (!storage->reserved) {
		if (!storage->baseline_live) {
			storage->old = session->ops->get_published(session->context, session->slot);
			if (storage->old) {
				if (!storage->old->published_live)
					return -ESTALE;
				result = kd_jit_image_owner_use_get(&storage->old->owner, &storage->baseline,
						storage, KD_JIT_IMAGE_OWNER_USE_BASELINE);
				if (result)
					return result;
				storage->baseline_live = true;
				storage->expected_old = storage->old->owner.image;
			}
		}
		if (old != (unsigned long)storage->expected_old)
			return -ESTALE;
		result = session->ops->reserve(session->context, session->epoch, &storage->candidate);
		if (result)
			return result;
		storage->reserved = true;
	}
	candidate = &storage->candidate;
	if (old != (unsigned long)storage->expected_old || !candidate->control || !candidate->image ||
	    !candidate->inputs || !candidate->emission || !candidate->code_base || !candidate->code_capacity ||
	    !candidate->code_lease || !candidate->code_release)
		return -ESTALE;
	symbols = symbol_bytes(candidate);
	if (!symbols || !room(capacity, 12, 0, 0, symbols))
		return -EMSGSIZE;
	start(&writer, output, KD_JIT_CONTROL_BUILD_START, 0);
	put(&writer, (unsigned long)candidate->control);
	put(&writer, slot);
	put(&writer, (unsigned long)candidate->image);
	put(&writer, (unsigned long)candidate->inputs);
	put(&writer, (unsigned long)&candidate->control->producer);
	put(&writer, (unsigned long)&storage->update);
	put(&writer, (unsigned long)storage);
	put(&writer, old);
	put(&writer, (unsigned long)candidate->emission);
	put(&writer, epoch);
	put(&writer, candidate->code_base);
	put(&writer, candidate->code_capacity);
	put_blob(&writer, &candidate->descriptor_symbol);
	put_blob(&writer, &candidate->source_symbol);
	put_blob(&writer, &candidate->producer_symbol);
	put_blob(&writer, &candidate->entry_symbol);
	finish(&writer, length);
	return 0;
}

static int stage_command(struct kd_jit_control_session *session, struct reader *input,
		u64 rows, void *output, size_t capacity, size_t *length)
{
	struct kd_jit_control_storage *storage = session->storage;
	struct kd_jit_control_bytes assembly, metadata, manifest, machine, flat_metadata;
	struct kd_jit_control_image *image;
	struct writer writer;
	u64 candidate;
	int result;

	if (rows || !take(input, &candidate) || !blob(input, &assembly) || !blob(input, &metadata) ||
	    !blob(input, &manifest) || !blob(input, &machine) || !blob(input, &flat_metadata) || input->left || !storage || !storage->reserved ||
	    candidate != (unsigned long)storage->candidate.control || storage->update_started || storage->aborted)
		return -EINVAL;
	if (!room(capacity, 1, 0, 0, 0))
		return -EMSGSIZE;
	result = session->ops->load(session->context, &storage->candidate, &assembly, &metadata, &manifest, &machine, &flat_metadata);
	if (result)
		return result;
	image = storage->candidate.control;
	if (!image->producer_initialized) {
		if (storage->candidate.image->feedback_producer != &image->producer ||
		    storage->candidate.inputs->image != storage->candidate.image ||
		    storage->candidate.emission->inputs != storage->candidate.inputs)
			return -ESTALE;
		result = kd_jit_feedback_producer_init(&image->producer, &image->producer,
			storage->candidate.image, &storage->build, storage);
		if (result)
			return result;
		image->producer_initialized = true;
	}
	if (!image->owner_initialized) {
		result = kd_jit_image_owner_init(&image->owner, storage->candidate.image,
			storage->candidate.inputs, &storage->build, storage,
			session->epoch->description.configuration_identity,
			session->epoch->description.load_identity, storage->candidate.code_lease,
			storage->candidate.code_release);
		if (result)
			return result;
		image->owner_initialized = true;
	}
	if (!storage->candidate_live) {
		result = kd_jit_image_owner_use_get(&image->owner, &storage->candidate_use,
			storage, KD_JIT_IMAGE_OWNER_USE_EXTERNAL);
		if (result)
			return result;
		storage->candidate_live = true;
	}
	storage->loaded = true;
	start(&writer, output, KD_JIT_CONTROL_STAGE_LOAD, 0);
	put(&writer, candidate);
	finish(&writer, length);
	return 0;
}

static int select_inputs(struct kd_jit_control_storage *storage, struct reader *input,
		unsigned int count)
{
	unsigned int index, member;
	u64 identity, incarnation;

	if (count > storage->capacity)
		return -EINVAL;
	if (storage->update_started && count != storage->included_count)
		return -ESTALE;
	for (index = 0; index < count; ++index) {
		if (!take(input, &identity) || !take(input, &incarnation))
			return -EINVAL;
		for (member = 0; member < storage->claim.count; ++member)
			if (identity == (unsigned long)storage->claim_items[member].identity &&
			    incarnation == storage->claim_items[member].incarnation)
				break;
		if (member == storage->claim.count)
			return -ESTALE;
		if (storage->update_started) {
			if (storage->included[index].record != storage->claim_items[member].record ||
			    storage->included[index].identity != storage->claim_items[member].identity ||
			    storage->included[index].incarnation != incarnation)
				return -ESTALE;
		} else {
			storage->included[index] = storage->claim_items[member];
		}
	}
	if (input->left)
		return -EINVAL;
	if (!storage->update_started)
		storage->included_count = count;
	return kd_jit_feedback_claim_check(&storage->claim, storage->claim.holder,
					 storage->included, count);
}

static int publish_progress(struct kd_jit_control_session *session)
{
	struct kd_jit_control_storage *storage = session->storage;
	struct kd_jit_control_image *image = storage->candidate.control;
	int result;

	if (!storage->update_started) {
		if (session->ops->admit_publish) {
			result = session->ops->admit_publish(session->context);
			if (result)
				return result;
		}
		result = kd_jit_image_update_begin(session->slot, &storage->update,
			storage->expected_old, storage->candidate.image, storage);
		if (result)
			return result;
		storage->update_started = true;
	}
	if (storage->old && !storage->old_prepared) {
		result = kd_jit_image_owner_retire_prepare(&storage->old->published,
			storage->old, &storage->update, storage);
		if (result)
			return result;
		storage->old_prepared = true;
	}
	if (!storage->publication_prepared) {
		result = kd_jit_feedback_publication_prepare(&storage->publication, storage,
			&storage->claim, storage->claim.holder, storage->included, storage->included_count,
			storage->ack_items, storage->capacity, &storage->candidate_use, storage,
			storage->candidate.emission, &storage->update, storage);
		if (result)
			return result;
		storage->publication_prepared = true;
	}
	if (!storage->committed) {
		result = kd_jit_image_update_try_commit(&storage->update, storage, &storage->retired);
		if (result)
			return result;
		storage->committed = true;
	}
	if (!storage->new_bound) {
		result = kd_jit_image_owner_slot_get(&storage->candidate_use, storage,
			&image->published, image, session->slot);
		if (result)
			return result;
		image->published_live = true;
		storage->new_bound = true;
	}
	if (storage->old && !storage->old_finished) {
		result = kd_jit_image_owner_retire_finish(&storage->old->published,
			storage->old, &storage->update, storage, storage->retired);
		if (result)
			return result;
		storage->old->published_live = false;
		storage->old_finished = true;
	}
	if (!storage->current_set) {
		session->ops->published(session->context, session->slot, storage->old, image);
		storage->current_set = true;
	}
	if (!storage->published) {
		result = kd_jit_feedback_publication_commit(&storage->publication, storage, storage->retired);
		if (result)
			return result;
		storage->published = true;
	}
	if (storage->baseline_live) {
		result = kd_jit_image_owner_use_put(&storage->baseline, storage);
		if (result)
			return result;
		storage->baseline_live = false;
	}
	if (storage->old && !storage->old_reported) {
		session->ops->retired(session->context, storage->old);
		storage->old_reported = true;
	}
	return 0;
}

static int publish_command(struct kd_jit_control_session *session, struct reader *input,
		u64 rows, void *output, size_t capacity, size_t *length)
{
	struct kd_jit_control_storage *storage = session->storage;
	const struct kd_jit_feedback_commit_receipt *receipt;
	struct writer writer;
	u64 candidate, claim, holder;
	unsigned int index;
	int result;

	if (!take(input, &candidate) || !take(input, &claim) || !take(input, &holder) ||
	    rows > ~0U || !claim_matches(storage, claim, holder) || !storage->loaded ||
	    storage->aborted || candidate != (unsigned long)storage->candidate.control)
		return -EINVAL;
	if (!room(capacity, 14, rows, 2, 0))
		return -EMSGSIZE;
	result = select_inputs(storage, input, rows);
	if (result)
		return result;
	result = publish_progress(session);
	if (result)
		return result;
	receipt = &storage->publication.committed;
	start(&writer, output, KD_JIT_CONTROL_PUBLISH, receipt->included_count);
	put(&writer, (unsigned long)receipt->identity);
	put(&writer, claim);
	put(&writer, holder);
	put(&writer, (unsigned long)receipt->slot);
	put(&writer, (unsigned long)receipt->update);
	put(&writer, (unsigned long)receipt->update_identity);
	put(&writer, receipt->expected_old_image_identity);
	put(&writer, receipt->candidate_image_identity);
	put(&writer, receipt->returned_old_image_identity);
	put(&writer, (unsigned long)receipt->epoch);
	put(&writer, (unsigned long)receipt->emission);
	put(&writer, (unsigned long)storage->candidate.inputs);
	put(&writer, (unsigned long)&storage->candidate.control->producer);
	put(&writer, candidate);
	for (index = 0; index < receipt->included_count; ++index) {
		put(&writer, (unsigned long)receipt->included[index].identity);
		put(&writer, receipt->included[index].incarnation);
	}
	finish(&writer, length);
	return 0;
}

static int ack_command(struct kd_jit_control_session *session, struct reader *input,
		u64 rows, void *output, size_t capacity, size_t *length)
{
	struct kd_jit_control_storage *storage = session->storage;
	const struct kd_jit_feedback_ack_receipt *receipt;
	struct writer writer;
	u64 publication;
	unsigned int index;
	int result;

	if (rows || !take(input, &publication) || input->left || !storage || !storage->published ||
	    publication != (unsigned long)storage->publication.committed.identity)
		return -EINVAL;
	if (!room(capacity, 5, storage->publication.ack_count, 2, 0))
		return -EMSGSIZE;
	if (!storage->acknowledged) {
		result = kd_jit_feedback_publication_ack(&storage->publication, storage);
		if (result)
			return result;
		storage->acknowledged = true;
	}
	receipt = &storage->publication.acknowledged;
	start(&writer, output, KD_JIT_CONTROL_ACK, receipt->count);
	put(&writer, (unsigned long)receipt->identity);
	put(&writer, (unsigned long)receipt->publication->identity);
	put(&writer, (unsigned long)receipt->claim);
	put(&writer, (unsigned long)receipt->claim_holder);
	put(&writer, (unsigned long)session->epoch);
	for (index = 0; index < receipt->count; ++index) {
		put(&writer, (unsigned long)receipt->items[index].identity);
		put(&writer, receipt->items[index].incarnation);
	}
	finish(&writer, length);
	return 0;
}

static int cancel_candidate(struct kd_jit_control_session *session)
{
	struct kd_jit_control_storage *storage = session->storage;
	struct kd_jit_control_image *image;
	int result;

	if (storage->committed)
		return -EBUSY;
	if (storage->update_started && storage->update.phase != KD_JIT_IMAGE_UPDATE_ABORTED) {
		result = kd_jit_image_update_abort(&storage->update, storage);
		if (result)
			return result;
	}
	if (storage->old_prepared) {
		result = kd_jit_image_owner_retire_abort(&storage->old->published,
			storage->old, &storage->update, storage);
		if (result)
			return result;
		storage->old_prepared = false;
	}
	if (storage->publication_prepared &&
	    storage->publication.phase != KD_JIT_FEEDBACK_PUBLICATION_ABORTED) {
		result = kd_jit_feedback_publication_abort(&storage->publication, storage);
		if (result)
			return result;
	}
	if (storage->candidate_live) {
		result = kd_jit_image_owner_use_put(&storage->candidate_use, storage);
		if (result)
			return result;
		storage->candidate_live = false;
	}
	if (storage->reserved) {
		image = storage->candidate.control;
		if (image && image->owner_initialized) {
			if (image->owner.phase == KD_JIT_IMAGE_OWNER_OPEN) {
				result = kd_jit_image_owner_cancel_unpublished(&image->owner);
				if (result)
					return result;
			}
			result = kd_jit_control_image_collect(image);
			if (result)
				return result;
		} else {
			/* No owner accepted this provider hold; release exactly once. */
			if (storage->candidate.code_lease) {
				void *lease = storage->candidate.code_lease;
				kd_jit_image_code_release_fn release = storage->candidate.code_release;

				storage->candidate.code_lease = NULL;
				release(lease);
			}
			if (image) {
				result = kd_jit_control_image_collect(image);
				if (result)
					return result;
			}
		}
	}
	if (storage->baseline_live) {
		result = kd_jit_image_owner_use_put(&storage->baseline, storage);
		if (result)
			return result;
		storage->baseline_live = false;
	}
	storage->aborted = true;
	return 0;
}

static int abort_command(struct kd_jit_control_session *session, struct reader *input,
		u64 rows, void *output, size_t capacity, size_t *length)
{
	struct kd_jit_control_storage *storage = session->storage;
	struct writer writer;
	u64 candidate, claim, holder;
	int result;

	if (rows || !take(input, &candidate) || !take(input, &claim) || !take(input, &holder) ||
	    input->left || !claim_matches(storage, claim, holder) ||
	    candidate != (storage->reserved ? (unsigned long)storage->candidate.control : 0))
		return -EINVAL;
	if (!room(capacity, 3, 0, 0, 0))
		return -EMSGSIZE;
	if (!storage->aborted) {
		result = cancel_candidate(session);
		if (result)
			return result;
	}
	start(&writer, output, KD_JIT_CONTROL_ABORT, 0);
	put(&writer, candidate);
	put(&writer, claim);
	put(&writer, holder);
	finish(&writer, length);
	return 0;
}

static int end_command(struct kd_jit_control_session *session, struct reader *input,
		u64 rows, void *output, size_t capacity, size_t *length)
{
	struct kd_jit_control_storage *storage = session->storage;
	struct writer writer;
	u64 claim, holder;
	int result;

	if (rows || !take(input, &claim) || !take(input, &holder) || input->left ||
	    !storage || claim != (unsigned long)&storage->claim ||
	    holder != (unsigned long)storage->claim_holder ||
	    (!storage->aborted && !storage->acknowledged &&
	     (storage->reserved || storage->update_started)))
		return -EINVAL;
	if (!room(capacity, 2, 0, 0, 0))
		return -EMSGSIZE;
	storage->ending = true;
	/* Explicit caller receipt that every compiler/publication/transport observer
	 * has finished. Claim end may partially progress; its own cursor resumes it.
	 */
	if (storage->claim_live) {
		result = kd_jit_feedback_claim_end(&storage->claim, storage->claim_holder);
		if (result)
			return result;
		storage->claim_live = false;
	}
	if (storage->candidate_live) {
		result = kd_jit_image_owner_use_put(&storage->candidate_use, storage);
		if (result)
			return result;
		storage->candidate_live = false;
	}
	if (storage->baseline_live) {
		result = kd_jit_image_owner_use_put(&storage->baseline, storage);
		if (result)
			return result;
		storage->baseline_live = false;
	}
	if (storage->build_live) {
		result = kd_jit_source_use_put(&storage->build, storage);
		if (result)
			return result;
		storage->build_live = false;
	}
	start(&writer, output, KD_JIT_CONTROL_CLAIM_END, 0);
	put(&writer, claim);
	put(&writer, holder);
	finish(&writer, length);
	session->storage = NULL;
	/* No cycle access follows its provider release. Published controls persist. */
	session->ops->release(session->context, storage);
	return 0;
}

int kd_jit_control_command(struct kd_jit_control_session *session, unsigned long op,
		const void *input, size_t input_length, void *output,
		size_t output_capacity, size_t *output_length)
{
	struct reader reader = { .data = input, .left = input_length };
	u64 abi, encoded_op, total, rows;

	if (!session || !input || !output || !output_length)
		return -EINVAL;
	*output_length = 0;
	if (session->storage && session->storage->ending && op != KD_JIT_CONTROL_CLAIM_END)
		return -EBUSY;
	if (!take(&reader, &abi) || !take(&reader, &encoded_op) || !take(&reader, &total) ||
	    !take(&reader, &rows) || abi != KD_JIT_CONTROL_ABI || encoded_op != op || total != input_length)
		return -EINVAL;
	switch (op) {
	case KD_JIT_CONTROL_CLAIM:
		return claim_command(session, &reader, rows, output, output_capacity, output_length);
	case KD_JIT_CONTROL_BUILD_START:
		return build_command(session, &reader, rows, output, output_capacity, output_length);
	case KD_JIT_CONTROL_STAGE_LOAD:
		return stage_command(session, &reader, rows, output, output_capacity, output_length);
	case KD_JIT_CONTROL_PUBLISH:
		return publish_command(session, &reader, rows, output, output_capacity, output_length);
	case KD_JIT_CONTROL_ACK:
		return ack_command(session, &reader, rows, output, output_capacity, output_length);
	case KD_JIT_CONTROL_CLAIM_END:
		return end_command(session, &reader, rows, output, output_capacity, output_length);
	case KD_JIT_CONTROL_ABORT:
		return abort_command(session, &reader, rows, output, output_capacity, output_length);
	default:
		if (session->ops->command)
			return session->ops->command(session->context, session, op, input,
				input_length, output, output_capacity, output_length);
		return -EINVAL;
	}
}
