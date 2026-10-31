/* SPDX-License-Identifier: GPL-2.0 */
#include <linux/linkage.h>
#include <linux/kd_api_provider.h>
#include <asm/nospec-branch.h>

/* RDI is the exact physical word, RSI/RDX/RCX the caller's SP/IP/BP;
 * R8 is its immutable provider. Tail dispatch adds no source-stack frame. */
.macro KD_API_BRIDGE name, op, native
SYM_FUNC_START(\name)
	testq %r8, %r8
	jz \native
	movq \op(%r8), %rax
	JMP_NOSPEC rax
SYM_FUNC_END(\name)
.endm
KD_API_BRIDGE kd_api_files_lock_clobber, KD_API_OP_SPIN_LOCK, _raw_spin_lock
KD_API_BRIDGE kd_api_files_unlock_clobber, KD_API_OP_SPIN_UNLOCK, _raw_spin_unlock
KD_API_BRIDGE kd_api_pipe_unlock_clobber, KD_API_OP_MUTEX_UNLOCK, mutex_unlock

SYM_FUNC_START(kd_api_pipe_lock_clobber)
	testq %r8, %r8
	jz mutex_lock
	testq %r9, %r9
	jz 1f
	movq KD_API_OP_MUTEX_LOCK(%r8), %rax
	JMP_NOSPEC rax
1:
	movq KD_API_OP_MUTEX_LOCAL_LOCK(%r8), %rax
	JMP_NOSPEC rax
SYM_FUNC_END(kd_api_pipe_lock_clobber)
