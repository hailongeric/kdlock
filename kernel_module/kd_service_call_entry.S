/* SPDX-License-Identifier: GPL-2.0 */
/* One real returning C CALL on the origin's Native task stack. Metadata and
 * output stores use retained storage; no source return word is replaced. */
#include <linux/linkage.h>
#include <asm/nospec-branch.h>
#include <asm/unwind_hints.h>
#include "kd_service_calls.h"
#include "kd_regs.h"

	.text
SYM_FUNC_START(kd_service_origin_bridge)
	endbr64
	pushq %rbp
	pushq %rbx
	pushq %r12
	pushq %r13
	pushq %r14
	pushq %r15
	movq %rdi, %r12
	movq %rsp, KD_ORIGIN_CALL_SHADOW_SP(%r12)
	movq %rbp, KD_ORIGIN_CALL_SHADOW_BP(%r12)
	/* Before either preemption change, SP lies in task->stack below the
	 * suspended source CALL. No shadow frame is ever scheduled away. */
	movq KD_ORIGIN_CALL_NATIVE_SP(%r12), %rsp
	UNWIND_HINT_UNDEFINED
	movq KD_ORIGIN_CALL_PACKET(%r12), %rbx
	movq KD_REG_BP(%rbx), %rbp
	movq %r12, %rdi
	call kd_service_origin_context_begin
	movq KD_REG_DI(%rbx), %rdi
	movq KD_REG_SI(%rbx), %rsi
	movq KD_REG_DX(%rbx), %rdx
	movq KD_REG_CX(%rbx), %rcx
	movq KD_REG_R8(%rbx), %r8
	movq KD_REG_R9(%rbx), %r9
	movq KD_ORIGIN_CALL_TARGET(%r12), %r11
	CALL_NOSPEC r11
	/* Save every C-volatile output and flags before context restoration can
	 * change them. Source callee-saved virtual values stay in the packet. */
	pushfq
	popq KD_REG_FLAGS(%rbx)
	movq %rax, KD_REG_AX(%rbx)
	movq %rcx, KD_REG_CX(%rbx)
	movq %rdx, KD_REG_DX(%rbx)
	movq %rsi, KD_REG_SI(%rbx)
	movq %rdi, KD_REG_DI(%rbx)
	movq %r8, KD_REG_R8(%rbx)
	movq %r9, KD_REG_R9(%rbx)
	movq %r10, KD_REG_R10(%rbx)
	movq %r11, KD_REG_R11(%rbx)
	movq %r12, %rdi
	call kd_service_origin_context_end
	movq KD_ORIGIN_CALL_SHADOW_SP(%r12), %rsp
	UNWIND_HINT_UNDEFINED
	popq %r15
	popq %r14
	popq %r13
	popq %r12
	popq %rbx
	popq %rbp
	RET
SYM_FUNC_END(kd_service_origin_bridge)
	.section .note.GNU-stack,"",@progbits
