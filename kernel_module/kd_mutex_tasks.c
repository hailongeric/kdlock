// SPDX-License-Identifier: GPL-2.0

/* RCU task identities retain exact acquisition references. Zero references
 * remove routing immediately; a bounded inactive cache avoids allocation and
 * RCU callback traffic on every contested acquisition. Eviction waits for RCU. */
#include <linux/cache.h>
#include <linux/hash.h>
#include <linux/rculist.h>
#include <linux/moduleparam.h>
#include <linux/rcupdate.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/spinlock.h>

#include "kd_lock.h"
#include "kd_mutex_stats.h"

/* Keep task routing alive through queue waits, the owner's CS, and borrowed
 * native CSs, independently of CPU frequency or target-process selection.
 * Reads neither sleep nor allocate. Cached references use their own atomic;
 * only insertion and eviction take the bucket's lock. */
struct kd_mutex_task {
	struct hlist_node link;
	struct rcu_head rcu;
	struct task_struct *task;
	atomic_t refs; /* >=0 live identity, -1 claimed exclusively for eviction */
	unsigned int owned_holds; /* current task's ordinary/nested KD acquisitions */
};

#define KD_MUTEX_TASK_BITS 8
#define KD_MUTEX_TASK_BUCKETS (1U << KD_MUTEX_TASK_BITS)
#define KD_MUTEX_TASK_CACHE_PER_BUCKET 8

struct kd_mutex_task_bucket {
	raw_spinlock_t lock;
	struct hlist_head tasks;
	unsigned int count; /* resident identities; protected by this bucket's lock */
} ____cacheline_aligned_in_smp;

static struct kd_mutex_task_bucket kd_mutex_task_buckets[KD_MUTEX_TASK_BUCKETS] = {
	[0 ... KD_MUTEX_TASK_BUCKETS - 1] = {
		.lock = __RAW_SPIN_LOCK_UNLOCKED(kd_mutex_task_buckets.lock),
	},
};

static struct kd_mutex_task_bucket *kd_mutex_task_bucket(struct task_struct *task)
{
	return &kd_mutex_task_buckets[hash_ptr(task, KD_MUTEX_TASK_BITS)];
}

/* Controlled-drain snapshot only, as before: callers stop new acquisitions
 * before relying on idleness. Each bucket retains exact membership; no global
 * increment/decrement cacheline is written by every contending CPU. */
static unsigned int kd_mutex_task_count(void)
{
	unsigned int count = 0, i;
	struct kd_mutex_task *entry;

	rcu_read_lock();
	for (i = 0; i < KD_MUTEX_TASK_BUCKETS; i++)
		hlist_for_each_entry_rcu(entry, &kd_mutex_task_buckets[i].tasks, link)
			count += atomic_read(&entry->refs) > 0;
	rcu_read_unlock();
	return count;
}
KD_MUTEX_STAT(kd_mutex_task_failures);
KD_MUTEX_STAT(kd_mutex_task_reroutes);
static int kd_mutex_task_fail_once __read_mostly;
module_param_named(mutex_task_fail_once, kd_mutex_task_fail_once, int, 0644);

#ifdef KDLOCK_SELFTEST
/* Observe the real deferred free without replacing RCU or task references.
 * Hooks are unpublished during the probe, so only its records contribute. */
static atomic_t kd_mutex_task_test_frees = ATOMIC_INIT(0);
#endif

bool kd_mutex_task_active(struct task_struct *task)
{
	struct kd_mutex_task_bucket *bucket = kd_mutex_task_bucket(task);
	struct kd_mutex_task *entry;
	bool active = false;

	rcu_read_lock();
	hlist_for_each_entry_rcu(entry, &bucket->tasks, link) {
		if (entry->task == task) {
			active = atomic_read(&entry->refs) > 0;
			break;
		}
	}
	rcu_read_unlock();
	return active;
}

bool kd_mutex_task_reroute(struct task_struct *task)
{
	if (!kd_mutex_task_active(task))
		return false;
	this_cpu_inc(kd_mutex_task_reroutes);
	return true;
}

static void kd_mutex_task_free(struct rcu_head *rcu);

/* Caller holds the bucket lock. A concurrent cache hit can reactivate zero;
 * the CAS arbitrates that race without unlinking a newly active identity.
 * Once negative, no getter can revive the entry and RCU protects old readers. */
static bool kd_mutex_task_evict(struct kd_mutex_task_bucket *bucket,
				struct kd_mutex_task *entry)
{
	if (atomic_cmpxchg(&entry->refs, 0, -1) != 0)
		return false;
	hlist_del_rcu(&entry->link);
	WRITE_ONCE(bucket->count, bucket->count - 1);
	call_rcu(&entry->rcu, kd_mutex_task_free);
	return true;
}

bool kd_mutex_task_get(struct task_struct *task)
{
	struct kd_mutex_task_bucket *bucket = kd_mutex_task_bucket(task);
	struct kd_mutex_task *entry, *new;
	unsigned long flags;

	/* The test switch is normally zero. A read avoids taking exclusive
	 * ownership of its cacheline on every real acquisition; the CAS still
	 * allows exactly one injected failure when the switch is armed. */
	if (unlikely(READ_ONCE(kd_mutex_task_fail_once) == 1) &&
	    cmpxchg(&kd_mutex_task_fail_once, 1, 0) == 1)
		goto failure;
	rcu_read_lock();
	hlist_for_each_entry_rcu(entry, &bucket->tasks, link) {
		if (entry->task == task && atomic_add_unless(&entry->refs, 1, -1)) {
			rcu_read_unlock();
			return true;
		}
	}
	rcu_read_unlock();
	new = kmalloc(sizeof(*new), GFP_ATOMIC);
	if (!new)
		goto failure;
	raw_spin_lock_irqsave(&bucket->lock, flags);
	hlist_for_each_entry(entry, &bucket->tasks, link) {
		if (entry->task == task) {
			atomic_inc(&entry->refs);
			raw_spin_unlock_irqrestore(&bucket->lock, flags);
			kfree(new);
			return true;
		}
	}
	if (bucket->count >= KD_MUTEX_TASK_CACHE_PER_BUCKET) {
		hlist_for_each_entry(entry, &bucket->tasks, link)
			if (kd_mutex_task_evict(bucket, entry))
				break;
	}
	get_task_struct(task);
	new->task = task;
	new->owned_holds = 0;
	atomic_set(&new->refs, 1);
	hlist_add_head_rcu(&new->link, &bucket->tasks);
	WRITE_ONCE(bucket->count, bucket->count + 1);
	raw_spin_unlock_irqrestore(&bucket->lock, flags);
	return true;
failure:
	this_cpu_inc(kd_mutex_task_failures);
	return false;
}

static void kd_mutex_task_free(struct rcu_head *rcu)
{
	struct kd_mutex_task *entry = container_of(rcu, struct kd_mutex_task, rcu);

	put_task_struct(entry->task);
	kfree(entry);
#ifdef KDLOCK_SELFTEST
	atomic_inc(&kd_mutex_task_test_frees);
#endif
}

void kd_mutex_task_put(struct task_struct *task)
{
	struct kd_mutex_task_bucket *bucket = kd_mutex_task_bucket(task);
	struct kd_mutex_task *entry;
	unsigned long flags;

	rcu_read_lock();
	hlist_for_each_entry_rcu(entry, &bucket->tasks, link) {
		int refs;

		if (entry->task != task)
			continue;
		refs = atomic_dec_return(&entry->refs);

		WARN_ON_ONCE(refs < 0);
		/* Active collisions may exceed the cache bound. Only the cold
		 * zero transition of an overfull bucket needs writer serialization. */
		if (!refs && READ_ONCE(bucket->count) > KD_MUTEX_TASK_CACHE_PER_BUCKET) {
			raw_spin_lock_irqsave(&bucket->lock, flags);
			kd_mutex_task_evict(bucket, entry);
			raw_spin_unlock_irqrestore(&bucket->lock, flags);
		}
		rcu_read_unlock();
		return;
	}
	rcu_read_unlock();
	WARN_ON_ONCE(1);
}

bool kd_mutex_tasks_idle(void)
{
	/* Snapshot guard, not a barrier against arbitrary new native callers. */
	return !kd_mutex_task_count();
}

/* Outer-cookie calls are explicitly outermost entries. Ordinary/direct
 * controls can nest, so retain an exact task-local depth through their native
 * critical sections. An early A unlock while B is held must not execute an A
 * waiter that acquires B: the native B unlock is still below this call frame.
 * One routing reference pins the identity until the entire depth drains. */
static bool kd_owned_tracking_exhausted;

static struct kd_mutex_task *kd_owned_current_record(void)
{
	struct kd_mutex_task *entry;

	hlist_for_each_entry_rcu(entry, &kd_mutex_task_bucket(current)->tasks, link)
		if (entry->task == current)
			return entry;
	return NULL;
}

void kd_owned_mutex_task_enter(void)
{
	struct kd_mutex_task *entry;

	rcu_read_lock();
	entry = kd_owned_current_record();
	if (entry && entry->owned_holds) {
		BUG_ON(entry->owned_holds == UINT_MAX);
		entry->owned_holds++;
		rcu_read_unlock();
		return;
	}
	rcu_read_unlock();
	/* Refusal cannot make a mutex acquisition fail. If identity allocation
	 * fails, permanently disable new batches for this provider lifetime.
	 * Existing requests receive SELF handoff and retain their normal drain.
	 * Untracked tasks never start tracking a later nested acquisition. */
	if (unlikely(READ_ONCE(kd_owned_tracking_exhausted)))
		return;
	if (!kd_mutex_task_get(current)) {
		WRITE_ONCE(kd_owned_tracking_exhausted, true);
		pr_warn("kd_owned_mutex: task tracking exhausted; combining disabled until unload\n");
		return;
	}
	rcu_read_lock();
	entry = kd_owned_current_record();
	BUG_ON(!entry || entry->owned_holds);
	entry->owned_holds = 1;
	rcu_read_unlock();
}

void kd_owned_mutex_task_leave(void)
{
	struct kd_mutex_task *entry;
	bool put = false;

	rcu_read_lock();
	entry = kd_owned_current_record();
	if (entry && entry->owned_holds)
		put = !--entry->owned_holds;
	else
		BUG_ON(!READ_ONCE(kd_owned_tracking_exhausted));
	rcu_read_unlock();
	if (put)
		kd_mutex_task_put(current);
}

bool kd_owned_mutex_task_can_combine(void)
{
	struct kd_mutex_task *entry;
	bool allowed;

	if (unlikely(READ_ONCE(kd_owned_tracking_exhausted)))
		return false;
	rcu_read_lock();
	entry = kd_owned_current_record();
	allowed = !entry || !entry->owned_holds;
	rcu_read_unlock();
	return allowed;
}

static void kd_mutex_tasks_purge(void)
{
	/* Controlled teardown only: all hook callers and acquisitions must have
	 * finished before unregistering. This is not concurrent hot-unload support. */
	unsigned int i;

	for (i = 0; i < KD_MUTEX_TASK_BUCKETS; i++) {
		struct kd_mutex_task_bucket *bucket = &kd_mutex_task_buckets[i];
		struct kd_mutex_task *entry;
		struct hlist_node *next;
		unsigned long flags;

		raw_spin_lock_irqsave(&bucket->lock, flags);
		hlist_for_each_entry_safe(entry, next, &bucket->tasks, link)
			WARN_ON_ONCE(!kd_mutex_task_evict(bucket, entry));
		raw_spin_unlock_irqrestore(&bucket->lock, flags);
	}
	rcu_barrier();
}

void kd_mutex_tasks_exit(void)
{
	kd_mutex_tasks_purge();
	pr_info("kd_mutex tasks: active_tasks=%d task_alloc_failure=%lld task_reroutes=%lld\n",
		kd_mutex_task_count(),
		(long long)KD_MUTEX_STAT_READ(kd_mutex_task_failures),
		(long long)KD_MUTEX_STAT_READ(kd_mutex_task_reroutes));
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/mutex/mutex_task_selftest.c"
#endif
