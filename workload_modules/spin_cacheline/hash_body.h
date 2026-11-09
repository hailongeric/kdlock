/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SC_HASH_PAYLOAD_H
#define SC_HASH_PAYLOAD_H

#include <linux/bitmap.h>
#include <linux/list.h>

/* Write logic adapted from rs3lab/TCLocks, commit bbfb9f00a12af51dff6ca291cb9829a82960c2ef,
 * src/kernel/rcuht/rcuht.c:rcuhashbash_write_lock. One global lock protects
 * all buckets. Preallocated module storage stays live throughout the session;
 * no allocation, RCU service, or dynamic lifetime occurs in the critical section.
 * Fixed 64-byte bucket/node strides are common to the three backends. */
struct sc_hash_bucket {
	struct hlist_head head;
} __aligned(SC_LINE_BYTES);

struct sc_hash_entry {
	struct hlist_node node;
	u32 value;
} __aligned(SC_LINE_BYTES);

struct sc_hash_stats {
	u64 moves, dests, misses;
};

static struct sc_hash_bucket sc_hash_table[SC_HASH_BUCKETS];
static struct sc_hash_entry sc_hash_nodes[SC_HASH_ENTRIES];
static atomic64_t sc_hash_moves = ATOMIC64_INIT(0);
static atomic64_t sc_hash_dests = ATOMIC64_INIT(0);
static atomic64_t sc_hash_misses = ATOMIC64_INIT(0);

static __attribute__((noipa)) void sc_body_0(u32 src_value, u32 dst_value,
					  struct sc_hash_stats *stats)
{
	u32 src_bucket = src_value % SC_HASH_BUCKETS;
	u32 dst_bucket = dst_value % SC_HASH_BUCKETS;
	struct sc_hash_entry *entry, *src_entry = NULL;
	bool same_bucket = src_bucket == dst_bucket;
	bool dest_in_use = false;

	SC_LOCK(0);
	hlist_for_each_entry(entry, &sc_hash_table[src_bucket].head, node) {
		if (entry->value == src_value)
			src_entry = entry;
		if (same_bucket && entry->value == dst_value)
			dest_in_use = true;
	}
	if (!src_entry) {
		stats->misses++;
		goto unlock;
	}
	if (dest_in_use) {
		stats->dests++;
		goto unlock;
	}
	if (same_bucket) {
		stats->moves++;
		src_entry->value = dst_value;
		goto unlock;
	}
	hlist_for_each_entry(entry, &sc_hash_table[dst_bucket].head, node) {
		if (entry->value == dst_value) {
			dest_in_use = true;
			break;
		}
	}
	if (dest_in_use) {
		stats->dests++;
		goto unlock;
	}
	/* Consume the caller's stats pointer before writes through list links.
	 * The operation is now committed to a move, and all backends count it
	 * under the same lock. This avoids a post-write spill reload whose alias
	 * with a list field the bounded JIT analysis cannot rule out. */
	stats->moves++;
	/* This live node is immediately relinked under the same global lock.
	 * Skip hlist_del's transient LIST_POISON stores: no observer can see the
	 * detached state, and hlist_add_head replaces both link fields below.
	 * Keeping those constants in dynamic memory needlessly widens JIT alias
	 * analysis. All backends use this same relocation; admission stays strict. */
	__hlist_del(&src_entry->node);
	src_entry->value = dst_value;
	hlist_add_head(&src_entry->node, &sc_hash_table[dst_bucket].head);
unlock:
	SC_UNLOCK();
}

/* Deterministic per-worker xorshift64* stream, evaluated outside the lock.
 * Use high output bits; adjacent low LCG bits would correlate source/dest keys. */
static u32 sc_hash_random(u64 *state)
{
	u64 x = *state;
	x ^= x >> 12;
	x ^= x << 25;
	x ^= x >> 27;
	*state = x;
	return (x * 2685821657736338717ULL) >> 32;
}

static void sc_hash_init(void)
{
	u32 i;
	for (i = 0; i < SC_HASH_ENTRIES; i++) {
		sc_hash_nodes[i].value = i;
		hlist_add_head(&sc_hash_nodes[i].node,
			       &sc_hash_table[i % SC_HASH_BUCKETS].head);
	}
}

/* Called only with the quiescent snapshot gate held, outside timing.
 * Validate an address before dereferencing it, bound traversal to catch cycles,
 * and check membership, back-links, bucket placement and unique keys. */
static int sc_hash_snapshot(struct sc_counts *counts)
{
	static DECLARE_BITMAP(seen_nodes, SC_HASH_ENTRIES);
	static DECLARE_BITMAP(seen_keys, SC_HASH_KEY_RANGE);
	u32 bucket, total = 0;

	bitmap_zero(seen_nodes, SC_HASH_ENTRIES);
	bitmap_zero(seen_keys, SC_HASH_KEY_RANGE);
	for (bucket = 0; bucket < SC_HASH_BUCKETS; bucket++) {
		struct hlist_node **prev = &sc_hash_table[bucket].head.first;
		struct hlist_node *node = *prev;
		while (node) {
			unsigned long offset = (unsigned long)node -
				(unsigned long)sc_hash_nodes;
			struct sc_hash_entry *entry;
			u32 index;
			if (offset >= sizeof(sc_hash_nodes) ||
			    offset % sizeof(sc_hash_nodes[0]) ||
			    ++total > SC_HASH_ENTRIES)
				return -EUCLEAN;
			index = offset / sizeof(sc_hash_nodes[0]);
			entry = &sc_hash_nodes[index];
			if (test_bit(index, seen_nodes) || node->pprev != prev ||
			    entry->value >= SC_HASH_KEY_RANGE ||
			    entry->value % SC_HASH_BUCKETS != bucket ||
			    test_bit(entry->value, seen_keys))
				return -EUCLEAN;
			__set_bit(index, seen_nodes);
			__set_bit(entry->value, seen_keys);
			prev = &node->next;
			node = node->next;
		}
	}
	if (total != SC_HASH_ENTRIES)
		return -EUCLEAN;
	counts->values[1] = atomic64_read(&sc_hash_moves);
	counts->values[2] = atomic64_read(&sc_hash_dests);
	counts->values[3] = atomic64_read(&sc_hash_misses);
	counts->values[0] = counts->values[1] + counts->values[2] + counts->values[3];
	return 0;
}

#endif
