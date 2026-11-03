/* SPDX-License-Identifier: GPL-2.0 */
/* Production source decisions with deterministic owner/query primitives.
 * This does not simulate executable allocation or live module removal. */
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned int u32;
typedef unsigned long long u64;
typedef long long s64;
#include "kd_source_api.h"
#include "kd_generated_text.h"

static unsigned int checks, depth, query_calls;
#define CHECK(expr) do { checks++; if (!(expr)) { \
	fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #expr); exit(1); } } while (0)
#define BUG_ON(expr) CHECK(!(expr))
#define U64_MAX ULLONG_MAX
#define PAGE_SIZE 4096UL
#define CORE 0x100000000UL
#define ORDINARY 0x200000000UL
#define GENERATED 0x300000000UL
#define READ_ONCE(value) (value)
#define WRITE_ONCE(value, next) ((value) = (next))
#define min(a, b) ((a) < (b) ? (a) : (b))
#define DEFINE_RAW_SPINLOCK(name) unsigned int name
#define raw_spin_lock_irqsave(lock, flags) do { \
	(flags) = depth; CHECK(!*(lock)); *(lock) = 1; depth++; } while (0)
#define raw_spin_unlock_irqrestore(lock, flags) do { \
	CHECK(*(lock) && depth); *(lock) = 0; depth = (flags); } while (0)
typedef long long atomic64_t;
#define ATOMIC64_INIT(value) (value)
#define atomic64_read(ptr) (*(ptr))
#define atomic64_set(ptr, value) (*(ptr) = (value))
#define atomic64_dec_return(ptr) (--*(ptr))
#define atomic64_fetch_or(value, ptr) ({ s64 old_ = *(ptr); *(ptr) |= (value); old_; })
static bool atomic64_try_cmpxchg(atomic64_t *ptr, s64 *old, s64 next)
{
	if (*ptr != *old) { *old = *ptr; return false; }
	*ptr = next;
	return true;
}

enum { MODULE_STATE_LIVE, MODULE_STATE_COMING, MODULE_STATE_GOING };
enum mod_mem_type { MOD_TEXT, MOD_DATA, MOD_INIT_TEXT, MOD_MEM_NUM_TYPES };
#define mod_mem_type_is_init(type) ((type) == MOD_INIT_TEXT)
struct module {
	int state, refs;
	struct { void *base; unsigned long size; } mem[MOD_MEM_NUM_TYPES];
};
static struct module provider, owners[KD_SOURCE_MAX_MODULES + 1];
#define THIS_MODULE (&provider)
static bool try_module_get(struct module *owner)
{
	CHECK(owner);
	if (owner->state == MODULE_STATE_GOING)
		return false;
	owner->refs++;
	return true;
}
static void module_put(struct module *owner)
{
	CHECK(owner && owner->refs > 0);
	owner->refs--;
}
static struct module *module_address(unsigned long address)
{
	CHECK(depth);
	for (unsigned int i = 0; i <= KD_SOURCE_MAX_MODULES; i++)
		for (unsigned int kind = MOD_TEXT; kind < MOD_MEM_NUM_TYPES; kind++) {
			unsigned long base = (unsigned long)owners[i].mem[kind].base;
			if (address >= base && address - base < owners[i].mem[kind].size)
				return &owners[i];
		}
	return NULL;
}
static unsigned long query_symbol;
static unsigned long kallsyms_lookup_name(const char *name)
{
	if (!strcmp(name, "__module_address")) return (unsigned long)module_address;
	if (!strcmp(name, "kd_generated_text_lookup")) return query_symbol;
	if (!strcmp(name, "_stext")) return CORE;
	if (!strcmp(name, "_etext")) return CORE + 0x2000;
	if (!strcmp(name, "__init_begin")) return CORE + 0x3000;
	if (!strcmp(name, "__init_end")) return CORE + 0x4000;
	if (!strcmp(name, "_end")) return CORE + 0x8000;
	return 0;
}

#include "generated_source_production.h"

static struct kd_generated_text_extent reply;
static int query_result;
static int generated_query(unsigned long address, struct kd_generated_text_extent *extent)
{
	(void)address;
	CHECK(depth);
	query_calls++;
	if (query_result)
		return query_result;
	*extent = reply;
	if (extent->owner && !try_module_get(extent->owner))
		return -ESTALE;
	return 0;
}
static void reset(void)
{
	CHECK(!depth);
	for (unsigned int i = 0; i <= KD_SOURCE_MAX_MODULES; i++)
		CHECK(!owners[i].refs);
	CHECK(!provider.refs);
	memset(owners, 0, sizeof(owners));
	memset(&provider, 0, sizeof(provider));
	for (unsigned int i = 0; i <= KD_SOURCE_MAX_MODULES; i++) {
		owners[i].mem[MOD_TEXT].base = (void *)(ORDINARY + i * 0x10000);
		owners[i].mem[MOD_TEXT].size = PAGE_SIZE;
	}
	query_symbol = 0;
	CHECK(!kd_source_init());
	query_calls = 0;
	query_result = 0;
	reply = (struct kd_generated_text_extent) {
		.start = GENERATED, .end = GENERATED + PAGE_SIZE,
		.abi = KD_GENERATED_TEXT_ABI_VERSION, .kind = KD_GENERATED_TEXT_CORE_ITS,
	};
}
static void retire(void)
{
	CHECK(!kd_source_begin_retire());
	kd_source_finish_retire();
	CHECK(kd_sources.state == KD_SOURCE_RETIRED && !kd_sources.modules);
	for (unsigned int i = 0; i <= KD_SOURCE_MAX_MODULES; i++)
		CHECK(!owners[i].refs);
}
static void core_and_missing_query(void)
{
	reset();
	CHECK(!kd_source_pin_root(CORE + 1) && !query_calls);
	CHECK(kd_source_pin_root(GENERATED) == -ESTALE && !query_calls);
	kd_generated_lookup = generated_query;
	CHECK(!kd_source_pin_root(GENERATED + 32));
	CHECK(!kd_sources.modules && !provider.refs && query_calls == 1);
	CHECK(kd_source_pin_root(CORE + 0x3000) == -EPERM && query_calls == 1);
	CHECK(kd_source_writer_get());
	CHECK(!kd_source_pin_range(GENERATED + PAGE_SIZE - 8, 8));
	CHECK(kd_source_pin_range(GENERATED + PAGE_SIZE - 8, 9) == -EPROTO);
	query_result = -ENOENT;
	CHECK(kd_source_pin_range(GENERATED, 1) == -ESTALE);
	CHECK(!kd_sources.modules && !provider.refs);
	query_result = -ENODATA;
	CHECK(kd_source_pin_range(GENERATED, 1) == -ENODATA);
	kd_source_writer_put();
	retire();
	unsigned int calls = query_calls;
	CHECK(kd_source_pin_root(GENERATED) == -ESHUTDOWN && query_calls == calls);
	CHECK(!kd_source_writer_get() && !kd_source_frame_get());
	reset();
	query_symbol = ORDINARY;
	CHECK(kd_source_init() == -EOPNOTSUPP);
	query_symbol = 0;
	CHECK(!kd_source_init());
	retire();
}
static void module_reference_paths(void)
{
	for (unsigned int ordinary_first = 0; ordinary_first < 2; ordinary_first++) {
		reset();
		kd_generated_lookup = generated_query;
		reply.kind = KD_GENERATED_TEXT_MODULE_ITS;
		reply.owner = &owners[0];
		if (ordinary_first)
			CHECK(!kd_source_pin_root(ORDINARY));
		CHECK(!kd_source_pin_root(GENERATED + 32));
		CHECK(!kd_source_pin_root(GENERATED + 64));
		CHECK(!kd_source_pin_root(ORDINARY));
		CHECK(kd_sources.modules == 1 && owners[0].refs == 1);
		CHECK(kd_source_writer_get());
		CHECK(kd_source_begin_retire() == -EBUSY && owners[0].refs == 1);
		CHECK(!kd_source_pin_range(GENERATED, 1));
		kd_source_writer_put();
		CHECK(owners[0].refs == 1);
		retire();
	}
}
static void malformed_replies(void)
{
	for (unsigned int variant = 0; variant < 10; variant++) {
		reset();
		kd_generated_lookup = generated_query;
		reply.kind = KD_GENERATED_TEXT_MODULE_ITS;
		reply.owner = &owners[0];
		switch (variant) {
		case 0: reply.abi++; break;
		case 1: reply.kind = 0; break;
		case 2: reply.start++; break;
		case 3: reply.end = reply.start; break;
		case 4: reply.end += PAGE_SIZE; break;
		case 5: reply.start += PAGE_SIZE; reply.end += PAGE_SIZE; break;
		case 6: reply.owner = NULL; break;
		case 7: reply.kind = KD_GENERATED_TEXT_CORE_ITS; break;
		case 8: owners[0].state = MODULE_STATE_COMING; break;
		case 9: owners[0].state = MODULE_STATE_GOING; break;
		}
		CHECK(kd_source_pin_root(GENERATED) == (variant >= 8 ? -ESTALE : -EPROTO));
		CHECK(!owners[0].refs && !kd_sources.modules);
		retire();
	}
}
static void bounded_owner_storage(void)
{
	reset();
	kd_generated_lookup = generated_query;
	for (unsigned int i = 0; i < KD_SOURCE_MAX_MODULES; i++)
		CHECK(!kd_source_pin_root(ORDINARY + i * 0x10000));
	reply.kind = KD_GENERATED_TEXT_MODULE_ITS;
	reply.owner = &owners[KD_SOURCE_MAX_MODULES];
	CHECK(kd_source_pin_root(GENERATED) == -ENOSPC);
	CHECK(!reply.owner->refs && kd_sources.modules == KD_SOURCE_MAX_MODULES);
	reply.owner = &owners[0];
	CHECK(!kd_source_pin_root(GENERATED) && owners[0].refs == 1);
	retire();
}
int main(void)
{
	core_and_missing_query();
	module_reference_paths();
	malformed_replies();
	bounded_owner_storage();
	printf("production generated source: %u checks, 0 failures\n", checks);
	return 0;
}
