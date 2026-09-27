/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_DIRECT_H
#define KD_MUTEX_DIRECT_H

#include <asm/asm.h>
#include <linux/mutex.h>
#include "exe_info.h"

int kd_mutex_prepare(struct mutex *, unsigned long, unsigned int);
void kd_mutex_direct_lock_clobber_v1(struct mutex *, unsigned long,
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

#endif
