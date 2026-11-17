/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Whole-kernel switch (CONFIG_KDLOCK_ALL): struct mutex.
 *
 * With the switch, struct mutex (linux/mutex_types.h) is
 *
 *	struct mutex { struct kd_mutex kd; };
 *
 * 32 bytes as the native one, and kernel/locking/mutex.c is not built;
 * kernel/kd_all.c defines the native function names for callers that take
 * their address. Included by linux/mutex.h after the native declarations
 * and before its lock guard classes.
 *
 * The native static initialiser leaves the same bytes as the kd one (zero
 * words, an empty list at offset 16), but it names native fields, so it is
 * redefined. A code path that reads a native field (->owner, ->wait_list)
 * no longer compiles; that is how the build finds every user that does not
 * go through the lock API.
 *
 * struct ww_mutex keeps its definition (a struct mutex followed by the
 * context pointer, the layout of struct kd_ww_mutex); its operations are
 * the native function names, defined in kernel/kd_all.c on kd_ww_mutex.
 */
#ifndef _KDLOCK_KD_ALL_MUTEX_H
#define _KDLOCK_KD_ALL_MUTEX_H

#include <kdlock/kd_api.h>

#undef __MUTEX_INITIALIZER
#define __MUTEX_INITIALIZER(lockname)					\
	{ .kd = __KD_MUTEX_INITIALIZER((lockname).kd) }

#ifndef KD_ALL_NO_MAP

static __always_inline struct kd_mutex *__kd_all_mx(struct mutex *m)
{
	return &m->kd;
}

#undef mutex_init
#define mutex_init(m)			kd_mutex_init(__kd_all_mx(m))
#define mutex_lock(m)			kd_mutex_lock(__kd_all_mx(m))
#define mutex_lock_interruptible(m)	kd_mutex_lock_interruptible(__kd_all_mx(m))
#define mutex_lock_killable(m)		kd_mutex_lock_killable(__kd_all_mx(m))
#define mutex_lock_io(m)		kd_mutex_lock_io(__kd_all_mx(m))
#define mutex_trylock(m)		kd_mutex_trylock(__kd_all_mx(m))
#define mutex_unlock(m)			kd_mutex_unlock(__kd_all_mx(m))
#define mutex_is_locked(m)		kd_mutex_is_locked(__kd_all_mx(m))

/*
 * The _nested and _nest_lock forms of linux/mutex.h already expand to the
 * names above (no lockdep). mutex_get_owner() and atomic_dec_and_mutex_lock()
 * stay functions (kernel/kd_all.c).
 */

#endif /* !KD_ALL_NO_MAP */
#endif /* _KDLOCK_KD_ALL_MUTEX_H */
