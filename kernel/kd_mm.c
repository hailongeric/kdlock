// SPDX-License-Identifier: GPL-2.0
/*
 * Backend choice for the mm_struct mmap lock (CONFIG_KDLOCK_MM); see
 * include/kdlock/kd_mm_types.h.
 *
 * kd_mm (core parameter, 0644): the backend a new mm gets. 0 native
 * rw_semaphore (default), 1 kdlock rwsem. Changing it affects only mms
 * created afterwards, so a native and a kdlock run can follow each other
 * within one boot by starting new processes.
 */
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/moduleparam.h>
#include <kdlock/kd_mm.h>
#include "kd_internal.h"

static bool kd_mm __read_mostly;
core_param(kd_mm, kd_mm, bool, 0644);

/* Called for every new mm before anybody else can see it. */
void kd_mm_init(struct kd_mm_lock *l)
{
	l->use_kd = READ_ONCE(kd_mm);
	if (l->use_kd)
		kd_rwsem_init(&l->kd);
	else
		init_rwsem(&l->native);
}
EXPORT_SYMBOL(kd_mm_init);

/* The mm is being freed: its lock must be idle. */
void kd_mm_destroy(struct kd_mm_lock *l)
{
	if (l->use_kd)
		WARN_ON_ONCE(atomic_long_read(&l->kd.count) ||
			     atomic_read(&l->kd.m.q.val) ||
			     !list_empty(&l->kd.m.waiters));
}
EXPORT_SYMBOL(kd_mm_destroy);
