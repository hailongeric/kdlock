/*
 * test_hotlock_state.c — verify the hot-lock promotion state machine.
 *
 * Simulates count_uaddr_cnt logic: INIT → CHECKING → DELEGATE after 10K hits
 * within the time window, or IGNORE if too slow.
 */
#include "mock_kernel.h"
#include "test_harness.h"

/* Replicate state definitions from exe.h */
#define KD_UADDR_INIT      -1
#define KD_UADDR_CHECKING   0
#define KD_UADDR_DELEGATE   1
#define KD_UADDR_IGNORE    -2
#define KD_MAX_UADDR       131071

struct kd_uaddr_state {
	unsigned long uaddr;
	unsigned long begin;
	unsigned long end;
	int state;
	int cnt;
	atomic_t is_delegating;
};

static struct kd_uaddr_state states[64];
static atomic_long_t start_work_cycle = { .counter = 0 };
static atomic_long_t count_uaddr_time = { .counter = 2500000000L };

static struct kd_uaddr_state *get_state(unsigned long uaddr) {
	int pos = uaddr % 64;
	while (states[pos].state != KD_UADDR_INIT && states[pos].uaddr != uaddr)
		pos = (pos + 1) % 64;
	if (states[pos].uaddr == 0)
		states[pos].uaddr = uaddr;
	return &states[pos];
}

static void init_states(void) {
	for (int i = 0; i < 64; i++) {
		states[i].uaddr = 0;
		states[i].begin = 0;
		states[i].end = 0;
		states[i].state = KD_UADDR_INIT;
		states[i].cnt = 0;
		atomic_set(&states[i].is_delegating, 0);
	}
	start_work_cycle.counter = 0;
	count_uaddr_time.counter = 2500000000L;
	mock_tsc = 1000000000UL;
}

/* Simplified count_uaddr_cnt (same logic, no NUMA bits) */
static int mock_count_uaddr_cnt(unsigned long uaddr) {
	if (atomic_long_read(&start_work_cycle) == 0) {
		atomic_long_cmpxchg(&start_work_cycle, 0, rdtsc_ordered());
		return 0;
	} else if (rdtsc_ordered() - atomic_long_read(&start_work_cycle) < 1000000000)
		return 0;

	struct kd_uaddr_state *u = get_state(uaddr);
	if (u->state == KD_UADDR_DELEGATE) return 1;
	if (u->state == KD_UADDR_IGNORE) { u->cnt++; return 0; }

	u->cnt++;
	if (u->state == KD_UADDR_INIT) {
		u->state = KD_UADDR_CHECKING;
		u->begin = rdtsc_ordered();
		return 0;
	}
	if (u->state == KD_UADDR_CHECKING) {
		u->end = rdtsc_ordered();
		if (u->end - u->begin >= (unsigned long)atomic_long_read(&count_uaddr_time)) {
			u->state = KD_UADDR_IGNORE;
			return 0;
		} else if (u->cnt >= 10000) {
			u->state = KD_UADDR_DELEGATE;
			return 1;
		}
	}
	return 0;
}

static int mock_check_uaddr_state(unsigned long uaddr) {
	struct kd_uaddr_state *u = get_state(uaddr);
	return u->state == KD_UADDR_DELEGATE ? 1 : 0;
}

TEST(initial_state_not_delegate) {
	init_states();
	ASSERT_EQ(mock_check_uaddr_state(0x1234), 0);
}

TEST(promote_after_10k_fast_hits) {
	init_states();
	/* First call starts the work cycle clock */
	mock_count_uaddr_cnt(0xAAAA);
	/* Advance TSC past the 1B warmup threshold */
	mock_tsc += 1100000000UL;

	/* Hit 10000 times quickly (TSC advances slowly) */
	int promoted = 0;
	for (int i = 0; i < 11000; i++) {
		mock_tsc += 1; /* very fast hits */
		if (mock_count_uaddr_cnt(0xAAAA)) {
			promoted = 1;
			break;
		}
	}
	ASSERT_EQ(promoted, 1);
	ASSERT_EQ(mock_check_uaddr_state(0xAAAA), 1);
}

TEST(ignore_if_too_slow) {
	init_states();
	mock_count_uaddr_cnt(0xBBBB);
	mock_tsc += 1100000000UL;

	/* Hit slowly — each hit takes a long time */
	for (int i = 0; i < 100; i++) {
		mock_tsc += 500000000UL; /* very slow */
		mock_count_uaddr_cnt(0xBBBB);
	}
	struct kd_uaddr_state *u = get_state(0xBBBB);
	ASSERT_EQ(u->state, KD_UADDR_IGNORE);
	ASSERT_EQ(mock_check_uaddr_state(0xBBBB), 0);
}

TEST(different_addrs_independent) {
	init_states();
	mock_count_uaddr_cnt(0x1111);
	mock_tsc += 1100000000UL;

	/* Promote addr 0x1111 */
	for (int i = 0; i < 11000; i++) {
		mock_tsc += 1;
		mock_count_uaddr_cnt(0x1111);
	}
	ASSERT_EQ(mock_check_uaddr_state(0x1111), 1);
	ASSERT_EQ(mock_check_uaddr_state(0x2222), 0);
}

int main(void) {
	printf("=== test_hotlock_state ===\n");
	RUN_TEST(initial_state_not_delegate);
	RUN_TEST(promote_after_10k_fast_hits);
	RUN_TEST(ignore_if_too_slow);
	RUN_TEST(different_addrs_independent);
	REPORT();
}
