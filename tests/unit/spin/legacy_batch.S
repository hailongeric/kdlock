/* Frozen pre-unified runner: exercise compatibility with KDWB001 images.
 * Test-only; production uses the compiler clobber boundary for both ABIs. */
/* SPDX-License-Identifier: GPL-2.0 */
/* The lock scheduler, not generated JIT code, chooses every successor. Save the
 * original combiner once; neither virtual registers nor a wrapper C frame must
 * survive the callback. All state needed across a clobber-all call is on stack.
 * This is deliberately a separate ABI from a normal C function pointer call. */
#include <linux/linkage.h>
#include <asm/nospec-branch.h>

SYM_FUNC_START(kd_spin_batch_enter)
	pushq %rbp
	movq %rsp, %rbp
	pushq %rbx
	pushq %r12
	pushq %r13
	pushq %r14
	pushq %r15
	subq $24, %rsp
	movq %rdi, 0(%rsp)
	movq %rsi, 8(%rsp)
.Lstep:
	leaq 64(%rsp), %rbp
	movq 0(%rsp), %rdi
	movq 8(%rsp), %rax
	CALL_NOSPEC rax
	testq %rax, %rax
	jz .Ldone
	movq %rax, %rdx
	movq 0(%rax), %rdi
	leaq 8(%rax), %rsi
	movq 24(%rax), %rax
	CALL_NOSPEC rax
	jmp .Lstep
.Ldone:
	addq $24, %rsp
	popq %r15
	popq %r14
	popq %r13
	popq %r12
	popq %rbx
	popq %rbp
	RET
SYM_FUNC_END(kd_spin_batch_enter)
.section .note.GNU-stack,"",@progbits
