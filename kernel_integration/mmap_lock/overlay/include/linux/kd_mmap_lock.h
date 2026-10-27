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
void kd_mmap_assert_held(const struct kd_mmap_lock *lock);
void kd_mmap_assert_held_write(const struct kd_mmap_lock *lock);

#endif
