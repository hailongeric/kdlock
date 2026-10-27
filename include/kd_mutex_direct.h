/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_DIRECT_H
#define KD_MUTEX_DIRECT_H

#include <asm/asm.h>
#include "kd_mutex.h"
#include <linux/sched.h>
#include "kd_hotlock.h"
#include "exe_info.h"

int kd_mutex_prepare(struct kd_mutex *, unsigned long, unsigned int);
void kd_mutex_direct_lock_clobber_v1(struct kd_mutex *, unsigned long,
									 unsigned long, unsigned long);
void kd_mutex_direct_contended_clobber_v1(struct kd_mutex *, unsigned long,
										  unsigned long, unsigned long);
unsigned long kd_mutex_outer_contended_clobber_v1(struct kd_mutex *, unsigned long,
												  unsigned long, unsigned long);
void kd_mutex_direct_unlock_clobber_v1(struct kd_mutex *, unsigned long,
									   unsigned long, unsigned long);

/* ABI2: compiler-owned spills and the existing lock/SP/IP/BP arguments.
 * The ordinary mutex may sleep; the queue implementation owns waiter pinning.
 * A named continuation is used only once, in a noipa workload function.
 * __auto_type keeps the capture variable out of scope during its initializer:
 * a caller may itself name its lock pointer kd_arg. The typed second variable
 * retains the original pointer-type check before entering the assembly ABI. */
#define KD_MUTEX_DIRECT_CALL(symbol, lock, continuation)            \
	do                                                              \
	{                                                               \
		__auto_type kd_arg = (lock);                                   \
		struct kd_mutex *kd_lock_arg = kd_arg;                         \
		unsigned long kd_sp, kd_ip, kd_bp;                          \
		asm volatile("movq %%rsp, %%rsi\n\t"                        \
					 "leaq 1f(%%rip), %%rdx\n\t"                    \
					 "movq %%rbp, %%rcx\n\t"                        \
					 "call " #symbol "\n\t1:\n\t" continuation "\n\t" \
					 : "+D"(kd_lock_arg), "=S"(kd_sp), "=d"(kd_ip), \
					   "=c"(kd_bp), ASM_CALL_CONSTRAINT             \
					 :                                              \
					 : "rax", "rbx", "r8", "r9", "r10", "r11",      \
					   "r12", "r13", "r14", "r15", "cc", "memory"); \
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
 * exact owner pointer; zero means route through the provider, not unowned.
 * Only this caller's logical execution accesses the cookie; the polling origin
 * does not access it while the delegated body owns the transferred frame.
 * Ordinary C accesses leave this
 * private value in compiler-owned registers or spills. It is not a published
 * lock word and requires no READ_ONCE/WRITE_ONCE access. The clobber boundary
 * still defines its exact result before either continuation consumes it. */
struct kd_mutex_outer_cookie
{
	unsigned long owner;
};

static __always_inline bool
kd_mutex_outer_trylock(struct kd_mutex *lock, unsigned long owner)
{
	/* A combiner keeps KD physical exclusion across many bodies. Failed locked
	 * RMWs from every producer would repeatedly invalidate its owner line.
	 * The read only declines a busy mutex; the zero-owner CAS still decides
	 * acquisition and preserves the KD WAITERS/HANDOFF/PICKUP flags.
	 * Bound the probes so brief clashes can resolve before queue admission.
	 * An active combiner receives new work immediately. A lone gate owner
	 * may finish its local body during the short retry window. The observed
	 * gate state is only a hint, never permission to acquire or retire.
	 * Busy owners receive reads rather than repeated locked RMWs. Exhaustion
	 * enters the unchanged legacy admission and pinned-waiter protocol. */
	for (unsigned int probe = 0; probe < 8; probe++) {
		unsigned long zero = 0;

		if (!atomic_long_read(&lock->owner) &&
		    atomic_long_try_cmpxchg_acquire(&lock->owner, &zero, owner))
			return true;
		/* This is the same read-only hint as the exported helper. Keep it
		 * inline in every producer's bounded probe sequence. */
		if (atomic_read_acquire(&lock->delegation_state) ==
		    KD_MUTEX_GATE_COMBINER)
			return false;
		cpu_relax();
	}
	return false;
}

#define KD_MUTEX_OUTER_LOCK(lock, cookie, continuation)                       \
	do                                                                        \
	{                                                                         \
		struct kd_mutex *kd_outer_lock = (lock);                                 \
		unsigned long kd_native_owner = (unsigned long)current;               \
		might_sleep();                                                        \
		if (kd_mutex_outer_trylock(kd_outer_lock, kd_native_owner))           \
		{                                                                     \
			kd_hotlock_mutex_entry();                                         \
			(cookie).owner = kd_native_owner;                                 \
		}                                                                     \
		else                                                                  \
		{                                                                     \
			unsigned long kd_sp, kd_ip, kd_bp, kd_route;                      \
			/* The physical return consumes an exact acquisition result. The  \
			 * separate JIT entry defines ROUTED without any incoming GPR. */ \
			asm volatile("movq %%rsp, %%rsi\n\t"                              \
						 "leaq 1f(%%rip), %%rdx\n\t"                          \
						 "movq %%rbp, %%rcx\n\t"                              \
						 "call kd_mutex_outer_contended_clobber_v1\n\t"       \
						 "jmp 2f\n\t1:\n\t" continuation "\n\t"              \
						 "xorl %%eax, %%eax\n\t2:\n\t"                        \
						 : "=a"(kd_route), "+D"(kd_outer_lock),               \
						   "=S"(kd_sp), "=d"(kd_ip), "=c"(kd_bp),             \
						   ASM_CALL_CONSTRAINT                                \
						 :                                                    \
						 : "rbx", "r8", "r9", "r10", "r11",                   \
						   "r12", "r13", "r14", "r15", "cc", "memory");       \
			(cookie).owner = kd_route;                                        \
		}                                                                     \
	} while (0)

/* Both branches end at known mutex control CALLs. An inline native release
 * CAS could succeed without a CALL and pull the caller's canary/epilogue into
 * the conservative translated CFG. The KD local function supplies its exact
 * owner/flags slowpath while bypassing the KD task-routing lookup. */
#define KD_MUTEX_OUTER_UNLOCK(lock, cookie)                            \
	do                                                                 \
	{                                                                  \
		struct kd_mutex *kd_outer_lock = (lock);                          \
		unsigned long kd_native_owner = (cookie).owner;                 \
		if (kd_native_owner)                                           \
		{                                                              \
			kd_mutex_local_unlock(kd_outer_lock);                             \
			/* Retain a CALL boundary even when last in the caller. */ \
			asm volatile("" : : : "memory");                           \
		}                                                              \
		else                                                           \
		{                                                              \
			KD_MUTEX_DIRECT_UNLOCK(kd_outer_lock);                     \
		}                                                              \
	} while (0)

#endif
