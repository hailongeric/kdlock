// SPDX-License-Identifier: GPL-2.0
/* Test-only held writer; no production hooks or lock ownership transfer. */
#include <linux/completion.h>
#include <linux/fs.h>
#include <linux/kthread.h>
#include <linux/jiffies.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched/mm.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include "api.h"

#ifndef CONFIG_KDLOCK_MMAP
#error "actual enabled-MM kernel required"
#endif

struct sh_file {
	struct mm_struct *mm;
	struct task_struct *task;
	struct mutex control;
	struct completion release, entered;
	struct sh_report report;
	int state;
};
static atomic_t files = ATOMIC_INIT(0), mm_refs = ATOMIC_INIT(0);
static atomic_t active = ATOMIC_INIT(0), errors = ATOMIC_INIT(0);
static atomic64_t objects = ATOMIC64_INIT(0);

static int holder(void *arg)
{
	struct sh_file *s = arg;
	int ret;

	complete(&s->entered);
	s->report.holder_tid = task_pid_nr(current);
	ret = mmap_write_lock_killable(s->mm);
	if (ret) {
		s->report.errors++;
		goto done;
	}
	s->report.acquired = 1;
	if (!kd_mmap_is_write_owner(&s->mm->mmap_lock))
		s->report.errors++;
	/* Publish only after the physical owner is established. The separate-mm
	 * observer controls release; no user access is needed by this owner. */
	smp_store_release(&s->state, SH_HELD);
	if (!wait_for_completion_timeout(&s->release, 10 * HZ))
		s->report.timed_out = 1;
	if (!kd_mmap_is_write_owner(&s->mm->mmap_lock))
		s->report.errors++;
	mmap_write_unlock(s->mm);
	s->report.unlocked = 1;
done:
	mmput(s->mm);
	atomic_dec(&mm_refs);
	atomic_dec(&active);
	smp_store_release(&s->state, SH_FINISHED);
	return 0;
}

/* control serializes start/join; the holder never acquires this mutex. */
static void join(struct sh_file *s)
{
	if (!s->task)
		return;
	complete_all(&s->release);
	/* A stop issued before first execution can bypass the function entirely.
	 * Wait for its entry so that the worker always consumes its mm reference. */
	wait_for_completion(&s->entered);
	kthread_stop(s->task);
	put_task_struct(s->task);
	s->task = NULL;
	s->report.joined = 1;
}

static int sh_open(struct inode *inode, struct file *file)
{
	struct sh_file *s;

	if (!current->mm)
		return -EINVAL;
	s = kzalloc(sizeof(*s), GFP_KERNEL);
	if (!s)
		return -ENOMEM;
	s->mm = current->mm;
	mmgrab(s->mm);
	atomic_inc(&mm_refs);
	mutex_init(&s->control);
	init_completion(&s->release);
	init_completion(&s->entered);
	s->report = (struct sh_report) {
		.abi = SH_ABI, .object = atomic64_inc_return(&objects),
		.mm = (unsigned long)s->mm,
		.mmap_lock = (unsigned long)&s->mm->mmap_lock,
		.target_tgid = task_tgid_nr(current), .target_tid = task_pid_nr(current),
		.use_kd = s->mm->mmap_lock.use_kd,
	};
	file->private_data = s;
	atomic_inc(&files);
	return 0;
}

static int sh_close(struct inode *inode, struct file *file)
{
	struct sh_file *s = file->private_data;

	mutex_lock(&s->control);
	join(s);
	if (s->report.errors || s->report.timed_out ||
	    s->report.acquired != s->report.unlocked)
		atomic_inc(&errors);
	mutex_unlock(&s->control);
	mmdrop(s->mm);
	atomic_dec(&mm_refs);
	atomic_dec(&files);
	kfree(s);
	return 0;
}

static long sh_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct sh_file *s = file->private_data;
	struct sh_report report;
	long ret = 0;
	int state;

	if (cmd == SH_CONTEXT) {
		struct sh_context context = {
			.mm = (unsigned long)current->mm,
			.tgid = task_tgid_nr(current), .tid = task_pid_nr(current),
		};
		return copy_to_user((void __user *)arg, &context, sizeof(context)) ? -EFAULT : 0;
	}
	/* The inherited file is the explicit control capability. It intentionally
	 * permits an observer with another mm to release this exact holder. */
	if (cmd == SH_STATUS)
		return smp_load_acquire(&s->state);
	if (cmd == SH_RELEASE) {
		if (smp_load_acquire(&s->state) != SH_HELD)
			return -EINVAL;
		complete_all(&s->release);
		return 0;
	}
	mutex_lock(&s->control);
	state = smp_load_acquire(&s->state);
	if (cmd == SH_START) {
		if (state != SH_IDLE || s->task) {
			ret = -EBUSY;
			goto out;
		}
		if (!mmget_not_zero(s->mm)) {
			ret = -ESRCH;
			goto out;
		}
		atomic_inc(&mm_refs);
		atomic_inc(&active);
		smp_store_release(&s->state, SH_STARTING);
		s->task = kthread_create(holder, s, "mw_strict_hold");
		if (IS_ERR(s->task)) {
			ret = PTR_ERR(s->task);
			s->task = NULL;
			mmput(s->mm);
			atomic_dec(&mm_refs);
			atomic_dec(&active);
			s->report.errors++;
			smp_store_release(&s->state, SH_FINISHED);
			goto out;
		}
		get_task_struct(s->task);
		kthread_bind(s->task, 1);
		wake_up_process(s->task);
	} else if (cmd == SH_JOIN) {
		join(s);
		if (!s->report.joined || s->report.errors || s->report.timed_out ||
		    s->report.acquired != 1 || s->report.unlocked != 1)
			ret = -EIO;
	} else if (cmd == SH_REPORT) {
		/* No racing report packet and no copy while the target lock is held. */
		if (state != SH_IDLE && !s->report.joined) {
			ret = -EBUSY;
			goto out;
		}
		report = s->report;
		report.state = state;
		ret = copy_to_user((void __user *)arg, &report, sizeof(report)) ? -EFAULT : 0;
	} else {
		ret = -ENOTTY;
	}
out:
	mutex_unlock(&s->control);
	return ret;
}

static const struct file_operations ops = {
	.owner = THIS_MODULE, .open = sh_open, .release = sh_close, .unlocked_ioctl = sh_ioctl,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mmap_strict_hold", .fops = &ops, .mode = 0600,
};
static int health_get(char *buffer, const struct kernel_param *unused)
{
	return scnprintf(buffer, PAGE_SIZE, "files=%d mm_refs=%d active=%d errors=%d objects=%lld\n",
		atomic_read(&files), atomic_read(&mm_refs), atomic_read(&active),
		atomic_read(&errors), atomic64_read(&objects));
}
static const struct kernel_param_ops health_ops = { .get = health_get };
module_param_cb(health, &health_ops, NULL, 0400);
static int __init sh_init(void) { return misc_register(&device); }
static void __exit sh_exit(void)
{
	WARN_ON_ONCE(atomic_read(&files) || atomic_read(&mm_refs) || atomic_read(&active));
	misc_deregister(&device);
}
module_init(sh_init);
module_exit(sh_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Correctness-only bounded holder for an actual same-mm syscall writer witness");
