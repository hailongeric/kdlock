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
#ifndef SC_MUTEX_WORKLOAD
#include "direct.h"
#ifdef SC_DIRECT_KDLOCK
static kd_spinlock_t sc_lock __attribute__((aligned(SC_LINE_BYTES)));
#else
static spinlock_t sc_lock __attribute__((aligned(SC_LINE_BYTES)));
#endif

#endif /* SC_MUTEX_WORKLOAD supplies its own lock shell. */

#include "scenario.h"

#ifdef SC_HASH_PAYLOAD
#include "hash_payload.h"
#else
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
	SC_LOCK(n); \
	SC_EXTRA_LOCK(n); \
	SC_TOUCH_##n \
	SC_EXIT(); \
}
SC_BODY(1)
#ifndef SC_MUTEX_OWNED
SC_BODY(2)
SC_BODY(4)
SC_BODY(8)
SC_BODY(16)
#endif
#endif

/* Register the CALL continuation, never a C wrapper/prologue. Only the chosen
 * body is published in this session, after module load and before timing. */
static inline int sc_prepare(unsigned int lines)
{
#ifdef SC_DIRECT_KDLOCK
	unsigned long entry;
	switch (lines) {
#ifdef SC_HASH_PAYLOAD
	case 0: entry = (unsigned long)sc_entry_0; break;
#else
	case 1: entry = (unsigned long)sc_entry_1; break;
#ifndef SC_MUTEX_OWNED
	case 2: entry = (unsigned long)sc_entry_2; break;
	case 4: entry = (unsigned long)sc_entry_4; break;
	case 8: entry = (unsigned long)sc_entry_8; break;
	case 16: entry = (unsigned long)sc_entry_16; break;
#endif
#endif
	default: return -EINVAL;
	}
#ifdef SC_MUTEX_WORKLOAD
#ifdef SC_MUTEX_OWNED
	return kd_owned_mutex_prepare(&sc_lock, entry, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#else
	return kd_mutex_prepare(&sc_lock, entry, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#endif
#else
	return kd_spin_prepare(&sc_lock, entry, KD_ENTRY_ABI_SPIN_CLOBBER_V1);
#endif
#else
#ifdef SC_HASH_PAYLOAD
	return lines == 0 ? 0 : -EINVAL;
#else
	return lines == 1 || lines == 2 || lines == 4 || lines == 8 || lines == 16 ?
		0 : -EINVAL;
#endif
#endif
}

#endif
