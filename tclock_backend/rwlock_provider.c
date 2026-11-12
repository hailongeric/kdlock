// SPDX-License-Identifier: GPL-2.0
/* Exclusive task-context rwlock backend. Caller pins across each read/write
 * pair. The target binding is inspected only at a joined, no-new-call boundary. */
#include "rwlock_compat.h"

static unsigned long target_lock;
long komb_batch_size = 1024;
module_param(komb_batch_size, long, 0444);
MODULE_INFO(rwlock_numa, "1");

static bool target_idle(void)
{
	struct komb_rwlock *lock = (void *)target_lock;
	return !lock || (!atomic_read(&lock->cnts) && !atomic_read(&lock->lock.val));
}

static int target_set(const char *value, const struct kernel_param *param)
{
	unsigned long address;
	int error = kstrtoul(value, 0, &address);
	if (error)
		return error;
	if (address % __alignof__(struct komb_rwlock))
		return -EINVAL;
	if (!target_idle() || !tc_rw_contexts_idle())
		return -EBUSY;
	WRITE_ONCE(*(unsigned long *)param->arg, address);
	return 0;
}
static const struct kernel_param_ops target_ops = {
	.set = target_set, .get = param_get_ulong,
};
module_param_cb(target_lock, &target_ops, &target_lock, 0644);

static int idle_get(char *buffer, const struct kernel_param *param)
{
	return scnprintf(buffer, PAGE_SIZE, "%d\n", target_idle() && tc_rw_contexts_idle());
}
static const struct kernel_param_ops idle_ops = { .get = idle_get };
module_param_cb(quiescent, &idle_ops, NULL, 0444);

static int __init tc_rw_init(void)
{
	if (komb_batch_size < 1 || komb_batch_size > 1024 || nr_cpu_ids > 256)
		return -EINVAL;
	return komb_rwinit();
}
static void __exit tc_rw_exit(void)
{
	WARN_ON_ONCE(!target_idle() || !tc_rw_contexts_idle());
	komb_rwfree();
}
module_init(tc_rw_init);
module_exit(tc_rw_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TCLock upstream rwlock stack-delegation benchmark backend");
