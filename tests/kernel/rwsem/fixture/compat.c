// SPDX-License-Identifier: GPL-2.0
/* Native source spellings operate only on this translation unit's KD objects. */
#include <linux/errno.h>
#include <linux/module.h>
#include "kd_rwsem_compat.h"

static DECLARE_RWSEM(sem);
int kd_rwsem_compat_checks(void);

int kd_rwsem_compat_checks(void)
{
	struct rw_semaphore dynamic;
	struct lock_class_key key;
	int (*locked)(struct rw_semaphore *) = rwsem_is_locked;
	int (*contended)(struct rw_semaphore *) = rwsem_is_contended;
	void (*local)(struct rw_semaphore *) = down_write;
	unsigned int errors = 0, entered = 0, annotation = 0;

	__init_rwsem(&dynamic, "rwsem_compat", &key);
	errors += locked(&dynamic) || contended(&dynamic);
	init_rwsem(&dynamic);
	down_write_nested(&dynamic, annotation++);
	errors += annotation != 0 || !locked(&dynamic);
	rwsem_assert_held(&dynamic);
	rwsem_assert_held_write(&dynamic);
	downgrade_write(&dynamic);
	up_read(&dynamic);
	local(&dynamic);
	up_write(&dynamic);
	down_read_nested(&sem, annotation++);
	errors += down_write_trylock(&sem) != 0 || annotation != 0;
	up_read(&sem);
	down_read_non_owner(&sem);
	up_read_non_owner(&sem);
	{ guard(rwsem_read)(&sem); errors += !locked(&sem); }
	{ guard(rwsem_write)(&sem); errors += !locked(&sem); }
	{ guard(rwsem_init)(&dynamic); errors += locked(&dynamic); }
	scoped_guard(rwsem_read, &sem) { entered++; }
	scoped_guard(rwsem_write, &sem) { entered++; }
	scoped_cond_guard(rwsem_read_try, errors++, &sem) { entered++; }
	scoped_cond_guard(rwsem_write_try, errors++, &sem) { entered++; }
	{
		ACQUIRE(rwsem_read_intr, acquired)(&sem);

		errors += ACQUIRE_ERR(rwsem_read_intr, &acquired) != 0;
	}
	{
		ACQUIRE(rwsem_write_kill, acquired)(&sem);

		errors += ACQUIRE_ERR(rwsem_write_kill, &acquired) != 0;
	}
	errors += entered != 4 || locked(&sem) || contended(&sem) || locked(&dynamic);
	return errors ? -EINVAL : 0;
}
