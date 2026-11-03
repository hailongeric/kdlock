/* SPDX-License-Identifier: GPL-2.0 */
/* Exact production selection with observed Native-owner/context substitutes.
 * GS instruction effects have a separate Native differential fixture. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
#include "kd_origin_memory.h"

#define X86_EFLAGS_IF 0x200
#define KD_NATIVE_OWNER_FREE 0
#define KD_NATIVE_OWNER_PREEMPT 3
struct kd_native_owner { unsigned int kind; struct kd_native_owner *next; };
struct owner_list { struct kd_native_owner *head; };
struct kd_service_root {
	struct { struct kd_origin_memory origin_memory; } continuation;
	struct owner_list native_owners;
	struct kd_native_owner *held;
	unsigned int native_pins, origin_cpu;
};
static int __preempt_count, counts[2];
static unsigned int native_preempt, find_calls, reserve_calls, checks;
static struct kd_native_owner spare;
static unsigned long data[2];
#define per_cpu_ptr(pointer, cpu) ((void)(pointer), &counts[(cpu)])
#define preempt_count() native_preempt
#define list_for_each_entry(owner, list, member) \
	for ((owner) = (list)->head; (owner); (owner) = (owner)->next)
#define CHECK(expression) do { ++checks; if (!(expression)) { \
	fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #expression); exit(1); } } while (0)

static unsigned int kd_service_native_pins(struct kd_service_root *root)
{ return root->native_pins; }
static struct kd_native_owner *kd_service_native_find(struct kd_service_root *root,
	unsigned int kind, unsigned long object)
{
	++find_calls;
	CHECK(kind == KD_NATIVE_OWNER_PREEMPT && object == (unsigned long)&counts[root->origin_cpu]);
	return root->held;
}
static struct kd_native_owner *kd_service_native_reserve(struct kd_service_root *root,
	unsigned int kind, unsigned long object, u64 sequence)
{
	++reserve_calls;
	CHECK(kind == KD_NATIVE_OWNER_PREEMPT && object == (unsigned long)&counts[root->origin_cpu]);
	CHECK(sequence == 17);
	return &spare;
}

#include "production.h"

static void reset(struct kd_service_root *root, struct kd_origin_memory_site *site)
{
	/* No transaction or owner remains live across fixture resets. */
	memset(root, 0, sizeof(*root));
	memset(site, 0, sizeof(*site));
	root->origin_cpu = 1;
	root->continuation.origin_memory.site = site;
	root->continuation.origin_memory.effective_offset = (unsigned long)&data[0];
	root->continuation.origin_memory.executor_irq_flags = X86_EFLAGS_IF;
	root->continuation.origin_memory.sequence = 17;
	native_preempt = 1;
	find_calls = reserve_calls = 0;
	spare.kind = KD_NATIVE_OWNER_FREE;
	spare.next = NULL;
}

int main(void)
{
	struct kd_service_root root;
	struct kd_origin_memory_site site;
	struct kd_origin_memory *operation = &root.continuation.origin_memory;
	const struct { unsigned int operation, width; } reads[] = {
		{ KD_ORIGIN_MEMORY_LOAD, 32 }, { KD_ORIGIN_MEMORY_LOAD, 64 },
		{ KD_ORIGIN_MEMORY_TEST, 16 }, { KD_ORIGIN_MEMORY_TEST, 32 },
		{ KD_ORIGIN_MEMORY_SUB, 32 }, { KD_ORIGIN_MEMORY_SUB, 64 },
	};
	unsigned int i, pins;

	for (i = 0; i < sizeof(reads) / sizeof(reads[0]); ++i)
	for (pins = 0; pins < 2; ++pins) {
		reset(&root, &site);
		site.operation = reads[i].operation;
		site.width = reads[i].width;
		site.flags = KD_ORIGIN_MEMORY_READ;
		root.native_pins = pins;
		CHECK(!kd_service_memory_prepare(&root));
		CHECK(!operation->preempt_operand && !operation->preempt_owner);
		CHECK(operation->executor_pinned == (pins != 0));
		CHECK(!find_calls && !reserve_calls && native_preempt == 1);
	}
	reset(&root, &site);
	site.operation = KD_ORIGIN_MEMORY_LOAD; site.width = 32; site.flags = KD_ORIGIN_MEMORY_READ;
	operation->effective_offset = (unsigned long)&counts[1];
	CHECK(!kd_service_memory_prepare(&root));
	CHECK(operation->preempt_operand && operation->executor_pinned && !operation->preempt_owner);
	CHECK(!find_calls && !reserve_calls);
	reset(&root, &site);
	site.operation = KD_ORIGIN_MEMORY_INC; site.width = 32;
	operation->effective_offset = (unsigned long)&counts[1];
	root.native_owners.head = &spare;
	CHECK(!kd_service_memory_prepare(&root));
	CHECK(operation->preempt_operand && operation->preempt_owner == &spare && reserve_calls == 1);
	reset(&root, &site);
	site.operation = KD_ORIGIN_MEMORY_DEC; site.width = 32;
	operation->effective_offset = (unsigned long)&counts[1];
	CHECK(kd_service_memory_prepare(&root) == -EINVAL && find_calls == 1);
	root.held = &spare;
	CHECK(!kd_service_memory_prepare(&root) && operation->preempt_owner == &spare);
	reset(&root, &site);
	site.operation = KD_ORIGIN_MEMORY_LOAD; site.width = 64; site.flags = KD_ORIGIN_MEMORY_READ;
	operation->executor_irq_flags = 0;
	CHECK(kd_service_memory_prepare(&root) == -EOPNOTSUPP);
	operation->executor_irq_flags = X86_EFLAGS_IF;
	native_preempt = 2;
	CHECK(kd_service_memory_prepare(&root) == -EOPNOTSUPP);
	native_preempt = 1;
	operation->effective_offset = ~0UL - 1;
	CHECK(kd_service_memory_prepare(&root) == -EOPNOTSUPP);
	reset(&root, &site);
	site.operation = KD_ORIGIN_MEMORY_INC; site.width = 64;
	operation->effective_offset = (unsigned long)&counts[1];
	CHECK(kd_service_memory_prepare(&root) == -EOPNOTSUPP);
	CHECK(!find_calls && !reserve_calls);
	printf("production GS read policy: %u checks, 0 failures\n", checks);
	return 0;
}
