/* SPDX-License-Identifier: GPL-2.0-only */
/* Private prepared root entry. All fallible admission/resource work precedes
 * the compiler-clobber prefix. DI=object, SI=pre-CALL source SP, DX=post-CALL
 * source label, CX=source BP, R8=retained entry metadata. No packet is copied.
 * The task owns its admitted auxiliary wait stack; no source is published while
 * native wait/control frames still occupy the original source stack.
 * This source-only bridge supplies no IRQ/unwind/return-mitigation proof.
 */
#include "kd_mutex.h"

	.intel_syntax noprefix
	.text
	.p2align 4
	.globl kd_mutex_entry_asm
	.type kd_mutex_entry_asm, @function
kd_mutex_entry_asm:
	endbr64
	/* Preserve each declared input in registers before using normal C ABI:
	 * run(entry, object, source_sp, continuation_ip, source_bp).
	 * This entry does not use RBP as scratch; source BP is the fifth argument.
	 */
	mov r9, rcx
	mov rax, rdi
	mov rdi, r8
	mov r8, r9
	mov rcx, rdx
	mov rdx, rsi
	mov rsi, rax
	/* Root admission has retained and checked this exact task-owned range,
	 * aligned top, complete callback capacity and nonreturning callback.
	 * No prologue/helper/source publication is allowed before this switch.
	 */
	/* Entered phase prevents private cancellation after this boundary, even
	 * when the callback later owns a fresh native binding on this stack. */
	mov QWORD PTR[rdi + KD_MUTEX_ENTRY_PHASE], KD_MUTEX_ENTRY_ENTERED
	mov rsp, QWORD PTR[rdi + KD_MUTEX_ENTRY_CONTROL_TOP]
	call QWORD PTR[rdi + KD_MUTEX_ENTRY_RUN]
	/* A callback return cannot restore source after possible mutex effects.
	 * This is an internal contract violation, never a source replay route.
	 */
	ud2
	.size kd_mutex_entry_asm, .-kd_mutex_entry_asm
	.section .note.GNU-stack, "", @progbits
