/* SPDX-License-Identifier: GPL-2.0 */
/*
 * kdlock public lock API.
 *
 * Every lock operation is an out-of-line call. That is a protocol
 * requirement, not a style choice: generated code recognises lock
 * operations by their call target, so an inlined release would let a
 * delegated critical section run past its end.
 *
 * "Delegable" entries are assembly stubs (kd_entry.S). While their lock is
 * in delegation mode, a contended caller records its continuation and the
 * lock holder may run the caller's critical section from generated code.
 * All other entries always execute on the calling task.
 *
 * The API covers every variant the Linux 7.0 headers declare for
 * spinlock_t, raw_spinlock_t, rwlock_t, struct mutex, struct ww_mutex and
 * struct rw_semaphore; integration/kd_linux_map.h lists the mapping. The
 * lockdep-only variants (_nested, _nest_lock) have no counterpart here:
 * without lockdep they are the plain operations.
 */
#ifndef _KDLOCK_KD_API_H
#define _KDLOCK_KD_API_H

#include <kdlock/kd_types.h>
#include <asm/asm.h>

/* ---- spinlock --------------------------------------------------------- */

/* Delegable. */
void kd_spin_lock(struct kd_spinlock *l);
void kd_spin_lock_irq(struct kd_spinlock *l);
unsigned long kd_spin_lock_irqsave(struct kd_spinlock *l);
void kd_spin_lock_bh(struct kd_spinlock *l);

/* Never delegated: for raw_spinlock_t users (scheduler, timers, lock internals). */
void kd_raw_spin_lock(struct kd_spinlock *l);
void kd_raw_spin_lock_irq(struct kd_spinlock *l);
unsigned long kd_raw_spin_lock_irqsave(struct kd_spinlock *l);
void kd_raw_spin_lock_bh(struct kd_spinlock *l);

int kd_spin_trylock(struct kd_spinlock *l);
int kd_spin_trylock_bh(struct kd_spinlock *l);
int kd_spin_trylock_irq(struct kd_spinlock *l);
int kd_spin_trylock_irqsave(struct kd_spinlock *l, unsigned long *flags);
void kd_spin_unlock(struct kd_spinlock *l);
void kd_spin_unlock_irq(struct kd_spinlock *l);
void kd_spin_unlock_irqrestore(struct kd_spinlock *l, unsigned long flags);
void kd_spin_unlock_bh(struct kd_spinlock *l);

static inline void kd_spin_lock_init(struct kd_spinlock *l)
{
	atomic_set(&l->q.val, 0);
}

static inline int kd_spin_is_locked(struct kd_spinlock *l)
{
	return READ_ONCE(l->q.locked) != 0;
}

static inline int kd_spin_is_contended(struct kd_spinlock *l)
{
	/* A queue or a pending waiter, as for the native queued spinlock. */
	return (atomic_read(&l->q.val) & ~KD_Q_LOCKED_MASK) != 0;
}

/*
 * arch_spin_*() level, for the few callers that manage preemption
 * themselves. Never delegated; the preempt count is not touched.
 */
void kd_arch_spin_lock(struct kd_spinlock *l);

static inline int kd_arch_spin_trylock(struct kd_spinlock *l)
{
	int old = 0;

	return atomic_try_cmpxchg_acquire(&l->q.val, &old, KD_Q_LOCKED);
}

static inline void kd_arch_spin_unlock(struct kd_spinlock *l)
{
	smp_store_release(&l->q.locked, 0);
}

/* ---- rwlock ----------------------------------------------------------- */

/* Delegable writers. */
void kd_write_lock(struct kd_rwlock *rw);
void kd_write_lock_irq(struct kd_rwlock *rw);
unsigned long kd_write_lock_irqsave(struct kd_rwlock *rw);
void kd_write_lock_bh(struct kd_rwlock *rw);

int kd_write_trylock(struct kd_rwlock *rw);
int kd_write_trylock_irqsave(struct kd_rwlock *rw, unsigned long *flags);
void kd_write_unlock(struct kd_rwlock *rw);
void kd_write_unlock_irq(struct kd_rwlock *rw);
void kd_write_unlock_irqrestore(struct kd_rwlock *rw, unsigned long flags);
void kd_write_unlock_bh(struct kd_rwlock *rw);

/* Readers always execute on their own task. */
void kd_read_lock(struct kd_rwlock *rw);
void kd_read_lock_irq(struct kd_rwlock *rw);
unsigned long kd_read_lock_irqsave(struct kd_rwlock *rw);
void kd_read_lock_bh(struct kd_rwlock *rw);
int kd_read_trylock(struct kd_rwlock *rw);
void kd_read_unlock(struct kd_rwlock *rw);
void kd_read_unlock_irq(struct kd_rwlock *rw);
void kd_read_unlock_irqrestore(struct kd_rwlock *rw, unsigned long flags);
void kd_read_unlock_bh(struct kd_rwlock *rw);

static inline void kd_rwlock_init(struct kd_rwlock *rw)
{
	atomic_set(&rw->cnts, 0);
	atomic_set(&rw->wait.val, 0);
}

/* Somebody is in the slow path, as arch_rwlock_is_contended(). */
static inline int kd_rwlock_is_contended(struct kd_rwlock *rw)
{
	return atomic_read(&rw->wait.val) != 0;
}

/* arch_read/write_*() level: the caller manages preemption. */
void kd_arch_read_lock(struct kd_rwlock *rw);
void kd_arch_write_lock(struct kd_rwlock *rw);

static inline int kd_arch_read_trylock(struct kd_rwlock *rw)
{
	int c = atomic_read(&rw->cnts);

	if (likely(!(c & KD_RW_WMASK))) {
		c = atomic_add_return_acquire(KD_RW_RBIAS, &rw->cnts);
		if (likely(!(c & KD_RW_WMASK)))
			return 1;
		atomic_sub(KD_RW_RBIAS, &rw->cnts);
	}
	return 0;
}

static inline int kd_arch_write_trylock(struct kd_rwlock *rw)
{
	int c = 0;

	return atomic_try_cmpxchg_acquire(&rw->cnts, &c, KD_RW_WLOCKED);
}

static inline void kd_arch_read_unlock(struct kd_rwlock *rw)
{
	(void)atomic_sub_return_release(KD_RW_RBIAS, &rw->cnts);
}

static inline void kd_arch_write_unlock(struct kd_rwlock *rw)
{
	smp_store_release(&rw->wlocked, 0);
}

/* ---- mutex ------------------------------------------------------------ */

/*
 * Delegable. A delegated acquisition returns 0; signals are observed only
 * once the caller parks.
 */
void kd_mutex_lock(struct kd_mutex *m);
int kd_mutex_lock_interruptible(struct kd_mutex *m);
int kd_mutex_lock_killable(struct kd_mutex *m);
void kd_mutex_lock_io(struct kd_mutex *m);

int kd_mutex_trylock(struct kd_mutex *m);
void kd_mutex_unlock(struct kd_mutex *m);
unsigned long kd_mutex_get_owner(struct kd_mutex *m);

static inline void kd_mutex_init(struct kd_mutex *m)
{
	atomic_set(&m->q.val, 0);
	atomic_set(&m->wait_lock.val, 0);
	m->owner = NULL;
	INIT_LIST_HEAD(&m->waiters);
}

static inline bool kd_mutex_is_locked(struct kd_mutex *m)
{
	return READ_ONCE(m->q.locked) != 0;
}

/* ---- ww_mutex --------------------------------------------------------- */

/*
 * Wound/wait mutexes, with the kernel's own acquire context and class
 * (linux/ww_mutex.h). Never delegated. Every class is handled with the
 * wait-die rule: a younger context that already holds a lock backs off
 * (-EDEADLK) instead of waiting for an older one. Callers handle that
 * result the same way for both native algorithms.
 */
void kd_ww_mutex_init(struct kd_ww_mutex *lock, struct ww_class *ww_class);
int kd_ww_mutex_lock(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
int kd_ww_mutex_lock_interruptible(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
void kd_ww_mutex_lock_slow(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
int kd_ww_mutex_lock_slow_interruptible(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
int kd_ww_mutex_trylock(struct kd_ww_mutex *lock, struct ww_acquire_ctx *ctx);
void kd_ww_mutex_unlock(struct kd_ww_mutex *lock);

static inline bool kd_ww_mutex_is_locked(struct kd_ww_mutex *lock)
{
	return kd_mutex_is_locked(&lock->base);
}

/* ---- rwsem ------------------------------------------------------------ */

/* Delegable writers. */
void kd_down_write(struct kd_rwsem *sem);
int kd_down_write_killable(struct kd_rwsem *sem);

int kd_down_write_trylock(struct kd_rwsem *sem);
void kd_up_write(struct kd_rwsem *sem);
void kd_downgrade_write(struct kd_rwsem *sem);

void kd_down_read(struct kd_rwsem *sem);
int kd_down_read_interruptible(struct kd_rwsem *sem);
int kd_down_read_killable(struct kd_rwsem *sem);
int kd_down_read_trylock(struct kd_rwsem *sem);
void kd_up_read(struct kd_rwsem *sem);

static inline void kd_rwsem_init(struct kd_rwsem *sem)
{
	atomic_long_set(&sem->count, 0);
	kd_mutex_init(&sem->m);
}

static inline int kd_rwsem_is_locked(struct kd_rwsem *sem)
{
	return (atomic_long_read(&sem->count) & ~(KD_RWSEM_WWAIT | KD_RWSEM_NEEDWAKE)) != 0;
}

/* Held for writing (rwsem_assert_held_write()). */
static inline int kd_rwsem_is_write_locked(struct kd_rwsem *sem)
{
	return (atomic_long_read(&sem->count) & KD_RWSEM_WLOCKED) != 0;
}

/*
 * Somebody waits in the slow path, as rwsem_is_contended(): a queued writer
 * or reader, or readers registered behind the writer that holds the lock.
 */
static inline int kd_rwsem_is_contended(struct kd_rwsem *sem)
{
	long c = atomic_long_read(&sem->count);

	return atomic_read(&sem->m.q.val) != 0 || !list_empty(&sem->m.waiters) ||
	       ((c & KD_RWSEM_WLOCKED) && (c >> KD_RWSEM_RSHIFT));
}

/* ---- clobber entries --------------------------------------------------- */

/*
 * kd_spin_lock_cl(), kd_spin_unlock_cl(), kd_write_lock_cl(),
 * kd_write_unlock_cl(), kd_mutex_lock_cl(), kd_mutex_unlock_cl(),
 * kd_down_write_cl(), kd_up_write_cl().
 *
 * The same operations as kd_spin_lock() and the others, for call sites
 * whose critical section is worth the most to delegate. The call is made
 * from inline assembly that declares every general register except rsp and
 * rbp lost across it (rbp is the frame pointer). The compiler then keeps
 * nothing in rbx and r12-r15 across the lock and release calls; what it
 * needs afterwards it reloads, and the registers the function itself must
 * preserve are saved once in its prologue, on its own CPU.
 *
 * What that buys: a waiter that queues through such an entry publishes
 * rsp, rbp, its return address and its flags instead of every register,
 * and so does a delegated section that ends at such a release. The
 * combiner then fetches two lines of the waiter's packet instead of four
 * per section, and writes one instead of three when the section ends
 * (struct kd_regs, kind KD_RS_COMPACT).
 *
 * Semantics are those of the ordinary calls, and both kinds of entry can be
 * mixed on one lock and at the two ends of one section: wherever one end is
 * an ordinary call, the full state is kept. Not covered: the irq, irqsave
 * and bh variants, the interruptible and killable ones (they return a value
 * the macros would have to carry) and the readers, which are never
 * delegated.
 *
 * Use them only as calls in C code. The entries they call are not C
 * functions and are declared below as arrays, so that they can neither be
 * called directly nor stored in a function pointer; code that reaches a
 * lock operation through a pointer uses the ordinary functions above.
 *
 * With CONFIG_KDLOCK_CLOBBER_ENTRY off the macros are the ordinary calls.
 */
extern const unsigned char __kd_spin_lock_cl[], __kd_spin_unlock_cl[];
extern const unsigned char __kd_write_lock_cl[], __kd_write_unlock_cl[];
extern const unsigned char __kd_mutex_lock_cl[], __kd_mutex_unlock_cl[];
extern const unsigned char __kd_down_write_cl[], __kd_up_write_cl[];

#ifdef CONFIG_KDLOCK_CLOBBER_ENTRY

#define __KD_CL_LOST	"memory", "cc", "rax", "rcx", "rdx", "rsi", "r8", "r9",	\
			"r10", "r11", "rbx", "r12", "r13", "r14", "r15"

/* rdi carries the lock in and is lost like the others: an in-out operand. */
#define __kd_cl_call(entry, type, lock) do {				\
	type *__kd_cl_lock = (lock);					\
	asm volatile("call " #entry					\
		     : ASM_CALL_CONSTRAINT, "+D" (__kd_cl_lock)		\
		     : : __KD_CL_LOST);					\
} while (0)

#define kd_spin_lock_cl(l)	__kd_cl_call(__kd_spin_lock_cl, struct kd_spinlock, l)
#define kd_spin_unlock_cl(l)	__kd_cl_call(__kd_spin_unlock_cl, struct kd_spinlock, l)
#define kd_write_lock_cl(rw)	__kd_cl_call(__kd_write_lock_cl, struct kd_rwlock, rw)
#define kd_write_unlock_cl(rw)	__kd_cl_call(__kd_write_unlock_cl, struct kd_rwlock, rw)
#define kd_mutex_lock_cl(m)	__kd_cl_call(__kd_mutex_lock_cl, struct kd_mutex, m)
#define kd_mutex_unlock_cl(m)	__kd_cl_call(__kd_mutex_unlock_cl, struct kd_mutex, m)
#define kd_down_write_cl(sem)	__kd_cl_call(__kd_down_write_cl, struct kd_rwsem, sem)
#define kd_up_write_cl(sem)	__kd_cl_call(__kd_up_write_cl, struct kd_rwsem, sem)

#else

#define kd_spin_lock_cl(l)	kd_spin_lock(l)
#define kd_spin_unlock_cl(l)	kd_spin_unlock(l)
#define kd_write_lock_cl(rw)	kd_write_lock(rw)
#define kd_write_unlock_cl(rw)	kd_write_unlock(rw)
#define kd_mutex_lock_cl(m)	kd_mutex_lock(m)
#define kd_mutex_unlock_cl(m)	kd_mutex_unlock(m)
#define kd_down_write_cl(sem)	kd_down_write(sem)
#define kd_up_write_cl(sem)	kd_up_write(sem)

#endif

#endif /* _KDLOCK_KD_API_H */
