/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_DIRECT_H
#define KD_SPIN_DIRECT_H
/* Plain raw_spin_lock semantics: acquisition pins preemption, but does not
 * save/disable IRQs or BH. Callers needing that protection supply it outside. */

#include <asm/asm.h>
#include <linux/percpu.h>
#include "kd_spin_type.h"
#include "kd_hotlock.h"
#include "exe_info.h"

int kd_spin_prepare(kd_spinlock_t *lock, unsigned long ip, unsigned int abi);
void kd_spin_lock_clobber_v1(kd_spinlock_t *, unsigned long, unsigned long,
			   unsigned long);
void kd_spin_unlock_clobber_v1(kd_spinlock_t *, unsigned long, unsigned long,
			     unsigned long);
unsigned int kd_spin_direct_enter(kd_spinlock_t *lock,
				 unsigned int * __percpu *cpu_hot);
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

/* The paired shell preserves C callee-saved registers itself, only on its
 * hot branch. An if around the broad-clobber macro above still makes GCC save
 * all five in the function prologue, including on cold acquisitions.
 *
 * The JIT starts at the POPs: the saved values are ordinary waiter-stack
 * inputs to the unchanged minimal ABI. Its final unlock writes a fresh save
 * area before COMPLETE, and the physical waiter executes the matching POPs.
 * cookie names kd_spin_direct_cookie, the single shared CPU heat view. The
 * C selector reads it after pinning. The continuation does not carry/store a
 * cookie or depend on an uncaptured return register. Unlock reads ownership
 * from the lock byte; neither a heat change nor another lock can reroute it.
 * The named continuation is unique in a noipa caller, as for the old shell. */
#define KD_SPIN_DIRECT_SAVE \
	"pushq %%rbx\n\tpushq %%r12\n\tpushq %%r13\n\t" \
	"pushq %%r14\n\tpushq %%r15\n\t"
#define KD_SPIN_DIRECT_RESTORE \
	"popq %%r15\n\tpopq %%r14\n\tpopq %%r13\n\t" \
	"popq %%r12\n\tpopq %%rbx\n\t"

#define KD_SPIN_DIRECT_LOCK(lock, cookie, continuation) do { \
	kd_spinlock_t *kd_arg = (kd_spinlock_t *)(lock); \
	if (kd_spin_direct_enter(kd_arg, &(cookie))) { \
		unsigned long kd_sp, kd_ip, kd_bp; \
		asm volatile(KD_SPIN_DIRECT_SAVE \
			"movq %%rsp, %%rsi\n\tleaq 1f(%%rip), %%rdx\n\t" \
			"movq %%rbp, %%rcx\n\t" \
			"call kd_spin_lock_pinned_clobber_v1\n\t1:\n\t" continuation \
			KD_SPIN_DIRECT_RESTORE \
			: "+D" (kd_arg), "=S" (kd_sp), \
			  "=d" (kd_ip), "=c" (kd_bp), ASM_CALL_CONSTRAINT \
			: : "rax", "r8", "r9", "r10", "r11", "cc", "memory"); \
	} \
} while (0)

#define KD_SPIN_DIRECT_UNLOCK(lock, cookie) do { \
	kd_spinlock_t *kd_arg = (kd_spinlock_t *)(lock); \
	/* Same shared cookie argument; unlock deliberately does not read heat. */ \
	(void)sizeof(cookie); \
	if (READ_ONCE(kd_arg->locked) != KD_SPIN_DIRECT_NATIVE_HELD) { \
		unsigned long kd_sp, kd_ip, kd_bp; \
		asm volatile(KD_SPIN_DIRECT_SAVE \
			"movq %%rsp, %%rsi\n\tleaq 1f(%%rip), %%rdx\n\t" \
			"movq %%rbp, %%rcx\n\t" \
			"call kd_spin_unlock_clobber_v1\n\t1:\n\t" \
			KD_SPIN_DIRECT_RESTORE \
			: "+D" (kd_arg), "=S" (kd_sp), "=d" (kd_ip), \
			  "=c" (kd_bp), ASM_CALL_CONSTRAINT \
			: : "rax", "r8", "r9", "r10", "r11", "cc", "memory"); \
	} else { \
		kd_spin_direct_native_unlock(kd_arg); \
	} \
} while (0)

#endif
