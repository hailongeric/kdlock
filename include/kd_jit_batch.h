/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_JIT_BATCH_H
#define KD_JIT_BATCH_H

/* Versioned second wrapper entry. The ordinary two-word args ABI is unchanged.
 * Only the resident lock-side assembly runner may call this clobber-all entry.
 * Keep the six initial words synchronized with wrapper.S / spin_batch.S. */
#define KD_JIT_BATCH_OFFSET 16
#ifndef __ASSEMBLER__
struct kd_jit_batch_call {
	struct pt_regs *regs;
	unsigned long args[2];
	void *code;
	unsigned long lock;
	unsigned long unlock;
	unsigned long entry_sp;
	unsigned long dispatch_start;
	unsigned long wrapper_start;
};
void kd_spin_batch_enter(void *batch,
		struct kd_jit_batch_call *(*step)(void *batch));
#endif
#endif
