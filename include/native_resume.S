/* SPDX-License-Identifier: GPL-2.0-only */
/* Exact-IP/SP native continuation on the original task, after its C bridge has
 * accepted the fresh native binding. This is not a source CALL/RET completion:
 * the temporary bridge word leaves final source SP exactly unchanged. The
 * admitted retained stack must include writable SP-8; no red-zone use is
 * assumed. Old executor/control frames are abandoned, never returned through.
 * General flags/SIMD use AS01. Return mitigation coverage is unvalidated.
 */
#include "kd_regs.h"

	.intel_syntax noprefix
	.text
	.p2align 4
	.globl kd_native_resume
	.type kd_native_resume, @function
kd_native_resume:
	endbr64
	/* RDI keeps the canonical packet pointer until its final packet read. */
	mov rsp, QWORD PTR[rdi + KD_REG_SP]
	push QWORD PTR[rdi + KD_REG_IP]
	mov rbp, QWORD PTR[rdi + KD_REG_BP]
	mov r15, QWORD PTR[rdi + KD_REG_R15]
	mov r14, QWORD PTR[rdi + KD_REG_R14]
	mov r13, QWORD PTR[rdi + KD_REG_R13]
	mov r12, QWORD PTR[rdi + KD_REG_R12]
	mov r11, QWORD PTR[rdi + KD_REG_R11]
	mov rbx, QWORD PTR[rdi + KD_REG_BX]
	mov r10, QWORD PTR[rdi + KD_REG_R10]
	mov r9, QWORD PTR[rdi + KD_REG_R9]
	mov r8, QWORD PTR[rdi + KD_REG_R8]
	mov rax, QWORD PTR[rdi + KD_REG_AX]
	mov rcx, QWORD PTR[rdi + KD_REG_CX]
	mov rdx, QWORD PTR[rdi + KD_REG_DX]
	mov rsi, QWORD PTR[rdi + KD_REG_SI]
	mov rdi, QWORD PTR[rdi + KD_REG_DI]
	ret
	.size kd_native_resume, .-kd_native_resume
	/* The last spin unlock left no grant. Keep the control pin until
	 * the source stack and its frame chain are active. Build a transient
	 * frame whose caller is the exact post-unlock continuation. The
	 * admitted source stack has room for the ordinary unlock and its
	 * scheduling path here. R12 retains the canonical packet across the
	 * C call, and kd_native_resume restores source R12 and exact IP/SP.
	 */
	.p2align 4
	.globl kd_spin_native_resume
	.type kd_spin_native_resume, @function
kd_spin_native_resume:
	endbr64
	mov r12, rdi
	mov rsp, QWORD PTR[rdi + KD_REG_SP]
	push QWORD PTR[rdi + KD_REG_IP]
	push QWORD PTR[rdi + KD_REG_BP]
	mov rbp, rsp
	and rsp, -16
	call kd_spin_resume_unpin
	mov rdi, r12
	jmp kd_native_resume
	.size kd_spin_native_resume, .-kd_spin_native_resume
	.section .note.GNU-stack, "", @progbits
