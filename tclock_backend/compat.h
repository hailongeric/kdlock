/* SPDX-License-Identifier: GPL-2.0 */
#ifndef TCLOCK_BACKEND_COMPAT_H
#define TCLOCK_BACKEND_COMPAT_H

/* Use the upstream in-kernel polling path. KERNEL_SYNCSTRESS's schedule() on
 * per-CPU borrowed stacks is not appropriate for the recovery kernel. */
#include <linux/kernel.h>
#include <linux/percpu.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/errno.h>
#include "include/lib/combiner.h"
#include "include/spinlock/komb.h"

#define LOCK_START_TIMING_PER_CPU(name)
#define LOCK_END_TIMING_PER_CPU(name)

DECLARE_PER_CPU(u64, tc_delegated);
DECLARE_PER_CPU(u64, tc_completed);
DECLARE_PER_CPU(u64, tc_batches);
int tc_contexts_idle(void);
int __komb_spin_lock_slowpath(struct qspinlock *lock);
void komb_spin_lock_slowpath(struct qspinlock *lock);
u64 *get_shadow_stack_ptr(void);
u64 *get_komb_rsp_ptr(void);
#endif
