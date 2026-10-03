/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_DIRECT_H
#define KD_MUTEX_DIRECT_H

#include <asm/asm.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include "kd_hotlock.h"
#include "exe_info.h"

int kd_mutex_prepare(struct mutex *, unsigned long, unsigned int);
void kd_mutex_direct_lock_clobber_v1(struct mutex *, unsigned long,
				   unsigned long, unsigned long);
void kd_mutex_direct_contended_clobber_v1(struct mutex *, unsigned long,
					unsigned long, unsigned long);
void kd_mutex_direct_unlock_clobber_v1(struct mutex *, unsigned long,
				     unsigned long, unsigned long);

/* ABI2: compiler-owned spills and the existing lock/SP/IP/BP arguments.
 * The ordinary mutex may sleep; the queue implementation owns waiter pinning.
 * A named continuation is used only once, in a noipa workload function. */
#define KD_MUTEX_DIRECT_CALL(symbol, lock, continuation) do {               \
	struct mutex *kd_arg = (lock);                                      \
	unsigned long kd_sp, kd_ip, kd_bp;                                  \
	asm volatile("movq %%rsp, %%rsi\n\t"                                \
		     "leaq 1f(%%rip), %%rdx\n\t"                           \
		     "movq %%rbp, %%rcx\n\t"                              \
		     "call " #symbol "\n\t1:\n\t" continuation             \
		     : "+D" (kd_arg), "=S" (kd_sp), "=d" (kd_ip),          \
		       "=c" (kd_bp), ASM_CALL_CONSTRAINT                    \
		     :                                                       \
		     : "rax", "rbx", "r8", "r9", "r10", "r11",           \
		       "r12", "r13", "r14", "r15", "cc", "memory");       \
} while (0)

#define KD_MUTEX_DIRECT_LOCK(lock, continuation) \
	KD_MUTEX_DIRECT_CALL(kd_mutex_direct_lock_clobber_v1, lock, continuation)
#define KD_MUTEX_DIRECT_UNLOCK(lock) \
	KD_MUTEX_DIRECT_CALL(kd_mutex_direct_unlock_clobber_v1, lock, "")

/* Explicit outer-only pair. Nested locks inside a translated body keep the
 * general KD_MUTEX_DIRECT interface: their owner changes require a KD ledger.
 * This cookie belongs to one lexical acquisition, survives sleeping/migration,
 * and is opaque, same-task and non-transferable: do not copy, modify or reuse
 * it until the matching unlock. A native cookie records this acquisition's
 * exact owner pointer; zero means route through the provider, not unowned. */
struct kd_mutex_outer_cookie {
	unsigned long owner;
};

static __always_inline bool
kd_mutex_outer_trylock(struct mutex *lock, unsigned long owner)
{
	unsigned long zero = 0;

	return atomic_long_try_cmpxchg_acquire(&lock->owner, &zero, owner);
}

#define KD_MUTEX_OUTER_LOCK(lock, cookie, continuation) do {                 \
	struct mutex *kd_outer_lock = (lock);                                       \
	unsigned long kd_native_owner = (unsigned long)current;                     \
	might_sleep();                                                              \
	if (kd_mutex_outer_trylock(kd_outer_lock, kd_native_owner)) {               \
		kd_hotlock_mutex_entry();                                                  \
		WRITE_ONCE((cookie).owner, kd_native_owner);                               \
	} else {                                                                    \
		KD_MUTEX_DIRECT_CALL(kd_mutex_direct_contended_clobber_v1,                 \
				     kd_outer_lock, continuation);                                       \
		/* This store is INSIDE the translated continuation. FULL                  \
		 * recovery and native fallbacks retain the same endpoint. */              \
		WRITE_ONCE((cookie).owner, 0);                                             \
	}                                                                           \
} while (0)

/* Both branches end at known mutex control CALLs. An inline native release
 * CAS could succeed without a CALL and pull the caller's canary/epilogue into
 * the conservative translated CFG. The original function supplies its exact
 * owner/flags slowpath while bypassing the KD task-routing lookup. */
#define KD_MUTEX_OUTER_UNLOCK(lock, cookie) do {                              \
	struct mutex *kd_outer_lock = (lock);                                 \
	unsigned long kd_native_owner = READ_ONCE((cookie).owner);             \
	if (kd_native_owner) {                                               \
		(mutex_unlock)(kd_outer_lock);                                \
		/* Retain a CALL boundary even when last in the caller. */    \
		asm volatile("" : : : "memory");                              \
	} else {                                                            \
		KD_MUTEX_DIRECT_UNLOCK(kd_outer_lock);                        \
	}                                                                   \
} while (0)

#endif
