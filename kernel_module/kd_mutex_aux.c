// SPDX-License-Identifier: GPL-2.0
/*
 * Address-indexed delegation records for the native-sized KD physical mutex.
 * Bucket locks serialize lookup/reference acquisition with final unlink. No
 * unreferenced pointer escapes a bucket, so immediate freeing needs no RCU.
 * Ordinary physical locking needs neither a record nor registry allocation.
 */
#include <linux/cache.h>
#include <linux/hash.h>
#include <linux/limits.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/slab.h>

#include "kd_mutex_aux.h"

#define KD_MUTEX_AUX_BITS 8
#define KD_MUTEX_AUX_BUCKETS (1U << KD_MUTEX_AUX_BITS)

struct kd_mutex_aux_bucket {
	raw_spinlock_t lock;
	struct hlist_head records;
	unsigned int count;
} ____cacheline_aligned_in_smp;

static struct kd_mutex_aux_bucket kd_mutex_aux_buckets[KD_MUTEX_AUX_BUCKETS] = {
	[0 ... KD_MUTEX_AUX_BUCKETS - 1] = {
		.lock = __RAW_SPIN_LOCK_UNLOCKED(kd_mutex_aux_buckets.lock),
	},
};
static struct kmem_cache *kd_mutex_aux_cache;
static int kd_mutex_aux_fail_once __read_mostly;
module_param_named(mutex_aux_fail_once, kd_mutex_aux_fail_once, int, 0644);

static struct kd_mutex_aux_bucket *kd_mutex_aux_bucket(struct kd_mutex *lock)
{
	return &kd_mutex_aux_buckets[hash_ptr(lock, KD_MUTEX_AUX_BITS)];
}

/* Caller holds the bucket's native raw spinlock. */
static struct kd_mutex_aux *
kd_mutex_aux_find_locked(struct kd_mutex_aux_bucket *bucket, struct kd_mutex *lock)
{
	struct kd_mutex_aux *aux;

	hlist_for_each_entry(aux, &bucket->records, link)
		if (aux->lock == lock)
			return aux;
	return NULL;
}

static void kd_mutex_aux_ref_locked(struct kd_mutex_aux *aux)
{
	BUG_ON(!aux->refs || aux->refs == UINT_MAX);
	aux->refs++;
}

struct kd_mutex_aux *kd_mutex_aux_lookup(struct kd_mutex *lock)
{
	struct kd_mutex_aux_bucket *bucket;
	struct kd_mutex_aux *aux;
	unsigned long flags;

	if (!lock)
		return NULL;
	bucket = kd_mutex_aux_bucket(lock);
	flags = _raw_spin_lock_irqsave(&bucket->lock);
	aux = kd_mutex_aux_find_locked(bucket, lock);
	if (aux)
		kd_mutex_aux_ref_locked(aux);
	_raw_spin_unlock_irqrestore(&bucket->lock, flags);
	return aux;
}

struct kd_mutex_aux *kd_mutex_aux_get(struct kd_mutex *lock)
{
	struct kd_mutex_aux_bucket *bucket;
	struct kd_mutex_aux *aux, *candidate;
	unsigned long flags;

	if (!lock)
		return NULL;
	aux = kd_mutex_aux_lookup(lock);
	if (aux)
		return aux;
	/* Allocation precedes all publication and occurs outside bucket locks.
	 * Refusal leaves the original KD physical primitive fully available. */
	if (unlikely(READ_ONCE(kd_mutex_aux_fail_once) == 1) &&
	    cmpxchg(&kd_mutex_aux_fail_once, 1, 0) == 1)
		return NULL;
	candidate = kmem_cache_alloc(kd_mutex_aux_cache, GFP_ATOMIC);
	if (!candidate)
		return kd_mutex_aux_lookup(lock);
	candidate->lock = lock;
	candidate->refs = 1;
	candidate->physical_owner = NULL;
	atomic_set(&candidate->state, 0);
	candidate->tail = 0;
	atomic_set(&candidate->waiter_count, 0);
	bucket = kd_mutex_aux_bucket(lock);
	flags = _raw_spin_lock_irqsave(&bucket->lock);
	aux = kd_mutex_aux_find_locked(bucket, lock);
	if (aux) {
		/* A racing creator owns the sole record for this address. */
		kd_mutex_aux_ref_locked(aux);
	} else {
		aux = candidate;
		BUG_ON(bucket->count == UINT_MAX);
		hlist_add_head(&aux->link, &bucket->records);
		bucket->count++;
	}
	_raw_spin_unlock_irqrestore(&bucket->lock, flags);
	if (aux != candidate)
		kmem_cache_free(kd_mutex_aux_cache, candidate);
	return aux;
}

/* A live invocation or owner reference must already protect aux. */
void kd_mutex_aux_ref(struct kd_mutex_aux *aux)
{
	struct kd_mutex_aux_bucket *bucket = kd_mutex_aux_bucket(aux->lock);
	unsigned long flags = _raw_spin_lock_irqsave(&bucket->lock);

	kd_mutex_aux_ref_locked(aux);
	_raw_spin_unlock_irqrestore(&bucket->lock, flags);
}

void kd_mutex_aux_put(struct kd_mutex_aux *aux)
{
	struct kd_mutex_aux_bucket *bucket = kd_mutex_aux_bucket(aux->lock);
	unsigned long flags = _raw_spin_lock_irqsave(&bucket->lock);
	bool retire;

	BUG_ON(!aux->refs);
	retire = --aux->refs == 0;
	if (retire) {
		/* References cover reservations before tail publication, all delayed
		 * links, physical ownership and frames after early gate release.
		 * Empty queue fields alone cannot establish any of those lifetimes. */
		BUG_ON(READ_ONCE(aux->physical_owner) || atomic_read(&aux->state) ||
		       READ_ONCE(aux->tail) || atomic_read(&aux->waiter_count));
		BUG_ON(!bucket->count);
		hlist_del(&aux->link);
		bucket->count--;
	}
	_raw_spin_unlock_irqrestore(&bucket->lock, flags);
	if (retire)
		kmem_cache_free(kd_mutex_aux_cache, aux);
}

/* Observations hold the bucket only while reading the record. They allocate
 * nothing and retain no pointer. Physical acquisition remains the owner CAS. */
bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task)
{
	struct kd_mutex_aux_bucket *bucket = kd_mutex_aux_bucket(lock);
	struct kd_mutex_aux *aux;
	unsigned long flags = _raw_spin_lock_irqsave(&bucket->lock);
	bool owned;

	aux = kd_mutex_aux_find_locked(bucket, lock);
	owned = aux && task && READ_ONCE(aux->physical_owner) == task;
	_raw_spin_unlock_irqrestore(&bucket->lock, flags);
	return owned;
}

bool kd_mutex_combiner_active(struct kd_mutex *lock)
{
	struct kd_mutex_aux_bucket *bucket = kd_mutex_aux_bucket(lock);
	struct kd_mutex_aux *aux;
	unsigned long flags = _raw_spin_lock_irqsave(&bucket->lock);
	bool active;

	aux = kd_mutex_aux_find_locked(bucket, lock);
	active = aux && READ_ONCE(aux->locked) == KD_MUTEX_GATE_COMBINER;
	_raw_spin_unlock_irqrestore(&bucket->lock, flags);
	return active;
}
EXPORT_SYMBOL_GPL(kd_mutex_combiner_active);

int kd_mutex_aux_waiter_count(struct kd_mutex *lock)
{
	struct kd_mutex_aux_bucket *bucket;
	struct kd_mutex_aux *aux;
	unsigned long flags;
	int count;

	if (!lock)
		return -EINVAL;
	bucket = kd_mutex_aux_bucket(lock);
	flags = _raw_spin_lock_irqsave(&bucket->lock);
	aux = kd_mutex_aux_find_locked(bucket, lock);
	count = aux ? atomic_read(&aux->waiter_count) : 0;
	_raw_spin_unlock_irqrestore(&bucket->lock, flags);
	return count;
}

bool kd_mutex_aux_is_idle(struct kd_mutex *lock)
{
	struct kd_mutex_aux_bucket *bucket = kd_mutex_aux_bucket(lock);
	unsigned long flags = _raw_spin_lock_irqsave(&bucket->lock);
	bool idle = !kd_mutex_aux_find_locked(bucket, lock);

	_raw_spin_unlock_irqrestore(&bucket->lock, flags);
	return idle;
}

/* Exact membership at each bucket, suitable only after callers stop and join.
 * No globally contended approximate counter substitutes for those records. */
unsigned int kd_mutex_debug_aux_count(void)
{
	unsigned int i, count = 0;

	for (i = 0; i < KD_MUTEX_AUX_BUCKETS; i++) {
		struct kd_mutex_aux_bucket *bucket = &kd_mutex_aux_buckets[i];
		unsigned long flags = _raw_spin_lock_irqsave(&bucket->lock);

		BUG_ON(UINT_MAX - count < bucket->count);
		count += bucket->count;
		_raw_spin_unlock_irqrestore(&bucket->lock, flags);
	}
	return count;
}
EXPORT_SYMBOL_GPL(kd_mutex_debug_aux_count);

bool kd_mutex_aux_all_idle(void)
{
	unsigned int i;

	for (i = 0; i < KD_MUTEX_AUX_BUCKETS; i++) {
		struct kd_mutex_aux_bucket *bucket = &kd_mutex_aux_buckets[i];
		unsigned long flags = _raw_spin_lock_irqsave(&bucket->lock);
		bool idle = hlist_empty(&bucket->records);

		_raw_spin_unlock_irqrestore(&bucket->lock, flags);
		if (!idle)
			return false;
	}
	return true;
}

int kd_mutex_aux_init(void)
{
	BUILD_BUG_ON(sizeof(struct kd_mutex_aux) != 4 * L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_mutex_aux, physical_owner) != L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_mutex_aux, tail) != 2 * L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_mutex_aux, waiter_count) != 3 * L1_CACHE_BYTES);
	BUG_ON(kd_mutex_aux_cache || !kd_mutex_aux_all_idle());
	kd_mutex_aux_cache = kmem_cache_create("kd_mutex_aux", sizeof(struct kd_mutex_aux),
					     __alignof__(struct kd_mutex_aux), 0, NULL);
	return kd_mutex_aux_cache ? 0 : -ENOMEM;
}

void kd_mutex_aux_exit(void)
{
	/* Provider teardown has stopped callers and verified every exact lease. */
	BUG_ON(!kd_mutex_aux_all_idle());
	if (kd_mutex_aux_cache) {
		kmem_cache_destroy(kd_mutex_aux_cache);
		kd_mutex_aux_cache = NULL;
	}
}
