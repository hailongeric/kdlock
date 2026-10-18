// SPDX-License-Identifier: GPL-2.0
/* The exact kernel strcmp executes on stable module-owned strings. A long,
 * still valid string exceeds the service's preflight bound; its original CALL
 * must then run on the waiter exactly once, after the already executed prefix.
 * The control gate changes strings only after every worker has drained. */
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include "kd_spin_direct.h"
#include "api.h"

static DEFINE_KD_SPINLOCK(test_lock);
static atomic_t control = ATOMIC_INIT(0);
static atomic_t writers = ATOMIC_INIT(0);
static atomic_t failures = ATOMIC_INIT(0);
static atomic_t worker_active[64];
static unsigned int hot;
static u64 prefix __aligned(64), suffix, hot_taken;
static char left[301], right[301];
extern char jit_escape_entry[];

struct guard_record {
	int result;
	unsigned long task;
};
static struct guard_record records[64];

static __attribute__((noipa)) void guard_body(struct guard_record *record)
{
	KD_SPIN_DIRECT_LOCK(&test_lock, kd_spin_direct_cookie,
		".globl jit_escape_entry\njit_escape_entry:\n\t" ANNOTATE_NOENDBR);
	if (atomic_inc_return(&writers) != 1)
		atomic_inc(&failures);
	WRITE_ONCE(prefix, READ_ONCE(prefix) + 1);
	record->result = strcmp(left, right);
	asm volatile("movq %%gs:current_task, %%rax\n\t"
		     "movq %%rax, %0\n\t"
		     : "=m" (record->task) : : "rax", "memory");
	if (READ_ONCE(hot))
		WRITE_ONCE(hot_taken, READ_ONCE(hot_taken) + 1);
	WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
	if (atomic_dec_return(&writers))
		atomic_inc(&failures);
	KD_SPIN_DIRECT_UNLOCK(&test_lock, kd_spin_direct_cookie);
}

static long guard_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct jit_escape_snapshot snapshot = { 0 };
	struct jit_escape_run run;
	unsigned int before_preempt, i;
	bool before_irqs;
	int ret = 0;

	(void)file;
	if (cmd == JIT_ESCAPE_RUN) {
		if (copy_from_user(&run, user, sizeof(run)))
			return -EFAULT;
		if (!run.iterations || run.iterations > 10000000 ||
		    run.worker >= 64 || run.reserved[0] || run.reserved[1])
			return -EINVAL;
		if (atomic_cmpxchg(&worker_active[run.worker], 0, 1))
			return -EBUSY;
		if (!atomic_add_unless(&control, 1, -1)) {
			atomic_set_release(&worker_active[run.worker], 0);
			return -EBUSY;
		}
		before_preempt = preempt_count();
		before_irqs = irqs_disabled();
		run.completed = run.errors = 0;
		for (i = 0; i < run.iterations; i++) {
			guard_body(&records[run.worker]);
			if (records[run.worker].result != 0 ||
			    records[run.worker].task != (unsigned long)current)
				run.errors++;
			run.completed++;
			if ((i & 255) == 0)
				cond_resched();
		}
		if (preempt_count() != before_preempt || irqs_disabled() != before_irqs)
			run.errors++;
		if (run.errors)
			atomic_inc(&failures);
		atomic_set_release(&worker_active[run.worker], 0);
		(void)atomic_dec_return_release(&control);
		return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
	}
	if (cmd != JIT_ESCAPE_SNAPSHOT && cmd != JIT_ESCAPE_PREPARE && cmd != JIT_ESCAPE_HOT)
		return -ENOTTY;
	if (atomic_cmpxchg_acquire(&control, 0, -1))
		return -EBUSY;
	if (cmd == JIT_ESCAPE_PREPARE) {
		ret = kd_spin_prepare(&test_lock, (unsigned long)jit_escape_entry,
				      KD_ENTRY_ABI_SPIN_CLOBBER_V1);
	} else if (cmd == JIT_ESCAPE_HOT) {
		if (atomic_read(&test_lock.val))
			ret = -EBUSY;
		else {
			memset(left, 'x', sizeof(left) - 1);
			memset(right, 'x', sizeof(right) - 1);
			WRITE_ONCE(hot, 1);
		}
	} else {
		snapshot.prefix = prefix;
		snapshot.suffix = suffix;
		snapshot.hot_taken = hot_taken;
		snapshot.lock_address = (unsigned long)&test_lock;
		snapshot.entry = (unsigned long)jit_escape_entry;
		snapshot.marker = (unsigned long)strcmp;
		snapshot.failures = atomic_read(&failures);
		snapshot.active = atomic_read(&writers);
		snapshot.hot = READ_ONCE(hot);
		snapshot.idle = !atomic_read(&test_lock.val);
		ret = copy_to_user(user, &snapshot, sizeof(snapshot)) ? -EFAULT : 0;
	}
	atomic_set_release(&control, 0);
	return ret;
}

static const struct file_operations guard_fops = {
	.owner = THIS_MODULE, .unlocked_ioctl = guard_ioctl,
};
static struct miscdevice guard_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_jit_string_service_test",
	.fops = &guard_fops, .mode = 0600,
};
static int __init guard_init(void)
{
	BUILD_BUG_ON(sizeof(struct jit_escape_run) != 32);
	BUILD_BUG_ON(sizeof(struct jit_escape_snapshot) != 80);
	memset(left, 'x', 15);
	memset(right, 'x', 15);
	return misc_register(&guard_device);
}
static void __exit guard_exit(void) { misc_deregister(&guard_device); }
module_init(guard_init);
module_exit(guard_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Checked kernel string service and unexecuted-CALL native continuation");
