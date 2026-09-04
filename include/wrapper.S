#include "asm_head.h"

	.intel_syntax noprefix

main:
	endbr64
	push	rbp			/* Save the native stack frame. */
	mov	rbp, rsp

	push	rbx			/* Preserve callee-saved registers. */
	push	r12
	push	r13
	push	r14
	push	r15

	push	rdi			/* Stack_PT_REG */
	push	rsi			/* Stack_ARG_REG */

	mov	PT_REG, rdi
	mov	ARG_REG, rsi

	mov	rbx, PT_RBX
	mov	r11, PT_R11
	mov	r10, PT_R10
	mov	r9, PT_R9
	mov	r8, PT_R8
	mov	rax, PT_RAX
	mov	rcx, PT_RCX
	mov	rdx, PT_RDX
	mov	rsi, PT_RSI
	mov	rdi, PT_RDI

	push	PT_RBP
	push	PT_RSP
	push	PT_R15
	push	PT_R14
	push	PT_R13
	push	PT_R12
	push	PT_R11
	push	PT_GS
	push	PT_TASK
	sub	RSP, 3*8		/* Stack_RIP, Stack_IJ, Stack_INST_CNT */
	mov	Stack_INST_CNT, 0

	mov	R13, Stack_RSP
	mov	R12, Stack_RBP

#include "jit.S"

comp_syscall:
	mov	Stack_IJ, 0x0
	jmp	exit

ij_failed:
	mov	Stack_IJ, R15
	jmp	exit

seg_error:
	mov	Stack_IJ, 0x3
	jmp	exit

seg_error2:
	popf
	mov	Stack_IJ, 0x3
	jmp	exit

inst_limit:
	mov	Stack_IJ, 0x4
	jmp	exit

exit:
	mov	Stack_RIP, R14
	mov	Stack_RSP, R13
	mov	Stack_RBP, R12

	mov	PT_REG, Stack_PT_REG
	mov	ARG_REG, Stack_ARG_REG

	pop	MEM_ARG2		/* args[1] <- Stack_INST_CNT */
	pop	MEM_ARG			/* args[0] <- Stack_IJ */
	pop	PT_RIP
	add	RSP, 2*8		/* Discard Stack_RGS and Stack_TASK. */

	pop	PT_R11
	pop	PT_R12
	pop	PT_R13
	pop	PT_R14
	pop	PT_R15
	pop	PT_RSP
	pop	PT_RBP

	mov	PT_RBX, rbx
	mov	PT_R10, r10
	mov	PT_R9, r9
	mov	PT_R8, r8
	mov	PT_RAX, rax
	mov	PT_RCX, rcx
	mov	PT_RDX, rdx
	mov	PT_RSI, rsi
	mov	PT_RDI, rdi

	add	rsp, 2*8		/* Discard Stack_PT_REG and Stack_ARG_REG. */
	pop	r15
	pop	r14
	pop	r13
	pop	r12
	pop	rbx
	pop	rbp
	ret
