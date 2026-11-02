// SPDX-License-Identifier: GPL-2.0
/* Unscored observation only: no native MM body or lock API is changed. */
#include <linux/fs.h>
#include <linux/kprobes.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mman.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/sched/mm.h>
#include <linux/spinlock.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include "api.h"

#ifndef CONFIG_X86_64
#error "The captured vm_mmap_pgoff argument contract is x86-64 only"
#endif

static char target[TASK_COMM_LEN];
module_param_string(target, target, sizeof(target), 0444);
static DEFINE_MUTEX(control);
static DEFINE_RAW_SPINLOCK(records_lock);
static struct kd_mmap1_identity_snapshot snapshot;
static struct mm_struct *held_mm[KD_MMAP1_IDENTITY_CAPACITY];
static bool registered;

static int observe(struct kprobe *probe, struct pt_regs *regs)
{
	struct kd_mmap1_identity_record *row;
	struct mm_struct *mm;
	unsigned long flags;
	unsigned int i;
	pid_t tid;
	u64 start;
	bool use_kd = false;
	void *backing;
	const void *provider = NULL;
	u64 route = 0;

	(void)probe;
	/* vm_mmap_pgoff(file, addr, len, prot, flags, pgoff), native C ABI.
	 * Exclude loader/harness mappings: only the unchanged mmap1 testcase
	 * has this exact anonymous 128 MiB argument tuple. */
	if (strncmp(current->comm, target, TASK_COMM_LEN) || regs->di || regs->si ||
	    regs->dx != 128UL * 1024 * 1024 || regs->cx != (PROT_READ | PROT_WRITE) ||
	    regs->r8 != (MAP_PRIVATE | MAP_ANONYMOUS) || regs->r9)
		return 0;
	mm = current->mm;
	if (!mm)
		return 0;
	tid = task_pid_nr(current);
	start = current->start_boottime;
#ifdef CONFIG_KDLOCK_MMAP
	use_kd = READ_ONCE(mm->mmap_lock.use_kd);
	backing = use_kd ? (void *)&mm->mmap_lock.kd : (void *)&mm->mmap_lock.native;
	provider = READ_ONCE(mm->mmap_lock.provider);
	route = use_kd ? (provider ? 2 : 1) : 0;
#else
	backing = &mm->mmap_lock;
#endif
	raw_spin_lock_irqsave(&records_lock, flags);
	for (i = 0; i < snapshot.count; i++) {
		row = &snapshot.records[i];
		if (row->tid != (u64)tid || row->start_boottime_ns != start)
			continue;
		if (row->mm != (unsigned long)mm || row->lock != (unsigned long)&mm->mmap_lock ||
		    row->backing != (unsigned long)backing || row->use_kd != use_kd ||
		    row->provider != (unsigned long)provider || row->route != route)
			snapshot.errors++;
		goto out;
	}
	if (snapshot.count == KD_MMAP1_IDENTITY_CAPACITY) {
		snapshot.overflow++;
		goto out;
	}
	/* Retain the exact allocation while the table contains its address.
	 * The original task owns mm_users here. Teardown drops these mm_count
	 * references only after unregister_kprobe has excluded every handler. */
	mmgrab(mm);
	held_mm[i] = mm;
	row = &snapshot.records[i];
	row->tid = tid;
	row->tgid = task_tgid_nr(current);
	row->start_boottime_ns = start;
	row->mm = (unsigned long)mm;
	row->lock = (unsigned long)&mm->mmap_lock;
	row->backing = (unsigned long)backing;
	row->use_kd = use_kd;
	row->cpu = raw_smp_processor_id();
	row->provider = (unsigned long)provider;
	row->route = route;
	snapshot.refs_acquired++;
	snapshot.count++;
out:
	raw_spin_unlock_irqrestore(&records_lock, flags);
	return 0;
}

static struct kprobe mapping_probe = {
	.symbol_name = "vm_mmap_pgoff",
	.pre_handler = observe,
};

static void stop_observation(void)
{
	unsigned int i;

	if (registered) {
		unregister_kprobe(&mapping_probe);
		registered = false;
	}
	for (i = 0; i < snapshot.count; i++) {
		struct mm_struct *mm = held_mm[i];

		if (!mm)
			continue;
		held_mm[i] = NULL;
		mmdrop(mm);
		snapshot.refs_released++;
	}
	snapshot.stopped = 1;
}

static long observation_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
	long result = 0;

	(void)file;
	if (command != KD_MMAP1_IDENTITY_STOP)
		return -ENOTTY;
	mutex_lock(&control);
	stop_observation();
	if (copy_to_user((void __user *)arg, &snapshot, sizeof(snapshot)))
		result = -EFAULT;
	mutex_unlock(&control);
	return result;
}

static const struct file_operations observation_operations = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = observation_ioctl,
};
static struct miscdevice observation_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "kd_mmap1_identity",
	.fops = &observation_operations,
	.mode = 0600,
};

static int __init observation_init(void)
{
	int result;

	if (strcmp(target, "mmap1_threads") && strcmp(target, "mmap1_processes"))
		return -EINVAL;
	snapshot.abi = 2;
	result = register_kprobe(&mapping_probe);
	if (result)
		return result;
	registered = true;
	result = misc_register(&observation_device);
	if (result)
		stop_observation();
	return result;
}

static void __exit observation_exit(void)
{
	misc_deregister(&observation_device);
	mutex_lock(&control);
	stop_observation();
	mutex_unlock(&control);
}
module_init(observation_init);
module_exit(observation_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Unscored unchanged mmap1 task/mm/mmap_lock identity observer");
