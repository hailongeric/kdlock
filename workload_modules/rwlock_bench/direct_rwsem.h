/* SPDX-License-Identifier: GPL-2.0 */
/* Sleeping rwsem bodies execute on their caller. The KD gate uses the
 * selected physical mutex protocol, without a delegated writer entry. */
#ifdef RB_KDLOCK
#include "kd_rwsem.h"
static DEFINE_KD_RWSEM(rb_lock);
#define RB_BACKEND 2
#define RB_READ_LOCK() kd_down_read(&rb_lock)
#define RB_READ_UNLOCK() kd_up_read(&rb_lock)
#define RB_WRITE_LOCK() kd_down_write(&rb_lock)
#define RB_WRITE_UNLOCK() kd_up_write(&rb_lock)
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
	return 0;
}

static void rb_lock_snapshot(struct rw_bench_snapshot *s)
{
	s->lock_addr = (unsigned long)&rb_lock;
#ifdef RB_KDLOCK
	s->gate_addr = (unsigned long)&rb_lock.gate;
	s->cnts = atomic_long_read(&rb_lock.readers);
	s->gate = !kd_rwsem_is_idle(&rb_lock);
#else
	s->gate = rwsem_is_locked(&rb_lock);
#endif
}
