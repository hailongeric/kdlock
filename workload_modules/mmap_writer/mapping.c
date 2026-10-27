// SPDX-License-Identifier: GPL-2.0
/* Native mmap writer baseline. No private backing lock and no lock substitution.
 * A VFS file binds one exact mm_struct. Native mmap/munmap own VMA transitions;
 * the callbacks observe those transitions without granting release authority. */
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/sched/mm.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include "mmap_writer_uapi.h"

struct mw_file {
	struct mm_struct *mm;
	u64 object;
	atomic64_t maps, clones, closes, faults, context_errors, foreign_rejects, contended;
	atomic_t vmas;
};
static bool observe;
module_param(observe, bool, 0400);
static atomic_t files = ATOMIC_INIT(0), mm_refs = ATOMIC_INIT(0);
static atomic64_t objects = ATOMIC64_INIT(0), destroyed = ATOMIC64_INIT(0);
static atomic64_t release_errors = ATOMIC64_INIT(0);

static int mw_open(struct inode *inode, struct file *file)
{
	struct mw_file *m;
	if (!current->mm)
		return -EOPNOTSUPP;
	m = kzalloc(sizeof(*m), GFP_KERNEL);
	if (!m)
		return -ENOMEM;
	m->mm = current->mm;
	/* Pin only the mm descriptor, not mm_users. Pinning mm_users here could
	 * make a cycle through this file's VMAs and prevent exit_mmap teardown. */
	mmgrab(m->mm);
	atomic_inc(&mm_refs);
	m->object = atomic64_inc_return(&objects);
	file->private_data = m;
	atomic_inc(&files);
	return 0;
}

static int mw_release(struct inode *inode, struct file *file)
{
	struct mw_file *m = file->private_data;
	/* Only final VFS release permits destruction. Counts check consistency;
	 * they never replace file/VMA references or native lock ownership. */
	if (atomic_read(&m->vmas) || atomic64_read(&m->faults) ||
	    atomic64_read(&m->context_errors) ||
	    atomic64_read(&m->maps) + atomic64_read(&m->clones) != atomic64_read(&m->closes)) {
		atomic64_inc(&release_errors);
		WARN_ON_ONCE(1);
		__module_get(THIS_MODULE);
		return 0; /* Keep the exact mm/file state pinned for diagnosis. */
	}
	mmdrop(m->mm);
	atomic_dec(&mm_refs);
	kfree(m);
	atomic_dec(&files);
	atomic64_inc(&destroyed);
	return 0;
}

static void mw_vma_open(struct vm_area_struct *vma)
{
	struct mw_file *m = vma->vm_private_data;
	if (vma->vm_mm != m->mm)
		atomic64_inc(&m->context_errors);
	atomic64_inc(&m->clones);
	atomic_inc(&m->vmas);
}

static void mw_vma_close(struct vm_area_struct *vma)
{
	struct mw_file *m = vma->vm_private_data;
	/* Exit teardown need not have current->mm installed. VMA identity and
	 * its file reference, not implicit current state, protect this callback. */
	if (vma->vm_mm != m->mm)
		atomic64_inc(&m->context_errors);
	atomic64_inc(&m->closes);
	if (atomic_dec_return(&m->vmas) < 0)
		atomic64_inc(&m->context_errors);
}

static vm_fault_t mw_fault(struct vm_fault *vmf)
{
	struct mw_file *m = vmf->vma->vm_private_data;
	atomic64_inc(&m->faults);
	/* This module has no backing pages. Any access is a workload failure,
	 * never a page-fault timing sample or an implicitly populated mapping. */
	return VM_FAULT_SIGBUS;
}

static const struct vm_operations_struct mw_vm_ops = {
	.open = mw_vma_open, .close = mw_vma_close, .fault = mw_fault,
};

static bool mw_same_mm(struct mw_file *m)
{
	if (current->mm == m->mm)
		return true;
	atomic64_inc(&m->foreign_rejects);
	return false;
}

static int mw_mmap(struct file *file, struct vm_area_struct *vma)
{
	struct mw_file *m = file->private_data;
	if (!mw_same_mm(m))
		return -EXDEV;
	if (vma->vm_mm != m->mm) {
		atomic64_inc(&m->context_errors);
		return -EUCLEAN;
	}
	if (!(vma->vm_flags & VM_SHARED) || !(vma->vm_flags & VM_READ) ||
	    vma->vm_flags & (VM_WRITE | VM_EXEC))
		return -EOPNOTSUPP;
	if (vma->vm_pgoff >= MW_MAX_PAGES || vma_pages(vma) > MW_MAX_PAGES - vma->vm_pgoff)
		return -EINVAL;
	/* The native mmap syscall has acquired its real mmap_lock for writing.
	 * This assertion/queue query observes it; neither authorizes an unlock. */
	mmap_assert_write_locked(m->mm);
	if (observe && mmap_lock_is_contended(m->mm))
		atomic64_inc(&m->contended);
	vm_flags_set(vma, VM_DONTEXPAND | VM_DONTDUMP | VM_DONTCOPY);
	vm_flags_clear(vma, VM_MAYWRITE | VM_MAYEXEC);
	vma->vm_ops = &mw_vm_ops;
	vma->vm_private_data = m;
	atomic64_inc(&m->maps);
	atomic_inc(&m->vmas); /* Initial mmap does not invoke vm_ops.open. */
	return 0;
}

static long mw_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
	struct mw_file *m = file->private_data;
	void __user *user = (void __user *)arg;
	if (!mw_same_mm(m))
		return -EXDEV;
	if (command == MW_ID) {
		struct mw_identity id = {
			.abi = MW_ABI, .object = m->object,
			.mm = (unsigned long)m->mm, .mmap_lock = (unsigned long)&m->mm->mmap_lock,
			.tgid = task_tgid_nr(current), .tid = task_pid_nr(current),
		};
		return copy_to_user(user, &id, sizeof(id)) ? -EFAULT : 0;
	}
	if (command == MW_STATS) {
		struct mw_stats s = {
			.object = m->object, .maps = atomic64_read(&m->maps),
			.clones = atomic64_read(&m->clones), .closes = atomic64_read(&m->closes),
			.vmas = atomic_read(&m->vmas), .faults = atomic64_read(&m->faults),
			.context_errors = atomic64_read(&m->context_errors),
			.foreign_rejects = atomic64_read(&m->foreign_rejects),
			.contended_mmaps = atomic64_read(&m->contended), .observe = observe,
		};
		return copy_to_user(user, &s, sizeof(s)) ? -EFAULT : 0;
	}
	return -ENOTTY;
}

static const struct file_operations mw_fops = {
	.owner = THIS_MODULE, .open = mw_open, .release = mw_release,
	.mmap = mw_mmap, .unlocked_ioctl = mw_ioctl,
};
static struct miscdevice mw_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mmap_writer_native", .fops = &mw_fops, .mode = 0600,
};
static int health_get(char *buffer, const struct kernel_param *parameter)
{
	return scnprintf(buffer, PAGE_SIZE, "files=%d mm_refs=%d destroyed=%lld release_errors=%lld\n",
		atomic_read(&files), atomic_read(&mm_refs), atomic64_read(&destroyed), atomic64_read(&release_errors));
}
static const struct kernel_param_ops health_ops = { .get = health_get };
module_param_cb(health, &health_ops, NULL, 0400);
static int __init mw_init(void) { return misc_register(&mw_device); }
static void __exit mw_exit(void)
{
	WARN_ON_ONCE(atomic_read(&files) || atomic_read(&mm_refs) || atomic64_read(&release_errors));
	misc_deregister(&mw_device);
}
module_init(mw_init);
module_exit(mw_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Native shared-mm mmap writer baseline; no backing pages or lock replacement");
