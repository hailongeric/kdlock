// SPDX-License-Identifier: GPL-2.0
/* Public continuation capture; the generated MM backend never links this file. */
#include <linux/module.h>
#include "kd_rwsem_api.h"

int kd_rwsem_prepare(struct kd_rwsem *sem, unsigned long ip, unsigned int abi)
{
	int ret;

	BUILD_BUG_ON(sizeof(struct kd_rwsem) != 320);
	BUILD_BUG_ON(offsetof(struct kd_rwsem, readers) != 64);
	BUILD_BUG_ON(offsetof(struct kd_rwsem, admission) != 128);
	BUILD_BUG_ON(offsetof(struct kd_rwsem, prepared_writes) != 32);
	BUILD_BUG_ON(offsetof(struct kd_rwsem, phase_wait) != 192);
	BUILD_BUG_ON(offsetof(struct kd_rwsem, reader_drain) != 256);
	BUILD_BUG_ON(offsetof(struct kd_rwsem, reader_osq) != 280);
	if (!sem || !ip || abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1)
		return -EINVAL;
	/* The caller must already have stopped/joined users. This catches live
	 * objects but is not a concurrent admission or lifetime barrier. */
	if (!kd_rwsem_is_idle(sem))
		return -EBUSY;
	ret = kd_mutex_prepare(&sem->gate, ip, abi);
	if (!ret)
		WRITE_ONCE(sem->prepared_writes, 1);
	return ret;
}
EXPORT_SYMBOL_GPL(kd_rwsem_prepare);

__attribute__((noipa)) noinline notrace void
kd_rwsem_down_write_clobber_v1(struct kd_rwsem *sem, unsigned long sp,
                              unsigned long ip, unsigned long bp)
{
	/* This is the original task before publication. Reader drainage may
	 * sleep here; the mutex entry receives the caller's actual continuation,
	 * never a continuation inside this returning helper. */
	if (!READ_ONCE(sem->prepared_writes)) {
		(kd_down_write)(sem);
		return;
	}
	kd_rwsem_delegate_enter(sem);
	kd_mutex_direct_lock_clobber_v1(&sem->gate, sp, ip, bp);
}
EXPORT_SYMBOL_GPL(kd_rwsem_down_write_clobber_v1);
