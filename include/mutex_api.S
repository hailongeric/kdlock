/* SPDX-License-Identifier: GPL-2.0-only */
/* Ordinary source-operation entries. No source is lent before the prepared
 * task-owned auxiliary switch. The four scalars are original declared inputs,
 * not a packet copy or native waiter-body execution engine. Admission performs
 * no allocation. A NULL descriptor reports completed native unlock work; a
 * prepared descriptor selects the auxiliary route before any source lending.
 * Its transient source-stack frames are fully unwound before the switch.
 */
#include "kd_mutex_api.h"

	.intel_syntax noprefix
	.text

	.macro KD_MUTEX_SOURCE_ENTRY symbol, prepare
	.p2align 4
	.globl \symbol
	.type \symbol, @function
\symbol:
	endbr64
	/* Preserve all four declared scalars, then align the C call independently
	 * of the source compiler's stack alignment. The saved cursor belongs to
	 * this transient native bootstrap, not another source continuation.
	 */
	push rdi
	push rsi
	push rdx
	push rcx
	mov rax, rsp
	and rsp, -16
	sub rsp, 16
	mov QWORD PTR[rsp], rax
	call \prepare
	mov rsp, QWORD PTR[rsp]
	mov r8, rax
	pop rcx
	pop rdx
	pop rsi
	pop rdi
	/* Original CALL word remains transient. CAPTURED_CONTINUATION uses
	 * pre-CALL SP/post-CALL IP directly, with no fabricated push or pop.
	 */
	test r8, r8
	jz .Lnative_complete_\@
	jmp kd_mutex_entry_asm
.Lnative_complete_\@:
	/* Local queue/owner work already finished on the native source stack.
	 * This is its actual hardware CALL return, not a packet import.
	 */
	ret
	.size \symbol, .-\symbol
	.endm

	KD_MUTEX_SOURCE_ENTRY kd_mutex_lock_entry_asm, kd_mutex_prepare_lock_current
	KD_MUTEX_SOURCE_ENTRY kd_mutex_unlock_entry_asm, kd_mutex_prepare_unlock_current
	.section .note.GNU-stack, "", @progbits
