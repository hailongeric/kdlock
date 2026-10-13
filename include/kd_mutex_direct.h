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
unsigned long kd_mutex_outer_contended_clobber_v1(struct mutex *, unsigned long,
												  unsigned long, unsigned long);
struct kd_mutex;
struct kd_mutex *kd_mutex_outer_preflight(struct mutex *);
unsigned long kd_mutex_outer_prepared_clobber_v1(struct mutex *, unsigned long,
		unsigned long, unsigned long, struct kd_mutex *);
void kd_mutex_direct_unlock_clobber_v1(struct mutex *, unsigned long,
									   unsigned long, unsigned long);

/* ABI2: compiler-owned spills and the existing lock/SP/IP/BP arguments.
 * The ordinary mutex may sleep; the queue implementation owns waiter pinning.
 * A named continuation is used only once, in a noipa workload function. */
#define KD_MUTEX_DIRECT_CALL(symbol, lock, continuation)            \
	do                                                              \
	{                                                               \
		struct mutex *kd_arg = (lock);                              \
		unsigned long kd_sp, kd_ip, kd_bp;                          \
		asm volatile("movq %%rsp, %%rsi\n\t"                        \
					 "leaq 1f(%%rip), %%rdx\n\t"                    \
					 "movq %%rbp, %%rcx\n\t"                        \
					 "call " #symbol "\n\t1:\n\t" continuation      \
					 : "+D"(kd_arg), "=S"(kd_sp), "=d"(kd_ip),      \
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
 * exact owner pointer; zero means route through the provider, not unowned. */
struct kd_mutex_outer_cookie
{
	unsigned long owner;
};

/* Experimental caller-side capture policy. Preserve the public packet ABI:
 * the JIT root starts before the restores, so every callee-saved input is
 * defined by the saved stack, never by an uncaptured incoming register.
 * Reserve six words to preserve the caller's stack alignment. The paired
 * unlock saves the same registers before its control CALL: COMPLETE resumes
 * at those restores, where ordinary C code can again rely on its registers.
 * Moving only the lock saves would make minimal completion unsafe. */
#ifndef KD_MUTEX_OUTER_LAZY_SAVE
#define KD_MUTEX_OUTER_LAZY_SAVE 0
#endif
#if KD_MUTEX_OUTER_LAZY_SAVE
#define KD_MUTEX_OUTER_SAVE_GPRS                                      \
	"subq $8, %%rsp\n\t"                                           \
	"pushq %%rbx\n\tpushq %%r12\n\tpushq %%r13\n\t"                \
	"pushq %%r14\n\tpushq %%r15\n\t"
#define KD_MUTEX_OUTER_RESTORE_GPRS                                   \
	"popq %%r15\n\tpopq %%r14\n\tpopq %%r13\n\t"                   \
	"popq %%r12\n\tpopq %%rbx\n\taddq $8, %%rsp\n\t"
#define KD_MUTEX_OUTER_CALLEE_CLOBBERS
#else
#define KD_MUTEX_OUTER_SAVE_GPRS ""
#define KD_MUTEX_OUTER_RESTORE_GPRS ""
#define KD_MUTEX_OUTER_CALLEE_CLOBBERS "rbx", "r12", "r13", "r14", "r15",
#endif

#ifndef KD_MUTEX_OUTER_PREFLIGHT
#define KD_MUTEX_OUTER_PREFLIGHT 0
#endif
#if KD_MUTEX_OUTER_PREFLIGHT
#if !KD_MUTEX_OUTER_LAZY_SAVE
#error "KD_MUTEX_OUTER_PREFLIGHT requires KD_MUTEX_OUTER_LAZY_SAVE"
#endif
/* The ordinary helper either owns Linux's mutex or returns a non-owning
 * shadow hint. Capture and resource acquisition occur only for the latter. */
#define KD_MUTEX_OUTER_BEFORE_CAPTURE(lock, cookie, native_owner)             \
	register struct kd_mutex *kd_prepared asm("r8") =                        \
		kd_mutex_outer_preflight(lock);                                     \
	if (!kd_prepared) {                                                     \
		WRITE_ONCE((cookie).owner, native_owner);                            \
		break;                                                             \
	}
#define KD_MUTEX_OUTER_CAPTURE_CALL "call kd_mutex_outer_prepared_clobber_v1\n\t"
#define KD_MUTEX_OUTER_PREPARED_OUTPUT "+r"(kd_prepared),
#define KD_MUTEX_OUTER_LOCK_R8_CLOBBER
#else
#define KD_MUTEX_OUTER_BEFORE_CAPTURE(lock, cookie, native_owner)
#define KD_MUTEX_OUTER_CAPTURE_CALL "call kd_mutex_outer_contended_clobber_v1\n\t"
#define KD_MUTEX_OUTER_PREPARED_OUTPUT
#define KD_MUTEX_OUTER_LOCK_R8_CLOBBER "r8",
#endif

static __always_inline bool
kd_mutex_outer_trylock(struct mutex *lock, unsigned long owner)
{
	unsigned long zero = 0;

	/* A combiner keeps the original mutex across many bodies. Failed locked
	 * RMWs from every producer would repeatedly invalidate its owner line.
	 * The read only declines a busy mutex; the zero-owner CAS still decides
	 * acquisition and preserves Linux's WAITERS/HANDOFF/PICKUP semantics. */
	return !atomic_long_read(&lock->owner) &&
	       atomic_long_try_cmpxchg_acquire(&lock->owner, &zero, owner);
}

#define KD_MUTEX_OUTER_LOCK(lock, cookie, continuation)                       \
	do                                                                        \
	{                                                                         \
		struct mutex *kd_outer_lock = (lock);                                 \
		unsigned long kd_native_owner = (unsigned long)current;               \
		might_sleep();                                                        \
		if (kd_mutex_outer_trylock(kd_outer_lock, kd_native_owner))           \
		{                                                                     \
			kd_hotlock_mutex_entry();                                         \
			WRITE_ONCE((cookie).owner, kd_native_owner);                      \
		}                                                                     \
		else                                                                  \
		{                                                                     \
			unsigned long kd_sp, kd_ip, kd_bp, kd_route;                      \
			KD_MUTEX_OUTER_BEFORE_CAPTURE(kd_outer_lock, cookie, kd_native_owner) \
			/* The physical return consumes an exact acquisition result. The  \
			 * separate JIT entry defines ROUTED without any incoming GPR. */ \
			asm volatile(KD_MUTEX_OUTER_SAVE_GPRS                             \
						 "movq %%rsp, %%rsi\n\t"                              \
						 "leaq 1f(%%rip), %%rdx\n\t"                          \
						 "movq %%rbp, %%rcx\n\t"                              \
						 KD_MUTEX_OUTER_CAPTURE_CALL                          \
						 "jmp 2f\n\t1:\n\t" continuation                      \
						 "xorl %%eax, %%eax\n\t2:\n\t"                        \
						 KD_MUTEX_OUTER_RESTORE_GPRS                          \
						 : "=a"(kd_route), "+D"(kd_outer_lock),               \
						   "=S"(kd_sp), "=d"(kd_ip), "=c"(kd_bp),             \
						   KD_MUTEX_OUTER_PREPARED_OUTPUT ASM_CALL_CONSTRAINT   \
						 :                                                    \
						 : KD_MUTEX_OUTER_CALLEE_CLOBBERS                      \
						   KD_MUTEX_OUTER_LOCK_R8_CLOBBER                     \
						   "r9", "r10", "r11", "cc", "memory");               \
			WRITE_ONCE((cookie).owner, kd_route);                             \
		}                                                                     \
	} while (0)

/* Both physical return and JIT COMPLETE resume before these local restores.
 * The direct/nested API retains its original full-clobber compiler contract. */
#define KD_MUTEX_OUTER_ROUTED_UNLOCK(lock)                             \
	do                                                                  \
	{                                                                   \
		struct mutex *kd_arg = (lock);                                  \
		unsigned long kd_sp, kd_ip, kd_bp;                              \
		asm volatile(KD_MUTEX_OUTER_SAVE_GPRS                           \
					 "movq %%rsp, %%rsi\n\t"                              \
					 "leaq 1f(%%rip), %%rdx\n\t"                          \
					 "movq %%rbp, %%rcx\n\t"                              \
					 "call kd_mutex_direct_unlock_clobber_v1\n\t1:\n\t"    \
					 KD_MUTEX_OUTER_RESTORE_GPRS                          \
					 : "+D"(kd_arg), "=S"(kd_sp), "=d"(kd_ip),             \
					   "=c"(kd_bp), ASM_CALL_CONSTRAINT                   \
					 :                                                    \
					 : KD_MUTEX_OUTER_CALLEE_CLOBBERS                      \
					   "rax", "r8", "r9", "r10", "r11", "cc", "memory");  \
	} while (0)

/* Both branches end at known mutex control CALLs. An inline native release
 * CAS could succeed without a CALL and pull the caller's canary/epilogue into
 * the conservative translated CFG. The original function supplies its exact
 * owner/flags slowpath while bypassing the KD task-routing lookup. */
#define KD_MUTEX_OUTER_UNLOCK(lock, cookie)                            \
	do                                                                 \
	{                                                                  \
		struct mutex *kd_outer_lock = (lock);                          \
		unsigned long kd_native_owner = READ_ONCE((cookie).owner);     \
		if (kd_native_owner)                                           \
		{                                                              \
			(mutex_unlock)(kd_outer_lock);                             \
			/* Retain a CALL boundary even when last in the caller. */ \
			asm volatile("" : : : "memory");                           \
		}                                                              \
		else                                                           \
		{                                                              \
			KD_MUTEX_OUTER_ROUTED_UNLOCK(kd_outer_lock);               \
		}                                                              \
	} while (0)

#endif
