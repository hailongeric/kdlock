// SPDX-License-Identifier: GPL-2.0
/* Queue-owned prefetch hints. The producer prepares them before next/tail
 * publication; consumers stop using the node before wake/outer release.
 * Hints do not own the packet, replace logical SP, or grant JIT admission. */

static unsigned int kd_spin_prefetch_mode __read_mostly = 2;
module_param_named(spin_prefetch, kd_spin_prefetch_mode, uint, 0400);
MODULE_PARM_DESC(spin_prefetch,
	"Successor prefetch: 0=off, 1=consumer lookup, 2=producer hints (default)");

/* Called with initialized, exclusively owned request state. Physical callers
 * pass their inline packet directly; virtual children pass the retained parent
 * packet and always publish FULL. Thus MINIMAL hints use the aligned inline
 * packet, whose IP/SP/BP and hot frame sharing is a build-time invariant.
 * No register copy and no extra task/request reference is introduced. */
static void kd_spin_prepare_prefetch(struct kd_spin_node *node,
				     struct kd_regs *regs)
{
	struct kd_exec_frame *frame = &node->execution->frame;
	struct task_struct *task;
	unsigned long sp, base;

	if (READ_ONCE(kd_spin_prefetch_mode) != 2)
		return;
	node->prefetch_regs = regs;
	node->prefetch_sp = 0;
	node->prefetch_stack_lines = 0;
	node->prefetch_full = frame->packet_state == KD_PACKET_FULL;
	node->prefetch_complex = frame->complex_ready;
	task = frame->logical_task;
	if (!task || !regs)
		return;
	sp = regs->sp;
	base = (unsigned long)task_stack_page(task);
	/* Retain the translated CALL slot below SP and warm the caller's locals
	 * above it. Four upward lines also cover the hash caller's statistics;
	 * count only hint addresses within this retained task's stack. Prepare
	 * the bound here so the combiner needs no task/stack lookup per waiter.
	 * This checked address remains a hint, never a second executable SP. */
	if (sp >= base + sizeof(unsigned long) && sp - base < THREAD_SIZE) {
		node->prefetch_sp = sp;
		node->prefetch_stack_lines = min_t(unsigned long, 4,
			DIV_ROUND_UP(base + THREAD_SIZE - sp, L1_CACHE_BYTES));
	}
}

/* The original consumer lookup is retained for same-image comparisons.
 * Complex/borrowed packets use their true regs_ref, never node-zero RSP. */
static void kd_spin_prefetch_lookup(struct kd_spin_node *node)
{
	struct kd_exec_frame *frame = &node->execution->frame;
	struct kd_regs *regs = READ_ONCE(frame->regs_ref);
	struct task_struct *task;
	unsigned long sp, base;
	unsigned int offset;

	if (!regs)
		return;
	prefetchw(frame);
	prefetchw(&frame->regs_ref);
	if (frame->packet_state == KD_PACKET_FULL) {
		for (offset = 0; offset < sizeof(*regs); offset += L1_CACHE_BYTES)
			prefetchw((char *)regs + offset);
	} else {
		/* Inline MINIMAL already shares the hot frame line. The five
		 * virtual GPR slots remain active JIT backing even for clobber. */
		prefetchw(&regs->r15);
	}
	if (READ_ONCE(frame->complex_ready)) {
		prefetchw(&frame->jit_lock_addr[0]);
		prefetchw(&frame->jit_lock_kind[0]);
		prefetchw(&frame->jit_lock_node[0]);
	}
	task = READ_ONCE(frame->logical_task);
	if (!task)
		return;
	sp = READ_ONCE(regs->sp);
	base = (unsigned long)task_stack_page(task);
	if (sp >= base + sizeof(unsigned long) && sp - base < THREAD_SIZE) {
		prefetchw((void *)sp);
		prefetchw((void *)(sp - sizeof(unsigned long)));
	}
}

/* All prepared addresses are available from one queue node. Issue frame and
 * register hints before executing the current body, without loading the next
 * frame, task or packet just to discover where to prefetch. */
static void kd_spin_prefetch_request(struct kd_spin_node *node)
{
	struct kd_exec_frame *frame;
	struct kd_regs *regs;
	unsigned long sp;
	unsigned int offset, mode = READ_ONCE(kd_spin_prefetch_mode);

	if (!mode || !node || check_irq_node(node) || !node->execution)
		return;
	if (mode == 1) {
		kd_spin_prefetch_lookup(node);
		return;
	}
	frame = &node->execution->frame;
	regs = node->prefetch_regs;
	/* One line contains request identity/state and the continuation triple.
	 * The retained task/GS/parent/packet pointers share a second line. */
	prefetchw(frame);
	prefetchw(&frame->regs_ref);
	if (!regs)
		return;
	if (node->prefetch_full) {
		for (offset = 0; offset < sizeof(*regs); offset += L1_CACHE_BYTES)
			prefetchw((char *)regs + offset);
	} else {
		/* MINIMAL is inline; its triple was warmed with the frame above.
		 * This adjacent line holds all five virtual GPR spill slots, whose
		 * accesses were observed in the generated hash loop. */
		prefetchw(&regs->r15);
	}
	if (node->prefetch_complex) {
		prefetchw(&frame->jit_lock_addr[0]);
		prefetchw(&frame->jit_lock_kind[0]);
		prefetchw(&frame->jit_lock_node[0]);
	}
	sp = node->prefetch_sp;
	if (sp) {
		prefetchw((void *)(sp - sizeof(unsigned long)));
		for (offset = 0; offset < node->prefetch_stack_lines; offset++)
			prefetchw((void *)(sp + offset * L1_CACHE_BYTES));
	}
}
