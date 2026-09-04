/* Verify the bounded hot-lock promotion state machine in kd_hotlock.c. */
#include "mock_kernel.h"
#include "test_harness.h"

#define MOCK_TABLE_SIZE 8
#define MOCK_WARMUP_CYCLES 1000000000UL
#define MOCK_INITIAL_WINDOW 2500000000UL
#define MOCK_SAMPLE_TARGET 10000U

enum mock_hotlock_status {
	MOCK_HOTLOCK_INIT = 0,
	MOCK_HOTLOCK_CHECKING,
	MOCK_HOTLOCK_DELEGATE,
	MOCK_HOTLOCK_IGNORE,
};

struct mock_hotlock_state {
	unsigned long lock_addr;
	unsigned long begin_cycles;
	unsigned long end_cycles;
	unsigned int samples;
	enum mock_hotlock_status status;
};

static struct mock_hotlock_state states[MOCK_TABLE_SIZE];
static unsigned long start_cycles;
static unsigned long window_cycles;

static struct mock_hotlock_state *mock_lookup(unsigned long lock_addr,
					      bool create)
{
	unsigned int pos = lock_addr % MOCK_TABLE_SIZE;
	unsigned int probes;

	if (!lock_addr)
		return NULL;

	for (probes = 0; probes < MOCK_TABLE_SIZE; probes++) {
		struct mock_hotlock_state *state = &states[pos];

		if (state->lock_addr == lock_addr)
			return state;
		if (!state->lock_addr) {
			if (!create)
				return NULL;
			state->lock_addr = lock_addr;
			return state;
		}
		pos = (pos + 1) % MOCK_TABLE_SIZE;
	}

	return NULL;
}

static void reset_states(void)
{
	memset(states, 0, sizeof(states));
	start_cycles = 0;
	window_cycles = MOCK_INITIAL_WINDOW;
	mock_tsc = 1000000000UL;
}

static int mock_record(unsigned long lock_addr)
{
	struct mock_hotlock_state *state;
	unsigned long now = rdtsc_ordered();

	if (!start_cycles) {
		start_cycles = now;
		return 0;
	}
	if (now - start_cycles < MOCK_WARMUP_CYCLES || !lock_addr)
		return 0;

	state = mock_lookup(lock_addr, true);
	if (!state)
		return 0;
	if (state->status == MOCK_HOTLOCK_DELEGATE)
		return 1;

	state->samples++;
	if (state->status == MOCK_HOTLOCK_IGNORE)
		return 0;
	if (state->status == MOCK_HOTLOCK_INIT) {
		state->status = MOCK_HOTLOCK_CHECKING;
		state->begin_cycles = now;
		return 0;
	}

	state->end_cycles = now;
	if (state->end_cycles - state->begin_cycles >= window_cycles) {
		state->status = MOCK_HOTLOCK_IGNORE;
	} else if (state->samples == MOCK_SAMPLE_TARGET) {
		state->status = MOCK_HOTLOCK_DELEGATE;
		return 1;
	}

	return 0;
}

static bool mock_is_promoted(unsigned long lock_addr)
{
	struct mock_hotlock_state *state = mock_lookup(lock_addr, false);

	return state && state->status == MOCK_HOTLOCK_DELEGATE;
}

static void pass_warmup(void)
{
	mock_record(0xaaaa);
	mock_tsc += MOCK_WARMUP_CYCLES + 1;
}

TEST(initial_state_is_not_delegate)
{
	reset_states();
	ASSERT_EQ(mock_is_promoted(0x1234), false);
}

TEST(promotes_after_fast_samples)
{
	unsigned int i;
	int promoted = 0;

	reset_states();
	pass_warmup();
	for (i = 0; i < MOCK_SAMPLE_TARGET; i++) {
		mock_tsc++;
		if (mock_record(0xaaaa)) {
			promoted = 1;
			break;
		}
	}

	ASSERT_EQ(promoted, 1);
	ASSERT_EQ(mock_is_promoted(0xaaaa), true);
}

TEST(ignores_slow_lock)
{
	struct mock_hotlock_state *state;

	reset_states();
	pass_warmup();
	mock_record(0xbbbb);
	mock_tsc += MOCK_INITIAL_WINDOW;
	mock_record(0xbbbb);
	state = mock_lookup(0xbbbb, false);

	ASSERT_NE(state, NULL);
	ASSERT_EQ((int)state->status, (int)MOCK_HOTLOCK_IGNORE);
	ASSERT_EQ(mock_is_promoted(0xbbbb), false);
}

TEST(collisions_remain_independent)
{
	struct mock_hotlock_state *first;
	struct mock_hotlock_state *second;

	reset_states();
	first = mock_lookup(1, true);
	second = mock_lookup(1 + MOCK_TABLE_SIZE, true);

	ASSERT_NE(first, NULL);
	ASSERT_NE(second, NULL);
	ASSERT_NE(first, second);
	ASSERT_EQ(first->lock_addr, 1UL);
	ASSERT_EQ(second->lock_addr, 1UL + MOCK_TABLE_SIZE);
}

TEST(full_table_fails_closed)
{
	unsigned int i;

	reset_states();
	for (i = 0; i < MOCK_TABLE_SIZE; i++)
		ASSERT_NE(mock_lookup(i + 1, true), NULL);

	ASSERT_EQ(mock_lookup(0xdeadbeef, true), NULL);
	ASSERT_EQ(mock_is_promoted(0xdeadbeef), false);
}

int main(void)
{
	printf("=== test_hotlock_state ===\n");
	RUN_TEST(initial_state_is_not_delegate);
	RUN_TEST(promotes_after_fast_samples);
	RUN_TEST(ignores_slow_lock);
	RUN_TEST(collisions_remain_independent);
	RUN_TEST(full_table_fails_closed);
	REPORT();
}
