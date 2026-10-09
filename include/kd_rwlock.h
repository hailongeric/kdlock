/* SPDX-License-Identifier: GPL-2.0 */
/* Reader/writer admission derived from TCLocks komb_rwlock.c.
 * Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi */
#ifndef KD_RWLOCK_H
#define KD_RWLOCK_H

#include <linux/errno.h>
#include <linux/spinlock.h>
#include "kd_spin_direct.h"

/* Ordinary task-context reader/writer spin lock, inspired by TCLock's
 * komb_rwlock. Readers execute concurrently on their own CPUs. The embedded
 * KD gate queues writers and slow readers; writer bodies use the existing
 * spin clobber-v1 JIT, source leases, packets and completion/ACK protocol.
 *
 * Every writer takes the gate, including uncontended writers. This avoids a
 * second physical-owner route and lets native and JIT writers share exactly
 * the same exclusion protocol. Never use Linux spin/rwlock APIs on this object.
 * Recursive reads, upgrades and IRQ/BH use are unsupported. Storage must live
 * until all readers, writers, queued requests and retained frames have drained.
 */
#define KD_RWLOCK_WRITER_LOCKED  0xffU
#define KD_RWLOCK_WRITER_WAITING 0x100U
#define KD_RWLOCK_WRITER_MASK   0x1ffU
#define KD_RWLOCK_READER_BIAS   0x200U

typedef struct kd_rwlock {
	union {
		atomic_t cnts;
		/* x86_64 little-endian: clear only writer ownership on release.
		 * Speculative reader increments in the upper bits must survive. */
		u8 wlocked;
	};
	kd_spinlock_t gate;
} kd_rwlock_t;

#define KD_RWLOCK_INITIALIZER { .cnts = ATOMIC_INIT(0), \
	.gate = KD_SPINLOCK_INITIALIZER }
#define DEFINE_KD_RWLOCK(name) kd_rwlock_t name = KD_RWLOCK_INITIALIZER

static inline void kd_rwlock_init(kd_rwlock_t *lock)
{
	atomic_set(&lock->cnts, 0);
	kd_spin_init(&lock->gate);
}

static __always_inline void kd_read_lock(kd_rwlock_t *lock)
{
	u32 cnts;

	preempt_disable();
	cnts = atomic_add_return_acquire(KD_RWLOCK_READER_BIAS, &lock->cnts);
	if (likely(!(cnts & KD_RWLOCK_WRITER_MASK)))
		return;

	/* Do not wait in the admission queue while counted as an active reader:
	 * its writer head may already be waiting for that count to reach zero. */
	atomic_sub(KD_RWLOCK_READER_BIAS, &lock->cnts);
	kd_spin_direct_native_lock_inline(&lock->gate);
	/* All writers own the gate until after clearing their writer byte, so
	 * holding it is sufficient to admit this reader. The acquisition pin
	 * remains live after releasing the gate, through the whole read body. */
	atomic_add(KD_RWLOCK_READER_BIAS, &lock->cnts);
	kd_spin_direct_native_release_inline(&lock->gate);
}

static __always_inline void kd_read_unlock(kd_rwlock_t *lock)
{
	(void)atomic_sub_return_release(KD_RWLOCK_READER_BIAS, &lock->cnts);
	preempt_enable();
}

/* Called with the gate held, on either the physical caller or a JIT executor.
 * Keep this inline: its atomics and reader-drain loop are part of the prepared
 * continuation, not an ordinary CALL that would force native continuation.
 * Only the gate owner can publish WAITING. Once published, arriving readers
 * withdraw their speculative count and queue, allowing existing readers to
 * drain. The acquire observation pairs with the final reader's release. */
static __always_inline void kd_rwlock_writer_enter(kd_rwlock_t *lock)
{
	if (atomic_cmpxchg_acquire(&lock->cnts, 0,
				 KD_RWLOCK_WRITER_LOCKED) == 0)
		return;
	atomic_add(KD_RWLOCK_WRITER_WAITING, &lock->cnts);
	do {
		atomic_cond_read_acquire(&lock->cnts,
					VAL == KD_RWLOCK_WRITER_WAITING);
	} while (atomic_cmpxchg_relaxed(&lock->cnts, KD_RWLOCK_WRITER_WAITING,
					KD_RWLOCK_WRITER_LOCKED) !=
		 KD_RWLOCK_WRITER_WAITING);
}

static __always_inline void kd_rwlock_writer_exit(kd_rwlock_t *lock)
{
	smp_store_release(&lock->wlocked, 0);
}

/* Explicit native writer pair, useful before publication and for controls.
 * Delegating callers use the macros below so the compiler, not a C adapter,
 * owns spills across both continuation boundaries. */
static __always_inline void kd_write_lock(kd_rwlock_t *lock)
{
	preempt_disable();
	kd_spin_direct_native_lock_inline(&lock->gate);
	kd_rwlock_writer_enter(lock);
}

static __always_inline void kd_write_unlock(kd_rwlock_t *lock)
{
	kd_rwlock_writer_exit(lock);
	kd_spin_direct_native_release_inline(&lock->gate);
	preempt_enable();
}

static inline int kd_rwlock_prepare(kd_rwlock_t *lock, unsigned long ip,
				   unsigned int abi)
{
	if (!lock)
		return -EINVAL;
	return kd_spin_prepare(&lock->gate, ip, abi);
}

#define kd_rwlock_direct_cookie kd_spin_direct_cookie

/* The prepared RIP includes writer admission as well as the user's body.
 * Release the writer byte BEFORE the spin completion endpoint. A delegated
 * waiter resumes AFTER that endpoint: it must never clear a successor's byte.
 * Use a unique named continuation in a noipa function, as for direct spin. */
#define KD_RWLOCK_DIRECT_WRITE_LOCK(lock, cookie, continuation) do { \
	kd_rwlock_t *kd_rw_acquire = (lock); \
	KD_SPIN_DIRECT_LOCK(&kd_rw_acquire->gate, cookie, continuation); \
	kd_rwlock_writer_enter(kd_rw_acquire); \
} while (0)

#define KD_RWLOCK_DIRECT_WRITE_UNLOCK(lock, cookie) do { \
	kd_rwlock_t *kd_rw_release = (lock); \
	kd_rwlock_writer_exit(kd_rw_release); \
	KD_SPIN_DIRECT_UNLOCK(&kd_rw_release->gate, cookie); \
} while (0)

#endif
