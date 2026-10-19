/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_STATE_H
#define KD_MUTEX_STATE_H

#include "kd_mutex.h"
#include <linux/bug.h>
#include <linux/limits.h>

static __always_inline u32 kd_mutex_gate_read(struct kd_mutex *lock)
{
	return (u32)atomic_read_acquire(&lock->delegation_state);
}

/* Only this CAS claims a free gate. Waiter records are independently owned by
 * reserved nodes, so a claim no longer retries against unrelated count writes. */
static __always_inline bool kd_mutex_gate_trylock(struct kd_mutex *lock)
{
	return atomic_cmpxchg(&lock->delegation_state, KD_MUTEX_GATE_FREE,
			      KD_MUTEX_GATE_ACQUIRING) == KD_MUTEX_GATE_FREE;
}

/* Only the gate owner stores an occupied phase. HELD release-publishes its
 * completed physical acquisition. RELEASING precedes the physical owner's
 * release operation, which orders that phase before an ordinary successor's
 * acquisition. FREE release follows the full physical unlock; this owner must
 * never touch the gate afterward because a new claimant can already own it. */
static __always_inline void kd_mutex_gate_set(struct kd_mutex *lock, u32 phase)
{
	BUG_ON(phase > KD_MUTEX_GATE_RELEASING);
	atomic_set_release(&lock->delegation_state, phase);
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
