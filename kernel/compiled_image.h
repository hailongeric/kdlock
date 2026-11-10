/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_COMPILED_IMAGE_H
#define KDLOCK_COMPILED_IMAGE_H

#include "control.h"

#define KD_JIT_FLAT_IMAGE_ABI 1UL

struct kd_jit_compiled_image;

/* Exact caller capacities; code_capacity is a nonzero page multiple and its
 * page count fits int. artifact_capacity covers assembly+C metadata+manifest;
 * flat_capacity covers the entire typed metadata blob. Tables are separately
 * bounded, with entries nonzero; zero source/observation capacity is allowed.
 * All allocation is cold, outside source execution. No defaults are supplied.
 */
struct kd_jit_compiled_image_limits {
	size_t code_capacity;
	size_t artifact_capacity;
	size_t flat_capacity;
	unsigned int entry_capacity;
	unsigned int source_capacity;
	unsigned int observation_capacity;
};

struct kd_jit_compiled_image_symbols {
	struct kd_jit_control_bytes descriptor;
	struct kd_jit_control_bytes source;
	struct kd_jit_control_bytes producer;
	struct kd_jit_control_bytes entry;
};

/* Serialized sleepable provider constructor under a live exact epoch BUILD
 * hold. Reserve actual executable memory with execmem_alloc_rw, force NX/RW,
 * and reserve durable descriptor/inputs/receipt/control addresses before build.
 * Copy the four distinct ASCII identifiers into retained storage. Success
 * transfers the actual code hold in candidate; failure transfers nothing.
 * Caller retains epoch, provider/callback and all controls through observers.
 * This grants no source, image-slot or publication admission.
 */
int kd_jit_compiled_image_reserve(struct kd_jit_source_epoch *epoch,
		const struct kd_jit_compiled_image_limits *limits,
		const struct kd_jit_compiled_image_symbols *symbols,
		struct kd_jit_compiled_image **out,
		struct kd_jit_control_candidate *candidate);
unsigned long kd_jit_compiled_image_code_base(struct kd_jit_compiled_image *image);
size_t kd_jit_compiled_image_code_capacity(struct kd_jit_compiled_image *image);
struct kd_jit_control_image *kd_jit_compiled_image_control(struct kd_jit_compiled_image *image);

/* Kernel buffers only, disjoint from this provider's mutable/code backing.
 * Actual host tools must have linked the ORIGINAL generated assembly at the
 * reserved code base, with entry offset zero, no unresolved relocations or
 * extra allocated sections. Assembly/C/manifest, code and flat metadata must
 * all belong to that same actual construction. This loader does no C parsing,
 * decoding, assembly, relocation or instruction-equivalence proof.
 *
 * Flat wire layout: nine LE u64 words [format ABI, image ABI, packet size, IO
 * size, GS offset, entry count, source count, observation count, version length];
 * raw version; entry source-IP words; each source row [IP,next IP,kind,length]
 * then its 1..15 raw bytes; observation rows [site,target,transfer,outcome].
 * No padding/trailing bytes. Kinds/outcomes are exact current C enum values.
 *
 * Validate finite typed metadata/epoch bytes before code effects. Retain all
 * five input blobs, copy code once, then establish RO/X permissions. A later
 * error retains the exact reservation; only identical input may finish a
 * permission retry. Successful repeats perform no code write. Old code is not
 * patched in place. Publish only after success and normal owner validation.
 */
int kd_jit_compiled_image_load(struct kd_jit_compiled_image *image,
		const struct kd_jit_control_bytes *assembly,
		const struct kd_jit_control_bytes *metadata,
		const struct kd_jit_control_bytes *manifest,
		const struct kd_jit_control_bytes *code,
		const struct kd_jit_control_bytes *flat);

/* Final control destruction, not code retirement. Code release is performed
 * only by candidate.code_release (private abort or the exact owner finalizer).
 * It frees execmem independently of late FACT users. This function refuses
 * still-live code/owner/producer controls; caller additionally ended EVERY host,
 * channel, cycle, receipt, callback and raw identity observer before this call.
 * Complete collection APIs before destroy; release phase alone is not proof of
 * their return. All calls are provider-serialized, with no concurrent finalizer.
 */
int kd_jit_compiled_image_destroy(struct kd_jit_compiled_image *image);

#endif
