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
 * Uncontended native writers own a distinct count byte without the gate.
 * Queued and delegated writers own the gate through their whole write body.
 * Never use Linux spin/rwlock APIs on this object.
 * Recursive reads, upgrades and IRQ/BH use are unsupported. Storage must live
 * until all readers, writers, queued requests and retained frames have drained.
 */
#define KD_RWLOCK_WRITER_LOCKED  0xffU
#define KD_RWLOCK_WRITER_FAST    0xf0U
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
	/* Queue polling must not share the reader count's cacheline. */
	kd_spinlock_t gate __aligned(64);
} kd_rwlock_t;

#define KD_RWLOCK_INITIALIZER { .cnts = ATOMIC_INIT(0), \
	.gate = KD_SPINLOCK_INITIALIZER }
#define DEFINE_KD_RWLOCK(name) kd_rwlock_t name = KD_RWLOCK_INITIALIZER

static inline void kd_rwlock_init(kd_rwlock_t *lock)
{
	atomic_set(&lock->cnts, 0);
	kd_spin_init(&lock->gate);
}

static inline u32 kd_rwlock_state(kd_rwlock_t *lock)
{
	return atomic_read(&lock->cnts);
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
	/* The count prevents another ungated writer from entering. A fast writer
	 * which won before this increment can still be active: wait for its
	 * release while holding the gate, before allowing the reader body. */
	atomic_add(KD_RWLOCK_READER_BIAS, &lock->cnts);
	atomic_cond_read_acquire(&lock->cnts, !(VAL & KD_RWLOCK_WRITER_LOCKED));
	kd_spin_direct_native_release_inline(&lock->gate);
}

static __always_inline void kd_read_unlock(kd_rwlock_t *lock)
{
	/* x86's locked SUB supplies release ordering without an unused XADD
	 * result. Keep the release compiler barrier explicit at the API. */
	smp_mb__before_atomic();
	atomic_sub(KD_RWLOCK_READER_BIAS, &lock->cnts);
	preempt_enable();
}

/* Called with the gate held, on either the physical caller or a JIT executor.
 * Admission precedes the prepared body, on both native and delegated paths.
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

/* Pinned caller only. The exact native acquisition count remains live through
 * an ungated write, so source/provider drain cannot miss this ownership route.
 * A failed attempt transfers to the gate's ordinary acquisition accounting. */
static __always_inline bool kd_rwlock_try_fast_write(kd_rwlock_t *lock)
{
	/* Avoid a failed locked CAS while existing readers/writers are visible. */
	if (atomic_read(&lock->cnts))
		return false;
	this_cpu_inc(kd_spin_fast_cpu.nondelegated);
	if (atomic_cmpxchg_acquire(&lock->cnts, 0, KD_RWLOCK_WRITER_FAST) == 0) {
		kd_hotlock_spin_entry_pinned();
		return true;
	}
	this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	return false;
}

/* Explicit native writer pair, useful before publication and for controls.
 * Delegating callers use the macros below so the compiler, not a C adapter,
 * owns spills across both continuation boundaries. */
static __always_inline void kd_write_lock(kd_rwlock_t *lock)
{
	preempt_disable();
	if (kd_rwlock_try_fast_write(lock))
		return;
	kd_spin_direct_native_lock_inline(&lock->gate);
	kd_rwlock_writer_enter(lock);
}

static __always_inline void kd_write_unlock(kd_rwlock_t *lock)
{
	if (READ_ONCE(lock->wlocked) == KD_RWLOCK_WRITER_FAST) {
		kd_rwlock_writer_exit(lock);
		this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	} else {
		kd_rwlock_writer_exit(lock);
		kd_spin_direct_native_release_inline(&lock->gate);
	}
	preempt_enable();
}

static inline int kd_rwlock_prepare(kd_rwlock_t *lock, unsigned long ip,
				   unsigned int abi)
{
	if (!lock || abi != KD_ENTRY_ABI_RWLOCK_CLOBBER_V1)
		return -EINVAL;
	return kd_spin_prepare(&lock->gate, ip, abi);
}

#define kd_rwlock_direct_cookie kd_spin_direct_cookie

void kd_rwlock_lock_pinned_clobber_v1(kd_spinlock_t *gate, unsigned long sp,
				    unsigned long ip, unsigned long bp);
void kd_rwlock_fast_write_unlock(kd_rwlock_t *lock);

/* ABI3 starts after writer admission. The pinned native helper acquires the
 * gate and count before returning; a combiner acquires the count before the
 * first JIT dispatch. An unstarted refusal releases that count before retry.
 * Release the writer byte BEFORE the spin completion endpoint. A delegated
 * waiter resumes AFTER that endpoint: it must never clear a successor's byte.
 * Use a unique named continuation in a noipa function, as for direct spin. */
#define KD_RWLOCK_DIRECT_WRITE_LOCK(lock, cookie, continuation) do { \
	kd_rwlock_t *kd_rw_acquire = (lock); \
	preempt_disable(); \
	if (kd_rwlock_try_fast_write(kd_rw_acquire)) { \
		/* The fast writer owns the count byte and its native drain pin. */ \
	} else if (!this_cpu_read(cookie)) { \
		kd_spin_direct_native_lock_inline(&kd_rw_acquire->gate); \
		kd_rwlock_writer_enter(kd_rw_acquire); \
	} else { \
		KD_SPIN_DIRECT_CALL(kd_rwlock_lock_pinned_clobber_v1, \
			&kd_rw_acquire->gate, continuation); \
	} \
} while (0)

#define KD_RWLOCK_DIRECT_WRITE_UNLOCK(lock, cookie) do { \
	kd_rwlock_t *kd_rw_release = (lock); \
	if (READ_ONCE(kd_rw_release->wlocked) == KD_RWLOCK_WRITER_FAST) { \
		kd_rwlock_fast_write_unlock(kd_rw_release); \
		/* Keep a CALL boundary; a tail jump would expose the helper as \
		 * translated source. Delegated writers always own 0xff. */ \
		barrier(); \
	} else { \
		kd_rwlock_writer_exit(kd_rw_release); \
		KD_SPIN_DIRECT_UNLOCK(&kd_rw_release->gate, cookie); \
	} \
} while (0)

#endif
