/* SPDX-License-Identifier: GPL-2.0-only */
/* Ordinary source-operation entries. No source is lent before the prepared
 * task-owned auxiliary switch. The four scalars are original declared inputs,
 * not a packet copy or native waiter-body execution engine. Admission performs
 * no allocation. A NULL descriptor reports a completed native operation; a
 * prepared descriptor selects the auxiliary route before any source lending.
 * Its transient source-stack frames are fully unwound before the switch.
 */
#include "kd_mutex_api.h"

	.intel_syntax noprefix
	.text

	.macro KD_MUTEX_SOURCE_ENTRY symbol, prepare, returns_int=0
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
	.if \returns_int
	/* Cache the second return word before restoring the source DX input. */
	mov r9, rdx
	.endif
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
	.if \returns_int
	mov eax, r9d
	.endif
	ret
	.size \symbol, .-\symbol
	.endm

	KD_MUTEX_SOURCE_ENTRY kd_mutex_lock_entry_asm, kd_mutex_prepare_lock_current
	/* Both native unlock routes finish on this stack. There is no capture
	 * descriptor to carry the four source scalars into an auxiliary entry.
	 * Preserve the incoming stack alignment contract for the C call.
	 */
	.p2align 4
	.globl kd_mutex_unlock_entry_asm
	.type kd_mutex_unlock_entry_asm, @function
kd_mutex_unlock_entry_asm:
	endbr64
	push rbp
	mov rbp, rsp
	and rsp, -16
	call kd_mutex_prepare_unlock_current
	leave
	ret
	.size kd_mutex_unlock_entry_asm, .-kd_mutex_unlock_entry_asm

	KD_MUTEX_SOURCE_ENTRY kd_spin_lock_entry_asm, kd_spin_prepare_lock_current
	KD_MUTEX_SOURCE_ENTRY kd_spin_unlock_entry_asm, kd_spin_prepare_unlock_current
	KD_MUTEX_SOURCE_ENTRY kd_rwsem_down_read_entry_asm, kd_rwsem_prepare_down_read_current
	KD_MUTEX_SOURCE_ENTRY kd_rwsem_up_read_entry_asm, kd_rwsem_prepare_up_read_current
	KD_MUTEX_SOURCE_ENTRY kd_rwsem_down_write_entry_asm, kd_rwsem_prepare_down_write_current
	KD_MUTEX_SOURCE_ENTRY kd_rwsem_down_write_killable_entry_asm, kd_rwsem_prepare_down_write_killable_current, 1
	KD_MUTEX_SOURCE_ENTRY kd_rwsem_up_write_entry_asm, kd_rwsem_prepare_up_write_current
	KD_MUTEX_SOURCE_ENTRY kd_rwsem_downgrade_write_entry_asm, kd_rwsem_prepare_downgrade_write_current
	KD_MUTEX_SOURCE_ENTRY kd_linux_rwsem_down_read_entry_asm, kd_linux_rwsem_prepare_down_read_current
	KD_MUTEX_SOURCE_ENTRY kd_linux_rwsem_up_read_entry_asm, kd_linux_rwsem_prepare_up_read_current
	KD_MUTEX_SOURCE_ENTRY kd_linux_rwsem_down_write_entry_asm, kd_linux_rwsem_prepare_down_write_current
	KD_MUTEX_SOURCE_ENTRY kd_linux_rwsem_down_write_killable_entry_asm, kd_linux_rwsem_prepare_down_write_killable_current, 1
	KD_MUTEX_SOURCE_ENTRY kd_linux_rwsem_up_write_entry_asm, kd_linux_rwsem_prepare_up_write_current
	KD_MUTEX_SOURCE_ENTRY kd_linux_rwsem_downgrade_write_entry_asm, kd_linux_rwsem_prepare_downgrade_write_current
	KD_MUTEX_SOURCE_ENTRY kd_linux_rwsem_is_locked_entry_asm, kd_linux_rwsem_prepare_is_locked_current, 1
	KD_MUTEX_SOURCE_ENTRY kd_linux_rwsem_is_write_locked_entry_asm, kd_linux_rwsem_prepare_is_write_locked_current, 1
	KD_MUTEX_SOURCE_ENTRY kd_rwlock_read_lock_entry_asm, kd_rwlock_prepare_read_lock_current
	KD_MUTEX_SOURCE_ENTRY kd_rwlock_read_unlock_entry_asm, kd_rwlock_prepare_read_unlock_current
	KD_MUTEX_SOURCE_ENTRY kd_rwlock_write_lock_entry_asm, kd_rwlock_prepare_write_lock_current
	KD_MUTEX_SOURCE_ENTRY kd_rwlock_write_unlock_entry_asm, kd_rwlock_prepare_write_unlock_current
	.section .note.GNU-stack, "", @progbits
