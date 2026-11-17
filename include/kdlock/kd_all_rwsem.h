/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Whole-kernel switch (CONFIG_KDLOCK_ALL): struct rw_semaphore, type part.
 *
 * Replaces the native !PREEMPT_RT block of linux/rwsem.h (the structure,
 * its initialisers and the state tests that read native fields):
 *
 *	struct rw_semaphore { struct kd_rwsem kd; };
 *
 * 40 bytes as the native one. kernel/locking/rwsem.c is not built;
 * kernel/kd_all.c defines the native function names. The operations are
 * mapped by kd_all_rwsem_ops.h, which linux/rwsem.h includes after the
 * native declarations and before its lock guard classes.
 *
 * rwsem_owner() and is_rwsem_reader_owned() have no counterpart: readers
 * and write holders record no owner. Their one user in this configuration,
 * the hung task detector's blocker report, is configured out
 * (KDLOCK_ALL depends on !DETECT_HUNG_TASK_BLOCKER).
 */
#ifndef _KDLOCK_KD_ALL_RWSEM_H
#define _KDLOCK_KD_ALL_RWSEM_H

#include <linux/bug.h>
#include <kdlock/kd_api.h>

context_lock_struct(rw_semaphore) {
	struct kd_rwsem	kd;
};

#define __RWSEM_INITIALIZER(name)					\
	{ .kd = __KD_RWSEM_INITIALIZER((name).kd) }

#define DECLARE_RWSEM(name) \
	struct rw_semaphore name = __RWSEM_INITIALIZER(name)

/* Kept for init_rwsem() users that pass a lockdep key; kernel/kd_all.c. */
extern void __init_rwsem(struct rw_semaphore *sem, const char *name,
			 struct lock_class_key *key);

#define init_rwsem(sem)		kd_rwsem_init(&(sem)->kd)

static inline int rwsem_is_locked(struct rw_semaphore *sem)
{
	return kd_rwsem_is_locked(&sem->kd);
}

static inline void rwsem_assert_held_nolockdep(const struct rw_semaphore *sem)
	__assumes_ctx_lock(sem)
{
	WARN_ON(!kd_rwsem_is_locked((struct kd_rwsem *)&sem->kd));
}

static inline void rwsem_assert_held_write_nolockdep(const struct rw_semaphore *sem)
	__assumes_ctx_lock(sem)
{
	WARN_ON(!kd_rwsem_is_write_locked((struct kd_rwsem *)&sem->kd));
}

static inline int rwsem_is_contended(struct rw_semaphore *sem)
{
	return kd_rwsem_is_contended(&sem->kd);
}

#endif /* _KDLOCK_KD_ALL_RWSEM_H */
