// SPDX-License-Identifier: GPL-2.0
/* Physical waiters lend their original stack to the remote JIT. Switch to
 * the per-CPU 8 KiB shadow stack BEFORE publishing the node. Keep switching,
 * publication and polling in one assembly region so compiler spills cannot
 * touch the lent stack. IRQs are already masked and the ticket pins this CPU;
 * no scheduling or calls occur on the polling stack. Virtual waiters instead
 * keep their executor's independent C stack and service the owner/ACK protocol.
 */
static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_spin_resume_completed(struct kd_spin_node *node);

static __always_inline void
kd_spin_publish_wait(struct kd_spin_node *node, struct kd_spin_node *previous,
		     void *wait_stack_top)
{
	asm volatile(
		/* Only an unexecuted head handoff may use the old C continuation.
		 * Save that one RSP on the shadow stack, not in the shared packet. */
		"movq %%rsp, %%rax\n"
		"movq %[stack_top], %%rsp\n"
		"pushq %%rax\n"
		/* x86 store ordering publishes the initialized packet before next. */
		"movq %[node], %c[next](%[previous])\n"
		"1: cmpb $0, %c[locked](%[node])\n"
		"je 2f\n"
		"pause\n"
		"jmp 1b\n"
		/* These loads acquire the release wakeup on x86. A head wake did
		 * not execute our body, so its C frames are still intact. */
		"2: movq %c[execution](%[node]), %%rdi\n"
		"cmpl $%c[native_ready], %c[result](%%rdi)\n"
		"je 3f\n"
		"cmpb $0, %c[completed](%[node])\n"
		"je 4f\n"
		/* Discard every old hook/queue frame. Only start C again below both
		 * the saved physical RSP and the final logical RSP. */
		"3: movq %c[rsp](%[node]), %%rax\n"
		"movq %c[regs](%%rdi), %%rdi\n"
		"cmpq %c[sp](%%rdi), %%rax\n"
		"cmovaq %c[sp](%%rdi), %%rax\n"
		"movq %[node], %%rdi\n"
		"andq $-16, %%rax\n"
		"movq %%rax, %%rsp\n"
		"callq %P[resume]\n"
		"ud2\n"
		"4: popq %%rsp\n"
		:
		: [node] "r"(node), [previous] "r"(previous),
		  [stack_top] "r"(wait_stack_top),
		  [next] "i"(offsetof(struct kd_spin_node, next)),
		  [locked] "i"(offsetof(struct kd_spin_node, locked)),
		  [execution] "i"(offsetof(struct kd_spin_node, execution)),
		  [result] "i"(offsetof(struct kd_spin_continuation, result)),
		  [native_ready] "i"(KD_SPIN_RES_NATIVE_READY),
		  [completed] "i"(offsetof(struct kd_spin_node, completed)),
		  [rsp] "i"(offsetof(struct kd_spin_node, rsp)),
		  [regs] "i"(offsetof(struct kd_spin_continuation, frame.regs_ref)),
		  [sp] "i"(offsetof(struct pt_regs, sp)),
		  [resume] "i"(kd_spin_resume_completed)
		: "rax", "rdi", "cc", "memory");
}
