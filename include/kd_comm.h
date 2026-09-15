/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_COMM_H
#define KD_COMM_H

#include <linux/compiler.h>
#include <linux/sched.h>
#include <linux/string.h>

/* x86_64 task comm has exactly 16 readable bytes. Match through the first NUL,
 * ignoring stale bytes after it, just like strcmp. An overlong target can
 * never match. Keys are prepared once before publishing the guest selector.
 */
struct kd_comm_key {
	unsigned long value[2];
	unsigned long mask[2];
};

static inline void kd_comm_init(struct kd_comm_key *key, const char *target)
{
	size_t length, i;

	BUILD_BUG_ON(TASK_COMM_LEN != 2 * sizeof(unsigned long));
	memset(key, 0, sizeof(*key));
	if (!target)
		return;
	length = strnlen(target, TASK_COMM_LEN);
	if (length == TASK_COMM_LEN)
		return;
	for (i = 0; i <= length; i++) {
		unsigned int shift = (i % sizeof(unsigned long)) * 8;
		key->mask[i / sizeof(unsigned long)] |= 0xffUL << shift;
		key->value[i / sizeof(unsigned long)] |=
			(unsigned long)(unsigned char)target[i] << shift;
	}
}

static __always_inline bool
kd_comm_matches(const struct kd_comm_key *key, const char comm[TASK_COMM_LEN])
{
	/* Packed loads permit the fixed-size comm array to be unaligned. As with
	 * the previous strcmp, concurrent rename is not a 16-byte atomic snapshot;
	 * retained acquisition records independently preserve unlock routing. */
	struct kd_comm_word { unsigned long value; } __attribute__((packed));
	const struct kd_comm_word *word = (const void *)comm;

	/* Every valid key, including the empty name, masks its first NUL byte.
	 * Reuse that fact instead of loading a redundant boolean state. */
	return key->mask[0] &&
	       (READ_ONCE(word[0].value) & key->mask[0]) == key->value[0] &&
	       (READ_ONCE(word[1].value) & key->mask[1]) == key->value[1];
}

#endif
