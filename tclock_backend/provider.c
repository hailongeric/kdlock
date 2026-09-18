// SPDX-License-Identifier: GPL-2.0
/* A benchmark-scoped replacement provider: the selected original lock word
 * belongs exclusively to TCLock for the whole session. There is no kdlock
 * shadow lock, translation registry, pt_regs packet, JIT or daemon here.
 * Keep the source workload loaded until this provider has drained/unloaded.
 */
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/kd_spin_hooks.h>
#include "compat.h"

static unsigned long target_lock;
module_param(target_lock, ulong, 0444);
MODULE_PARM_DESC(target_lock, "Exclusive benchmark lock address from SC_LAYOUT");

/* Upstream in-kernel default; also matches kdlock's batch limit. */
long komb_batch_size = 1024;
module_param(komb_batch_size, long, 0444);
DEFINE_PER_CPU(u64, tc_delegated);
DEFINE_PER_CPU(u64, tc_completed);
DEFINE_PER_CPU(u64, tc_batches);

static int counts_get(char *buffer, const struct kernel_param *param)
{
    u64 total = 0;
    int cpu;
    u64 __percpu *counter = param->arg;
    for_each_possible_cpu(cpu)
        total += READ_ONCE(*per_cpu_ptr(counter, cpu));
    return scnprintf(buffer, PAGE_SIZE, "%llu\n", (unsigned long long)total);
}
static const struct kernel_param_ops counts_ops = { .get = counts_get };
module_param_cb(delegated, &counts_ops, &tc_delegated, 0444);
module_param_cb(completed, &counts_ops, &tc_completed, 0444);
module_param_cb(batches, &counts_ops, &tc_batches, 0444);

static int idle_get(char *buffer, const struct kernel_param *param)
{
    struct qspinlock *lock = (void *)target_lock;
    return scnprintf(buffer, PAGE_SIZE, "%d\n",
                     !atomic_read(&lock->val) && tc_contexts_idle());
}
static const struct kernel_param_ops idle_ops = { .get = idle_get };
module_param_cb(quiescent, &idle_ops, NULL, 0444);

static int tc_select(void)
{
    /* The combined ordinary-spin hook routes by lock identity. No INT3 hook. */
    return 0;
}

static void tc_lock(raw_spinlock_t *lock, unsigned long sp, unsigned long ip)
{
    if ((unsigned long)lock != target_lock) {
        __raw_spin_lock(lock);
        return;
    }
    /* The upstream raw algorithm expects caller-owned preemption exclusion.
     * Each physical waiter balances this only after resuming its own stack. */
    preempt_disable();
    komb_spin_lock((struct qspinlock *)lock);
}

static void tc_unlock(raw_spinlock_t *lock, unsigned long sp, unsigned long ip)
{
    if ((unsigned long)lock != target_lock) {
        __raw_spin_unlock(lock);
        return;
    }
    komb_spin_unlock((struct qspinlock *)lock);
    preempt_enable();
}

static void tc_clobber_lock(raw_spinlock_t *lock, unsigned long sp,
                            unsigned long ip, unsigned long bp)
{
    tc_lock(lock, sp, ip);
}
static void tc_clobber_unlock(raw_spinlock_t *lock, unsigned long sp,
                              unsigned long ip, unsigned long bp)
{
    tc_unlock(lock, sp, ip);
}

static int __init tc_init(void)
{
    int result;
    BUILD_BUG_ON(offsetof(raw_spinlock_t, raw_lock) != 0);
    if (!target_lock || target_lock % __alignof__(raw_spinlock_t) ||
        komb_batch_size < 1 || komb_batch_size > 262144)
        return -EINVAL;
    result = komb_init();
    if (result)
        return result;
    result = kd_spin_static_install_clobber_v1(tc_select, tc_lock, tc_unlock,
                                               tc_clobber_lock, tc_clobber_unlock);
    if (result)
        komb_free();
    return result;
}

static void __exit tc_exit(void)
{
    /* Runner joins all workers and checks target lock/contexts before rmmod.
     * This is the same controlled external no-new-callers boundary as kdlock. */
    WARN_ON_ONCE(!tc_contexts_idle());
    kd_spin_static_remove();
    komb_free();
}
module_init(tc_init);
module_exit(tc_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TCLock native stack-delegation benchmark backend");
