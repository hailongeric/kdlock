/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_IMAGE_H
#define KD_IMAGE_H
#include "exe_info.h"

/* Construct privately, then publish once. Published descriptors and executable
 * blocks survive every frame/continuation until terminal session teardown. */
struct kd_jit_image {
	void *code;
	unsigned long length;
	unsigned long generation;
	unsigned int requirements;
	unsigned int entry_abi;
	struct kd_exe_info *entry;
	/* Initial spin images retain historical in-place updates. Once a guarded
	 * generation is published, this entry only publishes immutable images. */
	unsigned int immutable;
};

#define KD_ADDRESS_GUARD_MAX 64U
#define KD_ADDRESS_GUARD_PROOF 1U
struct kd_address_guard_site {
	unsigned long ip;
	unsigned char length;
	unsigned char proof;
	unsigned char reserved[6];
	unsigned char opcode[16];
} __attribute__((packed));
struct kd_address_guard_footer {
	unsigned char magic[8];
	unsigned int offset;
	unsigned int count;
} __attribute__((packed));

/* The bounded trailer is part of the immutable image, never a userspace
 * pointer. x86-64 is the negotiated provider architecture and byte order. */
static inline const struct kd_address_guard_site *
kd_image_guard_sites(const struct kd_jit_image *image, unsigned int *count)
{
	const unsigned char *code;
	const struct kd_address_guard_footer *footer;

	if (!image || !image->code ||
	    image->length < KD_IMAGE_HEADER_SIZE + sizeof(*footer) ||
	    !(image->requirements & KD_IMAGE_REQUIRE_ADDRESS_GUARD))
		return 0;
	code = image->code;
	footer = (const void *)(code + image->length - sizeof(*footer));
	if (__builtin_memcmp(footer->magic, "KDAG0001", 8) ||
	    !footer->count || footer->count > KD_ADDRESS_GUARD_MAX ||
	    footer->offset < KD_IMAGE_HEADER_SIZE ||
	    (unsigned long)footer->offset +
		footer->count * sizeof(struct kd_address_guard_site) !=
		image->length - sizeof(*footer))
		return 0;
	*count = footer->count;
	return (const void *)(code + footer->offset);
}

static inline int kd_image_guard_site_valid(const struct kd_address_guard_site *site)
{
	unsigned int i, mod, base, length = 3;

	/* Only the reviewed REX.W MOV memory-load family has a guard proof. */
	if (!site->ip || site->length < 3 || site->length > 8 ||
	    site->ip > ~0UL - site->length || site->proof != KD_ADDRESS_GUARD_PROOF ||
	    (site->opcode[0] & 0xf8) != 0x48 || site->opcode[1] != 0x8b ||
	    (site->opcode[2] & 0xc0) == 0xc0)
		return 0;
	mod = site->opcode[2] >> 6;
	base = site->opcode[2] & 7;
	if (base == 4) {
		/* SIB encoding is necessary for RSP/R12 even without an index.
		 * An actual index, RIP-relative or absolute address is outside
		 * this guard's single-source-register proof contract. */
		if (site->length < 4 || (site->opcode[0] & 2) ||
		    ((site->opcode[3] >> 3) & 7) != 4)
			return 0;
		base = site->opcode[3] & 7;
		length++;
	}
	if (!mod && base == 5)
		return 0;
	length += mod == 1 ? 1 : mod == 2 ? 4 : 0;
	if (site->length != length)
		return 0;
	for (i = 0; i < sizeof(site->reserved); i++)
		if (site->reserved[i])
			return 0;
	for (i = site->length; i < sizeof(site->opcode); i++)
		if (site->opcode[i])
			return 0;
	return 1;
}

struct kd_image_upload {
	struct kd_jit_image *image;
	void *code; /* destination fixed by the first chunk, including old spin */
	struct kd_recv_pkt identity;
	unsigned long covered;
};

struct kd_jit_image *kd_image_alloc(void);
void kd_image_discard(struct kd_jit_image *image);
int kd_image_validate_address_guards(const struct kd_jit_image *image);
int kd_image_publish(struct kd_exe_info *entry, struct kd_jit_image *image,
		     unsigned long base_generation);
int kd_image_publish_mutable(struct kd_exe_info *entry, void *code,
			     unsigned long length);
const struct kd_jit_image *kd_image_current(const struct kd_exe_info *entry);
void kd_image_report(struct kd_exe_info *entry, const struct kd_jit_image *image,
		     int status, unsigned long target, unsigned long from);
/* Terminal for this stable entry, including markers from an older image. */
void kd_image_disable(struct kd_exe_info *entry);
void kd_exe_snapshot(const struct kd_exe_info *entry, struct kd_exe_info *snapshot);
#endif
