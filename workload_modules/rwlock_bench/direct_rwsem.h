/* SPDX-License-Identifier: GPL-2.0 */
/* Readers retain sleeping rwsem semantics. The explicit delegated writer
 * shell reserves a reader-free epoch before entering the unchanged KD mutex
 * protocol; the ordinary shell remains a distinct local control. */
#ifdef RB_KDLOCK
#include "kd_rwsem.h"
static DEFINE_KD_RWSEM(rb_lock);
#define RB_BACKEND 2
#define RB_READ_LOCK() kd_down_read(&rb_lock)
#define RB_READ_UNLOCK() kd_up_read(&rb_lock)
#if RB_RWSEM_DELEGATE
#include "kd_rwsem_direct.h"
extern char rb_entry[];
#define RB_WRITE_LOCK() struct kd_rwsem_outer_cookie rb_writer_cookie; \
	KD_RWSEM_OUTER_WRITE_LOCK(&rb_lock, rb_writer_cookie, \
	".globl rb_entry\nrb_entry:\n\t" ANNOTATE_NOENDBR)
#define RB_WRITE_UNLOCK() KD_RWSEM_OUTER_WRITE_UNLOCK(&rb_lock, rb_writer_cookie)
#else
#define RB_WRITE_LOCK() kd_down_write(&rb_lock)
#define RB_WRITE_UNLOCK() kd_up_write(&rb_lock)
#endif
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
#if defined(RB_KDLOCK) && RB_RWSEM_DELEGATE
	return kd_mutex_prepare(&rb_lock.gate, (unsigned long)rb_entry,
				KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#else
	return 0;
#endif
}

static void rb_lock_snapshot(struct rw_bench_snapshot *s)
{
	s->lock_addr = (unsigned long)&rb_lock;
#ifdef RB_KDLOCK
	s->gate_addr = (unsigned long)&rb_lock.gate;
#if RB_RWSEM_DELEGATE
	s->entry = (unsigned long)rb_entry;
#endif
	s->cnts = atomic_long_read(&rb_lock.readers);
	s->gate = !kd_rwsem_is_idle(&rb_lock);
#else
	s->gate = rwsem_is_locked(&rb_lock);
#endif
}
