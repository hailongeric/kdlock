/*
 * test_mutex_count.c — verify mutex node-slot and resume management.
 */
#include "mock_kernel.h"
#include "test_harness.h"

#define KD_MUTEX_MAX_NODES 4

struct kd_mutex_node {
	int slot;
	bool stack_available;
	int tail;
	int cpuid;
	int socket_id;
	uint8_t completed;
	uint8_t locked;
	unsigned long rsp;
	unsigned long regs_sp;
	unsigned long regs_ip;
};

static struct kd_mutex_node nodes[KD_MUTEX_MAX_NODES];
static struct kd_mutex_node *resume_node;
static unsigned long node_slots;

struct resume_regs {
	unsigned long sp;
	unsigned long ip;
};

static void init_nodes(void)
{
	memset(nodes, 0, sizeof(nodes));
	for (int i = 0; i < KD_MUTEX_MAX_NODES; i++) {
		nodes[i].slot = i;
		nodes[i].stack_available = true;
	}
	resume_node = NULL;
	node_slots = 0;
}

static void publish_resume_node(struct kd_mutex_node *node)
{
	resume_node = node;
}

static bool snapshot_resume_regs(struct resume_regs *regs)
{
	struct kd_mutex_node *node = resume_node;

	if (!node || !regs)
		return false;
	regs->sp = node->regs_sp;
	regs->ip = node->regs_ip;
	resume_node = NULL;
	return true;
}

static struct kd_mutex_node *reserve_node(void)
{
	for (int i = 0; i < KD_MUTEX_MAX_NODES; i++) {
		if ((node_slots & (1UL << i)) || !nodes[i].stack_available)
			continue;
		node_slots |= 1UL << i;
		return &nodes[i];
	}
	return NULL;
}

static bool release_node(struct kd_mutex_node *node)
{
	unsigned long bit;

	if (!node || node->slot < 0 || node->slot >= KD_MUTEX_MAX_NODES)
		return false;
	bit = 1UL << node->slot;
	if (!(node_slots & bit))
		return false;
	node_slots &= ~bit;
	return true;
}

TEST(slots_start_empty)
{
	init_nodes();
	ASSERT_EQ(node_slots, 0UL);
}

TEST(single_reservation_release)
{
	struct kd_mutex_node *node;

	init_nodes();
	node = reserve_node();
	ASSERT_EQ(node, &nodes[0]);
	ASSERT_EQ(node_slots, 1UL);
	ASSERT_EQ(release_node(node), true);
	ASSERT_EQ(node_slots, 0UL);
}

TEST(all_slots_and_overflow)
{
	init_nodes();
	for (int i = 0; i < KD_MUTEX_MAX_NODES; i++)
		ASSERT_EQ(reserve_node(), &nodes[i]);
	ASSERT_EQ(node_slots, 0xfUL);
	ASSERT_EQ(reserve_node(), NULL);
}

TEST(out_of_order_release_reuses_only_free_slot)
{
	struct kd_mutex_node *node0;
	struct kd_mutex_node *node1;
	struct kd_mutex_node *node2;

	init_nodes();
	node0 = reserve_node();
	node1 = reserve_node();
	node2 = reserve_node();
	ASSERT_EQ(release_node(node0), true);
	ASSERT_EQ(reserve_node(), node0);
	ASSERT_EQ(node_slots & (1UL << node1->slot), 1UL << node1->slot);
	ASSERT_EQ(node_slots & (1UL << node2->slot), 1UL << node2->slot);
}

TEST(unavailable_stack_is_skipped)
{
	init_nodes();
	nodes[0].stack_available = false;
	ASSERT_EQ(reserve_node(), &nodes[1]);
	ASSERT_EQ(node_slots, 1UL << 1);
}

TEST(double_release_is_rejected)
{
	struct kd_mutex_node *node;

	init_nodes();
	node = reserve_node();
	ASSERT_EQ(release_node(node), true);
	ASSERT_EQ(release_node(node), false);
}

TEST(repeated_lock_unlock_stable)
{
	init_nodes();
	for (int i = 0; i < 1000; i++) {
		struct kd_mutex_node *node = reserve_node();

		ASSERT_EQ(node, &nodes[0]);
		ASSERT_EQ(release_node(node), true);
	}
	ASSERT_EQ(node_slots, 0UL);
}

TEST(resume_context_is_copied_before_node_reuse)
{
	struct resume_regs regs = { 0 };
	struct kd_mutex_node *node;

	init_nodes();
	node = reserve_node();
	node->regs_sp = 0x1000;
	node->regs_ip = 0x2000;
	publish_resume_node(node);
	ASSERT_EQ(snapshot_resume_regs(&regs), true);
	ASSERT_EQ(resume_node, NULL);
	ASSERT_EQ(release_node(node), true);

	/* A later waiter may reuse the per-CPU node after the snapshot. */
	ASSERT_EQ(reserve_node(), node);
	node->regs_sp = 0x3000;
	node->regs_ip = 0x4000;
	ASSERT_EQ(regs.sp, 0x1000UL);
	ASSERT_EQ(regs.ip, 0x2000UL);
	ASSERT_EQ(snapshot_resume_regs(&regs), false);
}

int main(void)
{
	printf("=== test_mutex_count ===\n");
	RUN_TEST(slots_start_empty);
	RUN_TEST(single_reservation_release);
	RUN_TEST(all_slots_and_overflow);
	RUN_TEST(out_of_order_release_reuses_only_free_slot);
	RUN_TEST(unavailable_stack_is_skipped);
	RUN_TEST(double_release_is_rejected);
	RUN_TEST(repeated_lock_unlock_stable);
	RUN_TEST(resume_context_is_copied_before_node_reuse);
	REPORT();
}
