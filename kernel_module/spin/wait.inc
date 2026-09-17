// SPDX-License-Identifier: GPL-2.0
/* Physical waiters lend their original stack to the remote JIT. Publication
 * and polling must be one assembly region: even a compiler spill or a tracing
 * call after linking the node could race virtual PUSH/CALL writes. IRQs are
 * already masked and the ticket pins this CPU. Virtual waiters instead keep
 * their executor's independent C stack and service the owner/ACK protocol.
 */
static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_spin_resume_completed(struct kd_spin_node *node);

static __always_inline void
kd_spin_publish_wait(struct kd_spin_node *node, struct kd_spin_node *previous)
{
	asm volatile(
		/* x86 store ordering publishes the initialized packet before next. */
		"movq %[node], %c[next](%[previous])\n"
		"1: cmpb $0, %c[locked](%[node])\n"
		"je 2f\n"
		"pause\n"
		"jmp 1b\n"
		/* These loads acquire the release wakeup on x86. A head wake did
		 * not execute our body, so its C frames are still intact. */
		"2: cmpb $0, %c[native](%[node])\n"
		"jne 3f\n"
		"cmpb $0, %c[completed](%[node])\n"
		"je 4f\n"
		/* Discard every old hook/queue frame. Only start C again below both
		 * the saved physical RSP and the final logical RSP. */
		"3: movq %[node], %%rdi\n"
		"movq %c[rsp](%%rdi), %%rax\n"
		"cmpq %c[sp](%%rdi), %%rax\n"
		"cmovaq %c[sp](%%rdi), %%rax\n"
		"andq $-16, %%rax\n"
		"movq %%rax, %%rsp\n"
		"callq %P[resume]\n"
		"ud2\n"
		"4:\n"
		:
		: [node] "r"(node), [previous] "r"(previous),
		  [next] "i"(offsetof(struct kd_spin_node, next)),
		  [locked] "i"(offsetof(struct kd_spin_node, locked)),
		  [native] "i"(offsetof(struct kd_spin_node, native_resume)),
		  [completed] "i"(offsetof(struct kd_spin_node, completed)),
		  [rsp] "i"(offsetof(struct kd_spin_node, rsp)),
		  [sp] "i"(offsetof(struct kd_spin_node, regs.sp)),
		  [resume] "i"(kd_spin_resume_completed)
		: "rax", "rdi", "cc", "memory");
}
