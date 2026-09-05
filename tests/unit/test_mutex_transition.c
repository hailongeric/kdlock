/* Model tests for the native-owner/serial-executor contract.
 * Kernel integration tests exercise the actual queue, atomics and hook ABI. */
#include "mock_kernel.h"
#include "test_harness.h"

struct protocol {
	int owner;
	int executor;
	int effects;
	bool promoted;
	bool inflight[4];
};

static bool native_trylock(struct protocol *p, int task)
{
	if (p->owner)
		return false;
	p->owner = task;
	return true;
}

static bool hook_matches(struct protocol *p, int task, bool target_name)
{
	return target_name || p->inflight[task];
}

TEST(promotion_does_not_bypass_native_owner)
{
	struct protocol p = { .owner = 1 };
	p.promoted = true;
	ASSERT_EQ(native_trylock(&p, 2), false);
	p.owner = 0;
	ASSERT_EQ(native_trylock(&p, 2), true);
}

TEST(borrowed_native_execution_keeps_external_tasks_out)
{
	struct protocol p = { .owner = 1, .executor = 1, .effects = 1 };
	p.inflight[1] = p.inflight[2] = true;
	p.executor = 2;
	ASSERT_EQ(p.owner, 1);
	ASSERT_EQ(native_trylock(&p, 3), false);
	ASSERT_EQ(native_trylock(&p, 1), false);
	p.effects++;
	p.executor = 1;
	p.inflight[2] = false;
	ASSERT_EQ(p.effects, 2);
	ASSERT_EQ(p.owner, 1);
	p.owner = 0;
	ASSERT_EQ(native_trylock(&p, 3), true);
}

TEST(renaming_cannot_drop_active_unlock_routing)
{
	struct protocol p = { 0 };
	ASSERT_EQ(hook_matches(&p, 2, false), false);
	p.inflight[2] = true;
	ASSERT_EQ(hook_matches(&p, 2, false), true);
	p.inflight[2] = false;
	ASSERT_EQ(hook_matches(&p, 2, false), false);
}

TEST(queue_handoff_does_not_transfer_native_ownership)
{
	struct protocol p = { .owner = 1 };
	ASSERT_EQ(native_trylock(&p, 2), false);
	p.owner = 0;
	ASSERT_EQ(native_trylock(&p, 3), true);
	ASSERT_EQ(native_trylock(&p, 2), false);
	p.owner = 0;
	ASSERT_EQ(native_trylock(&p, 2), true);
}

int main(void)
{
	printf("=== test_mutex_transition ===\n");
	RUN_TEST(promotion_does_not_bypass_native_owner);
	RUN_TEST(borrowed_native_execution_keeps_external_tasks_out);
	RUN_TEST(renaming_cannot_drop_active_unlock_routing);
	RUN_TEST(queue_handoff_does_not_transfer_native_ownership);
	REPORT();
}
