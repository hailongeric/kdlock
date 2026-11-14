/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_SPIN_POLICY_H
#define KDLOCK_SPIN_POLICY_H
#include <linux/types.h>

/* Compile-time policy defaults, independent of source eligibility and batch cap. */
#define KD_SPIN_POLICY_SLOTS 8
#define KD_SPIN_POLICY_WINDOW 100
#define KD_SPIN_POLICY_SLOW 99
#define KD_SPIN_POLICY_PERIOD 16

struct kd_spin_contention {
	const void *object;
	unsigned long epoch;
	unsigned int samples, slow, probe_tick;
	bool strong;
};
struct kd_spin_contention_cache {
	struct kd_spin_contention slot[KD_SPIN_POLICY_SLOTS];
};
struct kd_mutex;
unsigned long kd_spin_policy_epoch(struct kd_mutex *lock);

static inline struct kd_spin_contention *kd_spin_contention_slot(
		struct kd_spin_contention_cache *cache, const void *object)
{
	unsigned long key = (unsigned long)object;

	return &cache->slot[((key >> 6) ^ (key >> 12)) % KD_SPIN_POLICY_SLOTS];
}

/* Pinned task context only. Collisions and new object lifetimes restart cold;
 * another lock's samples never contribute. No clocks, allocation or shared
 * sampling counter. A completed window controls the next partial window.
 */
static inline bool kd_spin_contention_sample(struct kd_spin_contention_cache *cache,
		const void *object, unsigned long epoch, bool slow, bool *probe)
{
	struct kd_spin_contention *policy;

	*probe = false;
	if (!epoch)
		return false;
	policy = kd_spin_contention_slot(cache, object);
	if (policy->object != object || policy->epoch != epoch) {
		policy->object = object;
		policy->epoch = epoch;
		policy->samples = 0;
		policy->slow = 0;
		policy->probe_tick = 0;
		policy->strong = false;
	}
	policy->slow += slow;
	if (++policy->samples == KD_SPIN_POLICY_WINDOW) {
		policy->strong = policy->slow >= KD_SPIN_POLICY_SLOW;
		policy->samples = 0;
		policy->slow = 0;
	}
	if (!policy->strong) {
		policy->probe_tick = 0;
		return false;
	}
	*probe = policy->probe_tick == 0;
	policy->probe_tick = (policy->probe_tick + 1) % KD_SPIN_POLICY_PERIOD;
	return true;
}
#endif
