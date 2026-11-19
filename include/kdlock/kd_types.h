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
 * Queue word shared by all four families. The layout is that of the native
 * queued spinlock, so the spin class can use the same algorithm when it does
 * not delegate.
 *
 *   locked   0 = free; KD_Q_LOCKED while held, plus holder-owned mode bits
 *   pending  spin class: one waiter spins on ->locked outside the queue
 *   flags    sleepable class (same byte): KD_QF_*
 *   tail     last queued waiter, (cpu + 1) << 2 | node index, 0 = no queue
 *
 * Little-endian layout; x86_64 only.
 */
struct kd_qlock {
	union {
		atomic_t	val;
		struct {
			u8	locked;
			union {
				u8	pending;
				u8	flags;
			};
			u16	tail;
		};
		u16		locked_pending;
	};
};

/*
 * ->locked. Only the holder writes this byte while the lock is held, and a
 * release clears all of it.
 *
 * KD_Q_DELEG (spin class): the queue is deep enough for delegation to pay
 * off; contended callers publish their continuation while they see it.
 */
#define KD_Q_LOCKED		0x01U
#define KD_Q_DELEG		0x02U
#define KD_Q_LOCKED_MASK	0x000000ffU
#define KD_Q_PENDING_VAL	0x00000100U
#define KD_Q_PENDING_MASK	0x0000ff00U
#define KD_Q_LOCKED_PENDING_MASK 0x0000ffffU
#define KD_Q_TAIL_SHIFT		16

/* ->flags of a mutex queue word (changed with atomic operations only). */
#define KD_QF_SLEEPERS		0x01	/* tasks are parked on ->waiters */
#define KD_QF_HANDOFF		0x02	/* next release goes to the first parked task */
#define KD_QF_DELEG		0x04	/* delegation mode, as KD_Q_DELEG */
/*
 * The holder received its section back from a combiner, which now waits at
 * the queue head as a delegable waiter; the holder's release takes the
 * head role over (role exchange, kd_release_combine() in kd_core.c).
 */
#define KD_QF_XHEAD		0x08
/*
 * The first parked task has been woken, or is spinning, and has not gone
 * back to sleep since: it looks at the lock again before it sleeps, so a
 * release need not wake it (kd_mutex_sleep() in kd_mutex.c). Set and
 * cleared under ->wait_lock only.
 */
#define KD_QF_WOKEN		0x10
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
#define KD_RWSEM_XHEAD		0x08L	/* as KD_QF_XHEAD, for the write holder */
#define KD_RWSEM_HANDOFF	0x10L	/* the sleeping queue holder waited long: no write stealing */
#define KD_RWSEM_WMASK		(KD_RWSEM_WLOCKED | KD_RWSEM_WWAIT)
#define KD_RWSEM_RSHIFT		8
#define KD_RWSEM_RBIAS		(1L << KD_RWSEM_RSHIFT)

#define __KD_RWSEM_INITIALIZER(name) {					\
	.count = ATOMIC_LONG_INIT(0),					\
	.m = __KD_MUTEX_INITIALIZER((name).m),				\
}

/*
 * Wound/wait mutex: a mutex plus the acquire context that holds it. The
 * context and class types are the kernel's own (linux/ww_mutex.h).
 */
struct ww_acquire_ctx;
struct ww_class;

struct kd_ww_mutex {
	struct kd_mutex		base;
	struct ww_acquire_ctx	*ctx;
};

#endif /* _KDLOCK_KD_TYPES_H */
