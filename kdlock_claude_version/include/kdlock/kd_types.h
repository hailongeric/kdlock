/* SPDX-License-Identifier: GPL-2.0 */
/*
 * kdlock lock objects.
 *
 * Every object keeps the size and alignment of the native Linux type it
 * replaces (qspinlock 4, qrwlock 8, mutex 32, rw_semaphore 40 bytes), so
 * structures that embed locks keep their layout.
 */
#ifndef _KDLOCK_KD_TYPES_H
#define _KDLOCK_KD_TYPES_H

#include <linux/types.h>
#include <linux/list.h>
#include <linux/atomic.h>

struct task_struct;

/*
 * Queue word shared by all four families.
 *
 *   locked  0 = free, 1 = held
 *   flags   family specific (mutex: KD_QF_*)
 *   tail    last queued waiter, (cpu + 1) << 2 | node index, 0 = no queue
 *
 * Little-endian layout; x86_64 only.
 */
struct kd_qlock {
	union {
		atomic_t	val;
		struct {
			u8	locked;
			u8	flags;
			u16	tail;
		};
	};
};

#define KD_Q_LOCKED		1U
#define KD_QF_SLEEPERS		0x01	/* mutex: tasks are parked on ->waiters */
#define KD_QF_HANDOFF		0x02	/* mutex: next release goes to the first parked task */
#define KD_QF_SHIFT		8

#define __KD_QLOCK_UNLOCKED	{ { .val = ATOMIC_INIT(0) } }

/* Spinlock: the queue word is the lock. */
struct kd_spinlock {
	struct kd_qlock	q;
};

#define __KD_SPIN_UNLOCKED	{ .q = __KD_QLOCK_UNLOCKED }

/*
 * Rwlock: qrwlock-style count word plus a queue that orders slow-path
 * readers and writers. A combining writer keeps both the writer byte and
 * the queue lock for its whole session.
 */
struct kd_rwlock {
	union {
		atomic_t	cnts;
		struct {
			u8	wlocked;	/* 0xff while write-held */
			u8	__lstate[3];
		};
	};
	struct kd_qlock	wait;
};

#define KD_RW_WLOCKED		0x0ffU
#define KD_RW_WWAIT		0x100U	/* a queued writer waits for readers to leave */
#define KD_RW_WMASK		0x1ffU
#define KD_RW_RSHIFT		9
#define KD_RW_RBIAS		(1U << KD_RW_RSHIFT)

#define __KD_RW_UNLOCKED	{ { .cnts = ATOMIC_INIT(0) }, .wait = __KD_QLOCK_UNLOCKED }

/*
 * Mutex: byte lock with two waiter classes. Pinned waiters spin in the MCS
 * queue behind ->q and may have their critical section executed by the
 * combiner. Waiters that must sleep leave that queue and park on ->waiters.
 */
struct kd_mutex {
	struct kd_qlock		q;
	struct kd_qlock		wait_lock;	/* protects ->waiters */
	struct task_struct	*owner;		/* logical owner, spin heuristic only */
	struct list_head	waiters;
};

#define __KD_MUTEX_INITIALIZER(name) {					\
	.q = __KD_QLOCK_UNLOCKED,					\
	.wait_lock = __KD_QLOCK_UNLOCKED,				\
	.owner = NULL,							\
	.waiters = LIST_HEAD_INIT((name).waiters),			\
}

/*
 * Rwsem: count word plus a mutex used as the ordering queue. ->m.owner is
 * the task holding the queue; it is the one task that may sleep on count.
 */
struct kd_rwsem {
	atomic_long_t	count;
	struct kd_mutex	m;
};

#define KD_RWSEM_WLOCKED	0x01L
#define KD_RWSEM_WWAIT		0x02L	/* queue holder is a writer waiting for readers */
#define KD_RWSEM_NEEDWAKE	0x04L	/* queue holder sleeps on count */
#define KD_RWSEM_WMASK		(KD_RWSEM_WLOCKED | KD_RWSEM_WWAIT)
#define KD_RWSEM_RSHIFT		8
#define KD_RWSEM_RBIAS		(1L << KD_RWSEM_RSHIFT)

#define __KD_RWSEM_INITIALIZER(name) {					\
	.count = ATOMIC_LONG_INIT(0),					\
	.m = __KD_MUTEX_INITIALIZER((name).m),				\
}

#endif /* _KDLOCK_KD_TYPES_H */
