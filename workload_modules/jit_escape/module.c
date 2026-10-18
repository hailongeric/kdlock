// SPDX-License-Identifier: GPL-2.0
/* A safe instruction exit with exact effects before and after native resume. */
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/uaccess.h>
#include "kd_mutex_direct.h"
#include "api.h"

static DEFINE_KD_MUTEX(test_lock);
static atomic_t control = ATOMIC_INIT(0);
static atomic_t writers = ATOMIC_INIT(0);
static atomic_t failures = ATOMIC_INIT(0);
static unsigned int hot;
static u64 prefix __aligned(64);
static u64 suffix;
static u64 hot_taken;
extern char jit_escape_entry[], jit_escape_marker[];

struct escape_result {
	u8 taken;
	u8 carry, parity, zero, sign, overflow;
	u32 ah;
	u32 tsc_low, tsc_high;
	unsigned long task;
};

static __attribute__((noipa)) void escape_body(struct escape_result *result)
{
	struct kd_mutex_outer_cookie cookie;

	KD_MUTEX_OUTER_LOCK(&test_lock, cookie,
		".globl jit_escape_entry\njit_escape_entry:\n\t" ANNOTATE_NOENDBR);
	if (atomic_inc_return(&writers) != 1)
		atomic_inc(&failures);
	WRITE_ONCE(prefix, READ_ONCE(prefix) + 1);
	result->taken = 0;
	if (READ_ONCE(hot)) {
		result->taken = 1;
		/* CMP defines CF/PF/AF/ZF/SF/OF: 1 - 2 gives status mask 0x95.
		 * The unconditional branch tests flag preservation across a JIT
		 * block boundary. RDTSC is safe on this guest and leaves flags
		 * unchanged. The native suffix observes each condition immediately;
		 * LAHF additionally exposes AF, which has no SETcc instruction.
		 * Read actual current_task here, after RDTSC, and compare only after
		 * returning to the original caller. No unsafe privileged operation
		 * is used to exercise the escape mechanism. */
		asm volatile("movl $1, %%eax\n\t"
			     "cmpl $2, %%eax\n\t"
			     "jmp jit_escape_marker\n\t"
			     ".globl jit_escape_marker\njit_escape_marker:\n\t"
			     "rdtsc\n\t"
			     "movl %%eax, %[low]\n\t"
			     "movl %%edx, %[high]\n\t"
			     "setc %[carry]\n\t"
			     "setp %[parity]\n\t"
			     "setz %[zero]\n\t"
			     "sets %[sign]\n\t"
			     "seto %[overflow]\n\t"
			     "lahf\n\t"
			     "movzbl %%ah, %%eax\n\t"
			     "movl %%eax, %[ah]\n\t"
			     "movq %%gs:current_task, %%rax\n\t"
			     "movq %%rax, %[task]\n\t"
			     : [low] "=m" (result->tsc_low),
			       [high] "=m" (result->tsc_high),
			       [carry] "=m" (result->carry),
			       [parity] "=m" (result->parity),
			       [zero] "=m" (result->zero),
			       [sign] "=m" (result->sign),
			       [overflow] "=m" (result->overflow),
			       [ah] "=m" (result->ah),
			       [task] "=m" (result->task)
			     : : "rax", "rdx", "cc", "memory");
		WRITE_ONCE(hot_taken, READ_ONCE(hot_taken) + 1);
	}
	WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
	if (atomic_dec_return(&writers))
		atomic_inc(&failures);
	KD_MUTEX_OUTER_UNLOCK(&test_lock, cookie);
}

static long escape_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct jit_escape_snapshot snapshot = { 0 };
	struct jit_escape_run run;
	struct escape_result result;
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
		if (!atomic_add_unless(&control, 1, -1))
			return -EBUSY;
		before_preempt = preempt_count();
		before_irqs = irqs_disabled();
		run.completed = run.errors = 0;
		for (i = 0; i < run.iterations; i++) {
			escape_body(&result);
			/* This comparison is outside the translated critical section.
			 * A delegated GS read cannot substitute for executing the safe
			 * native suffix on this exact original task. */
			if (result.taken != READ_ONCE(hot) ||
			    (result.taken &&
			     (result.task != (unsigned long)current ||
			      result.carry != 1 || result.parity != 1 ||
			      result.zero != 0 || result.sign != 1 ||
			      result.overflow != 0 || (result.ah & 0xd5) != 0x95)))
				run.errors++;
			run.completed++;
			if ((i & 255) == 0)
				cond_resched();
		}
		if (preempt_count() != before_preempt || irqs_disabled() != before_irqs)
			run.errors++;
		if (run.errors)
			atomic_inc(&failures);
		(void)atomic_dec_return_release(&control);
		return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
	}
	if (cmd != JIT_ESCAPE_SNAPSHOT && cmd != JIT_ESCAPE_PREPARE &&
	    cmd != JIT_ESCAPE_HOT)
		return -ENOTTY;
	/* Phase changes and inspection require every workload caller to join. */
	if (atomic_cmpxchg_acquire(&control, 0, -1))
		return -EBUSY;
	if (cmd == JIT_ESCAPE_PREPARE) {
		ret = kd_mutex_prepare(&test_lock, (unsigned long)jit_escape_entry,
				       KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	} else if (cmd == JIT_ESCAPE_HOT) {
		if (!kd_mutex_is_idle(&test_lock))
			ret = -EBUSY;
		else
			WRITE_ONCE(hot, 1);
	} else {
		snapshot.prefix = prefix;
		snapshot.suffix = suffix;
		snapshot.hot_taken = hot_taken;
		snapshot.lock_address = (unsigned long)&test_lock;
		snapshot.entry = (unsigned long)jit_escape_entry;
		snapshot.marker = (unsigned long)jit_escape_marker;
		snapshot.failures = atomic_read(&failures);
		snapshot.active = atomic_read(&writers);
		snapshot.hot = READ_ONCE(hot);
		snapshot.idle = kd_mutex_is_idle(&test_lock);
		ret = copy_to_user(user, &snapshot, sizeof(snapshot)) ? -EFAULT : 0;
	}
	atomic_set_release(&control, 0);
	return ret;
}

static const struct file_operations escape_fops = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = escape_ioctl,
};
static struct miscdevice escape_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "kd_jit_escape_test",
	.fops = &escape_fops,
	.mode = 0600,
};
static int __init escape_init(void)
{
	BUILD_BUG_ON(sizeof(struct jit_escape_run) != 32);
	BUILD_BUG_ON(sizeof(struct jit_escape_snapshot) != 80);
	return misc_register(&escape_device);
}
static void __exit escape_exit(void) { misc_deregister(&escape_device); }
module_init(escape_init);
module_exit(escape_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Conditional JIT instruction escape and exact native continuation");
