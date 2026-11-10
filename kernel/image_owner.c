// SPDX-License-Identifier: GPL-2.0-only
/* Exact executable-provider/source holds around the existing image-slot APIs. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/string.h>

#include "image_owner.h"

static bool span_valid(unsigned long start, size_t length)
{
	return length && length - 1 <= ~0UL - start;
}

static bool bytes_valid(const void *bytes, size_t length)
{
	return bytes && span_valid((unsigned long)bytes, length);
}

static bool array_valid(const void *array, unsigned int count, size_t element_size)
{
	if (!count)
		return true;
	return (size_t)count <= (size_t)-1 / element_size &&
	       bytes_valid(array, (size_t)count * element_size);
}

static struct kd_jit_source_epoch *source_use_epoch(struct kd_jit_source_use *use,
		const void *holder, enum kd_jit_source_use_kind kind)
{
	struct kd_jit_source_epoch *epoch;
	bool valid;

	if (!use || !holder)
		return NULL;
	epoch = READ_ONCE(use->epoch);
	if (!epoch)
		return NULL;
	raw_spin_lock(&epoch->guard);
	valid = use->epoch == epoch && use->linked && use->holder == holder &&
		use->kind == kind &&
		(epoch->phase == KD_JIT_SOURCE_OPEN || epoch->phase == KD_JIT_SOURCE_CLOSED);
	raw_spin_unlock(&epoch->guard);
	return valid ? epoch : NULL;
}

static bool source_bytes_match(const struct kd_jit_source_description *source,
		const struct kd_jit_image_source_bytes *decoded)
{
	unsigned int byte, region;

	for (byte = 0; byte < decoded->length; ++byte) {
		unsigned long address = decoded->ip + byte;
		bool found = false;

		for (region = 0; region < source->region_count; ++region) {
			const struct kd_jit_source_region *retained = &source->regions[region];
			unsigned long offset;

			if (address < retained->start)
				continue;
			offset = address - retained->start;
			if (offset >= retained->length)
				continue;
			if (decoded->bytes[byte] != retained->bytes[offset])
				return false;
			found = true;
			break;
		}
		if (!found)
			return false;
	}
	return true;
}

static bool inputs_valid(const struct kd_jit_image *image,
		const struct kd_jit_image_inputs *inputs, struct kd_jit_source_epoch *epoch,
		const void *configuration_identity, const void *load_identity)
{
	const struct kd_jit_source_description *source = &epoch->description;
	unsigned int index, other;

	if (!image || !image->feedback_producer || !inputs || inputs->image != image || image->source_identity != epoch ||
	    !configuration_identity || configuration_identity != source->configuration_identity ||
	    !load_identity || load_identity != source->load_identity ||
	    !image->entry || image->abi_version != KD_JIT_ABI_VERSION ||
	    image->packet_size != sizeof(struct kd_regs) ||
	    image->io_size != sizeof(struct kd_jit_io) || !image->entry_count ||
	    !array_valid(image->entry_sites, image->entry_count, sizeof(*image->entry_sites)) ||
	    !array_valid(image->source_sites, image->source_count, sizeof(*image->source_sites)) ||
	    inputs->source_count != image->source_count ||
	    !array_valid(inputs->source_bytes, inputs->source_count, sizeof(*inputs->source_bytes)) ||
	    inputs->source_version_length != source->version_length ||
	    !bytes_valid(inputs->source_version, inputs->source_version_length) ||
	    inputs->current_task_gs_offset != source->current_task_gs_offset ||
	    memcmp(inputs->source_version, source->version, source->version_length))
		return false;
	for (index = 0; index < image->entry_count; ++index)
		for (other = 0; other < index; ++other)
			if (image->entry_sites[index] == image->entry_sites[other])
				return false;
	for (index = 0; index < image->source_count; ++index) {
		const struct kd_jit_source_site *site = &image->source_sites[index];
		const struct kd_jit_image_source_bytes *decoded = &inputs->source_bytes[index];

		if (decoded->ip != site->ip || !decoded->length || decoded->length > 15 ||
		    !span_valid(decoded->ip, decoded->length) ||
		    !bytes_valid(decoded->bytes, decoded->length) ||
		    site->next_ip != decoded->ip + decoded->length ||
		    (site->kind != KD_JIT_SITE_CALL && site->kind != KD_JIT_SITE_JUMP &&
		     site->kind != KD_JIT_SITE_OTHER) || !source_bytes_match(source, decoded))
			return false;
		for (other = 0; other < index; ++other)
			if (site->ip == image->source_sites[other].ip)
				return false;
	}
	return true;
}

int kd_jit_image_owner_init(struct kd_jit_image_owner *owner,
		const struct kd_jit_image *image, const struct kd_jit_image_inputs *inputs,
		struct kd_jit_source_use *build, const void *build_holder,
		const void *configuration_identity, const void *load_identity,
		void *code_lease, kd_jit_image_code_release_fn code_release)
{
	struct kd_jit_source_epoch *epoch;
	int result;

	if (!owner || build == &owner->source_use || !code_lease || !code_release)
		return -EINVAL;
	epoch = source_use_epoch(build, build_holder, KD_JIT_SOURCE_USE_BUILD);
	if (!epoch)
		return -ESTALE;
	/* The caller's retained BUILD and code hold protect all validation reads. */
	if (!inputs_valid(image, inputs, epoch, configuration_identity, load_identity))
		return -EINVAL;
	kd_jit_source_use_init(&owner->source_use);
	result = kd_jit_source_use_extend(build, build_holder, &owner->source_use,
					 owner, KD_JIT_SOURCE_USE_IMAGE);
	if (result)
		return result;
	kd_jit_feedback_producer_use_init(&owner->producer_use);
	result = kd_jit_feedback_producer_use_get(image->feedback_producer,
		&owner->producer_use, owner, KD_JIT_FEEDBACK_PRODUCER_IMAGE, image);
	if (result) {
		int drop = kd_jit_source_use_put(&owner->source_use, owner);

		return drop ? drop : result;
	}
	/* No fallible operation follows the code-provider hold transfer. */
	raw_spin_lock_init(&owner->guard);
	INIT_LIST_HEAD(&owner->users);
	owner->image = image;
	owner->inputs = inputs;
	owner->code_lease = code_lease;
	owner->code_release = code_release;
	owner->phase = KD_JIT_IMAGE_OWNER_OPEN;
	owner->ever_published = false;
	return 0;
}

void kd_jit_image_owner_use_init(struct kd_jit_image_owner_use *use)
{
	INIT_LIST_HEAD(&use->owner_link);
	use->owner = NULL;
	use->holder = NULL;
	use->kind = KD_JIT_IMAGE_OWNER_USE_UNUSED;
	use->slot = NULL;
	use->retire_update = NULL;
	use->retire_identity = NULL;
	use->linked = false;
}

static bool direct_kind_valid(enum kd_jit_image_owner_use_kind kind)
{
	return kind == KD_JIT_IMAGE_OWNER_USE_EXTERNAL || kind == KD_JIT_IMAGE_OWNER_USE_BASELINE;
}

static bool owner_live_locked(struct kd_jit_image_owner *owner)
{
	return owner->phase == KD_JIT_IMAGE_OWNER_OPEN || owner->phase == KD_JIT_IMAGE_OWNER_CLOSED;
}

static bool use_matches_locked(struct kd_jit_image_owner *owner,
		struct kd_jit_image_owner_use *use, const void *holder)
{
	return owner_live_locked(owner) && use->owner == owner && use->linked &&
	       use->holder == holder;
}

static int link_use_locked(struct kd_jit_image_owner *owner,
		struct kd_jit_image_owner_use *use, const void *holder,
		enum kd_jit_image_owner_use_kind kind, struct kd_jit_image_slot *slot)
{
	if (use->owner || use->linked || !list_empty(&use->owner_link))
		return -EALREADY;
	use->owner = owner;
	use->holder = holder;
	use->kind = kind;
	use->slot = slot;
	use->retire_update = NULL;
	use->retire_identity = NULL;
	use->linked = true;
	list_add_tail(&use->owner_link, &owner->users);
	return 0;
}

static void unlink_use_locked(struct kd_jit_image_owner_use *use)
{
	list_del_init(&use->owner_link);
	use->linked = false;
	use->holder = NULL;
	use->kind = KD_JIT_IMAGE_OWNER_USE_UNUSED;
	use->slot = NULL;
	use->retire_update = NULL;
	use->retire_identity = NULL;
	WRITE_ONCE(use->owner, NULL);
}

int kd_jit_image_owner_use_get(struct kd_jit_image_owner *owner,
		struct kd_jit_image_owner_use *use, const void *holder,
		enum kd_jit_image_owner_use_kind kind)
{
	int result;

	if (!owner || !use || !holder || !direct_kind_valid(kind))
		return -EINVAL;
	raw_spin_lock(&owner->guard);
	if (owner->phase != KD_JIT_IMAGE_OWNER_OPEN)
		result = -ESHUTDOWN;
	else
		result = link_use_locked(owner, use, holder, kind, NULL);
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_jit_image_owner_use_put(struct kd_jit_image_owner_use *use, const void *holder)
{
	struct kd_jit_image_owner *owner;
	int result = 0;

	if (!use || !holder)
		return -EINVAL;
	owner = READ_ONCE(use->owner);
	if (!owner)
		return -ESTALE;
	raw_spin_lock(&owner->guard);
	if (!use_matches_locked(owner, use, holder))
		result = -ESTALE;
	else if (!direct_kind_valid(use->kind))
		result = -EBUSY;
	else
		unlink_use_locked(use);
	/* No use/descriptor/code access follows successful unlink. */
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_jit_image_owner_slot_get(struct kd_jit_image_owner_use *parent,
		const void *parent_holder, struct kd_jit_image_owner_use *published,
		const void *published_holder, struct kd_jit_image_slot *slot)
{
	struct kd_jit_image_owner *owner;
	struct kd_jit_image_owner_use *other;
	const struct kd_jit_image *image;
	int result;

	if (!parent || !parent_holder || !published || parent == published ||
	    !published_holder || !slot)
		return -EINVAL;
	owner = READ_ONCE(parent->owner);
	if (!owner)
		return -ESTALE;
	raw_spin_lock(&owner->guard);
	if (!use_matches_locked(owner, parent, parent_holder) || !direct_kind_valid(parent->kind)) {
		raw_spin_unlock(&owner->guard);
		return -ESTALE;
	}
	image = owner->image;
	raw_spin_unlock(&owner->guard);

	/* The exact parent retains image across this caller-serialized binding. */
	raw_spin_lock(&slot->guard);
	result = !slot->closing && !slot->update &&
		rcu_dereference_protected(slot->image, lockdep_is_held(&slot->guard)) == image ?
		0 : -ESTALE;
	raw_spin_unlock(&slot->guard);
	if (result)
		return result;
	raw_spin_lock(&owner->guard);
	if (!use_matches_locked(owner, parent, parent_holder) || !direct_kind_valid(parent->kind)) {
		result = -ESTALE;
		goto unlock;
	}
	list_for_each_entry(other, &owner->users, owner_link)
		if (other->kind == KD_JIT_IMAGE_OWNER_USE_PUBLISHED_SLOT && other->slot == slot) {
			result = -EEXIST;
			goto unlock;
		}
	result = link_use_locked(owner, published, published_holder,
				 KD_JIT_IMAGE_OWNER_USE_PUBLISHED_SLOT, slot);
	if (!result)
		owner->ever_published = true;
unlock:
	raw_spin_unlock(&owner->guard);
	return result;
}

struct retiring_slot {
	struct kd_jit_image_owner *owner;
	struct kd_jit_image_slot *slot;
	const struct kd_jit_image *image;
};

static int retiring_slot_get(struct kd_jit_image_owner_use *use, const void *holder,
		struct kd_jit_image_update *update, const void *identity, bool prepared,
		struct retiring_slot *binding)
{
	struct kd_jit_image_owner *owner = READ_ONCE(use->owner);
	int result = 0;

	if (!owner)
		return -ESTALE;
	raw_spin_lock(&owner->guard);
	if (!use_matches_locked(owner, use, holder) ||
	    use->kind != KD_JIT_IMAGE_OWNER_USE_PUBLISHED_SLOT || !use->slot ||
	    (prepared ? (use->retire_update != update || use->retire_identity != identity) :
			(use->retire_update || use->retire_identity))) {
		result = -ESTALE;
	} else {
		binding->owner = owner;
		binding->slot = use->slot;
		binding->image = owner->image;
	}
	raw_spin_unlock(&owner->guard);
	return result;
}

static bool update_matches(struct retiring_slot *binding, struct kd_jit_image_update *update,
		const void *identity, enum kd_jit_image_update_phase phase)
{
	struct kd_jit_image_slot *slot = binding->slot;
	const struct kd_jit_image *current_image;
	bool valid;

	raw_spin_lock(&slot->guard);
	current_image = rcu_dereference_protected(slot->image, lockdep_is_held(&slot->guard));
	valid = update->slot == slot && update->owner_identity == identity &&
		update->expected_old == binding->image && update->candidate != binding->image &&
		update->phase == phase;
	if (phase == KD_JIT_IMAGE_UPDATE_CLOSING)
		valid = valid && slot->closing && slot->update == update &&
			current_image == binding->image;
	else
		valid = valid && !slot->closing && !slot->update &&
			current_image == (phase == KD_JIT_IMAGE_UPDATE_COMMITTED ?
					 update->candidate : binding->image);
	raw_spin_unlock(&slot->guard);
	return valid;
}

int kd_jit_image_owner_retire_prepare(struct kd_jit_image_owner_use *published,
		const void *published_holder, struct kd_jit_image_update *update,
		const void *update_identity)
{
	struct retiring_slot binding;
	int result;

	if (!published || !published_holder || !update || !update_identity)
		return -EINVAL;
	result = retiring_slot_get(published, published_holder, update, update_identity, false, &binding);
	if (result)
		return result;
	if (!update_matches(&binding, update, update_identity, KD_JIT_IMAGE_UPDATE_CLOSING))
		return -ESTALE;
	raw_spin_lock(&binding.owner->guard);
	if (!use_matches_locked(binding.owner, published, published_holder) ||
	    published->slot != binding.slot || published->retire_update || published->retire_identity)
		result = -ESTALE;
	else {
		published->retire_update = update;
		published->retire_identity = update_identity;
		result = 0;
	}
	raw_spin_unlock(&binding.owner->guard);
	return result;
}

int kd_jit_image_owner_retire_abort(struct kd_jit_image_owner_use *published,
		const void *published_holder, struct kd_jit_image_update *update,
		const void *update_identity)
{
	struct retiring_slot binding;
	int result;

	if (!published || !published_holder || !update || !update_identity)
		return -EINVAL;
	result = retiring_slot_get(published, published_holder, update, update_identity, true, &binding);
	if (result)
		return result;
	if (!update_matches(&binding, update, update_identity, KD_JIT_IMAGE_UPDATE_ABORTED))
		return -ESTALE;
	raw_spin_lock(&binding.owner->guard);
	if (!use_matches_locked(binding.owner, published, published_holder) ||
	    published->slot != binding.slot || published->retire_update != update ||
	    published->retire_identity != update_identity)
		result = -ESTALE;
	else {
		published->retire_update = NULL;
		published->retire_identity = NULL;
		result = 0;
	}
	raw_spin_unlock(&binding.owner->guard);
	return result;
}

int kd_jit_image_owner_retire_finish(struct kd_jit_image_owner_use *published,
		const void *published_holder, struct kd_jit_image_update *update,
		const void *update_identity, const struct kd_jit_image *retired)
{
	struct retiring_slot binding;
	int result;

	if (!published || !published_holder || !update || !update_identity || !retired)
		return -EINVAL;
	result = retiring_slot_get(published, published_holder, update, update_identity, true, &binding);
	if (result)
		return result;
	if (retired != binding.image ||
	    !update_matches(&binding, update, update_identity, KD_JIT_IMAGE_UPDATE_COMMITTED))
		return -ESTALE;
	raw_spin_lock(&binding.owner->guard);
	if (!use_matches_locked(binding.owner, published, published_holder) ||
	    published->slot != binding.slot || published->retire_update != update ||
	    published->retire_identity != update_identity)
		result = -ESTALE;
	else {
		unlink_use_locked(published);
		result = 0;
	}
	/* After unlink only independently retained owner control is accessed. */
	raw_spin_unlock(&binding.owner->guard);
	return result;
}

int kd_jit_image_owner_cancel_unpublished(struct kd_jit_image_owner *owner)
{
	int result = 0;

	if (!owner)
		return -EINVAL;
	raw_spin_lock(&owner->guard);
	if (owner->ever_published)
		result = -EBUSY;
	else if (owner->phase != KD_JIT_IMAGE_OWNER_OPEN)
		result = -EALREADY;
	else
		owner->phase = KD_JIT_IMAGE_OWNER_CLOSED;
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_jit_image_owner_close(struct kd_jit_image_owner *owner)
{
	int result = 0;

	if (!owner)
		return -EINVAL;
	raw_spin_lock(&owner->guard);
	if (owner->phase != KD_JIT_IMAGE_OWNER_OPEN)
		result = -EALREADY;
	else
		owner->phase = KD_JIT_IMAGE_OWNER_CLOSED;
	raw_spin_unlock(&owner->guard);
	return result;
}

int kd_jit_image_owner_try_release(struct kd_jit_image_owner *owner)
{
	struct kd_jit_source_use *source_use;
	struct kd_jit_feedback_producer_use *producer_use;
	kd_jit_image_code_release_fn release;
	const void *source_holder;
	void *lease;
	int result = 0;

	if (!owner)
		return -EINVAL;
	raw_spin_lock(&owner->guard);
	if (owner->phase == KD_JIT_IMAGE_OWNER_RELEASE_CLAIMED)
		result = -EALREADY;
	else if (owner->phase != KD_JIT_IMAGE_OWNER_CLOSED || !list_empty(&owner->users))
		result = -EBUSY;
	raw_spin_unlock(&owner->guard);
	if (result)
		return result;
	if (!source_use_epoch(&owner->source_use, owner, KD_JIT_SOURCE_USE_IMAGE))
		return -EUCLEAN;
	raw_spin_lock(&owner->guard);
	if (owner->phase == KD_JIT_IMAGE_OWNER_RELEASE_CLAIMED)
		result = -EALREADY;
	else if (owner->phase != KD_JIT_IMAGE_OWNER_CLOSED || !list_empty(&owner->users))
		result = -EBUSY;
	else if (!owner->code_lease || !owner->code_release)
		result = -EUCLEAN;
	if (result) {
		raw_spin_unlock(&owner->guard);
		return result;
	}
	release = owner->code_release;
	lease = owner->code_lease;
	source_use = &owner->source_use;
	producer_use = &owner->producer_use;
	source_holder = owner;
	owner->code_release = NULL;
	owner->code_lease = NULL;
	owner->phase = KD_JIT_IMAGE_OWNER_RELEASE_CLAIMED;
	raw_spin_unlock(&owner->guard);

	/* Callback/control backing is separately retained through both operations.
	 * No image, inputs or code-provider payload is sampled after this callback.
	 */
	release(lease);
	result = kd_jit_feedback_producer_use_put(producer_use, source_holder);
	if (result)
		return result;
	return kd_jit_source_use_put(source_use, source_holder);
}
