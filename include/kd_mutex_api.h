/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_MUTEX_API_H
#define KDLOCK_MUTEX_API_H

#ifndef __ASSEMBLY__
#include <linux/compiler.h>
#include <asm/asm.h>

struct kd_mutex;
struct kd_mutex_entry;

/* Distinct operation targets. Native admission runs before lending source. */
void kd_mutex_lock_entry_asm(struct kd_mutex *lock,
		unsigned long source_sp, unsigned long continuation_ip,
		unsigned long source_bp);
void kd_mutex_unlock_entry_asm(struct kd_mutex *lock,
		unsigned long source_sp, unsigned long continuation_ip,
		unsigned long source_bp);

/*
 * Source-rebuilt ordinary blocking pair. Task-time setup must already provide
 * the complete request/control capacity and admitted task-owned auxiliary stack.
 * Request records are task-provisioned and retained through their exact users.
 * No per-call allocation or public allocation-error result is introduced.
 * Native assembly admits its persistent control on the original stack, then
 * switches away before capture/publication. Translated execution recognizes
 * the distinct entry target before its source CALL and handles it through the
 * common recursive request path; it never runs native admission on another W.
 *
 * The compiler spills live values across this boundary. Capture inputs are
 * DI object, SI pre-CALL SP, DX post-CALL label and CX BP. No other source GPRs
 * are guessed. Native continuation uses current canonical IP/SP/BP. General
 * flags/SIMD follow AS01. All object/source/code and stack-context lifetimes
 * remain required. This source does not enable unprepared tasks, callable,
 * signalable, trylock, I/O, IRQ or PREEMPT_RT lanes.
 */
#define KD_MUTEX_SOURCE_CALL(object, entry_symbol) \
	({ \
		__auto_type kd_mutex_source_object = (object); \
		struct kd_mutex *kd_mutex_arg = kd_mutex_source_object; \
		unsigned long kd_mutex_sp, kd_mutex_ip, kd_mutex_bp; \
		asm volatile("movq %%rsp, %%rsi\n\t" \
			     "leaq 1f(%%rip), %%rdx\n\t" \
			     "movq %%rbp, %%rcx\n\t" \
			     "call " #entry_symbol "\n\t1:\n\t" \
			     : "+D"(kd_mutex_arg), "=S"(kd_mutex_sp), \
			       "=d"(kd_mutex_ip), "=c"(kd_mutex_bp), \
			       ASM_CALL_CONSTRAINT \
			     : \
			     : "rax", "rbx", "r8", "r9", "r10", "r11", \
			       "r12", "r13", "r14", "r15", "cc", "memory"); \
		(void)0; \
	})

#define kd_mutex_lock(object) \
	KD_MUTEX_SOURCE_CALL((object), kd_mutex_lock_entry_asm)
#define kd_mutex_unlock(object) \
	KD_MUTEX_SOURCE_CALL((object), kd_mutex_unlock_entry_asm)

#endif /* !__ASSEMBLY__ */
#endif
