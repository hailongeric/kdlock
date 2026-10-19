// SPDX-License-Identifier: GPL-2.0
/*
 * Direct-indexed delegation records for the native-sized KD physical mutex.
 * Permanent table storage needs neither a lookup lock nor deferred freeing.
 * Exact references protect each active generation. A collision or an in-flight
 * lifecycle reservation falls back before publishing any queue state.
 */
#include <linux/cache.h>
#include <linux/hash.h>
#include <linux/limits.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/sched.h>
#include <linux/vmalloc.h>

#include "kd_mutex_aux.h"
#include "kd_mutex_stats.h"

#define KD_MUTEX_AUX_BITS 16
#define KD_MUTEX_AUX_SLOTS (1U << KD_MUTEX_AUX_BITS)
/* Keep a huge count range below each state boundary. A negative-state getter
 * owns a rejected pin until its put, so lifecycle changes must preserve those
 * low bits. LIVE zero still has its key; only the zero-to-BUSY CAS reserves it. */
#define KD_MUTEX_AUX_BUSY (-(1L << 62))
#define KD_MUTEX_AUX_FREE LONG_MIN
#define KD_MUTEX_AUX_COUNT_MASK ((1UL << 62) - 1)
/* Keep admission far below any state boundary. Even concurrent increments
 * already in flight when the limit is observed stay in the same quadrant. */
#define KD_MUTEX_AUX_MAX_REFS INT_MAX

/* One deterministic slot per address prevents duplicate live records without
 * an insertion arbiter. The 16 MiB allocation serves every lock until provider
 * teardown; unrelated colliding locks keep the ordinary KD physical path. */
static struct kd_mutex_aux *kd_mutex_aux_slots;
static int kd_mutex_aux_fail_once __read_mostly;
module_param_named(mutex_aux_fail_once, kd_mutex_aux_fail_once, int, 0644);

/* Refusal observations only. Successful lookups/references never write these
 * counters, and no ownership, reclamation or idle decision reads them. */
KD_MUTEX_STAT(kd_mutex_aux_collisions);
KD_MUTEX_STAT(kd_mutex_aux_busy);
KD_MUTEX_STAT(kd_mutex_aux_generation_races);
KD_MUTEX_STAT(kd_mutex_aux_exhausted);
KD_MUTEX_STAT(kd_mutex_aux_injected_failures);

static struct kd_mutex_aux *kd_mutex_aux_slot(struct kd_mutex *lock)
{
	return &kd_mutex_aux_slots[hash_ptr(lock, KD_MUTEX_AUX_BITS)];
}

/* One fetch-add pins LIVE, including its empty interval before retirement.
 * A negative result never authorizes protocol-field access. Its rejected pin
 * must use the ordinary put: publication can turn it into the last LIVE count
 * before it is released. No retry loop writes this shared line under load. */
static bool kd_mutex_aux_try_ref(struct kd_mutex_aux *aux)
{
	long refs = atomic_long_fetch_inc(&aux->refs);

	/* Fail closed at the admission bound, with an enormous guard band to
	 * the state bits. The unused positive quadrant is invalid as well. */
	BUG_ON(((unsigned long)refs & KD_MUTEX_AUX_COUNT_MASK) >=
	       KD_MUTEX_AUX_MAX_REFS || refs > (long)KD_MUTEX_AUX_COUNT_MASK);
	if (likely(refs >= 0))
		return true;
	kd_mutex_aux_put(aux);
	return false;
}

static struct kd_mutex_aux *
kd_mutex_aux_find_ref(struct kd_mutex_aux *aux, struct kd_mutex *lock)
{
	/* Reject ordinary collisions without writing the other lock's ref line.
	 * This load alone never grants a reference or authorizes field access. */
	if (READ_ONCE(aux->lock) != lock || !kd_mutex_aux_try_ref(aux))
		return NULL;
	/* A stale increment may pin a newer generation. It is usable
	 * only when this post-acquisition key check identifies the requested lock. */
	if (likely(READ_ONCE(aux->lock) == lock))
		return aux;
	kd_mutex_aux_put(aux);
	return NULL;
}

static void kd_mutex_aux_note_refusal(struct kd_mutex_aux *aux,
				    struct kd_mutex *lock, long refs)
{
	struct kd_mutex *key = READ_ONCE(aux->lock);

	/* The sampled key can change after the failed reference attempt. Keep
	 * such races separate from an observed collision or BUSY reservation. */
	if (refs >= KD_MUTEX_AUX_BUSY && refs < 0)
		this_cpu_inc(kd_mutex_aux_busy);
	else if (refs >= 0 && key && key != lock)
		this_cpu_inc(kd_mutex_aux_collisions);
	else
		this_cpu_inc(kd_mutex_aux_generation_races);
}

/* Caller exclusively owns BUSY. The begin barrier orders the odd marker before
 * key changes; a release store alone would only order preceding writes. */
static u64 kd_mutex_aux_sequence_begin(struct kd_mutex_aux *aux)
{
	u64 sequence = READ_ONCE(aux->sequence);

	BUG_ON(sequence & 1);
	WRITE_ONCE(aux->sequence, sequence + 1);
	smp_wmb();
	return sequence;
}

static void kd_mutex_aux_sequence_end(struct kd_mutex_aux *aux, u64 sequence)
{
	/* Never wrap and admit an A -> B -> A observational ABA. The final odd
	 * value permanently disables this slot, with no active reference left. */
	smp_store_release(&aux->sequence,
		sequence == U64_MAX - 1 ? U64_MAX : sequence + 2);
}

static bool kd_mutex_aux_observation_valid(struct kd_mutex_aux *aux, u64 sequence)
{
	/* Key and protocol-field reads must finish before the second sequence
	 * load. Naturally aligned u64 loads are atomic on the supported x86-64. */
	smp_rmb();
	return READ_ONCE(aux->sequence) == sequence;
}

struct kd_mutex_aux *kd_mutex_aux_lookup(struct kd_mutex *lock)
{
	if (!lock || unlikely(!kd_mutex_aux_slots))
		return NULL;
	return kd_mutex_aux_find_ref(kd_mutex_aux_slot(lock), lock);
}

struct kd_mutex_aux *kd_mutex_aux_get(struct kd_mutex *lock)
{
	struct kd_mutex_aux *aux, *found;
	u64 sequence;
	long refs;

	if (!lock || unlikely(!kd_mutex_aux_slots))
		return NULL;
	aux = kd_mutex_aux_slot(lock);
	found = kd_mutex_aux_find_ref(aux, lock);
	if (found)
		return found;
	refs = atomic_long_read(&aux->refs);
	if (refs == KD_MUTEX_AUX_FREE)
		refs = atomic_long_cmpxchg(&aux->refs, KD_MUTEX_AUX_FREE, KD_MUTEX_AUX_BUSY);
	if (refs != KD_MUTEX_AUX_FREE) {
		/* A creator may already have finished. Take one ordinary lookup;
		 * a collision or BUSY result never waits for that creator to run. */
		found = kd_mutex_aux_find_ref(aux, lock);
		if (!found)
			kd_mutex_aux_note_refusal(aux, lock, refs);
		return found;
	}
	/* Only a new slot claim consumes the fault-injection request. Existing
	 * live references, ordinary collisions and exhausted slots do not. */
	sequence = READ_ONCE(aux->sequence);
	if (unlikely(sequence >= U64_MAX - 1)) {
		this_cpu_inc(kd_mutex_aux_exhausted);
		smp_store_release(&aux->sequence, U64_MAX);
		atomic_long_add_return(KD_MUTEX_AUX_FREE - KD_MUTEX_AUX_BUSY, &aux->refs);
		return NULL;
	}
	BUG_ON(sequence & 1);
	if (unlikely(READ_ONCE(kd_mutex_aux_fail_once) == 1) &&
	    cmpxchg(&kd_mutex_aux_fail_once, 1, 0) == 1) {
		this_cpu_inc(kd_mutex_aux_injected_failures);
		atomic_long_add_return(KD_MUTEX_AUX_FREE - KD_MUTEX_AUX_BUSY, &aux->refs);
		return NULL;
	}
	/* The initial table is zeroed once. Every final put verifies the same
	 * empty protocol state before making a slot reusable; no packet clear or
	 * mutable-field initialization occurs after publication. */
	BUG_ON(READ_ONCE(aux->lock) || READ_ONCE(aux->physical_owner) ||
	       atomic_read(&aux->state) || READ_ONCE(aux->tail) ||
	       atomic_read(&aux->waiter_count));
	sequence = kd_mutex_aux_sequence_begin(aux);
	WRITE_ONCE(aux->lock, lock);
	kd_mutex_aux_sequence_end(aux, sequence);
	/* Publish the creator's reference without erasing rejected pins. The
	 * returning RMW orders all initialization before a LIVE getter's RMW. */
	atomic_long_add_return(1 - KD_MUTEX_AUX_BUSY, &aux->refs);
	return aux;
}

/* A live invocation or owner reference must already protect aux. */
void kd_mutex_aux_ref(struct kd_mutex_aux *aux)
{
	BUG_ON(!kd_mutex_aux_try_ref(aux));
}

void kd_mutex_aux_put(struct kd_mutex_aux *aux)
{
	long refs = atomic_long_fetch_dec(&aux->refs);
	u64 sequence;

	/* Every put owns one low-bit count, whether accepted or rejected. Only
	 * LIVE's last count can start retirement. A pin from zero can win first;
	 * the losing put then owns nothing and must not inspect protocol fields. */
	BUG_ON(!((unsigned long)refs & KD_MUTEX_AUX_COUNT_MASK) ||
	       refs > (long)KD_MUTEX_AUX_COUNT_MASK);
	if (refs != 1 || atomic_long_cmpxchg(&aux->refs, 0, KD_MUTEX_AUX_BUSY))
		return;
	/* A delayed CAS can reserve a later empty generation after reuse. Its
	 * success, not the former key, authorizes this generation-neutral cleanup. */
	/* References cover unpublished reservations, delayed links, physical
	 * owners and frames after early gate release. Zero queue fields cannot
	 * replace those references as a retirement decision. */
	BUG_ON(READ_ONCE(aux->physical_owner) || atomic_read(&aux->state) ||
	       READ_ONCE(aux->tail) || atomic_read(&aux->waiter_count));
	sequence = kd_mutex_aux_sequence_begin(aux);
	WRITE_ONCE(aux->lock, NULL);
	kd_mutex_aux_sequence_end(aux, sequence);
	/* Retain any negative-state pins that arrived during retirement. The
	 * release RMW makes completed cleanup visible before an exact-FREE claim.
	 * A creator may win immediately: never access the slot after this add. */
	atomic_long_add_return(KD_MUTEX_AUX_FREE - KD_MUTEX_AUX_BUSY, &aux->refs);
}

/* Read-only observations never write the reference line. Lifecycle sequence
 * validation rejects a key/field mix from different generations. An actual
 * delegation owner retains its exact reference, so its generation cannot
 * change during the ownership check. Combiner state remains only a hint. */
bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task)
{
	struct kd_mutex_aux *aux;
	u64 sequence;
	bool owned;

	if (!lock || !task || unlikely(!kd_mutex_aux_slots))
		return false;
	aux = kd_mutex_aux_slot(lock);
	sequence = smp_load_acquire(&aux->sequence);
	if (sequence & 1)
		return false;
	owned = READ_ONCE(aux->lock) == lock &&
		READ_ONCE(aux->physical_owner) == task;
	return kd_mutex_aux_observation_valid(aux, sequence) && owned;
}

/* Only current can end its established owner lifetime. Its synchronous unlock
 * therefore borrows that exact reference through physical and gate release,
 * without acquiring a temporary lookup reference. Sequence validation rejects
 * mixed generations; this helper never lends another task's owner lifetime. */
struct kd_mutex_aux *kd_mutex_aux_borrow_owned(struct kd_mutex *lock)
{
	struct kd_mutex_aux *aux;
	u64 sequence;
	bool owned;

	if (!lock || unlikely(!kd_mutex_aux_slots))
		return NULL;
	aux = kd_mutex_aux_slot(lock);
	sequence = smp_load_acquire(&aux->sequence);
	if (sequence & 1)
		return NULL;
	owned = READ_ONCE(aux->lock) == lock &&
		READ_ONCE(aux->physical_owner) == current;
	if (!kd_mutex_aux_observation_valid(aux, sequence) || !owned)
		return NULL;
	return aux;
}

bool kd_mutex_combiner_active(struct kd_mutex *lock)
{
	struct kd_mutex_aux *aux;
	u64 sequence;
	bool active;

	if (!lock || unlikely(!kd_mutex_aux_slots))
		return false;
	aux = kd_mutex_aux_slot(lock);
	sequence = smp_load_acquire(&aux->sequence);
	if (sequence & 1)
		return false;
	active = READ_ONCE(aux->lock) == lock &&
		READ_ONCE(aux->locked) == KD_MUTEX_GATE_COMBINER;
	return kd_mutex_aux_observation_valid(aux, sequence) && active;
}
EXPORT_SYMBOL_GPL(kd_mutex_combiner_active);

int kd_mutex_aux_waiter_count(struct kd_mutex *lock)
{
	struct kd_mutex_aux *aux;
	u64 sequence;
	int count;

	if (!lock)
		return -EINVAL;
	if (unlikely(!kd_mutex_aux_slots))
		return 0;
	aux = kd_mutex_aux_slot(lock);
	sequence = smp_load_acquire(&aux->sequence);
	if (sequence & 1)
		return sequence == U64_MAX &&
			atomic_long_read(&aux->refs) == KD_MUTEX_AUX_FREE ? 0 : -EAGAIN;
	count = READ_ONCE(aux->lock) == lock ? atomic_read(&aux->waiter_count) : 0;
	return kd_mutex_aux_observation_valid(aux, sequence) ? count : -EAGAIN;
}

bool kd_mutex_aux_is_idle(struct kd_mutex *lock)
{
	struct kd_mutex_aux *aux;
	u64 sequence;
	long refs;
	bool different;

	if (unlikely(!kd_mutex_aux_slots))
		return true;
	aux = kd_mutex_aux_slot(lock);
	refs = atomic_long_read(&aux->refs);
	if (refs == KD_MUTEX_AUX_FREE)
		return true;
	if (refs <= 0)
		return false;
	sequence = smp_load_acquire(&aux->sequence);
	if (sequence & 1)
		return false;
	different = READ_ONCE(aux->lock) != lock;
	return kd_mutex_aux_observation_valid(aux, sequence) && different;
}

/* Exact slot reservations/references, suitable only after callers stop and
 * join. BUSY is counted as active; an exhausted, free-reference slot is idle. */
unsigned int kd_mutex_debug_aux_count(void)
{
	unsigned int i, count = 0;

	if (unlikely(!kd_mutex_aux_slots))
		return 0;
	for (i = 0; i < KD_MUTEX_AUX_SLOTS; i++)
		count += atomic_long_read(&kd_mutex_aux_slots[i].refs) != KD_MUTEX_AUX_FREE;
	return count;
}
EXPORT_SYMBOL_GPL(kd_mutex_debug_aux_count);

bool kd_mutex_aux_all_idle(void)
{
	unsigned int i;

	if (unlikely(!kd_mutex_aux_slots))
		return true;
	for (i = 0; i < KD_MUTEX_AUX_SLOTS; i++)
		if (atomic_long_read(&kd_mutex_aux_slots[i].refs) != KD_MUTEX_AUX_FREE)
			return false;
	return true;
}

int kd_mutex_aux_init(void)
{
	struct kd_mutex_aux *slots;
	unsigned int i;

	BUILD_BUG_ON(sizeof(struct kd_mutex_aux) != 4 * L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_mutex_aux, sequence) != sizeof(void *));
	BUILD_BUG_ON(offsetof(struct kd_mutex_aux, physical_owner) != L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_mutex_aux, tail) != 2 * L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_mutex_aux, waiter_count) != 3 * L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_mutex_aux, refs) !=
		     3 * L1_CACHE_BYTES + sizeof(atomic_long_t));
	BUILD_BUG_ON(sizeof(long) != sizeof(u64));
	BUG_ON(kd_mutex_aux_slots);
	slots = vzalloc(KD_MUTEX_AUX_SLOTS * sizeof(*slots));
	if (!slots)
		return -ENOMEM;
	for (i = 0; i < KD_MUTEX_AUX_SLOTS; i++)
		atomic_long_set(&slots[i].refs, KD_MUTEX_AUX_FREE);
	kd_mutex_aux_slots = slots;
	return 0;
}

void kd_mutex_aux_exit(void)
{
	/* Provider teardown has stopped/joined callers, including observations.
	 * Empty references alone cannot authorize freeing beneath a new caller. */
	BUG_ON(!kd_mutex_aux_all_idle());
	pr_info("kd_mutex aux: slots=%u bytes=%zu collision=%llu busy=%llu generation_race=%llu exhausted=%llu injected=%llu\n",
		KD_MUTEX_AUX_SLOTS, KD_MUTEX_AUX_SLOTS * sizeof(*kd_mutex_aux_slots),
		(unsigned long long)KD_MUTEX_STAT_READ(kd_mutex_aux_collisions),
		(unsigned long long)KD_MUTEX_STAT_READ(kd_mutex_aux_busy),
		(unsigned long long)KD_MUTEX_STAT_READ(kd_mutex_aux_generation_races),
		(unsigned long long)KD_MUTEX_STAT_READ(kd_mutex_aux_exhausted),
		(unsigned long long)KD_MUTEX_STAT_READ(kd_mutex_aux_injected_failures));
	vfree(kd_mutex_aux_slots);
	kd_mutex_aux_slots = NULL;
}
