/* SPDX-License-Identifier: GPL-2.0 */
/* Resident x86-64 lowering. Source registers stay in the canonical packet;
 * only this generated function's temporary values occupy executor GPRs. */
enum { A, C, D, B, SP, BP, SI, DI, R8, R9, R10, R11, S, P, F, T };
struct jit_output {
	u8 *code;
	unsigned int length, capacity;
	int error;
	unsigned int failures[12], failure_count;
	unsigned long return_target;
};

static int jit_mem_read(struct kd_reached_state *s, unsigned long address,
	u64 *value, unsigned int width)
{
	*value = 0;
	return s->ops->read(s->context, address, value, width) ? KD_REACHED_MEMORY : 0;
}

static int jit_mem_write(struct kd_reached_state *s, unsigned long address,
	u64 value, unsigned int width)
{
	return s->ops->write(s->context, address, &value, width) ? KD_REACHED_MEMORY : 0;
}

static int jit_mem_atomic(struct kd_reached_state *s, unsigned long address,
	u64 value, unsigned int operation, unsigned int width)
{
	int ret;

	if (!s->ops->atomic)
		return KD_REACHED_UNSUPPORTED;
	ret = s->ops->atomic(s->context, address, width, operation, value,
		s->regs->ax, s->regs->flags, &s->jit_value, &s->jit_flags);
	return ret == -EOPNOTSUPP ? KD_REACHED_UNSUPPORTED : ret ? KD_REACHED_MEMORY : 0;
}

static void j8(struct jit_output *o, unsigned int value)
{
	if (o->length >= o->capacity) { o->error = -ENOSPC; return; }
	o->code[o->length++] = value;
}
static void j32(struct jit_output *o, u32 value)
{
	unsigned int i;
	for (i = 0; i < 4; ++i) j8(o, value >> (8 * i));
}
static void j64(struct jit_output *o, u64 value)
{
	unsigned int i;
	for (i = 0; i < 8; ++i) j8(o, value >> (8 * i));
}
static void jr(struct jit_output *o, unsigned int width, unsigned int reg,
	unsigned int base)
{
	if (width == 2) j8(o, 0x66);
	j8(o, 0x40 | (width == 8 ? 8 : 0) | ((reg >> 3) << 2) | (base >> 3));
}
static void jm(struct jit_output *o, unsigned int reg, unsigned int base, int off)
{
	j8(o, 0x80 | ((reg & 7) << 3) | (base & 7));
	if ((base & 7) == SP) j8(o, 0x24);
	j32(o, off);
}
static void load(struct jit_output *o, unsigned int dst, unsigned int base,
	int offset, unsigned int width)
{
	jr(o, width >= 4 ? width : 4, dst, base);
	if (width <= 2) { j8(o, 0x0f); j8(o, width == 1 ? 0xb6 : 0xb7); }
	else j8(o, 0x8b);
	jm(o, dst, base, offset);
}
static void store(struct jit_output *o, unsigned int src, unsigned int base,
	int offset, unsigned int width)
{
	jr(o, width, src, base); j8(o, width == 1 ? 0x88 : 0x89); jm(o, src, base, offset);
}
static void move(struct jit_output *o, unsigned int dst, unsigned int src)
{
	jr(o, 8, src, dst); j8(o, 0x89); j8(o, 0xc0 | ((src & 7) << 3) | (dst & 7));
}
static void constant(struct jit_output *o, unsigned int dst, u64 value)
{
	j8(o, 0x48 | (dst >> 3)); j8(o, 0xb8 | (dst & 7)); j64(o, value);
}
static void binary(struct jit_output *o, unsigned int opcode, unsigned int width,
	unsigned int dst, unsigned int src)
{
	jr(o, width, src, dst); j8(o, opcode - (width == 1 ? 1 : 0));
	j8(o, 0xc0 | ((src & 7) << 3) | (dst & 7));
}
static void immediate32(struct jit_output *o, unsigned int group, unsigned int reg, u32 value)
{
	jr(o, 8, group, reg); j8(o, 0x81); j8(o, 0xc0 | (group << 3) | (reg & 7)); j32(o, value);
}
static unsigned int branch(struct jit_output *o, unsigned int cc)
{
	j8(o, 0x0f); j8(o, 0x80 | cc); j32(o, 0); return o->length - 4;
}
static void patch(struct jit_output *o, unsigned int position, unsigned int target)
{
	u32 relative = target - position - 4;
	unsigned int i;
	if (position + 4 > o->capacity) { o->error = -ENOSPC; return; }
	for (i = 0; i < 4; ++i) o->code[position + i] = relative >> (8 * i);
}
static void call(struct jit_output *o, unsigned long target)
{
	long distance = target - (unsigned long)(o->code + o->length + 5);
	if ((long)(s32)distance == distance) { j8(o, 0xe8); j32(o, distance); }
	else { constant(o, R11, target); j8(o, 0x41); j8(o, 0xff); j8(o, 0xd3); }
	/* Helpers return a precise event before packet commitment on failure. */
	j8(o, 0x85); j8(o, 0xc0);
	if (o->failure_count == ARRAY_SIZE(o->failures)) { o->error = -ENOSPC; return; }
	o->failures[o->failure_count++] = branch(o, 5);
}
static unsigned int slot(unsigned int reg)
{
	static const unsigned int offsets[16] = { KD_REG_AX, KD_REG_CX, KD_REG_DX,
		KD_REG_BX, KD_REG_SP, KD_REG_BP, KD_REG_SI, KD_REG_DI,
		KD_REG_R8, KD_REG_R9, KD_REG_R10, KD_REG_R11, KD_REG_R12,
		KD_REG_R13, KD_REG_R14, KD_REG_R15 };
	return offsets[reg & 15];
}
static void effective(struct jit_output *o, const struct operand *v, unsigned long next)
{
	if (v->has_base) load(o, A, P, slot(v->base), 8);
	else constant(o, A, v->rip_relative ? next : 0);
	if (v->has_index) {
		load(o, R10, P, slot(v->index), 8);
		j8(o, 0x4a); j8(o, 0x8d); j8(o, 0x04); j8(o, (v->scale << 6) | 0x10);
	}
	if (v->displacement) {
		constant(o, R10, v->displacement);
		j8(o, 0x4a); j8(o, 0x8d); j8(o, 0x04); j8(o, 0x10);
	}
}
static void memory_read(struct jit_output *o, unsigned int width)
{
	move(o, SI, A); move(o, DI, S);
	j8(o, 0x48); j8(o, 0x8d); j8(o, 0x14); j8(o, 0x24);
	constant(o, C, width); call(o, (unsigned long)jit_mem_read);
}
static void operand_read(struct jit_output *o, const struct operand *v,
	unsigned int destination, unsigned long next)
{
	if (v->literal) constant(o, destination, v->immediate);
	else if (!v->memory) load(o, destination, P, slot(v->reg) + v->high8, v->width);
	else {
		effective(o, v, next); memory_read(o, v->width); load(o, destination, SP, 0, 8);
	}
}
static void memory_write(struct jit_output *o, unsigned int width)
{
	move(o, SI, A); move(o, DI, S); move(o, D, B);
	constant(o, C, width); call(o, (unsigned long)jit_mem_write);
}
static void operand_write(struct jit_output *o, const struct operand *v, unsigned long next)
{
	if (v->memory) { effective(o, v, next); memory_write(o, v->width); }
	else {
		if (v->width == 4) { j8(o, 0x89); j8(o, 0xdb); }
		store(o, B, P, slot(v->reg) + v->high8, v->width == 4 ? 8 : v->width);
	}
}
static void flags_in(struct jit_output *o)
{
	load(o, F, P, KD_REG_FLAGS, 8);
	j8(o, 0x9c); j8(o, 0x41); j8(o, 0x5a);
	immediate32(o, 4, R10, ~KD_REG_ARITHMETIC_FLAGS);
	move(o, R11, F); immediate32(o, 4, R11, KD_REG_ARITHMETIC_FLAGS);
	binary(o, 0x09, 8, R10, R11);
	j8(o, 0x41); j8(o, 0x52); j8(o, 0x9d);
}
static void flags_out(struct jit_output *o)
{
	j8(o, 0x9c); j8(o, 0x41); j8(o, 0x5e);
	immediate32(o, 4, F, KD_REG_ARITHMETIC_FLAGS);
	load(o, R11, P, KD_REG_FLAGS, 8); immediate32(o, 4, R11, ~KD_REG_ARITHMETIC_FLAGS);
	binary(o, 0x09, 8, F, R11); store(o, F, SP, 16, 8);
}
static void cmov(struct jit_output *o, unsigned int cc, unsigned int width,
	unsigned int dst, unsigned int src)
{
	jr(o, width, dst, src); j8(o, 0x0f); j8(o, 0x40 | cc);
	j8(o, 0xc0 | ((dst & 7) << 3) | (src & 7));
}
static void unary(struct jit_output *o, unsigned int group, unsigned int width)
{
	jr(o, width, group, B); j8(o, group < 2 ? (width == 1 ? 0xfe : 0xff) :
		(width == 1 ? 0xf6 : 0xf7)); j8(o, 0xc3 | (group << 3));
}
static void bit_address(struct jit_output *o, const struct decoded *d, unsigned long next)
{
	effective(o, &d->dst, next);
	if (!d->src.literal) {
		unsigned int bits = d->dst.width * 8;
		move(o, R10, T);
		if (bits < 64) {
			jr(o, 8, 4, R10); j8(o, 0xc1); j8(o, 0xe2); j8(o, 64 - bits);
			jr(o, 8, 7, R10); j8(o, 0xc1); j8(o, 0xfa); j8(o, 64 - bits);
		}
		jr(o, 8, 7, R10); j8(o, 0xc1); j8(o, 0xfa);
		j8(o, d->dst.width == 2 ? 4 : d->dst.width == 4 ? 5 : 6);
		j8(o, 0x4a); j8(o, 0x8d); j8(o, 0x04);
		j8(o, (d->dst.width == 2 ? 0x40 : d->dst.width == 4 ? 0x80 : 0xc0) | 0x10);
	}
}

int kd_reached_jit_compile(const struct decoded *d, void *code,
	unsigned int capacity, unsigned long return_target)
{
	struct jit_output out = { .code = code, .capacity = capacity,
		.return_target = return_target }, *o = &out;
	unsigned long ip = d->state->regs->ip, next = ip + d->length;
	unsigned int edge = KD_REACHED_FALLTHROUGH, i, zero = 0;
	bool write = false, changed_flags = false, explicit_ip = false;
	bool atomic = d->locked || d->operation == OP_XCHG || d->operation == OP_XADD ||
		d->operation == OP_CMPXCHG || (d->operation == OP_BIT && d->dst.memory && d->condition);

	if (d->error || !d->length || !return_target || capacity < 64)
		return -EINVAL;
	/* Five saves and32 private bytes keep every helper CALL aligned. */
	j8(o, 0xf3); j8(o, 0x0f); j8(o, 0x1e); j8(o, 0xfa);
	for (i = S; i <= T; ++i) { j8(o, 0x41); j8(o, 0x50 | (i & 7)); }
	j8(o, 0x53); j8(o, 0x48); j8(o, 0x83); j8(o, 0xec); j8(o, 32);
	move(o, S, DI); load(o, P, S, offsetof(struct kd_reached_state, regs), 8);
	j8(o, 0x48); j8(o, 0x8d); j8(o, 0x05); j32(o, 0);
	store(o, A, S, offsetof(struct kd_reached_state, jit_code), 8);
	jr(o, 8, 0, S); j8(o, 0xff); jm(o, 0, S, offsetof(struct kd_reached_state, jit_entries));
	if (atomic) {
		unsigned int operation;
		if (!d->dst.memory || ((d->operation == OP_XADD || d->operation == OP_CMPXCHG) && !d->locked))
			return -EOPNOTSUPP;
		switch (d->operation) {
		case OP_ADD: operation = KD_REACHED_ATOMIC_ADD; break;
		case OP_SUB: operation = KD_REACHED_ATOMIC_SUB; break;
		case OP_AND: operation = KD_REACHED_ATOMIC_AND; break;
		case OP_OR: operation = KD_REACHED_ATOMIC_OR; break;
		case OP_XOR: operation = KD_REACHED_ATOMIC_XOR; break;
		case OP_INC: operation = KD_REACHED_ATOMIC_INC; break;
		case OP_DEC: operation = KD_REACHED_ATOMIC_DEC; break;
		case OP_XADD: operation = KD_REACHED_ATOMIC_XADD; break;
		case OP_XCHG: operation = KD_REACHED_ATOMIC_XCHG; break;
		case OP_CMPXCHG: operation = KD_REACHED_ATOMIC_CMPXCHG; break;
		case OP_BIT: operation = (d->locked ? KD_REACHED_ATOMIC_BTS_LOCKED :
			KD_REACHED_ATOMIC_BTS_UNLOCKED) + d->condition - 1; break;
		default: return -EOPNOTSUPP;
		}
		constant(o, T, 0);
		if (d->operation != OP_INC && d->operation != OP_DEC) operand_read(o, &d->src, T, next);
		if (d->operation == OP_BIT) bit_address(o, d, next); else effective(o, &d->dst, next);
		move(o, SI, A); move(o, DI, S); move(o, D, T);
		constant(o, C, operation); constant(o, R8, d->dst.width);
		call(o, (unsigned long)jit_mem_atomic);
		load(o, F, S, offsetof(struct kd_reached_state, jit_flags), 8); store(o, F, SP, 16, 8);
		changed_flags = true;
		if (d->operation == OP_XADD || d->operation == OP_XCHG || d->operation == OP_CMPXCHG) {
			load(o, B, S, offsetof(struct kd_reached_state, jit_value), 8);
			if (d->operation == OP_CMPXCHG) store(o, B, P, KD_REG_AX, 8);
			else operand_write(o, &d->src, next);
		}
		goto commit;
	}
	switch (d->operation) {
	case OP_NONE: break;
	case OP_PAUSE: j8(o, 0xf3); j8(o, 0x90); break;
	case OP_LFENCE: case OP_MFENCE: case OP_SFENCE:
		j8(o, 0x0f); j8(o, 0xae); j8(o, 0xe8 + 8 * (d->operation - OP_LFENCE)); break;
	case OP_LEA: effective(o, &d->src, next); move(o, B, A); write = true; break;
	case OP_MOV: case OP_ZX: case OP_SX: case OP_CMOV:
		operand_read(o, &d->src, B, next);
		if (d->operation == OP_SX) {
			jr(o, d->dst.width, B, B);
			if (d->src.width == 4) j8(o, 0x63);
			else { j8(o, 0x0f); j8(o, d->src.width == 1 ? 0xbe : 0xbf); }
			j8(o, 0xdb);
		}
		if (d->operation == OP_CMOV) {
			load(o, T, P, slot(d->dst.reg), 8); flags_in(o);
			cmov(o, d->condition, d->dst.width, T, B); move(o, B, T);
		}
		write = true; break;
	case OP_SET:
		flags_in(o); j8(o, 0x0f); j8(o, 0x90 | d->condition); j8(o, 0xc3); write = true; break;
	case OP_CLC: case OP_STC: case OP_CMC:
		flags_in(o); j8(o, d->operation == OP_CLC ? 0xf8 : d->operation == OP_STC ? 0xf9 : 0xf5);
		flags_out(o); changed_flags = true; break;
	case OP_LAHF: case OP_SAHF:
		load(o, A, P, KD_REG_AX, 8); flags_in(o); j8(o, d->operation == OP_LAHF ? 0x9f : 0x9e);
		if (d->operation == OP_LAHF) store(o, A, P, KD_REG_AX, 8);
		else { flags_out(o); changed_flags = true; }
		break;
	case OP_SIGN_PAIR:
		operand_read(o, &d->src, A, next);
		if (d->dst.width == 2) j8(o, 0x66);
		if (d->dst.width == 8) j8(o, 0x48);
		j8(o, 0x99); move(o, B, D); write = true; break;
	case OP_PUSH: case OP_CALL:
		operand_read(o, d->operation == OP_PUSH ? &d->dst : &d->src, B, next);
		if (d->operation == OP_CALL) {
			if (d->src.rip_relative && d->src.literal) { constant(o, T, next); binary(o, 0x01, 8, B, T); }
			store(o, B, SP, 8, 8); constant(o, B, next); edge = KD_REACHED_CALL;
		}
		load(o, A, P, KD_REG_SP, 8); immediate32(o, 5, A, 8); memory_write(o, 8);
		load(o, A, P, KD_REG_SP, 8); immediate32(o, 5, A, 8); store(o, A, P, KD_REG_SP, 8);
		if (d->operation == OP_CALL) { load(o, B, SP, 8, 8); explicit_ip = true; }
		break;
	case OP_POP: case OP_RET: case OP_LEAVE:
		load(o, A, P, d->operation == OP_LEAVE ? KD_REG_BP : KD_REG_SP, 8); memory_read(o, 8);
		load(o, B, SP, 0, 8);
		load(o, A, P, d->operation == OP_LEAVE ? KD_REG_BP : KD_REG_SP, 8);
		immediate32(o, 0, A, 8 + (d->operation == OP_RET ? d->adjustment : 0));
		store(o, A, P, KD_REG_SP, 8);
		if (d->operation == OP_LEAVE) store(o, B, P, KD_REG_BP, 8);
		else if (d->operation == OP_POP) operand_write(o, &d->dst, next);
		else { explicit_ip = true; edge = KD_REACHED_RETURN; }
		break;
	case OP_JCC:
		constant(o, B, next); constant(o, T, next + d->src.immediate); flags_in(o);
		cmov(o, d->condition, 8, B, T); explicit_ip = true; edge = KD_REACHED_JCC; break;
	case OP_JMP:
		operand_read(o, &d->src, B, next);
		if (d->src.rip_relative && d->src.literal) { constant(o, T, next); binary(o, 0x01, 8, B, T); }
		explicit_ip = true; edge = KD_REACHED_JUMP; break;
	case OP_MOVS: case OP_STOS:
		if (d->rep) { load(o, A, P, KD_REG_CX, 8); binary(o, 0x85, 8, A, A); zero = branch(o, 4); }
		if (d->operation == OP_MOVS) { load(o, A, P, KD_REG_SI, 8); memory_read(o, d->width); load(o, B, SP, 0, 8); }
		else load(o, B, P, KD_REG_AX, d->width);
		load(o, A, P, KD_REG_DI, 8); memory_write(o, d->width);
		constant(o, T, d->width); constant(o, B, -(u64)d->width);
		load(o, A, P, KD_REG_FLAGS, 8); immediate32(o, 4, A, 0x400);
		cmov(o, 5, 8, T, B);
		load(o, A, P, KD_REG_DI, 8); binary(o, 0x01, 8, A, T); store(o, A, P, KD_REG_DI, 8);
		if (d->operation == OP_MOVS) { load(o, A, P, KD_REG_SI, 8); binary(o, 0x01, 8, A, T); store(o, A, P, KD_REG_SI, 8); }
		constant(o, B, next);
		if (d->rep) {
			load(o, A, P, KD_REG_CX, 8); immediate32(o, 5, A, 1); store(o, A, P, KD_REG_CX, 8);
			constant(o, T, ip); cmov(o, 5, 8, B, T);
		}
		explicit_ip = true; break;
	case OP_BIT:
		operand_read(o, &d->src, T, next);
		if (d->dst.memory) { bit_address(o, d, next); memory_read(o, d->dst.width); load(o, B, SP, 0, 8); }
		else operand_read(o, &d->dst, B, next);
		flags_in(o); jr(o, d->dst.width, T, B); j8(o, 0x0f);
		j8(o, d->condition == 0 ? 0xa3 : d->condition == 1 ? 0xab : d->condition == 2 ? 0xb3 : 0xbb);
		j8(o, 0xc0 | ((T & 7) << 3) | B); flags_out(o);
		changed_flags = true; write = d->condition != 0; break;
	case OP_SCAN:
		operand_read(o, &d->src, T, next); load(o, B, P, slot(d->dst.reg), 8); flags_in(o);
		if (d->condition >= 2) j8(o, 0xf3);
		jr(o, d->dst.width, B, T); j8(o, 0x0f); j8(o, (d->condition & 1) ? 0xbd : 0xbc);
		j8(o, 0xc0 | (B << 3) | (T & 7)); flags_out(o); changed_flags = true;
		store(o, B, P, slot(d->dst.reg), 8); break;
	default:
		operand_read(o, &d->dst, B, next);
		if (d->operation == OP_IMUL && d->multiply_immediate) {
			operand_read(o, &d->src, B, next); constant(o, T, d->multiplier);
		} else if (d->operation != OP_INC && d->operation != OP_DEC && d->operation != OP_NOT && d->operation != OP_NEG)
			operand_read(o, &d->src, T, next);
		flags_in(o);
		if (d->operation == OP_SHIFT) {
			move(o, C, T); jr(o, d->dst.width, d->condition, B);
			j8(o, d->dst.width == 1 ? 0xd2 : 0xd3); j8(o, 0xc3 | (d->condition << 3));
		} else if (d->operation == OP_IMUL) {
			jr(o, d->dst.width, B, T); j8(o, 0x0f); j8(o, 0xaf); j8(o, 0xdf);
		} else if (d->operation == OP_INC || d->operation == OP_DEC || d->operation == OP_NOT || d->operation == OP_NEG) {
			unary(o, d->operation == OP_INC ? 0 : d->operation == OP_DEC ? 1 : d->operation == OP_NOT ? 2 : 3, d->dst.width);
		} else {
			unsigned int opcode;
			switch (d->operation) {
			case OP_ADD: opcode = 0x01; break; case OP_OR: opcode = 0x09; break;
			case OP_ADC: opcode = 0x11; break; case OP_SBB: opcode = 0x19; break;
			case OP_AND: opcode = 0x21; break; case OP_SUB: opcode = 0x29; break;
			case OP_XOR: opcode = 0x31; break; case OP_CMP: opcode = 0x39; break;
			case OP_TEST: opcode = 0x85; break; default: return -EOPNOTSUPP;
			}
			binary(o, opcode, d->dst.width, B, T);
		}
		if (d->operation != OP_NOT) { flags_out(o); changed_flags = true; }
		write = d->operation != OP_CMP && d->operation != OP_TEST;
	}
	if (write) operand_write(o, &d->dst, next);
commit:
	if (zero) { patch(o, zero, o->length); /* zero-count REP joins the next-IP path */
		/* A zero count must not inherit a temporary source-IP selection. */
		load(o, A, P, KD_REG_CX, 8); binary(o, 0x85, 8, A, A);
		constant(o, T, next); cmov(o, 4, 8, B, T);
	}
	if (!explicit_ip) constant(o, B, next);
	store(o, B, P, KD_REG_IP, 8);
	if (changed_flags) { load(o, F, SP, 16, 8); store(o, F, P, KD_REG_FLAGS, 8); }
	jr(o, 8, 0, S); j8(o, 0xff); jm(o, 0, S, offsetof(struct kd_reached_state, jit_retired));
	constant(o, A, edge == KD_REACHED_FALLTHROUGH ? KD_REACHED_NEXT : KD_REACHED_EDGE);
	for (i = 0; i < o->failure_count; ++i) patch(o, o->failures[i], o->length);
	j8(o, 0x48); j8(o, 0x83); j8(o, 0xc4); j8(o, 32); j8(o, 0x5b);
	for (i = T + 1; i-- > S;) { j8(o, 0x41); j8(o, 0x58 | (i & 7)); }
	{
		long distance = return_target - (unsigned long)(o->code + o->length + 5);
		if ((long)(s32)distance == distance) { j8(o, 0xe9); j32(o, distance); }
		else {
			constant(o, R11, return_target);
			/* Direct-thunk semantics across a far address: the target need
			 * not be an ordinary indirect function entry. */
			j8(o, 0x3e); j8(o, 0x41); j8(o, 0xff); j8(o, 0xe3);
		}
	}
	return o->error ? o->error : (int)o->length;
}
