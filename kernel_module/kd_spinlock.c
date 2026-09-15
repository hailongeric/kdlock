// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi
//
// Ported to kdlock: TCLocks komb.c → kd_spinlock.c
//
// kd_spinlock implements transparent delegation for kernel spinlocks.
// The protocol uses a per-CPU MCS-style queue with a combiner/waiter model:
// the lock holder (combiner) executes critical sections on behalf of queued
// waiters by running JIT-translated code through kd_exe_on_call_hl_entry().
//
// Key differences from TCLocks komb.c:
//   - Calls kd_exe_on_call_hl_entry() inside execute_cs() for JIT delegation
//   - Uses kd_spin_node (renamed from komb_node) with embedded pt_regs
//   - Delegation via sandbox JIT, not raw stack-switch

/* Scheduling nodes carry packets, but kd_spin_entry owns origin tickets and
 * kd_spin_gate owns native L. Keep these lifetimes separate when reading the
 * nested queue paths: a remote executor may carry the same logical waiter.
 * Physical shadow-stack switches still support combiners; JIT replaces the
 * critical-section body handoff, not every stack switch in this backend. */
#include "kd_spinlock.h"
#include "utils.h"
#include "exe.h"
#include "kd_exec.h"
#include "kd_segment.h"
#include "kd_spin_entry.h"
#include <linux/sched.h>
#include <linux/topology.h>
#include <linux/vmalloc.h>
#include <linux/kernel.h>

/* This file owns the public entry/return trampolines below. The ordered
 * components supply private state -> queues -> execution -> nested requests.
 * Keep one translation unit: stack-switch labels, static state and compiler
 * inlining form part of the existing entry ABI. See README.md for the map. */
#include "spin/state.inc"

#include "spin/shadow.inc"

#include "spin/diagnostics.inc"

#include "spin/queue.inc"

#include "spin/combiner.inc"

#include "spin/slowpath.inc"

#include "spin/lifecycle.inc"

#include "spin/nested.inc"

__attribute__((noipa)) noinline notrace static uint64_t *
get_shadow_stack_ptr(void)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	return &(ptr->local_shadow_stack_ptr);
}

/* Resume node defaults to the current CPU node if no explicit wakeup target exists.
 * This ensures direct return paths remain valid even without explicit set_resume.
 */
__attribute__((noipa)) noinline notrace static struct kd_spin_node *
get_kd_spin_resume_node(void)
{
	struct kd_spin_node *node =
		READ_ONCE(*this_cpu_ptr(&kd_spin_resume_nodes));

	return node ? node : this_cpu_ptr(&kd_spin_nodes[0]);
}

/* Native-input scratch slot is used as a temporary spill area for RSP handoff
 * while executing queue/combiner on shadow stack.
 */
__attribute__((noipa)) noinline notrace static struct kd_spin_native_input *
get_kd_spin_native_input(void)
{
	return this_cpu_ptr(&kd_spin_native_inputs);
}

/* Pick the earliest of node-rsp and logical-frame-rsp.
 * This avoids returning into an already-unwound return slot.
 */
__attribute__((noipa)) noinline notrace static unsigned long
get_kd_spin_resume_stack(void)
{
	struct kd_spin_node *node = get_kd_spin_resume_node();

	/* JIT may have grown the virtual CALL stack into old hook frames. Put
	 * our register copy below both live stacks, never over a return word.
	 */
	return min(node->rsp, node->regs.sp);
}

/*
 * When the following function is called, the compiler in caller frame does
 * this sequence:
 *
 * push caller-saved-regs			(rdi, rsi, rdx, rcx, ...)
 * ...<prepare arguments>...
 * .- push eip+1				(eip + 1 == pop insn)
 * callq |
 * `- jmp kd_spin_lock
 * pop caller-saved-regs
 *
 * This means that the following function must in no way modify the the rsp
 * before it is written to the task_frame, otherwise the top of the stack
 * (rsp) would no longer point to the return address. To do this, emit a
 * call in assembly and pass the top of the stack as an argument so that
 * we can use the stack while preserving the semantics of the combiner.
 *
 * NOTE: One advantage of offloading the caller-saved register spill to the
 * compiler is that it only saves the caller-saved registers in use in the
 * caller frame. If we were to inline this whole logic in assembly, we wouldn't
 * know the registers in use and would have to save all possible caller-saved
 * registers.
 */
#pragma GCC push_options
#pragma GCC optimize("O3")
/* Software packet restoration only: neither entry below loads flags. The
 * normal form consumes a saved stack return; the in-CS form pushes regs.ip.
 * Do not reuse them for a new flags-live exit without its separate contract. */
__attribute__((noipa)) noinline notrace void
jump_to_saved_regs(struct pt_regs *regs)
{
	asm volatile("movq 0x00(%%rdi), %%r15\n"
		     "movq 0x08(%%rdi), %%r14\n"
		     "movq 0x10(%%rdi), %%r13\n"
		     "movq 0x18(%%rdi), %%r12\n"
		     "movq 0x20(%%rdi), %%rbp\n"
		     "movq 0x28(%%rdi), %%rbx\n"
		     "movq 0x30(%%rdi), %%r11\n"
		     "movq 0x38(%%rdi), %%r10\n"
		     "movq 0x40(%%rdi), %%r9\n"
		     "movq 0x48(%%rdi), %%r8\n"
		     "movq 0x50(%%rdi), %%rax\n"
		     "movq 0x58(%%rdi), %%rcx\n"
		     "movq 0x60(%%rdi), %%rdx\n"
		     "movq 0x68(%%rdi), %%rsi\n"
		     "movq 0x98(%%rdi), %%rsp\n"
		     "movq 0x70(%%rdi), %%rdi\n"
		     "retq\n"
		     :
		     :
		     : "memory");
	__builtin_unreachable();
}

#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void
jump_to_saved_regs_in_cs(struct pt_regs *regs)
{
	asm volatile("movq 0x00(%%rdi), %%r15\n"
		     "movq 0x08(%%rdi), %%r14\n"
		     "movq 0x10(%%rdi), %%r13\n"
		     "movq 0x18(%%rdi), %%r12\n"
		     "movq 0x20(%%rdi), %%rbp\n"
		     "movq 0x28(%%rdi), %%rbx\n"
		     "movq 0x30(%%rdi), %%r11\n"
		     "movq 0x38(%%rdi), %%r10\n"
		     "movq 0x40(%%rdi), %%r9\n"
		     "movq 0x48(%%rdi), %%r8\n"
		     "movq 0x50(%%rdi), %%rax\n"
		     "movq 0x58(%%rdi), %%rcx\n"
		     "movq 0x60(%%rdi), %%rdx\n"
		     "movq 0x68(%%rdi), %%rsi\n"
		     "movq 0x98(%%rdi), %%rsp\n"
		     "pushq 0x80(%%rdi)\n"
		     "movq 0x70(%%rdi), %%rdi\n"
		     "retq\n"
		     :
		     :
		     : "memory");
	__builtin_unreachable();
}
#pragma GCC pop_options

__attribute__((noipa)) noinline notrace static void
kd_spin_resume_waiter(unsigned int mode)
{
	struct kd_spin_node *node = get_kd_spin_resume_node();
	struct pt_regs regs = node->regs;
	struct kd_spin_ref ref = node->spin_origin;

	if (node->jit_retry)
		KD_PR_INFO("spin JIT retry resume: node=%px cpu=%d ip=%lx\n",
			   node, node->cpuid, regs.ip);
	if (mode == 2)
		BUG_ON(kd_spin_entry_mark_native(&ref));
	else if (!mode)
		BUG_ON(kd_spin_entry_end(&ref));
	/* After end(), only native-stack locals may be read. */
	if (mode)
		jump_to_saved_regs_in_cs(&regs);
	jump_to_saved_regs(&regs);
	__builtin_unreachable();
}

#pragma GCC push_options
#pragma GCC optimize("O3")
/* Bridge from slow-path result code to resumed execution.
 * mode maps return classes from __kd_spin_lock_longjmp to:
 * 0=delegated native handoff, 1/3/4/5=queue/native restore variants.
 */
__attribute__((noipa)) noinline notrace static void
kd_spin_lock_slowpath(struct qspinlock *lock, unsigned long rsp_value)
{
	register int ret_val;

	asm volatile("callq %P0\n"
		     "movq %%rsp, %c1(%%rax)\n"
		     :
		     : "i"(get_kd_spin_native_input),
		       "i"(offsetof(struct kd_spin_native_input, rsp))
		     : "memory");
	WRITE_ONCE(this_cpu_ptr(&kd_spin_native_inputs)->regs_sp, rsp_value);
	asm volatile("callq %P0\n"
		     "movq (%%rax), %%rsp\n"
		     :
		     : "i"(get_shadow_stack_ptr)
		     : "memory");
	ret_val = __kd_spin_lock_slowpath(lock);
	if (ret_val == 0 || ret_val == 2) {
		/* This also handles node exhaustion, which has no resume node. */
		asm volatile("callq %P0\n"
			     "movq %c1(%%rax), %%rsp\n"
			     :
			     : "i"(get_kd_spin_native_input),
			       "i"(offsetof(struct kd_spin_native_input, rsp))
			     : "memory");
		return;
	}
	if (ret_val == 1 || ret_val == 3) {
		asm volatile("callq %P0\n"
			     "movq %%rax, %%rsp\n"
			     :
			     : "i"(get_kd_spin_resume_stack)
			     : "memory");
		kd_spin_resume_waiter(0);
		__builtin_unreachable();
	}
	if (ret_val == 4) {
		asm volatile("callq %P0\n"
			     "movq %%rax, %%rsp\n"
			     :
			     : "i"(get_kd_spin_resume_stack)
			     : "memory");
		kd_spin_resume_waiter(1);
		__builtin_unreachable();
	}
	if (ret_val == 5) {
		asm volatile("callq %P0\n"
			     "movq %%rax, %%rsp\n"
			     :
			     : "i"(get_kd_spin_resume_stack)
			     : "memory");
		kd_spin_resume_waiter(2);
		__builtin_unreachable();
	}
	BUG();
}
#pragma GCC pop_options

/* Hook entry for queued spin lock acquisition:
 * handles fast path when possible, otherwise routes to qspin queue protocol.
 */
__attribute__((noipa)) noinline notrace void
kd_spin_lock(struct qspinlock *lock, unsigned long rsp_value)
{
	struct kd_spin_ref ref = { 0 };
	struct qspinlock *word;
	u32 val, cnt;

	if (!in_task() || irqs_disabled() || softirq_count() ||
	    current->migration_disabled || kd_spin_entry_native_active())
		goto native;
	if (kd_spin_entry_begin((raw_spinlock_t *)lock, KD_SPIN_ENTRY_HOOK,
				&ref))
		goto native;
	/* A native helper called by JIT must not reenter its private C stack. */
	if (kd_exec_current_frame() || kd_exec_context_busy()) {
		BUG_ON(kd_spin_entry_end(&ref));
		goto native;
	}
	word = kd_spin_word(lock);
	val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);
	if (!val)
		goto acquired;
	if (val == _Q_PENDING_VAL_HL) {
		cnt = _Q_PENDING_LOOPS_HL;
		val = atomic_cond_read_relaxed(
			&word->val, (VAL != _Q_PENDING_VAL_HL) || !cnt--);
	}
	if (val & ~_Q_LOCKED_MASK_HL)
		goto queue;
	val = kd_spin_fetch_set_pending_acquire(lock);
	if (unlikely(val & ~_Q_LOCKED_MASK_HL)) {
		if (!(val & _Q_PENDING_MASK_HL))
			clear_pending(lock);
		goto queue;
	}
	if (val & _Q_LOCKED_MASK_HL)
		atomic_cond_read_acquire(&word->val,
					 !(VAL & _Q_LOCKED_MASK_HL));
	clear_pending_set_locked(lock);
	goto acquired;
queue:
	kd_spin_lock_slowpath(lock, rsp_value);
acquired:
	kd_spin_claim_origin(lock);
	return;
native:
	__raw_spin_lock((raw_spinlock_t *)lock);
}
EXPORT_SYMBOL_GPL(kd_spin_lock);

/*
 * No IPA is even more relevant here, because even if assembly is removed,
 * compiler shouldn't assume which caller-saved registers are in use inside
 * the function. When we jump from the spin loop to the return address after
 * the unlock function, we have caller-saved registers that are completely
 * inconsistent, because we only restored the callee-saved registers.
 */
__attribute__((noipa)) noinline notrace void
kd_spin_unlock(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	int from_cpuid = ptr->curr_cs_cpu;
	int j, max_idx, my_idx;

	uint64_t temp_lock_addr;

	j = 0;
	max_idx = -1;
	my_idx = -1;

	if (word->locked == _Q_LOCKED_VAL_HL ||
	    word->locked == _Q_LOCKED_IRQ_VAL) {
		kd_spin_release_origin(lock);
		return;
	}

	for (j = 0; j < 8; j++) {
		temp_lock_addr = ptr->lock_addr[j];
		if (temp_lock_addr != 0)
			max_idx = j;
		if (temp_lock_addr == (uint64_t)(unsigned long)lock)
			my_idx = j;
		if (temp_lock_addr == 0)
			break;
	}
	kd_spin_diag_validate_lock_stack(ptr);
	kd_spin_diag_validate_outer_unlock(ptr, lock, my_idx, max_idx);

	if (my_idx == -1) {
		if (word->locked == _Q_LOCKED_COMBINER_VAL) {
#ifdef KD_SPIN_STATS
			this_cpu_inc(ooo_unlocks);
#endif
			kd_spin_debug_ooo_unlock(lock,
						 kd_spin_lock_stack_depth(ptr));
			word->locked = _Q_UNLOCKED_OOO_VAL;
			print_debug("OOO unlock\n");
		} else
			BUG_ON(true);
		return;
	}

#ifdef DEBUG_KD_SPIN
	if (word->locked != _Q_LOCKED_COMBINER_VAL)
		BUG_ON(true);

	BUG_ON(from_cpuid == -1);

	if (max_idx < 0) {
		BUG_ON(true);
	}

#endif
	if (my_idx < max_idx) {
#ifdef KD_SPIN_STATS
		this_cpu_inc(ooo_unlocks);
#endif

		kd_spin_debug_ooo_unlock(lock, kd_spin_lock_stack_depth(ptr));
		word->locked = _Q_UNLOCKED_OOO_VAL;
		return;
	}

	struct kd_spin_node *curr_node =
		per_cpu_ptr(&kd_spin_nodes[0], from_cpuid);

#ifdef ENABLE_IRQS_CHECK
	curr_node->irqs_disabled = irqs_disabled();
#endif
	if (ptr->irqs_disabled) {
		ptr->irqs_disabled = false;
		local_irq_disable();
	}
}

static __always_inline int kd_spin_trylock(struct qspinlock *lock)
{
	struct qspinlock *word = kd_spin_word(lock);
	u32 val;

	val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);
	if (val == 0)
		return true;

	return false;
}

#ifdef KDLOCK_SELFTEST
/* Keep access to private queue state out of the production API. */
#include "../tests/kernel/spin_frame_trace.c"
#include "../tests/kernel/spin_readmission_trace.c"
#include "../tests/kernel/spin_refusal_trace.c"
#include "../tests/kernel/spin_deferred_trace.c"
#include "../tests/kernel/spin_shadow_selftest.c"
#include "../tests/kernel/spin_virtual_selftest.c"
#endif
