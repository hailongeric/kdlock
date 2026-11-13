/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Switchable lock objects, spinlock_t and rwlock_t (CONFIG_KDLOCK_API).
 *
 * A switchable lock is a union of the native lock and the kdlock one plus a
 * flag saying which of the two this object uses. The flag is set when the
 * object is initialised, from the kd_api core parameter, and never changes
 * afterwards, so all users of one object follow one protocol. Objects that
 * are zero-filled or statically initialised without an init call use the
 * native lock (a zero flag), which is also the native unlocked state.
 *
 * Integration changes only the type of a selected lock field, e.g.
 *
 *	struct files_struct { ... struct kd_sw_spinlock file_lock; ... };
 *
 * The unchanged lock calls on that field (spin_lock(&files->file_lock),
 * spin_lock_init(), ...) reach the operations below through the _Generic
 * dispatch at the end of this file: a pointer to a switchable lock selects
 * kd_sw_*, any other argument selects the native function exactly as
 * before. The compiler therefore finds every user of a converted field: a
 * native-only interface applied to it (one this file does not dispatch)
 * fails to build instead of silently using the other protocol.
 *
 * The operations are __always_inline so that each acquisition is a call
 * to kd_spin_lock() and friends from the code that holds the lock: the
 * delegation site is that call's return address, and the generated code
 * recognises the end of a section by the direct call to the release.
 *
 * Included at the end of linux/spinlock.h; kernel/locking/ files that
 * define the native functions set KD_SW_NO_DISPATCH first.
 */
#ifndef _KDLOCK_KD_SW_SPIN_H
#define _KDLOCK_KD_SW_SPIN_H

#include <linux/bug.h>
#include <kdlock/kd_api.h>

/* kd_api bits: which lock families new switchable objects take from kdlock. */
#define KD_SW_SPIN	0x1U
#define KD_SW_RWLOCK	0x2U
#define KD_SW_MUTEX	0x4U
#define KD_SW_RWSEM	0x8U

extern unsigned int kd_api;

static __always_inline bool kd_sw_choose(unsigned int family)
{
	return READ_ONCE(kd_api) & family;
}

/* ---- types ---------------------------------------------------------------- */

struct kd_sw_spinlock {
	union {
		spinlock_t		native;
		struct kd_spinlock	kd;
	};
	bool				use_kd;
};

#define __KD_SW_SPIN_UNLOCKED(name)					\
	{ .native = __SPIN_LOCK_UNLOCKED((name).native), .use_kd = false }

struct kd_sw_rwlock {
	union {
		rwlock_t		native;
		struct kd_rwlock	kd;
	};
	bool				use_kd;
};

#define __KD_SW_RW_UNLOCKED(name)					\
	{ .native = __RW_LOCK_UNLOCKED((name).native), .use_kd = false }

/* ---- native forms of the macro interfaces --------------------------------
 *
 * Some native interfaces are macros. Their dispatch needs a function to
 * select, so these capture the native expansion before it is redefined.
 */
static __always_inline void __kd_nat_spin_lock_init(spinlock_t *l)
{
	spin_lock_init(l);
}

static __always_inline unsigned long __kd_nat_spin_lock_irqsave(spinlock_t *l)
{
	unsigned long flags;

	spin_lock_irqsave(l, flags);
	return flags;
}

static __always_inline void __kd_nat_assert_spin_locked(spinlock_t *l)
{
	assert_spin_locked(l);
}

static __always_inline void __kd_nat_rwlock_init(rwlock_t *l)
{
	rwlock_init(l);
}

static __always_inline void __kd_nat_read_lock(rwlock_t *l) { read_lock(l); }
static __always_inline void __kd_nat_read_lock_irq(rwlock_t *l) { read_lock_irq(l); }
static __always_inline void __kd_nat_read_lock_bh(rwlock_t *l) { read_lock_bh(l); }
static __always_inline int __kd_nat_read_trylock(rwlock_t *l) { return read_trylock(l); }
static __always_inline void __kd_nat_read_unlock(rwlock_t *l) { read_unlock(l); }
static __always_inline void __kd_nat_read_unlock_irq(rwlock_t *l) { read_unlock_irq(l); }
static __always_inline void __kd_nat_read_unlock_bh(rwlock_t *l) { read_unlock_bh(l); }
static __always_inline void __kd_nat_write_lock(rwlock_t *l) { write_lock(l); }
static __always_inline void __kd_nat_write_lock_irq(rwlock_t *l) { write_lock_irq(l); }
static __always_inline void __kd_nat_write_lock_bh(rwlock_t *l) { write_lock_bh(l); }
static __always_inline int __kd_nat_write_trylock(rwlock_t *l) { return write_trylock(l); }
static __always_inline void __kd_nat_write_unlock(rwlock_t *l) { write_unlock(l); }
static __always_inline void __kd_nat_write_unlock_irq(rwlock_t *l) { write_unlock_irq(l); }
static __always_inline void __kd_nat_write_unlock_bh(rwlock_t *l) { write_unlock_bh(l); }

static __always_inline unsigned long __kd_nat_read_lock_irqsave(rwlock_t *l)
{
	unsigned long flags;

	read_lock_irqsave(l, flags);
	return flags;
}

static __always_inline unsigned long __kd_nat_write_lock_irqsave(rwlock_t *l)
{
	unsigned long flags;

	write_lock_irqsave(l, flags);
	return flags;
}

static __always_inline void __kd_nat_read_unlock_irqrestore(rwlock_t *l, unsigned long flags)
{
	read_unlock_irqrestore(l, flags);
}

static __always_inline void __kd_nat_write_unlock_irqrestore(rwlock_t *l, unsigned long flags)
{
	write_unlock_irqrestore(l, flags);
}

static __always_inline int __kd_nat_write_trylock_irqsave(rwlock_t *l, unsigned long *flags)
{
	return write_trylock_irqsave(l, *flags);
}

static __always_inline int __kd_nat_rwlock_is_contended(rwlock_t *l)
{
	return rwlock_is_contended(l);
}

/* ---- spinlock_t operations -------------------------------------------------- */

static __always_inline void kd_sw_spin_lock_init(struct kd_sw_spinlock *l)
{
	l->use_kd = kd_sw_choose(KD_SW_SPIN);
	if (l->use_kd)
		kd_spin_lock_init(&l->kd);
	else
		spin_lock_init(&l->native);
}

static __always_inline void kd_sw_spin_lock(struct kd_sw_spinlock *l)
{
	if (l->use_kd)
		kd_spin_lock(&l->kd);
	else
		spin_lock(&l->native);
}

static __always_inline void kd_sw_spin_lock_bh(struct kd_sw_spinlock *l)
{
	if (l->use_kd)
		kd_spin_lock_bh(&l->kd);
	else
		spin_lock_bh(&l->native);
}

static __always_inline void kd_sw_spin_lock_irq(struct kd_sw_spinlock *l)
{
	if (l->use_kd)
		kd_spin_lock_irq(&l->kd);
	else
		spin_lock_irq(&l->native);
}

static __always_inline unsigned long kd_sw_spin_lock_irqsave(struct kd_sw_spinlock *l)
{
	if (l->use_kd)
		return kd_spin_lock_irqsave(&l->kd);
	return __kd_nat_spin_lock_irqsave(&l->native);
}

static __always_inline int kd_sw_spin_trylock(struct kd_sw_spinlock *l)
{
	return l->use_kd ? kd_spin_trylock(&l->kd) : spin_trylock(&l->native);
}

static __always_inline int kd_sw_spin_trylock_bh(struct kd_sw_spinlock *l)
{
	return l->use_kd ? kd_spin_trylock_bh(&l->kd) : spin_trylock_bh(&l->native);
}

static __always_inline int kd_sw_spin_trylock_irq(struct kd_sw_spinlock *l)
{
	return l->use_kd ? kd_spin_trylock_irq(&l->kd) : spin_trylock_irq(&l->native);
}

static __always_inline bool kd_sw_spin_trylock_irqsave(struct kd_sw_spinlock *l,
						       unsigned long *flags)
{
	return l->use_kd ? kd_spin_trylock_irqsave(&l->kd, flags)
			 : _spin_trylock_irqsave(&l->native, flags);
}

static __always_inline void kd_sw_spin_unlock(struct kd_sw_spinlock *l)
{
	if (l->use_kd)
		kd_spin_unlock(&l->kd);
	else
		spin_unlock(&l->native);
}

static __always_inline void kd_sw_spin_unlock_bh(struct kd_sw_spinlock *l)
{
	if (l->use_kd)
		kd_spin_unlock_bh(&l->kd);
	else
		spin_unlock_bh(&l->native);
}

static __always_inline void kd_sw_spin_unlock_irq(struct kd_sw_spinlock *l)
{
	if (l->use_kd)
		kd_spin_unlock_irq(&l->kd);
	else
		spin_unlock_irq(&l->native);
}

static __always_inline void kd_sw_spin_unlock_irqrestore(struct kd_sw_spinlock *l,
							 unsigned long flags)
{
	if (l->use_kd)
		kd_spin_unlock_irqrestore(&l->kd, flags);
	else
		spin_unlock_irqrestore(&l->native, flags);
}

static __always_inline int kd_sw_spin_is_locked(struct kd_sw_spinlock *l)
{
	return l->use_kd ? kd_spin_is_locked(&l->kd) : spin_is_locked(&l->native);
}

static __always_inline int kd_sw_spin_is_contended(struct kd_sw_spinlock *l)
{
	return l->use_kd ? kd_spin_is_contended(&l->kd) : spin_is_contended(&l->native);
}

static __always_inline int kd_sw_spin_needbreak(struct kd_sw_spinlock *l)
{
	return l->use_kd ? preempt_model_preemptible() && kd_spin_is_contended(&l->kd)
			 : spin_needbreak(&l->native);
}

static __always_inline void kd_sw_assert_spin_locked(struct kd_sw_spinlock *l)
{
	if (l->use_kd)
		BUG_ON(!kd_spin_is_locked(&l->kd));
	else
		__kd_nat_assert_spin_locked(&l->native);
}

/* ---- rwlock_t operations ----------------------------------------------------
 *
 * Readers never delegate (kd_read_lock() runs the section locally); writers
 * are delegable.
 */
static __always_inline void kd_sw_rwlock_init(struct kd_sw_rwlock *l)
{
	l->use_kd = kd_sw_choose(KD_SW_RWLOCK);
	if (l->use_kd)
		kd_rwlock_init(&l->kd);
	else
		__kd_nat_rwlock_init(&l->native);
}

#define __KD_SW_RW_OP(name, kdfn)						\
static __always_inline void kd_sw_##name(struct kd_sw_rwlock *l)		\
{										\
	if (l->use_kd)								\
		kdfn(&l->kd);							\
	else									\
		__kd_nat_##name(&l->native);					\
}
__KD_SW_RW_OP(read_lock, kd_read_lock)
__KD_SW_RW_OP(read_lock_irq, kd_read_lock_irq)
__KD_SW_RW_OP(read_lock_bh, kd_read_lock_bh)
__KD_SW_RW_OP(read_unlock, kd_read_unlock)
__KD_SW_RW_OP(read_unlock_irq, kd_read_unlock_irq)
__KD_SW_RW_OP(read_unlock_bh, kd_read_unlock_bh)
__KD_SW_RW_OP(write_lock, kd_write_lock)
__KD_SW_RW_OP(write_lock_irq, kd_write_lock_irq)
__KD_SW_RW_OP(write_lock_bh, kd_write_lock_bh)
__KD_SW_RW_OP(write_unlock, kd_write_unlock)
__KD_SW_RW_OP(write_unlock_irq, kd_write_unlock_irq)
__KD_SW_RW_OP(write_unlock_bh, kd_write_unlock_bh)
#undef __KD_SW_RW_OP

static __always_inline int kd_sw_read_trylock(struct kd_sw_rwlock *l)
{
	return l->use_kd ? kd_read_trylock(&l->kd) : __kd_nat_read_trylock(&l->native);
}

static __always_inline int kd_sw_write_trylock(struct kd_sw_rwlock *l)
{
	return l->use_kd ? kd_write_trylock(&l->kd) : __kd_nat_write_trylock(&l->native);
}

static __always_inline unsigned long kd_sw_read_lock_irqsave(struct kd_sw_rwlock *l)
{
	if (l->use_kd)
		return kd_read_lock_irqsave(&l->kd);
	return __kd_nat_read_lock_irqsave(&l->native);
}

static __always_inline unsigned long kd_sw_write_lock_irqsave(struct kd_sw_rwlock *l)
{
	if (l->use_kd)
		return kd_write_lock_irqsave(&l->kd);
	return __kd_nat_write_lock_irqsave(&l->native);
}

static __always_inline void kd_sw_read_unlock_irqrestore(struct kd_sw_rwlock *l,
							 unsigned long flags)
{
	if (l->use_kd)
		kd_read_unlock_irqrestore(&l->kd, flags);
	else
		__kd_nat_read_unlock_irqrestore(&l->native, flags);
}

static __always_inline void kd_sw_write_unlock_irqrestore(struct kd_sw_rwlock *l,
							  unsigned long flags)
{
	if (l->use_kd)
		kd_write_unlock_irqrestore(&l->kd, flags);
	else
		__kd_nat_write_unlock_irqrestore(&l->native, flags);
}

static __always_inline int kd_sw_write_trylock_irqsave(struct kd_sw_rwlock *l,
						       unsigned long *flags)
{
	return l->use_kd ? kd_write_trylock_irqsave(&l->kd, flags)
			 : __kd_nat_write_trylock_irqsave(&l->native, flags);
}

static __always_inline int kd_sw_rwlock_is_contended(struct kd_sw_rwlock *l)
{
	return l->use_kd ? kd_rwlock_is_contended(&l->kd)
			 : __kd_nat_rwlock_is_contended(&l->native);
}

static __always_inline int kd_sw_rwlock_needbreak(struct kd_sw_rwlock *l)
{
	return l->use_kd ? preempt_model_preemptible() && kd_rwlock_is_contended(&l->kd)
			 : rwlock_needbreak(&l->native);
}

/* ---- dispatch ---------------------------------------------------------------- */
#ifndef KD_SW_NO_DISPATCH

#define __KD_SW_SPIN(l, kdfn, natfn)	\
	_Generic((l), struct kd_sw_spinlock *: kdfn, default: natfn)
#define __KD_SW_RW(l, kdfn, natfn)	\
	_Generic((l), struct kd_sw_rwlock *: kdfn, default: natfn)

#undef spin_lock_init
#define spin_lock_init(l)	__KD_SW_SPIN(l, kd_sw_spin_lock_init, __kd_nat_spin_lock_init)(l)
#define spin_lock(l)		__KD_SW_SPIN(l, kd_sw_spin_lock, spin_lock)(l)
#define spin_lock_bh(l)		__KD_SW_SPIN(l, kd_sw_spin_lock_bh, spin_lock_bh)(l)
#define spin_lock_irq(l)	__KD_SW_SPIN(l, kd_sw_spin_lock_irq, spin_lock_irq)(l)
#undef spin_lock_irqsave
#define spin_lock_irqsave(l, flags)						\
	do {									\
		typecheck(unsigned long, flags);				\
		flags = __KD_SW_SPIN(l, kd_sw_spin_lock_irqsave,		\
				     __kd_nat_spin_lock_irqsave)(l);		\
	} while (0)
/* Without lockdep the subclass and the outer lock have no meaning. */
#undef spin_lock_nested
#define spin_lock_nested(l, subclass)		spin_lock(((void)(subclass), (l)))
#undef spin_lock_nest_lock
#define spin_lock_nest_lock(l, nest_lock)	spin_lock(((void)(nest_lock), (l)))
#undef spin_lock_irqsave_nested
#define spin_lock_irqsave_nested(l, flags, subclass)			\
	spin_lock_irqsave(((void)(subclass), (l)), flags)
#define spin_trylock(l)		__KD_SW_SPIN(l, kd_sw_spin_trylock, spin_trylock)(l)
#define spin_trylock_bh(l)	__KD_SW_SPIN(l, kd_sw_spin_trylock_bh, spin_trylock_bh)(l)
#define spin_trylock_irq(l)	__KD_SW_SPIN(l, kd_sw_spin_trylock_irq, spin_trylock_irq)(l)
#undef spin_trylock_irqsave
#define spin_trylock_irqsave(l, flags)						\
	__KD_SW_SPIN(l, kd_sw_spin_trylock_irqsave, _spin_trylock_irqsave)(l, &(flags))
#define spin_unlock(l)		__KD_SW_SPIN(l, kd_sw_spin_unlock, spin_unlock)(l)
#define spin_unlock_bh(l)	__KD_SW_SPIN(l, kd_sw_spin_unlock_bh, spin_unlock_bh)(l)
#define spin_unlock_irq(l)	__KD_SW_SPIN(l, kd_sw_spin_unlock_irq, spin_unlock_irq)(l)
#define spin_unlock_irqrestore(l, flags)					\
	__KD_SW_SPIN(l, kd_sw_spin_unlock_irqrestore, spin_unlock_irqrestore)(l, flags)
#define spin_is_locked(l)	__KD_SW_SPIN(l, kd_sw_spin_is_locked, spin_is_locked)(l)
#define spin_is_contended(l)	__KD_SW_SPIN(l, kd_sw_spin_is_contended, spin_is_contended)(l)
#define spin_needbreak(l)	__KD_SW_SPIN(l, kd_sw_spin_needbreak, spin_needbreak)(l)
#undef assert_spin_locked
#define assert_spin_locked(l)							\
	__KD_SW_SPIN(l, kd_sw_assert_spin_locked, __kd_nat_assert_spin_locked)(l)

#undef rwlock_init
#define rwlock_init(l)		__KD_SW_RW(l, kd_sw_rwlock_init, __kd_nat_rwlock_init)(l)
#undef read_lock
#define read_lock(l)		__KD_SW_RW(l, kd_sw_read_lock, __kd_nat_read_lock)(l)
#undef read_lock_irq
#define read_lock_irq(l)	__KD_SW_RW(l, kd_sw_read_lock_irq, __kd_nat_read_lock_irq)(l)
#undef read_lock_bh
#define read_lock_bh(l)		__KD_SW_RW(l, kd_sw_read_lock_bh, __kd_nat_read_lock_bh)(l)
#undef read_trylock
#define read_trylock(l)		__KD_SW_RW(l, kd_sw_read_trylock, __kd_nat_read_trylock)(l)
#undef read_unlock
#define read_unlock(l)		__KD_SW_RW(l, kd_sw_read_unlock, __kd_nat_read_unlock)(l)
#undef read_unlock_irq
#define read_unlock_irq(l)	__KD_SW_RW(l, kd_sw_read_unlock_irq, __kd_nat_read_unlock_irq)(l)
#undef read_unlock_bh
#define read_unlock_bh(l)	__KD_SW_RW(l, kd_sw_read_unlock_bh, __kd_nat_read_unlock_bh)(l)
#undef write_lock
#define write_lock(l)		__KD_SW_RW(l, kd_sw_write_lock, __kd_nat_write_lock)(l)
#undef write_lock_nested
#define write_lock_nested(l, subclass)	write_lock(((void)(subclass), (l)))
#undef write_lock_irq
#define write_lock_irq(l)	__KD_SW_RW(l, kd_sw_write_lock_irq, __kd_nat_write_lock_irq)(l)
#undef write_lock_bh
#define write_lock_bh(l)	__KD_SW_RW(l, kd_sw_write_lock_bh, __kd_nat_write_lock_bh)(l)
#undef write_trylock
#define write_trylock(l)	__KD_SW_RW(l, kd_sw_write_trylock, __kd_nat_write_trylock)(l)
#undef write_unlock
#define write_unlock(l)		__KD_SW_RW(l, kd_sw_write_unlock, __kd_nat_write_unlock)(l)
#undef write_unlock_irq
#define write_unlock_irq(l)	__KD_SW_RW(l, kd_sw_write_unlock_irq, __kd_nat_write_unlock_irq)(l)
#undef write_unlock_bh
#define write_unlock_bh(l)	__KD_SW_RW(l, kd_sw_write_unlock_bh, __kd_nat_write_unlock_bh)(l)
#undef read_lock_irqsave
#define read_lock_irqsave(l, flags)						\
	do {									\
		typecheck(unsigned long, flags);				\
		flags = __KD_SW_RW(l, kd_sw_read_lock_irqsave,			\
				   __kd_nat_read_lock_irqsave)(l);		\
	} while (0)
#undef write_lock_irqsave
#define write_lock_irqsave(l, flags)						\
	do {									\
		typecheck(unsigned long, flags);				\
		flags = __KD_SW_RW(l, kd_sw_write_lock_irqsave,			\
				   __kd_nat_write_lock_irqsave)(l);		\
	} while (0)
#undef read_unlock_irqrestore
#define read_unlock_irqrestore(l, flags)					\
	__KD_SW_RW(l, kd_sw_read_unlock_irqrestore, __kd_nat_read_unlock_irqrestore)(l, flags)
#undef write_unlock_irqrestore
#define write_unlock_irqrestore(l, flags)					\
	__KD_SW_RW(l, kd_sw_write_unlock_irqrestore, __kd_nat_write_unlock_irqrestore)(l, flags)
#undef write_trylock_irqsave
#define write_trylock_irqsave(l, flags)						\
	__KD_SW_RW(l, kd_sw_write_trylock_irqsave, __kd_nat_write_trylock_irqsave)(l, &(flags))
#undef rwlock_is_contended
#define rwlock_is_contended(l)							\
	__KD_SW_RW(l, kd_sw_rwlock_is_contended, __kd_nat_rwlock_is_contended)(l)
#define rwlock_needbreak(l)	__KD_SW_RW(l, kd_sw_rwlock_needbreak, rwlock_needbreak)(l)

#endif /* !KD_SW_NO_DISPATCH */
#endif /* _KDLOCK_KD_SW_SPIN_H */
