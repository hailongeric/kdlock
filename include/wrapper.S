/* Callable shell around generated jit.S. Physical RSP/RBP belong to combiner;
 * virtual SP/BP and spilled GPRs belong to the shared packet. args has two words,
 * reused for exit kind and body witness. Current flags are not written back. */
#include "asm_head.h"
#ifndef KD_GENERATED_ENTRY_ABI
#define KD_GENERATED_ENTRY_ABI 0
#endif
/* Unknown/standalone images retain the two imports. Translation may omit an
 * unused import, while the directory, frame slots and two-word ABI stay fixed. */
#ifndef KD_GENERATED_GS_INPUT
#define KD_GENERATED_GS_INPUT 1
#endif
#ifndef KD_GENERATED_TASK_INPUT
#define KD_GENERATED_TASK_INPUT 1
#endif

	.intel_syntax noprefix

main:
	endbr64
	/* Fixed, versioned entry directory; old uploads use only main. */
	.byte 0xe9
	.long regular_entry - . - 4
	.ascii "KDWB002"
batch_entry:
	endbr64
	.byte 0xe9
	.long batch_body - . - 4
	.ascii "KDWC002"
clobber_entry_v1:
	endbr64
	.byte 0xe9
	.long clobber_body - . - 4
	.ascii "KDAB"
	.byte KD_GENERATED_ENTRY_ABI
	.balign 16
batch_body:
	/* The lock-side clobber caller owns the native combiner live values.
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
	sub rsp, 14*8
	mov Stack_BATCH, rdx
	mov Stack_CLOBBER, 0
	mov PT_REG, rdi
	mov REG_BANK, rdi
	mov ARG_REG, rsi
	/* Spilled virtual GPRs already live in regs; only CPU-resident values
	 * need importing. R11 holds their backing pointer, never logical R11. */
#if KD_GENERATED_GS_INPUT
	mov rax, PT_GS
	mov Stack_RGS, rax
#endif
#if KD_GENERATED_TASK_INPUT
	mov rax, PT_TASK
	mov Stack_TASK, rax
#endif
	mov Stack_JIT_WITNESS, 0
	mov rbx, PT_RBX
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

	jmp generated_body

clobber_body:
	cmp QWORD PTR[rdx + 72], KD_GENERATED_ENTRY_ABI
	jne clobber_invalid
	mov rax, QWORD PTR[rdx + 80]
	cmp DWORD PTR[rax], 1
	jne clobber_invalid
	/* Same JIT scratch offsets, without a thread GPR import or group save. */
	push rbp
	mov rbp, rsp
	sub rsp, 5*8
	push rdi
	push rsi
	sub rsp, 14*8
	/* Clobber exits never read the legacy-only Stack_BATCH slot. */
	mov Stack_CLOBBER, rdx
	mov PT_REG, rdi
	mov REG_BANK, rdi
	mov ARG_REG, rsi
	mov R12, PT_RBP
	mov R13, PT_RSP
#if KD_GENERATED_GS_INPUT
	mov rax, PT_GS
	mov Stack_RGS, rax
#endif
#if KD_GENERATED_TASK_INPUT
	mov rax, PT_TASK
	mov Stack_TASK, rax
#endif
	mov Stack_JIT_WITNESS, 0
	/* The fixed directory is usable only by a matching generated image. */
#if KD_GENERATED_ENTRY_ABI != 1 && KD_GENERATED_ENTRY_ABI != 2 && KD_GENERATED_ENTRY_ABI != 3
	ud2
#endif
generated_body:
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
	mov R15, Stack_CLOBBER
	test R15, R15
	jz legacy_exit
	/* Entry refusal preserves the three-word input without materializing GPRs. */
	cmp Stack_IJ, 6
	je clobber_refused
	cmp QWORD PTR[R15 + 88], 0
	je full_exit
	cmp Stack_IJ, 1
	jne full_exit
	cmp R14, QWORD PTR[R15 + 40]
	jne full_exit
	cmp RDI, QWORD PTR[R15 + 32]
	jne full_exit
	/* Prove the exact post-CALL boundary before granting minimal completion. */
	lea R14, [R13 + 8]
	cmp RSI, R14
	jne clobber_bad_metadata
	cmp RCX, R12
	jne clobber_bad_metadata
	cmp RDX, QWORD PTR[R13]
	jne clobber_bad_metadata
clobber_complete:
	/* A fused terminal CALL reaches here only after the same identity and
	 * SP/IP/BP proof, with the pre-CALL stack untouched. */
	mov PT_REG, Stack_PT_REG
	mov PT_RIP, rdx
	mov PT_RSP, rsi
	mov PT_RBP, R12
	mov rax, QWORD PTR[R15 + 80]
	mov DWORD PTR[rax], 2
	mov ARG_REG, Stack_ARG_REG
	mov MEM_ARG, 7
	jmp clobber_result
clobber_bad_metadata:
	/* Keep the actual target for a full, checked control exit. */
	mov R14, QWORD PTR[R15 + 40]
	jmp full_exit
clobber_refused:
	mov ARG_REG, Stack_ARG_REG
	mov MEM_ARG, 6
clobber_result:
	mov rax, Stack_JIT_WITNESS
	mov MEM_ARG2, rax
	jmp clobber_return
legacy_exit:
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
	/* R11--R15 backing values were written directly by the JIT spills. */
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

	/* SP/BP above and all virtual GPR spills already use the packet. */

	mov	PT_RBX, rbx
	mov	PT_R10, r10
	mov	PT_R9, r9
	mov	PT_R8, r8
	mov	PT_RAX, rax
	mov	PT_RCX, rcx
	mov	PT_RDX, rdx
	mov	PT_RSI, rsi
	mov	PT_RDI, rdi

	/* Keep all private slots allocated until their final read. With IRQs
	 * enabled, advancing RSP first exposes metadata to interrupt frames.
	 * GPRs are already exported, so RAX can copy the three result words. */
	mov rax, Stack_JIT_WITNESS
	mov MEM_ARG2, rax
	mov rax, Stack_IJ
	mov MEM_ARG, rax
	mov rax, Stack_RIP
	mov PT_RIP, rax
	cmp Stack_CLOBBER, 0
	je legacy_return
	mov rax, Stack_CLOBBER
	mov rax, QWORD PTR[rax + 80]
	mov DWORD PTR[rax], 0
	jmp clobber_return
legacy_return:
	cmp Stack_BATCH, 0
	jne batch_return
	lea rsp, [rbp - 5*8]
	pop	r15
	pop	r14
	pop	r13
	pop	r12
	pop	rbx
	pop	rbp
	ret

clobber_invalid:
	ud2
clobber_return:
	mov rsp, rbp
	pop rbp
	ret

batch_return:
	lea rsp, [rbp + 8]
	ret
