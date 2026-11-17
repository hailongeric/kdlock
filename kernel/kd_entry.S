/* SPDX-License-Identifier: GPL-2.0 */
/*
 * kdlock entry stubs and generated-code transfer.
 *
 * Delegable lock entries are written in assembly because the path that
 * publishes a continuation must see the caller's state exactly as the call
 * instruction left it: the return address on top of the stack and the
 * callee-saved registers untouched. Caller-saved registers are dead across
 * a call, so those eight words are the caller's whole continuation.
 *
 * A contended entry first calls its C *_slow function on the caller's own
 * stack. In plain mode that function waits and acquires like the native
 * lock and the stub returns. A C call preserves the callee-saved registers
 * and the stack pointer, so when the function instead reports that the
 * lock is in delegation mode, the continuation is still intact and the
 * stub publishes it (offer path).
 *
 * Offer path order (each step relies on the previous one):
 *   1. preemption is off (lock semantics for spin/rwlock, an explicit pin
 *      for mutex/rwsem), so the CPU's packet and wait stack are ours;
 *   2. bts on kd_cpu.busy claims them against interrupts on this CPU; if
 *      it was already set we are nested and take the non-delegable path;
 *   3. the continuation is stored in the packet;
 *   4. rsp moves to the wait stack. From here on nothing on this CPU
 *      writes below the caller's stack pointer, so a combiner may run the
 *      caller's critical section on the caller's stack;
 *   5. the C wait function queues and returns how the wait ended.
 *
 * Clobber entries (__kd_*_cl, reached only from the kd_*_cl() macros of
 * kd_api.h). Their callers declare every general register except rsp and
 * rbp lost across the call, so the continuation is rsp, rbp, the return
 * address and the flags, and the packet records it as KD_RS_COMPACT: two
 * cache lines instead of four for the combiner to fetch. They are not C
 * functions and have no prototype, so they cannot be reached through a
 * function pointer; such calls use the ordinary entries, which keep the C
 * convention. Both kinds queue on the same lock and are served by the same
 * sessions.
 */
#include <linux/linkage.h>
#include <linux/export.h>
#include <linux/objtool.h>
#include <asm/percpu.h>
#include <asm/nospec-branch.h>
#include <asm/unwind_hints.h>
#include "kd_asm.h"

#define KC(off)		PER_CPU_VAR(kd_cpu + (off))
#define KR(off)		PER_CPU_VAR(kd_cpu + KD_CPU_regs + (off))

	.text

/*
 * Store the continuation, wait, and come back on the caller's stack unless
 * the section was executed elsewhere.
 *
 * In:   rdi = lock, rax = value the lock call must return, [rsp] = return
 *       address, busy set, preemption off.
 * Out (not resumed): rsp = caller's stack with the return address on top,
 *       rdi = lock, rdx = return value, esi = wait result, flags from
 *       "test wait result" (SF set: sleeping path), busy clear.
 */
.macro KD_OFFER waitfn:req
	movq	%rbx, KR(KD_R_rbx)
	movq	%rbp, KR(KD_R_rbp)
	movq	%r12, KR(KD_R_r12)
	movq	%r13, KR(KD_R_r13)
	movq	%r14, KR(KD_R_r14)
	movq	%r15, KR(KD_R_r15)
	movq	%rax, KR(KD_R_rax)
	leaq	8(%rsp), %rax
	movq	%rax, KR(KD_R_rsp)
	movq	(%rsp), %rax
	movq	%rax, KR(KD_R_rip)
	pushfq
	popq	KR(KD_R_rflags)
	movb	$KD_RS_FULL, KR(KD_R_kind)
	movq	%rdi, %rbx			/* lock pointer survives the C call */
	movq	KC(KD_CPU_wait_stack), %rsp
	call	\waitfn
	testl	%eax, %eax
	jg	kd_resume
	/* mov and lea leave the flags of the test intact. */
	movl	%eax, %esi
	movq	%rbx, %rdi
	movq	KR(KD_R_rbx), %rbx
	movq	KR(KD_R_rsp), %rdx
	leaq	-8(%rdx), %rsp			/* return address is still in place */
	movq	KR(KD_R_rax), %rdx
	movl	$0, KC(KD_CPU_busy)
.endm

/*
 * KD_OFFER for the clobber entries: the same steps with a compact state.
 * The caller has given up rbx, so the lock pointer is kept there without
 * saving it, and nothing but rsp is put back on the way out.
 */
.macro KD_OFFER_CL waitfn:req
	movq	%rbp, KR(KD_R_rbp)
	movq	%rax, KR(KD_R_rax)
	leaq	8(%rsp), %rax
	movq	%rax, KR(KD_R_rsp)
	movq	(%rsp), %rax
	movq	%rax, KR(KD_R_rip)
	pushfq
	popq	KR(KD_R_rflags)
	movb	$KD_RS_COMPACT, KR(KD_R_kind)
	movq	%rdi, %rbx
	movq	KC(KD_CPU_wait_stack), %rsp
	call	\waitfn
	testl	%eax, %eax
	jg	kd_resume
	movl	%eax, %esi
	movq	%rbx, %rdi
	movq	KR(KD_R_rsp), %rdx
	leaq	-8(%rdx), %rsp
	movq	KR(KD_R_rax), %rdx
	movl	$0, KC(KD_CPU_busy)
.endm

/*
 * Spin-class entry (spinlock and rwlock writer).
 *
 * irq:  0 none, 1 disable, 2 save and disable (flags returned in rax)
 * bh:   disable softirqs instead of a plain preempt_disable()
 * val:  value swapped into the 32-bit lock word when it is 0
 *
 * Interrupt state is changed with a native cli; the configuration must not
 * route irq flags through paravirt or irqflags tracing.
 */
.macro KD_SPIN_ENTRY name:req, irq:req, bh:req, val:req, slowfn:req, waitfn:req, plainfn:req, nestop:req, cl=0
.if !\cl
/*
 * Entry used by generated code in place of \name. Same fast path. When
 * contended it does not wait here: the executor is running somebody's
 * continuation, and that continuation - now stopped right after this lock
 * call - is what has to queue. kd_nested_exit stores it in the packet and
 * returns to the executor, which queues it for the inner lock.
 */
SYM_FUNC_START(\name\()_jit)
.if \irq == 2
	pushfq
	popq	%rcx
.endif
.if \irq
	cli
.endif
.if \bh
	addl	$KD_ASM_SOFTIRQ_LOCK_OFFSET, PER_CPU_VAR(__preempt_count)
.else
	incl	PER_CPU_VAR(__preempt_count)
.endif
	xorl	%eax, %eax
	movl	$\val, %edx
	lock cmpxchgl %edx, (%rdi)
	jnz	.Lnest_\name
.if \irq == 2
	movq	%rcx, %rax
.endif
	RET
.Lnest_\name:
	movq	%rcx, %rax
	movl	$(KD_ASM_X_NESTED | (\nestop << 8)), %edx
	jmp	kd_nested_exit
SYM_FUNC_END(\name\()_jit)
STACK_FRAME_NON_STANDARD \name\()_jit
.endif

SYM_FUNC_START(\name)
.if \irq == 2
	pushfq
	popq	%rcx
.endif
.if \irq
	cli
.endif
.if \bh
	addl	$KD_ASM_SOFTIRQ_LOCK_OFFSET, PER_CPU_VAR(__preempt_count)
.else
	incl	PER_CPU_VAR(__preempt_count)
.endif
	xorl	%eax, %eax
	movl	$\val, %edx
	lock cmpxchgl %edx, (%rdi)
	jnz	.Lslow_\name
.if \irq == 2
	movq	%rcx, %rax
.endif
	RET
.Lslow_\name:
	/* \slowfn(lock, call site): true = acquired on this stack. */
	movq	(%rsp), %rsi
	pushq	%rcx				/* irqsave result; unused otherwise */
	pushq	%rdi
	call	\slowfn
	popq	%rdi
	popq	%rcx
	testb	%al, %al
	jz	.Loffer_\name
.if \irq == 2
	movq	%rcx, %rax
.endif
	RET
.Loffer_\name:
	btsl	$0, KC(KD_CPU_busy)
	jc	.Lplain_\name
	movq	%rcx, %rax
.if \cl
	KD_OFFER_CL \waitfn
.else
	KD_OFFER \waitfn
.endif
	movq	%rdx, %rax
	RET
.Lplain_\name:
.if \irq == 2
	pushq	%rcx
	call	\plainfn
	popq	%rax
	RET
.else
	jmp	\plainfn
.endif
SYM_FUNC_END(\name)
STACK_FRAME_NON_STANDARD \name
EXPORT_SYMBOL(\name)
.endm

KD_SPIN_ENTRY kd_spin_lock,         0, 0, KD_ASM_SPIN_LOCKED, kd_q_lock_slow,    kd_spin_wait,  kd_spin_lock_plain, KD_ASM_OP_NEST_SPIN
KD_SPIN_ENTRY kd_spin_lock_irq,     1, 0, KD_ASM_SPIN_LOCKED, kd_q_lock_slow,    kd_spin_wait,  kd_spin_lock_plain, KD_ASM_OP_NEST_SPIN
KD_SPIN_ENTRY kd_spin_lock_irqsave, 2, 0, KD_ASM_SPIN_LOCKED, kd_q_lock_slow,    kd_spin_wait,  kd_spin_lock_plain, KD_ASM_OP_NEST_SPIN
KD_SPIN_ENTRY kd_spin_lock_bh,      0, 1, KD_ASM_SPIN_LOCKED, kd_q_lock_slow,    kd_spin_wait,  kd_spin_lock_plain, KD_ASM_OP_NEST_SPIN

KD_SPIN_ENTRY kd_write_lock,         0, 0, KD_ASM_RW_WLOCKED, kd_write_lock_slow, kd_write_wait, kd_write_lock_plain, KD_ASM_OP_NEST_WRITE
KD_SPIN_ENTRY kd_write_lock_irq,     1, 0, KD_ASM_RW_WLOCKED, kd_write_lock_slow, kd_write_wait, kd_write_lock_plain, KD_ASM_OP_NEST_WRITE
KD_SPIN_ENTRY kd_write_lock_irqsave, 2, 0, KD_ASM_RW_WLOCKED, kd_write_lock_slow, kd_write_wait, kd_write_lock_plain, KD_ASM_OP_NEST_WRITE
KD_SPIN_ENTRY kd_write_lock_bh,      0, 1, KD_ASM_RW_WLOCKED, kd_write_lock_slow, kd_write_wait, kd_write_lock_plain, KD_ASM_OP_NEST_WRITE

/*
 * Clobber entries of the spin class. Inside generated code they are called
 * through the ordinary _jit entries (kd_image.c), whose full state is a
 * correct substitute.
 */
KD_SPIN_ENTRY __kd_spin_lock_cl,  0, 0, KD_ASM_SPIN_LOCKED, kd_q_lock_slow,     kd_spin_wait,  kd_spin_lock_plain,  KD_ASM_OP_NEST_SPIN,  1
KD_SPIN_ENTRY __kd_write_lock_cl, 0, 0, KD_ASM_RW_WLOCKED,  kd_write_lock_slow, kd_write_wait, kd_write_lock_plain, KD_ASM_OP_NEST_WRITE, 1

/*
 * Sleepable-class entry (mutex and rwsem writer).
 *
 * The fast path differs per family and is supplied by the caller of this
 * macro; it must jump to .Lslow_\name on failure with rdi intact.
 *
 * \slowfn(lock, call site) waits on the caller's stack and returns 0 or
 * -EINTR, or KD_SLOW_OFFER with preemption disabled. That pin is internal,
 * not part of the API: every way out of the offer path drops it again
 * (kd_unpin, or the packet's pc_delta on the resume path).
 */
.macro KD_SLEEPABLE_SLOW name:req, slowfn:req, waitfn:req, sleepfn:req, cl=0
.Lslow_\name:
	movq	(%rsp), %rsi
	pushq	%rdi
	call	\slowfn
	popq	%rdi
	cmpl	$KD_SLOW_OFFER, %eax
	je	.Loffer_\name
	RET
.Loffer_\name:
	btsl	$0, KC(KD_CPU_busy)
	jc	.Lnested_\name
	xorl	%eax, %eax			/* a delegated acquisition returns 0 */
.if \cl
	KD_OFFER_CL \waitfn
.else
	KD_OFFER \waitfn
.endif
	js	.Lsleep_\name
	pushq	%rdx
	call	kd_unpin
	popq	%rax
	RET
.Lsleep_\name:
	pushq	%rdi
	pushq	%rsi
	call	kd_unpin
	popq	%rsi
	popq	%rdi
	jmp	\sleepfn			/* sleepfn(lock, wait result) */
.Lnested_\name:
	/* Cannot happen after \slowfn checked busy; kept as a safe way out. */
	decl	PER_CPU_VAR(__preempt_count)
	movl	$KD_WAIT_SLEEP, %esi
	jmp	\sleepfn
.endm

.macro KD_MUTEX_ENTRY name:req, slowfn:req, sleepfn:req, cl=0
SYM_FUNC_START(\name)
	xorl	%eax, %eax
	movb	$1, %dl
	lock cmpxchgb %dl, (%rdi)
	jnz	.Lslow_\name
	movq	PER_CPU_VAR(current_task), %rax
	movq	%rax, KD_MUTEX_owner(%rdi)
	xorl	%eax, %eax
	RET
	KD_SLEEPABLE_SLOW \name, \slowfn, kd_mutex_wait, \sleepfn, \cl
SYM_FUNC_END(\name)
STACK_FRAME_NON_STANDARD \name
EXPORT_SYMBOL(\name)
.endm

KD_MUTEX_ENTRY kd_mutex_lock,               kd_mutex_lock_slow,               kd_mutex_lock_sleep
KD_MUTEX_ENTRY kd_mutex_lock_interruptible, kd_mutex_lock_slow_interruptible, kd_mutex_lock_sleep_interruptible
KD_MUTEX_ENTRY kd_mutex_lock_killable,      kd_mutex_lock_slow_killable,      kd_mutex_lock_sleep_killable
KD_MUTEX_ENTRY kd_mutex_lock_io,            kd_mutex_lock_slow_io,            kd_mutex_lock_sleep_io
KD_MUTEX_ENTRY __kd_mutex_lock_cl,          kd_mutex_lock_slow,               kd_mutex_lock_sleep, 1

.macro KD_RWSEM_ENTRY name:req, slowfn:req, sleepfn:req, cl=0
SYM_FUNC_START(\name)
	xorl	%eax, %eax
	movl	$KD_ASM_RWSEM_WLOCKED, %edx
	lock cmpxchgq %rdx, (%rdi)
	jnz	.Lslow_\name
	xorl	%eax, %eax
	RET
	KD_SLEEPABLE_SLOW \name, \slowfn, kd_down_write_wait, \sleepfn, \cl
SYM_FUNC_END(\name)
STACK_FRAME_NON_STANDARD \name
EXPORT_SYMBOL(\name)
.endm

KD_RWSEM_ENTRY kd_down_write,          kd_down_write_slow,          kd_down_write_sleep
KD_RWSEM_ENTRY kd_down_write_killable, kd_down_write_slow_killable, kd_down_write_sleep_killable
KD_RWSEM_ENTRY __kd_down_write_cl,     kd_down_write_slow,          kd_down_write_sleep, 1

/*
 * Clobber releases. Called natively they are the ordinary release, which
 * keeps more than their callers need. Their own addresses are what tells
 * generated code that a release ends with only rsp and rbp live
 * (KD_SYM_UNLOCK_CL), so that section can leave through kd_jit_exit_cl.
 */
.macro KD_CL_RELEASE name:req, target:req
SYM_FUNC_START(\name)
	jmp	\target
SYM_FUNC_END(\name)
EXPORT_SYMBOL(\name)
.endm

KD_CL_RELEASE __kd_spin_unlock_cl,  kd_spin_unlock
KD_CL_RELEASE __kd_write_unlock_cl, kd_write_unlock
KD_CL_RELEASE __kd_mutex_unlock_cl, kd_mutex_unlock
KD_CL_RELEASE __kd_up_write_cl,     kd_up_write

/*
 * kd_resume - continue the origin from its packet.
 *
 * Reached on the wait stack after the C wait function returned
 * KD_WAIT_RESUMED with interrupts disabled and the preempt count already
 * adjusted. Interrupts stay off until the final popfq so that no handler
 * on this CPU can claim the packet between "busy = 0" and the last load.
 *
 * The continuation address and flags are staged just below the origin's
 * stack pointer, an area the origin's own code treats as free.
 */
SYM_CODE_START(kd_resume)
	UNWIND_HINT_UNDEFINED
	cli
	cmpb	$KD_RS_COMPACT, KR(KD_R_kind)
	je	.Lresume_compact
	movq	KR(KD_R_rbx), %rbx
	movq	KR(KD_R_rcx), %rcx
	movq	KR(KD_R_rdx), %rdx
	movq	KR(KD_R_rsi), %rsi
	movq	KR(KD_R_rdi), %rdi
	movq	KR(KD_R_rbp), %rbp
	movq	KR(KD_R_r8), %r8
	movq	KR(KD_R_r9), %r9
	movq	KR(KD_R_r10), %r10
	movq	KR(KD_R_r11), %r11
	movq	KR(KD_R_r12), %r12
	movq	KR(KD_R_r13), %r13
	movq	KR(KD_R_r14), %r14
	movq	KR(KD_R_r15), %r15
	movq	KR(KD_R_rsp), %rsp
	pushq	KR(KD_R_rip)
	pushq	KR(KD_R_rflags)
	movq	KR(KD_R_rax), %rax
	movl	$0, KC(KD_CPU_busy)
	popfq					/* installs the logical IF */
	ANNOTATE_UNRET_SAFE
	ret
	int3
.Lresume_compact:
	/*
	 * Only rsp, rbp, flags and rax are the origin's. The others are
	 * cleared rather than left with values of the wait path.
	 */
	xorl	%ebx, %ebx
	xorl	%ecx, %ecx
	xorl	%edx, %edx
	xorl	%esi, %esi
	xorl	%edi, %edi
	xorl	%r8d, %r8d
	xorl	%r9d, %r9d
	xorl	%r10d, %r10d
	xorl	%r11d, %r11d
	xorl	%r12d, %r12d
	xorl	%r13d, %r13d
	xorl	%r14d, %r14d
	xorl	%r15d, %r15d
	movq	KR(KD_R_rbp), %rbp
	movq	KR(KD_R_rsp), %rsp
	pushq	KR(KD_R_rip)
	pushq	KR(KD_R_rflags)
	movq	KR(KD_R_rax), %rax
	movl	$0, KC(KD_CPU_busy)
	popfq
	ANNOTATE_UNRET_SAFE
	ret
	int3
SYM_CODE_END(kd_resume)

/*
 * void kd_jit_enter(struct kd_regs *regs, void *code)
 *
 * Run generated code for the packet in @regs starting at @code. Returns
 * when the code leaves through kd_jit_exit; the reason is in kd_cpu.
 * The caller has preemption disabled and has set kd_cpu.cur = @regs.
 *
 * The transfer uses push/ret rather than an indirect jump so that resume
 * points inside an image need no ENDBR and no retpoline.
 */
SYM_FUNC_START(kd_jit_enter)
	pushq	%rbp
	pushq	%rbx
	pushq	%r12
	pushq	%r13
	pushq	%r14
	pushq	%r15
	movq	%rsp, KC(KD_CPU_host_rsp)
	movq	%rdi, %rax
	movq	KD_R_rsp(%rax), %rsp		/* origin's stack from here on */
	pushq	%rsi
	pushq	KD_R_rflags(%rax)
	movq	KD_R_rbp(%rax), %rbp
	cmpb	$KD_RS_COMPACT, KD_R_kind(%rax)
	je	.Lenter_compact
	movq	KD_R_rbx(%rax), %rbx
	movq	KD_R_rcx(%rax), %rcx
	movq	KD_R_rdx(%rax), %rdx
	movq	KD_R_rsi(%rax), %rsi
	movq	KD_R_rdi(%rax), %rdi
	movq	KD_R_r8(%rax), %r8
	movq	KD_R_r9(%rax), %r9
	movq	KD_R_r10(%rax), %r10
	movq	KD_R_r11(%rax), %r11
	movq	KD_R_r12(%rax), %r12
	movq	KD_R_r13(%rax), %r13
	movq	KD_R_r14(%rax), %r14
	movq	KD_R_r15(%rax), %r15
	movq	KD_R_rax(%rax), %rax
	popfq
	ANNOTATE_UNRET_SAFE
	ret
	int3
.Lenter_compact:
	/* The section relies on nothing else; the executor's values are not passed on. */
	xorl	%ebx, %ebx
	xorl	%ecx, %ecx
	xorl	%edx, %edx
	xorl	%esi, %esi
	xorl	%edi, %edi
	xorl	%r8d, %r8d
	xorl	%r9d, %r9d
	xorl	%r10d, %r10d
	xorl	%r11d, %r11d
	xorl	%r12d, %r12d
	xorl	%r13d, %r13d
	xorl	%r14d, %r14d
	xorl	%r15d, %r15d
	movq	KD_R_rax(%rax), %rax
	popfq
	ANNOTATE_UNRET_SAFE
	ret
	int3
SYM_FUNC_END(kd_jit_enter)
STACK_FRAME_NON_STANDARD kd_jit_enter

/*
 * kd_nested_exit - leave generated code from inside a contended lock call.
 *
 * In: rdi = lock, rax = value the lock call returns, edx = exit code,
 *     [rsp] = return address in generated code.
 *
 * The call's side effects on this CPU (preempt count, interrupt flag) are
 * already in place and stay; only the wait is still owed. Caller-saved
 * registers are dead after a call, so the callee-saved set, the stack
 * pointer past the return address and the return value are the whole
 * continuation. The return address becomes kd_cpu.resume: it is where
 * whoever obtains the lock continues.
 */
SYM_CODE_START(kd_nested_exit)
	UNWIND_HINT_UNDEFINED
	movl	%edx, KC(KD_CPU_exit_code)
	movq	KC(KD_CPU_cur), %rdx
	movq	%rax, KD_R_rax(%rdx)
	movq	%rbx, KD_R_rbx(%rdx)
	movq	%rbp, KD_R_rbp(%rdx)
	movq	%rdi, KD_R_rdi(%rdx)
	movq	%r12, KD_R_r12(%rdx)
	movq	%r13, KD_R_r13(%rdx)
	movq	%r14, KD_R_r14(%rdx)
	movq	%r15, KD_R_r15(%rdx)
	popq	%rax
	movq	%rax, KC(KD_CPU_resume)
	movq	%rsp, KD_R_rsp(%rdx)
	pushfq
	popq	KD_R_rflags(%rdx)
	movb	$KD_RS_FULL, KD_R_kind(%rdx)
	movq	KC(KD_CPU_host_rsp), %rsp
	cld
	popq	%r15
	popq	%r14
	popq	%r13
	popq	%r12
	popq	%rbx
	popq	%rbp
	RET
SYM_CODE_END(kd_nested_exit)

/*
 * kd_jit_exit - generated code jumps here after its exit stub stored
 * exit_ip / exit_code (and resume, aux where applicable) in kd_cpu.
 *
 * Saves the complete register state into the packet, returns to the
 * executor's stack and from kd_jit_enter. Exit stubs for instructions use
 * only mov, so the flags saved here are the source program's flags.
 */
SYM_CODE_START(kd_jit_exit)
	UNWIND_HINT_UNDEFINED
	movq	%rax, KC(KD_CPU_tmp)
	movq	KC(KD_CPU_cur), %rax
	movq	%rbx, KD_R_rbx(%rax)
	movq	%rcx, KD_R_rcx(%rax)
	movq	%rdx, KD_R_rdx(%rax)
	movq	%rsi, KD_R_rsi(%rax)
	movq	%rdi, KD_R_rdi(%rax)
	movq	%rbp, KD_R_rbp(%rax)
	movq	%rsp, KD_R_rsp(%rax)
	movq	%r8, KD_R_r8(%rax)
	movq	%r9, KD_R_r9(%rax)
	movq	%r10, KD_R_r10(%rax)
	movq	%r11, KD_R_r11(%rax)
	movq	%r12, KD_R_r12(%rax)
	movq	%r13, KD_R_r13(%rax)
	movq	%r14, KD_R_r14(%rax)
	movq	%r15, KD_R_r15(%rax)
	pushfq
	popq	KD_R_rflags(%rax)
	movb	$KD_RS_FULL, KD_R_kind(%rax)
	movq	KC(KD_CPU_tmp), %rbx
	movq	%rbx, KD_R_rax(%rax)
	movq	KC(KD_CPU_host_rsp), %rsp
	cld
	popq	%r15
	popq	%r14
	popq	%r13
	popq	%r12
	popq	%rbx
	popq	%rbp
	RET
SYM_CODE_END(kd_jit_exit)

/*
 * kd_jit_exit_cl - the exit at a clobber release that ends the section
 * (KD_SYM_UNLOCK_CL, not a sibling call). Its caller keeps nothing in
 * registers across the call but rsp and rbp, and the release returns
 * nothing, so that and the flags are the whole state: a compact one, in
 * line 0 of the packet (kind is in line 1, which the executor writes
 * anyway).
 */
SYM_CODE_START(kd_jit_exit_cl)
	UNWIND_HINT_UNDEFINED
	movq	KC(KD_CPU_cur), %rax
	movq	%rbp, KD_R_rbp(%rax)
	movq	%rsp, KD_R_rsp(%rax)
	pushfq
	popq	KD_R_rflags(%rax)
	movb	$KD_RS_COMPACT, KD_R_kind(%rax)
	movq	KC(KD_CPU_host_rsp), %rsp
	cld
	popq	%r15
	popq	%r14
	popq	%r13
	popq	%r12
	popq	%rbx
	popq	%rbp
	RET
SYM_CODE_END(kd_jit_exit_cl)
