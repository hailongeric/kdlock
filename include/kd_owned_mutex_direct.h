/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_OWNED_MUTEX_DIRECT_H
#define KD_OWNED_MUTEX_DIRECT_H

#include <asm/asm.h>
#include <linux/sched.h>
#include "kd_mutex.h"
#include "kd_hotlock.h"
#include "exe_info.h"
#include "kd_owned_mutex_cabi.h"

int kd_owned_mutex_prepare(struct kd_mutex *, unsigned long, unsigned int);
int kd_owned_mutex_init_percpu(void);
bool kd_owned_mutex_check_idle(void);
void kd_owned_mutex_exit(void);
#ifdef KDLOCK_SELFTEST
int kd_owned_mutex_wait_selftest(void);
#endif
void kd_owned_mutex_direct_lock_clobber_v1(struct kd_mutex *, unsigned long,
					unsigned long, unsigned long);
void kd_owned_mutex_direct_contended_clobber_v1(struct kd_mutex *, unsigned long,
					      unsigned long, unsigned long);
/* Called only after a failed outer probe. True means physical ownership;
 * false requests ABI2 capture. No preparation resource survives this call. */
bool kd_owned_mutex_outer_preflight_v1(struct kd_mutex *);
/* Capture-first entry: records this failed outer attempt before admission. */
unsigned long kd_owned_mutex_outer_contended_clobber_v1(struct kd_mutex *,
			unsigned long, unsigned long, unsigned long);
/* Prepared-only entry: the ordinary preflight already sampled this attempt. */
unsigned long kd_owned_mutex_outer_prepared_clobber_v1(struct kd_mutex *,
			unsigned long, unsigned long, unsigned long);
void kd_owned_mutex_direct_unlock_clobber_v1(struct kd_mutex *, unsigned long,
					  unsigned long, unsigned long);
unsigned long kd_owned_mutex_outer_lock_cabi_v2(struct kd_mutex *);
void kd_owned_mutex_outer_unlock_cabi_v2(struct kd_mutex *, unsigned long);

/* ABI2 captures only IP/SP/BP. The compiler spills every other live value;
 * neither SELF refusal nor synthetic JIT entry can assume incoming GPRs. */
#define KD_OWNED_MUTEX_DIRECT_CALL(symbol, lock, continuation)                 \
	do {                                                                    \
		struct kd_mutex *kd_arg = (lock);                                  \
		unsigned long kd_sp, kd_ip, kd_bp;                                \
		asm volatile("movq %%rsp, %%rsi\n\t"                               \
			     "leaq 1f(%%rip), %%rdx\n\t"                          \
			     "movq %%rbp, %%rcx\n\t"                              \
			     "call " #symbol "\n\t1:\n\t" continuation             \
			     : "+D"(kd_arg), "=S"(kd_sp), "=d"(kd_ip),             \
			       "=c"(kd_bp), ASM_CALL_CONSTRAINT                    \
			     :                                                      \
			     : "rax", "rbx", "r8", "r9", "r10", "r11",            \
			       "r12", "r13", "r14", "r15", "cc", "memory");       \
	} while (0)

#define KD_OWNED_MUTEX_DIRECT_LOCK(lock, continuation) \
	KD_OWNED_MUTEX_DIRECT_CALL(kd_owned_mutex_direct_lock_clobber_v1, lock, continuation)
#define KD_OWNED_MUTEX_DIRECT_UNLOCK(lock) \
	KD_OWNED_MUTEX_DIRECT_CALL(kd_owned_mutex_direct_unlock_clobber_v1, lock, "")

/* Same-task acquisition cookie. Nonzero proves physical ownership by this
 * acquisition; zero routes a borrowed continuation to its retained executor.
 * Both routes use the owned protocol, including unlock-side combining. */
struct kd_owned_mutex_outer_cookie {
	unsigned long owner;
};

static __always_inline bool
kd_owned_mutex_outer_trylock(struct kd_mutex *lock, unsigned long owner)
{
	unsigned long zero = 0;

	return !atomic_long_read(&lock->owner) &&
		atomic_long_try_cmpxchg_acquire(&lock->owner, &zero, owner);
}

/* Caller selection is compile-time only. The default emits neither a C-gate
 * call nor a runtime policy read, and retains the original sampled endpoint. */
#ifndef KD_OWNED_MUTEX_PREFLIGHT
#define KD_OWNED_MUTEX_PREFLIGHT 0
#endif
#ifndef KD_OWNED_MUTEX_CABI
#define KD_OWNED_MUTEX_CABI 0
#endif
#if KD_OWNED_MUTEX_CABI != 0 && KD_OWNED_MUTEX_CABI != 1
#error "KD_OWNED_MUTEX_CABI must be 0 or 1"
#endif
#if KD_OWNED_MUTEX_CABI && KD_OWNED_MUTEX_PREFLIGHT
#error "Owned ordinary C ABI and ABI2 preflight are separate caller contracts"
#endif
#if KD_OWNED_MUTEX_CABI
#define KD_OWNED_MUTEX_ENTRY_ABI KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2
#define KD_OWNED_MUTEX_PREPARE_IP(label) \
	((unsigned long)(label) - KD_CABI_CALL_STUB_SIZE)
#else
#define KD_OWNED_MUTEX_ENTRY_ABI KD_ENTRY_ABI_MUTEX_CLOBBER_V1
#define KD_OWNED_MUTEX_PREPARE_IP(label) ((unsigned long)(label))
#endif
#if KD_OWNED_MUTEX_PREFLIGHT != 0 && KD_OWNED_MUTEX_PREFLIGHT != 1
#error "KD_OWNED_MUTEX_PREFLIGHT must be 0 or 1"
#endif
#if KD_OWNED_MUTEX_PREFLIGHT
#define KD_OWNED_MUTEX_PREFLIGHT_BRANCH(lock, cookie)                        \
	else if (kd_owned_mutex_outer_preflight_v1(lock)) {                    \
		WRITE_ONCE((cookie).owner, (unsigned long)current);             \
	}
#define KD_OWNED_MUTEX_CAPTURE_CALL \
	"call kd_owned_mutex_outer_prepared_clobber_v1\n\t"
#else
#define KD_OWNED_MUTEX_PREFLIGHT_BRANCH(lock, cookie)
#define KD_OWNED_MUTEX_CAPTURE_CALL \
	"call kd_owned_mutex_outer_contended_clobber_v1\n\t"
#endif

#if !KD_OWNED_MUTEX_CABI
#define KD_OWNED_MUTEX_OUTER_LOCK(lock, cookie, continuation)                  \
	do {                                                                    \
		struct kd_mutex *kd_outer_lock = (lock);                           \
		unsigned long kd_owner;                                            \
		might_sleep();                                                      \
		kd_owner = (unsigned long)current;                                 \
		if (kd_owned_mutex_outer_trylock(kd_outer_lock, kd_owner)) {         \
			kd_hotlock_owned_mutex_entry();                              \
			WRITE_ONCE((cookie).owner, kd_owner);                         \
		}                                                                   \
		KD_OWNED_MUTEX_PREFLIGHT_BRANCH(kd_outer_lock, cookie)               \
		else {                                                              \
			unsigned long kd_sp, kd_ip, kd_bp, kd_route;                  \
			asm volatile("movq %%rsp, %%rsi\n\t"                         \
				     "leaq 1f(%%rip), %%rdx\n\t"                    \
				     "movq %%rbp, %%rcx\n\t"                        \
				     KD_OWNED_MUTEX_CAPTURE_CALL                         \
				     "jmp 2f\n\t1:\n\t" continuation                \
				     "xorl %%eax, %%eax\n\t2:\n\t"                  \
				     : "=a"(kd_route), "+D"(kd_outer_lock),          \
				       "=S"(kd_sp), "=d"(kd_ip), "=c"(kd_bp),       \
				       ASM_CALL_CONSTRAINT                          \
				     :                                                \
				     : "rbx", "r8", "r9", "r10", "r11",             \
				       "r12", "r13", "r14", "r15", "cc", "memory"); \
			WRITE_ONCE((cookie).owner, kd_route);                       \
		}                                                                   \
	} while (0)

/* A real CALL boundary is required at both translated unlock alternatives. */
#define KD_OWNED_MUTEX_OUTER_UNLOCK(lock, cookie)                             \
	do {                                                                    \
		struct kd_mutex *kd_outer_lock = (lock);                           \
		if (READ_ONCE((cookie).owner)) {                                   \
			kd_owned_mutex_outer_unlock_v1(kd_outer_lock);                \
			asm volatile("" : : : "memory");                           \
		} else {                                                            \
			KD_OWNED_MUTEX_DIRECT_UNLOCK(kd_outer_lock);                  \
		}                                                                   \
	} while (0)
#else
/* ABI4 uses Linux local acquisition before KD admission or capture; it does
 * not participate in ABI2's entry-ratio/heat sampling policy.
 * The fixed ordinary-C CALL stub starts at the hardware return PC. A physical
 * SELF return skips arbitrary supplied continuation text. The synthetic entry
 * seeds RAX=0 and reaches that text before writing its borrowed cookie. No
 * nonvolatile clobber forces spills on enclosing native critical sections. */
#define KD_OWNED_MUTEX_OUTER_LOCK(lock, cookie, continuation)                 \
	do {                                                                   \
		struct kd_mutex *kd_arg = (lock);                                \
		unsigned long kd_route;                                         \
		might_sleep();                                                   \
		asm volatile("call kd_owned_mutex_outer_lock_cabi_v2\n\t"        \
			     ".byte 0x48,0x85,0xc0,0x0f,0x85\n\t"                 \
			     ".long 2f - . - 4\n\t" continuation                 \
			     "xorl %%eax, %%eax\n\t2:\n\t"                     \
			     : "=a"(kd_route), "+D"(kd_arg), ASM_CALL_CONSTRAINT \
			     :                                                    \
			     : "rcx", "rdx", "rsi", "r8", "r9", "r10", "r11", \
			       "cc", "memory");                               \
		WRITE_ONCE((cookie).owner, kd_route);                            \
	} while (0)

#define KD_OWNED_MUTEX_OUTER_UNLOCK(lock, cookie)                             \
	do {                                                                   \
		kd_owned_mutex_outer_unlock_cabi_v2((lock),                       \
					 READ_ONCE((cookie).owner));            \
		asm volatile("" : : : "memory");                              \
	} while (0)
#endif

#endif
