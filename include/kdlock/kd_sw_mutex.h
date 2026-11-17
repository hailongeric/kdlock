/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Switchable lock objects, struct mutex (CONFIG_KDLOCK_API). See
 * kd_sw_spin.h for the scheme. Included at the end of linux/mutex.h.
 */
#ifndef _KDLOCK_KD_SW_MUTEX_H
#define _KDLOCK_KD_SW_MUTEX_H

#include <kdlock/kd_api.h>

#ifndef KD_SW_MUTEX
#define KD_SW_MUTEX	0x4U
#endif
extern unsigned int kd_api;

struct kd_sw_mutex {
	union {
		struct mutex		native;
		struct kd_mutex		kd;
	};
	bool				use_kd;
};

#define __KD_SW_MUTEX_INITIALIZER(name)					\
	{ .native = __MUTEX_INITIALIZER((name).native), .use_kd = false }

static __always_inline void __kd_nat_mutex_init(struct mutex *m)
{
	mutex_init(m);
}

static __always_inline void kd_sw_mutex_init(struct kd_sw_mutex *m)
{
	m->use_kd = READ_ONCE(kd_api) & KD_SW_MUTEX;
	if (m->use_kd)
		kd_mutex_init(&m->kd);
	else
		mutex_init(&m->native);
}

static __always_inline void kd_sw_mutex_lock(struct kd_sw_mutex *m)
{
	if (m->use_kd)
		kd_mutex_lock(&m->kd);
	else
		mutex_lock(&m->native);
}

static __always_inline int __must_check kd_sw_mutex_lock_interruptible(struct kd_sw_mutex *m)
{
	if (m->use_kd)
		return kd_mutex_lock_interruptible(&m->kd);
	return mutex_lock_interruptible(&m->native);
}

static __always_inline int __must_check kd_sw_mutex_lock_killable(struct kd_sw_mutex *m)
{
	if (m->use_kd)
		return kd_mutex_lock_killable(&m->kd);
	return mutex_lock_killable(&m->native);
}

static __always_inline void kd_sw_mutex_lock_io(struct kd_sw_mutex *m)
{
	if (m->use_kd)
		kd_mutex_lock_io(&m->kd);
	else
		mutex_lock_io(&m->native);
}

static __always_inline int kd_sw_mutex_trylock(struct kd_sw_mutex *m)
{
	return m->use_kd ? kd_mutex_trylock(&m->kd) : mutex_trylock(&m->native);
}

static __always_inline void kd_sw_mutex_unlock(struct kd_sw_mutex *m)
{
	if (m->use_kd)
		kd_mutex_unlock(&m->kd);
	else
		mutex_unlock(&m->native);
}

static __always_inline bool kd_sw_mutex_is_locked(struct kd_sw_mutex *m)
{
	return m->use_kd ? kd_mutex_is_locked(&m->kd) : mutex_is_locked(&m->native);
}

static __always_inline unsigned long kd_sw_mutex_get_owner(struct kd_sw_mutex *m)
{
	return m->use_kd ? kd_mutex_get_owner(&m->kd) : mutex_get_owner(&m->native);
}

static __always_inline void kd_sw_mutex_destroy(struct kd_sw_mutex *m)
{
	if (!m->use_kd)
		mutex_destroy(&m->native);
}

#ifndef KD_SW_NO_DISPATCH

#define __KD_SW_MX(m, kdfn, natfn)	\
	_Generic((m), struct kd_sw_mutex *: kdfn, default: natfn)

#undef mutex_init
#define mutex_init(m)		__KD_SW_MX(m, kd_sw_mutex_init, __kd_nat_mutex_init)(m)
#define mutex_lock(m)		__KD_SW_MX(m, kd_sw_mutex_lock, mutex_lock)(m)
#define mutex_lock_interruptible(m)						\
	__KD_SW_MX(m, kd_sw_mutex_lock_interruptible, mutex_lock_interruptible)(m)
#define mutex_lock_killable(m)							\
	__KD_SW_MX(m, kd_sw_mutex_lock_killable, mutex_lock_killable)(m)
#define mutex_lock_io(m)	__KD_SW_MX(m, kd_sw_mutex_lock_io, mutex_lock_io)(m)
#define mutex_trylock(m)	__KD_SW_MX(m, kd_sw_mutex_trylock, mutex_trylock)(m)
#define mutex_unlock(m)		__KD_SW_MX(m, kd_sw_mutex_unlock, mutex_unlock)(m)
#define mutex_is_locked(m)	__KD_SW_MX(m, kd_sw_mutex_is_locked, mutex_is_locked)(m)
#define mutex_get_owner(m)	__KD_SW_MX(m, kd_sw_mutex_get_owner, mutex_get_owner)(m)
#define mutex_destroy(m)	__KD_SW_MX(m, kd_sw_mutex_destroy, mutex_destroy)(m)

#endif /* !KD_SW_NO_DISPATCH */
#endif /* _KDLOCK_KD_SW_MUTEX_H */
