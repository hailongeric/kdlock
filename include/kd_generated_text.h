/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_GENERATED_TEXT_H
#define KD_GENERATED_TEXT_H

#include <linux/types.h>

struct module;

#define KD_GENERATED_TEXT_ABI_VERSION 1U

enum kd_generated_text_kind {
	KD_GENERATED_TEXT_CORE_ITS = 1,
	KD_GENERATED_TEXT_MODULE_ITS = 2,
};

/* The producer owns one complete PAGE_SIZE-aligned executable page. Core pages
 * remain resident for the boot. Module pages remain resident while owner has a
 * reference; they need not appear in the module's ordinary memory regions. */
struct kd_generated_text_extent {
	unsigned long start;
	unsigned long end;
	struct module *owner;
	u32 abi;
	u32 kind;
};

/* Built-in producer query, also callable under a raw IRQ-preserving guard.
 * No allocation or sleeping is permitted. Success is zero and covers address;
 * CORE_ITS requires owner == NULL, MODULE_ITS requires a live owner reference.
 * Every non-NULL owner in a successful reply transfers exactly one reference,
 * including a reply rejected by the consumer. Failure transfers no reference.
 * Neither executable mappings nor matching instruction bytes supply membership. */
int kd_generated_text_lookup(unsigned long address,
			     struct kd_generated_text_extent *extent);

#endif
