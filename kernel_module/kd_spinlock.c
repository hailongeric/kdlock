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
//   - Uses kd_spin_node with a shared request/frame/register packet
//   - Delegation via sandbox JIT; a per-CPU shadow stack isolates waiter polling

/* Scheduling nodes carry packets, but kd_spin_entry owns origin tickets and
 * the KD word owns exclusion. Keep these lifetimes separate when reading the
 * nested queue paths: a remote executor may carry the same logical waiter.
 * Combiners use their task stack. Physical waiters switch to a shadow stack
 * before publication and return to their task stack after the release wake. */
#include "kd_spinlock.h"
#include "utils.h"
#include "exe.h"
#include "kd_exec.h"
#include "kd_jit_batch.h"
#include "kd_source.h"
#include "kd_segment.h"
#include "kd_spin_entry.h"
#include "kd_spin_fast.h"
#include "kd_hotlock.h"
#include <linux/sched.h>
#include <linux/sched/task_stack.h>
#include <linux/topology.h>
#include <linux/vmalloc.h>
#include <linux/kernel.h>
#include <linux/module.h>

/* This file owns the public entry/return trampolines below. The ordered
 * components supply private state -> queues -> execution -> nested requests.
 * Keep one translation unit: stack-switch labels, static state and compiler
 * inlining form part of the existing entry ABI. See README.md for the map. */
#include "spin/state.inc"

#include "spin/shadow.inc"

#include "spin/diagnostics.inc"

#include "spin/queue.inc"

#include "spin/nondelegated.inc"

#include "spin/request.inc"

#include "spin/prefetch.inc"

#include "spin/combiner.inc"

#include "spin/wait.inc"

#include "spin/slowpath.inc"

#include "spin/lifecycle.inc"

#include "spin/nested.inc"

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

/* Called after all packet reads/retirement, on the restored task stack.
 * The full-packet path already restored GPRs: this helper and the kernel
 * scheduling thunk preserve them while consuming exactly the original pin. */
static __attribute__((noipa, used, no_caller_saved_registers)) noinline notrace void
kd_spin_restore_unpin(void)
{
	preempt_enable();
}

/* No packet read may follow this sequence. The acquisition pin still fixes
 * the CPU; interrupt callers use native nodes, never continuation storage. */
#define KD_SPIN_RETIRE_ASM \
	"pushq %%rax\n" \
	"pushq %%rcx\n" \
	"movq %c[storage](%%rdi), %%rax\n" \
	"movb $1, %c[retired](%%rdi)\n" \
	"movl %c[top](%%rax), %%ecx\n" \
	"5: testl %%ecx, %%ecx\n" \
	"jz 6f\n" \
	"movl %%ecx, %%edi\n" \
	"imulq $%c[stride], %%rdi\n" \
	"cmpb $0, %c[last_retired](%%rax,%%rdi)\n" \
	"je 6f\n" \
	"decl %%ecx\n" \
	"jmp 5b\n" \
	"6: movl %%ecx, %c[top](%%rax)\n" \
	"popq %%rcx\n" \
	"popq %%rax\n"
#define KD_SPIN_RETIRE_OPERANDS \
	[storage] "i"(offsetof(struct kd_spin_continuation, storage)), \
	[retired] "i"(offsetof(struct kd_spin_continuation, retired)), \
	[top] "i"(offsetof(struct kd_spin_continuation_stack, top)), \
	[stride] "i"(sizeof(struct kd_spin_continuation)), \
	[last_retired] "i"((long)offsetof(struct kd_spin_continuation_stack, records) + \
		offsetof(struct kd_spin_continuation, retired) - sizeof(struct kd_spin_continuation))

static __attribute__((noipa, noreturn)) noinline notrace void
kd_spin_restore_request(struct kd_spin_continuation *execution,
						unsigned int mode)
{
	if (execution->frame.entry_abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1 &&
		execution->frame.packet_state != KD_PACKET_FULL)
	{
		BUG_ON(mode == 2);
		asm volatile(
			"movq %c[sp](%%rdi), %%rsp\n"
			"pushq %c[ip](%%rdi)\n"
			"movq %c[bp](%%rdi), %%rbp\n"
			KD_SPIN_RETIRE_ASM
			"testl %%esi, %%esi\n"
			"jnz 7f\n"
			"callq %P[unpin]\n"
			"7:\n"
			"retq\n"
			:
			: "D"(execution), "S"(mode),
			  [unpin] "i"(kd_spin_restore_unpin),
			  [sp] "i"(offsetof(struct kd_spin_continuation, frame.regs.sp)),
			  [ip] "i"(offsetof(struct kd_spin_continuation, frame.regs.ip)),
			  [bp] "i"(offsetof(struct kd_spin_continuation, frame.regs.bp)),
			  KD_SPIN_RETIRE_OPERANDS
			: "memory", "cc");
		__builtin_unreachable();
	}
	asm volatile(
		"movq %c[sp](%%rdi), %%rsp\n"
		"testl %%edx, %%edx\n"
		"jz 1f\n"
		"pushq %c[ip](%%rdi)\n"
		"1: pushq %%rdx\n"
		"pushq %c[packet]+0x70(%%rdi)\n"
		"movq %c[packet]+0x00(%%rdi), %%r15\n"
		"movq %c[packet]+0x08(%%rdi), %%r14\n"
		"movq %c[packet]+0x10(%%rdi), %%r13\n"
		"movq %c[packet]+0x18(%%rdi), %%r12\n"
		"movq %c[packet]+0x20(%%rdi), %%rbp\n"
		"movq %c[packet]+0x28(%%rdi), %%rbx\n"
		"movq %c[packet]+0x30(%%rdi), %%r11\n"
		"movq %c[packet]+0x38(%%rdi), %%r10\n"
		"movq %c[packet]+0x40(%%rdi), %%r9\n"
		"movq %c[packet]+0x48(%%rdi), %%r8\n"
		"movq %c[packet]+0x50(%%rdi), %%rax\n"
		"movq %c[packet]+0x58(%%rdi), %%rcx\n"
		"movq %c[packet]+0x60(%%rdi), %%rdx\n"
		"movq %c[packet]+0x68(%%rdi), %%rsi\n"
		/* Native execution retains this root until the final unlock barrier. */
		"cmpl $2, 8(%%rsp)\n"
		"je 3f\n"
		KD_SPIN_RETIRE_ASM
		"3:\n"
		"popq %%rdi\n"
		"cmpl $0, (%%rsp)\n"
		"je 7f\n"
		"cmpl $3, (%%rsp)\n"
		"je 7f\n"
		"addq $8, %%rsp\n"
		"jmp 8f\n"
		"7: addq $8, %%rsp\n"
		"callq %P[unpin]\n"
		"8:\n"
		"retq\n"
		:
		: "D"(execution), "d"(mode),
		  [unpin] "i"(kd_spin_restore_unpin),
		  [packet] "i"(offsetof(struct kd_spin_continuation, frame.regs)),
		  [sp] "i"(offsetof(struct kd_spin_continuation, frame.regs.sp)),
		  [ip] "i"(offsetof(struct kd_spin_continuation, frame.regs.ip)),
		  KD_SPIN_RETIRE_OPERANDS
		: "memory", "cc");
	__builtin_unreachable();
}

__attribute__((noipa)) noinline notrace static void
kd_spin_resume_waiter(struct kd_spin_node *node, unsigned int mode)
{
	struct kd_spin_continuation *execution = node->execution;
	struct kd_spin_ref ref = node->execution->frame.spin_origin;

	if (node->execution->result == KD_SPIN_RES_RETRY)
		KD_PR_INFO("spin JIT retry resume: node=%px cpu=%d ip=%lx\n",
				   node, node->cpuid, node->execution->frame.regs_ref->ip);
	if (mode == 2) {
		BUG_ON(kd_spin_entry_mark_native(&ref));
		*this_cpu_ptr(&kd_spin_native_root) = execution;
		if (!kd_exec_native_pending(current)) {
			BUG_ON(kd_spin_entry_borrow_wait(&ref));
			*this_cpu_ptr(&kd_spin_native_root) = NULL;
			mode = 3; /* In-CS IP, but all executors already retired. */
			BUG_ON(kd_spin_entry_end_pinned(&ref));
		}
	}
	else if (!mode)
		BUG_ON(kd_spin_entry_end_pinned(&ref));
	/* No node reads follow release; keep the pin through final packet loads. */
	barrier();
	this_cpu_dec(kd_spin_cpu.node_count);
	kd_spin_selftest_node_event(KD_NODE_RELEASE);
	kd_spin_restore_request(execution, mode);
	__builtin_unreachable();
}

/* Entered directly from the stack-free assembly interval. All old C frames
 * have been abandoned; this helper runs below the final virtual stack. */
static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_spin_resume_completed(struct kd_spin_node *node)
{
	unsigned int mode = (READ_ONCE(node->execution->result) == KD_SPIN_RES_NATIVE_READY) ? 2 : 0;

	if (mode)
		kd_spin_selftest_node_event(KD_NODE_NATIVE_RETURN);
	else
		kd_spin_selftest_node_event(KD_NODE_REMOTE_RETURN);
	kd_spin_diag_waiter_exit(node->execution->diag);
	kd_spin_resume_waiter(node, mode);
	__builtin_unreachable();
}

/* Queue preparation and combiner C code stay on the task stack. Like plain
 * raw_spin_lock, leave IRQ state unchanged throughout waiting/execution.
 * JIT may overwrite the original C frames, so restoration uses the packet. */
__attribute__((noipa)) noinline notrace static void
kd_spin_lock_slowpath(struct qspinlock *lock, unsigned long rsp_value,
					  struct kd_spin_request *request, unsigned long ip,
					  unsigned long bp, unsigned int abi)
{
	struct kd_spin_native_input input;
	unsigned long sp;
	int ret;

	asm volatile("movq %%rsp, %0" : "=r"(sp));
	input.rsp = sp;
	input.regs_sp = rsp_value;
	input.ip = ip;
	input.bp = bp;
	input.entry_abi = abi;
	ret = __kd_spin_lock_slowpath(lock, request, &input);
	if (ret == 0 || ret == 2)
	{
		return;
	}
	/* A pre-body refusal can acquire the queue and retry from its decoded
	 * entry. It has not touched the caller's stack; completed/native wakes
	 * already left through kd_spin_resume_completed and cannot return here. */
	if (ret == 4)
	{
		struct kd_spin_node *node =
			READ_ONCE(*this_cpu_ptr(&kd_spin_resume_nodes));

		sp = min(node->rsp, node->execution->frame.regs_ref->sp) & ~15UL;
		asm volatile("movq %0, %%rsp\n"
					 "callq %P3\n"
					 "ud2\n"
					 :
					 : "r"(sp), "D"(node), "S"(1U),
					   "i"(kd_spin_resume_waiter)
					 : "memory");
		__builtin_unreachable();
	}
	BUG();
}

/* Admission refusal retains the KD queue protocol. Only genuine node
 * exhaustion polls the full word; ordinary contention uses local MCS waits. */
static void kd_spin_lock_nondelegated_pinned(kd_spinlock_t *lock)
{
	this_cpu_inc(kd_spin_fast_cpu.nondelegated);
	kd_spin_acquire_nondelegated(lock);
	/* A sole task-context hold can use the existing fast ownership record.
	 * Publish it before dropping the acquisition drain count. Nested/IRQ
	 * callers keep their independent count and cannot overwrite that owner. */
	if (in_task() && preempt_count() == 1) {
		kd_spin_fast_claim(lock);
		this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	}
}
void kd_spin_lock_nondelegated(kd_spinlock_t *lock)
{
	preempt_disable();
	kd_spin_lock_nondelegated_pinned(lock);
}
/* A physical ACK releases a lock; this barrier releases the root's pin only
 * after every registered native executor has finished all frame accesses. */
void kd_spin_native_retire(struct kd_spin_ref *ref)
{
	struct kd_spin_continuation *root = *this_cpu_ptr(&kd_spin_native_root);

	BUG_ON(!root || root->frame.spin_origin.entry != ref->entry ||
	       root->frame.spin_origin.sequence != ref->sequence);
	BUG_ON(kd_spin_entry_borrow_wait(ref));
	*this_cpu_ptr(&kd_spin_native_root) = NULL;
	kd_spin_continuation_release(root);
	BUG_ON(kd_spin_entry_end(ref));
}

void kd_spin_unlock_nondelegated(kd_spinlock_t *lock)
{
	/* Native bridge callers use this paired API directly, bypassing the
	 * public unlock router. They can also own the sole fast record. */
	if (kd_spin_fast_unlock((raw_spinlock_t *)lock))
		return;
	smp_store_release(&lock->locked, 0);
	this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	preempt_enable();
}

/* The entry has already pinned admission. Root callers pass the failed CAS
 * value; nested callers reserve their ticket before their first CAS. Keeping
 * the address-taken request here avoids its initialization and stack canary
 * on an uncontended root acquisition. Pending ownership remains ticket-free. */
noinline notrace static void
kd_spin_lock_contended(struct qspinlock *lock, unsigned long rsp_value,
                      unsigned long rip, unsigned long bp, unsigned int abi,
                      u32 val)
{
	struct kd_spin_request request = { .word = lock };
	struct qspinlock *word = lock;
	u32 cnt;

	if (preempt_count() != 1) {
		if (kd_spin_entry_begin_pinned((raw_spinlock_t *)lock, &request.ref))
			goto native;
		val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);
		if (!val)
			goto acquired;
	}
	if (val == _Q_PENDING_VAL_HL)
	{
		cnt = _Q_PENDING_LOOPS_HL;
		val = atomic_cond_read_relaxed(
			&word->val, (VAL != _Q_PENDING_VAL_HL) || !cnt--);
	}
	if (val & ~_Q_LOCKED_MASK_HL)
		goto queue;
	val = kd_spin_fetch_set_pending_acquire(word);
	if (unlikely(val & ~_Q_LOCKED_MASK_HL))
	{
		if (!(val & _Q_PENDING_MASK_HL))
			clear_pending(word);
		goto queue;
	}
	if (val & _Q_LOCKED_MASK_HL)
		atomic_cond_read_acquire(&word->val,
								 !(VAL & _Q_LOCKED_MASK_HL));
	clear_pending_set_locked(word);
	goto acquired;
queue:
	/* A sole pending owner never publishes a continuation or lends its
	 * ownership to a remote executor. Defer its ticket until MCS admission;
	 * fast/pending success can use the same CPU-local physical owner record.
	 * Nested callers reserved above and retain their independent ticket. */
	if (!request.ref.entry &&
	    kd_spin_entry_begin_pinned((raw_spinlock_t *)lock, &request.ref))
		goto native;
	/* Before publication, an absent/refused translation needs only an MCS
	 * node. Keep registration for later admission, but allocate no logical
	 * packet/frame and never lend this caller's stack to a combiner. */
	if (preempt_count() != 1 ||
	    !kd_exe_entry_is_ready(kd_get_exe(0, rip), 0, rip)) {
		kd_exe_add_abi(0, rip, KD_EXE_LOCK_SPIN, abi);
		kd_spin_acquire_nondelegated(word);
		goto acquired;
	}
	kd_spin_lock_slowpath(lock, rsp_value, &request, rip, bp, abi);
	/* Every intact slowpath return has already claimed (or reclaimed) the
	 * ticket, including capacity fallback. Remote completion never returns
	 * here. Do not take its guard a second time merely to confirm OWNED. */
	return;
acquired:
	if (request.ref.entry)
		kd_spin_claim_origin(&request);
	else
		kd_spin_fast_claim(lock);
	return;
native:
	kd_spin_lock_nondelegated_pinned(lock);
}
/* One acquisition pin spans admission, queueing and the entire CS. Refusal
 * transfers that pin to native execution; unlock/completion consumes it. */
static __always_inline void
kd_spin_lock_abi_pinned(struct qspinlock *lock, unsigned long rsp_value,
                 unsigned long rip, unsigned long bp, unsigned int abi)
{
	u32 val = 0;

	if (!kd_spin_delegate || !kd_hotlock_record_spin_pinned((unsigned long)lock))
		goto native;
	if (!in_task() || softirq_count() || current->migration_disabled ||
	    kd_spin_entry_native_active())
		goto native;
	if (kd_exec_context_occupied())
		goto native;
	if (preempt_count() == 1) {
		val = atomic_cmpxchg_acquire(&lock->val, 0, _Q_LOCKED_VAL_HL);
		if (!val) {
			kd_spin_fast_claim(lock);
			return;
		}
	}
	kd_spin_lock_contended(lock, rsp_value, rip, bp, abi, val);
	return;
native:
	kd_spin_lock_nondelegated_pinned(lock);
}

__attribute__((noipa)) noinline notrace void
kd_spin_lock_abi(struct qspinlock *lock, unsigned long sp,
		 unsigned long ip, unsigned long bp, unsigned int abi)
{
	preempt_disable();
	kd_spin_lock_abi_pinned(lock, sp, ip, bp, abi);
}

/* The inline caller already pinned and chose self-execution. A failed CAS
 * enters the complete native pending/MCS algorithm, including CPU sampling;
 * later heat changes never turn this acquisition into delegated work.
 * The lock byte carries ownership, while the sole per-CPU cookie remains
 * just rate_hot. Keep native holders counted through their paired release. */
__attribute__((noipa)) noinline notrace void
kd_spin_direct_native_lock(kd_spinlock_t *lock)
{
	u32 val;

	this_cpu_inc(kd_spin_fast_cpu.nondelegated);
	val = atomic_cmpxchg_acquire(&lock->val, 0, KD_SPIN_DIRECT_NATIVE_HELD);
	if (val) {
		kd_spin_acquire_nondelegated_contended(lock, val);
		/* The shared pending/MCS core acquires with its ordinary byte.
		 * We now own it: publish paired native provenance without touching
		 * pending or a successor's tail. No second acquisition CAS. */
		WRITE_ONCE(lock->locked, KD_SPIN_DIRECT_NATIVE_HELD);
	}
}
EXPORT_SYMBOL_GPL(kd_spin_direct_native_lock);

__attribute__((noipa)) noinline notrace void
kd_spin_direct_native_unlock(kd_spinlock_t *lock)
{
	/* The lock byte proves native ownership; preserve a concurrently added tail. */
	smp_store_release(&lock->locked, 0);
	this_cpu_dec(kd_spin_fast_cpu.nondelegated);
	preempt_enable();
}
EXPORT_SYMBOL_GPL(kd_spin_direct_native_unlock);

__attribute__((noipa)) noinline notrace void
kd_spin_lock_pinned_clobber_v1(kd_spinlock_t *lock, unsigned long sp,
			     unsigned long ip, unsigned long bp)
{
	kd_spin_lock_abi_pinned(lock, sp, ip, bp, KD_ENTRY_ABI_SPIN_CLOBBER_V1);
}
EXPORT_SYMBOL_GPL(kd_spin_lock_pinned_clobber_v1);

void kd_spin_lock(struct qspinlock *lock, unsigned long sp, unsigned long ip)
{
	kd_spin_lock_abi(lock, sp, ip, 0, KD_ENTRY_ABI_LEGACY);
}
EXPORT_SYMBOL_GPL(kd_spin_lock);

/* Preparation is explicitly outside the operation loop and after the source
 * module is LIVE, so its text can be pinned until retirement. */
int kd_spin_prepare(struct qspinlock *lock, unsigned long ip, unsigned int abi)
{
	struct kd_exe_info *exe;

	if (!lock || !ip || !kd_entry_abi_valid(KD_EXE_LOCK_SPIN, abi))
		return -EINVAL;
	if (!kd_source_is_open())
		return -ESHUTDOWN;
	kd_exe_add_abi(0, ip, KD_EXE_LOCK_SPIN, abi);
	exe = kd_get_exe(0, ip);
	if (!exe || smp_load_acquire(&exe->status_code) == KD_EXE_UNUSED ||
		exe->RIP != ip || exe->entry_abi != abi ||
		exe->lock_kind != KD_EXE_LOCK_SPIN || !exe->code_block)
		return -EINVAL;
	return READ_ONCE(exe->status_code) == KD_EXE_NATIVE_ONLY ? -EOPNOTSUPP : 0;
}
EXPORT_SYMBOL_GPL(kd_spin_prepare);

__attribute__((noipa)) noinline notrace void
kd_spin_lock_clobber_v1(struct qspinlock *lock, unsigned long sp,
						unsigned long ip, unsigned long bp)
{
	/* Ordinary clobber callers acquire their own pin; paired hot callers
	 * enter the same inlined core through the already-pinned entry above. */
	preempt_disable();
	kd_spin_lock_abi_pinned(lock, sp, ip, bp, KD_ENTRY_ABI_SPIN_CLOBBER_V1);
}
EXPORT_SYMBOL_GPL(kd_spin_lock_clobber_v1);

/*
 * No IPA is even more relevant here, because even if assembly is removed,
 * compiler shouldn't assume which caller-saved registers are in use inside
 * the function. When we jump from the spin loop to the return address after
 * the unlock function, we have caller-saved registers that are completely
 * inconsistent, because we only restored the callee-saved registers.
 */
__attribute__((noipa)) noinline notrace static void
kd_spin_unlock_request(struct qspinlock *lock, struct kd_spin_request *request)
{
	struct qspinlock *word = request->word;
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);
	int j, max_idx, my_idx;

	uint64_t temp_lock_addr;

	j = 0;
	max_idx = -1;
	my_idx = -1;

	if (word->locked == _Q_LOCKED_VAL_HL ||
		word->locked == _Q_LOCKED_IRQ_VAL)
	{
		kd_spin_release_origin(request);
		return;
	}

	for (j = 0; j < 8; j++)
	{
		temp_lock_addr = ptr->lock_addr[j];
		if (temp_lock_addr != 0)
			max_idx = j;
		if (temp_lock_addr == (uint64_t)(unsigned long)lock)
			my_idx = j;
		if (temp_lock_addr == 0)
			break;
	}
	kd_spin_diag_validate_lock_stack(ptr);
	kd_spin_diag_validate_outer_unlock(ptr, lock, word, my_idx, max_idx);

	if (my_idx == -1)
	{
		if (word->locked == _Q_LOCKED_COMBINER_VAL)
		{
#ifdef KD_SPIN_STATS
			this_cpu_inc(ooo_unlocks);
#endif
			kd_spin_debug_ooo_unlock(lock,
									 kd_spin_lock_stack_depth(ptr));
			word->locked = _Q_UNLOCKED_OOO_VAL;
			print_debug("OOO unlock\n");
		}
		else
			BUG_ON(true);
		return;
	}

#ifdef DEBUG_KD_SPIN
	if (word->locked != _Q_LOCKED_COMBINER_VAL)
		BUG_ON(true);

	BUG_ON(ptr->curr_cs_cpu == -1);

	if (max_idx < 0)
	{
		BUG_ON(true);
	}

#endif
	if (my_idx < max_idx)
	{
#ifdef KD_SPIN_STATS
		this_cpu_inc(ooo_unlocks);
#endif

		kd_spin_debug_ooo_unlock(lock, kd_spin_lock_stack_depth(ptr));
		word->locked = _Q_UNLOCKED_OOO_VAL;
		return;
	}

	/* Plain spin leaves each physical caller's IRQ state unchanged. */
}

__attribute__((noipa)) noinline notrace void
kd_spin_unlock_ref(struct qspinlock *lock, const struct kd_spin_ref *ref)
{
	struct kd_spin_request request = {
		.ref = *ref,
		.word = kd_spin_request_word(ref),
	};

	kd_spin_unlock_request(lock, &request);
}

__attribute__((noipa)) noinline notrace void
kd_spin_unlock_protocol(struct qspinlock *lock)
{
	struct kd_spin_request request = kd_spin_unlock_lookup(lock);

	kd_spin_unlock_request(lock, &request);
}

/* Explicit callers need the same acquisition-provenance release as the old
 * hook, including the ticket-free KD owner and unstarted native fallback.
 * This is protocol routing, independent of comm, frequency or JIT policy. */
noinline notrace static void
kd_spin_unlock_slow(struct qspinlock *lock)
{
	struct kd_spin_ref ref = {0};

	if (kd_exec_native_unlock((unsigned long)lock, false))
		return;
	if (kd_spin_entry_find((raw_spinlock_t *)lock, &ref))
	{
		kd_spin_unlock_ref(lock, &ref);
		return;
	}
	kd_spin_unlock_nondelegated(lock);
}
/* Avoid preparing a ticket reference until physical fast ownership misses.
 * Inline only this small router; request/continuation work remains slow. */
static __always_inline void
kd_spin_unlock_core(struct qspinlock *lock)
{
	if (kd_spin_fast_unlock((raw_spinlock_t *)lock))
		return;
	kd_spin_unlock_slow(lock);
}

__attribute__((noipa)) noinline notrace void
kd_spin_unlock(struct qspinlock *lock)
{
	kd_spin_unlock_core(lock);
}
EXPORT_SYMBOL_GPL(kd_spin_unlock);

__attribute__((noipa)) noinline notrace void
kd_spin_unlock_clobber_v1(struct qspinlock *lock, unsigned long sp,
						  unsigned long ip, unsigned long bp)
{
	/* Byte 5 carries paired native ownership without a fast record/ticket.
	 * Release only that byte, then drop its count and acquisition pin. Keep
	 * this short route inline; the ordinary generic router handles all other
	 * owners. Callers still provide SP/IP/BP: the JIT completion endpoint
	 * validates those words even though physical release does not use them. */
	if (READ_ONCE(lock->locked) == KD_SPIN_DIRECT_NATIVE_HELD) {
		smp_store_release(&lock->locked, 0);
		this_cpu_dec(kd_spin_fast_cpu.nondelegated);
		preempt_enable();
		return;
	}
	kd_spin_unlock_core(lock);
}
EXPORT_SYMBOL_GPL(kd_spin_unlock_clobber_v1);

static __always_inline int kd_spin_trylock(struct qspinlock *word)
{
	u32 val;

	val = atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL);
	if (val == 0)
		return true;

	return false;
}

#ifdef KDLOCK_SELFTEST
/* Keep access to private queue state out of the production API. */
#include "../tests/kernel/spin/spin_frame_trace.c"
#include "../tests/kernel/spin/spin_readmission_trace.c"
#include "../tests/kernel/spin/spin_refusal_trace.c"
#include "../tests/kernel/spin/spin_deferred_trace.c"
#include "../tests/kernel/spin/spin_shadow_selftest.c"
#include "../tests/kernel/spin/spin_virtual_selftest.c"
#endif
