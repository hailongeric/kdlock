/* SPDX-License-Identifier: GPL-2.0 */
#ifndef TCLOCK_BACKEND_COMPAT_H
#define TCLOCK_BACKEND_COMPAT_H

/* Match the pinned upstream RCUHT scheduling branch. */
#include <linux/kernel.h>
#include <linux/percpu.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/errno.h>
#include "include/lib/combiner.h"
#include "include/spinlock/komb.h"

#define LOCK_START_TIMING_PER_CPU(name)
#define LOCK_END_TIMING_PER_CPU(name)

int tc_contexts_idle(void);
void komb_spin_lock_slowpath(struct qspinlock *lock);
#endif
