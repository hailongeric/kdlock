/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_FAST_H
#define KD_SPIN_FAST_H
#include <linux/percpu.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include "kd_spin_type.h"

/* A sole task-context hold needs no frame/ticket. Only the pinned owner
 * writes this record. Native roots transfer their acquisition drain count
 * here; nested/IRQ nondelegating holds retain that count through unlock. */
struct kd_spin_fast_cpu {
 kd_spinlock_t *held;
 struct task_struct *owner;
 unsigned int nondelegated;
};
DECLARE_PER_CPU(struct kd_spin_fast_cpu, kd_spin_fast_cpu);
static __always_inline bool kd_spin_fast_active(void)
{
 struct kd_spin_fast_cpu *fast;
 if (!in_task() || !(preempt_count() & PREEMPT_MASK)) return false;
 fast = raw_cpu_ptr(&kd_spin_fast_cpu);
 return fast->held && fast->owner == current;
}
static __always_inline void kd_spin_fast_claim(kd_spinlock_t *lock)
{
 struct kd_spin_fast_cpu *fast = raw_cpu_ptr(&kd_spin_fast_cpu);
 BUG_ON(fast->held);
 fast->owner = current;
 WRITE_ONCE(fast->held, lock);
}
static __always_inline bool kd_spin_fast_unlock(raw_spinlock_t *lock)
{
 struct kd_spin_fast_cpu *fast;
 if (!kd_spin_fast_active()) return false;
 fast = raw_cpu_ptr(&kd_spin_fast_cpu);
 if (fast->held != (kd_spinlock_t *)lock) return false;
 /* Finish record accesses before releasing the pin. Preserve pending/tail. */
 smp_store_release(&fast->held->locked, 0);
 fast->owner = NULL;
 WRITE_ONCE(fast->held, NULL);
 preempt_enable();
 return true;
}
static inline bool kd_spin_fast_idle(void)
{
 int cpu;
 for_each_possible_cpu(cpu)
  if (READ_ONCE(per_cpu(kd_spin_fast_cpu, cpu).held) ||
      READ_ONCE(per_cpu(kd_spin_fast_cpu, cpu).nondelegated)) return false;
 return true;
}
#endif
