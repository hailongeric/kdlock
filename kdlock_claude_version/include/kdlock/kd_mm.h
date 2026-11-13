/* SPDX-License-Identifier: GPL-2.0 */
/*
 * mmap lock operations for CONFIG_KDLOCK_MM; include/linux/mmap_lock.h maps
 * its __mmap_sem_* layer onto these.
 *
 * They are inline on purpose. A delegable acquisition is keyed by its call
 * site (the return address of the kd_down_write* call), so the call must
 * be made from the code that holds the lock, not from a shared wrapper:
 * with an out-of-line wrapper every mmap writer in the kernel would share
 * one site, one image and one usefulness account. Likewise the release
 * must be a direct call to kd_up_write() in that code, which is how a
 * delegated section is recognised to end.
 */
#ifndef _KDLOCK_KD_MM_H
#define _KDLOCK_KD_MM_H

#include <linux/bug.h>
#include <linux/rwsem.h>
#include <kdlock/kd_mm_types.h>
#include <kdlock/kd_api.h>

void kd_mm_init(struct kd_mm_lock *l);
void kd_mm_destroy(struct kd_mm_lock *l);

static __always_inline void kd_mm_down_write(struct kd_mm_lock *l)
{
	if (l->use_kd)
		kd_down_write(&l->kd);
	else
		down_write(&l->native);
}

/* Without lockdep the subclass has no meaning. */
static __always_inline void kd_mm_down_write_nested(struct kd_mm_lock *l, int subclass)
{
	if (l->use_kd)
		kd_down_write(&l->kd);
	else
		down_write_nested(&l->native, subclass);
}

static __always_inline int kd_mm_down_write_killable(struct kd_mm_lock *l)
{
	if (l->use_kd)
		return kd_down_write_killable(&l->kd);
	return down_write_killable(&l->native);
}

static __always_inline void kd_mm_up_write(struct kd_mm_lock *l)
{
	if (l->use_kd)
		kd_up_write(&l->kd);
	else
		up_write(&l->native);
}

static __always_inline void kd_mm_downgrade_write(struct kd_mm_lock *l)
{
	if (l->use_kd)
		kd_downgrade_write(&l->kd);
	else
		downgrade_write(&l->native);
}

static __always_inline void kd_mm_down_read(struct kd_mm_lock *l)
{
	if (l->use_kd)
		kd_down_read(&l->kd);
	else
		down_read(&l->native);
}

static __always_inline int kd_mm_down_read_killable(struct kd_mm_lock *l)
{
	if (l->use_kd)
		return kd_down_read_killable(&l->kd);
	return down_read_killable(&l->native);
}

static __always_inline int kd_mm_down_read_trylock(struct kd_mm_lock *l)
{
	if (l->use_kd)
		return kd_down_read_trylock(&l->kd);
	return down_read_trylock(&l->native);
}

static __always_inline void kd_mm_up_read(struct kd_mm_lock *l)
{
	if (l->use_kd)
		kd_up_read(&l->kd);
	else
		up_read(&l->native);
}

/* Readers record no owner, so releasing for another task is the same call. */
static __always_inline void kd_mm_up_read_non_owner(struct kd_mm_lock *l)
{
	if (l->use_kd)
		kd_up_read(&l->kd);
	else
		up_read_non_owner(&l->native);
}

static __always_inline int kd_mm_is_locked(struct kd_mm_lock *l)
{
	return l->use_kd ? kd_rwsem_is_locked(&l->kd) : rwsem_is_locked(&l->native);
}

static __always_inline int kd_mm_is_contended(struct kd_mm_lock *l)
{
	return l->use_kd ? kd_rwsem_is_contended(&l->kd) : rwsem_is_contended(&l->native);
}

static __always_inline void kd_mm_assert_held(const struct kd_mm_lock *l)
{
	if (l->use_kd)
		WARN_ON(!kd_rwsem_is_locked((struct kd_rwsem *)&l->kd));
	else
		rwsem_assert_held(&l->native);
}

static __always_inline void kd_mm_assert_held_write(const struct kd_mm_lock *l)
{
	if (l->use_kd)
		WARN_ON(!kd_rwsem_is_write_locked((struct kd_rwsem *)&l->kd));
	else
		rwsem_assert_held_write(&l->native);
}

#endif /* _KDLOCK_KD_MM_H */
