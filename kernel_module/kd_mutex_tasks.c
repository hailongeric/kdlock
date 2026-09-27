// SPDX-License-Identifier: GPL-2.0
/* Bounded stable task identities for exact mutex acquisition routing. Cached
 * keys retain task references until unload; refs==0 never grants routing. */
#include <linux/atomic.h>
#include <linux/hash.h>
#include <linux/moduleparam.h>
#include <linux/sched/task.h>
#include <linux/cache.h>

#include "kd_lock.h"

#define KD_MUTEX_TASK_BITS 10
#define KD_MUTEX_TASK_CAPACITY (1U << KD_MUTEX_TASK_BITS)
struct kd_mutex_task {
	struct task_struct *task;
	atomic_t refs;
} ____cacheline_aligned;

/* Zero initialization precedes module publication. An entry never moves or
 * gets recycled, so readers need neither RCU nor a global registry lock. */
static struct kd_mutex_task kd_mutex_tasks[KD_MUTEX_TASK_CAPACITY];
static atomic64_t kd_mutex_task_failures = ATOMIC64_INIT(0);
static atomic64_t kd_mutex_task_reroutes = ATOMIC64_INIT(0);
static int kd_mutex_task_fail_once;
module_param_named(mutex_task_fail_once, kd_mutex_task_fail_once, int, 0644);

static struct kd_mutex_task *kd_mutex_task_find(struct task_struct *task)
{
	unsigned int pos = hash_long((unsigned long)task, KD_MUTEX_TASK_BITS), n;

	for (n = 0; n < KD_MUTEX_TASK_CAPACITY; n++) {
		struct kd_mutex_task *entry = &kd_mutex_tasks[pos];
		struct task_struct *seen = smp_load_acquire(&entry->task);

		if (seen == task)
			return entry;
		if (!seen)
			return NULL;
		pos = (pos + 1) & (KD_MUTEX_TASK_CAPACITY - 1);
	}
	return NULL;
}

bool kd_mutex_task_active(struct task_struct *task)
{
	struct kd_mutex_task *entry = kd_mutex_task_find(task);

	return entry && atomic_read(&entry->refs) > 0;
}

bool kd_mutex_task_reroute(struct task_struct *task)
{
	if (!kd_mutex_task_active(task))
		return false;
	atomic64_inc(&kd_mutex_task_reroutes);
	return true;
}

bool kd_mutex_task_get(struct task_struct *task)
{
	unsigned int pos = hash_long((unsigned long)task, KD_MUTEX_TASK_BITS), n;

	if (unlikely(READ_ONCE(kd_mutex_task_fail_once) == 1 &&
		     cmpxchg(&kd_mutex_task_fail_once, 1, 0) == 1))
		goto fail;
	for (n = 0; n < KD_MUTEX_TASK_CAPACITY; n++) {
		struct kd_mutex_task *entry = &kd_mutex_tasks[pos];
		struct task_struct *seen = smp_load_acquire(&entry->task);

		if (!seen) {
			/* Publish only after taking the lifetime reference. A loser
			 * drops its extra reference; it never resets a winner's refs. */
			get_task_struct(task);
			seen = cmpxchg(&entry->task, NULL, task);
			if (seen)
				put_task_struct(task);
		}
		if (!seen || seen == task) {
			/* This exact acquisition reference remains through queue wait,
			 * native continuation and the final owner ACK. Publication of
			 * the request happens only after get() has returned success. */
			atomic_inc(&entry->refs);
			return true;
		}
		pos = (pos + 1) & (KD_MUTEX_TASK_CAPACITY - 1);
	}
fail:
	atomic64_inc(&kd_mutex_task_failures);
	return false;
}

void kd_mutex_task_put(struct task_struct *task)
{
	struct kd_mutex_task *entry = kd_mutex_task_find(task);

	BUG_ON(!entry || atomic_dec_return(&entry->refs) < 0);
	/* A final put makes the cache entry inactive before the owner publishes
	 * its last ACK. The key/task lifetime survives for the next acquisition. */
}

static unsigned int kd_mutex_tasks_active_count(void)
{
	unsigned int n, active = 0;

	for (n = 0; n < KD_MUTEX_TASK_CAPACITY; n++)
		active += atomic_read(&kd_mutex_tasks[n].refs) != 0;
	return active;
}

static unsigned int kd_mutex_tasks_retained_count(void)
{
	unsigned int n, retained = 0;

	for (n = 0; n < KD_MUTEX_TASK_CAPACITY; n++)
		retained += !!smp_load_acquire(&kd_mutex_tasks[n].task);
	return retained;
}

bool kd_mutex_tasks_idle(void)
{
	/* Exact after all callers stop; this scan is not concurrent hot-unload
	 * admission. Never substitute the cached-key count for active ownership. */
	return !kd_mutex_tasks_active_count();
}

void kd_mutex_tasks_exit(void)
{
	unsigned int n, retained = kd_mutex_tasks_retained_count();

	/* Source/workload pins and the controlled drain precede module teardown.
	 * Only here may a stable key release its task's lifetime reference. */
	BUG_ON(!kd_mutex_tasks_idle());
	for (n = 0; n < KD_MUTEX_TASK_CAPACITY; n++) {
		struct task_struct *task = READ_ONCE(kd_mutex_tasks[n].task);

		if (task)
			put_task_struct(task);
	}
	pr_info("kd_mutex tasks: active_tasks=0 retained_tasks=%u released_tasks=%u task_alloc_failure=%lld task_reroutes=%lld\n",
		retained, retained, (long long)atomic64_read(&kd_mutex_task_failures),
		(long long)atomic64_read(&kd_mutex_task_reroutes));
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/mutex/mutex_task_selftest.c"
#endif
