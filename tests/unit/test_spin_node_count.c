/*
 * test_spin_node_count.c - model spin MCS node exhaustion behavior.
 *
 * Native acquisition falls back to direct spinning when all per-CPU nodes are
 * occupied. A nested JIT acquisition cannot block inside that fallback, so it
 * reports a pending resource error for native continuation at that lock CALL.
 * Neither path may leak the base-node count.
 */
#include "mock_kernel.h"
#include "test_harness.h"

#define MAX_NODES 4
#define NESTED_OVERFLOW -2
#define NATIVE_FALLBACK -1

struct spin_node_pool {
	int count;
};

static int reserve_nested(struct spin_node_pool *pool)
{
	int idx = pool->count++;

	if (idx >= MAX_NODES) {
		pool->count--;
		return NESTED_OVERFLOW;
	}
	return idx;
}

static int reserve_native(struct spin_node_pool *pool)
{
	int idx = pool->count++;

	if (idx >= MAX_NODES) {
		pool->count--;
		return NATIVE_FALLBACK;
	}
	return idx;
}

static void release_node(struct spin_node_pool *pool)
{
	pool->count--;
}

TEST(nested_exhaustion_rolls_back_count)
{
	struct spin_node_pool pool = { 0 };

	for (int i = 0; i < MAX_NODES; i++)
		ASSERT_EQ(reserve_nested(&pool), i);
	ASSERT_EQ(reserve_nested(&pool), NESTED_OVERFLOW);
	ASSERT_EQ(pool.count, MAX_NODES);
}

TEST(native_exhaustion_uses_count_neutral_fallback)
{
	struct spin_node_pool pool = { 0 };

	for (int i = 0; i < MAX_NODES; i++)
		ASSERT_EQ(reserve_native(&pool), i);
	ASSERT_EQ(reserve_native(&pool), NATIVE_FALLBACK);
	ASSERT_EQ(pool.count, MAX_NODES);
}

TEST(capacity_recovers_after_release)
{
	struct spin_node_pool pool = { 0 };

	for (int i = 0; i < MAX_NODES; i++)
		ASSERT_EQ(reserve_nested(&pool), i);
	release_node(&pool);
	ASSERT_EQ(pool.count, MAX_NODES - 1);
	ASSERT_EQ(reserve_nested(&pool), MAX_NODES - 1);
	ASSERT_EQ(pool.count, MAX_NODES);
}

int main(void)
{
	printf("=== test_spin_node_count ===\n");
	RUN_TEST(nested_exhaustion_rolls_back_count);
	RUN_TEST(native_exhaustion_uses_count_neutral_fallback);
	RUN_TEST(capacity_recovers_after_release);
	REPORT();
}
