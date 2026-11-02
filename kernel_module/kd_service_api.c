// SPDX-License-Identifier: GPL-2.0
/* Integer public controls. Conventional C acquisitions remain separate. */
#include <linux/module.h>
#include <linux/sched.h>
#include "kd_mutex_direct.h"
#include "kd_service_api.h"

__attribute__((noipa)) noinline notrace int
kd_mutex_lock_interruptible_clobber_v1(struct kd_mutex *lock,
	unsigned long sp, unsigned long ip, unsigned long bp)
{
	return kd_service_capture(lock, KD_ADMISSION_MUTEX, TASK_INTERRUPTIBLE,
				  sp, ip, bp);
}
EXPORT_SYMBOL_GPL(kd_mutex_lock_interruptible_clobber_v1);

__attribute__((noipa)) noinline notrace int
kd_mutex_lock_killable_clobber_v1(struct kd_mutex *lock,
	unsigned long sp, unsigned long ip, unsigned long bp)
{
	return kd_service_capture(lock, KD_ADMISSION_MUTEX, TASK_KILLABLE,
				  sp, ip, bp);
}
EXPORT_SYMBOL_GPL(kd_mutex_lock_killable_clobber_v1);
