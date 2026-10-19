// SPDX-License-Identifier: GPL-2.0
/* Native layout, ordinary API semantics, sleeping owners and cancellation.
 * The compatibility header is deliberately included after all Linux headers.
 */
#include <linux/module.h>
#include <linux/kthread.h>
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/sched/signal.h>
#include <linux/slab.h>
#include <linux/mutex.h>

/* Preserve the native type before the compatibility header aliases its tag. */
typedef struct mutex kd_native_mutex_layout;

#include "kd_mutex_compat.h"

struct native_container {
	u8 prefix;
	kd_native_mutex_layout lock;
	u8 suffix;
};

struct kd_container {
	u8 prefix;
	struct mutex lock;
	u8 suffix;
};

static DEFINE_MUTEX(test_lock);
static DEFINE_MUTEX(nested);
static atomic_t active = ATOMIC_INIT(0), errors = ATOMIC_INIT(0);
static unsigned long operations;
static struct completion done[8];
static DECLARE_COMPLETION(ready);
static DECLARE_COMPLETION(cancelled);
static int cancel_result, cancel_signal;

static int worker(void *arg)
{
	unsigned long id = (unsigned long)arg;
	unsigned int i;

	for (i = 0; i < 20000; i++) {
		mutex_lock(&test_lock);
		if (atomic_inc_return(&active) != 1)
			atomic_inc(&errors);
		operations++;
		if (!(i % 1000)) {
			mutex_lock_nested(&nested, 1);
			usleep_range(100, 200);
			mutex_unlock(&nested);
		}
		if (atomic_dec_return(&active))
			atomic_inc(&errors);
		mutex_unlock(&test_lock);
		cond_resched();
	}
	complete(&done[id]);
	return 0;
}

static int cancel_worker(void *unused)
{
	allow_signal(cancel_signal);
	complete(&ready);
	cancel_result = cancel_signal == SIGKILL ?
		mutex_lock_killable(&test_lock) : mutex_lock_interruptible(&test_lock);
	if (!cancel_result)
		mutex_unlock(&test_lock);
	complete(&cancelled);
	return 0;
}

static int cancellation(int sig)
{
	struct task_struct *task;
	int tries = 1000;
	bool queued;

	reinit_completion(&ready);
	reinit_completion(&cancelled);
	cancel_signal = sig;
	mutex_lock(&test_lock);
	task = kthread_run(cancel_worker, NULL, "kd-cancel");
	if (IS_ERR(task)) {
		mutex_unlock(&test_lock);
		return PTR_ERR(task);
	}
	get_task_struct(task);
	wait_for_completion(&ready);
	do {
		raw_spin_lock(&test_lock.wait_lock);
		queued = !list_empty(&test_lock.wait_list);
		raw_spin_unlock(&test_lock.wait_lock);
		if (!queued)
			usleep_range(100, 200);
	} while (!queued && --tries);
	send_sig(sig, task, 1);
	wait_for_completion(&cancelled);
	kthread_stop(task);
	put_task_struct(task);
	mutex_unlock(&test_lock);
	return queued && cancel_result == -EINTR && kd_mutex_is_idle(&test_lock) ? 0 : -EINVAL;
}

static int __init probe_init(void)
{
	struct task_struct *tasks[8];
	struct mutex *many;
	atomic_t ref = ATOMIC_INIT(2);
	int i, pass, started = 0, ret = 0, old_io = current->in_iowait;

	BUILD_BUG_ON(sizeof(struct mutex) != 32);
	BUILD_BUG_ON(__alignof__(struct mutex) != 8);
	BUILD_BUG_ON(sizeof(struct mutex) != sizeof(kd_native_mutex_layout));
	BUILD_BUG_ON(__alignof__(struct mutex) !=
		     __alignof__(kd_native_mutex_layout));
	BUILD_BUG_ON(offsetof(struct kd_container, lock) !=
		     offsetof(struct native_container, lock));
	BUILD_BUG_ON(offsetof(struct kd_container, suffix) !=
		     offsetof(struct native_container, suffix));
	BUILD_BUG_ON(sizeof(struct kd_container) != sizeof(struct native_container));

	/* This controlled probe has no delegation callers. Exact registry
	 * membership must remain empty even while ordinary owners are live. */
	if (kd_mutex_debug_aux_count())
		return -EINVAL;
	if (!mutex_trylock(&test_lock) || !mutex_is_locked(&test_lock) ||
	    kd_mutex_debug_aux_count() || mutex_trylock(&test_lock))
		return -EINVAL;
	mutex_unlock(&test_lock);
	mutex_lock_io(&test_lock);
	if (current->in_iowait != old_io)
		ret = -EINVAL;
	mutex_unlock(&test_lock);
	if (atomic_dec_and_mutex_lock(&ref, &test_lock) ||
	    !atomic_dec_and_mutex_lock(&ref, &test_lock))
		return -EINVAL;
	mutex_unlock(&test_lock);
	many = kcalloc(2048, sizeof(*many), GFP_KERNEL);
	if (!many)
		return -ENOMEM;
	/* Reuse every exact address after drain, then release caller storage
	 * without destroy. Ordinary Linux callers have no extra cleanup duty.
	 */
	for (pass = 0; pass < 2; pass++) {
		for (i = 0; i < 2048; i++) {
			mutex_init(&many[i]);
			mutex_lock(&many[i]);
			if (kd_mutex_debug_aux_count())
				ret = -EINVAL;
			mutex_unlock(&many[i]);
			if (!kd_mutex_is_idle(&many[i]))
				ret = -EINVAL;
		}
	}
	kfree(many);
	if (ret || cancellation(SIGUSR1) || cancellation(SIGKILL))
		return -EINVAL;
	for (i = 0; i < 8; i++) {
		init_completion(&done[i]);
		tasks[i] = kthread_create(worker, (void *)(unsigned long)i, "kd-local/%d", i);
		if (IS_ERR(tasks[i])) {
			ret = PTR_ERR(tasks[i]);
			break;
		}
		kthread_bind(tasks[i], i);
		get_task_struct(tasks[i]);
		wake_up_process(tasks[i]);
		started++;
	}
	for (i = 0; i < started; i++) {
		wait_for_completion(&done[i]);
		kthread_stop(tasks[i]);
		put_task_struct(tasks[i]);
	}
	if (ret || operations != 160000 || atomic_read(&errors) ||
	    !kd_mutex_is_idle(&test_lock) || !kd_mutex_is_idle(&nested) ||
	    kd_mutex_debug_aux_count())
		return -EINVAL;
	pr_info("KD_LOCAL_PROBE PASS operations=%lu workers=8 objects=2048 lock_size=%zu lock_align=%zu containing_layout=PASS address_reuse=PASS no_destroy=PASS no_aux=PASS interruptible=EINTR killable=EINTR nested_sleep=PASS io=PASS drain=PASS\n",
		operations, sizeof(struct mutex), (size_t)__alignof__(struct mutex));
	return 0;
}
static void __exit probe_exit(void) { }
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
