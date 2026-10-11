// SPDX-License-Identifier: GPL-2.0-only
/* Bounded UTS namespace read/write comparison, captured Linux 6.1.159.
 * Only a private namespace with fixed native-x86-64 personality is bound.
 * Readers copy the real utsname; writers replace one 64-byte name. User copies,
 * permission checks, entropy mixing and proc notification remain in the syscall.
 * The matched arms notify AFTER unlocking: no proc-sysctl observers or independent
 * consumers of this namespace are allowed. All matched arms use private locks:
 * a Linux rwsem or KD/TC task-context rwlocks for this non-sleeping body. Stock
 * alone retains global uts_sem. This is not a general rwsem adapter.
 */
#include <linux/capability.h>
#include <linux/ftrace.h>
#include <linux/kallsyms.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/percpu.h>
#include <linux/personality.h>
#include <linux/pid.h>
#include <linux/random.h>
#include <linux/rwsem.h>
#include <linux/sched/task.h>
#include <linux/uaccess.h>
#include <linux/utsname.h>

static int target_pid, domain;
module_param(target_pid, int, 0400);
module_param(domain, int, 0400);
static char *target_path; /* Common controller receipt; namespace binds by PID. */
module_param(target_path, charp, 0400);
static struct uts_namespace *target_uts;
static void (*notify_uts)(enum uts_proc);
static void (*free_uts)(struct uts_namespace *);
static unsigned long lock_addr, gate_addr;
module_param(lock_addr, ulong, 0400);
module_param(gate_addr, ulong, 0400);
static DEFINE_PER_CPU(u64, redirected);

#ifdef RB_KDLOCK
#include "kd_rwlock.h"
static kd_rwlock_t rw_lock __aligned(64) = KD_RWLOCK_INITIALIZER;
extern char rb_entry[];
#define RA_READ() kd_read_lock(&rw_lock)
#define RA_READ_END() kd_read_unlock(&rw_lock)
#define RA_WRITE() KD_RWLOCK_DIRECT_WRITE_LOCK(&rw_lock, kd_rwlock_direct_cookie, \
	".globl rb_entry\nrb_entry:\n\t" ANNOTATE_NOENDBR)
#define RA_WRITE_END() KD_RWLOCK_DIRECT_WRITE_UNLOCK(&rw_lock, kd_rwlock_direct_cookie)
#elif defined(RB_TCLOCK)
#include "rwlock/komb_rwlock.h"
static struct komb_rwlock rw_lock __aligned(64) = __KOMB_RWLOCK_UNLOCKED;
#define RA_READ() do { preempt_disable(); komb_read_lock(&rw_lock); } while (0)
#define RA_READ_END() do { komb_read_unlock(&rw_lock); preempt_enable(); } while (0)
#define RA_WRITE() do { preempt_disable(); komb_write_lock(&rw_lock); } while (0)
#define RA_WRITE_END() do { komb_write_unlock(&rw_lock); preempt_enable(); } while (0)
#else
static struct rw_semaphore rw_lock __aligned(64) = __RWSEM_INITIALIZER(rw_lock);
#define RA_READ() down_read(&rw_lock)
#define RA_READ_END() up_read(&rw_lock)
#define RA_WRITE() down_write(&rw_lock)
#define RA_WRITE_END() up_write(&rw_lock)
#endif

static __attribute__((noipa)) void rb_body(char *field, const char *value)
{
	RA_WRITE();
	memcpy(field, value, __NEW_UTS_LEN);
	field[__NEW_UTS_LEN] = 0;
	RA_WRITE_END();
}
static long read_name(const struct pt_regs *regs)
{
	struct new_utsname tmp;
	RA_READ();
	memcpy(&tmp, &target_uts->name, sizeof(tmp));
	RA_READ_END();
	return copy_to_user((void __user *)regs->di, &tmp, sizeof(tmp)) ? -EFAULT : 0;
}
static long write_name(const struct pt_regs *regs)
{
	char tmp[__NEW_UTS_LEN];
	if (!ns_capable(target_uts->user_ns, CAP_SYS_ADMIN))
		return -EPERM;
	if ((int)regs->si != sizeof(tmp))
		return -EINVAL;
	if (copy_from_user(tmp, (void __user *)regs->di, sizeof(tmp)))
		return -EFAULT;
	add_device_randomness(tmp, sizeof(tmp));
	rb_body(domain ? target_uts->name.domainname : target_uts->name.nodename, tmp);
	/* No observers of the bound namespace. Retain one global notification per
	 * successful syscall, on its original caller, outside the measured lock. */
	notify_uts(domain ? UTS_PROC_DOMAINNAME : UTS_PROC_HOSTNAME);
	return 0;
}
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
static bool lock_idle(void)
{
#ifdef RB_KDLOCK
	return !kd_rwlock_state(&rw_lock) && !atomic_read(&rw_lock.gate.val);
#elif defined(RB_TCLOCK)
	return !atomic_read(&rw_lock.cnts) && !atomic_read(&rw_lock.lock.val);
#else
	return !rwsem_is_locked(&rw_lock);
#endif
}
static int idle_get(char *buf, const struct kernel_param *kp)
{
	return scnprintf(buf, PAGE_SIZE, "%d\n", lock_idle());
}
static const struct kernel_param_ops idle_ops = { .get = idle_get };
module_param_cb(quiescent, &idle_ops, NULL, 0400);
static int prepare_set(const char *value, const struct kernel_param *kp)
{
	unsigned int n;
	if (kstrtouint(value, 0, &n) || n != 1 || !lock_addr)
		return -EINVAL;
#ifdef RB_KDLOCK
	return kd_rwlock_prepare(&rw_lock, (unsigned long)rb_entry, KD_ENTRY_ABI_RWLOCK_CLOBBER_V1);
#else
	return 0;
#endif
}
static const struct kernel_param_ops prepare_ops = { .set = prepare_set };
module_param_cb(prepare, &prepare_ops, NULL, 0200);
static unsigned long read_ip, write_ip;
static struct ftrace_ops read_ops, write_ops;
static void notrace redirect(unsigned long ip, unsigned long parent_ip,
		struct ftrace_ops *ops, struct ftrace_regs *fregs)
{
	struct pt_regs *regs = ftrace_get_regs(fregs);
	const struct pt_regs *syscall_regs;
	if (!regs || current->tgid != target_pid || current->personality != PER_LINUX ||
	    current->nsproxy->uts_ns != target_uts)
		return;
	syscall_regs = (void *)regs->di;
	if (ops == &write_ops && (int)syscall_regs->si != __NEW_UTS_LEN)
		return;
	this_cpu_inc(redirected);
	regs->ip = (unsigned long)(ops == &read_ops ? read_name : write_name);
}
static struct ftrace_ops read_ops = {
	.func = redirect,
	.flags = FTRACE_OPS_FL_SAVE_REGS | FTRACE_OPS_FL_IPMODIFY | FTRACE_OPS_FL_RECURSION,
};
static struct ftrace_ops write_ops = {
	.func = redirect,
	.flags = FTRACE_OPS_FL_SAVE_REGS | FTRACE_OPS_FL_IPMODIFY | FTRACE_OPS_FL_RECURSION,
};
static void drop_namespace(void)
{
	if (refcount_dec_and_test(&target_uts->ns.count))
		free_uts(target_uts);
}
static int __init rb_init(void)
{
	struct uts_namespace *initial;
	struct task_struct *task;
	struct pid *pid;
	int ret;
	notify_uts = (void *)kallsyms_lookup_name("uts_proc_notify");
	free_uts = (void *)kallsyms_lookup_name("free_uts_ns");
	initial = (void *)kallsyms_lookup_name("init_uts_ns");
	read_ip = kallsyms_lookup_name("__x64_sys_newuname");
	write_ip = kallsyms_lookup_name(domain ? "__x64_sys_setdomainname" : "__x64_sys_sethostname");
	if (!notify_uts || !free_uts || !initial || !read_ip || !write_ip ||
	    target_pid <= 0 || (domain != 0 && domain != 1))
		return -EINVAL;
	pid = find_get_pid(target_pid);
	if (!pid)
		return -ESRCH;
	task = get_pid_task(pid, PIDTYPE_PID);
	put_pid(pid);
	if (!task)
		return -ESRCH;
	task_lock(task);
	if (task->nsproxy && task->personality == PER_LINUX) {
		target_uts = task->nsproxy->uts_ns;
		get_uts_ns(target_uts);
	}
	task_unlock(task);
	put_task_struct(task);
	if (!target_uts)
		return -EINVAL;
	if (target_uts == initial) {
		drop_namespace();
		return -EPERM;
	}
#ifdef RB_KDLOCK
	lock_addr = (unsigned long)&rw_lock;
	gate_addr = (unsigned long)&rw_lock.gate;
#elif defined(RB_TCLOCK)
	lock_addr = (unsigned long)&rw_lock;
	gate_addr = (unsigned long)&rw_lock.lock;
#else
	lock_addr = (unsigned long)&rw_lock;
	gate_addr = lock_addr;
#endif
	ret = ftrace_set_filter_ip(&read_ops, read_ip, 0, 0);
	if (ret)
		goto fail;
	ret = ftrace_set_filter_ip(&write_ops, write_ip, 0, 0);
	if (ret)
		goto unfilter_read;
	ret = register_ftrace_function(&read_ops);
	if (ret)
		goto unfilter_write;
	ret = register_ftrace_function(&write_ops);
	if (!ret)
		return 0;
	unregister_ftrace_function(&read_ops);
unfilter_write:
	ftrace_set_filter_ip(&write_ops, write_ip, 1, 0);
unfilter_read:
	ftrace_set_filter_ip(&read_ops, read_ip, 1, 0);
fail:
	drop_namespace();
	return ret;
}
static void __exit rb_exit(void)
{
	unregister_ftrace_function(&write_ops);
	unregister_ftrace_function(&read_ops);
	ftrace_set_filter_ip(&read_ops, read_ip, 1, 0);
	ftrace_set_filter_ip(&write_ops, write_ip, 1, 0);
	WARN_ON_ONCE(!lock_idle());
	drop_namespace();
}
module_init(rb_init);
module_exit(rb_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Scoped private UTS namespace read/write comparison");
