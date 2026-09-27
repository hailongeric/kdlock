// SPDX-License-Identifier: GPL-2.0
/* The caller lends its native stack only after this assembly has moved onto
 * the reserved shadow stack. Completed bodies may overwrite every old hook
 * frame; resume C below both stack positions, never through those frames. */
static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_mutex_resume_completed(struct kd_mutex_node *node)
{
	struct pt_regs full;
	bool native = READ_ONCE(node->native_resume);
	bool minimal = node->packet_state == KD_PACKET_COMPLETE;
	unsigned long sp = node->regs.sp, ip = node->regs.ip, bp = node->regs.bp;

	BUG_ON(node->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	BUG_ON(native ? minimal : !READ_ONCE(node->completed));
	BUG_ON(!minimal && node->packet_state != KD_PACKET_FULL);
	/* FULL must outlive node reuse; COMPLETE never reads absent GPRs. */
	if (!minimal)
		full = node->regs;
	WRITE_ONCE(this_cpu_ptr(&kd_mutex_shadows)->resume_node, NULL);
	kd_mutex_release_node(node);
	if (!native)
		this_cpu_inc(kd_mutex_jit_resume_count);
	preempt_enable();
	migrate_enable();
	if (native)
		jump_to_saved_regs_in_cs(&full);
	kd_mutex_task_put(current);
	if (!minimal)
		jump_to_saved_regs(&full);
	/* Both pointers describe the post-unlock boundary. Active caller values
	 * were spilled by its compiler, which reloads them after this return. */
	asm volatile("movq %%rax, %%rsp\n\t"
		     "movq %%rcx, %%rbp\n\t"
		     "pushq %%rdx\n\t"
#ifdef CONFIG_RETHUNK
		     "jmp __x86_return_thunk\n\t"
#else
		     "ret\n\t"
#endif
		     : : "a"(sp), "c"(bp), "d"(ip) : "memory");
	__builtin_unreachable();
}

static __always_inline int
kd_mutex_clobber_wait(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	int result;

	/* R12 holds only queue identity across the C slowpath. The enclosing
	 * compiler, not this trampoline, preserves its other live C values. */
	asm volatile(UNWIND_HINT(0, 0, UNWIND_HINT_TYPE_SAVE, 0)
		     "pushq %%rbp\n\t"
		     "movq %%rsp, %c[saved](%%rsi)\n\t"
		     "movq %%rsi, %%r12\n\t"
		     "movq %c[shadow](%%rsi), %%rsp\n\t"
		     "andq $-16, %%rsp\n\t"
		     "xorq %%rbp, %%rbp\n\t"
		     "callq %P[wait]\n\t"
		     "cmpl $3, %%eax\n\t"
		     "je 1f\n\t"
		     "cmpl $5, %%eax\n\t"
		     "je 1f\n\t"
		     "movq %c[saved](%%r12), %%rsp\n\t"
		     "popq %%rbp\n\t"
		     "jmp 2f\n\t"
		     "1: movq %c[saved](%%r12), %%rax\n\t"
		     "cmpq %c[sp](%%r12), %%rax\n\t"
		     "cmovaq %c[sp](%%r12), %%rax\n\t"
		     "andq $-16, %%rax\n\t"
		     "movq %%rax, %%rsp\n\t"
		     "movq %%r12, %%rdi\n\t"
		     "xorq %%rbp, %%rbp\n\t"
		     "callq %P[resume]\n\t"
		     "ud2\n\t"
		     "2:\n\t"
		     UNWIND_HINT(0, 0, UNWIND_HINT_TYPE_RESTORE, 0)
		     : "=a"(result), "+D"(lock), "+S"(node), ASM_CALL_CONSTRAINT
		     : [saved] "i"(offsetof(struct kd_mutex_node, rsp)),
		       [shadow] "i"(offsetof(struct kd_mutex_node, shadow_stack_ptr)),
		       [sp] "i"(offsetof(struct kd_mutex_node, regs.sp)),
		       [wait] "i"(kd_mutex_lock_slowpath),
		       [resume] "i"(kd_mutex_resume_completed)
		     : "rbx", "rcx", "rdx", "r8", "r9", "r10", "r11",
		       "r12", "r13", "r14", "r15", "cc", "memory");
	return result;
}
