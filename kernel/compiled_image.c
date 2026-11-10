// SPDX-License-Identifier: GPL-2.0-only
/* Load original generated machine code into a fresh retained executable image. */
#include <linux/bug.h>
#include <linux/errno.h>
#include <linux/execmem.h>
#include <linux/limits.h>
#include <linux/overflow.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <asm/page.h>
#include <asm/set_memory.h>

#include "compiled_image.h"

struct kd_jit_compiled_image {
	struct kd_jit_control_image control;
	struct kd_jit_image image;
	struct kd_jit_image_inputs inputs;
	struct kd_jit_feedback_emission_receipt emission;
	struct kd_jit_source_epoch *epoch;
	struct kd_jit_compiled_image_limits limits;
	struct kd_jit_control_bytes symbols[4];
	unsigned long *entries;
	struct kd_jit_source_site *sites;
	struct kd_jit_image_source_bytes *source_bytes;
	struct kd_jit_feedback_emission *observations;
	unsigned char *artifacts;
	unsigned char *flat;
	void *code;
	size_t lengths[5];
	bool accepted;
	bool loaded;
	bool code_released;
};

struct flat_reader { const unsigned char *data; size_t left; };

static bool take(struct flat_reader *reader, u64 *value)
{
	unsigned int index;

	if (reader->left < 8)
		return false;
	*value = 0;
	for (index = 0; index < 8; ++index)
		*value |= (u64)reader->data[index] << (index * 8);
	reader->data += 8;
	reader->left -= 8;
	return true;
}

static bool identifier(const struct kd_jit_control_bytes *symbol)
{
	const unsigned char *text = symbol->data;
	size_t index;

	if (!text || !symbol->length)
		return false;
	for (index = 0; index < symbol->length; ++index) {
		unsigned char byte = text[index];

		if (!((byte >= 'a' && byte <= 'z') || (byte >= 'A' && byte <= 'Z') ||
		      byte == '_' || (index && byte >= '0' && byte <= '9')))
			return false;
	}
	return true;
}

static void free_backing(struct kd_jit_compiled_image *image)
{
	unsigned int index;

	for (index = 0; index < 4; ++index)
		kfree(image->symbols[index].data);
	kvfree(image->entries);
	kvfree(image->sites);
	kvfree(image->source_bytes);
	kvfree(image->observations);
	kvfree(image->artifacts);
	kvfree(image->flat);
	kfree(image);
}

static void release_code(void *lease)
{
	struct kd_jit_compiled_image *image = lease;
	void *code;

	BUG_ON(!image || image->code_released || !image->code);
	code = image->code;
	image->code = NULL;
	image->code_released = true;
	/* Durable controls remain independently held. No payload read follows. */
	execmem_free(code);
}

int kd_jit_compiled_image_reserve(struct kd_jit_source_epoch *epoch,
		const struct kd_jit_compiled_image_limits *limits,
		const struct kd_jit_compiled_image_symbols *symbols,
		struct kd_jit_compiled_image **out,
		struct kd_jit_control_candidate *candidate)
{
	const struct kd_jit_control_bytes *names[4];
	struct kd_jit_compiled_image *image;
	unsigned int index, other;
	int result;

	if (!out)
		return -EINVAL;
	*out = NULL;
	if (!epoch || !limits || !symbols || !candidate || !limits->code_capacity ||
	    (limits->code_capacity & (PAGE_SIZE - 1)) ||
	    (limits->code_capacity >> PAGE_SHIFT) > INT_MAX ||
	    !limits->artifact_capacity || !limits->flat_capacity || !limits->entry_capacity)
		return -EINVAL;
	names[0] = &symbols->descriptor;
	names[1] = &symbols->source;
	names[2] = &symbols->producer;
	names[3] = &symbols->entry;
	for (index = 0; index < 4; ++index) {
		if (!identifier(names[index]))
			return -EINVAL;
		for (other = 0; other < index; ++other)
			if (names[index]->length == names[other]->length &&
			    !memcmp(names[index]->data, names[other]->data, names[index]->length))
				return -EINVAL;
	}
	image = kmalloc(sizeof(*image), GFP_KERNEL);
	if (!image)
		return -ENOMEM;
	image->epoch = epoch;
	image->limits = *limits;
	image->entries = NULL;
	image->sites = NULL;
	image->source_bytes = NULL;
	image->observations = NULL;
	image->artifacts = NULL;
	image->flat = NULL;
	image->code = NULL;
	image->accepted = false;
	image->loaded = false;
	image->code_released = false;
	for (index = 0; index < 4; ++index)
		image->symbols[index].data = NULL;
	kd_jit_control_image_init(&image->control);
	for (index = 0; index < 4; ++index) {
		image->symbols[index].data = kmemdup(names[index]->data, names[index]->length, GFP_KERNEL);
		image->symbols[index].length = names[index]->length;
		if (!image->symbols[index].data)
			goto no_memory;
	}
	image->entries = kvmalloc_array(limits->entry_capacity, sizeof(*image->entries), GFP_KERNEL);
	if (limits->source_capacity) {
		image->sites = kvmalloc_array(limits->source_capacity, sizeof(*image->sites), GFP_KERNEL);
		image->source_bytes = kvmalloc_array(limits->source_capacity,
						 sizeof(*image->source_bytes), GFP_KERNEL);
	}
	if (limits->observation_capacity)
		image->observations = kvmalloc_array(limits->observation_capacity,
						 sizeof(*image->observations), GFP_KERNEL);
	image->artifacts = kvmalloc(limits->artifact_capacity, GFP_KERNEL);
	image->flat = kvmalloc(limits->flat_capacity, GFP_KERNEL);
	if (!image->entries || !image->artifacts || !image->flat ||
	    (limits->source_capacity && (!image->sites || !image->source_bytes)) ||
	    (limits->observation_capacity && !image->observations))
		goto no_memory;
	image->code = execmem_alloc_rw(EXECMEM_DEFAULT, limits->code_capacity);
	if (!image->code)
		goto no_memory;
	result = set_memory_nx((unsigned long)image->code, limits->code_capacity >> PAGE_SHIFT);
	if (result)
		goto fail_code;
	result = set_memory_rw((unsigned long)image->code, limits->code_capacity >> PAGE_SHIFT);
	if (result)
		goto fail_code;
	/* Unused capacity contains explicit stop instructions, never old bytes. */
	memset(image->code, 0xcc, limits->code_capacity);
	image->image.source_identity = epoch;
	image->image.feedback_producer = &image->control.producer;
	image->image.abi_version = KD_JIT_ABI_VERSION;
	image->image.packet_size = sizeof(struct kd_regs);
	image->image.io_size = sizeof(struct kd_jit_io);
	image->image.entry = (kd_jit_entry_fn)image->code;
	image->image.entry_sites = image->entries;
	image->image.entry_count = 0;
	image->image.source_sites = NULL;
	image->image.source_count = 0;
	image->inputs.image = &image->image;
	image->inputs.source_version = NULL;
	image->inputs.source_version_length = 0;
	image->inputs.current_task_gs_offset = 0;
	image->inputs.source_bytes = NULL;
	image->inputs.source_count = 0;
	image->emission.inputs = &image->inputs;
	image->emission.observations = NULL;
	image->emission.observation_count = 0;
	candidate->control = &image->control;
	candidate->image = &image->image;
	candidate->inputs = &image->inputs;
	candidate->emission = &image->emission;
	candidate->code_base = (unsigned long)image->code;
	candidate->code_capacity = limits->code_capacity;
	candidate->descriptor_symbol = image->symbols[0];
	candidate->source_symbol = image->symbols[1];
	candidate->producer_symbol = image->symbols[2];
	candidate->entry_symbol = image->symbols[3];
	candidate->code_lease = image;
	candidate->code_release = release_code;
	*out = image;
	return 0;
no_memory:
	result = -ENOMEM;
	goto fail;
fail_code:
	execmem_free(image->code);
fail:
	free_backing(image);
	return result;
}

unsigned long kd_jit_compiled_image_code_base(struct kd_jit_compiled_image *image)
{
	return image ? (unsigned long)image->code : 0;
}

size_t kd_jit_compiled_image_code_capacity(struct kd_jit_compiled_image *image)
{
	return image ? image->limits.code_capacity : 0;
}

struct kd_jit_control_image *kd_jit_compiled_image_control(struct kd_jit_compiled_image *image)
{
	return image ? &image->control : NULL;
}

static bool source_match(struct kd_jit_source_epoch *epoch, unsigned long ip,
			 const unsigned char *bytes, unsigned int length)
{
	unsigned int offset, index;

	for (offset = 0; offset < length; ++offset) {
		unsigned long address = ip + offset;
		bool found = false;

		for (index = 0; index < epoch->description.region_count; ++index) {
			const struct kd_jit_source_region *region = &epoch->description.regions[index];

			if (address >= region->start && address - region->start < region->length) {
				if (region->bytes[address - region->start] != bytes[offset])
					return false;
				found = true;
				break;
			}
		}
		if (!found)
			return false;
	}
	return true;
}

static int parse_flat(struct kd_jit_compiled_image *image, size_t length)
{
	struct flat_reader reader = { image->flat, length };
	u64 header[9], row[4], value;
	unsigned int index, other, item;

	for (index = 0; index < 9; ++index)
		if (!take(&reader, &header[index]))
			return -EINVAL;
	if (header[0] != KD_JIT_FLAT_IMAGE_ABI || header[1] != KD_JIT_ABI_VERSION ||
	    header[2] != sizeof(struct kd_regs) || header[3] != sizeof(struct kd_jit_io) ||
	    header[4] != image->epoch->description.current_task_gs_offset ||
	    !header[5] || header[5] > image->limits.entry_capacity ||
	    header[6] > image->limits.source_capacity ||
	    header[7] > image->limits.observation_capacity ||
	    !header[8] || header[8] > reader.left ||
	    header[8] != image->epoch->description.version_length ||
	    memcmp(reader.data, image->epoch->description.version, header[8]))
		return -EINVAL;
	image->inputs.source_version = reader.data;
	image->inputs.source_version_length = header[8];
	image->inputs.current_task_gs_offset = header[4];
	reader.data += header[8];
	reader.left -= header[8];
	for (index = 0; index < header[5]; ++index) {
		if (!take(&reader, &value))
			return -EINVAL;
		for (other = 0; other < index; ++other)
			if (image->entries[other] == value)
				return -EINVAL;
		image->entries[index] = value;
	}
	for (index = 0; index < header[6]; ++index) {
		for (item = 0; item < 4; ++item)
			if (!take(&reader, &row[item]))
				return -EINVAL;
		if (row[2] > KD_JIT_SITE_OTHER || !row[3] || row[3] > 15 ||
		    row[3] > reader.left || row[0] > ~0UL - row[3] ||
		    row[1] != row[0] + row[3] ||
		    !source_match(image->epoch, row[0], reader.data, row[3]))
			return -EINVAL;
		for (other = 0; other < index; ++other)
			if (image->sites[other].ip == row[0])
				return -EINVAL;
		image->sites[index].ip = row[0];
		image->sites[index].next_ip = row[1];
		image->sites[index].kind = row[2];
		image->source_bytes[index].ip = row[0];
		image->source_bytes[index].bytes = reader.data;
		image->source_bytes[index].length = row[3];
		reader.data += row[3];
		reader.left -= row[3];
	}
	for (index = 0; index < header[7]; ++index) {
		bool source = false, target = false;

		for (item = 0; item < 4; ++item)
			if (!take(&reader, &row[item]))
				return -EINVAL;
		if (row[2] > KD_JIT_FEEDBACK_TRANSFER_JUMP ||
		    row[3] > KD_JIT_FEEDBACK_EMISSION_DISPATCH_NOT_EMITTED)
			return -EINVAL;
		for (other = 0; other < index; ++other)
			if (image->observations[other].source_ip == row[0] &&
			    image->observations[other].target == row[1] &&
			    image->observations[other].kind == row[2])
				return -EINVAL;
		if (row[3] == KD_JIT_FEEDBACK_EMISSION_EMITTED) {
			for (other = 0; other < header[6]; ++other) {
				if (image->sites[other].ip == row[0])
					source = image->sites[other].kind ==
						(row[2] == KD_JIT_FEEDBACK_TRANSFER_CALL ?
						 KD_JIT_SITE_CALL : KD_JIT_SITE_JUMP);
				if (image->sites[other].ip == row[1])
					target = true;
			}
			if (!source || !target)
				return -EINVAL;
		}
		image->observations[index].source_ip = row[0];
		image->observations[index].target = row[1];
		image->observations[index].kind = row[2];
		image->observations[index].outcome = row[3];
	}
	if (reader.left)
		return -EINVAL;
	image->image.entry_count = header[5];
	image->image.source_count = header[6];
	image->image.source_sites = header[6] ? image->sites : NULL;
	image->inputs.source_count = header[6];
	image->inputs.source_bytes = header[6] ? image->source_bytes : NULL;
	image->emission.observation_count = header[7];
	image->emission.observations = header[7] ? image->observations : NULL;
	return 0;
}

static int finish_permissions(struct kd_jit_compiled_image *image)
{
	int result;
	int pages = image->limits.code_capacity >> PAGE_SHIFT;

	/* execmem_restore_rox is a stub without ARCH_HAS_EXECMEM_ROX; use actual
	 * x86 page permissions in that configuration rather than trusting the stub.
	 */
	if (IS_ENABLED(CONFIG_ARCH_HAS_EXECMEM_ROX))
		return execmem_restore_rox(image->code, image->limits.code_capacity);
	result = set_memory_ro((unsigned long)image->code, pages);
	if (result)
		return result;
	return set_memory_x((unsigned long)image->code, pages);
}

int kd_jit_compiled_image_load(struct kd_jit_compiled_image *image,
		const struct kd_jit_control_bytes *assembly,
		const struct kd_jit_control_bytes *metadata,
		const struct kd_jit_control_bytes *manifest,
		const struct kd_jit_control_bytes *code,
		const struct kd_jit_control_bytes *flat)
{
	const struct kd_jit_control_bytes *blobs[5] = { assembly, metadata, manifest, code, flat };
	size_t artifact_bytes = 0, offset = 0;
	unsigned int index;
	int result;

	if (!image || image->code_released || !image->code)
		return -ESTALE;
	for (index = 0; index < 5; ++index)
		if (!blobs[index] || !blobs[index]->data || !blobs[index]->length)
			return -EINVAL;
	for (index = 0; index < 3; ++index)
		if (check_add_overflow(artifact_bytes, blobs[index]->length, &artifact_bytes))
			return -EOVERFLOW;
	if (artifact_bytes > image->limits.artifact_capacity ||
	    code->length > image->limits.code_capacity || flat->length > image->limits.flat_capacity)
		return -ENOSPC;
	if (image->accepted) {
		for (index = 0; index < 5; ++index)
			if (image->lengths[index] != blobs[index]->length)
				return -ESTALE;
		for (index = 0; index < 3; ++index) {
			if (memcmp(image->artifacts + offset, blobs[index]->data, blobs[index]->length))
				return -ESTALE;
			offset += blobs[index]->length;
		}
		if (memcmp(image->flat, flat->data, flat->length) ||
		    memcmp(image->code, code->data, code->length))
			return -ESTALE;
		if (image->loaded)
			return 0;
	} else {
		for (index = 0; index < 3; ++index) {
			memcpy(image->artifacts + offset, blobs[index]->data, blobs[index]->length);
			offset += blobs[index]->length;
		}
		memcpy(image->flat, flat->data, flat->length);
		result = parse_flat(image, flat->length);
		if (result)
			return result;
		for (index = 0; index < 5; ++index)
			image->lengths[index] = blobs[index]->length;
		/* No fallible operation occurs between accepting and this sole copy. */
		image->accepted = true;
		memcpy(image->code, code->data, code->length);
	}
	result = finish_permissions(image);
	if (result)
		return result;
	image->loaded = true;
	return 0;
}

int kd_jit_compiled_image_destroy(struct kd_jit_compiled_image *image)
{
	if (!image)
		return -EINVAL;
	if (!image->code_released || image->control.published_live ||
	    (image->control.owner_initialized && !image->control.owner_released) ||
	    (image->control.producer_initialized && !image->control.producer_released))
		return -EBUSY;
	free_backing(image);
	return 0;
}
