/* SPDX-License-Identifier: GPL-2.0 */
/* Port of TCLocks lib/combiner.c and komb_spin_lock_slowpath(), copyright
 * (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi. Keep their six-register/RSP
 * contract, with explicit entry/return code independent of C prologues.
 * CALL continuations, including unlock, stay on the borrowed native stack.
 */
#ifndef TC_CONTEXT_TEST
#include <linux/linkage.h>
#include <asm/nospec-branch.h>
#include <asm/ibt.h>
#include <asm/unwind_hints.h>
#else
#define SYM_FUNC_START(name) .globl name; .type name,@function; name:
#define SYM_FUNC_END(name) .size name,.-name
#define ENDBR
#define RET ret
#define UNWIND_HINT_EMPTY
#endif

.text
.macro tc_save
    pushq %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
.endm
.macro tc_restore
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
.endm

SYM_FUNC_START(komb_context_switch)
    ENDBR
    tc_save
    movq %rsp, (%rsi)
    movq (%rdi), %rsp
    UNWIND_HINT_EMPTY
    tc_restore
    RET
SYM_FUNC_END(komb_context_switch)

SYM_FUNC_START(komb_spin_lock_slowpath)
    ENDBR
    tc_save
    /* Helpers use an ordinary C ABI; preserve the lock across both calls. */
    movq %rdi, %r12
    call get_komb_rsp_ptr
    movq %rsp, (%rax)
    call get_shadow_stack_ptr
    movq (%rax), %rsp
    UNWIND_HINT_EMPTY
    movq %r12, %rdi
    call __komb_spin_lock_slowpath
    testl %eax, %eax
    jnz .Ltc_parent_return
    call get_shadow_stack_ptr
    movq %rsp, (%rax)
    call get_komb_rsp_ptr
    movq (%rax), %rsp
    UNWIND_HINT_EMPTY
    tc_restore
    RET
.Ltc_parent_return:
    /* Upstream out-of-order parent continuation; benchmark uses one lock. */
    call get_shadow_stack_ptr
    movq (%rax), %rsp
    UNWIND_HINT_EMPTY
    tc_restore
    RET
SYM_FUNC_END(komb_spin_lock_slowpath)

.section .note.GNU-stack,"",@progbits
