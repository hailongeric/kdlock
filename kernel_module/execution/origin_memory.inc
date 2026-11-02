/* SPDX-License-Identifier: GPL-2.0 */
/* The two decoders share a deliberately small x86-64 encoding contract:
 * GS, optional REX, FF /0 or /1, ordinary 64-bit memory addressing. */
struct kd_memory_operand {
	u8 base, index, shift, width, operation;
	s32 displacement;
};

#define KD_MEMORY_RIP 16U
#define KD_MEMORY_NO_REG 17U

static int kd_memory_operand_decode(const struct kd_origin_memory_site *site,
	struct kd_memory_operand *operand)
{
	const u8 *bytes = site->opcode;
	unsigned int cursor = 1, rex = 0, modrm, mod, rm, sib, disp = 0, i;

	if (site->reserved || site->length < 3 || site->length > 15 ||
	    bytes[0] != 0x65 || !site->ip || site->ip > ~0UL - site->length ||
	    site->next_ip != site->ip + site->length)
		return -EPROTO;
	if (bytes[cursor] >= 0x40 && bytes[cursor] <= 0x4f)
		rex = bytes[cursor++];
	if (cursor + 2 > site->length || bytes[cursor++] != 0xff)
		return -EPROTO;
	modrm = bytes[cursor++];
	mod = modrm >> 6;
	rm = modrm & 7;
	operand->operation = ((modrm >> 3) & 7) + 1;
	operand->width = rex & 8 ? 64 : 32;
	operand->base = KD_MEMORY_NO_REG;
	operand->index = KD_MEMORY_NO_REG;
	operand->shift = 0;
	operand->displacement = 0;
	if (mod == 3 || operand->operation > KD_ORIGIN_MEMORY_DEC ||
	    operand->operation != site->operation || operand->width != site->width)
		return -EPROTO;
	if (rm == 4) {
		if (cursor >= site->length)
			return -EPROTO;
		sib = bytes[cursor++];
		operand->shift = sib >> 6;
		if (((sib >> 3) & 7) != 4 || (rex & 2))
			operand->index = ((sib >> 3) & 7) | ((rex & 2) << 2);
		if (mod == 0 && (sib & 7) == 5)
			disp = 4;
		else
			operand->base = (sib & 7) | ((rex & 1) << 3);
	} else if (mod == 0 && rm == 5) {
		operand->base = KD_MEMORY_RIP;
		disp = 4;
	} else {
		operand->base = rm | ((rex & 1) << 3);
	}
	if (mod)
		disp = mod == 1 ? 1 : 4;
	if (cursor + disp != site->length)
		return -EPROTO;
	if (disp == 1)
		operand->displacement = (s8)bytes[cursor];
	else if (disp == 4)
		operand->displacement = (s32)((u32)bytes[cursor] |
			((u32)bytes[cursor + 1] << 8) | ((u32)bytes[cursor + 2] << 16) |
			((u32)bytes[cursor + 3] << 24));
	for (i = site->length; i < sizeof(site->opcode); ++i)
		if (bytes[i])
			return -EPROTO;
	return 0;
}

/* An exact unsupported source instruction may keep a refusal marker in an
 * otherwise usable image. It has no executable JIT successor and no effects. */
static bool kd_memory_refusal_site(const struct kd_origin_memory_site *site)
{
	unsigned int i;

	if (site->operation || site->width || site->reserved || site->continuation_offset ||
	    !site->length || site->length > 15 || !site->ip ||
	    site->ip > ~0UL - site->length || site->next_ip != site->ip + site->length)
		return false;
	for (i = site->length; i < sizeof(site->opcode); ++i)
		if (site->opcode[i])
			return false;
	return true;
}

static unsigned long kd_memory_register(const struct kd_regs *regs, unsigned int reg,
	unsigned long next_ip)
{
	switch (reg) {
	case 0: return regs->ax;
	case 1: return regs->cx;
	case 2: return regs->dx;
	case 3: return regs->bx;
	case 4: return regs->sp;
	case 5: return regs->bp;
	case 6: return regs->si;
	case 7: return regs->di;
	case 8: return regs->r8;
	case 9: return regs->r9;
	case 10: return regs->r10;
	case 11: return regs->r11;
	case 12: return regs->r12;
	case 13: return regs->r13;
	case 14: return regs->r14;
	case 15: return regs->r15;
	case KD_MEMORY_RIP: return next_ip;
	default: return 0;
	}
}

int kd_origin_memory_decode(const struct kd_origin_memory_site *site,
	const struct kd_regs *regs, unsigned long *effective_offset)
{
	struct kd_memory_operand operand;
	int result;

	if (!site)
		return -EINVAL;
	result = kd_memory_operand_decode(site, &operand);
	if (result || !effective_offset)
		return result;
	if (!regs)
		return -EINVAL;
	*effective_offset = kd_memory_register(regs, operand.base, site->next_ip) +
		(kd_memory_register(regs, operand.index, site->next_ip) << operand.shift) +
		(long)operand.displacement;
	return 0;
}

const struct kd_origin_memory_site *kd_image_memory_sites(
	const struct kd_jit_image *image, unsigned int *count)
{
	const struct kd_origin_memory_footer *footer;
	const unsigned char *code;

	if (!image || !image->code || !(image->requirements & KD_IMAGE_REQUIRE_ORIGIN_MEMORY) ||
	    image->length < KD_IMAGE_SERVICE_HEADER_SIZE + sizeof(*footer))
		return NULL;
	code = image->code;
	footer = (const void *)(code + image->length - sizeof(*footer));
	if (memcmp(footer->magic, "KDOM0001", 8) || !footer->count ||
	    footer->count > KD_ORIGIN_MEMORY_MAX || footer->offset < KD_IMAGE_SERVICE_HEADER_SIZE ||
	    (unsigned long)footer->offset + footer->count * sizeof(struct kd_origin_memory_site) !=
		image->length - sizeof(*footer))
		return NULL;
	*count = footer->count;
	return (const void *)(code + footer->offset);
}

int kd_image_validate_memory_sites(const struct kd_jit_image *image)
{
	const struct kd_origin_memory_site *sites;
	unsigned int count, i, j;
	int result;
	u8 bytes[16];

	if (!(image->requirements & KD_IMAGE_REQUIRE_ORIGIN_MEMORY))
		return 0;
	sites = kd_image_memory_sites(image, &count);
	if (!sites || image->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1)
		return -EPROTO;
	for (i = 0; i < count; ++i) {
		if (!kd_memory_refusal_site(&sites[i]) &&
		    (kd_origin_memory_decode(&sites[i], NULL, NULL) ||
		    sites[i].continuation_offset < KD_IMAGE_SERVICE_HEADER_SIZE ||
		    sites[i].continuation_offset >= (unsigned long)((const u8 *)sites -
			(const u8 *)image->code)))
			return -EPROTO;
		for (j = 0; j < i; ++j)
			if (sites[j].ip == sites[i].ip)
				return -EPROTO;
		result = kd_source_pin_root(sites[i].ip);
		if (!result)
			result = kd_source_pin_root(sites[i].next_ip - 1);
		if (!result)
			result = kd_source_pin_root(sites[i].next_ip);
		if (result)
			return result;
		if (copy_from_kernel_nofault(bytes, (void *)sites[i].ip, sites[i].length) ||
		    memcmp(bytes, sites[i].opcode, sites[i].length))
			return -EILSEQ;
	}
	return 0;
}

int kd_exec_cont_memory_prepare(struct kd_exec_frame *frame)
{
	struct kd_exec_continuation *cont = frame ? kd_exec_frame_continuation(frame) : NULL;
	struct kd_origin_memory *operation;
	const struct kd_origin_memory_site *sites, *site = NULL;
	unsigned long offset;
	unsigned int count, i;
	u8 bytes[16];

	if (!kd_exec_cont_valid(cont) || !cont->service_ops ||
	    cont->state != KD_CONT_BOUND || cont->executor != current ||
	    cont->root->packet_owner != cont || frame->packet_state != KD_PACKET_FULL ||
	    !frame->executed || !frame->image || !frame->image->immutable ||
	    !(frame->image->requirements & KD_IMAGE_REQUIRE_ORIGIN_MEMORY) ||
	    cont->service_call.api != KD_SERVICE_NONE || cont->origin_call.entry ||
	    cont->origin_call.servicing || (cont->origin_call.phase != KD_ORIGIN_CALL_IDLE &&
		cont->origin_call.phase != KD_ORIGIN_CALL_CONSUMED))
		return -EINVAL;
	operation = &cont->origin_memory;
	if ((operation->phase != KD_ORIGIN_MEMORY_IDLE &&
	     operation->phase != KD_ORIGIN_MEMORY_CONSUMED) || operation->sequence == U64_MAX ||
	    !(cont->packet->flags & 2))
		return -EINVAL;
	sites = kd_image_memory_sites(frame->image, &count);
	if (!sites)
		return -EPROTO;
	for (i = 0; i < count; ++i)
		if (sites[i].ip == cont->packet->ip) {
			if (site)
				return -EPROTO;
			site = &sites[i];
		}
	if (!site || copy_from_kernel_nofault(bytes, (void *)site->ip, site->length) ||
	    memcmp(bytes, site->opcode, site->length) ||
	    cont->packet->sp < cont->stack_base + 512 ||
	    cont->packet->sp > cont->stack_base + THREAD_SIZE)
		return -EPROTO;
	if (kd_memory_refusal_site(site))
		return -EOPNOTSUPP;
	if (kd_origin_memory_decode(site, cont->packet, &offset))
		return -EPROTO;
	operation->packet = cont->packet;
	operation->image = frame->image;
	operation->site = site;
	operation->origin = cont->request->logical_origin;
	operation->executor = current;
	operation->identity = cont->request->identity;
	operation->generation = cont->generation;
	++operation->sequence;
	operation->gsbase = frame->gsbase;
	operation->effective_offset = offset;
	operation->source_sp = cont->packet->sp;
	operation->input_flags = cont->packet->flags;
	operation->result_flags = 0;
	operation->result = 0;
	local_save_flags(operation->executor_irq_flags);
	WRITE_ONCE(operation->phase, KD_ORIGIN_MEMORY_PREPARED);
	return 0;
}

int kd_exec_cont_memory_complete(struct kd_exec_continuation *cont, u64 sequence)
{
	struct kd_origin_memory *operation;
	bool complete;

	if (!kd_exec_cont_valid(cont) || !cont->service_ops ||
	    cont->state != KD_CONT_BOUND || cont->executor != current ||
	    kd_exec_current_frame() != &cont->frame || cont->root->packet_owner != cont ||
	    !cont->service_ops->validate(cont->service_scope, cont))
		return -EINVAL;
	operation = &cont->origin_memory;
	if (smp_load_acquire(&operation->phase) != KD_ORIGIN_MEMORY_DONE ||
	    operation->sequence != sequence || operation->result ||
	    operation->origin != cont->request->logical_origin ||
	    operation->executor != current || operation->identity != cont->request->identity ||
	    operation->generation != cont->generation || operation->packet != cont->packet ||
	    operation->image != cont->frame.image || !operation->site ||
	    cont->packet->sp != operation->source_sp ||
	    cont->packet->ip != operation->site->ip || !(operation->result_flags & 2) ||
	    ((operation->result_flags ^ operation->input_flags) & 1))
		return -EPROTO;
	cont->packet->flags = (operation->input_flags & ~KD_REG_ARITHMETIC_FLAGS) |
		(operation->result_flags & KD_REG_ARITHMETIC_FLAGS);
	cont->packet->ip = operation->site->next_ip;
	if (cont->service_ops->outer_released(cont->service_scope)) {
		cont->frame.outer_unlock_seen = true;
		cont->frame.jit_lock_released[0] = true;
	}
	complete = cont->frame.outer_unlock_seen &&
		cont->service_ops->all_released(cont->service_scope);
	/* An instruction has no CALL word. Final restoration must transfer this
	 * exact next-IP/SP and arithmetic flags through the provider's v2 baton. */
	cont->packet->orig_ax = complete ? KD_REG_ORIGIN_SUFFIX_TAG : KD_REG_SERVICE_REENTRY_TAG;
	cont->frame.control_call.phase = KD_CALL_NONE;
	cont->frame.continuation_ip = cont->packet->ip;
	cont->frame.continuation_sp = cont->packet->sp;
	smp_store_release(&operation->phase, KD_ORIGIN_MEMORY_CONSUMED);
	return complete ? KD_EXE_RUN_TO_UNLOCK : 0;
}

void kd_origin_memory_apply(struct kd_origin_memory *operation)
{
	unsigned long flags, input;
	unsigned long offset = operation->effective_offset;

	asm volatile("pushfq; popq %0" : "=r"(flags) : : "memory");
	input = (flags & ~KD_REG_ARITHMETIC_FLAGS) |
		(operation->input_flags & KD_REG_ARITHMETIC_FLAGS);
#define KD_MEMORY_APPLY(instruction) \
	asm volatile("pushq %[input]; popfq; " instruction " %%gs:(%[offset]); " \
		"pushfq; popq %[output]" : [output] "=r"(flags) \
		: [input] "r"(input), [offset] "r"(offset) : "cc", "memory")
	if (operation->site->operation == KD_ORIGIN_MEMORY_INC) {
		if (operation->site->width == 32)
			KD_MEMORY_APPLY("incl");
		else
			KD_MEMORY_APPLY("incq");
	} else {
		if (operation->site->width == 32)
			KD_MEMORY_APPLY("decl");
		else
			KD_MEMORY_APPLY("decq");
	}
#undef KD_MEMORY_APPLY
	operation->result_flags = flags;
}
