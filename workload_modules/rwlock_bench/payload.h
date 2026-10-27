/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RW_BENCH_PAYLOAD_H
#define KD_RW_BENCH_PAYLOAD_H

/* Explicitly configured register-only post-work, matching the spin suite. */
#include "post_work.h"
#ifdef RB_SNAPSHOT_PAYLOAD
#include "snapshot_payload.h"
#elif defined(RB_NANO)
#include "nano_payload.h"
#elif defined(RB_HASH)
/* Reuse the existing TCLock RCUHT move body and full structural oracle. Only
 * its locking shell changes; keys, linked-list stores and outcome accounting
 * stay identical to the earlier KD/TCLock hash comparison. */
#define SC_LINE_BYTES 64
#define SC_HASH_BUCKETS 1024
#define SC_HASH_ENTRIES 4096
#define SC_HASH_KEY_RANGE 8192
#define SC_LOCK(n) RB_WRITE_LOCK()
#define SC_UNLOCK() RB_WRITE_UNLOCK()
#define sc_counts rw_bench_snapshot
#define sc_body_0 rb_write
#include "hash_payload.h"
#undef sc_counts
#undef sc_body_0

static __attribute__((noipa)) bool rb_read(u32 key)
{
	struct sc_hash_entry *entry;
	bool found = false;
	RB_READ_LOCK();
	hlist_for_each_entry(entry, &sc_hash_table[key % SC_HASH_BUCKETS].head, node) {
		if (entry->value == key) {
			found = true;
			break;
		}
	}
	RB_READ_UNLOCK();
	return found;
}
#else
struct rb_slot { u64 value; } __aligned(64);
static struct rb_slot rb_values[RB_SLOTS];

#define RB_EACH_1(op) op(0)
#define RB_EACH_2(op) RB_EACH_1(op) op(1)
#define RB_EACH_4(op) RB_EACH_2(op) op(2) op(3)
#define RB_EACH_8(op) RB_EACH_4(op) op(4) op(5) op(6) op(7)
#define RB_EACH_16(op) RB_EACH_8(op) op(8) op(9) op(10) op(11) op(12) op(13) op(14) op(15)
#define RB_EXPAND_INNER(n, op) RB_EACH_##n(op)
#define RB_EXPAND(n, op) RB_EXPAND_INNER(n, op)
#define RB_TOUCH(i) WRITE_ONCE(rb_values[i].value, READ_ONCE(rb_values[i].value) + 1);

static __attribute__((noipa)) void rb_write(void)
{
	RB_WRITE_LOCK();
	RB_EXPAND(RB_LINES, RB_TOUCH)
	RB_WRITE_UNLOCK();
}

/* Read comparisons only affect a caller-local result. No global counter or
 * cacheline write serializes successful readers. The extra first-line load
 * also checks stability in the single-line case. */
#define RB_CHECK(i) bad |= READ_ONCE(rb_values[i].value) != first;
static __attribute__((noipa)) bool rb_read(void)
{
	u64 first;
	bool bad = false;
	RB_READ_LOCK();
	first = READ_ONCE(rb_values[0].value);
	RB_EXPAND(RB_LINES, RB_CHECK)
	RB_READ_UNLOCK();
	return bad;
}
#endif
#endif
