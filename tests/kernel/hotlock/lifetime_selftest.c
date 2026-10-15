/* SPDX-License-Identifier: GPL-2.0 */
/* Real provider calls with a held KD object while the local hash table fills, and an
 * owned mutex sleeper forced to another CPU after admission returned.
 * This is an ownership/migration test, not an actual JIT body witness. */
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/kthread.h>
#include <linux/cpu.h>
#include "kd_lock.h"
#include "kd_owned_mutex_internal.h"
#include "kd_spinlock.h"

static bool hotlock_lifetime_selftest;
module_param(hotlock_lifetime_selftest, bool, 0444);
static struct {
 struct kd_mutex mutex;
 struct completion entered, done;
 int before_cpu, after_cpu;
 bool balanced;
} kd_hot_test;

static int kd_hot_test_waiter(void *unused)
{
 unsigned int pins = preempt_count();
 (void)unused;
 kd_hot_test.before_cpu = raw_smp_processor_id();
 preempt_disable();
 kd_hotlock_owned_mutex_entry();
 kd_hotlock_record_owned_mutex_pinned((unsigned long)&kd_hot_test.mutex);
 preempt_enable();
 kd_hot_test.balanced = pins == preempt_count();
 complete(&kd_hot_test.entered);
 kd_owned_mutex_lock_self(&kd_hot_test.mutex);
 kd_hot_test.after_cpu = raw_smp_processor_id();
 kd_hot_test.balanced &= pins == preempt_count();
 kd_owned_mutex_release(&kd_hot_test.mutex);
 complete(&kd_hot_test.done);
 set_current_state(TASK_INTERRUPTIBLE);
 while (!kthread_should_stop()) {
  schedule();
  set_current_state(TASK_INTERRUPTIBLE);
 }
 __set_current_state(TASK_RUNNING);
 return 0;
}

int kd_hotlock_lifetime_check(void)
{
 kd_spinlock_t lock = KD_SPINLOCK_INITIALIZER;
 struct task_struct *worker;
 struct kd_hotlock_table *t;
 unsigned long address = (unsigned long)&lock;
 unsigned int i;
 int ret = 0;
 bool retained;
 if (!hotlock_lifetime_selftest) return 0;
 if (!cpu_online(1) || !cpu_online(2)) return -ENODEV;
 /* A cold root falls back to the same physical fast-owner record. */
 kd_spin_lock_abi(&lock, 0, 0, 0, KD_ENTRY_ABI_SPIN_CLOBBER_V1);
 /* This ownership probe has no peers. Explicitly simulate the CPU events;
  * real adaptive warmup is checked separately with contended workloads. */
 for (i = 0; i < 2 * KD_HOTLOCK_SPIN_MCS_INTERVAL; i++)
  kd_hotlock_record_spin_mcs_pinned();
 for (i = 0; i < KD_HOTLOCK_SPIN_SAMPLE_TARGET; i++) kd_hotlock_record_spin(address);
 t = &this_cpu_ptr(kd_hotlock_cpu)->table;
 if (!kd_hotlock_find(t, address)) ret = -EUCLEAN;
 /* Fill with distinct identities and try one more. A full exact table must
  * preserve the held lock's entry, its owner and the physical lock word. */
 for (i = 0; i < KD_HOTLOCK_ENTRIES; i++) kd_hotlock_record_spin(address + 64 * (1 + i));
 retained = kd_hotlock_find(t, address) != NULL;
 if (!retained || t->used != KD_HOTLOCK_ENTRIES ||
     kd_hotlock_find(t, address + 64 * KD_HOTLOCK_ENTRIES) ||
     kd_spin_debug_owner((void *)&lock) != (unsigned long)current || !lock.locked)
  ret = -EUCLEAN;
 pr_info("kd_hotlock role: type=spin address=%lx role=OWNER retained=%u full=%u owner=%d preparation=simulated_mcs\n",
         address, retained, t->used == KD_HOTLOCK_ENTRIES, current->pid);
 kd_spin_unlock(&lock);
 if (atomic_read(&lock.val)) ret = -EUCLEAN;
 pr_info("kd_hotlock role: type=spin address=%lx role=DONE word=%x\n", address, atomic_read(&lock.val));
 if (ret) return ret;
 kd_mutex_init(&kd_hot_test.mutex);
 init_completion(&kd_hot_test.entered);
 init_completion(&kd_hot_test.done);
 kd_owned_mutex_lock_self(&kd_hot_test.mutex);
 worker = kthread_create(kd_hot_test_waiter, NULL, "kd-hot-migrate");
 if (IS_ERR(worker)) {
  kd_owned_mutex_release(&kd_hot_test.mutex);
  return PTR_ERR(worker);
 }
 ret = set_cpus_allowed_ptr(worker, cpumask_of(1));
 wake_up_process(worker);
 if (!wait_for_completion_timeout(&kd_hot_test.entered, 5 * HZ)) ret = -ETIMEDOUT;
 /* Wait for the real uninterruptible mutex slowpath before moving affinity. */
 for (i = 0; i < 5000 && !(READ_ONCE(worker->__state) & TASK_UNINTERRUPTIBLE); i++) msleep(1);
 if (i == 5000) ret = -ETIMEDOUT;
 if (!ret) ret = set_cpus_allowed_ptr(worker, cpumask_of(2));
 kd_owned_mutex_release(&kd_hot_test.mutex);
 if (!wait_for_completion_timeout(&kd_hot_test.done, 5 * HZ)) ret = -ETIMEDOUT;
 kthread_stop(worker);
 if (!kd_hot_test.balanced || kd_hot_test.before_cpu != 1 || kd_hot_test.after_cpu != 2) ret = -EUCLEAN;
 pr_info("kd_hotlock mutex migration: before=%d after=%d balanced=%u ret=%d\n",
         kd_hot_test.before_cpu, kd_hot_test.after_cpu, kd_hot_test.balanced, ret);
 return ret;
}
