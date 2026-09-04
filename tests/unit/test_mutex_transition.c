/*
 * test_mutex_transition.c — verify original-to-shadow mutex promotion rules.
 *
 * The real hook uses struct mutex::owner to route unlock and keeps an
 * origin-user count so the independent shadow mutex cannot overlap an
 * original owner or waiter while a hot lock is being promoted.
 */
#include "mock_kernel.h"
#include "test_harness.h"

#define KD_UADDR_CHECKING 0
#define KD_UADDR_DELEGATE 1

struct transition_state {
	int state;
	atomic_t origin_users;
};

static void begin_origin_candidate(struct transition_state *state)
{
	state->origin_users.counter++;
}

static bool recheck_and_use_origin(struct transition_state *state)
{
	if (state->state != KD_UADDR_DELEGATE)
		return true;
	state->origin_users.counter--;
	return false;
}

static bool shadow_can_enter(struct transition_state *state)
{
	return state->state == KD_UADDR_DELEGATE &&
	       atomic_read(&state->origin_users) == 0;
}

static void finish_origin_unlock(struct transition_state *state)
{
	if (state->origin_users.counter > 0)
		state->origin_users.counter--;
}

TEST(origin_holder_blocks_shadow_after_promotion) {
	struct transition_state state = {
		.state = KD_UADDR_CHECKING,
		.origin_users = { .counter = 0 },
	};

	begin_origin_candidate(&state);
	ASSERT(recheck_and_use_origin(&state));
	state.state = KD_UADDR_DELEGATE;
	ASSERT_EQ(shadow_can_enter(&state), false);

	finish_origin_unlock(&state);
	ASSERT_EQ(shadow_can_enter(&state), true);
}

TEST(origin_waiters_all_drain_before_shadow) {
	struct transition_state state = {
		.state = KD_UADDR_CHECKING,
		.origin_users = { .counter = 0 },
	};

	begin_origin_candidate(&state);
	begin_origin_candidate(&state);
	ASSERT(recheck_and_use_origin(&state));
	ASSERT(recheck_and_use_origin(&state));
	state.state = KD_UADDR_DELEGATE;

	finish_origin_unlock(&state);
	ASSERT_EQ(shadow_can_enter(&state), false);
	finish_origin_unlock(&state);
	ASSERT_EQ(shadow_can_enter(&state), true);
}

TEST(promotion_during_recheck_withdraws_origin_candidate) {
	struct transition_state state = {
		.state = KD_UADDR_CHECKING,
		.origin_users = { .counter = 0 },
	};

	begin_origin_candidate(&state);
	state.state = KD_UADDR_DELEGATE;
	ASSERT_EQ(recheck_and_use_origin(&state), false);
	ASSERT_EQ(atomic_read(&state.origin_users), 0);
	ASSERT_EQ(shadow_can_enter(&state), true);
}

TEST(untracked_pre_module_unlock_does_not_underflow) {
	struct transition_state state = {
		.state = KD_UADDR_DELEGATE,
		.origin_users = { .counter = 0 },
	};

	finish_origin_unlock(&state);
	ASSERT_EQ(atomic_read(&state.origin_users), 0);
}

int main(void)
{
	printf("=== test_mutex_transition ===\n");
	RUN_TEST(origin_holder_blocks_shadow_after_promotion);
	RUN_TEST(origin_waiters_all_drain_before_shadow);
	RUN_TEST(promotion_during_recheck_withdraws_origin_candidate);
	RUN_TEST(untracked_pre_module_unlock_does_not_underflow);
	REPORT();
}
