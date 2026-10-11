// SPDX-License-Identifier: GPL-2.0-only
/* Scoped, task-context syscall comparison on the captured 6.1.159 kernel.
 * Native and KD retain the actual kernel mutex. TCLock requires its own object;
 * all consumers of the private pipe/file must obey the selected protocol.
 * The client retains every descriptor until the workers join and hooks unload.
 * No reads/writes/resizes, descriptor mutation, or independent consumers while
 * bound. This is not a general pipe/file locking replacement.
 */
#include <linux/file.h>
#include <linux/capability.h>
#include <linux/fs.h>
#include <linux/ftrace.h>
#include <linux/kallsyms.h>
#include <linux/magic.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/objtool.h>
#include <linux/percpu.h>
#include <linux/pid.h>
#include <linux/pipe_fs_i.h>
#include <linux/sched/task.h>
#include <linux/uaccess.h>
#include <asm/ioctls.h>
#include "control.h"

static char *target_path;
module_param(target_path, charp, 0400);
static int target_pid;
module_param(target_pid, int, 0400);
static int target_fd;
static struct file *target_file;
static struct pipe_inode_info *target_pipe;
static struct mutex *original_lock;
static unsigned long lock_addr;
module_param(lock_addr, ulong, 0400);
static DEFINE_PER_CPU(u64, redirected);

#ifdef RB_KDLOCK
#include "kd_mutex_direct.h"
#define RA_COOKIE struct kd_mutex_outer_cookie cookie
#define RA_LOCK() KD_MUTEX_OUTER_LOCK(original_lock, cookie, \
	".globl rb_entry\nrb_entry:\n\t" ANNOTATE_NOENDBR)
#define RA_UNLOCK() KD_MUTEX_OUTER_UNLOCK(original_lock, cookie)
extern char rb_entry[];
#elif defined(RB_TCLOCK)
#include "mutex/komb_mutex.h"
static struct komb_mutex tc_lock __aligned(64);
int tc_mutex_worker_register(void);
int tc_mutex_workers_drain(void);
#define RA_COOKIE do { } while (0)
#define RA_LOCK() komb_mutex_lock(&tc_lock)
#define RA_UNLOCK() komb_mutex_unlock(&tc_lock)
#else
#define RA_COOKIE do { } while (0)
#define RA_LOCK() (mutex_lock)(original_lock)
#define RA_UNLOCK() (mutex_unlock)(original_lock)
#endif

#if defined(RB_PIPEBYTES) || defined(RB_PIPECAP)
static __attribute__((noipa)) long rb_body(struct pipe_inode_info *pipe)
{
	long result;
#ifdef RB_PIPEBYTES
	unsigned int count, head, tail, mask;
#endif
	RA_COOKIE;
	RA_LOCK();
#ifdef RB_PIPEBYTES
	/* fs/pipe.c: pipe_ioctl(FIONREAD), including the live ring traversal. */
	count = 0;
	head = pipe->head;
	tail = pipe->tail;
	mask = pipe->ring_size - 1;
	while (tail != head) {
		count += pipe->bufs[tail & mask].len;
		tail++;
	}
	result = count;
#else
	/* fs/pipe.c: pipe_fcntl(F_GETPIPE_SZ). */
	result = pipe->max_usage * PAGE_SIZE;
#endif
	RA_UNLOCK();
	return result;
}
static long rb_redirected(struct file *file, unsigned int cmd, unsigned long arg)
{
	long result = rb_body(file->private_data);
#ifdef RB_PIPEBYTES
	return put_user((int)result, (int __user *)arg);
#else
	return result;
#endif
}
#ifdef RB_PIPEBYTES
#define RA_SYMBOL "pipe_ioctl"
#define RA_CMD FIONREAD
#else
#define RA_SYMBOL "pipe_fcntl"
#define RA_CMD F_GETPIPE_SZ
#endif
#else
static __attribute__((noipa)) long rb_body(struct file *file, loff_t offset,
					 unsigned int whence)
{
	loff_t maxsize, result;
	RA_COOKIE;
	RA_LOCK();
	/* The bound tmpfs file uses generic_file_llseek; only SEEK_SET/END.
	 * Both size reads and the real f_pos/f_version updates stay protected. */
	maxsize = file_inode(file)->i_sb->s_maxbytes;
	if (whence == SEEK_END)
		offset += i_size_read(file_inode(file));
	if (offset < 0 || offset > maxsize)
		result = -EINVAL;
	else {
		if (offset != file->f_pos) {
			file->f_pos = offset;
			file->f_version = 0;
		}
		result = offset;
	}
	RA_UNLOCK();
	return result;
}
static long rb_redirected(unsigned int fd, off_t offset, unsigned int whence)
{
	struct fd f = fdget(fd);
	long result;
	if (!f.file)
		return -EBADF;
	result = rb_body(f.file, offset, whence);
	fdput(f);
	return result;
}
#define RA_SYMBOL "ksys_lseek"
#endif

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
static int prepare_set(const char *value, const struct kernel_param *kp)
{
	unsigned int n;
	if (kstrtouint(value, 0, &n) || n != 1 || !lock_addr)
		return -EINVAL;
#ifdef RB_KDLOCK
	return kd_mutex_prepare(original_lock, (unsigned long)rb_entry,
				KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#else
	return 0;
#endif
}
static const struct kernel_param_ops prepare_ops = { .set = prepare_set };
module_param_cb(prepare, &prepare_ops, NULL, 0200);

static long control_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	/* Recovery can request the normal checked drain after a client exits.
	 * The provider itself rejects live tasks or active queue/stack state. */
	if (current->tgid != target_pid && !(cmd == RA_DRAIN && capable(CAP_SYS_ADMIN)))
		return -EPERM;
	if (cmd == RA_REGISTER) {
#ifdef RB_TCLOCK
		return tc_mutex_worker_register();
#else
		return 0;
#endif
	}
	if (cmd == RA_DRAIN) {
#ifdef RB_TCLOCK
		return tc_mutex_workers_drain();
#else
		return 0;
#endif
	}
	return -ENOTTY;
}
static const struct file_operations control_fops = {
	.owner = THIS_MODULE, .unlocked_ioctl = control_ioctl,
};
static struct miscdevice control_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "real_api_control",
	.fops = &control_fops, .mode = 0600,
};
static void notrace redirect(unsigned long ip, unsigned long parent_ip,
		struct ftrace_ops *ops, struct ftrace_regs *fregs)
{
	struct pt_regs *regs = ftrace_get_regs(fregs);
	bool match;
	if (!regs || current->tgid != target_pid)
		return;
#if defined(RB_PIPEBYTES) || defined(RB_PIPECAP)
	match = ((struct file *)regs->di)->private_data == target_pipe &&
		regs->si == RA_CMD;
#else
	match = regs->di == target_fd &&
		(regs->dx == SEEK_SET || regs->dx == SEEK_END);
#endif
	if (match) {
		this_cpu_inc(redirected);
		regs->ip = (unsigned long)rb_redirected;
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
	struct file *(*get_file)(struct task_struct *, unsigned int);
	struct task_struct *task;
	struct pid *pid;
	int path_pid, ret = -EINVAL;
	get_file = (void *)kallsyms_lookup_name("fget_task");
	if (!get_file || !target_path || target_pid <= 0 ||
	    sscanf(target_path, "/proc/%d/fd/%d", &path_pid, &target_fd) != 2 ||
	    path_pid != target_pid || target_fd < 0)
		return -EINVAL;
	pid = find_get_pid(target_pid);
	if (!pid)
		return -ESRCH;
	task = get_pid_task(pid, PIDTYPE_PID);
	put_pid(pid);
	if (!task)
		return -ESRCH;
	target_file = get_file(task, target_fd);
	put_task_struct(task);
	if (!target_file)
		return -EBADF;
	if (file_inode(target_file)->i_nlink)
		goto fail;
#if defined(RB_PIPEBYTES) || defined(RB_PIPECAP)
	if (!S_ISFIFO(file_inode(target_file)->i_mode) || !target_file->private_data)
		goto fail;
	target_pipe = target_file->private_data;
	if (pipe_has_watch_queue(target_pipe))
		goto fail;
	original_lock = &target_pipe->mutex;
#else
	if (!S_ISREG(file_inode(target_file)->i_mode) ||
	    file_inode(target_file)->i_sb->s_magic != TMPFS_MAGIC ||
	    (target_file->f_op->llseek != generic_file_llseek &&
	     (unsigned long)target_file->f_op->llseek != kallsyms_lookup_name("shmem_file_llseek")) ||
	    !(target_file->f_mode & FMODE_ATOMIC_POS))
		goto fail;
	original_lock = &target_file->f_pos_lock;
#endif
	if (mutex_is_locked(original_lock))
		goto fail;
#ifdef RB_TCLOCK
	komb_mutex_init(&tc_lock);
	lock_addr = (unsigned long)&tc_lock;
#else
	lock_addr = (unsigned long)original_lock;
#endif
	hook_addr = kallsyms_lookup_name(RA_SYMBOL);
	if (!hook_addr) {
		ret = -ENOENT;
		goto fail;
	}
	ret = misc_register(&control_device);
	if (ret)
		goto fail;
	ret = ftrace_set_filter_ip(&trace_ops, hook_addr, 0, 0);
	if (!ret) {
		ret = register_ftrace_function(&trace_ops);
		if (!ret)
			return 0;
		ftrace_set_filter_ip(&trace_ops, hook_addr, 1, 0);
	}
	misc_deregister(&control_device);
fail:
	fput(target_file);
	return ret;
}
static void __exit rb_exit(void)
{
	unregister_ftrace_function(&trace_ops);
	ftrace_set_filter_ip(&trace_ops, hook_addr, 1, 0);
	misc_deregister(&control_device);
	WARN_ON_ONCE(mutex_is_locked(original_lock));
	fput(target_file);
}
module_init(rb_init);
module_exit(rb_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Scoped pipe query and file position mutex comparison");
