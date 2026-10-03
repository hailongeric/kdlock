// SPDX-License-Identifier: GPL-2.0

/* RCU task membership preserves mutex ownership routing inside the hooks.
 * Acquisition references outlive comm changes and native borrowed suffixes.
 * Last put removes routing immediately; deferred freeing waits for readers. */
#include <linux/cache.h>
#include <linux/hashtable.h>
#include <linux/moduleparam.h>
#include <linux/rcupdate.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/spinlock.h>

#include "kd_lock.h"
#include "kd_mutex_stats.h"

/* Keep task routing alive through queue waits, the owner's CS, and borrowed
 * native CSs, independently of CPU frequency or target-process selection.
 * Reads neither sleep nor allocate; writers serialize membership and refs. */
struct kd_mutex_task {
	struct hlist_node link;
	struct rcu_head rcu;
	struct task_struct *task;
	unsigned int refs;
};

static DEFINE_HASHTABLE(kd_mutex_tasks, 8);
/* Serialize exactly one hash chain and its reference updates, rather than all
 * task identities. Colliding tasks still share the same lock. Cacheline-sized
 * lock records keep independent buckets from bouncing the same lock line. */
struct kd_mutex_task_lock_bucket {
	raw_spinlock_t lock;
} ____cacheline_aligned;

/* Static initialization precedes every direct API and pre-hook SELFTEST call.
 * No acquisition allocates a lock or changes the bucket array's lifetime. */
static struct kd_mutex_task_lock_bucket
kd_mutex_task_locks[HASH_SIZE(kd_mutex_tasks)] = {
	[0 ... HASH_SIZE(kd_mutex_tasks) - 1] = {
		.lock = __RAW_SPIN_LOCK_UNLOCKED(kd_mutex_task_locks),
	},
};

static __always_inline raw_spinlock_t *
kd_mutex_task_bucket_lock(struct task_struct *task)
{
	/* Match hash_add_rcu/hash_for_each_possible exactly, including their
	 * native-word key width. A different hash would not protect the chain. */
	return &kd_mutex_task_locks[
		hash_min((unsigned long)task, HASH_BITS(kd_mutex_tasks))].lock;
}
static atomic_t kd_mutex_task_count = ATOMIC_INIT(0);
KD_MUTEX_STAT(kd_mutex_task_failures);
KD_MUTEX_STAT(kd_mutex_task_reroutes);
static int kd_mutex_task_fail_once;
module_param_named(mutex_task_fail_once, kd_mutex_task_fail_once, int, 0644);

#ifdef KDLOCK_SELFTEST
/* Observe the real deferred free without replacing RCU or task references.
 * Hooks are unpublished during the probe, so only its records contribute. */
static atomic_t kd_mutex_task_test_frees = ATOMIC_INIT(0);
#endif

bool kd_mutex_task_active(struct task_struct *task)
{
	struct kd_mutex_task *entry;
	bool active = false;

	rcu_read_lock();
	hash_for_each_possible_rcu(kd_mutex_tasks, entry, link,
				   (unsigned long)task) {
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
	struct kd_mutex_task *entry, *new;
	raw_spinlock_t *bucket_lock = kd_mutex_task_bucket_lock(task);
	unsigned long flags;

	new = cmpxchg(&kd_mutex_task_fail_once, 1, 0) == 1 ?
		      NULL : kmalloc(sizeof(*new), GFP_ATOMIC);
	if (!new) {
		this_cpu_inc(kd_mutex_task_failures);
		return false;
	}
	raw_spin_lock_irqsave(bucket_lock, flags);
	hash_for_each_possible(kd_mutex_tasks, entry, link, (unsigned long)task) {
		if (entry->task == task) {
			entry->refs++;
			raw_spin_unlock_irqrestore(bucket_lock, flags);
			kfree(new);
			return true;
		}
	}
	get_task_struct(task);
	new->task = task;
	new->refs = 1;
	hash_add_rcu(kd_mutex_tasks, &new->link, (unsigned long)task);
	atomic_inc(&kd_mutex_task_count);
	raw_spin_unlock_irqrestore(bucket_lock, flags);
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
	struct kd_mutex_task *entry;
	raw_spinlock_t *bucket_lock = kd_mutex_task_bucket_lock(task);
	unsigned long flags;

	raw_spin_lock_irqsave(bucket_lock, flags);
	hash_for_each_possible(kd_mutex_tasks, entry, link, (unsigned long)task) {
		if (entry->task != task)
			continue;
		if (!--entry->refs) {
			hash_del_rcu(&entry->link);
			atomic_dec(&kd_mutex_task_count);
			call_rcu(&entry->rcu, kd_mutex_task_free);
		}
		raw_spin_unlock_irqrestore(bucket_lock, flags);
		return;
	}
	raw_spin_unlock_irqrestore(bucket_lock, flags);
	WARN_ON_ONCE(1);
}

bool kd_mutex_tasks_idle(void)
{
	/* Snapshot guard, not a barrier against arbitrary new native callers. */
	return !atomic_read(&kd_mutex_task_count);
}

void kd_mutex_tasks_exit(void)
{
	/* Controlled teardown only: all hook callers and acquisitions must have
	 * finished before unregistering. This is not concurrent hot-unload support. */
	WARN_ON_ONCE(!hash_empty(kd_mutex_tasks));
	rcu_barrier();
	pr_info("kd_mutex tasks: active_tasks=%d task_alloc_failure=%lld task_reroutes=%lld\n",
		atomic_read(&kd_mutex_task_count),
		(long long)KD_MUTEX_STAT_READ(kd_mutex_task_failures),
		(long long)KD_MUTEX_STAT_READ(kd_mutex_task_reroutes));
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/mutex/mutex_task_selftest.c"
#endif
