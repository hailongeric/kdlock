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
	/* Pass the original caller's continuation and the exact rwsem identity.
	 * Queue publication is not a reader-drain result. The selected executor
	 * closes and drains its own phase before any caller body executes. */
	if (!READ_ONCE(sem->prepared_writes)) {
		(kd_down_write)(sem);
		return;
	}
	kd_mutex_rwsem_lock_clobber_v1(sem, sp, ip, bp);
}
EXPORT_SYMBOL_GPL(kd_rwsem_down_write_clobber_v1);

__attribute__((noipa)) noinline notrace void
kd_rwsem_up_write_clobber_v1(struct kd_rwsem *sem, unsigned long sp,
                            unsigned long ip, unsigned long bp)
{
	/* The generated control handles this endpoint without entering the C
	 * helper. Ordinary execution preserves the same public release route. */
	(void)sp;
	(void)ip;
	(void)bp;
	(kd_up_write)(sem);
}
EXPORT_SYMBOL_GPL(kd_rwsem_up_write_clobber_v1);
