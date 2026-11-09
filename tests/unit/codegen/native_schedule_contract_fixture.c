/* SPDX-License-Identifier: GPL-2.0 */
/* VM-only policy fixture. It does not execute a kernel scheduling entry. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#define IS_ENABLED(option) (option)
/* Match the current live kernel; map roster variants have their own fixture. */
#define CONFIG_SLAB_BUCKETS 1
typedef uint64_t u64;
typedef unsigned int atomic_t;
struct module;
#define atomic_read(pointer) (*(pointer))
#define BUG_ON(condition) do { if (condition) abort(); } while (0)
#define X86_EFLAGS_IF 0x200UL
static unsigned int native_preempt = 1;
#define preempt_count() native_preempt
static unsigned long kallsyms_lookup_name(const char *name)
{ return !strcmp(name, "__stack_chk_fail") ? 0x9000UL : 0; }

/* The exact production admission body observes these counted owner/context
 * substitutes. No Native acquisition or target body executes in this fixture. */
struct kd_native_owner { unsigned int kind; struct kd_native_owner *next; };
struct owner_list { struct kd_native_owner *head; };
struct kd_origin_call {
	struct kd_native_owner *rwsem_owner, *spin_owner, *rcu_owner;
	unsigned long executor_irq_flags, object, object_out;
	u64 sequence;
	unsigned int context_kind;
	bool executor_pinned;
};
struct kd_service_root {
	struct { struct kd_origin_call origin_call; } continuation;
	struct owner_list native_owners;
	unsigned int pins, rcu, finds, reservations;
};
#define list_for_each_entry(owner, list, member) \
	for ((owner) = (list)->head; (owner); (owner) = (owner)->next)
static unsigned int kd_service_native_pins(struct kd_service_root *root)
{ return root->pins; }
static unsigned int kd_service_native_depth(struct kd_service_root *root, unsigned int kind)
{ (void)kind; return root->rcu; }
static struct kd_native_owner *kd_service_native_find(struct kd_service_root *root,
	unsigned int kind, unsigned long object)
{ (void)kind; (void)object; ++root->finds; return NULL; }
static struct kd_native_owner *kd_service_native_reserve(struct kd_service_root *root,
	unsigned int kind, unsigned long object, u64 sequence)
{ (void)kind; (void)object; (void)sequence; ++root->reservations; return NULL; }
#include "production.h"

#define CHECK(condition) do { \
	if (!(condition)) { \
		fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #condition); \
		return 1; \
	} \
	++checks; \
} while (0)

#define KD_SERVICE_CONTEXT(name, args, result_type, context) \
	{ .symbol = #name, .nargs = args, .result_kind = result_type, .context_kind = context },
#define KD_SERVICE_CALL(name, args, result_type) \
	KD_SERVICE_CONTEXT(name, args, result_type, KD_SERVICE_CALL_BALANCED_ORIGIN)
#define KD_SERVICE_MAPPED_CALL(name, arity, execution, native_arity, a0, a1, a2, a3, a4, a5) \
	KD_SERVICE_CALL(name, arity, KD_SERVICE_CALL_WORD)
static const struct kd_service_call_desc primitives[] = {
#include "kd_service_calls.def"
};
#undef KD_SERVICE_MAPPED_CALL
#undef KD_SERVICE_CALL
#undef KD_SERVICE_CONTEXT

int main(void)
{
	struct kd_service_call_desc desc = {
		.nargs = 0, .result_kind = KD_SERVICE_CALL_VOID,
		.context_kind = KD_SERVICE_CALL_SCHEDULE_ORIGIN,
	};
	unsigned int checks = 0, schedules = 0, policies = 0, callbacks = 0, writers = 0, allocators = 0;
	unsigned int conditional = 0, page_allocators = 0, page_accounting = 0;
	unsigned int memcg_accounting = 0, page_release = 0, cpu_notifications = 0, folio_release = 0;
	unsigned int context, pins, rcu;
	size_t i;

	CHECK(KD_SERVICE_CALL_SCHEDULE_ORIGIN == 10);
	CHECK(kd_service_call_context_valid(&desc));
	CHECK(!kd_service_call_requires_preempt_rcu(desc.context_kind));
	desc.nargs = 1;
	CHECK(!kd_service_call_context_valid(&desc));
	desc.nargs = 0;
	desc.result_kind = KD_SERVICE_CALL_WORD;
	CHECK(!kd_service_call_context_valid(&desc));
	desc.result_kind = KD_SERVICE_CALL_VOID;
	desc.context_kind = KD_SERVICE_CALL_ARG0_BALANCED_OR_ATOMIC + 1;
	CHECK(!kd_service_call_context_valid(&desc));
	for (context = KD_SERVICE_CALL_RWSEM_WRITE_LOCK;
	     context <= KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK; ++context) {
		desc.context_kind = context;
		desc.nargs = 1;
		CHECK(kd_service_call_context_valid(&desc));
		CHECK(!kd_service_call_requires_preempt_rcu(context));
		CHECK(!kd_service_native_executor_pinned(context, 0));
		CHECK(kd_service_native_executor_pinned(context, 1));
		desc.nargs = 0;
		CHECK(!kd_service_call_context_valid(&desc));
		desc.nargs = 1;
		desc.result_kind = KD_SERVICE_CALL_WORD;
		CHECK(!kd_service_call_context_valid(&desc));
		desc.result_kind = KD_SERVICE_CALL_VOID;
	}

	for (pins = 0; pins != 3; ++pins) {
		for (rcu = 0; rcu != 3; ++rcu) {
			bool allowed = !pins && (!rcu || CONFIG_PREEMPT_RCU);

			CHECK(kd_service_schedule_origin_allowed(pins, rcu) == allowed);
		}
	}
	for (context = KD_SERVICE_CALL_BALANCED_ORIGIN;
	     context <= KD_SERVICE_CALL_SCHEDULE_ORIGIN; ++context) {
		bool owner_context = context >= KD_SERVICE_CALL_PTE_LOCK &&
			context <= KD_SERVICE_CALL_PTE_RCU;

		CHECK(kd_service_call_requires_preempt_rcu(context) == owner_context);
		CHECK(kd_service_native_executor_pinned(context, 0) == owner_context);
		CHECK(kd_service_native_executor_pinned(context, 1));
	}
	/* Resolution consumes the captured argument value, never its pointee.
	 * The complete immutable entry and every fixed context remain unchanged. */
	{
		static const unsigned long arguments[] = { 0, 1, 0x8000000000000000UL, ~0UL };
		struct kd_service_call_entry entry = { .users = 1,
			.context_kind = KD_SERVICE_CALL_ARG0_BALANCED_OR_ATOMIC, .nargs = 2 };
		struct kd_service_call_entry saved;
		struct kd_service_call_mapped_desc mapped = {
			.source = { .symbol = "conditional_fixture", .target = 0x1000,
				.nargs = 2, .result_kind = KD_SERVICE_CALL_VOID,
				.context_kind = KD_SERVICE_CALL_ARG0_BALANCED_OR_ATOMIC },
			.execution_target = 0x2000, .version = KD_SERVICE_CALL_MAP_V1,
		};
		struct kd_service_root root;
		struct kd_native_owner held = { .kind = KD_NATIVE_OWNER_SPIN };
		struct kd_native_owner free_owner = { .kind = KD_NATIVE_OWNER_FREE, .next = &held };
		unsigned int argument, resolved;

		memcpy(&saved, &entry, sizeof(saved));
		CHECK(KD_SERVICE_CALL_ARG0_BALANCED_OR_ATOMIC == 14);
		CHECK(kd_service_call_context_valid(&mapped.source));
		CHECK(!kd_service_call_mapped_valid(&mapped));
		mapped.source.context_kind = KD_SERVICE_CALL_BALANCED_ORIGIN;
		CHECK(kd_service_call_mapped_valid(&mapped));
		mapped.source.context_kind = KD_SERVICE_CALL_ARG0_BALANCED_OR_ATOMIC;
		for (argument = 0; argument <= 7; ++argument) {
			mapped.source.nargs = argument;
			CHECK(kd_service_call_context_valid(&mapped.source) == (argument >= 1 && argument <= 6));
		}
		for (argument = 0; argument < sizeof(arguments) / sizeof(arguments[0]); ++argument) {
			resolved = arguments[argument] ? KD_SERVICE_CALL_ATOMIC_ORIGIN :
				KD_SERVICE_CALL_BALANCED_ORIGIN;
			CHECK(kd_service_call_invocation_context(&entry, arguments[argument]) == resolved);
			CHECK(!memcmp(&entry, &saved, sizeof(entry)) && entry.users == 1);
			for (pins = 0; pins < 3; ++pins)
			for (rcu = 0; rcu < 3; ++rcu) {
				memset(&root, 0, sizeof(root));
				root.pins = pins; root.rcu = rcu;
				root.native_owners.head = &free_owner;
				root.continuation.origin_call.context_kind = resolved;
				root.continuation.origin_call.executor_irq_flags = X86_EFLAGS_IF;
				CHECK(kd_service_native_prepare(&root) ==
					(!arguments[argument] && (pins || rcu) ? -EOPNOTSUPP : 0));
				CHECK(root.pins == pins && root.rcu == rcu &&
					root.native_owners.head == &free_owner && free_owner.next == &held &&
					free_owner.kind == KD_NATIVE_OWNER_FREE && held.kind == KD_NATIVE_OWNER_SPIN &&
					!root.finds && !root.reservations);
				CHECK(root.continuation.origin_call.context_kind == resolved);
				if (arguments[argument] || (!pins && !rcu))
					CHECK(root.continuation.origin_call.executor_pinned == (pins != 0));
			}
		}
		for (context = KD_SERVICE_CALL_BALANCED_ORIGIN;
		     context < KD_SERVICE_CALL_ARG0_BALANCED_OR_ATOMIC; ++context) {
			entry.context_kind = context;
			memcpy(&saved, &entry, sizeof(saved));
			for (argument = 0; argument < sizeof(arguments) / sizeof(arguments[0]); ++argument) {
				CHECK(kd_service_call_invocation_context(&entry, arguments[argument]) == context);
				CHECK(!memcmp(&entry, &saved, sizeof(entry)) && entry.users == 1);
			}
		}
		/* Runtime admission must receive a resolved context; its existing
		 * IRQ/preempt checks are retained for both selected contexts. */
		memset(&root, 0, sizeof(root));
		root.continuation.origin_call.executor_irq_flags = X86_EFLAGS_IF;
		root.continuation.origin_call.context_kind = KD_SERVICE_CALL_ARG0_BALANCED_OR_ATOMIC;
		CHECK(kd_service_native_prepare(&root) == -EOPNOTSUPP);
		for (context = KD_SERVICE_CALL_BALANCED_ORIGIN;
		     context <= KD_SERVICE_CALL_ATOMIC_ORIGIN; ++context) {
			root.continuation.origin_call.context_kind = context;
			root.continuation.origin_call.executor_irq_flags = 0;
			CHECK(kd_service_native_prepare(&root) == -EOPNOTSUPP);
			root.continuation.origin_call.executor_irq_flags = X86_EFLAGS_IF;
			native_preempt = 2;
			CHECK(kd_service_native_prepare(&root) == -EOPNOTSUPP);
			native_preempt = 1;
			CHECK(!kd_service_native_prepare(&root) && !root.finds && !root.reservations);
		}
	}
	for (i = 0; i < sizeof(primitives) / sizeof(primitives[0]); ++i) {
		const struct kd_service_call_desc *primitive = &primitives[i];
		bool owner_context = kd_service_call_requires_preempt_rcu(primitive->context_kind);

		CHECK(kd_service_call_context_valid(primitive) ==
			(!owner_context || CONFIG_PREEMPT_RCU));
		if (primitive->context_kind == KD_SERVICE_CALL_SCHEDULE_ORIGIN) {
			++schedules;
			CHECK(!primitive->nargs && primitive->result_kind == KD_SERVICE_CALL_VOID);
			CHECK(strcmp(primitive->symbol, "preempt_schedule_irq"));
		}
		if (!strcmp(primitive->symbol, "security_vm_enough_memory_mm")) {
			++policies;
			CHECK(primitive->nargs == 2 && primitive->result_kind == KD_SERVICE_CALL_WORD &&
				primitive->context_kind == KD_SERVICE_CALL_BALANCED_ORIGIN);
		}
		if (!strcmp(primitive->symbol, "security_mmap_addr")) {
			++policies;
			CHECK(primitive->nargs == 1 && primitive->result_kind == KD_SERVICE_CALL_WORD &&
				primitive->context_kind == KD_SERVICE_CALL_BALANCED_ORIGIN);
		}
		{
			static const struct { const char *name; unsigned int nargs; } file_calls[] = {
				{ "ext4_file_mmap_prepare", 1 }, { "shmem_mmap_prepare", 1 },
				{ "generic_file_mmap_prepare", 1 }, { "generic_file_readonly_mmap_prepare", 1 },
				{ "generic_file_mmap", 2 }, { "generic_file_readonly_mmap", 2 },
				{ "thp_get_unmapped_area", 5 }, { "shmem_get_unmapped_area", 5 },
			};
			size_t callback;

			for (callback = 0; callback < sizeof(file_calls) / sizeof(file_calls[0]); ++callback)
				if (!strcmp(primitive->symbol, file_calls[callback].name)) {
					++callbacks;
					CHECK(primitive->nargs == file_calls[callback].nargs &&
						primitive->result_kind == KD_SERVICE_CALL_WORD &&
						primitive->context_kind == KD_SERVICE_CALL_BALANCED_ORIGIN);
				}
		}
		if (!strcmp(primitive->symbol, "__kmalloc_cache_noprof") ||
		    !strcmp(primitive->symbol, "__kmalloc_cache_node_noprof")) {
			++allocators;
			CHECK(primitive->nargs == (!strcmp(primitive->symbol, "__kmalloc_cache_noprof") ? 3 : 4) &&
				primitive->result_kind == KD_SERVICE_CALL_WORD &&
				primitive->context_kind == KD_SERVICE_CALL_BALANCED_ORIGIN);
		}
		{
			static const struct { const char *name; unsigned int nargs; } page_calls[] = {
				{ "__alloc_pages_noprof", 4 }, { "__folio_alloc_noprof", 4 },
				{ "alloc_pages_noprof", 2 }, { "folio_alloc_noprof", 2 },
				{ "get_free_pages_noprof", 2 }, { "get_zeroed_page_noprof", 1 },
			};
			size_t allocation;

			for (allocation = 0; allocation < sizeof(page_calls) / sizeof(page_calls[0]); ++allocation)
				if (!strcmp(primitive->symbol, page_calls[allocation].name)) {
					CHECK(!(page_allocators & (1U << allocation)));
					page_allocators |= 1U << allocation;
					CHECK(primitive->nargs == page_calls[allocation].nargs &&
						primitive->result_kind == KD_SERVICE_CALL_WORD &&
						primitive->context_kind == KD_SERVICE_CALL_ATOMIC_ORIGIN);
					CHECK(!kd_service_call_requires_preempt_rcu(primitive->context_kind) &&
						!kd_service_native_executor_pinned(primitive->context_kind, 0) &&
						kd_service_native_executor_pinned(primitive->context_kind, 1));
				}
		}
		{
			static const struct { const char *name; unsigned int nargs; } accounting_calls[] = {
				{ "mod_node_page_state", 3 }, { "mod_zone_page_state", 3 },
				{ "inc_node_page_state", 2 }, { "inc_zone_page_state", 2 },
				{ "dec_node_page_state", 2 }, { "dec_zone_page_state", 2 },
			};
			size_t accounting;

			for (accounting = 0; accounting < sizeof(accounting_calls) / sizeof(accounting_calls[0]); ++accounting)
				if (!strcmp(primitive->symbol, accounting_calls[accounting].name)) {
					CHECK(!(page_accounting & (1U << accounting)));
					page_accounting |= 1U << accounting;
					CHECK(primitive->nargs == accounting_calls[accounting].nargs &&
						primitive->result_kind == KD_SERVICE_CALL_VOID &&
						primitive->context_kind == KD_SERVICE_CALL_ATOMIC_ORIGIN);
					CHECK(!kd_service_call_requires_preempt_rcu(primitive->context_kind) &&
						!kd_service_native_executor_pinned(primitive->context_kind, 0) &&
						kd_service_native_executor_pinned(primitive->context_kind, 1));
				}
		}
		{
			static const char *const memcg_calls[] = {
				"mod_memcg_state", "mod_lruvec_state",
				"lruvec_stat_mod_folio", "mod_lruvec_kmem_state",
			};
			size_t accounting;

			for (accounting = 0; accounting < sizeof(memcg_calls) / sizeof(memcg_calls[0]); ++accounting)
				if (!strcmp(primitive->symbol, memcg_calls[accounting])) {
					CHECK(!(memcg_accounting & (1U << accounting)));
					memcg_accounting |= 1U << accounting;
					CHECK(primitive->nargs == 3 && primitive->result_kind == KD_SERVICE_CALL_VOID &&
						primitive->context_kind == KD_SERVICE_CALL_ATOMIC_ORIGIN);
					CHECK(!kd_service_call_requires_preempt_rcu(primitive->context_kind) &&
						!kd_service_native_executor_pinned(primitive->context_kind, 0) &&
						kd_service_native_executor_pinned(primitive->context_kind, 1));
				}
		}

		{
			static const char *const release_calls[] = { "__free_pages", "free_pages",
				"free_pages_nolock", "free_pages_exact", "free_frozen_pages", "free_frozen_pages_nolock" };
			size_t entry;
			for (entry = 0; entry < sizeof(release_calls) / sizeof(release_calls[0]); ++entry)
				if (!strcmp(primitive->symbol, release_calls[entry])) {
					CHECK(!(page_release & (1U << entry))); page_release |= 1U << entry;
					CHECK(primitive->nargs == 2 && primitive->result_kind == KD_SERVICE_CALL_VOID &&
						primitive->context_kind == KD_SERVICE_CALL_ATOMIC_ORIGIN);
					CHECK(!kd_service_native_executor_pinned(primitive->context_kind, 0) &&
						kd_service_native_executor_pinned(primitive->context_kind, 1));
				}
		}
		{
			static const char *const calls[] = { "__folio_put", "folios_put_refs", "release_pages", "free_pages_and_swap_cache" };
			size_t entry;
			for (entry = 0; entry < sizeof(calls) / sizeof(calls[0]); ++entry)
				if (!strcmp(primitive->symbol, calls[entry])) {
					CHECK(!(folio_release & (1U << entry))); folio_release |= 1U << entry;
					CHECK(primitive->nargs == (entry ? 2 : 1) && primitive->result_kind == KD_SERVICE_CALL_VOID &&
						primitive->context_kind == KD_SERVICE_CALL_ATOMIC_ORIGIN);
					CHECK(!kd_service_native_executor_pinned(primitive->context_kind, 0) &&
						kd_service_native_executor_pinned(primitive->context_kind, 1));
				}
		}
		if (!strcmp(primitive->symbol, "kick_process")) {
			++cpu_notifications;
			CHECK(primitive->nargs == 1 && primitive->result_kind == KD_SERVICE_CALL_VOID &&
				primitive->context_kind == KD_SERVICE_CALL_ATOMIC_ORIGIN);
			CHECK(!kd_service_native_executor_pinned(primitive->context_kind, 0) &&
				kd_service_native_executor_pinned(primitive->context_kind, 1));
		}
		if (!strcmp(primitive->symbol, "down_write") || !strcmp(primitive->symbol, "up_write")) {
			++writers;
			CHECK(primitive->nargs == 1 && primitive->result_kind == KD_SERVICE_CALL_VOID &&
				primitive->context_kind == (!strcmp(primitive->symbol, "down_write") ?
				KD_SERVICE_CALL_RWSEM_WRITE_LOCK : KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK));
		}
		if (!strcmp(primitive->symbol, "kvfree_call_rcu")) {
			++conditional;
			CHECK(primitive->nargs == 2 && primitive->result_kind == KD_SERVICE_CALL_VOID &&
				primitive->context_kind == KD_SERVICE_CALL_ARG0_BALANCED_OR_ATOMIC);
		}
	}
	CHECK(schedules == 8);
	CHECK(policies == 2);
	CHECK(callbacks == 8 && writers == 2 && allocators == 2);
	CHECK(conditional == 1);
	CHECK(page_allocators == 0x3f);
	CHECK(page_accounting == 0x3f);
	CHECK(memcg_accounting == 0xf);
	CHECK(page_release == 0x3f);
	CHECK(cpu_notifications == 1);
	CHECK(folio_release == 0xf);
	printf("Native schedule context: checks=%u PREEMPT_RCU=%u\n", checks,
		(unsigned int)CONFIG_PREEMPT_RCU);
	return 0;
}
