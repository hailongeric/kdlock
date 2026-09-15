/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SPIN_CACHELINE_PAYLOAD_H
#define SPIN_CACHELINE_PAYLOAD_H

/* N counts only payload lines. All five paths use exactly the same lock.
 * Keep every update explicit: no loop/selection/service inside the lock. */
struct sc_slot {
	__u64 value;
	unsigned char padding[SC_LINE_BYTES - sizeof(__u64)];
} __attribute__((aligned(SC_LINE_BYTES)));

static struct sc_slot sc_data[SC_SLOTS];
static spinlock_t sc_lock __attribute__((aligned(SC_LINE_BYTES)));

#define SC_TOUCH(i) WRITE_ONCE(sc_data[i].value, READ_ONCE(sc_data[i].value) + 1)
#define SC_TOUCH_1 SC_TOUCH(0);
#define SC_TOUCH_2 SC_TOUCH_1 SC_TOUCH(1);
#define SC_TOUCH_4 SC_TOUCH_2 SC_TOUCH(2); SC_TOUCH(3);
#define SC_TOUCH_8 SC_TOUCH_4 SC_TOUCH(4); SC_TOUCH(5); SC_TOUCH(6); SC_TOUCH(7);
#define SC_TOUCH_16 SC_TOUCH_8 SC_TOUCH(8); SC_TOUCH(9); SC_TOUCH(10); \
	SC_TOUCH(11); SC_TOUCH(12); SC_TOUCH(13); SC_TOUCH(14); SC_TOUCH(15);

/* noipa preserves five identifiable entries and prevents cross-path merging.
 * The caller chooses the function once, before the iterations start. */
#define SC_BODY(n) \
static __attribute__((noipa)) void sc_body_##n(void) \
{ \
	spin_lock(&sc_lock); \
	SC_TOUCH_##n \
	spin_unlock(&sc_lock); \
}
SC_BODY(1)
SC_BODY(2)
SC_BODY(4)
SC_BODY(8)
SC_BODY(16)

#endif
