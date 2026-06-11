/*
 * test_mutex_count.c — verify mutex node count management.
 *
 * The count field lives in nodes[0] and must be incremented/decremented
 * correctly regardless of which node index is used.
 */
#include "mock_kernel.h"
#include "test_harness.h"

#define KD_MUTEX_MAX_NODES 4

struct kd_mutex_node {
	int count;
	int tail;
	int cpuid;
	int socket_id;
	uint8_t completed;
	uint8_t locked;
	unsigned long rsp;
	unsigned long regs_sp;
};

static struct kd_mutex_node nodes[KD_MUTEX_MAX_NODES];

static void init_nodes(void) {
	memset(nodes, 0, sizeof(nodes));
}

/* Simulate the fixed kd_mutex_lock_slowpath count logic */
static int simulate_lock(void) {
	struct kd_mutex_node *base = &nodes[0];
	int idx = base->count++;

	if (idx >= KD_MUTEX_MAX_NODES) {
		base->count--;
		return -1; /* overflow fallback */
	}
	return idx;
}

/* Simulate the fixed count decrement (must target nodes[0]) */
static void simulate_unlock(void) {
	nodes[0].count--;
}

/* Simulate the OLD buggy decrement (targets nodes[idx]) */
static void simulate_unlock_buggy(int idx) {
	nodes[idx].count--;
}

TEST(count_starts_at_zero) {
	init_nodes();
	ASSERT_EQ(nodes[0].count, 0);
}

TEST(single_lock_unlock) {
	init_nodes();
	int idx = simulate_lock();
	ASSERT_EQ(idx, 0);
	ASSERT_EQ(nodes[0].count, 1);
	simulate_unlock();
	ASSERT_EQ(nodes[0].count, 0);
}

TEST(nested_lock_unlock) {
	init_nodes();
	int idx0 = simulate_lock();
	int idx1 = simulate_lock();
	int idx2 = simulate_lock();
	ASSERT_EQ(idx0, 0);
	ASSERT_EQ(idx1, 1);
	ASSERT_EQ(idx2, 2);
	ASSERT_EQ(nodes[0].count, 3);

	simulate_unlock();
	simulate_unlock();
	simulate_unlock();
	ASSERT_EQ(nodes[0].count, 0);
}

TEST(overflow_protection) {
	init_nodes();
	for (int i = 0; i < KD_MUTEX_MAX_NODES; i++)
		simulate_lock();
	ASSERT_EQ(nodes[0].count, 4);

	/* Next attempt should fail */
	int rc = simulate_lock();
	ASSERT_EQ(rc, -1);
	ASSERT_EQ(nodes[0].count, 4); /* unchanged */
}

TEST(buggy_decrement_leaks_count) {
	/* Demonstrate the bug we fixed: decrementing nodes[idx] instead of nodes[0] */
	init_nodes();
	simulate_lock(); /* idx=0, count=1 */
	simulate_lock(); /* idx=1, count=2 */
	simulate_unlock_buggy(1); /* decrements nodes[1].count, NOT nodes[0]! */
	simulate_unlock_buggy(0); /* decrements nodes[0].count → 0 */

	/* After "unlocking" both, count should be 0 if correct, but with
	 * the buggy version only the second decrement actually hits nodes[0] */
	/* The first lock (idx=0) decrements correctly, the second (idx=1) leaks */
	/* Let's verify the leak: lock again and idx should be != 0 */
	init_nodes();
	simulate_lock(); /* count: 0→1, idx=0 */
	simulate_unlock_buggy(0); /* nodes[0].count: 1→0 ✓ */

	simulate_lock(); /* count: 0→1, idx=0 */
	int idx = simulate_lock(); /* count: 1→2, idx=1 */
	ASSERT_EQ(idx, 1);
	simulate_unlock_buggy(1); /* BUG: nodes[1].count--, nodes[0].count stays 2 */
	ASSERT_EQ(nodes[0].count, 2); /* leaked! should be 1 */

	/* With correct version: */
	init_nodes();
	simulate_lock();
	simulate_lock();
	simulate_unlock(); /* nodes[0].count: 2→1 */
	ASSERT_EQ(nodes[0].count, 1); /* correct */
	simulate_unlock(); /* nodes[0].count: 1→0 */
	ASSERT_EQ(nodes[0].count, 0); /* correct */
}

TEST(repeated_lock_unlock_stable) {
	init_nodes();
	for (int i = 0; i < 1000; i++) {
		int idx = simulate_lock();
		ASSERT_EQ(idx, 0);
		simulate_unlock();
	}
	ASSERT_EQ(nodes[0].count, 0);
}

int main(void) {
	printf("=== test_mutex_count ===\n");
	RUN_TEST(count_starts_at_zero);
	RUN_TEST(single_lock_unlock);
	RUN_TEST(nested_lock_unlock);
	RUN_TEST(overflow_protection);
	RUN_TEST(buggy_decrement_leaks_count);
	RUN_TEST(repeated_lock_unlock_stable);
	REPORT();
}
