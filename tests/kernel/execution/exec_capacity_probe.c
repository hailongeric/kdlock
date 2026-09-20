// SPDX-License-Identifier: GPL-2.0
/* Included by kd_exec.c only in SELFTEST builds. No deep-path allocation/print. */
static atomic_t kd_capacity_claimed = ATOMIC_INIT(0);
static struct {
	struct kd_exec_context before;
	struct kd_exec_frame live[KD_EXEC_MAX_NESTING];
	struct pt_regs packets[KD_EXEC_MAX_NESTING];
	unsigned long entry, outer;
	unsigned int depth, cpu, preempt;
	int task, owner;
	bool ready, attempted, rejected, unchanged, valid_before, valid_after,
		irq;
} kd_capacity;

void kd_exec_selftest_capacity_probe(const struct kd_exec_frame *frame)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	const struct kd_exec_frame *cursor;
	unsigned int i;

	if (!frame || frame->depth + 1 != KD_EXEC_MAX_NESTING ||
	    atomic_cmpxchg(&kd_capacity_claimed, 0, 1))
		return;
	kd_capacity.entry = frame->entry_ip;
	kd_capacity.outer = frame->outer_lock_addr;
	kd_capacity.depth = ctx->depth;
	kd_capacity.cpu = raw_smp_processor_id();
	kd_capacity.task = frame->logical_task ? frame->logical_task->pid : 0;
	kd_capacity.owner = current->pid;
	kd_capacity.preempt = preempt_count();
	kd_capacity.irq = irqs_disabled();
	kd_capacity.valid_before = ctx->depth == KD_EXEC_MAX_NESTING &&
				   kd_capacity.preempt &&
				   kd_exec_current_frame() == frame &&
				   kd_exec_context_validate(ctx);
	if (!kd_capacity.valid_before)
		goto out;
	/* One claimant owns this static snapshot; never put the whole context on the stack. */
	memcpy(&kd_capacity.before, ctx, sizeof(*ctx));
	/* External request frames are reached through top/parent, not the legacy
	 * array in before. Preserve the same full-state refusal oracle. */
	for (cursor = ctx->top, i = 0; cursor; cursor = cursor->parent, i++) {
		kd_capacity.live[i] = *cursor;
		kd_capacity.packets[i] = *kd_exec_frame_regs(cursor);
	}
	kd_capacity.attempted = true;
	kd_capacity.rejected = !kd_exec_frame_push(
		kd_exec_frame_regs(frame), frame->entry_ip, frame->outer_lock_addr, frame->held_lock_depth,
		frame->gsbase, frame->logical_task);
	kd_capacity.unchanged = !memcmp(&kd_capacity.before, ctx, sizeof(*ctx));
	for (cursor = ctx->top, i = 0; cursor && i < KD_EXEC_MAX_NESTING;
	     cursor = cursor->parent, i++)
		kd_capacity.unchanged &=
			!memcmp(&kd_capacity.live[i], cursor, sizeof(*cursor)) &&
			!memcmp(&kd_capacity.packets[i], kd_exec_frame_regs(cursor),
				sizeof(kd_capacity.packets[i]));
	kd_capacity.valid_after = kd_exec_current_frame() == frame &&
				  kd_exec_context_validate(ctx);
out:
	smp_store_release(&kd_capacity.ready, true);
}

void kd_exec_selftest_capacity_report(void)
{
	/* The caller has drained all frame users before reporting scalar evidence. */
	pr_info("kd_frame capacity: claimed=%u ready=%u attempted=%u rejected=%u unchanged=%u valid_before=%u valid_after=%u depth=%u cpu=%u task=%d owner=%d entry=%lx outer=%lx preempt=%u irq=%u snapshot=%zu\n",
		atomic_read(&kd_capacity_claimed),
		smp_load_acquire(&kd_capacity.ready), kd_capacity.attempted,
		kd_capacity.rejected, kd_capacity.unchanged,
		kd_capacity.valid_before, kd_capacity.valid_after,
		kd_capacity.depth, kd_capacity.cpu, kd_capacity.task,
		kd_capacity.owner, kd_capacity.entry, kd_capacity.outer,
		kd_capacity.preempt, kd_capacity.irq,
		sizeof(kd_capacity.before));
}
