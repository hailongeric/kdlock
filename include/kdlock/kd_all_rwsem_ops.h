/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Whole-kernel switch (CONFIG_KDLOCK_ALL): struct rw_semaphore operations.
 *
 * Included by linux/rwsem.h after the native declarations and before its
 * lock guard classes. Writers use the delegable entries; readers, the
 * trylocks and downgrade_write() always run on the calling task. The
 * _nested, _nest_lock and _non_owner forms at the end of linux/rwsem.h
 * expand to these names (no lockdep; a kd rwsem records no reader owner).
 */
#ifndef _KDLOCK_KD_ALL_RWSEM_OPS_H
#define _KDLOCK_KD_ALL_RWSEM_OPS_H

#ifndef KD_ALL_NO_MAP

static __always_inline struct kd_rwsem *__kd_all_rs(struct rw_semaphore *sem)
{
	return &sem->kd;
}

#define down_read(sem)			kd_down_read(__kd_all_rs(sem))
#define down_read_interruptible(sem)	kd_down_read_interruptible(__kd_all_rs(sem))
#define down_read_killable(sem)		kd_down_read_killable(__kd_all_rs(sem))
#define down_read_trylock(sem)		kd_down_read_trylock(__kd_all_rs(sem))
#define up_read(sem)			kd_up_read(__kd_all_rs(sem))
#define down_write(sem)			kd_down_write(__kd_all_rs(sem))
#define down_write_killable(sem)	kd_down_write_killable(__kd_all_rs(sem))
#define down_write_trylock(sem)		kd_down_write_trylock(__kd_all_rs(sem))
#define up_write(sem)			kd_up_write(__kd_all_rs(sem))
/* linux/rwsem.h declares downgrade_write() later only without the switch. */
#define downgrade_write(sem)		kd_downgrade_write(__kd_all_rs(sem))

#endif /* !KD_ALL_NO_MAP */
#endif /* _KDLOCK_KD_ALL_RWSEM_OPS_H */
