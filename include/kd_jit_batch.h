/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_JIT_BATCH_H
#define KD_JIT_BATCH_H

/* Versioned wrapper directory. The ordinary two-word args ABI is unchanged.
 * Both entries run inside one lock-side C loop, including mixed batches.
 * Offset 16 may destroy RBP; offset 32 preserves it. Keep field offsets
 * synchronized with wrapper.S. Neither entry is a normal C function. */
#define KD_JIT_BATCH_OFFSET 16
#define KD_JIT_CLOBBER_OFFSET 32
#define KD_JIT_ABI_OFFSET 45
#ifndef __ASSEMBLER__
struct kd_jit_batch_call {
	struct kd_regs *regs;
	unsigned long args[2];
	void *code;
	unsigned long lock;
	unsigned long unlock;
	unsigned long entry_sp;
	unsigned long dispatch_start;
	unsigned long wrapper_start;
	unsigned long entry_abi;
	unsigned int *packet_state;
	unsigned long complete;
};
#ifdef __KERNEL__
#include <linux/objtool.h>
#include <asm/asm.h>
#include <asm/nospec-branch.h>
/* The compiler saves live combiner values around the same clobber contract.
 * RBP/RSP obey normal call boundaries; the new wrapper only saves RBP. */
static __always_inline void kd_jit_clobber_call_v1(struct kd_jit_batch_call *call)
{
	struct kd_regs *regs = call->regs;
	unsigned long *args = call->args;
	void *entry = call->code;
	void *metadata = call;

	asm volatile(CALL_NOSPEC
		: "+D"(regs), "+S"(args), "+d"(metadata),
		  [thunk_target] "+a"(entry), ASM_CALL_CONSTRAINT
		:
		: "rbx", "rcx", "r8", "r9", "r10", "r11",
		  "r12", "r13", "r14", "r15", "cc", "memory");
}
/* The batch entry retains the legacy return convention: it discards the
 * wrapper frame without restoring physical RBP. Save only that frame pointer
 * here, so both layout-2 entries can share the resident C loop. The
 * compiler owns all other live combiner values, as in the v1 call above.
 * Keep CALL alignment and the caller's exact RSP; never infer its prologue.
 * SAVE/RESTORE describe the unchanged outer unwind state: this inner RBP pop
 * is not the enclosing C function's epilogue. They generate no instructions. */
static __always_inline void kd_jit_legacy_batch_call(struct kd_jit_batch_call *call)
{
	struct kd_regs *regs = call->regs;
	unsigned long *args = call->args;
	void *entry = call->code;
	void *metadata = call;

	asm volatile(UNWIND_HINT(0, 0, UNWIND_HINT_TYPE_SAVE, 0)
		     "pushq %%rbp\n\t"
		     "subq $8, %%rsp\n\t"
		     CALL_NOSPEC
		     "addq $8, %%rsp\n\t"
		     "popq %%rbp\n\t"
		     UNWIND_HINT(0, 0, UNWIND_HINT_TYPE_RESTORE, 0)
		: "+D"(regs), "+S"(args), "+d"(metadata),
		  [thunk_target] "+a"(entry), ASM_CALL_CONSTRAINT
		:
		: "rbx", "rcx", "r8", "r9", "r10", "r11",
		  "r12", "r13", "r14", "r15", "cc", "memory");
}
#endif
#endif
#endif
