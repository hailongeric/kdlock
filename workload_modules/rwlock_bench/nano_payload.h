/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RW_BENCH_NANO_PAYLOAD_H
#define KD_RW_BENCH_NANO_PAYLOAD_H

#if RB_LINES != 2
#error "nano requires two logical words in one payload cacheline"
#endif

/* One resident, shared record isolates a small load/update body. Both fields
 * occupy the same cacheline; there are no links, per-call arguments, helpers or
 * per-operation allocation. Every backend compiles the identical payload. */
struct rb_nano_record {
	u64 sequence;
	u64 copy;
} __aligned(64);

static struct rb_nano_record rb_nano;

static __attribute__((noipa)) void rb_write(void)
{
	u64 next;

	RB_WRITE_LOCK();
	next = READ_ONCE(rb_nano.sequence) + 1;
	WRITE_ONCE(rb_nano.sequence, next);
	WRITE_ONCE(rb_nano.copy, next);
	RB_WRITE_UNLOCK();
}

static __attribute__((noipa)) bool rb_read(void)
{
	u64 sequence, copy;

	RB_READ_LOCK();
	sequence = READ_ONCE(rb_nano.sequence);
	copy = READ_ONCE(rb_nano.copy);
	RB_READ_UNLOCK();
	return sequence != copy;
}

/* Called only under the runner's quiescent snapshot gate. The two-word
 * invariant catches torn reader snapshots; the userspace oracle independently
 * requires both deltas to equal the exact sum of completed worker writes. */
static int rb_nano_snapshot(u64 *values)
{
	values[0] = READ_ONCE(rb_nano.sequence);
	values[1] = READ_ONCE(rb_nano.copy);
	return values[0] == values[1] ? 0 : -EUCLEAN;
}

#endif
