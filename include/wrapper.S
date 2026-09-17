/* Callable shell around generated jit.S. Physical RSP/RBP belong to combiner;
 * virtual SP/BP and spilled GPRs belong to waiter. args has exactly two words,
 * reused for exit kind and body witness. Current flags are not written back. */
#include "asm_head.h"

	.intel_syntax noprefix

main:
	endbr64
	/* Fixed, versioned entry directory; old uploads use only main. */
	.byte 0xe9
	.long regular_entry - . - 4
	.ascii "KDWB001"
batch_entry:
	endbr64
	/* The lock-side runner already saved the native combiner registers.
	 * Reserve the same frame slots without writing six redundant values. */
	sub rsp, 6*8
	lea rbp, [rsp + 5*8]
	jmp load_packet
regular_entry:
	push rbp
	mov rbp, rsp
	push rbx
	push r12
	push r13
	push r14
	push r15
	xor edx, edx
load_packet:
	push rdi
	push rsi
	/* Allocate before stores: no kernel red-zone use. The additional slot
	 * keeps the original jit.S offsets and both args words unchanged. */
	sub rsp, 13*8
	mov Stack_BATCH, rdx
	mov PT_REG, rdi
	mov ARG_REG, rsi
	mov rax, PT_RBP
	mov Stack_RBP, rax
	mov rax, PT_RSP
	mov Stack_RSP, rax
	mov rax, PT_R15
	mov Stack_R15, rax
	mov rax, PT_R14
	mov Stack_R14, rax
	mov rax, PT_R13
	mov Stack_R13, rax
	mov rax, PT_R12
	mov Stack_R12, rax
	mov rax, PT_R11
	mov Stack_R11, rax
	mov rax, PT_GS
	mov Stack_RGS, rax
	mov rax, PT_TASK
	mov Stack_TASK, rax
	mov Stack_JIT_WITNESS, 0
	mov rbx, PT_RBX
	mov r11, PT_R11
	mov r10, PT_R10
	mov r9, PT_R9
	mov r8, PT_R8
	mov rax, PT_RAX
	mov rcx, PT_RCX
	mov rdx, PT_RDX
	mov rsi, PT_RSI
	mov rdi, PT_RDI
	mov R13, Stack_RSP
	mov R12, Stack_RBP

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
	/* Only a lock-side admitted pristine root can take the reduced ABI exit.
	 * R15 is translator scratch here; the logical R15 is already spilled.
	 * Every other exit writes the full packet for hostcall/native/continuation. */
	mov R15, Stack_BATCH
	test R15, R15
	jz full_exit
	cmp Stack_IJ, 1
	jne full_exit
	cmp R14, QWORD PTR[R15 + 40]
	jne full_exit
	cmp RDI, QWORD PTR[R15 + 32]
	jne full_exit
	mov PT_REG, Stack_PT_REG
	mov PT_RBX, rbx
	mov PT_RBP, R12
	mov PT_RSP, R13
	mov PT_RDI, rdi
	mov rax, Stack_R15
	mov PT_R15, rax
	mov rax, Stack_R14
	mov PT_R14, rax
	mov rax, Stack_R13
	mov PT_R13, rax
	mov rax, Stack_R12
	mov PT_R12, rax
	mov rax, QWORD PTR[R15 + 40]
	mov PT_RIP, rax
	mov ARG_REG, Stack_ARG_REG
	mov MEM_ARG, 1
	mov rax, Stack_JIT_WITNESS
	mov MEM_ARG2, rax
	lea rsp, [rbp + 8]
	ret
full_exit:
	mov	Stack_RIP, R14
	mov	Stack_RSP, R13
	mov	Stack_RBP, R12

	mov	PT_REG, Stack_PT_REG
	mov	ARG_REG, Stack_ARG_REG

	lea rsp, [rbp - 19*8]
	pop	MEM_ARG2		/* args[1] <- Stack_JIT_WITNESS */
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
	cmp Stack_BATCH, 0
	jne batch_return
	pop	r15
	pop	r14
	pop	r13
	pop	r12
	pop	rbx
	pop	rbp
	ret

batch_return:
	add rsp, 6*8
	ret
