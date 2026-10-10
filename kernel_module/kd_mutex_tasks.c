// SPDX-License-Identifier: GPL-2.0

/* RCU task membership preserves mutex ownership routing inside the hooks.
 * Acquisition references outlive comm changes and native borrowed suffixes.
 * Last put removes routing immediately; deferred freeing waits for readers. */
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
 * Reads neither sleep nor allocate. Writers serialize only the bucket for
 * this exact task; unrelated acquisitions do not share a global cacheline. */
struct kd_mutex_task {
	struct hlist_node link;
	struct rcu_head rcu;
	struct task_struct *task;
	unsigned int refs;
};

#define KD_MUTEX_TASK_BITS 8
#define KD_MUTEX_TASK_BUCKETS (1U << KD_MUTEX_TASK_BITS)

struct kd_mutex_task_bucket {
	raw_spinlock_t lock;
	struct hlist_head tasks;
	unsigned int count; /* exact membership, protected by this bucket's lock */
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

	for (i = 0; i < KD_MUTEX_TASK_BUCKETS; i++)
		count += READ_ONCE(kd_mutex_task_buckets[i].count);
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
			active = true;
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

bool kd_mutex_task_get(struct task_struct *task)
{
	struct kd_mutex_task_bucket *bucket = kd_mutex_task_bucket(task);
	struct kd_mutex_task *entry, *new;
	unsigned long flags;

	/* The test switch is normally zero. A read avoids taking exclusive
	 * ownership of its cacheline on every real acquisition; the CAS still
	 * allows exactly one injected failure when the switch is armed. */
	new = unlikely(READ_ONCE(kd_mutex_task_fail_once) == 1) &&
	      cmpxchg(&kd_mutex_task_fail_once, 1, 0) == 1 ?
		      NULL : kmalloc(sizeof(*new), GFP_ATOMIC);
	if (!new) {
		this_cpu_inc(kd_mutex_task_failures);
		return false;
	}
	raw_spin_lock_irqsave(&bucket->lock, flags);
	hlist_for_each_entry(entry, &bucket->tasks, link) {
		if (entry->task == task) {
			entry->refs++;
			raw_spin_unlock_irqrestore(&bucket->lock, flags);
			kfree(new);
			return true;
		}
	}
	get_task_struct(task);
	new->task = task;
	new->refs = 1;
	hlist_add_head_rcu(&new->link, &bucket->tasks);
	WRITE_ONCE(bucket->count, bucket->count + 1);
	raw_spin_unlock_irqrestore(&bucket->lock, flags);
	return true;
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

	raw_spin_lock_irqsave(&bucket->lock, flags);
	hlist_for_each_entry(entry, &bucket->tasks, link) {
		if (entry->task != task)
			continue;
		if (!--entry->refs) {
			hlist_del_rcu(&entry->link);
			WRITE_ONCE(bucket->count, bucket->count - 1);
			call_rcu(&entry->rcu, kd_mutex_task_free);
		}
		raw_spin_unlock_irqrestore(&bucket->lock, flags);
		return;
	}
	raw_spin_unlock_irqrestore(&bucket->lock, flags);
	WARN_ON_ONCE(1);
}

bool kd_mutex_tasks_idle(void)
{
	/* Snapshot guard, not a barrier against arbitrary new native callers. */
	return !kd_mutex_task_count();
}

void kd_mutex_tasks_exit(void)
{
	/* Controlled teardown only: all hook callers and acquisitions must have
	 * finished before unregistering. This is not concurrent hot-unload support. */
	unsigned int i;

	for (i = 0; i < KD_MUTEX_TASK_BUCKETS; i++)
		WARN_ON_ONCE(!hlist_empty(&kd_mutex_task_buckets[i].tasks));
	rcu_barrier();
	pr_info("kd_mutex tasks: active_tasks=%d task_alloc_failure=%lld task_reroutes=%lld\n",
		kd_mutex_task_count(),
		(long long)KD_MUTEX_STAT_READ(kd_mutex_task_failures),
		(long long)KD_MUTEX_STAT_READ(kd_mutex_task_reroutes));
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/mutex/mutex_task_selftest.c"
#endif
