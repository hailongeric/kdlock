/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_DIRECT_H
#define KD_SPIN_DIRECT_H

#include <asm/asm.h>
#include "kd_spin_type.h"
#include "exe_info.h"

int kd_spin_prepare(kd_spinlock_t *lock, unsigned long ip, unsigned int abi);
void kd_spin_lock_clobber_v1(kd_spinlock_t *, unsigned long, unsigned long,
			   unsigned long);
void kd_spin_unlock_clobber_v1(kd_spinlock_t *, unsigned long, unsigned long,
			     unsigned long);

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

#endif
