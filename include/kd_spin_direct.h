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
#include "kd_spin_fast.h"
#include "exe_info.h"

int kd_spin_prepare(kd_spinlock_t *lock, unsigned long ip, unsigned int abi);
void kd_spin_lock_clobber_v1(kd_spinlock_t *, unsigned long, unsigned long,
			   unsigned long);
void kd_spin_unlock_clobber_v1(kd_spinlock_t *, unsigned long, unsigned long,
			     unsigned long);
void kd_spin_direct_native_lock(kd_spinlock_t *lock);
void kd_spin_direct_native_contended(kd_spinlock_t *lock, u32 failed);
/* The caller already pinned and selected self-execution. Keep the common CAS
 * here; a failed attempt retains that pin and enters the complete native queue.
 * The drain count stays live through the generic byte-5 unlock. */
static __always_inline void kd_spin_direct_native_lock_inline(kd_spinlock_t *lock)
{
	u32 val;

	this_cpu_inc(kd_spin_fast_cpu.nondelegated);
	val = atomic_cmpxchg_acquire(&lock->val, 0, KD_SPIN_DIRECT_NATIVE_HELD);
	/* Both outcomes count once before any possible MCS publication. */
	kd_hotlock_spin_entry_pinned();
	if (val)
		kd_spin_direct_native_contended(lock, val);
}
void kd_spin_direct_native_unlock(kd_spinlock_t *lock);
void kd_spin_lock_pinned_clobber_v1(kd_spinlock_t *, unsigned long,
				 unsigned long, unsigned long);
/* One shared CPU-hot cookie: the sampler's sole spin gate, not an acquisition
 * path or a nesting counter. Never assign to it here. */
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

/* Selecting this shell opts into CPU-heat routing; provider policy switches
 * are handled by the shared core/sampler. Pin before the per-CPU read.
 * Keep the gate in C so only the hot branch has the broad clobber contract;
 * cold inlines its first CAS and calls the native pending/MCS finisher only
 * on contention. Neither branch exports a path
 * cookie or captures extra GPRs. The named continuation belongs to hot only.
 * The compiler owns all live-register spills, even if it places them before
 * the branch. Do not insert PUSH/POP adapters into the translated body.
 * cookie is the provider's directly addressed per-CPU gate. */
#define KD_SPIN_DIRECT_LOCK(lock, cookie, continuation) do { \
	kd_spinlock_t *kd_lock_word = (kd_spinlock_t *)(lock); \
	preempt_disable(); \
	if (!this_cpu_read(cookie)) \
		kd_spin_direct_native_lock_inline(kd_lock_word); \
	else \
		KD_SPIN_DIRECT_CALL(kd_spin_lock_pinned_clobber_v1, \
				    kd_lock_word, continuation); \
} while (0)

#define KD_SPIN_DIRECT_UNLOCK(lock, cookie) do { \
	kd_spinlock_t *kd_unlock_word = (kd_spinlock_t *)(lock); \
	/* Both ownership kinds use the same clobber/metadata contract. The \
	 * provider handles byte-5 release; JIT sees one completion endpoint. */ \
	(void)sizeof(cookie); \
	KD_SPIN_DIRECT_CALL(kd_spin_unlock_clobber_v1, kd_unlock_word, ""); \
} while (0)

#endif
