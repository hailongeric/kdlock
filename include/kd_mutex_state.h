/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_STATE_H
#define KD_MUTEX_STATE_H

#include "kd_mutex.h"
#include <linux/bug.h>
#include <linux/limits.h>

#define KD_MUTEX_PHASE_MASK 0xffU
#define KD_MUTEX_WAITER_SHIFT 8
#define KD_MUTEX_WAITER_ONE (1U << KD_MUTEX_WAITER_SHIFT)
#define KD_MUTEX_WAITER_MAX (U32_MAX >> KD_MUTEX_WAITER_SHIFT)

static __always_inline u32 kd_mutex_gate_read(struct kd_mutex *lock)
{
	return (u32)atomic_read_acquire(&lock->delegation_state) & KD_MUTEX_PHASE_MASK;
}

/* Every phase change preserves concurrent exact waiter accounting. Never use
 * byte stores on this atomic word: enqueue/retirement can update its high bits. */
static __always_inline bool kd_mutex_gate_trylock(struct kd_mutex *lock)
{
	u32 old = atomic_read(&lock->delegation_state);

	while (!(old & KD_MUTEX_PHASE_MASK)) {
		u32 seen = atomic_cmpxchg(&lock->delegation_state, old,
					 old | KD_MUTEX_GATE_ACQUIRING);
		if (seen == old)
			return true;
		old = seen;
	}
	return false;
}

/* Only the gate owner changes an occupied phase. The full atomic operation
 * orders ACQUIRING -> physical acquire -> HELD and RELEASING -> physical
 * release -> FREE. An ordinary physical owner cannot inherit a stale HELD. */
static __always_inline void kd_mutex_gate_set(struct kd_mutex *lock, u32 phase)
{
	u32 old = atomic_read(&lock->delegation_state);

	BUG_ON(phase > KD_MUTEX_GATE_RELEASING);
	for (;;) {
		u32 seen = atomic_cmpxchg(&lock->delegation_state, old,
					 (old & ~KD_MUTEX_PHASE_MASK) | phase);
		if (seen == old)
			return;
		old = seen;
	}
}

static __always_inline int kd_mutex_state_waiter_count(struct kd_mutex *lock)
{
	return (u32)atomic_read(&lock->delegation_state) >> KD_MUTEX_WAITER_SHIFT;
}

static __always_inline void kd_mutex_state_waiter_enter(struct kd_mutex *lock)
{
	u32 old = atomic_fetch_add(KD_MUTEX_WAITER_ONE, &lock->delegation_state);

	BUG_ON((old >> KD_MUTEX_WAITER_SHIFT) == KD_MUTEX_WAITER_MAX);
}

static __always_inline void kd_mutex_state_waiter_exit(struct kd_mutex *lock)
{
	u32 old = atomic_fetch_sub(KD_MUTEX_WAITER_ONE, &lock->delegation_state);

	BUG_ON(!(old >> KD_MUTEX_WAITER_SHIFT));
}

#endif
