// SPDX-License-Identifier: GPL-2.0
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/uaccess.h>
#include "probe.h"
#include "kd_mmap_rwsem.h"

struct result {
	u64 checks, errors, contexts, concurrent, writers, cancellations;
	u64 rollbacks, injections, atomic_wakes, idle;
};
static struct kd_mmap_lock locks[2];
static DEFINE_MUTEX(control);
static struct result result;
static atomic_t wakes = ATOMIC_INIT(0), atomic_wakes = ATOMIC_INIT(0);
static unsigned long payload;

static void check(bool ok)
{
	result.checks++;
	if (!ok)
		result.errors++;
}

static bool idle(struct kd_mmap_lock *lock)
{
	return lock->use_kd ? kd_mmap_rwsem_is_idle(&lock->kd) :
		!rwsem_is_locked(&lock->native) && !rwsem_is_contended(&lock->native);
}

static void context_enter(unsigned int context, unsigned long *flags)
{
	if (context == 1)
		local_irq_save(*flags);
	else if (context == 2)
		preempt_disable();
}

static void context_leave(unsigned int context, unsigned long flags)
{
	if (context == 1)
		local_irq_restore(flags);
	else if (context == 2)
		preempt_enable();
}

/* Measure state inside the tested context. Native release follows its existing
 * caller contract (restore first); KD additionally supports atomic release. */
static bool try_read(struct kd_mmap_lock *lock, unsigned int context, bool release)
{
	unsigned long flags = 0;
	int count;
	bool irq, acquired;

	context_enter(context, &flags);
	irq = irqs_disabled();
	count = preempt_count();
	acquired = kd_mmap_read_trylock(lock);
	check(irqs_disabled() == irq && preempt_count() == count);
	if (acquired && release && lock->use_kd) {
		kd_mmap_read_unlock(lock);
		check(irqs_disabled() == irq && preempt_count() == count);
	}
	context_leave(context, flags);
	if (acquired && release && !lock->use_kd)
		kd_mmap_read_unlock(lock);
	check(!irqs_disabled() && preempt_count() == 0);
	return acquired;
}

static void release_read(struct kd_mmap_lock *lock, unsigned int context)
{
	unsigned long flags = 0;
	int count;
	bool irq;

	if (!lock->use_kd)
		context = 0;
	context_enter(context, &flags);
	irq = irqs_disabled();
	count = preempt_count();
	kd_mmap_read_unlock(lock);
	check(irqs_disabled() == irq && preempt_count() == count);
	context_leave(context, flags);
}

struct worker {
	struct kd_mmap_lock *lock;
	struct task_struct *task;
	struct completion entered, release, done;
	unsigned int mode;
	int ret;
	unsigned long observed;
};

static int worker_fn(void *arg)
{
	struct worker *w = arg;

	allow_signal(SIGUSR1);
	allow_signal(SIGKILL);
	if (w->mode == 0) {
		kd_mmap_read_lock(w->lock);
		w->ret = 0;
	} else if (w->mode == 2) {
		/* This additional shared KD API has no Native counterpart in 6.1. */
		w->ret = kd_mmap_down_write_interruptible(&w->lock->kd);
	} else if (w->mode == 3) {
		w->ret = kd_mmap_write_lock_killable(w->lock);
	} else {
		kd_mmap_write_lock(w->lock);
		w->ret = 0;
	}
	if (!w->ret) {
		w->observed = READ_ONCE(payload);
		complete(&w->entered);
		wait_for_completion(&w->release);
		if (w->mode)
			kd_mmap_write_unlock(w->lock);
		else
			kd_mmap_read_unlock(w->lock);
	}
	complete_all(&w->done);
	return 0;
}

static bool start(struct worker *w, struct kd_mmap_lock *lock, unsigned int mode)
{
	w->lock = lock;
	w->mode = mode;
	w->ret = -EINPROGRESS;
	init_completion(&w->entered);
	init_completion(&w->release);
	init_completion(&w->done);
	w->task = kthread_create(worker_fn, w, "kd-irq-probe");
	check(!IS_ERR(w->task));
	if (IS_ERR(w->task))
		return false;
	get_task_struct(w->task);
	wake_up_process(w->task);
	return true;
}

static void joined(struct worker *w)
{
	complete(&w->release);
	if (!wait_for_completion_timeout(&w->done, 5 * HZ)) {
		check(false);
		/* Failure is not drain: retain this ioctl/module until its user exits. */
		wait_for_completion(&w->done);
	}
	kthread_stop(w->task);
	put_task_struct(w->task);
}

static bool entered(struct worker *w)
{
	bool ok = wait_for_completion_timeout(&w->entered, 5 * HZ) != 0;

	check(ok);
	return ok;
}

static bool draining(struct worker *w)
{
	unsigned long end = jiffies + 5 * HZ;
	bool queued;

	do {
		queued = w->lock->use_kd ? waitqueue_active(&w->lock->kd.reader_drain) :
			rwsem_is_contended(&w->lock->native);
		if (queued && READ_ONCE(w->task->__state) != TASK_RUNNING) {
			check(!completion_done(&w->entered));
			return true;
		}
		msleep(1);
	} while (time_before(jiffies, end));
	check(false);
	return false;
}

static int observe_wake(wait_queue_entry_t *entry, unsigned int mode, int flags, void *key)
{
	atomic_inc(&wakes);
	/* wake_up takes an IRQ-safe queue lock itself. The state at this callback
	 * is atomic even on the safe task path; caller context is tested through
	 * the zero-callback assertion around each atomic release. */
	return 0;
}

static void matrix(struct kd_mmap_lock *lock)
{
	unsigned int c;
	struct worker reader;

	for (c = 0; c < 3; c++) {
		check(try_read(lock, c, true));
		check(idle(lock));
		kd_mmap_write_lock(lock);
		check(!try_read(lock, c, true));
		check(kd_mmap_is_write_owner(lock));
		kd_mmap_write_unlock(lock);
		check(idle(lock));
		result.contexts++;
	}
	if (!start(&reader, lock, 0))
		return;
	if (entered(&reader)) {
		for (c = 0; c < 3; c++) {
			bool acquired = try_read(lock, c, false);

			check(acquired);
			check(!kd_mmap_write_trylock(lock));
			if (acquired)
				release_read(lock, c);
			check(kd_mmap_is_locked(lock));
			result.concurrent++;
		}
	}
	joined(&reader);
	check(idle(lock));
}

static void writer_cases(struct kd_mmap_lock *lock)
{
	unsigned int c, mode;

	for (mode = 1; mode <= 3; mode++) {
		if (mode == 2 && !lock->use_kd)
			continue;
		for (c = 0; c < 3; c++) {
			struct worker writer;
			DEFINE_WAIT_FUNC(observer, observe_wake);
			int before;

			kd_mmap_read_lock(lock);
			if (!start(&writer, lock, mode)) {
				kd_mmap_read_unlock(lock);
				return;
			}
			if (draining(&writer)) {
				check(!try_read(lock, c, true));
				check(!completion_done(&writer.entered));
			}
			if (lock->use_kd)
				add_wait_queue(&lock->kd.reader_drain, &observer);
			before = atomic_read(&wakes);
			WRITE_ONCE(payload, 100 + mode * 3 + c);
			release_read(lock, c);
			if (lock->use_kd) {
				int delta = atomic_read(&wakes) - before;

				check(c ? !delta : delta == 1);
				if (c)
					atomic_add(delta, &atomic_wakes);
				remove_wait_queue(&lock->kd.reader_drain, &observer);
			}
			if (entered(&writer)) {
				check(!writer.ret && writer.observed == 100 + mode * 3 + c);
				check(!try_read(lock, c, true));
			}
			joined(&writer);
			check(idle(lock));
			result.writers++;
		}
	}
	for (mode = 2; mode <= 3; mode++) {
		struct worker writer;

		if (mode == 2 && !lock->use_kd)
			continue;
		kd_mmap_read_lock(lock);
		if (!start(&writer, lock, mode)) {
			kd_mmap_read_unlock(lock);
			return;
		}
		if (draining(&writer)) {
			if (mode == 3) {
				check(!send_sig(SIGUSR1, writer.task, 1));
				msleep(20);
				check(!completion_done(&writer.done));
			}
			check(!send_sig(mode == 2 ? SIGUSR1 : SIGKILL, writer.task, 1));
			check(wait_for_completion_timeout(&writer.done, 5 * HZ) != 0);
			check(writer.ret == -EINTR && !completion_done(&writer.entered));
		}
		kd_mmap_read_unlock(lock);
		joined(&writer);
		check(idle(lock));
		result.cancellations++;
	}
}

static void rollback_cases(void)
{
	struct kd_mmap_lock *lock = &locks[1];
	unsigned int c;

	for (c = 0; c < 3; c++) {
		DEFINE_WAIT_FUNC(observer, observe_wake);
		int before = atomic_read(&wakes), delta;

		add_wait_queue(&lock->kd.reader_drain, &observer);
		WRITE_ONCE(kd_irq_inject, &lock->kd);
		check(!try_read(lock, c, true));
		WRITE_ONCE(kd_irq_inject, NULL);
		check(atomic_long_read(&lock->kd.readers) == 0);
		check(atomic_long_read(&lock->kd.admission) == -1);
		delta = atomic_read(&wakes) - before;
		check(c ? !delta : delta == 1);
		if (c)
			atomic_add(delta, &atomic_wakes);
		/* Retire this synthetic reservation, never an acquired writer. */
		check(atomic_long_xchg(&lock->kd.admission, 0) == -1);
		remove_wait_queue(&lock->kd.reader_drain, &observer);
		check(idle(lock));
		result.rollbacks++;
	}
}

static long probe_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	int mode, ret = 0;

	if (cmd != _IOR('I', 1, struct result))
		return -ENOTTY;
	if (!mutex_trylock(&control))
		return -EBUSY;
	memset(&result, 0, sizeof(result));
	for (mode = 0; mode < 2; mode++) {
		check(idle(&locks[mode]));
		matrix(&locks[mode]);
		writer_cases(&locks[mode]);
	}
	rollback_cases();
	result.injections = kd_irq_injections;
	result.atomic_wakes = atomic_read(&atomic_wakes);
	result.idle = idle(&locks[0]) && idle(&locks[1]) && !kd_irq_inject;
	check(result.idle);
	if (copy_to_user((void __user *)arg, &result, sizeof(result)))
		ret = -EFAULT;
	mutex_unlock(&control);
	return ret;
}

static const struct file_operations ops = {
	.owner = THIS_MODULE, .unlocked_ioctl = probe_ioctl, .llseek = no_llseek,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mmap_irq_probe", .fops = &ops, .mode = 0600,
};
static int __init probe_init(void)
{
	int ret = kd_mmap_mutex_local_runtime_init();

	if (ret)
		return ret;
	kd_irq_init_lock(&locks[0], false);
	kd_irq_init_lock(&locks[1], true);
	ret = misc_register(&device);
	if (ret)
		kd_mmap_mutex_local_runtime_exit();
	return ret;
}
static void __exit probe_exit(void)
{
	BUG_ON(!idle(&locks[0]) || !idle(&locks[1]) || kd_irq_inject);
	kd_mmap_destroy(&locks[0]);
	kd_mmap_destroy(&locks[1]);
	misc_deregister(&device);
	kd_mmap_mutex_local_runtime_exit();
}
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Native/KD read trylock IRQ state, rollback and reader drain regression");
