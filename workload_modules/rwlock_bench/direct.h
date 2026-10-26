/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RW_BENCH_DIRECT_H
#define KD_RW_BENCH_DIRECT_H
#ifdef RB_SPIN
#include "direct_spin.h"
#elif defined(RB_MUTEX)
#include "direct_mutex.h"
#elif defined(RB_RWSEM)
#include "direct_rwsem.h"
#else
#ifdef RB_KDLOCK
#include "kd_rwlock.h"
static kd_rwlock_t rb_lock __aligned(64) = KD_RWLOCK_INITIALIZER;
extern char rb_entry[];
#define RB_BACKEND 2
#define RB_READ_LOCK() kd_read_lock(&rb_lock)
#define RB_READ_UNLOCK() kd_read_unlock(&rb_lock)
#define RB_WRITE_LOCK() KD_RWLOCK_DIRECT_WRITE_LOCK(&rb_lock, \
	kd_rwlock_direct_cookie, ".globl rb_entry\nrb_entry:\n\t" ANNOTATE_NOENDBR)
#define RB_WRITE_UNLOCK() KD_RWLOCK_DIRECT_WRITE_UNLOCK(&rb_lock, kd_rwlock_direct_cookie)
#elif defined(RB_TCLOCK)
#include "rwlock/komb_rwlock.h"
static struct komb_rwlock rb_lock __aligned(64) = __KOMB_RWLOCK_UNLOCKED;
#define RB_BACKEND 1
/* Original rwlock inline returns can leave IRQs off. These callers enter
 * with IRQs enabled and restore that context after the complete pair. */
#define RB_READ_LOCK() do { preempt_disable(); komb_read_lock(&rb_lock); } while (0)
#define RB_READ_UNLOCK() do { komb_read_unlock(&rb_lock); local_irq_enable(); preempt_enable(); } while (0)
#define RB_WRITE_LOCK() do { preempt_disable(); komb_write_lock(&rb_lock); } while (0)
#define RB_WRITE_UNLOCK() do { komb_write_unlock(&rb_lock); local_irq_enable(); preempt_enable(); } while (0)
#else
static rwlock_t rb_lock __aligned(64) = __RW_LOCK_UNLOCKED(rb_lock);
#define RB_BACKEND 0
#define RB_READ_LOCK() read_lock(&rb_lock)
#define RB_READ_UNLOCK() read_unlock(&rb_lock)
#define RB_WRITE_LOCK() write_lock(&rb_lock)
#define RB_WRITE_UNLOCK() write_unlock(&rb_lock)
#endif

static int rb_prepare(void)
{
#ifdef RB_KDLOCK
	return kd_rwlock_prepare(&rb_lock, (unsigned long)rb_entry, KD_ENTRY_ABI_RWLOCK_CLOBBER_V1);
#else
	return 0;
#endif
}

static void rb_lock_snapshot(struct rw_bench_snapshot *s)
{
	s->lock_addr = (unsigned long)&rb_lock;
#if defined(RB_KDLOCK)
	s->gate_addr = (unsigned long)&rb_lock.gate;
	s->entry = (unsigned long)rb_entry;
	s->cnts = kd_rwlock_state(&rb_lock);
	s->gate = atomic_read(&rb_lock.gate.val);
#elif defined(RB_TCLOCK)
	s->gate_addr = (unsigned long)&rb_lock.lock;
	s->cnts = atomic_read(&rb_lock.cnts);
	s->gate = atomic_read(&rb_lock.lock.val);
#else
	s->cnts = atomic_read(&rb_lock.raw_lock.cnts);
	s->gate = atomic_read(&rb_lock.raw_lock.wait_lock.val);
#endif
}
#endif /* ordinary rwlock */
#endif
