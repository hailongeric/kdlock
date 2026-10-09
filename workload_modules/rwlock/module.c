// SPDX-License-Identifier: GPL-2.0
/* One payload for native Linux rwlocks and the KD JIT writer protocol. */
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include "api.h"

#ifdef RW_KDLOCK
#include "kd_rwlock.h"
static DEFINE_KD_RWLOCK(test_lock);
extern char rw_test_entry[];
#define READ_LOCK() kd_read_lock(&test_lock)
#define READ_UNLOCK() kd_read_unlock(&test_lock)
#define WRITE_LOCK() KD_RWLOCK_DIRECT_WRITE_LOCK(&test_lock, \
	kd_rwlock_direct_cookie, ".globl rw_test_entry\nrw_test_entry:\n\t" ANNOTATE_NOENDBR)
#define WRITE_UNLOCK() KD_RWLOCK_DIRECT_WRITE_UNLOCK(&test_lock, kd_rwlock_direct_cookie)
#else
static DEFINE_RWLOCK(test_lock);
#define READ_LOCK() read_lock(&test_lock)
#define READ_UNLOCK() read_unlock(&test_lock)
#define WRITE_LOCK() write_lock(&test_lock)
#define WRITE_UNLOCK() write_unlock(&test_lock)
#endif

static u64 values[8] __aligned(64);
static atomic_t control = ATOMIC_INIT(0);
static atomic_t readers = ATOMIC_INIT(0);
static atomic_t writers = ATOMIC_INIT(0);
static atomic_t failures = ATOMIC_INIT(0);
static atomic_t max_readers = ATOMIC_INIT(0);

static noinline void rw_read_body(void)
{
	u64 first;
	int count, peak, i;

	READ_LOCK();
	count = atomic_inc_return(&readers);
	peak = atomic_read(&max_readers);
	while (count > peak && !atomic_try_cmpxchg(&max_readers, &peak, count))
		;
	if (atomic_read(&writers))
		atomic_inc(&failures);
	first = READ_ONCE(values[0]);
	for (i = 1; i < ARRAY_SIZE(values); i++) {
		if (first != READ_ONCE(values[i]))
			atomic_inc(&failures);
		cpu_relax();
	}
	if (atomic_read(&writers))
		atomic_inc(&failures);
	atomic_dec(&readers);
	READ_UNLOCK();
}

static __attribute__((noipa)) void rw_write_body(void)
{
	WRITE_LOCK();
	if (atomic_inc_return(&writers) != 1 || atomic_read(&readers))
		atomic_inc(&failures);
	/* Fixed straight-line stores also make corruption visible to readers. */
	WRITE_ONCE(values[0], READ_ONCE(values[0]) + 1);
	WRITE_ONCE(values[1], READ_ONCE(values[1]) + 1);
	WRITE_ONCE(values[2], READ_ONCE(values[2]) + 1);
	WRITE_ONCE(values[3], READ_ONCE(values[3]) + 1);
	WRITE_ONCE(values[4], READ_ONCE(values[4]) + 1);
	WRITE_ONCE(values[5], READ_ONCE(values[5]) + 1);
	WRITE_ONCE(values[6], READ_ONCE(values[6]) + 1);
	WRITE_ONCE(values[7], READ_ONCE(values[7]) + 1);
	atomic_dec(&writers);
	WRITE_UNLOCK();
}

static long rw_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct rw_test_snapshot snapshot = { 0 };
	struct rw_test_run run;
	unsigned int before_preempt, i;
	bool before_irqs;
	int ret = 0;

	(void)file;
	if (cmd == RW_TEST_RUN) {
		if (copy_from_user(&run, user, sizeof(run)))
			return -EFAULT;
		if (!run.iterations || run.iterations > 10000000 || run.reserved ||
		    run.write_every > 10000 || run.worker > 1024)
			return -EINVAL;
		if (!atomic_add_unless(&control, 1, -1))
			return -EBUSY;
		before_preempt = preempt_count();
		before_irqs = irqs_disabled();
		run.reads = run.writes = 0;
		for (i = 0; i < run.iterations; i++) {
			if (run.write_every && (i + run.worker) % run.write_every == 0) {
				rw_write_body();
				run.writes++;
			} else {
				rw_read_body();
				run.reads++;
			}
			if ((i & 255) == 0)
				cond_resched();
		}
		if (preempt_count() != before_preempt || irqs_disabled() != before_irqs)
			atomic_inc(&failures);
		(void)atomic_dec_return_release(&control);
		return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
	}
	if (cmd != RW_TEST_SNAPSHOT && cmd != RW_TEST_PREPARE)
		return -ENOTTY;
	if (atomic_cmpxchg_acquire(&control, 0, -1))
		return -EBUSY;
	if (cmd == RW_TEST_PREPARE) {
#ifdef RW_KDLOCK
		ret = kd_rwlock_prepare(&test_lock, (unsigned long)rw_test_entry,
					KD_ENTRY_ABI_RWLOCK_CLOBBER_V1);
#endif
	} else {
		for (i = 0; i < ARRAY_SIZE(values); i++)
			snapshot.values[i] = values[i];
		snapshot.failures = atomic_read(&failures);
		snapshot.max_readers = atomic_read(&max_readers);
		snapshot.active = atomic_read(&readers) + atomic_read(&writers);
#ifdef RW_KDLOCK
		snapshot.gate_address = (unsigned long)&test_lock.gate;
		snapshot.entry = (unsigned long)rw_test_entry;
		snapshot.cnts = kd_rwlock_state(&test_lock);
		snapshot.gate = atomic_read(&test_lock.gate.val);
#endif
		ret = copy_to_user(user, &snapshot, sizeof(snapshot)) ? -EFAULT : 0;
	}
	atomic_set_release(&control, 0);
	return ret;
}

static const struct file_operations rw_fops = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = rw_ioctl,
};
static struct miscdevice rw_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_rwlock_test", .fops = &rw_fops,
	.mode = 0600,
};
static int __init rw_init(void)
{
	BUILD_BUG_ON(sizeof(struct rw_test_run) != 32);
	BUILD_BUG_ON(sizeof(struct rw_test_snapshot) != 104);
	return misc_register(&rw_device);
}
static void __exit rw_exit(void) { misc_deregister(&rw_device); }
module_init(rw_init);
module_exit(rw_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Concurrent reader/writer and JIT writer correctness workload");
