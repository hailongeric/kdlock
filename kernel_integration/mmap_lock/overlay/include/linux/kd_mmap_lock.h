/* SPDX-License-Identifier: GPL-2.0 */
#ifndef LINUX_KD_MMAP_LOCK_H
#define LINUX_KD_MMAP_LOCK_H

#include <linux/kd_mmap_lock_types.h>

void kd_mmap_init(struct kd_mmap_lock *lock);
void kd_mmap_destroy(struct kd_mmap_lock *lock);
void kd_mmap_write_lock(struct kd_mmap_lock *lock);
void kd_mmap_write_lock_nested(struct kd_mmap_lock *lock, int subclass);
int kd_mmap_write_lock_killable(struct kd_mmap_lock *lock);
int kd_mmap_write_trylock(struct kd_mmap_lock *lock);
void kd_mmap_write_unlock(struct kd_mmap_lock *lock);
void kd_mmap_write_downgrade(struct kd_mmap_lock *lock);
void kd_mmap_read_lock(struct kd_mmap_lock *lock);
int kd_mmap_read_lock_killable(struct kd_mmap_lock *lock);
int kd_mmap_read_trylock(struct kd_mmap_lock *lock);
void kd_mmap_read_unlock(struct kd_mmap_lock *lock);
void kd_mmap_read_unlock_non_owner(struct kd_mmap_lock *lock);
bool kd_mmap_is_locked(struct kd_mmap_lock *lock);
bool kd_mmap_is_write_owner(struct kd_mmap_lock *lock);
bool kd_mmap_is_contended(struct kd_mmap_lock *lock);
bool kd_mmap_is_idle(struct kd_mmap_lock *lock);

struct mm_struct;
/* Explicit experiment opt-in under this mm's physical write ownership. */
int kd_mmap_body_enable(struct mm_struct *mm);
bool kd_mmap_body_write_owned(struct kd_mmap_lock *lock);
unsigned int kd_mmap_body_pending(struct mm_struct *mm);
int kd_mmap_madvise(struct mm_struct *mm, unsigned long start,
		   unsigned long end, int behavior);
/* Fixed in-tree implementations, never supplied by a module or user pointer.
 * try performs no effects before refusal; native runs only on the origin. */
bool kd_mmap_madvise_try(struct mm_struct *mm, unsigned long start,
			unsigned long end, int behavior, int *result);
int kd_mmap_madvise_native(struct mm_struct *mm, unsigned long start,
			  unsigned long end, int behavior);

#endif
