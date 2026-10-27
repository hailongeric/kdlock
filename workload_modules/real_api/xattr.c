// SPDX-License-Identifier: GPL-2.0-only
/* Scoped Linux 7 xattr rb-tree/shared-reader comparison.
 * The client retains an unlinked private tmpfs file and freezes its xattrs
 * before binding. No metadata mutation or independent consumer is permitted
 * until the entire worker cohort joins and the hook is removed. Every matched
 * arm uses its own correctly typed private rwlock; no embedded Linux lock is
 * reinterpreted. This is a scoped syscall experiment, not a general adapter.
 * KD readers execute locally: no delegation entry, image or helper learning.
 */
#include <linux/file.h>
#include <linux/fs.h>
#include <linux/ftrace.h>
#include <linux/kallsyms.h>
#include <linux/magic.h>
#include <linux/module.h>
#include <linux/percpu.h>
#include <linux/rbtree.h>
#include <linux/spinlock.h>
#include <linux/sched.h>
#include <linux/shmem_fs.h>
#include <linux/xattr.h>

static char *target_path;
static int target_pid;
module_param(target_path, charp, 0400);
module_param(target_pid, int, 0400);
static struct file *target_file;
static struct simple_xattrs *target_xattrs;
static unsigned long lock_addr, gate_addr;
module_param(lock_addr, ulong, 0400);
module_param(gate_addr, ulong, 0400);
static DEFINE_PER_CPU(u64, redirected);

#ifdef RB_KDLOCK
#include "kd_rwlock.h"
static kd_rwlock_t rw_lock __aligned(64) = KD_RWLOCK_INITIALIZER;
#define RA_READ() kd_read_lock(&rw_lock)
#define RA_READ_END() kd_read_unlock(&rw_lock)
#elif defined(RB_TCLOCK)
#include "rwlock/komb_rwlock.h"
static struct komb_rwlock rw_lock __aligned(64) = __KOMB_RWLOCK_UNLOCKED;
/* The admitted syscall callers enter with IRQs enabled. Match the existing
 * TCLock rwlock pairing and restore that state after the complete read pair. */
#define RA_READ() do { preempt_disable(); komb_read_lock(&rw_lock); } while (0)
#define RA_READ_END() do { komb_read_unlock(&rw_lock); local_irq_enable(); preempt_enable(); } while (0)
#else
static rwlock_t rw_lock __aligned(64) = __RW_LOCK_UNLOCKED(rw_lock);
#define RA_READ() read_lock(&rw_lock)
#define RA_READ_END() read_unlock(&rw_lock)
#endif

static int rb_xattr_compare(const void *key, const struct rb_node *node)
{
	const struct simple_xattr *xattr = rb_entry(node, struct simple_xattr, rb_node);

	return strcmp(xattr->name, key);
}

/* Ubuntu linux=7.0.0-38.38 fs/xattr.c: simple_xattr_get and its comparator.
 * Keep rb_find's strcmp ordering, -ENODATA/-ERANGE, size-only lookup and value
 * copy semantics. Only the shared-read lock routes to the selected backend.
 * "front"/"tail" queries identify keys, not positions in the former list. */
static __attribute__((noipa)) int rb_body(struct simple_xattrs *xattrs,
		const char *name, void *buffer, size_t size)
{
	struct simple_xattr *xattr = NULL;
	struct rb_node *node;
	int ret = -ENODATA;

	RA_READ();
	node = rb_find(name, &xattrs->rb_root, rb_xattr_compare);
	if (node) {
		xattr = rb_entry(node, struct simple_xattr, rb_node);
		ret = xattr->size;
		if (buffer) {
			if (size < xattr->size)
				ret = -ERANGE;
			else
				memcpy(buffer, xattr->value, xattr->size);
		}
	}
	RA_READ_END();
	return ret;
}

static bool lock_idle(void)
{
#ifdef RB_KDLOCK
	return !kd_rwlock_state(&rw_lock) && !atomic_read(&rw_lock.gate.val);
#elif defined(RB_TCLOCK)
	return !atomic_read(&rw_lock.cnts) && !atomic_read(&rw_lock.lock.val);
#else
	return !atomic_read(&rw_lock.raw_lock.cnts) &&
		!atomic_read(&rw_lock.raw_lock.wait_lock.val);
#endif
}

static int calls_get(char *buffer, const struct kernel_param *param)
{
	u64 sum = 0;
	int cpu;

	for_each_possible_cpu(cpu)
		sum += READ_ONCE(per_cpu(redirected, cpu));
	return scnprintf(buffer, PAGE_SIZE, "%llu\n", sum);
}
static const struct kernel_param_ops calls_ops = { .get = calls_get };
module_param_cb(calls, &calls_ops, NULL, 0400);

static int idle_get(char *buffer, const struct kernel_param *param)
{
	return scnprintf(buffer, PAGE_SIZE, "%d\n", lock_idle());
}
static const struct kernel_param_ops idle_ops = { .get = idle_get };
module_param_cb(quiescent, &idle_ops, NULL, 0400);

static int prepare_set(const char *value, const struct kernel_param *param)
{
	unsigned int n;

	if (kstrtouint(value, 0, &n) || n != 1 || !lock_addr)
		return -EINVAL;
	/* The common controller may mark binding complete; no JIT is prepared. */
	return 0;
}
static const struct kernel_param_ops prepare_ops = { .set = prepare_set };
module_param_cb(prepare, &prepare_ops, NULL, 0200);

static void notrace redirect(unsigned long ip, unsigned long parent_ip,
		struct ftrace_ops *ops, struct ftrace_regs *fregs)
{
	struct pt_regs *regs = ftrace_get_regs(fregs);

	if (!regs || current->tgid != target_pid || (void *)regs->di != target_xattrs)
		return;
	/* The recursion-protected callback pins this per-CPU observation. The
	 * original syscall resumes in rb_body with its own task and arguments. */
	this_cpu_inc(redirected);
	regs->ip = (unsigned long)rb_body;
}
static struct ftrace_ops trace_ops = {
	.func = redirect,
	.flags = FTRACE_OPS_FL_SAVE_REGS | FTRACE_OPS_FL_IPMODIFY |
		 FTRACE_OPS_FL_RECURSION,
};
static unsigned long hook_addr;

static int __init rb_init(void)
{
	struct inode *inode;
	int path_pid, path_fd, ret;

	if (!target_path || target_pid <= 0 ||
	    sscanf(target_path, "/proc/%d/fd/%d", &path_pid, &path_fd) != 2 ||
	    path_pid != target_pid || path_fd < 0)
		return -EINVAL;
	target_file = filp_open(target_path, O_RDONLY, 0);
	if (IS_ERR(target_file))
		return PTR_ERR(target_file);
	inode = file_inode(target_file);
	if (inode->i_sb->s_magic != TMPFS_MAGIC || !S_ISREG(inode->i_mode) || inode->i_nlink) {
		ret = -EINVAL;
		goto fail;
	}
	/* The file reference pins this inode and its immutable xattr tree through
	 * the joined/no-new-callers boundary and hook removal. */
	target_xattrs = &SHMEM_I(inode)->xattrs;
	lock_addr = (unsigned long)&rw_lock;
#ifdef RB_KDLOCK
	gate_addr = (unsigned long)&rw_lock.gate;
#elif defined(RB_TCLOCK)
	gate_addr = (unsigned long)&rw_lock.lock;
#else
	gate_addr = (unsigned long)&rw_lock.raw_lock.wait_lock;
#endif
	hook_addr = kallsyms_lookup_name("simple_xattr_get");
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
	fput(target_file);
	return ret;
}

static void __exit rb_exit(void)
{
	/* The controller has joined every worker and barred new calls. Callback
	 * unregister alone does not establish the redirected body's lifetime. */
	unregister_ftrace_function(&trace_ops);
	ftrace_set_filter_ip(&trace_ops, hook_addr, 1, 0);
	WARN_ON_ONCE(!lock_idle());
	fput(target_file);
}
module_init(rb_init);
module_exit(rb_exit);
MODULE_LICENSE("GPL");
MODULE_INFO(workload_scope, "xattr-rbtree-read-v1");
MODULE_INFO(jit_eligibility, "local-read-only");
MODULE_DESCRIPTION("Scoped Linux 7 xattr rb-tree lookup with private shared-read locks");
