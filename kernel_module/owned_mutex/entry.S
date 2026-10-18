/* SPDX-License-Identifier: GPL-2.0 */
#include <linux/linkage.h>
#include <asm/asm.h>
#include <asm/nospec-branch.h>
#include <asm/percpu.h>
#include <asm/unwind_hints.h>
#include "kd_owned_mutex_cabi.h"

	.text
/*
 * Ordinary C ABI: the uncontended path changes caller-saved registers only.
 * Fast and optimistic SELF acquisitions do no KD admission accounting. The
 * slow C gate returns before any nonvolatile register is captured, so its
 * compiler-owned frame cannot become part of the delegated continuation.
 */
SYM_FUNC_START(kd_owned_mutex_outer_lock_cabi_v2)
	/* A crowded episode bypasses failed write-prefixed owner CAS operations.
	 * Cold/small cohorts retain the original leaf CAS and local retry cadence.
	 * The hint is off the owner cacheline: cold reads must not downgrade the
	 * line before its CAS. The C gate rechecks a free owner. */
	cmpb $0, 88(%rdi)
	jne .Lowned_cabi_slow
	movq PER_CPU_VAR(current_task), %rdx
	xorl %eax, %eax
	lock cmpxchgq %rdx, (%rdi)
	jne .Lowned_cabi_slow
	movq %rdx, %rax
	RET
.Lowned_cabi_slow:
	/* Preserve L and the actual caller return PC; keep C CALL alignment. */
	pushq %rbp
	movq %rsp, %rbp
	subq $16, %rsp
	movq %rdi, (%rsp)
	movq 24(%rsp), %rsi
	call kd_owned_mutex_outer_cabi_gate
	testq %rax, %rax
	jz .Lowned_cabi_capture
	addq $16, %rsp
	popq %rbp
	RET
.Lowned_cabi_capture:
	movq (%rsp), %rdi
	addq $16, %rsp
	/*
	 * Keep the standard slow frame: saved caller BP at [RBP], hardware
	 * return PC at [RBP+8]. The record still begins 80 bytes below caller SP.
	 */
	subq $64, %rsp
	movq 72(%rsp), %rax
	movq %rax, KD_CABI_IP(%rsp)
	leaq 80(%rsp), %rax
	movq %rax, KD_CABI_SP(%rsp)
	movq (%rbp), %rax
	movq %rax, KD_CABI_BP(%rsp)
	/*
	 * These are capture copies, not spills needed by the returning SELF
	 * path. The C ABI preserves their physical values and this stack frame.
	 */
	UNWIND_HINT_SAVE
	movq %r15, KD_CABI_R15(%rsp)
	movq %r14, KD_CABI_R14(%rsp)
	movq %r13, KD_CABI_R13(%rsp)
	movq %r12, KD_CABI_R12(%rsp)
	movq %rbx, KD_CABI_BX(%rsp)
	movq %rsp, %rsi
	call kd_owned_mutex_outer_cabi_capture
	/*
	 * Only an unexecuted physical SELF grant returns through this frame.
	 * COMPLETE/FULL restore a separate recorded continuation directly.
	 */
	UNWIND_HINT_RESTORE
	addq $64, %rsp
	popq %rbp
	RET
SYM_FUNC_END(kd_owned_mutex_outer_lock_cabi_v2)

/*
 * Ordinary C ABI unlock: only the validated physical owner with no flags may
 * release here. Borrowed zero cookies and every slow/invalid case retain the
 * C checks and ACK route, with their original arguments and return address.
 */
SYM_FUNC_START(kd_owned_mutex_outer_unlock_cabi_v2)
	testq %rsi, %rsi
	jz .Lowned_cabi_unlock_slow
	movq PER_CPU_VAR(current_task), %rax
	cmpq %rax, %rsi
	jne .Lowned_cabi_unlock_slow
	xorl %edx, %edx
	lock cmpxchgq %rdx, (%rdi)
	jne .Lowned_cabi_unlock_slow
	RET
.Lowned_cabi_unlock_slow:
	jmp kd_owned_mutex_outer_cabi_unlock_slow
SYM_FUNC_END(kd_owned_mutex_outer_unlock_cabi_v2)

/*
 * Read all record words before switching stacks: the original caller's body
 * may have overwritten every native frame below its post-lock SP.
 */
SYM_FUNC_START(kd_owned_mutex_resume_cabi)
	/*
	 * Stop the abandoned chain while still describing the real old stack.
	 * A bare EMPTY has no CFA, so even the later RSP write is untrackable.
	 */
	UNWIND_HINT sp_reg=ORC_REG_SP sp_offset=8 type=UNWIND_HINT_TYPE_CALL end=1
	movq KD_CABI_IP(%rdi), %rdx
	movq KD_CABI_SP(%rdi), %rax
	movq KD_CABI_BP(%rdi), %rbp
	movq KD_CABI_R15(%rdi), %r15
	movq KD_CABI_R14(%rdi), %r14
	movq KD_CABI_R13(%rdi), %r13
	movq KD_CABI_R12(%rdi), %r12
	movq KD_CABI_BX(%rdi), %rbx
	movq %rax, %rsp
	/* The new post-unlock stack has no return slot until the next push. */
	UNWIND_HINT sp_reg=ORC_REG_SP sp_offset=0 type=UNWIND_HINT_TYPE_CALL end=1
	pushq %rdx
	/* The new stack now has an ordinary return word and caller-owned RBP. */
	UNWIND_HINT_FUNC
	RET
SYM_FUNC_END(kd_owned_mutex_resume_cabi)
