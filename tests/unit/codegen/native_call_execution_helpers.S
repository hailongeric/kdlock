/* SPDX-License-Identifier: GPL-2.0 */
/* Ordinary ABI glue contains the clobber-all wrapper call. The helpers destroy
 * every SysV volatile GPR; only the declared native return value survives. */
.text
.globl fixture_invoke_clobber
.type fixture_invoke_clobber,@function
fixture_invoke_clobber:
	pushq %rbp
	movq %rsp, %rbp
	pushq %rbx
	pushq %r12
	pushq %r13
	pushq %r14
	pushq %r15
	subq $8, %rsp
	/* Both kernel-C stack residues are legal. Recover the exact caller stack
	 * through RBP after the wrapper independently aligns its private stack. */
	subq fixture_invoke_padding(%rip), %rsp
	movq %rsp, %r11
	subq $8, %r11
	andq $15, %r11
	movq %r11, fixture_wrapper_stack_residue(%rip)
	movq %rdi, %rdx
	leaq 8(%rdi), %rsi
	movq 24(%rdi), %rax
	movq (%rdi), %rdi
	call *%rax
	leaq -40(%rbp), %rsp
	popq %r15
	popq %r14
	popq %r13
	popq %r12
	popq %rbx
	popq %rbp
	ret
.size fixture_invoke_clobber,.-fixture_invoke_clobber

.macro alignment_check
	movq %rsp, %r11
	andq $15, %r11
	cmpq $8, %r11
	je 1f
	incq fixture_alignment_errors(%rip)
1:
.endm

.macro capture_entry
	/* Observe actual native-entry flags before the alignment oracle changes
	 * them. Each C body checks these observations, including repeated calls. */
	pushfq
	popq fixture_helper_entry_flags(%rip)
	movq %rcx, fixture_helper_entry_rcx(%rip)
.endm

.globl fixture_hostile_strcmp
.type fixture_hostile_strcmp,@function
fixture_hostile_strcmp:
	capture_entry
	alignment_check
	subq $8, %rsp
	call fixture_strcmp_body
	addq $8, %rsp
	/* An int return promises only EAX; poison its upper half deliberately. */
	movabsq $0xfedcba9800000000, %r11
	orq %r11, %rax
	jmp .Lclobber_volatile
.size fixture_hostile_strcmp,.-fixture_hostile_strcmp

.globl fixture_hostile_pad
.type fixture_hostile_pad,@function
fixture_hostile_pad:
	capture_entry
	alignment_check
	subq $8, %rsp
	call fixture_pad_body
	addq $8, %rsp
.Lclobber_volatile:
	/* Byte addition defines all six arithmetic flags: CF/PF/AF/ZF set,
	 * SF/OF clear. This differs from the fixture's incoming flag pattern. */
	movl $255, %ecx
	addb $1, %cl
	pushfq
	popq fixture_helper_output_flags(%rip)
	movabsq $0xa1a1a1a1a1a1a1a1, %rcx
	movabsq $0xa2a2a2a2a2a2a2a2, %rdx
	movabsq $0xa3a3a3a3a3a3a3a3, %rsi
	movabsq $0xa4a4a4a4a4a4a4a4, %rdi
	movabsq $0xa5a5a5a5a5a5a5a5, %r8
	movabsq $0xa6a6a6a6a6a6a6a6, %r9
	movabsq $0xa7a7a7a7a7a7a7a7, %r10
	movabsq $0xa8a8a8a8a8a8a8a8, %r11
	ret
.size fixture_hostile_pad,.-fixture_hostile_pad
.section .note.GNU-stack,"",@progbits
