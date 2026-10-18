// SPDX-License-Identifier: GPL-2.0
/* Register-packet restoration, continuation retirement and waiter return.
 * Included after nested request support; the entry ABI must keep its exact
 * stack-switch order and compiler attributes. */

/*
 * When the following function is called, the compiler in caller frame does
 * this sequence:
 *
 * push caller-saved-regs			(rdi, rsi, rdx, rcx, ...)
 * ...<prepare arguments>...
 * .- push eip+1				(eip + 1 == pop insn)
 * callq |
 * `- jmp kd_spin_lock
 * pop caller-saved-regs
 *
 * This means that the following function must in no way modify the the rsp
 * before it is written to the task_frame, otherwise the top of the stack
 * (rsp) would no longer point to the return address. To do this, emit a
 * call in assembly and pass the top of the stack as an argument so that
 * we can use the stack while preserving the semantics of the combiner.
 *
 * NOTE: One advantage of offloading the caller-saved register spill to the
 * compiler is that it only saves the caller-saved registers in use in the
 * caller frame. If we were to inline this whole logic in assembly, we wouldn't
 * know the registers in use and would have to save all possible caller-saved
 * registers.
 */
#define KD_RESTORE_REG_OPERANDS \
	[reg_ip] "i"(offsetof(struct kd_regs, ip)), \
	[reg_sp] "i"(offsetof(struct kd_regs, sp)), \
	[reg_bp] "i"(offsetof(struct kd_regs, bp)), \
	[reg_r15] "i"(offsetof(struct kd_regs, r15)), \
	[reg_r14] "i"(offsetof(struct kd_regs, r14)), \
	[reg_r13] "i"(offsetof(struct kd_regs, r13)), \
	[reg_r12] "i"(offsetof(struct kd_regs, r12)), \
	[reg_r11] "i"(offsetof(struct kd_regs, r11)), \
	[reg_bx] "i"(offsetof(struct kd_regs, bx)), \
	[reg_r10] "i"(offsetof(struct kd_regs, r10)), \
	[reg_r9] "i"(offsetof(struct kd_regs, r9)), \
	[reg_r8] "i"(offsetof(struct kd_regs, r8)), \
	[reg_ax] "i"(offsetof(struct kd_regs, ax)), \
	[reg_cx] "i"(offsetof(struct kd_regs, cx)), \
	[reg_dx] "i"(offsetof(struct kd_regs, dx)), \
	[reg_si] "i"(offsetof(struct kd_regs, si)), \
	[reg_di] "i"(offsetof(struct kd_regs, di))

/* Reached only through a checked instruction marker. All C cleanup and
 * scheduling ran before this call. Merge source arithmetic flags into the
 * waiter's control flags; installing the executor's IF/DF/AC would change
 * task context. After POPF, the return path must preserve flags through the
 * untouched original instruction. The verified guest's return thunks meet
 * that contract; use its configured mitigation instead of a bare return. */
static __attribute__((noipa, noreturn)) noinline notrace void
kd_jump_to_saved_regs_with_flags(struct kd_regs *regs)
{
	asm volatile("pushfq\n"
		     "popq %%rax\n"
		     "andq $%c[keep_flags], %%rax\n"
		     "movq %c[reg_flags](%%rdi), %%rcx\n"
		     "andq $%c[arithmetic_flags], %%rcx\n"
		     "orq %%rcx, %%rax\n"
		     "movq %c[reg_sp](%%rdi), %%rsp\n"
		     "pushq %c[reg_ip](%%rdi)\n"
		     "pushq %%rax\n"
		     "movq %c[reg_r15](%%rdi), %%r15\n"
		     "movq %c[reg_r14](%%rdi), %%r14\n"
		     "movq %c[reg_r13](%%rdi), %%r13\n"
		     "movq %c[reg_r12](%%rdi), %%r12\n"
		     "movq %c[reg_bp](%%rdi), %%rbp\n"
		     "movq %c[reg_bx](%%rdi), %%rbx\n"
		     "movq %c[reg_r11](%%rdi), %%r11\n"
		     "movq %c[reg_r10](%%rdi), %%r10\n"
		     "movq %c[reg_r9](%%rdi), %%r9\n"
		     "movq %c[reg_r8](%%rdi), %%r8\n"
		     "movq %c[reg_ax](%%rdi), %%rax\n"
		     "movq %c[reg_cx](%%rdi), %%rcx\n"
		     "movq %c[reg_dx](%%rdi), %%rdx\n"
		     "movq %c[reg_si](%%rdi), %%rsi\n"
		     "movq %c[reg_di](%%rdi), %%rdi\n"
		     "popfq\n"
#ifdef CONFIG_RETHUNK
		     "jmp __x86_return_thunk\n"
#else
		     "retq\n"
#endif
		     :
		     : KD_RESTORE_REG_OPERANDS,
		       [reg_flags] "i"(offsetof(struct kd_regs, flags)),
		       [arithmetic_flags] "i"(KD_REG_ARITHMETIC_FLAGS),
		       [keep_flags] "i"(~KD_REG_ARITHMETIC_FLAGS)
		     : "memory", "cc");
	__builtin_unreachable();
}

#pragma GCC push_options
#pragma GCC optimize("O3")
/* Ordinary CALL restoration has no live-flags contract. The in-CS form
 * separately routes a validated instruction marker to its flags-aware path. */
__attribute__((noipa)) noinline notrace void
jump_to_saved_regs(struct kd_regs *regs)
{
	asm volatile("movq %c[reg_r15](%%rdi), %%r15\n"
				 "movq %c[reg_r14](%%rdi), %%r14\n"
				 "movq %c[reg_r13](%%rdi), %%r13\n"
				 "movq %c[reg_r12](%%rdi), %%r12\n"
				 "movq %c[reg_bp](%%rdi), %%rbp\n"
				 "movq %c[reg_bx](%%rdi), %%rbx\n"
				 "movq %c[reg_r11](%%rdi), %%r11\n"
				 "movq %c[reg_r10](%%rdi), %%r10\n"
				 "movq %c[reg_r9](%%rdi), %%r9\n"
				 "movq %c[reg_r8](%%rdi), %%r8\n"
				 "movq %c[reg_ax](%%rdi), %%rax\n"
				 "movq %c[reg_cx](%%rdi), %%rcx\n"
				 "movq %c[reg_dx](%%rdi), %%rdx\n"
				 "movq %c[reg_si](%%rdi), %%rsi\n"
				 "movq %c[reg_sp](%%rdi), %%rsp\n"
				 "movq %c[reg_di](%%rdi), %%rdi\n"
				 "retq\n"
				 :
				 : KD_RESTORE_REG_OPERANDS
				 : "memory");
	__builtin_unreachable();
}

#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void
jump_to_saved_regs_in_cs(struct kd_regs *regs)
{
	if (regs->orig_ax == KD_REG_NATIVE_ESCAPE_TAG)
		kd_jump_to_saved_regs_with_flags(regs);
	asm volatile("movq %c[reg_r15](%%rdi), %%r15\n"
				 "movq %c[reg_r14](%%rdi), %%r14\n"
				 "movq %c[reg_r13](%%rdi), %%r13\n"
				 "movq %c[reg_r12](%%rdi), %%r12\n"
				 "movq %c[reg_bp](%%rdi), %%rbp\n"
				 "movq %c[reg_bx](%%rdi), %%rbx\n"
				 "movq %c[reg_r11](%%rdi), %%r11\n"
				 "movq %c[reg_r10](%%rdi), %%r10\n"
				 "movq %c[reg_r9](%%rdi), %%r9\n"
				 "movq %c[reg_r8](%%rdi), %%r8\n"
				 "movq %c[reg_ax](%%rdi), %%rax\n"
				 "movq %c[reg_cx](%%rdi), %%rcx\n"
				 "movq %c[reg_dx](%%rdi), %%rdx\n"
				 "movq %c[reg_si](%%rdi), %%rsi\n"
				 "movq %c[reg_sp](%%rdi), %%rsp\n"
				 "pushq %c[reg_ip](%%rdi)\n"
				 "movq %c[reg_di](%%rdi), %%rdi\n"
				 "retq\n"
				 :
				 : KD_RESTORE_REG_OPERANDS
				 : "memory");
	__builtin_unreachable();
}
#pragma GCC pop_options

/* Called after all packet reads/retirement, on the restored task stack.
 * The full-packet path already restored GPRs: this helper and the kernel
 * scheduling thunk preserve them while consuming exactly the original pin. */
static __attribute__((noipa, used, no_caller_saved_registers)) noinline notrace void
kd_spin_restore_unpin(void)
{
	preempt_enable();
}

/* No packet read may follow this sequence. The acquisition pin still fixes
 * the CPU; interrupt callers use native nodes, never continuation storage. */
#define KD_SPIN_RETIRE_ASM \
	"pushq %%rax\n" \
	"pushq %%rcx\n" \
	"movq %c[storage](%%rdi), %%rax\n" \
	"movb $1, %c[retired](%%rdi)\n" \
	"movl %c[top](%%rax), %%ecx\n" \
	"5: testl %%ecx, %%ecx\n" \
	"jz 6f\n" \
	"movl %%ecx, %%edi\n" \
	"imulq $%c[stride], %%rdi\n" \
	"cmpb $0, %c[last_retired](%%rax,%%rdi)\n" \
	"je 6f\n" \
	"decl %%ecx\n" \
	"jmp 5b\n" \
	"6: movl %%ecx, %c[top](%%rax)\n" \
	"popq %%rcx\n" \
	"popq %%rax\n"
#define KD_SPIN_RETIRE_OPERANDS \
	[storage] "i"(offsetof(struct kd_spin_continuation, storage)), \
	[retired] "i"(offsetof(struct kd_spin_continuation, retired)), \
	[top] "i"(offsetof(struct kd_spin_continuation_stack, top)), \
	[stride] "i"(sizeof(struct kd_spin_continuation)), \
	[last_retired] "i"((long)offsetof(struct kd_spin_continuation_stack, records) + \
		offsetof(struct kd_spin_continuation, retired) - sizeof(struct kd_spin_continuation))

static __attribute__((noipa, noreturn)) noinline notrace void
kd_spin_restore_request(struct kd_spin_continuation *execution,
						unsigned int mode)
{
	if (kd_entry_abi_spin_clobber(execution->frame.entry_abi) &&
		execution->frame.packet_state != KD_PACKET_FULL)
	{
		BUG_ON(mode == 2);
		asm volatile(
			"movq %c[sp](%%rdi), %%rsp\n"
			"pushq %c[ip](%%rdi)\n"
			"movq %c[bp](%%rdi), %%rbp\n"
			KD_SPIN_RETIRE_ASM
			"testl %%esi, %%esi\n"
			"jnz 7f\n"
			"callq %P[unpin]\n"
			"7:\n"
			"retq\n"
			:
			: "D"(execution), "S"(mode),
			  [unpin] "i"(kd_spin_restore_unpin),
			  [sp] "i"(offsetof(struct kd_spin_continuation, frame.regs.sp)),
			  [ip] "i"(offsetof(struct kd_spin_continuation, frame.regs.ip)),
			  [bp] "i"(offsetof(struct kd_spin_continuation, frame.regs.bp)),
			  KD_SPIN_RETIRE_OPERANDS
			: "memory", "cc");
		__builtin_unreachable();
	}
	asm volatile(
		"movq %c[sp](%%rdi), %%rsp\n"
		"testl %%edx, %%edx\n"
		"jz 1f\n"
		"pushq %c[ip](%%rdi)\n"
		"1: pushq %%rdx\n"
		"pushq %c[packet]+%c[reg_di](%%rdi)\n"
		"movq %c[packet]+%c[reg_r15](%%rdi), %%r15\n"
		"movq %c[packet]+%c[reg_r14](%%rdi), %%r14\n"
		"movq %c[packet]+%c[reg_r13](%%rdi), %%r13\n"
		"movq %c[packet]+%c[reg_r12](%%rdi), %%r12\n"
		"movq %c[packet]+%c[reg_bp](%%rdi), %%rbp\n"
		"movq %c[packet]+%c[reg_bx](%%rdi), %%rbx\n"
		"movq %c[packet]+%c[reg_r11](%%rdi), %%r11\n"
		"movq %c[packet]+%c[reg_r10](%%rdi), %%r10\n"
		"movq %c[packet]+%c[reg_r9](%%rdi), %%r9\n"
		"movq %c[packet]+%c[reg_r8](%%rdi), %%r8\n"
		"movq %c[packet]+%c[reg_ax](%%rdi), %%rax\n"
		"movq %c[packet]+%c[reg_cx](%%rdi), %%rcx\n"
		"movq %c[packet]+%c[reg_dx](%%rdi), %%rdx\n"
		"movq %c[packet]+%c[reg_si](%%rdi), %%rsi\n"
		/* Native execution retains this root until the final unlock barrier. */
		"cmpl $2, 8(%%rsp)\n"
		"je 3f\n"
		KD_SPIN_RETIRE_ASM
		"3:\n"
		"popq %%rdi\n"
		"cmpl $0, (%%rsp)\n"
		"je 7f\n"
		"cmpl $3, (%%rsp)\n"
		"je 7f\n"
		"addq $8, %%rsp\n"
		"jmp 8f\n"
		"7: addq $8, %%rsp\n"
		"callq %P[unpin]\n"
		"8:\n"
		"retq\n"
		:
		: "D"(execution), "d"(mode),
		  [unpin] "i"(kd_spin_restore_unpin),
		  [packet] "i"(offsetof(struct kd_spin_continuation, frame.regs)),
		  KD_RESTORE_REG_OPERANDS,
		  [sp] "i"(offsetof(struct kd_spin_continuation, frame.regs.sp)),
		  [ip] "i"(offsetof(struct kd_spin_continuation, frame.regs.ip)),
		  KD_SPIN_RETIRE_OPERANDS
		: "memory", "cc");
	__builtin_unreachable();
}

__attribute__((noipa)) noinline notrace static void
kd_spin_resume_waiter(struct kd_spin_node *node, unsigned int mode)
{
	struct kd_spin_continuation *execution = node->execution;
	struct kd_spin_ref ref = node->execution->frame.spin_origin;

	if (node->execution->result == KD_SPIN_RES_RETRY)
		KD_PR_INFO("spin JIT retry resume: node=%px cpu=%d ip=%lx\n",
				   node, node->cpuid, node->execution->frame.regs_ref->ip);
	if (mode == 2) {
		BUG_ON(kd_spin_entry_mark_native(&ref));
		*this_cpu_ptr(&kd_spin_native_root) = execution;
		if (!kd_exec_native_pending(current)) {
			BUG_ON(kd_spin_entry_borrow_wait(&ref));
			*this_cpu_ptr(&kd_spin_native_root) = NULL;
			mode = 3; /* In-CS IP, but all executors already retired. */
			BUG_ON(kd_spin_entry_end_pinned(&ref));
		}
	}
	else if (!mode)
		BUG_ON(kd_spin_entry_end_pinned(&ref));
	kd_spin_rw_retry(&execution->frame, mode);
	/* No node reads follow release; keep the pin through final packet loads. */
	barrier();
	this_cpu_dec(kd_spin_cpu.node_count);
	kd_spin_selftest_node_event(KD_NODE_RELEASE);
	kd_spin_restore_request(execution, mode);
	__builtin_unreachable();
}

/* Entered directly from the stack-free assembly interval. All old C frames
 * have been abandoned; this helper runs below the final virtual stack. */
static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_spin_resume_completed(struct kd_spin_node *node)
{
	unsigned int mode = (READ_ONCE(node->execution->result) == KD_SPIN_RES_NATIVE_READY) ? 2 : 0;

	if (mode)
		kd_spin_selftest_node_event(KD_NODE_NATIVE_RETURN);
	else
		kd_spin_selftest_node_event(KD_NODE_REMOTE_RETURN);
	kd_spin_diag_waiter_exit(node->execution->diag);
	kd_spin_resume_waiter(node, mode);
	__builtin_unreachable();
}
