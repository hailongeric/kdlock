// SPDX-License-Identifier: GPL-2.0-only
/* Scoped syscall experiment for the captured Linux 6.1.159 kernel.
 * The client owns a private memfd, populates it before binding, and keeps its
 * metadata and OFD owner alive and immutable until every worker has joined and
 * this module is removed. The setfd case changes only preallocated descriptor
 * flags; no descriptors may be opened or closed while it is bound.
 * This is NOT a general mixed-native locking adapter.
 * All selected operations on the bound object use one protocol; other objects
 * continue through the original kernel function. No kernel text is rewritten
 * outside the normal ftrace IPMODIFY mechanism.
 *
 * The xattr body is from fs/xattr.c (Andreas Gruenbacher, SGI, Red Hat).
 * The OFD body follows fs/locks.c: posix_test_lock, posix_locks_conflict,
 * locks_overlap and locks_copy_conflock, specialized to local OFD locks whose
 * absent lock-manager callbacks are checked at bind time.
 */
#include <linux/file.h>
#include <linux/fdtable.h>
#include <linux/fs.h>
#include <linux/ftrace.h>
#include <linux/kallsyms.h>
#include <linux/magic.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/percpu.h>
#include <linux/pid.h>
#include <linux/sched/task.h>
#include <linux/shmem_fs.h>
#include <linux/xattr.h>

#ifdef RB_KDLOCK
#include "kd_spin_direct.h"
#define RB_LOCK(p) KD_SPIN_DIRECT_LOCK((p), kd_spin_direct_cookie, \
	".globl rb_entry\nrb_entry:\n\t" ANNOTATE_NOENDBR)
#define RB_UNLOCK(p) KD_SPIN_DIRECT_UNLOCK((p), kd_spin_direct_cookie)
extern char rb_entry[];
#elif defined(RB_TCLOCK)
void komb_spin_lock(struct qspinlock *lock);
void komb_spin_unlock(struct qspinlock *lock);
#define RB_LOCK(p) do { preempt_disable(); komb_spin_lock((void *)(p)); } while (0)
#define RB_UNLOCK(p) do { komb_spin_unlock((void *)(p)); preempt_enable(); } while (0)
#else
#define RB_LOCK(p) __raw_spin_lock(&(p)->rlock)
#define RB_UNLOCK(p) __raw_spin_unlock(&(p)->rlock)
#endif

static char *target_path;
module_param(target_path, charp, 0400);
static struct file *target_file;
static struct inode *target_inode;
#ifdef RB_SETFD
static int target_pid;
module_param(target_pid, int, 0400);
static struct files_struct *target_files;
static void (*release_files)(struct files_struct *);
#endif
#ifdef RB_XATTR
static struct simple_xattrs *target_xattrs;
#endif
static unsigned long lock_addr;
module_param(lock_addr, ulong, 0400);
static DEFINE_PER_CPU(u64, redirected);

static int calls_get(char *buf, const struct kernel_param *kp)
{
	u64 sum = 0;
	int cpu;
	for_each_possible_cpu(cpu)
		sum += READ_ONCE(per_cpu(redirected, cpu));
	return scnprintf(buf, PAGE_SIZE, "%llu\n", sum);
}
static const struct kernel_param_ops calls_ops = { .get = calls_get };
module_param_cb(calls, &calls_ops, NULL, 0400);

#ifdef RB_XATTR
static __attribute__((noipa)) int rb_body(struct simple_xattrs *xattrs,
		const char *name, void *buffer, size_t size)
{
	struct simple_xattr *xattr;
	int ret = -ENODATA;

	RB_LOCK(&xattrs->lock);
	list_for_each_entry(xattr, &xattrs->head, list) {
		if (strcmp(name, xattr->name))
			continue;
		ret = xattr->size;
		if (buffer) {
			if (size < xattr->size)
				ret = -ERANGE;
			else
				memcpy(buffer, xattr->value, xattr->size);
		}
		break;
	}
	RB_UNLOCK(&xattrs->lock);
	return ret;
}
#define RB_SYMBOL "simple_xattr_get"
#elif defined(RB_OFD)
static __attribute__((noipa)) void rb_body(struct file *filp, struct file_lock *fl)
{
	struct file_lock_context *ctx = locks_inode_context(file_inode(filp));
	struct file_lock *cfl;

	if (!ctx || list_empty_careful(&ctx->flc_posix)) {
		fl->fl_type = F_UNLCK;
		return;
	}
	RB_LOCK(&ctx->flc_lock);
	list_for_each_entry(cfl, &ctx->flc_posix, fl_list) {
		if (fl->fl_owner == cfl->fl_owner)
			continue;
		if (fl->fl_end < cfl->fl_start || cfl->fl_end < fl->fl_start)
			continue;
		if (cfl->fl_type != F_WRLCK && fl->fl_type != F_WRLCK)
			continue;
		/* Bind rejects any lmops: no callback ownership/expiry is omitted
		 * from the admitted local-OFD workload. Field copies match Linux. */
		fl->fl_owner = cfl->fl_owner;
		fl->fl_pid = cfl->fl_pid;
		fl->fl_file = NULL;
		fl->fl_flags = cfl->fl_flags;
		fl->fl_type = cfl->fl_type;
		fl->fl_start = cfl->fl_start;
		fl->fl_end = cfl->fl_end;
		fl->fl_lmops = cfl->fl_lmops;
		fl->fl_ops = NULL;
		goto out;
	}
	fl->fl_type = F_UNLCK;
out:
	RB_UNLOCK(&ctx->flc_lock);
}
#define RB_SYMBOL "posix_test_lock"
#else
/* fs/file.c: set_close_on_exec, __set_close_on_exec, __clear_close_on_exec.
 * Preserve the clear-path test_bit as well as the original bitmap operations.
 * The task/files lookup occurs before the delegatable critical section. */
static __attribute__((noipa)) void rb_body(unsigned int fd, int flag)
{
	struct files_struct *files = current->files;
	struct fdtable *fdt;
	RB_LOCK(&files->file_lock);
	fdt = files_fdtable(files);
	if (flag)
		__set_bit(fd, fdt->close_on_exec);
	else if (test_bit(fd, fdt->close_on_exec))
		__clear_bit(fd, fdt->close_on_exec);
	RB_UNLOCK(&files->file_lock);
}
#define RB_SYMBOL "set_close_on_exec"
#endif

static int prepare_set(const char *value, const struct kernel_param *kp)
{
	unsigned int n;
	if (kstrtouint(value, 0, &n) || n != 1 || !lock_addr)
		return -EINVAL;
#ifdef RB_KDLOCK
	return kd_spin_prepare((void *)lock_addr, (unsigned long)rb_entry,
			       KD_ENTRY_ABI_SPIN_CLOBBER_V1);
#else
	return 0;
#endif
}
static const struct kernel_param_ops prepare_ops = { .set = prepare_set };
module_param_cb(prepare, &prepare_ops, NULL, 0200);

static void notrace redirect(unsigned long ip, unsigned long parent_ip,
		struct ftrace_ops *ops, struct ftrace_regs *fregs)
{
	struct pt_regs *regs = ftrace_get_regs(fregs);
	bool match;
	if (!regs)
		return;
#ifdef RB_XATTR
	match = (void *)regs->di == target_xattrs;
#elif defined(RB_OFD)
	match = file_inode((struct file *)regs->di) == target_inode;
#else
	match = current->files == target_files;
#endif
	if (match) {
		/* FTRACE_OPS_FL_RECURSION supplies recursion protection and pins
		 * preemption across this callback. Counters are read after join. */
		this_cpu_inc(redirected);
		regs->ip = (unsigned long)rb_body;
	}
}
static struct ftrace_ops trace_ops = {
	.func = redirect,
	.flags = FTRACE_OPS_FL_SAVE_REGS | FTRACE_OPS_FL_IPMODIFY |
		 FTRACE_OPS_FL_RECURSION,
};
static unsigned long hook_addr;

static int __init rb_init(void)
{
	int ret;
#ifdef RB_OFD
	struct file_lock_context *ctx;
	struct file_lock *fl;
	unsigned int count = 0;
#endif
#ifdef RB_SETFD
	struct pid *pid;
	struct task_struct *task;
	int path_pid, path_fd;
#endif
	BUILD_BUG_ON(sizeof(spinlock_t) != 4);
	if (!target_path)
		return -EINVAL;
	target_file = filp_open(target_path, O_RDONLY, 0);
	if (IS_ERR(target_file))
		return PTR_ERR(target_file);
	target_inode = file_inode(target_file);
	if (target_inode->i_sb->s_magic != TMPFS_MAGIC ||
	    !S_ISREG(target_inode->i_mode) || target_inode->i_nlink) {
		ret = -EINVAL;
		goto fail;
	}
#ifdef RB_XATTR
	target_xattrs = &SHMEM_I(target_inode)->xattrs;
	lock_addr = (unsigned long)&target_xattrs->lock;
#elif defined(RB_OFD)
	ctx = locks_inode_context(target_inode);
	if (!ctx) {
		ret = -EINVAL;
		goto fail;
	}
	__raw_spin_lock(&ctx->flc_lock.rlock);
	list_for_each_entry(fl, &ctx->flc_posix, fl_list) {
		if (!(fl->fl_flags & FL_OFDLCK) || fl->fl_lmops || fl->fl_ops) {
			count = 0;
			break;
		}
		count++;
	}
	__raw_spin_unlock(&ctx->flc_lock.rlock);
	if (!count) {
		ret = -EINVAL;
		goto fail;
	}
	lock_addr = (unsigned long)&ctx->flc_lock;
#else
	/* Hold an exact files_struct reference until hooks/callers have drained.
	 * put_files_struct is not exported by this captured kernel; resolve its
	 * real implementation for teardown only, never in a measured/JIT body. */
	release_files = (void *)kallsyms_lookup_name("put_files_struct");
	if (!release_files || target_pid <= 0 ||
	    sscanf(target_path, "/proc/%d/fd/%d", &path_pid, &path_fd) != 2 ||
	    path_pid != target_pid) {
		ret = -EINVAL;
		goto fail;
	}
	pid = find_get_pid(target_pid);
	if (!pid) {
		ret = -ESRCH;
		goto fail;
	}
	task = get_pid_task(pid, PIDTYPE_PID);
	put_pid(pid);
	if (!task) {
		ret = -ESRCH;
		goto fail;
	}
	task_lock(task);
	target_files = task->files;
	if (target_files)
		atomic_inc(&target_files->count);
	task_unlock(task);
	put_task_struct(task);
	if (!target_files) {
		ret = -ESRCH;
		goto fail;
	}
	lock_addr = (unsigned long)&target_files->file_lock;
#endif
	hook_addr = kallsyms_lookup_name(RB_SYMBOL);
	if (!hook_addr) {
		ret = -ENOENT;
		goto fail;
	}
	ret = ftrace_set_filter_ip(&trace_ops, hook_addr, 0, 0);
	if (ret)
		goto fail;
	ret = register_ftrace_function(&trace_ops);
	if (ret) {
		ftrace_set_filter_ip(&trace_ops, hook_addr, 1, 0);
		goto fail;
	}
	return 0;
fail:
#ifdef RB_SETFD
	if (target_files)
		release_files(target_files);
#endif
	fput(target_file);
	return ret;
}

static void __exit rb_exit(void)
{
	/* The controller joins all workers, checks the provider, and retires
	 * KD text before removal. The client retains the immutable object until
	 * after this returns. unregister waits for active trace callbacks. */
	unregister_ftrace_function(&trace_ops);
	ftrace_set_filter_ip(&trace_ops, hook_addr, 1, 0);
	WARN_ON_ONCE(atomic_read((atomic_t *)lock_addr));
#ifdef RB_SETFD
	release_files(target_files);
#endif
	fput(target_file);
}
module_init(rb_init);
module_exit(rb_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Scoped xattr / OFD / file-table syscall critical-section comparison");
