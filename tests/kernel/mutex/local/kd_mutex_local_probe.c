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

static bool no_delegation(struct mutex *lock)
{
	return !atomic_read(&lock->delegation_state) &&
		!READ_ONCE(lock->delegation_tail);
}

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
		queued = test_lock.wait_head != NULL;
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

struct ring_waiter {
	struct completion ready;
	struct completion done;
	struct task_struct *task;
	int result;
	unsigned int order;
};

static unsigned int ring_order;

static int ring_worker(void *arg)
{
	struct ring_waiter *waiter = arg;

	allow_signal(SIGUSR1);
	complete(&waiter->ready);
	waiter->result = mutex_lock_interruptible(&test_lock);
	if (!waiter->result) {
		if (atomic_inc_return(&active) != 1)
			atomic_inc(&errors);
		waiter->order = ++ring_order;
		/* The next waiter must survive an owner that sleeps after pickup. */
		usleep_range(100, 200);
		if (atomic_dec_return(&active))
			atomic_inc(&errors);
		mutex_unlock(&test_lock);
	}
	/* Cancellation checks and final joining both observe this completion. */
	complete_all(&waiter->done);
	return 0;
}

/* The parent holds the mutex and this worker has passed its ready marker.
 * This exact task's interruptible state is set only after queue insertion;
 * wait_lock excludes observing an insertion before its state publication. */
static bool ring_wait_until_queued(struct task_struct *task)
{
	unsigned int tries;

	for (tries = 0; tries < 1000; tries++) {
		bool queued;

		raw_spin_lock(&test_lock.wait_lock);
		queued = test_lock.wait_head &&
			READ_ONCE(task->__state) == TASK_INTERRUPTIBLE;
		raw_spin_unlock(&test_lock.wait_lock);
		if (queued)
			return true;
		usleep_range(100, 200);
	}
	return false;
}

static int ring_cancellation(unsigned int victim)
{
	struct ring_waiter waiters[3];
	struct kd_local_waiter *first;
	unsigned int i, tries, expected = 0, started = 0;
	bool handoff = false;
	int ret = 0;

	ring_order = 0;
	mutex_lock(&test_lock);
	for (i = 0; i < ARRAY_SIZE(waiters); i++) {
		init_completion(&waiters[i].ready);
		init_completion(&waiters[i].done);
		waiters[i].result = -EINPROGRESS;
		waiters[i].order = 0;
		waiters[i].task = kthread_run(ring_worker, &waiters[i],
					     "kd-local/ring-%u", i);
		if (IS_ERR(waiters[i].task)) {
			ret = PTR_ERR(waiters[i].task);
			goto release;
		}
		get_task_struct(waiters[i].task);
		started++;
		wait_for_completion(&waiters[i].ready);
		if (!ring_wait_until_queued(waiters[i].task)) {
			ret = -ETIMEDOUT;
			goto release;
		}
	}
	/* Ordered insertion creates known head/middle/tail positions. Wake the
	 * head while the parent still owns the mutex: its retry must request the
	 * existing physical HANDOFF bit (2), before cancellation changes the ring. */
	first = READ_ONCE(test_lock.wait_head);
	wake_up_process(waiters[0].task);
	for (tries = 0; tries < 1000; tries++) {
		handoff = atomic_long_read(&test_lock.owner) & 2UL;
		if (handoff)
			break;
		usleep_range(100, 200);
	}
	if (!handoff) {
		ret = -ETIMEDOUT;
		goto release;
	}
	send_sig(SIGUSR1, waiters[victim].task, 1);
	wait_for_completion(&waiters[victim].done);
	raw_spin_lock(&test_lock.wait_lock);
	if (waiters[victim].result != -EINTR || waiters[victim].order ||
	    !test_lock.wait_head ||
	    ((test_lock.wait_head == first) != (victim != 0)) ||
	    !(atomic_long_read(&test_lock.owner) & 2UL))
		ret = -EINVAL;
	raw_spin_unlock(&test_lock.wait_lock);
release:
	/* Always release the parent before joining. Never return while a worker
	 * can still reference its stack argument; a broken drain stays observable
	 * to the runner's timeout instead of freeing live waiter storage. */
	mutex_unlock(&test_lock);
	for (i = 0; i < started; i++) {
		wait_for_completion(&waiters[i].done);
		kthread_stop(waiters[i].task);
		put_task_struct(waiters[i].task);
	}
	if (!ret) {
		for (i = 0; i < started; i++) {
			if (i == victim)
				continue;
			if (waiters[i].result || waiters[i].order != ++expected)
				ret = -EINVAL;
		}
		if (ring_order != 2 || !kd_mutex_is_idle(&test_lock) ||
		    !no_delegation(&test_lock) || atomic_read(&errors))
			ret = -EINVAL;
	}
	return ret;
}

/* Compile and execute the captured kernel's real cleanup macros. Constructors
 * must acquire KD objects through the conventional ABI and destructors must
 * return through the shared router, including direct CLASS/__free token paste. */
static int api_helpers(void)
{
	void (*lock_fn)(struct mutex *) = &mutex_lock;
	void (*unlock_fn)(struct mutex *) = &mutex_unlock;
	unsigned int annotations = 0;

	__mutex_init(&nested, "kd-api", NULL);
	if (devm_mutex_init(NULL, &nested) ||
	    __devm_mutex_init(NULL, &nested))
		return -EINVAL;
	lock_fn(&nested);
	mutex_unlock(&nested);
	mutex_lock(&nested);
	unlock_fn(&nested);
	(mutex_lock)(&nested);
	(mutex_unlock)(&nested);
	{
		guard(mutex)(&nested);
		if (!mutex_is_locked(&nested))
			return -EINVAL;
	}
	if (!kd_mutex_is_idle(&nested))
		return -EINVAL;
	{
		CLASS(mutex, held)(&nested);
		if (!held || !mutex_is_locked(&nested))
			return -EINVAL;
	}
	if (!kd_mutex_is_idle(&nested))
		return -EINVAL;
	scoped_guard(mutex, &nested) {
		if (!mutex_is_locked(&nested))
			return -EINVAL;
	}
	if (!kd_mutex_is_idle(&nested))
		return -EINVAL;
	{
		struct mutex *held __free(mutex) = &nested;

		mutex_lock(held);
	}
	if (!kd_mutex_is_idle(&nested))
		return -EINVAL;
	mutex_lock_nested(&test_lock, ++annotations);
	mutex_lock_nest_lock(&nested, ++annotations);
	/* Release the earlier acquisition first: records must identify the lock,
	 * not assume a caller-side stack of cookies. */
	mutex_unlock(&test_lock);
	mutex_unlock(&nested);
	if (mutex_lock_interruptible_nested(&nested, ++annotations))
		return -EINVAL;
	mutex_unlock(&nested);
	if (mutex_lock_killable_nested(&nested, ++annotations))
		return -EINVAL;
	mutex_unlock(&nested);
	mutex_lock_io_nested(&nested, ++annotations);
	mutex_unlock(&nested);
	mutex_destroy(&nested);
	return !annotations && kd_mutex_is_idle(&nested) &&
		kd_mutex_is_idle(&test_lock) ? 0 : -EINVAL;
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

	/* This probe is outside the selected delegation comm. Unified calls still
	 * take the production DIRECT entry, then use local physical exclusion. */
	if (api_helpers() || !no_delegation(&test_lock))
		return -EINVAL;
	if (!mutex_trylock(&test_lock) || !mutex_is_locked(&test_lock) ||
	    !no_delegation(&test_lock) || mutex_trylock(&test_lock))
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
			if (!no_delegation(&many[i]))
				ret = -EINVAL;
			mutex_unlock(&many[i]);
			if (!kd_mutex_is_idle(&many[i]))
				ret = -EINVAL;
		}
	}
	kfree(many);
	if (ret || cancellation(SIGUSR1) || cancellation(SIGKILL))
		return -EINVAL;
	for (i = 0; i < 3; i++)
		if (ring_cancellation(i))
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
	    !no_delegation(&test_lock) || !no_delegation(&nested))
		return -EINVAL;
	pr_info("KD_LOCAL_PROBE PASS operations=%lu workers=8 objects=2048 lock_size=%zu lock_align=%zu containing_layout=PASS address_reuse=PASS no_destroy=PASS no_aux=PASS interruptible=EINTR killable=EINTR ring_cancel=PASS ring_handoff=PASS nested_sleep=PASS io=PASS api_helpers=PASS drain=PASS\n",
		operations, sizeof(struct mutex), (size_t)__alignof__(struct mutex));
	return 0;
}
static void __exit probe_exit(void) { }
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
