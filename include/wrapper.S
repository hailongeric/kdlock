/* SPDX-License-Identifier: GPL-2.0-only */
/* Per-image entry template for the original UB-derived KD mapping. Lowering
 * substitutes KD_JIT_ENTRY and KD_GENERATED_BODY for one image's own code.
 * All source state remains in its original thread's one canonical packet.
 * The caller supplies fresh origin GS/task inputs, exclusive source execution,
 * valid source/code bindings and the declared sleepable physical context.
 * The distinct executor's native stack and all origin waiting/control stacks
 * must be admitted disjoint from the stopped source stack; this template does
 * not establish or allocate that context and cannot execute an origin's own
 * source on overlapping native frames.
 * General flags/SIMD use AS01; this unrun wrapper is no equivalence evidence.
 */
#include "asm_head.h"

	.intel_syntax noprefix
	.text
	.p2align 4
	.globl KD_JIT_ENTRY
	.type KD_JIT_ENTRY, @function
KD_JIT_ENTRY:
	endbr64
	/* Preserve the executor's native callee-saved state. Logical source
	 * BP/SP are separate and never replace physical RBP/RSP here. */
	push rbp
	mov rbp, rsp
	push rbx
	push r12
	push r13
	push r14
	push r15
	/* Allocate every private slot before stores, without using a red zone
	 * or changing the assumed source flags during packet import. */
	lea rsp, [rsp - KD_WRAPPER_LOCAL_BYTES]
	mov Stack_IO, rsi
	mov REG_BANK, rdi
	mov r14, QWORD PTR[rsi + KD_JIT_IO_ORIGIN_GS]
	mov Stack_RGS, r14
	mov r14, QWORD PTR[rsi + KD_JIT_IO_ORIGIN_TASK]
	mov Stack_TASK, r14
	/* Source R11--R15 already have canonical backing. Only the resident
	 * source GPRs and stable BP/SP caches need importing. */
	mov rbx, QWORD PTR[REG_BANK + KD_REG_BX]
	mov r10, QWORD PTR[REG_BANK + KD_REG_R10]
	mov r9, QWORD PTR[REG_BANK + KD_REG_R9]
	mov r8, QWORD PTR[REG_BANK + KD_REG_R8]
	mov rax, QWORD PTR[REG_BANK + KD_REG_AX]
	mov rcx, QWORD PTR[REG_BANK + KD_REG_CX]
	mov rdx, QWORD PTR[REG_BANK + KD_REG_DX]
	mov rsi, QWORD PTR[REG_BANK + KD_REG_SI]
	mov rdi, QWORD PTR[REG_BANK + KD_REG_DI]
	mov r12, Stack_RBP
	mov r13, Stack_RSP
	jmp .Lkd_dispatch

/* KD_GENERATED_BODY */

.Lkd_export:
	/* The generated exit has already flushed mapped source GPRs, recovered
	 * physical R12/R13 as BP/SP and written the exact control result slots.
	 * Save all resident source values before reusing RAX/R14 for control. */
	mov Stack_RBP, r12
	mov Stack_RSP, r13
	mov QWORD PTR[REG_BANK + KD_REG_BX], rbx
	mov QWORD PTR[REG_BANK + KD_REG_R10], r10
	mov QWORD PTR[REG_BANK + KD_REG_R9], r9
	mov QWORD PTR[REG_BANK + KD_REG_R8], r8
	mov QWORD PTR[REG_BANK + KD_REG_AX], rax
	mov QWORD PTR[REG_BANK + KD_REG_CX], rcx
	mov QWORD PTR[REG_BANK + KD_REG_DX], rdx
	mov QWORD PTR[REG_BANK + KD_REG_SI], rsi
	mov QWORD PTR[REG_BANK + KD_REG_DI], rdi
	mov rax, Stack_RESUME
	mov QWORD PTR[REG_BANK + KD_REG_IP], rax
	mov r14, Stack_IO
	mov rax, Stack_KIND
	mov QWORD PTR[r14 + KD_JIT_IO_KIND], rax
	mov rax, Stack_DETAIL
	mov QWORD PTR[r14 + KD_JIT_IO_DETAIL], rax
	mov rax, Stack_SOURCE
	mov QWORD PTR[r14 + KD_JIT_IO_SOURCE_IP], rax
	mov rax, Stack_TARGET
	mov QWORD PTR[r14 + KD_JIT_IO_TARGET], rax
	mov rax, Stack_PHASE
	mov QWORD PTR[r14 + KD_JIT_IO_PHASE], rax
	/* Keep all private slots allocated through their final read. Returning
	 * publishes no ownership transfer by itself; lock code owns that order. */
	lea rsp, [rbp - 40]
	pop r15
	pop r14
	pop r13
	pop r12
	pop rbx
	pop rbp
	ret
	.size KD_JIT_ENTRY, .-KD_JIT_ENTRY
	.section .note.GNU-stack, "", @progbits
