// SPDX-License-Identifier: GPL-2.0
/*
 * Backend choice for switchable lock objects (CONFIG_KDLOCK_API); see
 * include/kdlock/kd_sw_spin.h.
 *
 * kd_api (core parameter, 0644): bit mask of the lock families whose new
 * switchable objects use kdlock: 1 spinlock_t, 2 rwlock_t, 4 mutex,
 * 8 rw_semaphore. Default 0 (all native). Each object reads it once, in its
 * init call, so a change affects only objects initialised afterwards
 * (new files tables, open files, pipes, lock contexts, xattr sets).
 *
 * kd_uts (core parameter, boot only): the one statically initialised
 * switchable object, uts_sem, cannot follow kd_api at run time because
 * users may hold it at any moment. With kd_uts=1 on the kernel command
 * line it is converted to kdlock below, before any user task exists.
 */
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/moduleparam.h>
#include <linux/utsname.h>
#include <kdlock/kd_sw_spin.h>
#include "kd_internal.h"

unsigned int kd_api __read_mostly;
EXPORT_SYMBOL(kd_api);
core_param(kd_api, kd_api, uint, 0644);

static bool kd_uts;
core_param(kd_uts, kd_uts, bool, 0444);

/*
 * Initcalls run before the first user task, and nothing in the kernel
 * takes uts_sem on its own before then (its users are system calls,
 * sysctl, namespace cloning and core dumps).
 */
static int __init kd_sw_uts_init(void)
{
	if (!kd_uts)
		return 0;
	if (WARN_ON(rwsem_is_locked(&uts_sem.native)))
		return 0;
	kd_rwsem_init(&uts_sem.kd);
	uts_sem.use_kd = true;
	pr_info("kdlock: uts_sem uses kdlock\n");
	return 0;
}
core_initcall(kd_sw_uts_init);
