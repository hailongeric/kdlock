// SPDX-License-Identifier: GPL-2.0
/* A benchmark-scoped replacement provider: the selected original lock word
 * belongs exclusively to TCLock for the whole session. There is no kdlock
 * shadow lock, translation registry, pt_regs packet, JIT or daemon here.
 * Keep the source workload loaded until this provider has drained/unloaded.
 */
#include <linux/module.h>
#include <linux/moduleparam.h>
#include "compat.h"

static unsigned long target_lock;
/* Direct workloads depend on this module, so bind only after loading the
 * workload. The runner writes while drained, before starting any workers,
 * and clears the address before unloading its storage. Never read it in the
 * lock hot path: komb_spin_lock/unlock are called directly. */
static int target_set(const char *value, const struct kernel_param *param)
{
    unsigned long address;
    int result = kstrtoul(value, 0, &address);
    if (result)
        return result;
    if (address % __alignof__(raw_spinlock_t))
        return -EINVAL;
    if (!tc_contexts_idle() || (target_lock &&
        atomic_read(&((struct qspinlock *)target_lock)->val)))
        return -EBUSY;
    WRITE_ONCE(*(unsigned long *)param->arg, address);
    return 0;
}
static const struct kernel_param_ops target_ops = {
    .set = target_set, .get = param_get_ulong,
};
module_param_cb(target_lock, &target_ops, &target_lock, 0644);
MODULE_PARM_DESC(target_lock, "Exclusive benchmark lock address from SC_LAYOUT");

/* Upstream in-kernel default; KD has its own measured bounded batch limit. */
long komb_batch_size = 1024;
#ifdef NUMA_AWARE
MODULE_INFO(spin_numa, "1");
#else
MODULE_INFO(spin_numa, "0");
#endif
module_param(komb_batch_size, long, 0444);

static int idle_get(char *buffer, const struct kernel_param *param)
{
    struct qspinlock *lock = (void *)target_lock;
    return scnprintf(buffer, PAGE_SIZE, "%d\n",
                     (!lock || !atomic_read(&lock->val)) && tc_contexts_idle());
}
static const struct kernel_param_ops idle_ops = { .get = idle_get };
module_param_cb(quiescent, &idle_ops, NULL, 0444);

static int __init tc_init(void)
{
    int result;
    BUILD_BUG_ON(offsetof(raw_spinlock_t, raw_lock) != 0);
    if (komb_batch_size < 1 || komb_batch_size > 262144)
        return -EINVAL;
    result = komb_init();
    if (result)
        return result;
    return result;
}

static void __exit tc_exit(void)
{
    /* Runner joins all workers and checks target lock/contexts before rmmod.
     * This is the same controlled external no-new-callers boundary as kdlock. */
    WARN_ON_ONCE(!tc_contexts_idle());
    komb_free();
}
module_init(tc_init);
module_exit(tc_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TCLock native stack-delegation benchmark backend");
