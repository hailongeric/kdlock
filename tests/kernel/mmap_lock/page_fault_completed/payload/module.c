// SPDX-License-Identifier: GPL-2.0
/* Observe the real fault return; no synthetic fault result or lock substitute. */
#include <linux/fs.h>
#include <linux/kprobes.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/sched/mm.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include "api.h"

#ifndef CONFIG_KD_MMAP_LOCK
#error "Actual mmap-lock integration kernel required"
#endif

struct watch {
	struct kretprobe probe;
	struct task_struct *task;
	struct mm_struct *mm;
	struct completed_range range;
	struct completed_result result;
	bool active, finished;
};
static atomic_t opened = ATOMIC_INIT(0), closes = ATOMIC_INIT(0), errors = ATOMIC_INIT(0);

static int fault_entry(struct kretprobe_instance *ri, struct pt_regs *regs)
{
	struct watch *w = container_of(get_kretprobe(ri), struct watch, probe);
	struct vm_area_struct *vma = (void *)regs->di;
	unsigned long address = regs->si;

	/* File lifetime retains this exact mm/task pair until unregistration.
	 * Only this task updates observations; address selection is immutable
	 * while active. No count grants an acquisition or a release. */
	if (current != w->task || !READ_ONCE(w->active) || vma->vm_mm != w->mm ||
	    address < w->range.start || address >= w->range.end)
		return 1;
	w->result.entries++;
	if (!(regs->dx & FAULT_FLAG_WRITE))
		w->result.errors++;
	return 0;
}

static int fault_return(struct kretprobe_instance *ri, struct pt_regs *regs)
{
	struct watch *w = container_of(get_kretprobe(ri), struct watch, probe);
	vm_fault_t result = (vm_fault_t)regs_return_value(regs);

	w->result.returns++;
	w->result.completed += !!(result & VM_FAULT_COMPLETED);
	w->result.retries += !!(result & VM_FAULT_RETRY);
	w->result.errors += !!(result & VM_FAULT_ERROR);
	return 0;
}

static int watch_open(struct inode *inode, struct file *file)
{
	struct watch *w;
	int ret;

	if (!current->mm || atomic_cmpxchg(&opened, 0, 1))
		return -EBUSY;
	w = kzalloc(sizeof(*w), GFP_KERNEL);
	if (!w) {
		atomic_set(&opened, 0);
		return -ENOMEM;
	}
	w->task = current;
	get_task_struct(w->task);
	w->mm = current->mm;
	mmgrab(w->mm);
	w->probe.kp.symbol_name = "handle_mm_fault";
	w->probe.entry_handler = fault_entry;
	w->probe.handler = fault_return;
	w->probe.maxactive = 256;
	ret = register_kretprobe(&w->probe);
	if (ret) {
		mmdrop(w->mm);
		put_task_struct(w->task);
		kfree(w);
		atomic_set(&opened, 0);
		return ret;
	}
	w->result.mm = (unsigned long)w->mm;
	w->result.lock = (unsigned long)&w->mm->mmap_lock;
	w->result.tid = task_pid_nr(current);
	w->result.use_kd = w->mm->mmap_lock.use_kd;
	file->private_data = w;
	return 0;
}

static long watch_ioctl(struct file *file, unsigned int command, unsigned long argument)
{
	struct watch *w = file->private_data;
	void __user *user = (void __user *)argument;

	if (current != w->task || current->mm != w->mm)
		return -EXDEV;
	if (command == COMPLETED_START) {
		struct completed_range range;
		if (w->active || w->finished || copy_from_user(&range, user, sizeof(range)))
			return -EINVAL;
		if (!range.start || range.start >= range.end ||
		    (range.start | range.end) & (PAGE_SIZE - 1))
			return -EINVAL;
		w->range = range;
		WRITE_ONCE(w->active, true);
		return 0;
	}
	if (command == COMPLETED_END) {
		if (!w->active || w->finished)
			return -EINVAL;
		/* This exact task has returned from its user writes. Reacquiring
		 * the real write lock also detects a leaked read acquisition. */
		WRITE_ONCE(w->active, false);
		mmap_write_lock(w->mm);
		w->result.write_reacquired = kd_mmap_is_write_owner(&w->mm->mmap_lock);
		mmap_write_unlock(w->mm);
		w->result.missed = w->probe.nmissed;
		w->finished = true;
		return copy_to_user(user, &w->result, sizeof(w->result)) ? -EFAULT : 0;
	}
	return -ENOTTY;
}

static int watch_release(struct inode *inode, struct file *file)
{
	struct watch *w = file->private_data;

	/* Unregistration disables future callbacks and synchronizes current
	 * handlers before the retained mm/task references or watch are freed. */
	unregister_kretprobe(&w->probe);
	if (!w->finished || w->result.entries != w->result.returns || w->result.errors ||
	    w->probe.nmissed || !w->result.write_reacquired)
		atomic_inc(&errors);
	mmdrop(w->mm);
	put_task_struct(w->task);
	kfree(w);
	atomic_inc(&closes);
	atomic_set(&opened, 0);
	return 0;
}

static const struct file_operations operations = {
	.owner = THIS_MODULE, .open = watch_open, .release = watch_release,
	.unlocked_ioctl = watch_ioctl, .llseek = no_llseek,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mmap_completed", .fops = &operations, .mode = 0600,
};
static int health_get(char *buffer, const struct kernel_param *parameter)
{
	return scnprintf(buffer, PAGE_SIZE, "opened=%d closes=%d errors=%d\n",
		atomic_read(&opened), atomic_read(&closes), atomic_read(&errors));
}
static const struct kernel_param_ops health_ops = { .get = health_get };
module_param_cb(health, &health_ops, NULL, 0400);
static int __init test_init(void) { return misc_register(&device); }
static void __exit test_exit(void) { misc_deregister(&device); }
module_init(test_init);
module_exit(test_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Exact-task actual mmap fault-completion observer");
