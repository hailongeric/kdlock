/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_STATE_H
#define KD_MUTEX_STATE_H

#include "kd_mutex.h"
#include <linux/bug.h>
#include <linux/limits.h>

static __always_inline u32 kd_mutex_gate_read(struct kd_mutex *lock)
{
	return (u32)atomic_read_acquire(&lock->delegation_state) & KD_MUTEX_GATE_PHASE_MASK;
}

/* A withdrawal reservation may survive a physical owner's phase change.
 * Full-word FREE->ACQUIRING must reject FREE|WITHDRAW until its holder clears
 * that reservation. No mixed-width accesses may update this atomic word. */
static __always_inline bool kd_mutex_gate_trylock(struct kd_mutex *lock)
{
	return atomic_cmpxchg(&lock->delegation_state, KD_MUTEX_GATE_FREE,
			      KD_MUTEX_GATE_ACQUIRING) == KD_MUTEX_GATE_FREE;
}

/* Exactly one attempt closes withdrawal for a proxy epoch. A busy withdrawal
 * makes this owner hand the queue off; it never waits for an origin response. */
static __always_inline bool kd_mutex_gate_try_combine(struct kd_mutex *lock)
{
	return atomic_cmpxchg(&lock->delegation_state, KD_MUTEX_GATE_HELD,
			      KD_MUTEX_GATE_COMBINER) == KD_MUTEX_GATE_HELD;
}

static __always_inline bool kd_mutex_gate_try_withdraw(struct kd_mutex *lock)
{
	u32 state = (u32)atomic_read_acquire(&lock->delegation_state);

	BUG_ON(state & ~(KD_MUTEX_GATE_PHASE_MASK | KD_MUTEX_GATE_WITHDRAW));
	BUG_ON((state & KD_MUTEX_GATE_PHASE_MASK) > KD_MUTEX_GATE_RELEASING);
	if ((state & KD_MUTEX_GATE_WITHDRAW) ||
	    (state & KD_MUTEX_GATE_PHASE_MASK) == KD_MUTEX_GATE_COMBINER)
		return false;
	return (u32)atomic_cmpxchg(&lock->delegation_state, state,
				   state | KD_MUTEX_GATE_WITHDRAW) == state;
}

/* Release every node-state access before reopening batch admission. A phase
 * writer may have run meanwhile, so clear only our bit. The origin must still
 * be pinned here and must never schedule while it owns this reservation. */
static __always_inline void kd_mutex_gate_end_withdraw(struct kd_mutex *lock)
{
	u32 state = (u32)atomic_fetch_andnot_release(KD_MUTEX_GATE_WITHDRAW,
						 &lock->delegation_state);

	BUG_ON(!(state & KD_MUTEX_GATE_WITHDRAW) ||
	       (state & KD_MUTEX_GATE_PHASE_MASK) == KD_MUTEX_GATE_COMBINER);
}

/* Only the exact gate owner changes phase. Preserve a concurrently reserved
 * withdrawal through HELD, RELEASING and FREE. COMBINER admission is exclusively
 * the single CAS above. After publishing FREE, never access this gate again. */
static __always_inline void kd_mutex_gate_set(struct kd_mutex *lock, u32 phase)
{
	u32 state, previous;

	BUG_ON(phase > KD_MUTEX_GATE_RELEASING || phase == KD_MUTEX_GATE_COMBINER);
	state = (u32)atomic_read(&lock->delegation_state);
	do {
		BUG_ON(state & ~(KD_MUTEX_GATE_PHASE_MASK | KD_MUTEX_GATE_WITHDRAW));
		BUG_ON((state & KD_MUTEX_GATE_PHASE_MASK) > KD_MUTEX_GATE_RELEASING);
		previous = state;
		/* Fully ordered CAS includes the release publication needed by
		 * physical acquisition/unlock and by epoch closure. */
		state = (u32)atomic_cmpxchg(&lock->delegation_state, previous,
					   phase | (previous & KD_MUTEX_GATE_WITHDRAW));
	} while (state != previous);
}

/* Only the migration-pinned origin updates this reserved node. Sequence
 * bracketing makes a reused slot distinguishable even when its key repeats.
 * No lock-wide RMW is needed; readers never dereference the sampled key. */
static __always_inline void
kd_mutex_count_transition(struct kd_mutex_node *node,
			  struct kd_mutex *expected, struct kd_mutex *next)
{
	u64 seq = READ_ONCE(node->count_seq);

	BUG_ON((seq & 1) || seq > U64_MAX - 2);
	BUG_ON(READ_ONCE(node->counted_lock) != expected);
	WRITE_ONCE(node->count_seq, seq + 1);
	smp_wmb();
	WRITE_ONCE(node->counted_lock, next);
	smp_wmb();
	WRITE_ONCE(node->count_seq, seq + 2);
}

static __always_inline void kd_mutex_count_enter(struct kd_mutex *lock,
						struct kd_mutex_node *node)
{
	BUG_ON(!lock);
	kd_mutex_count_transition(node, NULL, lock);
}

static __always_inline void kd_mutex_count_exit(struct kd_mutex *lock,
					       struct kd_mutex_node *node)
{
	BUG_ON(!lock);
	kd_mutex_count_transition(node, lock, NULL);
}

#endif
