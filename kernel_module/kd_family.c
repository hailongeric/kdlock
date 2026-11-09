// SPDX-License-Identifier: GPL-2.0
/* Root-owned family identity, exact service references and a small immutable
 * reached-instruction cache. No executable arena, allocation or global gate is
 * involved. Source residency and freshly observed bytes remain caller-owned. */
#include <linux/errno.h>
#include <linux/string.h>
#include "kd_family.h"

static bool family_identity(const struct kd_family *family,
	const void *identity, u64 generation)
{
	return family->identity == identity && family->generation == generation &&
		identity && generation && family->source_epoch;
}

static bool family_reference_locked(const struct kd_family *family,
	const struct kd_family_ref *reference)
{
	const struct kd_family_ref *member;

	if (!reference || !reference->held || reference->family != family ||
	    reference->family_generation != family->generation ||
	    !reference->request_identity || !reference->request_generation ||
	    (family->state != KD_FAMILY_ACTIVE &&
	     family->state != KD_FAMILY_DRAINING))
		return false;
	list_for_each_entry(member, &family->references, link)
		if (member == reference)
			return true;
	return false;
}

int kd_family_init(struct kd_family *family, const void *identity,
	u64 generation, u64 source_epoch, unsigned long entry_ip,
	unsigned int entry_abi)
{
	if (!family || !identity || !generation || !source_epoch ||
	    !entry_ip || !entry_abi)
		return -EINVAL;
	/* Fresh/retired storage only. Old instruction bytes need not be cleared:
	 * cached is reset before any new reference can read an old record. */
	raw_spin_lock_init(&family->guard);
	INIT_LIST_HEAD(&family->references);
	family->identity = identity;
	family->generation = generation;
	family->source_epoch = source_epoch;
	family->entry_ip = entry_ip;
	family->entry_abi = entry_abi;
	family->state = KD_FAMILY_ACTIVE;
	family->cached = 0;
	family->cache_hits = 0;
	family->cache_misses = 0;
	return 0;
}

void kd_family_ref_init(struct kd_family_ref *reference)
{
	INIT_LIST_HEAD(&reference->link);
	reference->family = NULL;
	reference->family_generation = 0;
	reference->request_identity = NULL;
	reference->request_generation = 0;
	reference->sequence = 0;
	reference->held = false;
}

int kd_family_ref_get(struct kd_family *family,
	struct kd_family_ref *reference, const struct kd_family_ref *parent,
	const void *request_identity, u64 request_generation, u64 sequence)
{
	unsigned long flags;
	int result = -EINVAL;

	if (!family || !reference || !request_identity || !request_generation ||
	    parent == reference)
		return -EINVAL;
	raw_spin_lock_irqsave(&family->guard, flags);
	if (reference->held || !list_empty(&reference->link))
		goto out;
	if (family->state == KD_FAMILY_RETIRED) {
		result = -ESHUTDOWN;
		goto out;
	}
	if (parent) {
		/* Retained requests may discover a new interval while DRAINING.
		 * Exact parent membership authorizes it; a new root cannot enter. */
		if (!family_reference_locked(family, parent)) {
			result = -ESTALE;
			goto out;
		}
	} else if (family->state != KD_FAMILY_ACTIVE || sequence ||
		   !family_identity(family, request_identity, request_generation)) {
		result = family->state == KD_FAMILY_DRAINING ? -ESHUTDOWN : -ESTALE;
		goto out;
	}
	reference->family = family;
	reference->family_generation = family->generation;
	reference->request_identity = request_identity;
	reference->request_generation = request_generation;
	reference->sequence = sequence;
	list_add_tail(&reference->link, &family->references);
	reference->held = true;
	result = 0;
out:
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return result;
}

int kd_family_ref_put(struct kd_family_ref *reference)
{
	struct kd_family *family;
	unsigned long flags;
	int result = -ESTALE;

	if (!reference || !READ_ONCE(reference->held))
		return -EINVAL;
	family = READ_ONCE(reference->family);
	if (!family)
		return -EINVAL;
	raw_spin_lock_irqsave(&family->guard, flags);
	if (family_reference_locked(family, reference)) {
		list_del_init(&reference->link);
		reference->held = false;
		/* Keep retired identity fields for diagnostics. The held bit closes
		 * their authority; an old observer must not follow a freed family. */
		result = 0;
	}
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return result;
}

bool kd_family_ref_valid(const struct kd_family_ref *reference)
{
	struct kd_family *family;
	unsigned long flags;
	bool valid;

	if (!reference || !READ_ONCE(reference->held))
		return false;
	family = READ_ONCE(reference->family);
	if (!family)
		return false;
	raw_spin_lock_irqsave(&family->guard, flags);
	valid = family_reference_locked(family, reference);
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return valid;
}

int kd_family_begin_retire(struct kd_family *family, const void *identity,
	u64 generation)
{
	unsigned long flags;
	int result = -ESTALE;

	if (!family)
		return -EINVAL;
	raw_spin_lock_irqsave(&family->guard, flags);
	if (family_identity(family, identity, generation)) {
		if (family->state == KD_FAMILY_RETIRED)
			result = -ESHUTDOWN;
		else {
			family->state = KD_FAMILY_DRAINING;
			result = 0;
		}
	}
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return result;
}

int kd_family_finish_retire(struct kd_family *family, const void *identity,
	u64 generation)
{
	unsigned long flags;
	int result = -ESTALE;

	if (!family)
		return -EINVAL;
	raw_spin_lock_irqsave(&family->guard, flags);
	if (family_identity(family, identity, generation)) {
		if (family->state != KD_FAMILY_DRAINING)
			result = -EINVAL;
		else if (!list_empty(&family->references))
			result = -EBUSY;
		else {
			family->state = KD_FAMILY_RETIRED;
			result = 0;
		}
	}
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return result;
}

unsigned int kd_family_live_refs(struct kd_family *family)
{
	const struct kd_family_ref *reference;
	unsigned long flags;
	unsigned int count = 0;

	if (!family)
		return 0;
	raw_spin_lock_irqsave(&family->guard, flags);
	list_for_each_entry(reference, &family->references, link)
		++count;
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return count;
}

static const struct kd_family_instruction *family_cached_locked(
	const struct kd_family *family, unsigned long source_ip,
	const u8 *observed, unsigned int length)
{
	const struct kd_family_instruction *instruction;
	unsigned int index;

	for (index = 0; index < family->cached; ++index) {
		instruction = &family->instructions[index];
		if (instruction->source_ip == source_ip && instruction->length == length &&
		    !memcmp(instruction->bytes, observed, length))
			return instruction;
	}
	return NULL;
}

const struct kd_family_instruction *kd_family_cache_find(
	const struct kd_family_ref *authority, unsigned long source_ip,
	const u8 *observed, unsigned int length)
{
	const struct kd_family_instruction *instruction = NULL;
	struct kd_family *family;
	unsigned long flags;

	if (!authority || !READ_ONCE(authority->held) || !source_ip || !observed ||
	    !length || length > KD_FAMILY_INSN_BYTES || source_ip > ~0UL - length)
		return NULL;
	family = authority->family;
	if (!family)
		return NULL;
	raw_spin_lock_irqsave(&family->guard, flags);
	if (family_reference_locked(family, authority)) {
		instruction = family_cached_locked(family, source_ip, observed, length);
		if (instruction)
			++family->cache_hits;
		else
			++family->cache_misses;
	}
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return instruction;
}

const struct kd_family_instruction *kd_family_cache_candidate(
	const struct kd_family_ref *authority, unsigned long source_ip)
{
	const struct kd_family_instruction *instruction = NULL;
	struct kd_family *family;
	unsigned long flags;
	unsigned int index;

	if (!authority || !READ_ONCE(authority->held) || !source_ip)
		return NULL;
	family = authority->family;
	if (!family)
		return NULL;
	raw_spin_lock_irqsave(&family->guard, flags);
	if (!family_reference_locked(family, authority))
		goto out;
	/* Records remain append-only. Prefer the latest observation while the
	 * caller separately proves that its full bytes are still current. */
	for (index = family->cached; index > 0; --index)
		if (family->instructions[index - 1].source_ip == source_ip) {
			instruction = &family->instructions[index - 1];
			break;
		}
out:
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return instruction;
}

const struct kd_family_instruction *kd_family_cache_publish(
	const struct kd_family_ref *authority, unsigned long source_ip,
	const u8 *observed, unsigned int length)
{
	const struct kd_family_instruction *existing;
	struct kd_family_instruction *instruction = NULL;
	struct kd_family *family;
	unsigned long flags;
	unsigned int index;

	if (!authority || !READ_ONCE(authority->held) || !source_ip || !observed ||
	    !length || length > KD_FAMILY_INSN_BYTES || source_ip > ~0UL - length)
		return NULL;
	family = authority->family;
	if (!family)
		return NULL;
	raw_spin_lock_irqsave(&family->guard, flags);
	if (!family_reference_locked(family, authority))
		goto out;
	existing = family_cached_locked(family, source_ip, observed, length);
	if (existing) {
		raw_spin_unlock_irqrestore(&family->guard, flags);
		return existing;
	}
	/* Full cache is an ordinary cold path, not a correctness failure. */
	if (family->cached == KD_FAMILY_CACHE_ENTRIES)
		goto out;
	instruction = &family->instructions[family->cached];
	instruction->source_ip = source_ip;
	instruction->generation = family->cached + 1;
	instruction->length = length;
	for (index = 0; index < length; ++index)
		instruction->bytes[index] = observed[index];
	++family->cached;
out:
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return instruction;
}

void kd_family_artifact_init(struct kd_family_artifact *artifact)
{
	kd_family_ref_init(&artifact->reference);
	artifact->source_ip = 0;
	artifact->source_epoch = 0;
	artifact->sequence = 0;
	artifact->kind = KD_FAMILY_ARTIFACT_NONE;
	artifact->length = 0;
}

int kd_family_artifact_get(struct kd_family_artifact *artifact,
	const struct kd_family_ref *parent, unsigned int kind,
	unsigned long source_ip, const u8 *bytes, unsigned int length,
	u64 sequence)
{
	unsigned int index;
	int result;

	if (!artifact || !parent || !READ_ONCE(parent->held) ||
	    !parent->family || kind <= KD_FAMILY_ARTIFACT_NONE ||
	    kind > KD_FAMILY_ARTIFACT_MEMORY || !sequence || !source_ip || !bytes ||
	    !length || length > KD_FAMILY_INSN_BYTES || source_ip > ~0UL - length ||
	    artifact->kind != KD_FAMILY_ARTIFACT_NONE)
		return -EINVAL;
	result = kd_family_ref_get(parent->family, &artifact->reference, parent,
		parent->request_identity, parent->request_generation, sequence);
	if (result)
		return result;
	artifact->source_ip = source_ip;
	artifact->source_epoch = parent->family->source_epoch;
	artifact->sequence = sequence;
	artifact->length = length;
	for (index = 0; index < length; ++index)
		artifact->bytes[index] = bytes[index];
	artifact->kind = kind;
	return 0;
}

bool kd_family_artifact_valid(const struct kd_family_artifact *artifact,
	const struct kd_family_ref *parent, u64 sequence)
{
	const struct kd_family_ref *reference;
	struct kd_family *family;
	unsigned long flags;
	bool valid;

	if (!artifact || !sequence || artifact->sequence != sequence ||
	    artifact->kind <= KD_FAMILY_ARTIFACT_NONE ||
	    artifact->kind > KD_FAMILY_ARTIFACT_MEMORY || !artifact->source_ip ||
	    !artifact->length || artifact->length > KD_FAMILY_INSN_BYTES)
		return false;
	reference = &artifact->reference;
	if (!READ_ONCE(reference->held) || !reference->family)
		return false;
	family = reference->family;
	raw_spin_lock_irqsave(&family->guard, flags);
	valid = family_reference_locked(family, reference) &&
		reference->sequence == sequence && artifact->source_epoch == family->source_epoch;
	/* The artifact owns an independent exact reference. A completed parent
	 * may retire first; compare its retained identity only, not its held bit. */
	if (valid && parent)
		valid = parent->family == family &&
			parent->family_generation == reference->family_generation &&
			parent->request_identity == reference->request_identity &&
			parent->request_generation == reference->request_generation;
	raw_spin_unlock_irqrestore(&family->guard, flags);
	return valid;
}

int kd_family_artifact_put(struct kd_family_artifact *artifact)
{
	int result;

	if (!artifact || !kd_family_artifact_valid(artifact, NULL, artifact->sequence))
		return -ESTALE;
	result = kd_family_ref_put(&artifact->reference);
	if (!result)
		artifact->kind = KD_FAMILY_ARTIFACT_NONE;
	return result;
}
