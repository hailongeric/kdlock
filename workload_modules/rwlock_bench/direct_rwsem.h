/* SPDX-License-Identifier: GPL-2.0 */
/* One ordinary public rwsem API. Quiescent preparation opts writer calls
 * into ABI2 delegation; callable symbols provide the explicit local control. */
#ifdef RB_KDLOCK
#include "kd_rwsem_api.h"
static DEFINE_KD_RWSEM(rb_lock);
#define RB_BACKEND 2
#define RB_READ_LOCK() kd_down_read(&rb_lock)
#define RB_READ_UNLOCK() kd_up_read(&rb_lock)
#if RB_RWSEM_DELEGATE
extern char rb_entry[];
#define RB_WRITE_LOCK() do { \
	kd_down_write(&rb_lock); \
	asm volatile(".globl rb_entry\n.set rb_entry, 1b\n\t" \
	             ".pushsection .discard.noendbr\n\t" \
	             _ASM_PTR " rb_entry\n\t.popsection\n\t" : : : "memory"); \
} while (0)
#define RB_WRITE_UNLOCK() kd_up_write(&rb_lock)
MODULE_INFO(kd_rwsem_api, "public-prepared-direct");
#else
#define RB_WRITE_LOCK() (kd_down_write)(&rb_lock)
#define RB_WRITE_UNLOCK() (kd_up_write)(&rb_lock)
MODULE_INFO(kd_rwsem_api, "callable-local");
#endif
#elif defined(RB_TCLOCK)
#include "rwsem/komb_rwsem.h"
extern int tc_rwsem_worker_register(void);
static DECLARE_KOMB_RWSEM(rb_lock);
#define RB_BACKEND 1
#define RB_READ_LOCK() komb_rwsem_down_read(&rb_lock)
#define RB_READ_UNLOCK() komb_rwsem_up_read(&rb_lock)
#define RB_WRITE_LOCK() komb_rwsem_down_write(&rb_lock)
#define RB_WRITE_UNLOCK() komb_rwsem_up_write(&rb_lock)
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
	return kd_rwsem_prepare(&rb_lock, (unsigned long)rb_entry,
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
#elif defined(RB_TCLOCK)
	s->cnts = atomic_long_read(&rb_lock.cnts);
	s->gate = atomic_read(&rb_lock.reader_wait_lock.val) || rb_lock.writer_tail != NULL;
#else
	s->gate = rwsem_is_locked(&rb_lock);
#endif
}
