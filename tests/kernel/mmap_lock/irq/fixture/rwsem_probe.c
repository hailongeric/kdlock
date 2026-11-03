// SPDX-License-Identifier: GPL-2.0
#include "probe.h"
#include "kd_mmap_rwsem.h"

struct kd_mmap_rwsem *kd_irq_inject;
unsigned int kd_irq_injections;

static long publish_reader(atomic_long_t *readers)
{
	long count = atomic_long_inc_return(readers);
	struct kd_mmap_rwsem *sem = READ_ONCE(kd_irq_inject);

	/* Deterministic admission interleaving, only for the rollback case. This
	 * creates exactly the writer's 0 -> -1 reservation after publication and
	 * before the reader recheck. It never impersonates an acquired writer. */
	if (sem && readers == &sem->readers) {
		BUG_ON(atomic_long_cmpxchg(&sem->admission, 0, -1) != 0);
		kd_irq_injections++;
	}
	return count;
}

#define atomic_long_inc_return(readers) publish_reader(readers)
#include "kd_mmap_rwsem.c"
