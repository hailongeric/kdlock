/* SPDX-License-Identifier: GPL-2.0 */
/* Reader/writer admission derived from TCLocks komb_rwlock.c.
 * Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi */
#ifndef KD_RWLOCK_H
#define KD_RWLOCK_H

#include <linux/errno.h>
#include <linux/hardirq.h>
#include <linux/spinlock.h>
#include "kd_spin_direct.h"

/* Reader/writer spin lock, inspired by TCLock's
 * komb_rwlock. Readers execute concurrently on their own CPUs. The embedded
 * KD gate queues writers and slow readers; writer bodies use the existing
 * spin clobber-v1 JIT, source leases, packets and completion/ACK protocol.
 *
 * Uncontended native writers own a distinct count byte without the gate.
 * Queued and delegated writers own the gate through their whole write body.
 * Never use Linux spin/rwlock APIs on this object.
 * Explicit IRQ/BH pairs execute locally. Task-context recursive reads,
 * upgrades and NMI use are unsupported. Storage must live
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

/* Called only after withdrawing a speculative task-reader count. */
void kd_rwlock_read_slowpath(kd_rwlock_t *lock);

static __always_inline void __kd_read_lock_pinned(kd_rwlock_t *lock)
{
	u32 cnts;

	cnts = atomic_add_return_acquire(KD_RWLOCK_READER_BIAS, &lock->cnts);
	if (likely(!(cnts & KD_RWLOCK_WRITER_MASK)))
		return;

	/* Match native queued rwlocks: an interrupt/BH reader may interrupt a
	 * reader that a queued writer is draining. Joining that writer's gate
	 * would deadlock the interrupted reader. Keep this count and wait only
	 * for actual writer ownership, never for WAITING or the gate. */
	if (unlikely(in_interrupt())) {
		atomic_cond_read_acquire(&lock->cnts, !(VAL & KD_RWLOCK_WRITER_LOCKED));
		return;
	}

	/* Do not wait in the admission queue while counted as an active reader:
	 * its writer head may already be waiting for that count to reach zero. */
	atomic_sub(KD_RWLOCK_READER_BIAS, &lock->cnts);
	kd_rwlock_read_slowpath(lock);
}

static __always_inline void kd_read_lock(kd_rwlock_t *lock)
{
	preempt_disable();
	__kd_read_lock_pinned(lock);
}

static __always_inline void __kd_read_unlock_pinned(kd_rwlock_t *lock)
{
	/* x86's locked SUB supplies release ordering without an unused XADD
	 * result. Keep the release compiler barrier explicit at the API. */
	smp_mb__before_atomic();
	atomic_sub(KD_RWLOCK_READER_BIAS, &lock->cnts);
}

static __always_inline void kd_read_unlock(kd_rwlock_t *lock)
{
	__kd_read_unlock_pinned(lock);
	preempt_enable();
}

/* Try acquisition never joins the gate. A failed speculative reader count
 * retires before restoring the caller's preemption state. */
static __always_inline int kd_read_trylock(kd_rwlock_t *lock)
{
	u32 cnts;

	preempt_disable();
	if (!(atomic_read(&lock->cnts) & KD_RWLOCK_WRITER_MASK)) {
		cnts = atomic_add_return_acquire(KD_RWLOCK_READER_BIAS, &lock->cnts);
		if (!(cnts & KD_RWLOCK_WRITER_MASK))
			return 1;
		atomic_sub(KD_RWLOCK_READER_BIAS, &lock->cnts);
	}
	preempt_enable();
	return 0;
}

/* Called with the gate held, on either the physical caller or a JIT executor.
 * Admission precedes the prepared body, on both native and delegated paths.
 * Only the gate owner can publish WAITING. Once published, task readers
 * withdraw their speculative count and queue; interrupt/BH readers retain
 * theirs to avoid blocking the reader context they interrupted. The acquire
 * observation pairs with the final reader's release. */
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
static __always_inline bool __kd_write_trylock_pinned(kd_rwlock_t *lock)
{
	/* Avoid a failed locked CAS while existing readers/writers are visible. */
	if (atomic_read(&lock->cnts))
		return false;
	this_cpu_inc(kd_spin_fast_cpu.nondelegated);
	if (atomic_cmpxchg_acquire(&lock->cnts, 0, KD_RWLOCK_WRITER_FAST) == 0)
		return true;
	this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	return false;
}

/* Ordinary writer entries retain their existing heat accounting. Explicit
 * IRQ/BH and trylock entries are local and do not enter the heat/JIT path. */
static __always_inline bool kd_rwlock_try_fast_write(kd_rwlock_t *lock)
{
	if (!__kd_write_trylock_pinned(lock))
		return false;
	kd_hotlock_spin_entry_pinned();
	return true;
}

static __always_inline void __kd_write_lock_pinned(kd_rwlock_t *lock)
{
	if (__kd_write_trylock_pinned(lock))
		return;
	kd_spin_direct_native_lock_inline(&lock->gate);
	kd_rwlock_writer_enter(lock);
}

static __always_inline int kd_write_trylock(kd_rwlock_t *lock)
{
	preempt_disable();
	if (__kd_write_trylock_pinned(lock))
		return 1;
	preempt_enable();
	return 0;
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

static __always_inline void __kd_write_unlock_pinned(kd_rwlock_t *lock)
{
	if (READ_ONCE(lock->wlocked) == KD_RWLOCK_WRITER_FAST) {
		kd_rwlock_writer_exit(lock);
		this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	} else {
		kd_rwlock_writer_exit(lock);
		kd_spin_direct_native_release_inline(&lock->gate);
	}
}

static __always_inline void kd_write_unlock(kd_rwlock_t *lock)
{
	__kd_write_unlock_pinned(lock);
	preempt_enable();
}

/* IRQ/BH ownership stays on its acquiring CPU. These local pairs use the
 * same count/gate protocol, but never capture a continuation or enter JIT.
 * Their ordering matches the target non-RT native rwlock interfaces. */
#define __KD_RWLOCK_IRQ_API(mode) \
static __always_inline unsigned long __kd_##mode##_lock_irqsave(kd_rwlock_t *lock) \
{ \
	unsigned long flags; \
	local_irq_save(flags); \
	preempt_disable(); \
	__kd_##mode##_lock_pinned(lock); \
	return flags; \
} \
static __always_inline void __kd_##mode##_unlock_irqrestore(kd_rwlock_t *lock, unsigned long flags) \
{ \
	__kd_##mode##_unlock_pinned(lock); \
	local_irq_restore(flags); \
	preempt_enable(); \
} \
static __always_inline void kd_##mode##_lock_irq(kd_rwlock_t *lock) \
{ \
	local_irq_disable(); \
	preempt_disable(); \
	__kd_##mode##_lock_pinned(lock); \
} \
static __always_inline void kd_##mode##_unlock_irq(kd_rwlock_t *lock) \
{ \
	__kd_##mode##_unlock_pinned(lock); \
	local_irq_enable(); \
	preempt_enable(); \
} \
static __always_inline void kd_##mode##_lock_bh(kd_rwlock_t *lock) \
{ \
	__local_bh_disable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET); \
	__kd_##mode##_lock_pinned(lock); \
} \
static __always_inline void kd_##mode##_unlock_bh(kd_rwlock_t *lock) \
{ \
	__kd_##mode##_unlock_pinned(lock); \
	__local_bh_enable_ip(_RET_IP_, SOFTIRQ_LOCK_OFFSET); \
}
__KD_RWLOCK_IRQ_API(read)
__KD_RWLOCK_IRQ_API(write)
#undef __KD_RWLOCK_IRQ_API

#define kd_read_lock_irqsave(lock, flags) do { \
	typecheck(unsigned long, flags); \
	(flags) = __kd_read_lock_irqsave(lock); \
} while (0)
#define kd_write_lock_irqsave(lock, flags) do { \
	typecheck(unsigned long, flags); \
	(flags) = __kd_write_lock_irqsave(lock); \
} while (0)

#define kd_read_unlock_irqrestore(lock, flags) do { \
	typecheck(unsigned long, flags); \
	__kd_read_unlock_irqrestore((lock), (flags)); \
} while (0)
#define kd_write_unlock_irqrestore(lock, flags) do { \
	typecheck(unsigned long, flags); \
	__kd_write_unlock_irqrestore((lock), (flags)); \
} while (0)

static __always_inline bool
__kd_write_trylock_irqsave(kd_rwlock_t *lock, unsigned long *flags)
{
	local_irq_save(*flags);
	if (kd_write_trylock(lock))
		return true;
	local_irq_restore(*flags);
	return false;
}
#define kd_write_trylock_irqsave(lock, flags) ({ \
	typecheck(unsigned long, flags); \
	__kd_write_trylock_irqsave((lock), &(flags)); \
})

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
