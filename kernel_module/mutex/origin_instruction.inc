// SPDX-License-Identifier: GPL-2.0
/* One original-task CPU instruction, with the queue and outer owner retained.
 * A prepared rwsem writer uses this same gate owner and retains its separate
 * admission reservation through final unlock ACK. Readers never enter here.
 * Included after kd_mutex_release_outer; no ordinary polling-loop change. */

__attribute__((__noinline__, __cold__, __no_instrument_function__))
static void kd_mutex_origin_cpuid_barrier(void)
{
	u32 ax, bx, cx, dx;

	/* The source CPUID executes on W. Its serialization must also cover the
	 * physical executor's prefix/suffix; release/acquire alone is not an
	 * instruction-stream serialization barrier. Leaf zero discards all data. */
	asm volatile("cpuid" : "=a"(ax), "=b"(bx), "=c"(cx), "=d"(dx)
		     : "0"(0U), "2"(0U) : "memory");
}

__attribute__((__cold__, __no_instrument_function__))
static noinline void kd_mutex_origin_instruction_waiter(struct kd_mutex_node *node)
{
	struct kd_origin_request *request = READ_ONCE(node->origin_request);
	struct kd_regs *regs;
	u32 ax, bx, cx, dx;
	int result = 0;

	BUG_ON(!request || request->node != node || READ_ONCE(request->returned));
	regs = request->regs;
	if (node->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	    node->task_struct_ptr != current || request->frame->logical_task != current ||
	    request->frame->packet_state != KD_PACKET_FULL ||
	    regs != kd_exec_frame_regs(request->frame) ||
	    request->frame->control_call.phase != KD_CALL_ORIGIN_INSTRUCTION ||
	    node->count_seq != request->count_sequence ||
	    node->counted_lock != node->lock || !request->sequence ||
	    node != this_cpu_ptr(&kd_mutex_nodes[node->slot]) ||
	    kd_read_kernel_gsbase() != node->gsbase ||
	    preempt_count() != 1 || irqs_disabled() || !current->migration_disabled ||
	    regs->ip != request->source_ip || regs->sp != request->source_sp)
		goto returned;
	request->origin_cpu = raw_smp_processor_id();
	request->origin_pid = current->pid;
	/* No source stack or arbitrary callee is involved. Only the exact scalar
	 * outputs change; source arithmetic flags remain in the existing packet. */
	switch (request->instruction) {
	case KD_ORIGIN_RDTSC:
		asm volatile("rdtsc" : "=a"(ax), "=d"(dx) : : "memory");
		regs->ax = ax;
		regs->dx = dx;
		break;
	case KD_ORIGIN_RDTSCP:
		asm volatile("rdtscp" : "=a"(ax), "=d"(dx), "=c"(cx) : : "memory");
		regs->ax = ax;
		regs->dx = dx;
		regs->cx = cx;
		break;
	case KD_ORIGIN_CPUID:
		asm volatile("cpuid" : "=a"(ax), "=b"(bx), "=c"(cx), "=d"(dx)
			     : "0"((u32)regs->ax), "2"((u32)regs->cx) : "memory");
		regs->ax = ax;
		regs->bx = bx;
		regs->cx = cx;
		regs->dx = dx;
		break;
	default:
		goto returned;
	}
	request->executed = true;
	result = 1;
returned:
	request->result = result;
	/* This is the last request/packet access. Rearm before ACK: C may publish
	 * another instruction or final completion immediately after acquiring it.
	 * W must not wait for a reset-to-zero ACK which can be missed between two
	 * services; it returns directly to the existing node notification poll. */
	WRITE_ONCE(node->locked, 1);
	smp_store_release(&request->returned, true);
}

__attribute__((__noinline__, __cold__, __no_instrument_function__))
int kd_mutex_origin_instruction(struct kd_exec_frame *frame,
				unsigned int instruction,
				unsigned long sequence)
{
	struct kd_origin_request request;
	struct kd_mutex_batch *batch;
	struct kd_mutex_node *node;
	struct kd_mutex *lock;
	struct kd_regs *regs;
	int origin_cpu;

	if (!frame || !frame->mutex_backend || !frame->complex_ready ||
	    frame->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	    frame->packet_state != KD_PACKET_FULL || frame->regs_borrowed ||
	    frame->parent || frame->depth || frame->request_frame ||
	    frame->resume_target || frame->remote_request || frame->native_request ||
	    kd_exec_frame_remote_pending(frame) || !list_empty(&frame->native_link) ||
	    frame->jit_lock_depth != 1 || frame->outer_lock_index ||
	    frame->jit_lock_kind[0] != KD_EXEC_LOCK_QUEUE_OWNER ||
	    frame->jit_lock_released[0] || frame->outer_unlock_seen ||
	    frame->completion_seen || !frame->executed ||
	    frame->mutex_mixed.transfer_requested || frame->mutex_mixed.transferred ||
	    frame->mutex_mixed.picked_up || !sequence ||
	    !frame->outer_unlock_hook || frame->outer_unlock_hook->released ||
	    frame->outer_unlock_hook->release != kd_mutex_release_outer ||
	    (frame->control_call.phase != KD_CALL_NONE && frame->control_call.phase != KD_CALL_COMPLETE) ||
	    !kd_exec_frame_can_borrow_locks(frame) || preempt_count() != 1 || irqs_disabled() ||
	    instruction < KD_ORIGIN_RDTSC || instruction > KD_ORIGIN_CPUID)
		return 0;
	batch = container_of(frame->outer_unlock_hook, struct kd_mutex_batch, outer);
	lock = batch->lock;
	node = batch->current_node;
	regs = kd_exec_frame_regs(frame);
	if (!lock || frame->outer_lock_addr != (unsigned long)lock ||
	    frame->jit_lock_node[0] != lock || !node || batch->current_retired ||
	    !kd_mutex_delegation_owned(lock, current) || !kd_origin_mutex_owned(lock, current) ||
	    kd_mutex_gate_read(lock) != KD_MUTEX_GATE_COMBINER ||
	    node->lock != lock || node->task_struct_ptr != frame->logical_task ||
	    node->task_struct_ptr == current || node->entry_abi != frame->entry_abi ||
	    node->counted_lock != lock || !node->count_seq ||
	    READ_ONCE(node->locked) != 1 || READ_ONCE(node->completed) ||
	    READ_ONCE(node->native_resume))
		return 0;
	origin_cpu = (node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1;
	if (origin_cpu < 0 || origin_cpu >= nr_cpu_ids ||
	    node->slot < 0 || node->slot >= KD_MUTEX_MAX_NODES ||
	    node != per_cpu_ptr(&kd_mutex_nodes[node->slot], origin_cpu))
		return -EINVAL;
	request = (struct kd_origin_request) {
		.frame = frame, .node = node, .regs = regs, .sequence = sequence,
		.count_sequence = node->count_seq, .source_ip = regs->ip, .source_sp = regs->sp,
		.instruction = instruction, .origin_cpu = -1, .origin_pid = -1,
	};
	frame->control_call.target = regs->ip;
	frame->control_call.stack = regs->sp;
	frame->control_call.return_ip = regs->ip + (instruction == KD_ORIGIN_RDTSCP ? 3 : 2);
	frame->control_call.phase = KD_CALL_ORIGIN_INSTRUCTION;
	if (instruction == KD_ORIGIN_CPUID)
		kd_mutex_origin_cpuid_barrier();
	WRITE_ONCE(node->origin_request, &request);
	WRITE_ONCE(node->native_resume, KD_MUTEX_RESUME_INSTRUCTION);
	smp_store_release(&node->locked, 0);
	while (!smp_load_acquire(&request.returned))
		cpu_relax();
	if (instruction == KD_ORIGIN_CPUID)
		kd_mutex_origin_cpuid_barrier();
	/* W has no remaining request/packet access. It retains its reservation
	 * and queue count and polls locked exactly as before this service. */
	BUG_ON(node->origin_request != &request || node->locked != 1 ||
	       node->native_resume != KD_MUTEX_RESUME_INSTRUCTION ||
	       node->count_seq != request.count_sequence || batch->current_node != node ||
	       batch->current_retired || request.regs != regs ||
	       regs->ip != request.source_ip || regs->sp != request.source_sp ||
	       frame->control_call.phase != KD_CALL_ORIGIN_INSTRUCTION ||
	       !kd_mutex_delegation_owned(lock, current) || !kd_origin_mutex_owned(lock, current));
	BUG_ON(request.executed != (request.result == 1) ||
	       (request.executed && (request.origin_cpu != origin_cpu ||
				     request.origin_pid != frame->logical_task->pid)));
	WRITE_ONCE(node->origin_request, NULL);
	WRITE_ONCE(node->native_resume, 0);
	frame->control_call.phase = KD_CALL_NONE;
	return request.result;
}
