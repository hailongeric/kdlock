// SPDX-License-Identifier: GPL-2.0
/* Audit scope: the static counter is private to this test module. Only task
 * ioctls below write it, under one KD mutex. No IRQ/NMI callback, exported
 * address, timer, workqueue or remote write exists. Summation happens only in
 * the stopped-worker REPORT ioctl. Each counter occupies its own cacheline.
 * Changing this file invalidates audit.json and all generated manifests. */
#include <linux/module.h>
#include <linux/miscdevice.h>
#include <linux/fs.h>
#include <linux/percpu.h>
#include <linux/uaccess.h>
#include <linux/objtool.h>
#include "kd_owned_mutex_direct.h"

static struct kd_mutex lock __aligned(64);
static DEFINE_PER_CPU_ALIGNED(u64, kd_origin_test_counter);
static atomic_t running = ATOMIC_INIT(0);
static unsigned long operations, errors;
extern char kd_origin_cpu_entry[], kd_origin_counter_entry[];

static noinline void cpu_body(unsigned int *observed)
{
	struct kd_owned_mutex_outer_cookie cookie;

	KD_OWNED_MUTEX_OUTER_LOCK(&lock, cookie,
		".globl kd_origin_cpu_entry\nkd_origin_cpu_entry:\n\t" ANNOTATE_NOENDBR);
	*observed = this_cpu_read(cpu_number);
	KD_OWNED_MUTEX_OUTER_UNLOCK(&lock, cookie);
}

static noinline void counter_body(unsigned int *observed)
{
	struct kd_owned_mutex_outer_cookie cookie;

	KD_OWNED_MUTEX_OUTER_LOCK(&lock, cookie,
		".globl kd_origin_counter_entry\nkd_origin_counter_entry:\n\t" ANNOTATE_NOENDBR);
	*observed = this_cpu_read(cpu_number);
	this_cpu_inc(kd_origin_test_counter);
	KD_OWNED_MUTEX_OUTER_UNLOCK(&lock, cookie);
}

static long origin_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	u64 total = 0;
	unsigned long i, failures = 0, count = arg;
	unsigned int observed, cpu;

	(void)file;
	if (cmd == 0x4700) {
		int ret = kd_owned_mutex_prepare(&lock, (unsigned long)kd_origin_cpu_entry - KD_CABI_CALL_STUB_SIZE, 4);
		return ret ? ret : kd_owned_mutex_prepare(&lock, (unsigned long)kd_origin_counter_entry - KD_CABI_CALL_STUB_SIZE, 4);
	}
	if (cmd == 0x4701 || cmd == 0x4702) {
		if (!count || count > 10000000)
			return -EINVAL;
		atomic_inc(&running);
		for (i = 0; i < count; i++) {
			migrate_disable();
			cpu = raw_smp_processor_id();
			if (cmd == 0x4701)
				cpu_body(&observed);
			else
				counter_body(&observed);
			failures += observed != cpu;
			migrate_enable();
			cond_resched();
		}
		/* Diagnostic totals are outside the translated body. */
		__sync_fetch_and_add(&operations, count);
		__sync_fetch_and_add(&errors, failures);
		atomic_dec(&running);
		return failures ? -EIO : 0;
	}
	if (cmd == 0x4703) {
		u64 result[4];

		if (atomic_read(&running) || !kd_owned_mutex_is_idle(&lock))
			return -EBUSY;
		for_each_possible_cpu(cpu)
			total += per_cpu(kd_origin_test_counter, cpu);
		result[0] = operations; result[1] = errors; result[2] = total; result[3] = 1;
		return copy_to_user((void __user *)arg, result, sizeof(result)) ? -EFAULT : 0;
	}
	return -ENOTTY;
}

static const struct file_operations ops = { .owner = THIS_MODULE, .unlocked_ioctl = origin_ioctl };
static struct miscdevice device = { .minor = MISC_DYNAMIC_MINOR, .name = "kd_origin_gs", .fops = &ops, .mode = 0600 };
static int __init origin_init(void)
{
	int ret;

	kd_mutex_init(&lock);
	ret = misc_register(&device);
	if (ret)
		return ret;
	return ret;
}
static void __exit origin_exit(void) { misc_deregister(&device); }
module_init(origin_init);
module_exit(origin_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Audited task-only origin GS mutex test");
