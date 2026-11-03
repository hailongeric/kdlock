/* SPDX-License-Identifier: GPL-2.0 */
/* Production bodies execute with counted module references and source pins.
 * The packet fields are named substitutes; assembly layout has separate checks. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

typedef uint64_t u64;
typedef int atomic_t;
struct module { int references; bool live; };
struct kd_regs { unsigned long ip, sp, di, si, dx, cx, r8, r9, flags; };
struct kd_source_info { unsigned int state, frames, writers; };
static struct kd_source_info source_info;
static unsigned long pins[256];
static unsigned int pin_count, fail_pin;
#define KD_SOURCE_OPEN 0U
#define PAGE_SIZE 4096U
#define CONFIG_PREEMPT_RCU 1
#define IS_ENABLED(option) (option)
#define DEFINE_MUTEX(name) int name
#define mutex_lock(lock) ((void)(lock))
#define mutex_unlock(lock) ((void)(lock))
#define atomic_set(pointer, value) (*(pointer) = (value))
#define atomic_read(pointer) (*(pointer))
#define atomic_inc(pointer) (++*(pointer))
#define atomic_dec(pointer) (--*(pointer))
#define smp_store_release(pointer, value) (*(pointer) = (value))
#define smp_load_acquire(pointer) (*(pointer))
#define unlikely(value) (value)
#define BUG_ON(value) do { if (value) abort(); } while (0)
static inline bool try_module_get(struct module *owner)
{ if (!owner->live) return false; ++owner->references; return true; }
static inline void module_put(struct module *owner) { --owner->references; }
static inline void kd_source_info(struct kd_source_info *info) { *info = source_info; }
static inline int kd_source_pin_root(unsigned long target)
{ pins[pin_count++] = target; return fail_pin == pin_count ? -ESTALE : 0; }
static inline long strscpy(char *to, const char *from, size_t capacity)
{
	size_t length = strlen(from);
	if (length >= capacity) return -E2BIG;
	memcpy(to, from, length + 1);
	return (long)length;
}
static inline unsigned long kallsyms_lookup_name(const char *name)
{ return !strcmp(name, "__stack_chk_fail") ? 0x9000 : 0; }
#include "production.h"

#define KD_SERVICE_CONTEXT(name, args, result, context)
#define KD_SERVICE_CALL(name, args, result)
#define KD_SERVICE_MAPPED_CALL(name, arity, execution, native_arity, a0, a1, a2, a3, a4, a5) \
	{ .source = { #name, 0x1000, arity, KD_SERVICE_CALL_WORD, KD_SERVICE_CALL_BALANCED_ORIGIN, 0 }, \
	  .execution_target = 0x2000, .version = KD_SERVICE_CALL_MAP_V1, .execution_nargs = native_arity, \
	  .arguments = { a0, a1, a2, a3, a4, a5 } },
static const struct kd_service_call_mapped_desc production_maps[] = {
#include "kd_service_calls.def"
};
#undef KD_SERVICE_MAPPED_CALL
#undef KD_SERVICE_CALL
#undef KD_SERVICE_CONTEXT

static unsigned int checks;
#define CHECK(value) do { ++checks; if (!(value)) { \
	fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #value); return 1; } } while (0)
static void reset(void)
{
	memset(kd_service_call_entries, 0, sizeof(kd_service_call_entries));
	kd_service_call_count = 0;
	kd_service_call_frozen = false;
	source_info = (struct kd_source_info){ .state = 2 };
	pin_count = fail_pin = 0;
	memset(pins, 0, sizeof(pins));
}
static struct kd_service_call_mapped_desc descriptor(void)
{
	return (struct kd_service_call_mapped_desc){
		.source = { "source_two", 0x1000, 2, KD_SERVICE_CALL_WORD, KD_SERVICE_CALL_BALANCED_ORIGIN, 0 },
		.execution_target = 0x2000, .version = KD_SERVICE_CALL_MAP_V1, .execution_nargs = 5,
		.arguments = { KD_SERVICE_ARG_SOURCE0, KD_SERVICE_ARG_ZERO, KD_SERVICE_ARG_SOURCE1,
			KD_SERVICE_ARG_MINUS_ONE, KD_SERVICE_ARG_RETURN_IP, KD_SERVICE_ARG_UNUSED },
	};
}

int main(void)
{
	struct kd_service_call_mapped_desc good = descriptor(), candidate, batch[80];
	struct kd_regs packet = { .ip = 0x1000, .sp = 0x8000, .di = 17, .si = 29,
		.dx = 41, .cx = 53, .r8 = 67, .r9 = 79, .flags = 0x295 }, saved;
	struct module owner = { .live = true };
	struct kd_service_call_entry *entry;
	unsigned long execution, arguments[6], expected[6] = {17, 0, 29, ~0UL, 0x3456, 79};
	char names[80][96];
	unsigned int i, j;

	CHECK(sizeof(production_maps) / sizeof(production_maps[0]) == 2);
	CHECK(!strcmp(production_maps[0].source.symbol, "__kmalloc_noprof"));
	CHECK(!strcmp(production_maps[1].source.symbol, "__kmalloc_node_noprof"));
#ifdef CONFIG_SLAB_BUCKETS
	CHECK(production_maps[0].source.nargs == 2 && production_maps[0].execution_nargs == 5);
	CHECK(!memcmp(production_maps[0].arguments, good.arguments, sizeof(good.arguments)));
	CHECK(production_maps[1].source.nargs == 4 && production_maps[1].execution_nargs == 5);
	for (i = 0; i < 4; ++i) CHECK(production_maps[1].arguments[i] == KD_SERVICE_ARG_SOURCE0 + i);
	CHECK(production_maps[1].arguments[4] == KD_SERVICE_ARG_RETURN_IP && !production_maps[1].arguments[5]);
#else
	{ const unsigned char ordinary[6] = { KD_SERVICE_ARG_SOURCE0, KD_SERVICE_ARG_SOURCE1,
		KD_SERVICE_ARG_MINUS_ONE, KD_SERVICE_ARG_RETURN_IP, KD_SERVICE_ARG_UNUSED, KD_SERVICE_ARG_UNUSED };
	  const unsigned char node[6] = { KD_SERVICE_ARG_SOURCE0, KD_SERVICE_ARG_SOURCE1,
		KD_SERVICE_ARG_SOURCE2, KD_SERVICE_ARG_RETURN_IP, KD_SERVICE_ARG_UNUSED, KD_SERVICE_ARG_UNUSED };
	  CHECK(production_maps[0].source.nargs == 2 && production_maps[0].execution_nargs == 4);
	  CHECK(production_maps[1].source.nargs == 3 && production_maps[1].execution_nargs == 4);
	  CHECK(!memcmp(production_maps[0].arguments, ordinary, sizeof(ordinary)));
	  CHECK(!memcmp(production_maps[1].arguments, node, sizeof(node))); }
#endif
	for (i = 0; i < 2; ++i) CHECK(kd_service_call_mapped_valid(&production_maps[i]));

	for (i = 0; i < 12; ++i) {
		reset(); candidate = good;
		switch (i) {
		case 0: candidate.version++; break;
		case 1: candidate.execution_target = 0; break;
		case 2: candidate.execution_nargs = 7; break;
		case 3: candidate.reserved = 1; break;
		case 4: candidate.source.reserved = 1; break;
		case 5: candidate.source.context_kind = KD_SERVICE_CALL_ATOMIC_ORIGIN; break;
		case 6: candidate.source.nargs = 1; break;
		case 7: candidate.arguments[0] = KD_SERVICE_ARG_UNUSED; break;
		case 8: candidate.arguments[5] = KD_SERVICE_ARG_ZERO; break;
		case 9: candidate.arguments[0] = 255; break;
		case 10: candidate.source.target = 0; break;
		case 11: candidate.source.symbol = "bad name"; break;
		}
		CHECK(!kd_service_call_mapped_valid(&candidate));
		batch[0] = good; batch[1] = candidate;
		CHECK(kd_service_call_register_mapped(batch, 2, &owner) == -EINVAL);
		CHECK(kd_service_call_count == 0 && owner.references == 0);
		for (j = 0; j < KD_SERVICE_CALL_MAX; ++j) CHECK(!kd_service_call_entries[j].active);
	}
	reset();
	CHECK(kd_service_call_register_mapped(NULL, 1, &owner) == -EINVAL);
	CHECK(kd_service_call_register_mapped(&good, 0, &owner) == -EINVAL);
	CHECK(kd_service_call_register_mapped(&good, 129, &owner) == -EINVAL);
	batch[0] = batch[1] = good;
	CHECK(kd_service_call_register_mapped(batch, 2, &owner) == -EEXIST && !kd_service_call_count);
	CHECK(!kd_service_call_register_mapped(&good, 1, &owner));
	CHECK(kd_service_call_count == 1 && !owner.references);
	CHECK(kd_service_call_register_mapped(&good, 1, &owner) == -EEXIST && kd_service_call_count == 1);
	entry = kd_service_call_get(good.source.target);
	CHECK(entry && owner.references == 1 && atomic_read(&entry->users) == 1);
	saved = packet;
	CHECK(!kd_service_call_arguments(entry, &packet, 0x3456, &execution, arguments));
	CHECK(execution == good.execution_target && !memcmp(arguments, expected, sizeof(expected)));
	CHECK(!memcmp(&packet, &saved, sizeof(packet)));
	CHECK(kd_service_call_invocation_matches(entry, good.source.target, good.execution_target));
	CHECK(!kd_service_call_invocation_matches(entry, good.source.target, good.execution_target + 1));
	CHECK(!kd_service_call_invocation_matches(entry, good.source.target + 1, good.execution_target));
	CHECK(kd_service_call_arguments(entry, &packet, 0, &execution, arguments) == -EINVAL);
	packet.ip++;
	CHECK(kd_service_call_arguments(entry, &packet, 0x3456, &execution, arguments) == -EINVAL);
	packet = saved;
	CHECK(kd_service_call_unregister(&owner) == -EBUSY);
	kd_service_call_put(entry);
	CHECK(owner.references == 0 && !atomic_read(&entry->users));
	CHECK(kd_service_call_arguments(entry, &packet, 0x3456, &execution, arguments) == -EINVAL);
	source_info.state = KD_SOURCE_OPEN;
	CHECK(kd_service_call_unregister(&owner) == -EBUSY);
	source_info.state = 2;
	CHECK(!kd_service_call_unregister(&owner) && !entry->active);
	CHECK(!kd_service_call_get(good.source.target));

	/* Reverse dependencies must read the untouched packet, not earlier outputs. */
	reset(); candidate = good; candidate.source.nargs = candidate.execution_nargs = 6;
	for (i = 0; i < 6; ++i) candidate.arguments[i] = KD_SERVICE_ARG_SOURCE5 - i;
	CHECK(!kd_service_call_register_mapped(&candidate, 1, &owner));
	entry = kd_service_call_get(candidate.source.target);
	CHECK(!kd_service_call_arguments(entry, &packet, 0x3456, &execution, arguments));
	{ unsigned long reversed[6] = {79, 67, 53, 41, 29, 17};
	  CHECK(!memcmp(arguments, reversed, sizeof(reversed)) && !memcmp(&packet, &saved, sizeof(packet))); }
	kd_service_call_put(entry);

	/* An identity entry keeps its old bridge input path and leaves the vector alone. */
	reset(); CHECK(!kd_service_call_register(&good.source, 1, &owner));
	entry = kd_service_call_get(good.source.target);
	memset(arguments, 0x5a, sizeof(arguments)); memcpy(expected, arguments, sizeof(expected));
	execution = 99;
	CHECK(!kd_service_call_arguments(entry, &packet, 0x3456, &execution, arguments));
	CHECK(!execution && !memcmp(arguments, expected, sizeof(expected)));
	kd_service_call_put(entry);

	for (i = 0; i <= 2; ++i) {
		reset(); CHECK(!kd_service_call_register_mapped(&good, 1, &owner));
		fail_pin = i;
		CHECK(kd_service_calls_pin() == (i ? -ESTALE : 0));
		CHECK(pin_count == (i ? i : 2) && pins[0] == good.source.target);
		if (pin_count == 2) CHECK(pins[1] == good.execution_target);
		CHECK(kd_service_call_frozen && kd_service_call_register_mapped(&good, 1, &owner) == -EBUSY);
	}
	reset();
	for (i = 0; i < 80; ++i) {
		memset(names[i], 'q', 90); names[i][90] = 0;
		snprintf(names[i], 5, "%04u", i); names[i][4] = 'q';
		batch[i] = good; batch[i].source.symbol = names[i]; batch[i].source.target += i * 16;
	}
	CHECK(kd_service_call_register_mapped(batch, 80, &owner) == -ENOSPC && !kd_service_call_count);
	for (i = 0; i < KD_SERVICE_CALL_MAX; ++i) CHECK(!kd_service_call_entries[i].active);
	printf("Native argument mapping: %u checks, 0 failures\n", checks);
	return 0;
}
