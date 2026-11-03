/* SPDX-License-Identifier: GPL-2.0 */
/* The two decoders share exact GS scalar opcodes and 64-bit addressing. */
struct kd_memory_operand {
	u8 base, index, shift, width, operation, destination;
	s32 displacement;
	u32 immediate;
};

#define KD_MEMORY_RIP 16U
#define KD_MEMORY_NO_REG 17U

static int kd_memory_operand_decode(const struct kd_origin_memory_site *site,
	struct kd_memory_operand *operand)
{
	const u8 *bytes = site->opcode;
	unsigned int cursor = 0, rex = 0, modrm, mod, rm, sib, disp = 0, i;
	unsigned int opcode, extension, immediate = 0;
	bool gs = false, word = false;

	if ((site->flags & ~KD_ORIGIN_MEMORY_READ) || site->length < 3 || site->length > 15 ||
	    !site->ip || site->ip > ~0UL - site->length ||
	    site->next_ip != site->ip + site->length)
		return -EPROTO;
	while (cursor < site->length && (bytes[cursor] == 0x65 || bytes[cursor] == 0x66)) {
		if (bytes[cursor] == 0x65) {
			if (gs)
				return -EPROTO;
			gs = true;
		} else {
			if (word)
				return -EPROTO;
			word = true;
		}
		++cursor;
	}
	if (cursor < site->length && bytes[cursor] >= 0x40 && bytes[cursor] <= 0x4f)
		rex = bytes[cursor++];
	if (!gs || cursor + 2 > site->length)
		return -EPROTO;
	opcode = bytes[cursor++];
	modrm = bytes[cursor++];
	mod = modrm >> 6;
	rm = modrm & 7;
	extension = (modrm >> 3) & 7;
	operand->width = rex & 8 ? 64 : word ? 16 : 32;
	operand->destination = KD_MEMORY_NO_REG;
	operand->immediate = 0;
	if (opcode == 0xff && extension <= 1 && !word) {
		operand->operation = extension + 1;
	} else if (opcode == 0x8b && !word) {
		operand->operation = KD_ORIGIN_MEMORY_LOAD;
		operand->destination = extension | ((rex & 4) << 1);
		if (operand->destination == 4)
			return -EPROTO;
	} else if (opcode == 0xf7 && extension == 0 && operand->width != 64) {
		operand->operation = KD_ORIGIN_MEMORY_TEST;
		immediate = operand->width / 8;
	} else {
		return -EPROTO;
	}
	operand->base = KD_MEMORY_NO_REG;
	operand->index = KD_MEMORY_NO_REG;
	operand->shift = 0;
	operand->displacement = 0;
	if (mod == 3 || operand->operation != site->operation || operand->width != site->width ||
	    !!(site->flags & KD_ORIGIN_MEMORY_READ) !=
		(operand->operation >= KD_ORIGIN_MEMORY_LOAD))
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
	if (cursor + disp + immediate != site->length)
		return -EPROTO;
	if (disp == 1)
		operand->displacement = (s8)bytes[cursor];
	else if (disp == 4)
		operand->displacement = (s32)((u32)bytes[cursor] |
			((u32)bytes[cursor + 1] << 8) | ((u32)bytes[cursor + 2] << 16) |
			((u32)bytes[cursor + 3] << 24));
	cursor += disp;
	for (i = 0; i < immediate; ++i)
		operand->immediate |= (u32)bytes[cursor + i] << (8 * i);
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

	if (site->operation || site->width || (site->flags & ~KD_ORIGIN_MEMORY_READ) ||
	    site->continuation_offset ||
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

static u8 kd_memory_reached_byte(struct kd_origin_memory_site *site,
	kd_origin_memory_reader reader, void *context, int *error)
{
	u8 value = 0;

	if (*error)
		return 0;
	if (site->length == 15 || site->ip > ~0UL - site->length - 1) {
		*error = -EOPNOTSUPP;
		return 0;
	}
	*error = reader(context, site->ip + site->length, &value, 1);
	if (!*error)
		site->opcode[site->length++] = value;
	return value;
}

/* Decode only the reached GS instruction. The final strict decoder remains
 * the authority for the supported addressing and operation contract. No byte
 * from a successor is needed to recognize a complete supported instruction. */
int kd_origin_memory_reached_decode(struct kd_origin_memory_site *site,
	unsigned long ip, kd_origin_memory_reader reader, void *context)
{
	struct kd_memory_operand decoded;
	unsigned int rex = 0, opcode, modrm, mod, rm, extension, sib = 0;
	unsigned int displacement = 0, immediate = 0, i;
	bool gs = false, word = false;
	int error = 0;
	u8 next;

	if (!site || !ip || !reader)
		return -EINVAL;
	*site = (struct kd_origin_memory_site){ .ip = ip };
	next = kd_memory_reached_byte(site, reader, context, &error);
	while (!error && (next == 0x65 || next == 0x66)) {
		if (next == 0x65) {
			if (gs)
				return -EOPNOTSUPP;
			gs = true;
		} else {
			if (word)
				return -EOPNOTSUPP;
			word = true;
		}
		next = kd_memory_reached_byte(site, reader, context, &error);
	}
	if (error)
		return error;
	if (!gs)
		return -EOPNOTSUPP;
	if (next >= 0x40 && next <= 0x4f) {
		rex = next;
		next = kd_memory_reached_byte(site, reader, context, &error);
	}
	opcode = next;
	if (error)
		return error;
	if (opcode != 0xff && opcode != 0x8b && opcode != 0xf7)
		return -EOPNOTSUPP;
	modrm = kd_memory_reached_byte(site, reader, context, &error);
	if (error)
		return error;
	mod = modrm >> 6;
	rm = modrm & 7;
	extension = (modrm >> 3) & 7;
	site->width = rex & 8 ? 64 : word ? 16 : 32;
	if (mod == 3)
		return -EOPNOTSUPP;
	if (opcode == 0xff && extension <= 1 && !word) {
		site->operation = extension + 1;
	} else if (opcode == 0x8b && !word) {
		site->operation = KD_ORIGIN_MEMORY_LOAD;
		site->flags = KD_ORIGIN_MEMORY_READ;
	} else if (opcode == 0xf7 && extension == 0 && site->width != 64) {
		site->operation = KD_ORIGIN_MEMORY_TEST;
		site->flags = KD_ORIGIN_MEMORY_READ;
		immediate = site->width / 8;
	} else {
		return -EOPNOTSUPP;
	}
	if (rm == 4) {
		sib = kd_memory_reached_byte(site, reader, context, &error);
		if (!mod && (sib & 7) == 5)
			displacement = 4;
	} else if (!mod && rm == 5) {
		displacement = 4;
	}
	if (mod)
		displacement = mod == 1 ? 1 : 4;
	for (i = 0; i < displacement + immediate && !error; ++i)
		kd_memory_reached_byte(site, reader, context, &error);
	if (error)
		return error;
	site->next_ip = ip + site->length;
	return kd_memory_operand_decode(site, &decoded) ? -EOPNOTSUPP : 0;
}

const struct kd_origin_memory_site *kd_image_memory_sites(
	const struct kd_jit_image *image, unsigned int *count)
{
	const struct kd_origin_memory_footer *footer;
	const struct kd_origin_memory_read_footer *read_footer;
	const unsigned char *code;
	unsigned long trailer;
	unsigned int offset, entries;

	if (!image || !image->code || !(image->requirements & KD_IMAGE_REQUIRE_ORIGIN_MEMORY) ||
	    image->length < KD_IMAGE_SERVICE_HEADER_SIZE + sizeof(*footer))
		return NULL;
	code = image->code;
	if (image->requirements & KD_IMAGE_REQUIRE_ORIGIN_CONTEXT_READ) {
		if (image->length < KD_IMAGE_SERVICE_HEADER_SIZE + sizeof(*read_footer))
			return NULL;
		read_footer = (const void *)(code + image->length - sizeof(*read_footer));
		if (memcmp(read_footer->magic, "KDOM0002", 8) ||
		    read_footer->preempt_symbol != (unsigned long)&__preempt_count)
			return NULL;
		offset = read_footer->offset;
		entries = read_footer->count;
		trailer = sizeof(*read_footer);
	} else {
		footer = (const void *)(code + image->length - sizeof(*footer));
		if (memcmp(footer->magic, "KDOM0001", 8))
			return NULL;
		offset = footer->offset;
		entries = footer->count;
		trailer = sizeof(*footer);
	}
	if (!entries || entries > KD_ORIGIN_MEMORY_MAX || offset < KD_IMAGE_SERVICE_HEADER_SIZE ||
	    (unsigned long)offset + entries * sizeof(struct kd_origin_memory_site) !=
		image->length - trailer)
		return NULL;
	*count = entries;
	return (const void *)(code + offset);
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
		if ((sites[i].flags & KD_ORIGIN_MEMORY_READ) &&
		    !(image->requirements & KD_IMAGE_REQUIRE_ORIGIN_CONTEXT_READ))
			return -EPROTO;
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
	struct kd_memory_operand decoded;
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
	if (kd_origin_memory_decode(site, cont->packet, &offset) ||
	    kd_memory_operand_decode(site, &decoded))
		return -EPROTO;
	operation->packet = cont->packet;
	operation->image = frame->image;
	operation->artifact_sequence = 0;
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
	operation->result_value = 0;
	operation->destination = decoded.destination;
	operation->immediate = decoded.immediate;
	operation->result = 0;
	local_save_flags(operation->executor_irq_flags);
	WRITE_ONCE(operation->phase, KD_ORIGIN_MEMORY_PREPARED);
	return 0;
}

static int kd_memory_reached_read(void *context, unsigned long address,
	void *out, unsigned int size)
{
	int ret;

	(void)context;
	ret = kd_source_pin_text_range(address, size);
	return ret ? ret : copy_from_kernel_nofault(out, (void *)address, size);
}

int kd_exec_cont_memory_prepare_reached(struct kd_exec_frame *frame)
{
	struct kd_exec_continuation *cont = frame ? kd_exec_frame_continuation(frame) : NULL;
	struct kd_origin_memory *operation;
	struct kd_memory_operand decoded;
	unsigned long offset;
	int result;

	if (!kd_exec_cont_valid(cont) || !cont->service_ops || !cont->reached_active ||
	    !cont->reached_artifact_sequence || cont->state != KD_CONT_BOUND ||
	    cont->executor != current || cont->root->packet_owner != cont ||
	    frame->packet_state != KD_PACKET_FULL || !frame->executed ||
	    cont->service_call.api != KD_SERVICE_NONE || cont->origin_call.entry ||
	    cont->origin_call.servicing || (cont->origin_call.phase != KD_ORIGIN_CALL_IDLE &&
	    cont->origin_call.phase != KD_ORIGIN_CALL_CONSUMED))
		return -EINVAL;
	operation = &cont->origin_memory;
	if ((operation->phase != KD_ORIGIN_MEMORY_IDLE &&
	     operation->phase != KD_ORIGIN_MEMORY_CONSUMED) || operation->sequence == U64_MAX ||
	    !(cont->packet->flags & 2) || cont->packet->sp < cont->stack_base + 512 ||
	    cont->packet->sp > cont->stack_base + THREAD_SIZE)
		return -EINVAL;
	result = kd_origin_memory_reached_decode(&operation->reached_site,
		cont->packet->ip, kd_memory_reached_read, cont);
	if (result)
		return result;
	if (kd_origin_memory_decode(&operation->reached_site, cont->packet, &offset) ||
	    kd_memory_operand_decode(&operation->reached_site, &decoded))
		return -EPROTO;
	operation->packet = cont->packet;
	operation->image = NULL;
	operation->site = &operation->reached_site;
	operation->artifact_sequence = cont->reached_artifact_sequence;
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
	operation->result_value = 0;
	operation->destination = decoded.destination;
	operation->immediate = decoded.immediate;
	operation->result = 0;
	local_save_flags(operation->executor_irq_flags);
	WRITE_ONCE(operation->phase, KD_ORIGIN_MEMORY_PREPARED);
	return 0;
}

static void kd_memory_write_register(struct kd_regs *regs, unsigned int destination,
	unsigned int width, unsigned long value)
{
	if (width == 32)
		value = (u32)value;
	switch (destination) {
	case 0: regs->ax = value; break;
	case 1: regs->cx = value; break;
	case 2: regs->dx = value; break;
	case 3: regs->bx = value; break;
	case 5: regs->bp = value; break;
	case 6: regs->si = value; break;
	case 7: regs->di = value; break;
	case 8: regs->r8 = value; break;
	case 9: regs->r9 = value; break;
	case 10: regs->r10 = value; break;
	case 11: regs->r11 = value; break;
	case 12: regs->r12 = value; break;
	case 13: regs->r13 = value; break;
	case 14: regs->r14 = value; break;
	case 15: regs->r15 = value; break;
	default: BUG();
	}
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
	    (operation->artifact_sequence ?
	     (!cont->reached_active || operation->artifact_sequence != cont->reached_artifact_sequence ||
	      operation->image || operation->site != &operation->reached_site) :
	     (cont->reached_active || operation->image != cont->frame.image)) || !operation->site ||
	    cont->packet->sp != operation->source_sp ||
	    cont->packet->ip != operation->site->ip || !(operation->result_flags & 2))
		return -EPROTO;
	if ((operation->site->operation <= KD_ORIGIN_MEMORY_DEC &&
	     ((operation->result_flags ^ operation->input_flags) & 1)) ||
	    (operation->site->operation == KD_ORIGIN_MEMORY_LOAD &&
	     ((operation->result_flags ^ operation->input_flags) & KD_REG_ARITHMETIC_FLAGS)) ||
	    (operation->site->operation == KD_ORIGIN_MEMORY_TEST &&
	     (operation->result_flags & (1UL | (1UL << 11)))))
		return -EPROTO;
	if (operation->site->operation == KD_ORIGIN_MEMORY_LOAD)
		kd_memory_write_register(cont->packet, operation->destination,
			operation->site->width, operation->result_value);
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
	unsigned long flags, input, value;
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
	} else if (operation->site->operation == KD_ORIGIN_MEMORY_DEC) {
		if (operation->site->width == 32)
			KD_MEMORY_APPLY("decl");
		else
			KD_MEMORY_APPLY("decq");
	} else if (operation->site->operation == KD_ORIGIN_MEMORY_LOAD) {
		if (operation->site->width == 32)
			asm volatile("pushq %[input]; popfq; movl %%gs:(%[offset]), %k[value]; "
				"pushfq; popq %[output]" : [output] "=r"(flags), [value] "=r"(value)
				: [input] "r"(input), [offset] "r"(offset) : "cc", "memory");
		else
			asm volatile("pushq %[input]; popfq; movq %%gs:(%[offset]), %[value]; "
				"pushfq; popq %[output]" : [output] "=r"(flags), [value] "=r"(value)
				: [input] "r"(input), [offset] "r"(offset) : "cc", "memory");
		operation->result_value = value;
	} else {
		value = operation->immediate;
		if (operation->site->width == 16)
			asm volatile("pushq %[input]; popfq; testw %w[value], %%gs:(%[offset]); "
				"pushfq; popq %[output]" : [output] "=r"(flags)
				: [input] "r"(input), [offset] "r"(offset), [value] "r"(value)
				: "cc", "memory");
		else
			asm volatile("pushq %[input]; popfq; testl %k[value], %%gs:(%[offset]); "
				"pushfq; popq %[output]" : [output] "=r"(flags)
				: [input] "r"(input), [offset] "r"(offset), [value] "r"(value)
				: "cc", "memory");
	}
#undef KD_MEMORY_APPLY
	operation->result_flags = flags;
}
