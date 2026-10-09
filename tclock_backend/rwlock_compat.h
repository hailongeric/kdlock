/* SPDX-License-Identifier: GPL-2.0 */
#ifndef TCLOCK_RWLOCK_COMPAT_H
#define TCLOCK_RWLOCK_COMPAT_H
#include <linux/module.h>
#include <linux/preempt.h>
#include <linux/spinlock.h>
#include "include/rwlock/komb_rwlock.h"

int tc_rw_contexts_idle(void);
void kombrw_spin_lock_slowpath(struct qspinlock *lock);
void kombrw_spin_lock(struct qspinlock *lock, int state);
void kombrw_spin_unlock(struct qspinlock *lock);
#endif
