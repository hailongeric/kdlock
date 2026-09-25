/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise real allocation/rollback and record helpers with tracked pages. */
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
	fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); \
} } while (0)
#define L1_CACHE_BYTES 64
#define __aligned(n) __attribute__((aligned(n)))
#define ____cacheline_aligned_in_smp __attribute__((aligned(64)))
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint8_t u8;
typedef uint16_t u16;
typedef struct { int counter; } atomic_t;
typedef struct { long counter; } atomic_long_t;
struct task_struct { int pid; };
struct list_head { struct list_head *next, *prev; };
struct qspinlock { uint32_t val; };
typedef struct qspinlock kd_spinlock_t;
#include "spin_storage_types.h"

/* Cover two full color cycles and both ends of every init rollback. */
#define CPUS 121
#define BUILD_BUG_ON(x) _Static_assert(!(x), #x)
#define BUG_ON(x) CHECK(!(x))
#define atomic_set(p, n) ((p)->counter = (n))
#define atomic_long_set(p, n) ((p)->counter = (n))
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, n) (*(p) = (n))
#define for_each_possible_cpu(i) for ((i) = 0; (i) < CPUS; (i)++)
#define per_cpu_ptr(p, i) (&(*(p))[i])
#define this_cpu_ptr(p) per_cpu_ptr(p, selected_cpu)
/* Keep the production object's attributes while substituting CPU storage.
 * The declaration itself is extracted with the allocator below. */
#define DEFINE_PER_CPU_SHARED_ALIGNED(type, name) \
	type name[CPUS] ____cacheline_aligned_in_smp

static struct kd_spin_cpu_state kd_spin_cpu[CPUS];
static struct kd_spin_continuation_stack *kd_spin_continuations[CPUS];
static struct kd_spin_continuation *kd_spin_native_root[CPUS];
static struct kd_spin_node *kd_spin_resume_nodes[CPUS];
static struct kd_spin_diag_slot kd_spin_diag_slots[KD_SPIN_DIAG_SLOTS];
static struct kd_spin_diag_cpu (*kd_spin_diag_cpu)[CPUS];
static unsigned int kd_spin_prefetch_mode = 2;
static int selected_cpu;
static int fail_at = -1, allocation_calls, allocated, freed;
static bool fail_stats;
static void *raw_allocations[CPUS], *stats_allocation;
static bool released[CPUS];

static void *allocate_stats(size_t bytes)
{
	CHECK(!stats_allocation);
	if (fail_stats)
		return NULL;
	stats_allocation = calloc(CPUS, bytes);
	CHECK(stats_allocation);
	return stats_allocation;
}
#define alloc_percpu(type) allocate_stats(sizeof(type))
static void free_percpu(void *p)
{
	if (!p)
		return;
	CHECK(p == stats_allocation);
	free(p);
	stats_allocation = NULL;
}

static void *vzalloc(size_t bytes)
{
	void *base;
	int index = allocation_calls++;

	CHECK(bytes == KD_SPIN_STORAGE_BYTES && index < CPUS);
	if (index == fail_at)
		return NULL;
	CHECK(posix_memalign(&base, 4096, bytes) == 0);
	memset(base, 0, bytes);
	raw_allocations[index] = base;
	allocated++;
	return base;
}

#ifdef NUMA_AWARE
#define cpu_to_node(cpu) ((cpu) / 20)
static void *vzalloc_node(size_t bytes, int node)
{
	CHECK(node == cpu_to_node(allocation_calls));
	return vzalloc(bytes);
}
#endif

static void vfree(void *p)
{
	if (!p)
		return;
	for (int i = 0; i < allocated; i++) {
		if (raw_allocations[i] != p)
			continue;
		CHECK(!released[i]);
		released[i] = true;
		freed++;
		free(p);
		return;
	}
	CHECK(false); /* Interior, truncated or foreign allocation address. */
}

#include "spin_storage_production.h"

static void reset(void)
{
	CHECK(!stats_allocation && !kd_spin_diag_cpu);
	CHECK(allocated == freed);
	for (int i = 0; i < CPUS; i++) {
		CHECK(!kd_spin_continuations[i]);
		CHECK(!kd_spin_cpu[i].wait_stack_top);
	}
	memset(raw_allocations, 0, sizeof(raw_allocations));
	memset(released, 0, sizeof(released));
	allocation_calls = allocated = freed = 0;
	fail_at = -1;
	fail_stats = false;
}

static void check_geometry(void)
{
	bool colors[KD_SPIN_CONT_BYTES / L1_CACHE_BYTES] = { false };
	size_t color_count = 1 + (KD_SPIN_CONT_BYTES -
		sizeof(struct kd_spin_continuation_stack)) / L1_CACHE_BYTES;
	const size_t pair = 2 * L1_CACHE_BYTES;

	/* Align the array without changing node layout or each node's stride. */
	CHECK(__alignof__(kd_spin_nodes) >= pair);
	CHECK((uintptr_t)kd_spin_nodes % pair == 0);
	CHECK(_Alignof(struct kd_spin_node) == L1_CACHE_BYTES);
	CHECK(sizeof(struct kd_spin_node) == pair);
	CHECK(offsetof(struct kd_spin_node, completed) == L1_CACHE_BYTES);
	CHECK(offsetof(struct kd_spin_node, locked) == L1_CACHE_BYTES + 1);

	/* Check actual array addresses as well as the type's offset and stride:
	 * no waiter counter may share a pair with either adjacent slot's reads. */
	CHECK(_Alignof(struct kd_spin_diag_slot) == pair);
	CHECK(offsetof(struct kd_spin_diag_slot, waiter_count) == pair);
	CHECK(sizeof(struct kd_spin_diag_slot) == 2 * pair);
	for (unsigned int i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
		struct kd_spin_diag_slot *slot = &kd_spin_diag_slots[i];
		uintptr_t identity = (uintptr_t)&slot->addr;
		uintptr_t disable = (uintptr_t)&slot->jit_disabled;
		uintptr_t waiter = (uintptr_t)&slot->waiter_count;

		CHECK(identity % pair == 0);
		CHECK(disable / pair == identity / pair);
		CHECK(waiter / pair == identity / pair + 1);
		if (i + 1 < KD_SPIN_DIAG_SLOTS)
			CHECK((uintptr_t)&kd_spin_diag_slots[i + 1].addr / pair ==
			      waiter / pair + 1);
	}

	CHECK(color_count > 1 && color_count * 2 < CPUS);
	for (selected_cpu = 0; selected_cpu < CPUS; selected_cpu++) {
		struct kd_spin_continuation_stack *stack =
			kd_spin_continuations[selected_cpu];
		unsigned char *base = raw_allocations[selected_cpu];
		unsigned char *wait_begin = base + KD_SPIN_CONT_BYTES;
		unsigned char *wait_end = base + KD_SPIN_STORAGE_BYTES;
		size_t offset = (unsigned char *)stack - base;

		CHECK(offset % L1_CACHE_BYTES == 0);
		CHECK(offset == kd_spin_continuation_offset(selected_cpu));
		CHECK(offset + sizeof(*stack) <= KD_SPIN_CONT_BYTES);
		CHECK(kd_spin_cpu[selected_cpu].wait_stack_top == wait_end);
		CHECK((size_t)(wait_end - wait_begin) == KD_SPIN_WAIT_STACK_SIZE);
		CHECK((uintptr_t)stack % _Alignof(*stack) == 0);
		if ((size_t)selected_cpu < color_count) {
			CHECK(!colors[offset / L1_CACHE_BYTES]);
			colors[offset / L1_CACHE_BYTES] = true;
		}
		CHECK(kd_spin_continuation_offset(selected_cpu + color_count) == offset);
		memset(wait_begin, 0xa5, KD_SPIN_WAIT_STACK_SIZE);
		for (unsigned int j = 0; j < KD_SPIN_CONT_SLOTS; j++) {
			struct kd_spin_continuation *record = kd_spin_continuation_reserve();

			CHECK(record == &stack->records[j]);
			CHECK(record->storage == stack && !record->retired);
			CHECK((unsigned char *)(record + 1) <= wait_begin);
		}
		CHECK(!kd_spin_continuation_reserve());
		/* Releasing below a live top retains the hole until the top retires. */
		kd_spin_continuation_release(&stack->records[0]);
		CHECK(stack->top == KD_SPIN_CONT_SLOTS);
		for (unsigned int j = KD_SPIN_CONT_SLOTS; j-- > 1;)
			kd_spin_continuation_release(&stack->records[j]);
		CHECK(stack->top == 0);
		for (size_t j = 0; j < KD_SPIN_WAIT_STACK_SIZE; j++)
			CHECK(wait_begin[j] == 0xa5);
	}
}

int main(void)
{
	reset();
	CHECK(kd_spinlock_init() == 0);
	CHECK(allocated == CPUS);
	check_geometry();
	kd_spinlock_free_percpu();
	reset();
	/* Every successful earlier allocation must be freed on any later failure. */
	for (int failed_cpu = 0; failed_cpu < CPUS; failed_cpu++) {
		fail_at = failed_cpu;
		CHECK(kd_spinlock_init() == -ENOMEM);
		CHECK(allocation_calls == failed_cpu + 1);
		CHECK(allocated == failed_cpu && freed == allocated);
		reset();
	}
	fail_stats = true;
	CHECK(kd_spinlock_init() == -ENOMEM);
	CHECK(!allocation_calls);
	reset();
	puts("PASS spin storage: real layouts, diagnostic pair separation, colors, all records, unchanged wait stack, original-base free and 122 allocation failure points");
	return 0;
}
