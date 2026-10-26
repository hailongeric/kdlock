/* SPDX-License-Identifier: GPL-2.0 */
/* The nano mutex profile uses only exclusive updates. Its default writer uses
 * the public ABI2 interface, with an explicit local control. The unused reader
 * shell acquires the same physical object locally, without a second JIT entry. */
#ifndef KD_RW_BENCH_DIRECT_MUTEX_H
#define KD_RW_BENCH_DIRECT_MUTEX_H

#include <linux/mutex.h>

#ifndef RB_MUTEX_DELEGATE
#define RB_MUTEX_DELEGATE 1
#endif
#if RB_MUTEX_DELEGATE != 0 && RB_MUTEX_DELEGATE != 1
#error "RB_MUTEX_DELEGATE must be zero or one"
#endif

#ifdef RB_KDLOCK
#include "kd_mutex_api.h"
static struct kd_mutex rb_lock __aligned(64) = KD_MUTEX_INITIALIZER(rb_lock);
#define RB_BACKEND 2
#define RB_READ_LOCK() (kd_mutex_lock)(&rb_lock)
#define RB_READ_UNLOCK() (kd_mutex_unlock)(&rb_lock)
#if RB_MUTEX_DELEGATE
extern char rb_entry[];
/* Alias the continuation saved by the public macro, before any compiler
 * register restores. The runner audits the compiled CALL and this address. */
#define RB_WRITE_LOCK() do { \
	kd_mutex_lock(&rb_lock); \
	asm volatile(".globl rb_entry\n.set rb_entry, 1b\n\t" \
		     ".pushsection .discard.noendbr\n\t" \
		     _ASM_PTR " rb_entry\n\t.popsection\n\t" : : : "memory"); \
} while (0)
#define RB_WRITE_UNLOCK() kd_mutex_unlock(&rb_lock)
MODULE_INFO(kd_mutex_api, "public");
#else
/* The explicit local control changes only the acquisition call shell. The
 * callable unlock still routes the exact provider record of that acquisition. */
#define RB_WRITE_LOCK() (kd_mutex_lock)(&rb_lock)
#define RB_WRITE_UNLOCK() (kd_mutex_unlock)(&rb_lock)
MODULE_INFO(kd_mutex_api, "local");
#endif
#elif defined(RB_TCLOCK)
#include "mutex/komb_mutex.h"
static struct komb_mutex rb_lock __aligned(64) = __KOMBMUTEX_INITIALIZER(rb_lock);
extern int tc_mutex_worker_register(void);
extern int tc_mutex_workers_drain(void);
#define RB_BACKEND 1
#define RB_READ_LOCK() komb_mutex_lock(&rb_lock)
#define RB_READ_UNLOCK() komb_mutex_unlock(&rb_lock)
#define RB_WRITE_LOCK() komb_mutex_lock(&rb_lock)
#define RB_WRITE_UNLOCK() komb_mutex_unlock(&rb_lock)
#else
static struct mutex rb_lock __aligned(64) = __MUTEX_INITIALIZER(rb_lock);
#define RB_BACKEND 0
/* Bypass the captured experiment kernel's mutex caller-clobber macros. */
#define RB_READ_LOCK() (mutex_lock)(&rb_lock)
#define RB_READ_UNLOCK() (mutex_unlock)(&rb_lock)
#define RB_WRITE_LOCK() (mutex_lock)(&rb_lock)
#define RB_WRITE_UNLOCK() (mutex_unlock)(&rb_lock)
#endif

static int rb_prepare(void)
{
#ifdef RB_KDLOCK
	BUILD_BUG_ON(sizeof(struct kd_mutex) != 32);
	BUILD_BUG_ON(__alignof__(struct kd_mutex) != 8);
#if RB_MUTEX_DELEGATE
	return kd_mutex_prepare(&rb_lock, (unsigned long)rb_entry,
				KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#else
	return 0;
#endif
#else
	return 0;
#endif
}

static void rb_lock_snapshot(struct rw_bench_snapshot *s)
{
	s->lock_addr = (unsigned long)&rb_lock;
	s->gate_addr = s->lock_addr;
#ifdef RB_KDLOCK
#if RB_MUTEX_DELEGATE
	s->entry = (unsigned long)rb_entry;
#endif
	s->gate = !kd_mutex_is_idle(&rb_lock);
#elif defined(RB_TCLOCK)
	/* Queue state supplements the provider's separate task-context drain. */
	s->gate = READ_ONCE(rb_lock.tail) || READ_ONCE(rb_lock.locked) ||
		READ_ONCE(rb_lock.combiner_task);
#else
	s->gate = mutex_is_locked(&rb_lock);
#endif
}

#endif
