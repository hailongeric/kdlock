/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SC_LIST_PAYLOAD_H
#define SC_LIST_PAYLOAD_H

#include <linux/prefetch.h>

/* Resident module storage, immutable links, one global lock. The same bounded
 * traversal and optional read-prefetch are compiled for every backend. Queue
 * prefetch in the KD provider is an independent setting. */
struct sc_list_node {
	struct sc_list_node *next;
	u64 value;
} __aligned(64);

static struct sc_list_node sc_list_nodes[SC_LIST_NODES];

static __always_inline void sc_list_write_locked(void)
{
	struct sc_list_node *node = &sc_list_nodes[0];
	unsigned int i;

	for (i = 0; i < SC_LIST_NODES; i++) {
		struct sc_list_node *next = READ_ONCE(node->next);

#if SC_LIST_PREFETCH
		prefetch(next);
#endif
		WRITE_ONCE(node->value, READ_ONCE(node->value) + 1);
		node = next;
	}
}

static __always_inline bool sc_list_read_locked(void)
{
	struct sc_list_node *node = &sc_list_nodes[0];
	u64 first = READ_ONCE(node->value);
	bool bad = false;
	unsigned int i;

	for (i = 0; i < SC_LIST_NODES; i++) {
		struct sc_list_node *next = READ_ONCE(node->next);

#if SC_LIST_PREFETCH
		prefetch(next);
#endif
		bad |= READ_ONCE(node->value) != first;
		node = next;
	}
	return bad;
}

static void sc_list_init(void)
{
	unsigned int i;

	BUILD_BUG_ON(SC_LIST_NODES != 16 && SC_LIST_NODES != 128);
	BUILD_BUG_ON(SC_LIST_PREFETCH != 0 && SC_LIST_PREFETCH != 1);
	BUILD_BUG_ON(sizeof(struct sc_list_node) != 64);
	for (i = 0; i < SC_LIST_NODES; i++) {
		sc_list_nodes[i].next = &sc_list_nodes[(i + 5) % SC_LIST_NODES];
		sc_list_nodes[i].value = 0;
	}
}

/* Quiescent only. Compare the known permutation before dereferencing each
 * pointer. Odd stride 5 visits every node for either supported power-of-two
 * size; exact next-link checks also reject short cycles and missing nodes.
 * One shared value counts full writes without another hot shared counter. */
static int sc_list_snapshot(u64 *values)
{
	struct sc_list_node *node = &sc_list_nodes[0];
	u64 first = READ_ONCE(sc_list_nodes[0].value);
	unsigned int i;

	for (i = 0; i < SC_LIST_NODES; i++) {
		unsigned int index = (i * 5) % SC_LIST_NODES;
		struct sc_list_node *next =
			&sc_list_nodes[(index + 5) % SC_LIST_NODES];

		if (node != &sc_list_nodes[index] ||
		    READ_ONCE(node->next) != next ||
		    READ_ONCE(node->value) != first)
			return -EUCLEAN;
		node = next;
	}
	if (node != &sc_list_nodes[0])
		return -EUCLEAN;
	values[0] = first;
	return 0;
}

#endif
