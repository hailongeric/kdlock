/* SPDX-License-Identifier: GPL-2.0 */
/* Only the lock binding differs; body.h retains the original nano work. */
#ifndef KD_NANO_DIRECT_H
#define KD_NANO_DIRECT_H

#ifdef RB_KDLOCK
#include "kernel/runtime.h"
#include "kernel/task_state.h"
#include "kernel/observation.h"
#ifdef RB_MUTEX
#include "include/kd_mutex_api.h"
static struct kd_mutex rb_lock __aligned(64);
#define RB_WRITE_LOCK() kd_mutex_lock(&rb_lock)
#define RB_WRITE_UNLOCK() kd_mutex_unlock(&rb_lock)
#define RB_READ_LOCK() kd_mutex_lock(&rb_lock)
#define RB_READ_UNLOCK() kd_mutex_unlock(&rb_lock)
#define RB_UNLOCK_KIND KD_OPERATION_MUTEX_UNLOCK
#define RB_FAMILY KD_LOCK_FAMILY_MUTEX
#else
#include "include/kd_rwsem_api.h"
#include "kernel/rw_admission.h"
static struct kd_rwsem rb_lock __aligned(64);
#define RB_WRITE_LOCK() kd_rwsem_down_write(&rb_lock)
#define RB_WRITE_UNLOCK() kd_rwsem_up_write(&rb_lock)
#define RB_READ_LOCK() kd_rwsem_down_read(&rb_lock)
#define RB_READ_UNLOCK() kd_rwsem_up_read(&rb_lock)
#define RB_UNLOCK_KIND KD_OPERATION_RWSEM_UP_WRITE
#define RB_FAMILY KD_LOCK_FAMILY_RWSEM
#endif
#define RB_BACKEND 2
#elif defined(RB_TCLOCK)
#ifdef RB_MUTEX
#include "mutex/komb_mutex.h"
static struct komb_mutex rb_lock __aligned(64) = __KOMBMUTEX_INITIALIZER(rb_lock);
extern int tc_mutex_worker_register(void);
extern int tc_mutex_workers_drain(void);
#define RB_WRITE_LOCK() komb_mutex_lock(&rb_lock)
#define RB_WRITE_UNLOCK() komb_mutex_unlock(&rb_lock)
#define RB_READ_LOCK() komb_mutex_lock(&rb_lock)
#define RB_READ_UNLOCK() komb_mutex_unlock(&rb_lock)
#else
#include "rwsem/komb_rwsem.h"
static DECLARE_KOMB_RWSEM(rb_lock);
extern int tc_rwsem_worker_register(void);
extern int tc_rwsem_workers_drain(void);
#define RB_WRITE_LOCK() komb_rwsem_down_write(&rb_lock)
#define RB_WRITE_UNLOCK() komb_rwsem_up_write(&rb_lock)
#define RB_READ_LOCK() komb_rwsem_down_read(&rb_lock)
#define RB_READ_UNLOCK() komb_rwsem_up_read(&rb_lock)
#endif
#define RB_BACKEND 1
#else
#ifdef RB_MUTEX
#include <linux/mutex.h>
static struct mutex rb_lock __aligned(64) = __MUTEX_INITIALIZER(rb_lock);
#define RB_WRITE_LOCK() (mutex_lock)(&rb_lock)
#define RB_WRITE_UNLOCK() (mutex_unlock)(&rb_lock)
#define RB_READ_LOCK() (mutex_lock)(&rb_lock)
#define RB_READ_UNLOCK() (mutex_unlock)(&rb_lock)
#else
#include <linux/rwsem.h>
static DECLARE_RWSEM(rb_lock);
#define RB_WRITE_LOCK() down_write(&rb_lock)
#define RB_WRITE_UNLOCK() up_write(&rb_lock)
#define RB_READ_LOCK() down_read(&rb_lock)
#define RB_READ_UNLOCK() up_read(&rb_lock)
#endif
#define RB_BACKEND 0
#endif

static int rb_prepare(void) { return 0; }

static void rb_lock_snapshot(struct rw_bench_snapshot *s)
{
	s->lock_addr = (unsigned long)&rb_lock;
	s->gate_addr = s->lock_addr;
#if defined(RB_KDLOCK) && defined(RB_MUTEX)
	s->gate = READ_ONCE(rb_lock.tail) || READ_ONCE(rb_lock.owner);
#elif defined(RB_KDLOCK)
	s->cnts = kd_rw_admission_readers(&rb_lock.core);
	s->gate = READ_ONCE(rb_lock.core.queue.tail) || READ_ONCE(rb_lock.core.queue.owner) ||
		READ_ONCE(rb_lock.core.writer) || READ_ONCE(rb_lock.core.writer_pending) ||
		atomic_long_read(&rb_lock.core.admission) || !list_empty(&rb_lock.core.read_waiters) ||
		!list_empty(&rb_lock.core.active_reads);
#elif defined(RB_TCLOCK) && defined(RB_MUTEX)
	s->gate = READ_ONCE(rb_lock.tail) || READ_ONCE(rb_lock.locked) || READ_ONCE(rb_lock.combiner_task);
#elif defined(RB_TCLOCK)
	s->cnts = atomic_long_read(&rb_lock.cnts);
	s->gate = atomic_read(&rb_lock.reader_wait_lock.val) || READ_ONCE(rb_lock.writer_tail);
#elif defined(RB_MUTEX)
	s->gate = mutex_is_locked(&rb_lock);
#else
	s->gate = rwsem_is_locked(&rb_lock);
#endif
}
#endif
