/* SPDX-License-Identifier: GPL-2.0 */
#ifdef RB_KDLOCK
#include "kd_rwsem.h"
static DEFINE_KD_RWSEM(rb_lock);
extern char rb_entry[];
#define RB_BACKEND 2
#define RB_READ_LOCK() kd_down_read(&rb_lock)
#define RB_READ_UNLOCK() kd_up_read(&rb_lock)
#define RB_WRITE_LOCK() struct kd_owned_mutex_outer_cookie kd_owned_mutex_cookie; \
	KD_RWSEM_OUTER_WRITE_LOCK(&rb_lock, kd_owned_mutex_cookie, \
	".globl rb_entry\nrb_entry:\n\t" ANNOTATE_NOENDBR)
#define RB_WRITE_UNLOCK() KD_RWSEM_OUTER_WRITE_UNLOCK(&rb_lock, kd_owned_mutex_cookie)
#else
#include <linux/rwsem.h>
static DECLARE_RWSEM(rb_lock);
#define RB_BACKEND 0
#define RB_READ_LOCK() down_read(&rb_lock)
#define RB_READ_UNLOCK() up_read(&rb_lock)
#define RB_WRITE_LOCK() down_write(&rb_lock)
#define RB_WRITE_UNLOCK() up_write(&rb_lock)
#endif

static int rb_prepare(void)
{
#ifdef RB_KDLOCK
	return kd_rwsem_prepare(&rb_lock, KD_OWNED_MUTEX_PREPARE_IP(rb_entry),
				KD_OWNED_MUTEX_ENTRY_ABI);
#else
	return 0;
#endif
}

static void rb_lock_snapshot(struct rw_bench_snapshot *s)
{
	s->lock_addr = (unsigned long)&rb_lock;
#ifdef RB_KDLOCK
	s->gate_addr = (unsigned long)&rb_lock.gate;
	s->entry = KD_OWNED_MUTEX_PREPARE_IP(rb_entry);
	s->cnts = atomic_long_read(&rb_lock.readers);
	s->gate = !kd_rwsem_is_idle(&rb_lock);
#else
	s->gate = rwsem_is_locked(&rb_lock);
#endif
}
