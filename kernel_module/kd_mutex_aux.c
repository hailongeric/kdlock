// SPDX-License-Identifier: GPL-2.0
/*
 * Address-indexed delegation records for the native-sized KD physical mutex.
 * RCU protects lookup until an exact reference is acquired. Bucket locks
 * serialize publication with the final zero transition and unlink; readers
 * cannot resurrect a retired record. Deferred frees outlive all RCU readers.
 * Ordinary physical locking needs neither a record nor registry allocation.
 */
#include <linux/cache.h>
#include <linux/hash.h>
#include <linux/limits.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/rculist.h>
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

/* Caller holds RCU, the bucket, or an existing reference. A zero count may
 * still be visible to an old RCU reader, but must never become live again. */
static bool kd_mutex_aux_try_ref(struct kd_mutex_aux *aux)
{
	int refs = atomic_read(&aux->refs);

	for (;;) {
		BUG_ON(refs < 0 || refs == INT_MAX);
		if (!refs)
			return false;
		if (atomic_try_cmpxchg(&aux->refs, &refs, refs + 1))
			return true;
	}
}

/* Caller holds an RCU read-side section for the returned borrowed pointer. */
static struct kd_mutex_aux *
kd_mutex_aux_find_rcu(struct kd_mutex_aux_bucket *bucket, struct kd_mutex *lock)
{
	struct kd_mutex_aux *aux;

	hlist_for_each_entry_rcu(aux, &bucket->records, link)
		if (aux->lock == lock)
			return aux;
	return NULL;
}

struct kd_mutex_aux *kd_mutex_aux_lookup(struct kd_mutex *lock)
{
	struct kd_mutex_aux_bucket *bucket;
	struct kd_mutex_aux *aux;

	if (!lock)
		return NULL;
	bucket = kd_mutex_aux_bucket(lock);
	rcu_read_lock();
	aux = kd_mutex_aux_find_rcu(bucket, lock);
	if (aux && !kd_mutex_aux_try_ref(aux))
		aux = NULL;
	/* Successful reference acquisition extends storage lifetime beyond RCU.
	 * A miss races only publication/retirement; get rechecks under the bucket. */
	rcu_read_unlock();
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
	atomic_set(&candidate->refs, 1);
	candidate->physical_owner = NULL;
	atomic_set(&candidate->state, 0);
	candidate->tail = 0;
	atomic_set(&candidate->waiter_count, 0);
	bucket = kd_mutex_aux_bucket(lock);
	flags = _raw_spin_lock_irqsave(&bucket->lock);
	aux = kd_mutex_aux_find_locked(bucket, lock);
	if (aux) {
		/* The final decrement and unlink share this lock, so every linked
		 * record is live here. A racing creator supplies the unique record. */
		BUG_ON(!kd_mutex_aux_try_ref(aux));
	} else {
		aux = candidate;
		BUG_ON(bucket->count == UINT_MAX);
		/* Publish only after the key, exact reference and all state fields
		 * are initialized. RCU readers observe one initialized generation. */
		hlist_add_head_rcu(&aux->link, &bucket->records);
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
	BUG_ON(!kd_mutex_aux_try_ref(aux));
}

static void kd_mutex_aux_free(struct rcu_head *rcu)
{
	struct kd_mutex_aux *aux = container_of(rcu, struct kd_mutex_aux, rcu);

	/* The lock object may already have been destroyed or reused. Only this
	 * retired allocation is touched; exit retains the slab through callbacks. */
	kmem_cache_free(kd_mutex_aux_cache, aux);
}

void kd_mutex_aux_put(struct kd_mutex_aux *aux)
{
	struct kd_mutex_aux_bucket *bucket;
	unsigned long flags;
	int refs = atomic_read(&aux->refs);
	bool retire;

	/* Every caller owns the reference it drops. Nonfinal puts need no writer
	 * lock; retaining the last reference until locked prevents a creator from
	 * finding a zero-count record still linked in the bucket. */
	for (;;) {
		BUG_ON(refs <= 0);
		if (refs == 1)
			break;
		if (atomic_try_cmpxchg(&aux->refs, &refs, refs - 1))
			return;
	}
	bucket = kd_mutex_aux_bucket(aux->lock);
	flags = _raw_spin_lock_irqsave(&bucket->lock);
	/* An RCU getter may have acquired another reference while we took the
	 * bucket. Only this decrement's zero result authorizes retirement. */
	BUG_ON(atomic_read(&aux->refs) <= 0);
	retire = atomic_dec_and_test(&aux->refs);
	if (retire) {
		/* References cover reservations before tail publication, all delayed
		 * links, physical ownership and frames after early gate release.
		 * Empty queue fields alone cannot establish any of those lifetimes. */
		BUG_ON(READ_ONCE(aux->physical_owner) || atomic_read(&aux->state) ||
		       READ_ONCE(aux->tail) || atomic_read(&aux->waiter_count));
		BUG_ON(!bucket->count);
		hlist_del_rcu(&aux->link);
		bucket->count--;
	}
	_raw_spin_unlock_irqrestore(&bucket->lock, flags);
	if (retire)
		call_rcu(&aux->rcu, kd_mutex_aux_free);
}

/* Observations borrow storage only inside RCU and never retain a pointer.
 * Retirement requires these owner/queue fields already clear. The exact owner
 * comparison is unchanged; a combiner hint never authorizes acquisition. */
bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task)
{
	struct kd_mutex_aux_bucket *bucket = kd_mutex_aux_bucket(lock);
	struct kd_mutex_aux *aux;
	bool owned;

	rcu_read_lock();
	aux = kd_mutex_aux_find_rcu(bucket, lock);
	owned = aux && task && READ_ONCE(aux->physical_owner) == task;
	rcu_read_unlock();
	return owned;
}

bool kd_mutex_combiner_active(struct kd_mutex *lock)
{
	struct kd_mutex_aux_bucket *bucket = kd_mutex_aux_bucket(lock);
	struct kd_mutex_aux *aux;
	bool active;

	rcu_read_lock();
	aux = kd_mutex_aux_find_rcu(bucket, lock);
	active = aux && READ_ONCE(aux->locked) == KD_MUTEX_GATE_COMBINER;
	rcu_read_unlock();
	return active;
}
EXPORT_SYMBOL_GPL(kd_mutex_combiner_active);

int kd_mutex_aux_waiter_count(struct kd_mutex *lock)
{
	struct kd_mutex_aux_bucket *bucket;
	struct kd_mutex_aux *aux;
	int count;

	if (!lock)
		return -EINVAL;
	bucket = kd_mutex_aux_bucket(lock);
	rcu_read_lock();
	aux = kd_mutex_aux_find_rcu(bucket, lock);
	count = aux ? atomic_read(&aux->waiter_count) : 0;
	rcu_read_unlock();
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
	BUILD_BUG_ON(offsetof(struct kd_mutex_aux, refs) !=
		     3 * L1_CACHE_BYTES + sizeof(atomic_t));
	BUG_ON(kd_mutex_aux_cache || !kd_mutex_aux_all_idle());
	kd_mutex_aux_cache = kmem_cache_create("kd_mutex_aux", sizeof(struct kd_mutex_aux),
					     __alignof__(struct kd_mutex_aux), 0, NULL);
	return kd_mutex_aux_cache ? 0 : -ENOMEM;
}

void kd_mutex_aux_exit(void)
{
	/* Provider teardown has stopped callers and verified every exact lease.
	 * Empty membership permits callbacks still awaiting their RCU readers. */
	BUG_ON(!kd_mutex_aux_all_idle());
	if (kd_mutex_aux_cache) {
		/* Keep both callback code and its slab alive through the last free. */
		rcu_barrier();
		kmem_cache_destroy(kd_mutex_aux_cache);
		kd_mutex_aux_cache = NULL;
	}
}
