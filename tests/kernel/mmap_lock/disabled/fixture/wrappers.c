// SPDX-License-Identifier: GPL-2.0
/* Compile-only real-header fixture. No module, synthetic lock or runtime body. */
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/sched/mm.h>

#ifdef CONFIG_KD_MMAP_LOCK
#error "This fixture requires the native, disabled integration branch"
#endif

static_assert(__same_type(((struct mm_struct *)0)->mmap_lock,
			 (struct rw_semaphore){}));

struct mm_struct disabled_static_mm = {
	MMAP_LOCK_INITIALIZER(disabled_static_mm)
};

const unsigned long disabled_layout[] = {
	sizeof(struct mm_struct), sizeof(struct rw_semaphore),
	offsetof(struct mm_struct, mmap_lock),
};

void disabled_init(struct mm_struct *mm) { mmap_init_lock(mm); }
void disabled_read(struct mm_struct *mm) { mmap_read_lock(mm); }
int disabled_read_killable(struct mm_struct *mm) { return mmap_read_lock_killable(mm); }
bool disabled_read_try(struct mm_struct *mm) { return mmap_read_trylock(mm); }
void disabled_read_release(struct mm_struct *mm) { mmap_read_unlock(mm); }
void disabled_read_non_owner(struct mm_struct *mm) { mmap_read_unlock_non_owner(mm); }
void disabled_write(struct mm_struct *mm) { mmap_write_lock(mm); }
void disabled_write_nested(struct mm_struct *mm) { mmap_write_lock_nested(mm, 1); }
int disabled_write_killable(struct mm_struct *mm) { return mmap_write_lock_killable(mm); }
bool disabled_write_try(struct mm_struct *mm) { return mmap_write_trylock(mm); }
void disabled_write_release(struct mm_struct *mm) { mmap_write_unlock(mm); }
void disabled_downgrade(struct mm_struct *mm) { mmap_write_downgrade(mm); }
void disabled_assert_read(struct mm_struct *mm) { mmap_assert_locked(mm); }
void disabled_assert_write(struct mm_struct *mm) { mmap_assert_write_locked(mm); }
bool disabled_contended(struct mm_struct *mm) { return mmap_lock_is_contended(mm); }

#ifdef CHECK_INTEGRATED
void disabled_destroy(struct mm_struct *mm) { mmap_destroy_lock(mm); }
void disabled_prepare(struct mmap_read_token *token, struct mm_struct *mm)
{
	mmap_read_unlock_prepare(token, mm);
}
void disabled_complete(struct mmap_read_token *token)
{
	mmap_read_unlock_complete(token);
}
#endif
