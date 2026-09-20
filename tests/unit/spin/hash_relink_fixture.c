/* Sequential equivalence oracle for the real benchmark's unlink/relink body.
 * hlist primitives are extracted from the guest kernel at test time. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef uint32_t u32;
typedef uint64_t u64;
typedef uint64_t atomic64_t;
#define ATOMIC64_INIT(x) (x)
#define __aligned(n) __attribute__((aligned(n)))
#define SC_LINE_BYTES 64
#define SC_HASH_BUCKETS 1024
#define SC_HASH_ENTRIES 4096
#define SC_HASH_KEY_RANGE 8192
#define SC_LOCK(n) ((void)(n))
#define SC_UNLOCK() ((void)0)
#define WRITE_ONCE(x, val) (*(volatile __typeof__(x) *)&(x) = (val))
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define LIST_POISON1 ((void *)(uintptr_t)0xdead000000000100ULL)
#define LIST_POISON2 ((void *)(uintptr_t)0xdead000000000122ULL)
struct hlist_node { struct hlist_node *next, **pprev; };
struct hlist_head { struct hlist_node *first; };
#define hlist_entry_safe(ptr, type, member) \
	((ptr) ? (type *)((char *)(ptr) - offsetof(type, member)) : NULL)
#define hlist_for_each_entry(pos, head, member) \
	for ((pos) = hlist_entry_safe((head)->first, __typeof__(*(pos)), member); \
	     (pos); (pos) = hlist_entry_safe((pos)->member.next, __typeof__(*(pos)), member))

/* KERNEL_HLIST_HELPERS */
/* PRODUCTION_HASH_BODIES */

static bool present[SC_HASH_KEY_RANGE];
static struct old_sc_hash_stats old_stats;
static struct new_sc_hash_stats new_stats;
static u64 moves, dests, misses;
static unsigned int positions, destinations;

/* Check both graphs by node index and exact back-link addresses; address
 * equality between separate tables is neither expected nor used. */
static void verify(void)
{
	bool seen[SC_HASH_ENTRIES] = { false };
	bool keys[SC_HASH_KEY_RANGE] = { false };
	u32 count = 0;
	for (u32 b = 0; b < SC_HASH_BUCKETS; b++) {
		struct hlist_node **op = &old_sc_hash_table[b].head.first;
		struct hlist_node **np = &new_sc_hash_table[b].head.first;
		while (*op || *np) {
			assert(*op && *np);
			uintptr_t oi = (uintptr_t)*op - (uintptr_t)old_sc_hash_nodes;
			uintptr_t ni = (uintptr_t)*np - (uintptr_t)new_sc_hash_nodes;
			assert(oi < sizeof(old_sc_hash_nodes) && ni < sizeof(new_sc_hash_nodes));
			assert(!(oi % sizeof(old_sc_hash_nodes[0])));
			assert(!(ni % sizeof(new_sc_hash_nodes[0])));
			oi /= sizeof(old_sc_hash_nodes[0]);
			ni /= sizeof(new_sc_hash_nodes[0]);
			assert(oi == ni && !seen[oi] && ++count <= SC_HASH_ENTRIES);
			seen[oi] = true;
			u32 key = new_sc_hash_nodes[ni].value;
			assert(key == old_sc_hash_nodes[oi].value && key < SC_HASH_KEY_RANGE);
			assert(present[key] && !keys[key] && key % SC_HASH_BUCKETS == b);
			keys[key] = true;
			assert((*op)->pprev == op && (*np)->pprev == np);
			op = &(*op)->next;
			np = &(*np)->next;
		}
	}
	assert(count == SC_HASH_ENTRIES);
	for (u32 key = 0; key < SC_HASH_KEY_RANGE; key++)
		assert(keys[key] == present[key]);
}

static void operation(u32 src, u32 dst)
{
	if (!present[src]) {
		misses++;
	} else if (present[dst]) {
		dests++;
	} else {
		if (src % SC_HASH_BUCKETS != dst % SC_HASH_BUCKETS) {
			struct new_sc_hash_entry *entry;
			hlist_for_each_entry(entry, &new_sc_hash_table[src % SC_HASH_BUCKETS].head, node) {
				if (entry->value != src)
					continue;
				positions |= entry->node.pprev == &new_sc_hash_table[src % SC_HASH_BUCKETS].head.first ? 1 :
					entry->node.next ? 2 : 4;
			}
			destinations |= new_sc_hash_table[dst % SC_HASH_BUCKETS].head.first ? 1 : 2;
		}
		present[src] = false;
		present[dst] = true;
		moves++;
	}
	old_sc_body_0(src, dst, &old_stats);
	new_sc_body_0(src, dst, &new_stats);
	assert(old_stats.moves == moves && new_stats.moves == moves);
	assert(old_stats.dests == dests && new_stats.dests == dests);
	assert(old_stats.misses == misses && new_stats.misses == misses);
}

int main(void)
{
	for (u32 i = 0; i < SC_HASH_ENTRIES; i++) {
		old_sc_hash_nodes[i].value = new_sc_hash_nodes[i].value = i;
		present[i] = true;
		hlist_add_head(&old_sc_hash_nodes[i].node, &old_sc_hash_table[i % SC_HASH_BUCKETS].head);
		hlist_add_head(&new_sc_hash_nodes[i].node, &new_sc_hash_table[i % SC_HASH_BUCKETS].head);
	}
	operation(7000, 4200); /* missing source */
	operation(0, 0);      /* destination equals source */
	operation(0, 4096);   /* same-bucket rename */
	operation(1, 2);      /* existing destination in another bucket */
	operation(3073, 4098); /* remove head */
	operation(2049, 4099); /* remove middle */
	operation(1, 4100);    /* remove tail */
	verify();
	u64 rng = 0x9e3779b97f4a7c15ULL;
	for (u32 i = 0; i < 100000; i++) {
		rng ^= rng >> 12; rng ^= rng << 25; rng ^= rng >> 27;
		u32 src = (rng * 2685821657736338717ULL >> 32) % SC_HASH_KEY_RANGE;
		rng ^= rng >> 12; rng ^= rng << 25; rng ^= rng >> 27;
		u32 dst = (rng * 2685821657736338717ULL >> 32) % SC_HASH_KEY_RANGE;
		operation(src, dst);
		if (!(i % 257))
			verify();
	}
	verify();
	assert(positions == 7 && destinations == 3);
	puts("PASS hash relink: 100007 operations match poisoned body and key-set oracle; head/middle/tail and empty/nonempty destinations covered");
	return 0;
}
