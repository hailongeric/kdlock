/* SPDX-License-Identifier: GPL-2.0 */
/* Production registry logic in a VM userspace component. No Native terminal
 * or kernel diagnostic is invoked by this fixture. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

typedef uint64_t u64;
typedef int atomic_t;
struct module;
struct kernel_param { void *arg; };
#define PAGE_SIZE 4096U
#define CONFIG_PREEMPT_RCU 1
#define IS_ENABLED(option) (option)
#define DEFINE_MUTEX(name) int name
#define mutex_lock(lock) ((void)(lock))
#define mutex_unlock(lock) ((void)(lock))
#define atomic_set(pointer, value) (*(pointer) = (value))
#define smp_store_release(pointer, value) (*(pointer) = (value))
#define X86_EFLAGS_IF 0x200UL
struct kd_native_owner {
	struct kd_native_owner *next;
	unsigned long object;
	unsigned int kind;
	bool held;
};
struct kd_origin_call {
	unsigned long executor_irq_flags, object, object_out;
	unsigned int context_kind;
	u64 sequence;
	bool executor_pinned;
	struct kd_native_owner *spin_owner, *rcu_owner, *rwsem_owner;
};
struct kd_service_root {
	struct { struct kd_origin_call origin_call; } continuation;
	struct kd_native_owner *native_owners;
	unsigned int pins, rcu;
};
#define list_for_each_entry(owner, head, link) \
	for ((owner) = *(head); (owner); (owner) = (owner)->next)
static unsigned int reservations;
static inline unsigned int preempt_count(void) { return 1; }
static inline unsigned int kd_service_native_pins(struct kd_service_root *root)
{ return root->pins; }
static inline unsigned int kd_service_native_depth(struct kd_service_root *root, unsigned int kind)
{ (void)kind; return root->rcu; }
static inline struct kd_native_owner *kd_service_native_find(struct kd_service_root *root,
	unsigned int kind, unsigned long object)
{
	struct kd_native_owner *owner;

	for (owner = root->native_owners; owner; owner = owner->next)
		if (owner->held && owner->kind == kind && owner->object == object)
			return owner;
	return NULL;
}
static inline struct kd_native_owner *kd_service_native_reserve(struct kd_service_root *root,
	unsigned int kind, unsigned long object, u64 sequence)
{
	(void)root; (void)kind; (void)object; (void)sequence;
	++reservations;
	return NULL;
}

static inline long strscpy(char *to, const char *from, size_t capacity)
{
	size_t size = strlen(from);

	if (size >= capacity)
		return -E2BIG;
	memcpy(to, from, size + 1);
	return (long)size;
}

static inline unsigned long kallsyms_lookup_name(const char *name)
{
	return !strcmp(name, "__stack_chk_fail") ? 0xffffffff81001000UL : 0;
}

#include "production.h"

#define CHECK(condition) do { \
	if (!(condition)) { \
		fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #condition); \
		return 1; \
	} \
	++checks; \
} while (0)

int main(void)
{
	struct kd_service_call_desc terminal = {
		.symbol = "__stack_chk_fail", .target = 0xffffffff81001000UL,
		.result_kind = KD_SERVICE_CALL_VOID,
		.context_kind = KD_SERVICE_CALL_NONRETURNING_ORIGIN,
	};
	struct kd_service_call_desc descs[64], candidate;
	char names[64][96], snapshot[PAGE_SIZE], before[PAGE_SIZE];
	unsigned int checks = 0, i;
	int used;
	struct kd_native_owner owners[] = {
		{ .object = 0x1100, .kind = KD_NATIVE_OWNER_SPIN, .held = true },
		{ .object = 0x1200, .kind = KD_NATIVE_OWNER_PREEMPT, .held = true },
		{ .kind = KD_NATIVE_OWNER_RCU, .held = true },
	}, retained[3];
	struct kd_service_root root = { .continuation.origin_call = {
		.executor_irq_flags = X86_EFLAGS_IF,
		.context_kind = KD_SERVICE_CALL_NONRETURNING_ORIGIN,
	}, .native_owners = owners, .pins = 2, .rcu = 1 };

	owners[0].next = &owners[1];
	owners[1].next = &owners[2];
	memcpy(retained, owners, sizeof(owners));
	CHECK(!kd_service_native_prepare(&root));
	CHECK(root.continuation.origin_call.executor_pinned);
	CHECK(!reservations && !memcmp(owners, retained, sizeof(owners)));
	root.native_owners = &owners[2];
	root.pins = 0;
	root.rcu = 1;
	CHECK(!kd_service_native_prepare(&root));
	CHECK(!root.continuation.origin_call.executor_pinned);
	CHECK(!reservations && !memcmp(owners, retained, sizeof(owners)));

	CHECK(KD_SERVICE_CALL_NONRETURNING_ORIGIN == 11);
	CHECK(kd_service_call_valid(&terminal));
	candidate = terminal;
	candidate.target++;
	CHECK(!kd_service_call_valid(&candidate));
	candidate = terminal;
	candidate.symbol = "panic";
	CHECK(!kd_service_call_valid(&candidate));
	candidate = terminal;
	candidate.nargs = 1;
	CHECK(!kd_service_call_valid(&candidate));
	candidate = terminal;
	candidate.result_kind = KD_SERVICE_CALL_WORD;
	CHECK(!kd_service_call_valid(&candidate));
	CHECK(!kd_service_call_register(&terminal, 1, NULL));

	for (i = 0; i != 64; ++i) {
		snprintf(names[i], sizeof(names[i]), "fixture_%u", i);
		descs[i] = (struct kd_service_call_desc) {
			.symbol = names[i], .target = 0xffffffff82000000UL + i,
			.result_kind = KD_SERVICE_CALL_VOID,
			.context_kind = KD_SERVICE_CALL_ATOMIC_ORIGIN,
		};
	}
	CHECK(!kd_service_call_register(descs, 64, NULL));
	CHECK(kd_service_call_count == 65);
	used = kd_service_call_table_get(before, NULL);
	CHECK(used > 0 && used < (int)PAGE_SIZE);
	for (i = 0; i != 63; ++i) {
		memset(names[i], 'x', 95);
		snprintf(names[i], 12, "large_%05u", i);
		names[i][11] = 'x';
		names[i][95] = 0;
		descs[i].target += 0x100000;
	}
	/* A larger roster publishes completely through bounded pages; an old
	 * one-page reader reports overflow rather than returning a prefix. */
	CHECK(!kd_service_call_register(descs, 63, NULL));
	CHECK(kd_service_call_count == 128 && kd_service_call_generation == 3);
	CHECK(kd_service_call_table_get(snapshot, NULL) == -EOVERFLOW);
	{
		unsigned int page, rows = 0;
		struct kernel_param parameter;
		for (page = 0; page < 8; ++page) {
			unsigned int j, lines = 0;
			parameter.arg = (void *)(unsigned long)page;
			used = kd_service_call_page_get(snapshot, &parameter);
			CHECK(used > 0 && used < (int)PAGE_SIZE && snapshot[used] == 0);
			for (j = 0; j < (unsigned int)used; ++j) lines += snapshot[j] == '\n';
			CHECK(lines == 16); rows += lines;
		}
		CHECK(rows == 128);
		parameter.arg = (void *)8UL;
		CHECK(kd_service_call_page_get(snapshot, &parameter) == -EINVAL);
		CHECK(kd_service_call_state_get(snapshot, NULL) > 0 && !strcmp(snapshot, "3 128 128\n"));
	}
	candidate = terminal; candidate.symbol = "extra_call"; candidate.target += 0x10000000;
	CHECK(kd_service_call_register(&candidate, 1, NULL) == -ENOSPC);
	CHECK(kd_service_call_count == 128 && kd_service_call_generation == 3);
	printf("Native terminal and bounded registry pages: checks=%u\n", checks);
	return 0;
}
