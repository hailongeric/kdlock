/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_DIRECT_H
#define KD_SPIN_DIRECT_H
/* Plain raw_spin_lock semantics: acquisition pins preemption, but does not
 * save/disable IRQs or BH. Callers needing that protection supply it outside. */

#include <asm/asm.h>
#include <linux/percpu.h>
#include <linux/preempt.h>
#include "kd_spin_type.h"
#include "kd_hotlock.h"
#include "exe_info.h"

int kd_spin_prepare(kd_spinlock_t *lock, unsigned long ip, unsigned int abi);
void kd_spin_lock_clobber_v1(kd_spinlock_t *, unsigned long, unsigned long,
			   unsigned long);
void kd_spin_unlock_clobber_v1(kd_spinlock_t *, unsigned long, unsigned long,
			     unsigned long);
void kd_spin_direct_native_lock(kd_spinlock_t *lock);
void kd_spin_direct_native_unlock(kd_spinlock_t *lock);
void kd_spin_lock_pinned_clobber_v1(kd_spinlock_t *, unsigned long,
				 unsigned long, unsigned long);
/* One shared CPU-hot cookie: a view of the existing rate_hot, not a second
 * flag, an acquisition path, or a nesting counter. Never assign to it here. */
#define kd_spin_direct_cookie kd_hotlock_spin_gate

/* Same compiler-owned spill contract as clobber-v1, with a direct module CALL.
 * The optional named continuation lets preparation register the exact RIP
 * without executing the lock or adding a registration branch to every op.
 * Use each named label once, in a noipa function, to prevent cloning. */
#define KD_SPIN_DIRECT_CALL(symbol, lock, continuation) do {                 \
	kd_spinlock_t *kd_arg = (kd_spinlock_t *)(lock);                 \
	unsigned long kd_sp, kd_ip, kd_bp;                                   \
	asm volatile("movq %%rsp, %%rsi\n\t"                                 \
		     "leaq 1f(%%rip), %%rdx\n\t"                           \
		     "movq %%rbp, %%rcx\n\t"                               \
		     "call " #symbol "\n\t1:\n\t" continuation             \
		     : "+D" (kd_arg), "=S" (kd_sp), "=d" (kd_ip),          \
		       "=c" (kd_bp), ASM_CALL_CONSTRAINT                     \
		     :                                                        \
		     : "rax", "rbx", "r8", "r9", "r10", "r11",           \
		       "r12", "r13", "r14", "r15", "cc", "memory");        \
} while (0)

/* Pin before the inline per-CPU read. The two entries share only the final
 * continuation: cold owns the native word; hot uses the original minimal
 * clobber ABI. Neither branch exports a path cookie or captures extra GPRs.
 * The compiler owns all live-register spills, even if it places them before
 * the branch. Do not insert PUSH/POP adapters into the translated body.
 * cookie is the provider's one per-CPU pointer to the existing rate_hot. */
#define KD_SPIN_DIRECT_LOCK(lock, cookie, continuation) do { \
	kd_spinlock_t *kd_arg = (kd_spinlock_t *)(lock); \
	unsigned int * __percpu *kd_gate = &(cookie); \
	unsigned long kd_ip, kd_bp; \
	preempt_disable(); \
	asm volatile("cmpb $0, kd_spin_cold_fastpath(%%rip)\n\tje 2f\n\t" \
		"cmpb $0, kd_spin_delegate(%%rip)\n\tje 1f\n\t" \
		"movq %%gs:(%%rsi), %%rax\n\tcmpl $0, (%%rax)\n\tjne 2f\n\t" \
		"1: call kd_spin_direct_native_lock\n\tjmp 3f\n\t" \
		"2: movq %%rsp, %%rsi\n\tleaq 3f(%%rip), %%rdx\n\t" \
		"movq %%rbp, %%rcx\n\t" \
		"call kd_spin_lock_pinned_clobber_v1\n\t3:\n\t" continuation \
		: "+D" (kd_arg), "+S" (kd_gate), "=d" (kd_ip), \
		  "=c" (kd_bp), ASM_CALL_CONSTRAINT \
		: : "rax", "rbx", "r8", "r9", "r10", "r11", \
		    "r12", "r13", "r14", "r15", "cc", "memory"); \
} while (0)

#define KD_SPIN_DIRECT_UNLOCK(lock, cookie) do { \
	kd_spinlock_t *kd_unlock_word = (kd_spinlock_t *)(lock); \
	/* Same shared cookie argument; unlock deliberately does not read heat. */ \
	(void)sizeof(cookie); \
	if (READ_ONCE(kd_unlock_word->locked) != KD_SPIN_DIRECT_NATIVE_HELD) \
		KD_SPIN_DIRECT_CALL(kd_spin_unlock_clobber_v1, kd_unlock_word, ""); \
	else \
		kd_spin_direct_native_unlock(kd_unlock_word); \
} while (0)

#endif
