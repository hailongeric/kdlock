/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Switchable lock objects, struct rw_semaphore (CONFIG_KDLOCK_API). See
 * kd_sw_spin.h for the scheme. Included at the end of linux/rwsem.h.
 *
 * Readers run their sections locally; writers are delegable.
 */
#ifndef _KDLOCK_KD_SW_RWSEM_H
#define _KDLOCK_KD_SW_RWSEM_H

#include <kdlock/kd_api.h>

#ifndef KD_SW_RWSEM
#define KD_SW_RWSEM	0x8U
#endif
extern unsigned int kd_api;

struct kd_sw_rwsem {
	union {
		struct rw_semaphore	native;
		struct kd_rwsem		kd;
	};
	bool				use_kd;
};

#define __KD_SW_RWSEM_INITIALIZER(name)					\
	{ .native = __RWSEM_INITIALIZER((name).native), .use_kd = false }
#define DECLARE_KD_SW_RWSEM(name)					\
	struct kd_sw_rwsem name = __KD_SW_RWSEM_INITIALIZER(name)

static __always_inline void __kd_nat_init_rwsem(struct rw_semaphore *s)
{
	init_rwsem(s);
}

static __always_inline void kd_sw_init_rwsem(struct kd_sw_rwsem *s)
{
	s->use_kd = READ_ONCE(kd_api) & KD_SW_RWSEM;
	if (s->use_kd)
		kd_rwsem_init(&s->kd);
	else
		init_rwsem(&s->native);
}

#define __KD_SW_RWSEM_VOID(name)					\
static __always_inline void kd_sw_##name(struct kd_sw_rwsem *s)		\
{									\
	if (s->use_kd)							\
		kd_##name(&s->kd);					\
	else								\
		name(&s->native);					\
}
#define __KD_SW_RWSEM_INT(name)						\
static __always_inline int kd_sw_##name(struct kd_sw_rwsem *s)		\
{									\
	if (s->use_kd)							\
		return kd_##name(&s->kd);				\
	return name(&s->native);					\
}
__KD_SW_RWSEM_VOID(down_read)
__KD_SW_RWSEM_INT(down_read_interruptible)
__KD_SW_RWSEM_INT(down_read_killable)
__KD_SW_RWSEM_INT(down_read_trylock)
__KD_SW_RWSEM_VOID(down_write)
__KD_SW_RWSEM_INT(down_write_killable)
__KD_SW_RWSEM_INT(down_write_trylock)
__KD_SW_RWSEM_VOID(up_read)
__KD_SW_RWSEM_VOID(up_write)
__KD_SW_RWSEM_VOID(downgrade_write)
#undef __KD_SW_RWSEM_VOID
#undef __KD_SW_RWSEM_INT

static __always_inline int kd_sw_rwsem_is_locked(struct kd_sw_rwsem *s)
{
	return s->use_kd ? kd_rwsem_is_locked(&s->kd) : rwsem_is_locked(&s->native);
}

static __always_inline int kd_sw_rwsem_is_contended(struct kd_sw_rwsem *s)
{
	return s->use_kd ? kd_rwsem_is_contended(&s->kd) : rwsem_is_contended(&s->native);
}

static __always_inline void kd_sw_rwsem_assert_held(const struct kd_sw_rwsem *s)
{
	if (s->use_kd)
		WARN_ON(!kd_rwsem_is_locked((struct kd_rwsem *)&s->kd));
	else
		rwsem_assert_held(&s->native);
}

static __always_inline void kd_sw_rwsem_assert_held_write(const struct kd_sw_rwsem *s)
{
	if (s->use_kd)
		WARN_ON(!kd_rwsem_is_write_locked((struct kd_rwsem *)&s->kd));
	else
		rwsem_assert_held_write(&s->native);
}

#ifndef KD_SW_NO_DISPATCH

#define __KD_SW_RS(s, kdfn, natfn)	\
	_Generic((s), struct kd_sw_rwsem *: kdfn, default: natfn)
#define __KD_SW_RSC(s, kdfn, natfn)	\
	_Generic((s), struct kd_sw_rwsem *: kdfn, const struct kd_sw_rwsem *: kdfn, \
		 default: natfn)

#undef init_rwsem
#define init_rwsem(s)		__KD_SW_RS(s, kd_sw_init_rwsem, __kd_nat_init_rwsem)(s)
#define down_read(s)		__KD_SW_RS(s, kd_sw_down_read, down_read)(s)
#define down_read_interruptible(s)						\
	__KD_SW_RS(s, kd_sw_down_read_interruptible, down_read_interruptible)(s)
#define down_read_killable(s)	__KD_SW_RS(s, kd_sw_down_read_killable, down_read_killable)(s)
#define down_read_trylock(s)	__KD_SW_RS(s, kd_sw_down_read_trylock, down_read_trylock)(s)
#define down_write(s)		__KD_SW_RS(s, kd_sw_down_write, down_write)(s)
#define down_write_killable(s)	__KD_SW_RS(s, kd_sw_down_write_killable, down_write_killable)(s)
#define down_write_trylock(s)	__KD_SW_RS(s, kd_sw_down_write_trylock, down_write_trylock)(s)
#define up_read(s)		__KD_SW_RS(s, kd_sw_up_read, up_read)(s)
#define up_write(s)		__KD_SW_RS(s, kd_sw_up_write, up_write)(s)
#define downgrade_write(s)	__KD_SW_RS(s, kd_sw_downgrade_write, downgrade_write)(s)
#define rwsem_is_locked(s)	__KD_SW_RS(s, kd_sw_rwsem_is_locked, rwsem_is_locked)(s)
#define rwsem_is_contended(s)	__KD_SW_RS(s, kd_sw_rwsem_is_contended, rwsem_is_contended)(s)
#define rwsem_assert_held(s)						\
	__KD_SW_RSC(s, kd_sw_rwsem_assert_held, rwsem_assert_held)(s)
#define rwsem_assert_held_write(s)					\
	__KD_SW_RSC(s, kd_sw_rwsem_assert_held_write, rwsem_assert_held_write)(s)
#define rwsem_assert_held_nolockdep(s)					\
	__KD_SW_RSC(s, kd_sw_rwsem_assert_held, rwsem_assert_held_nolockdep)(s)
#define rwsem_assert_held_write_nolockdep(s)				\
	__KD_SW_RSC(s, kd_sw_rwsem_assert_held_write, rwsem_assert_held_write_nolockdep)(s)

#endif /* !KD_SW_NO_DISPATCH */
#endif /* _KDLOCK_KD_SW_RWSEM_H */
