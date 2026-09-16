/* SPDX-License-Identifier: GPL-2.0 */
/* Deterministic TSC/allocation inputs for the extracted hotlock sampler.
 * Promotion transitions are checked here, not natural contention or JIT. */
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned long atomic_long_t;
static unsigned long now;
static int checks, failures;
static bool fail_alloc;
/* Inject another caller before the table lock is acquired, never while held. */
static void (*before_table_lock)(void);

/* Run one queued producer before acquisition, without recursively injecting. */
static void run_table_interleave(void)
{
	void (*call)(void) = before_table_lock;

	before_table_lock = NULL;
	if (call)
		call();
}

#define ____cacheline_aligned __attribute__((aligned(64)))
#define DEFINE_RAW_SPINLOCK(name) int name
#define atomic_long_read(p) (*(p))
#define atomic_long_set(p, value) (*(p) = (value))
#define array_size(count, size) ((count) * (size))
#define raw_spin_lock_irqsave(lock, flags) \
	do {                               \
		(void)(lock);              \
		(flags) = 0;               \
		run_table_interleave();    \
	} while (0)
#define raw_spin_unlock_irqrestore(lock, flags) \
	do {                                    \
		(void)(lock);                   \
		(void)(flags);                  \
	} while (0)
#define KD_PR_INFO(...)                      \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)
#define CHECK(expr)                                                     \
	do {                                                            \
		checks++;                                               \
		if (!(expr)) {                                          \
			fprintf(stderr, "FAIL line %d: %s\n", __LINE__, \
				#expr);                                 \
			failures++;                                     \
		}                                                       \
	} while (0)

static unsigned long rdtsc_ordered(void)
{
	return now;
}
static unsigned long atomic_long_cmpxchg(atomic_long_t *p, unsigned long old,
					 unsigned long value)
{
	unsigned long actual = *p;
	if (actual == old)
		*p = value;
	return actual;
}
static void *vzalloc(size_t size)
{
	void *p;
	if (fail_alloc || posix_memalign(&p, 64, size))
		return NULL;
	memset(p, 0, size);
	return p;
}
static void vfree(void *p)
{
	free(p);
}

#include "hotlock_production.h"

static void start_sampling(void)
{
	CHECK(kd_hotlock_init() == 0);
	now = 1;
	CHECK(kd_hotlock_record(1) == 0);
	CHECK(!kd_hotlock_is_promoted(1));
	now += KD_HOTLOCK_WARMUP_CYCLES - 1;
	CHECK(kd_hotlock_record(1) == 0);
	now++;
}

static void check_inflight_window(void)
{
	unsigned long a_start, b_start;
	unsigned int i;
	struct kd_hotlock_state *a;

	start_sampling();
	a_start = now;
	CHECK(kd_hotlock_record(1) == 0);
	now += 100;
	b_start = now;
	CHECK(kd_hotlock_record(2) == 0);
	for (i = 1; i < KD_HOTLOCK_SAMPLE_TARGET; i++) {
		now = b_start + 24983118UL * i / (KD_HOTLOCK_SAMPLE_TARGET - 1);
		kd_hotlock_record(2);
	}
	CHECK(kd_hotlock_is_promoted(2));
	now = a_start + 25016220UL;
	kd_hotlock_record(1);
	a = kd_hotlock_state_get(1);
	CHECK(a && a->status == KD_HOTLOCK_CHECKING);
	for (i = 2; i < KD_HOTLOCK_SAMPLE_TARGET; i++) {
		now++;
		kd_hotlock_record(1);
	}
	CHECK(kd_hotlock_is_promoted(1));
	CHECK(kd_hotlock_record(1) == 1);

	/* A's and B's observations must not change a new lock's own deadline. */
	CHECK(kd_hotlock_record(3) == 0);
	CHECK(kd_hotlock_state_get(3)->sample_window == KD_HOTLOCK_INITIAL_WINDOW);
	now += KD_HOTLOCK_INITIAL_WINDOW;
	CHECK(kd_hotlock_record(3) == 0);
	CHECK(kd_hotlock_state_get(3)->status == KD_HOTLOCK_IGNORE);
	CHECK(kd_hotlock_record(3) == 0);
	CHECK(!kd_hotlock_is_promoted(3));
	kd_hotlock_exit();
}

/* Supply acquisition timestamps to the production sampler, not a copied policy.
 * The final sample fixes the duration exactly, including the deadline boundary. */
static int sample_lock(unsigned long lock, unsigned long duration)
{
	unsigned long begin = now;
	int promoted = 0;

	CHECK(kd_hotlock_record(lock) == 0);
	CHECK(kd_hotlock_state_get(lock)->sample_window == KD_HOTLOCK_INITIAL_WINDOW);
	for (unsigned int i = 1; i < KD_HOTLOCK_SAMPLE_TARGET; i++) {
		now = begin + duration * i / (KD_HOTLOCK_SAMPLE_TARGET - 1);
		promoted = kd_hotlock_record(lock);
		if (i + 1 < KD_HOTLOCK_SAMPLE_TARGET)
			CHECK(promoted == 0);
	}
	CHECK(kd_hotlock_state_get(lock)->samples == KD_HOTLOCK_SAMPLE_TARGET);
	return promoted;
}

/* Equal per-lock observations must produce equal decisions in both discovery
 * orders. A fast unrelated lock must not permanently suppress a later B. */
static void check_discovery_order(void)
{
	const unsigned long durations[] = { 1000000UL, 100000000UL };

	for (unsigned int order = 0; order < 2; order++) {
		start_sampling();
		CHECK(sample_lock(1, durations[order]) == 1);
		CHECK(sample_lock(2, durations[1 - order]) == 1);
		CHECK(kd_hotlock_is_promoted(1) && kd_hotlock_is_promoted(2));
		/* Independence does not waive the original deadline or sample quota.
		 * Just inside the window may promote; equality must remain native. */
		CHECK(sample_lock(3, KD_HOTLOCK_INITIAL_WINDOW - 1) == 1);
		CHECK(sample_lock(4, KD_HOTLOCK_INITIAL_WINDOW) == 0);
		CHECK(kd_hotlock_state_get(4)->status == KD_HOTLOCK_IGNORE);
		CHECK(kd_hotlock_record(4) == 0);
		CHECK(!kd_hotlock_is_promoted(4));
		kd_hotlock_exit();
	}
}

/* A later caller may acquire the table lock first. Use the real producer for
 * both updates, with only scheduling/TSC substituted; no state is fabricated. */
static void intervening_first_sample(void)
{
	now += 100;
	CHECK(kd_hotlock_record(1) == 0);
	now += 100;
}

static void check_serialized_timestamp(void)
{
	struct kd_hotlock_state *state;
	unsigned long started;

	start_sampling();
	started = now;
	before_table_lock = intervening_first_sample;
	CHECK(kd_hotlock_record(1) == 0);
	state = kd_hotlock_state_get(1);
	CHECK(!before_table_lock && state->samples == 2);
	CHECK(state->status == KD_HOTLOCK_CHECKING);
	CHECK(state->begin_cycles == started + 100);
	CHECK(state->end_cycles == started + 200);
	kd_hotlock_exit();
}

static void check_lifecycle_and_capacity(void)
{
	struct kd_hotlock_state *first, *second;

	fail_alloc = true;
	CHECK(kd_hotlock_init() == -ENOMEM);
	CHECK(!kd_hotlock_state_get(1));
	CHECK(!kd_hotlock_is_promoted(1));
	fail_alloc = false;
	start_sampling();
	CHECK(sizeof(struct kd_hotlock_state) == 64);
	CHECK(!kd_hotlock_state_get(0));
	CHECK(kd_hotlock_record(0) == 0);
	first = kd_hotlock_state_get(1);
	second = kd_hotlock_state_get(1 + KD_HOTLOCK_TABLE_SIZE);
	CHECK(first && second && first != second);
	CHECK(kd_hotlock_state_get(1) == first);
	CHECK(first->lock_addr == 1 &&
	      second->lock_addr == 1 + KD_HOTLOCK_TABLE_SIZE);
	kd_hotlock_exit();
	start_sampling();
	for (unsigned int i = 1; i <= KD_HOTLOCK_TABLE_SIZE; i++)
		CHECK(kd_hotlock_state_get(i) != NULL);
	CHECK(!kd_hotlock_state_get(0xdeadbeef));
	CHECK(kd_hotlock_record(0xdeadbeef) == 0);
	CHECK(!kd_hotlock_is_promoted(0xdeadbeef));
	kd_hotlock_exit();
	CHECK(!kd_hotlock_state_get(1));
}

int main(void)
{
	check_inflight_window();
	check_discovery_order();
	check_serialized_timestamp();
	check_lifecycle_and_capacity();
	printf("hotlock production sampling: %d checks, %d failures, slot=%zu bytes\n",
	       checks, failures, sizeof(struct kd_hotlock_state));
	return failures != 0;
}
