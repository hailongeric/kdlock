/* SPDX-License-Identifier: GPL-2.0 */
/* Reached scalar execution is a continuation operation, never an admission
 * decision. The service dispatcher selects image-free capture explicitly. */
static bool kd_reached_frame_ready(struct kd_exec_frame *frame)
{
	struct kd_exec_continuation *cont = frame ? kd_exec_frame_continuation(frame) : NULL;

	return cont && kd_exec_cont_frame_valid(frame) && cont->service_ops &&
		cont->state == KD_CONT_BOUND && cont->executor == current &&
		kd_exec_current_frame() == frame && cont->root->packet_owner == cont &&
		cont->root->source_lease && cont->root->stack_lease &&
		!frame->completion_seen &&
		cont->service_call.api == KD_SERVICE_NONE &&
		!cont->origin_call.entry && !cont->origin_call.servicing &&
		(cont->origin_call.phase == KD_ORIGIN_CALL_IDLE ||
		 cont->origin_call.phase == KD_ORIGIN_CALL_CONSUMED) &&
		(cont->origin_memory.phase == KD_ORIGIN_MEMORY_IDLE ||
		 cont->origin_memory.phase == KD_ORIGIN_MEMORY_CONSUMED) &&
		!frame->native_request && !frame->remote_request &&
		(frame->control_call.phase == KD_CALL_NONE ||
		 frame->control_call.phase == KD_CALL_COMPLETE);
}

static int kd_reached_frame_fetch(void *context, unsigned long address,
	void *out, unsigned int size)
{
	struct kd_exec_frame *frame = context;
	struct kd_exec_continuation *cont;
	int ret;

	if (!kd_reached_frame_ready(context) || !size ||
	    size > KD_REACHED_MAX_BYTES || address > ~0UL - size)
		return -EINVAL;
	cont = kd_exec_frame_continuation(frame);
	if (cont->reached_active && cont->reached->initialized) {
		struct kd_reached_session *session = cont->reached;
		const struct kd_family_instruction *instruction;

		if (address == cont->packet->ip) {
			u8 observed[KD_REACHED_MAX_BYTES];

			session->fetch_instruction = NULL;
			instruction = kd_family_cache_candidate(&session->authority, address);
			/* An immutable cache record is a candidate, not source authority.
			 * Retain and compare its complete actual text before serving bytes. */
			if (instruction && !kd_source_pin_text_range(address, instruction->length) &&
			    !copy_from_kernel_nofault(observed, (void *)address, instruction->length) &&
			    !memcmp(observed, instruction->bytes, instruction->length))
				session->fetch_instruction = instruction;
		}
		instruction = session->fetch_instruction;
		if (instruction && address >= instruction->source_ip &&
		    address - instruction->source_ip < instruction->length &&
		    size <= instruction->length - (address - instruction->source_ip)) {
			memcpy(out, instruction->bytes + address - instruction->source_ip, size);
			return 0;
		}
	}
	ret = kd_source_pin_text_range(address, size);
	return ret ? ret : copy_from_kernel_nofault(out, (void *)address, size);
}

static int kd_reached_frame_read(void *context, unsigned long address,
	void *out, unsigned int size)
{
	if (!kd_reached_frame_ready(context) || address < TASK_SIZE_MAX ||
	    address > ~0UL - size)
		return -EFAULT;
	/* One source-width read, rather than a byte-copy lowering that could
	 * introduce tearing. Reached faults remain explicit runtime events. */
	pagefault_disable();
	switch (size) {
	case 1: __get_kernel_nofault(out, (void *)address, u8, fault); break;
	case 2: __get_kernel_nofault(out, (void *)address, u16, fault); break;
	case 4: __get_kernel_nofault(out, (void *)address, u32, fault); break;
	case 8: __get_kernel_nofault(out, (void *)address, u64, fault); break;
	default: pagefault_enable(); return -EINVAL;
	}
	pagefault_enable();
	return 0;
fault:
	pagefault_enable();
	return -EFAULT;
}

static int kd_reached_frame_write(void *context, unsigned long address,
	const void *in, unsigned int size)
{
	struct kd_exec_frame *frame = context;
	struct kd_exec_continuation *cont;
	unsigned long base;
	bool source_stack;

	if (!kd_reached_frame_ready(frame))
		return -EINVAL;
	cont = kd_exec_frame_continuation(frame);
	base = cont->root->stack_base;
	if (!base || base > ~0UL - THREAD_SIZE || !size || size > 8 ||
	    address < TASK_SIZE_MAX || address > ~0UL - size)
		return -EOPNOTSUPP;
	source_stack = address >= base && address <= base + THREAD_SIZE - size;
	/* The source caller owns ordinary RAM object lifetimes under its locks.
	 * Retained stack pages are stable. Other stores stay within one page;
	 * cross-page fault/fixup execution needs its own instruction contract. */
	if (!source_stack && offset_in_page(address) + size > PAGE_SIZE)
		return -EOPNOTSUPP;
	pagefault_disable();
	switch (size) {
	case 1: __put_kernel_nofault((void *)address, in, u8, fault); break;
	case 2: __put_kernel_nofault((void *)address, in, u16, fault); break;
	case 4: __put_kernel_nofault((void *)address, in, u32, fault); break;
	case 8: __put_kernel_nofault((void *)address, in, u64, fault); break;
	default: pagefault_enable(); return -EINVAL;
	}
	pagefault_enable();
	return 0;
fault:
	pagefault_enable();
	return -EFAULT;
}

static int kd_reached_frame_atomic(void *context, unsigned long address,
	unsigned int width, enum kd_reached_atomic_op operation, u64 input,
	u64 accumulator, unsigned long input_flags, u64 *old,
	unsigned long *output_flags)
{
	int result;

	if (!kd_reached_frame_ready(context) || address < TASK_SIZE_MAX ||
	    (width != 1 && width != 2 && width != 4 && width != 8) ||
	    address > ~0UL - width || offset_in_page(address) + width > PAGE_SIZE)
		return -EOPNOTSUPP;
	pagefault_disable();
	result = kd_reached_atomic_apply((void *)address, width, operation,
		input, accumulator, input_flags, old, output_flags);
	pagefault_enable();
	return result;
}

static const struct kd_reached_ops kd_reached_frame_ops = {
	.fetch = kd_reached_frame_fetch,
	.read = kd_reached_frame_read,
	.write = kd_reached_frame_write,
	.atomic = kd_reached_frame_atomic,
};

int kd_exe_reached_begin(struct kd_exec_frame *frame,
	struct kd_reached_state *state, u64 budget)
{
	struct kd_regs *regs;
	struct kd_exec_continuation *cont;
	int ret;

	if (!state || !budget || !kd_reached_frame_ready(frame) ||
	    frame->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	    (frame->packet_state == KD_PACKET_MINIMAL && frame->executed))
		return -EINVAL;
	regs = kd_exec_frame_regs(frame);
	cont = kd_exec_frame_continuation(frame);
	if (regs != cont->packet || (frame->packet_state == KD_PACKET_MINIMAL &&
	    (regs->ip != frame->entry_ip || regs->sp < cont->root->stack_base ||
	     cont->root->stack_base > ~0UL - THREAD_SIZE ||
	     regs->sp > cont->root->stack_base + THREAD_SIZE - sizeof(unsigned long))))
		return -EINVAL;
	ret = kd_reached_begin(state, regs,
		frame->packet_state, budget);
	if (ret)
		return ret;
	state->context = frame;
	state->ops = &kd_reached_frame_ops;
	state->owner_identity = cont->request->identity;
	state->owner_generation = cont->generation;
	frame->packet_state = KD_PACKET_FULL;
	return 0;
}

enum kd_reached_result kd_exe_reached_run(struct kd_exec_frame *frame,
	struct kd_reached_state *state, unsigned int instruction_limit)
{
	enum kd_reached_result result;
	u64 before;

	if (!kd_reached_frame_ready(frame) || !state ||
	    state->context != frame || state->ops != &kd_reached_frame_ops ||
	    state->regs != kd_exec_frame_regs(frame) ||
	    state->owner_identity != kd_exec_frame_continuation(frame)->request->identity ||
	    state->owner_generation != kd_exec_frame_continuation(frame)->generation ||
	    frame->packet_state != KD_PACKET_FULL || !instruction_limit ||
	    instruction_limit > 64)
		return KD_REACHED_PACKET;
	before = state->budget;
	result = kd_reached_run(state, instruction_limit);
	/* A final unsupported/source/memory event does not undo preceding
	 * committed instructions in this segment. Preserve their exact packet;
	 * the stop remains explicit and is never public lock completion. */
	if (state->budget < before) {
		frame->executed = true;
		kd_exec_frame_save_continuation(frame, state->regs);
	}
	return result;
}
