// SPDX-License-Identifier: GPL-2.0
/* Allocation-independent x86-64 scalar execution on the executor C stack.
 * Source RSP is an ordinary virtual register; no hardware stack switch occurs.
 * The bounded supported subset is intentionally explicit. Reached operations
 * needing a context/service contract stop before effects, never run a suffix
 * on the origin, and never decompose atomic operations into C loads/stores.
 */
#include <linux/errno.h>
#include <linux/string.h>
#include <asm/barrier.h>
#include <asm/processor.h>
#include "kd_reached.h"

#define F_CF 0x001UL
#define F_PF 0x004UL
#define F_AF 0x010UL
#define F_ZF 0x040UL
#define F_SF 0x080UL
#define F_OF 0x800UL
#define F_ARITH (F_CF | F_PF | F_AF | F_ZF | F_SF | F_OF)

enum operation {
	OP_NONE, OP_MOV, OP_LEA, OP_ZX, OP_SX,
	OP_ADD, OP_OR, OP_ADC, OP_SBB, OP_AND, OP_SUB, OP_XOR, OP_CMP,
	OP_TEST, OP_INC, OP_DEC, OP_NOT, OP_NEG,
	OP_PUSH, OP_POP, OP_LEAVE, OP_JCC, OP_CALL, OP_JMP, OP_RET,
	OP_CMOV, OP_SET, OP_PAUSE, OP_LFENCE, OP_MFENCE, OP_SFENCE,
};

struct operand {
	u64 immediate;
	s64 displacement;
	u8 reg, base, index, scale;
	u8 width;
	bool memory, literal, high8, rip_relative, has_base, has_index;
};

struct decoded {
	struct kd_reached_state *state;
	struct operand dst, src;
	u8 bytes[KD_REACHED_MAX_BYTES];
	u8 length, rex, width, operation, condition;
	u16 adjustment;
	bool rex_seen, op16, rep;
	int error;
};

static unsigned long *reg_slot(struct kd_regs *r, unsigned int reg)
{
	switch (reg) {
	case 0: return &r->ax;
	case 1: return &r->cx;
	case 2: return &r->dx;
	case 3: return &r->bx;
	case 4: return &r->sp;
	case 5: return &r->bp;
	case 6: return &r->si;
	case 7: return &r->di;
	case 8: return &r->r8;
	case 9: return &r->r9;
	case 10: return &r->r10;
	case 11: return &r->r11;
	case 12: return &r->r12;
	case 13: return &r->r13;
	case 14: return &r->r14;
	case 15: return &r->r15;
	default: return NULL;
	}
}

static u64 width_mask(unsigned int width)
{
	return width == 8 ? ~0ULL : (1ULL << (width * 8)) - 1;
}

static s64 sign_value(u64 value, unsigned int width)
{
	unsigned int shift = 64 - width * 8;

	return (s64)(value << shift) >> shift;
}

static u8 byte(struct decoded *d)
{
	u8 value = 0;

	if (d->error)
		return 0;
	if (d->length == KD_REACHED_MAX_BYTES) {
		d->error = -EOPNOTSUPP;
		return 0;
	}
	if (d->state->ops->fetch(d->state->context,
			d->state->regs->ip + d->length, &value, 1)) {
		d->error = -ENODATA;
		return 0;
	}
	d->bytes[d->length++] = value;
	return value;
}

static u64 immediate(struct decoded *d, unsigned int size)
{
	u64 value = 0;
	unsigned int i;

	for (i = 0; i < size && !d->error; ++i)
		value |= (u64)byte(d) << (i * 8);
	return value;
}

static struct operand reg_operand(struct decoded *d, unsigned int reg,
				  unsigned int width)
{
	struct operand o = { .reg = reg, .width = width };

	if (width == 1 && !d->rex_seen && reg >= 4 && reg <= 7) {
		o.reg = reg - 4;
		o.high8 = true;
	}
	return o;
}

static struct operand literal(u64 value, unsigned int width)
{
	struct operand o = { .immediate = value, .width = width, .literal = true };

	return o;
}

static void modrm(struct decoded *d, unsigned int width,
		  struct operand *rm, struct operand *reg, unsigned int *group)
{
	u8 value = byte(d), mod = value >> 6, r = (value >> 3) & 7, m = value & 7;

	*group = r;
	*reg = reg_operand(d, r | ((d->rex & 4) ? 8 : 0), width);
	*rm = reg_operand(d, m | ((d->rex & 1) ? 8 : 0), width);
	if (mod == 3 || d->error)
		return;
	rm->high8 = false;
	rm->memory = true;
	if (m == 4) {
		u8 sib = byte(d);
		u8 base = sib & 7, index = (sib >> 3) & 7;

		rm->scale = sib >> 6;
		if (index != 4 || (d->rex & 2)) {
			rm->has_index = true;
			rm->index = index | ((d->rex & 2) ? 8 : 0);
		}
		if (mod || base != 5) {
			rm->has_base = true;
			rm->base = base | ((d->rex & 1) ? 8 : 0);
		} else {
			rm->displacement = sign_value(immediate(d, 4), 4);
		}
	} else if (!mod && m == 5) {
		rm->rip_relative = true;
		rm->displacement = sign_value(immediate(d, 4), 4);
	} else {
		rm->has_base = true;
		rm->base = m | ((d->rex & 1) ? 8 : 0);
	}
	if (mod == 1)
		rm->displacement += sign_value(immediate(d, 1), 1);
	if (mod == 2)
		rm->displacement += sign_value(immediate(d, 4), 4);
}

static enum operation arithmetic(unsigned int group)
{
	static const u8 operations[8] = {
		OP_ADD, OP_OR, OP_ADC, OP_SBB, OP_AND, OP_SUB, OP_XOR, OP_CMP,
	};

	return operations[group & 7];
}

static void decode(struct decoded *d)
{
	struct operand rm, reg;
	unsigned int group, width;
	u8 op, second;
	bool prefix = true;

	while (prefix && !d->error) {
		op = byte(d);
		switch (op) {
		case 0x66:
			d->op16 = true; d->rex = 0; d->rex_seen = false; break;
		case 0xf3:
			d->rep = true; d->rex = 0; d->rex_seen = false; break;
		case 0xf0: case 0xf2: case 0x64: case 0x65:
		case 0x67: case 0x26: case 0x2e: case 0x36: case 0x3e:
			/* Atomic, repeated, segmented and address-size contracts are
			 * not ordinary scalar operations. No data effects precede this. */
			d->error = -EOPNOTSUPP;
			break;
		default:
			if ((op & 0xf0) == 0x40) {
				d->rex = op & 0xf;
				d->rex_seen = true;
			} else {
				prefix = false;
			}
		}
	}
	if (d->error)
		return;
	d->width = (d->rex & 8) ? 8 : d->op16 ? 2 : 4;
	if (d->rep && op != 0x90 && op != 0x0f) {
		d->error = -EOPNOTSUPP;
		return;
	}
	if (op == 0x90) {
		/* REX.B 90 exchanges RAX/R8, not NOP. */
		if (d->rex & 1) {
			d->error = -EOPNOTSUPP;
			return;
		}
		d->operation = d->rep ? OP_PAUSE : OP_NONE;
		return;
	}
	if (op >= 0x70 && op <= 0x7f) {
		d->operation = OP_JCC;
		d->condition = op & 15;
		d->src = literal(sign_value(immediate(d, 1), 1), 8);
		return;
	}
	if (op >= 0xb0 && op <= 0xbf) {
		width = op < 0xb8 ? 1 : d->width;
		d->operation = OP_MOV;
		d->dst = reg_operand(d, (op & 7) | ((d->rex & 1) ? 8 : 0), width);
		d->src = literal(immediate(d, width), width);
		return;
	}
	if (op >= 0x50 && op <= 0x5f) {
		d->operation = op < 0x58 ? OP_PUSH : OP_POP;
		/* Operand-size 16 stack operations are deferred explicitly. */
		if (d->op16) {
			d->error = -EOPNOTSUPP;
			return;
		}
		d->dst = reg_operand(d, (op & 7) | ((d->rex & 1) ? 8 : 0), 8);
		return;
	}
	if (op <= 0x3d && (op & 7) <= 5) {
		d->operation = arithmetic(op >> 3);
		width = (op & 1) ? d->width : 1;
		if ((op & 7) <= 3) {
			modrm(d, width, &rm, &reg, &group);
			d->dst = (op & 2) ? reg : rm;
			d->src = (op & 2) ? rm : reg;
		} else {
			d->dst = reg_operand(d, 0, width);
			d->src = literal(sign_value(immediate(d, width == 8 ? 4 : width),
						 width == 8 ? 4 : width), width);
		}
		return;
	}
	switch (op) {
	case 0x63:
		modrm(d, 4, &d->src, &d->dst, &group);
		if (!(d->rex & 8)) { d->error = -EOPNOTSUPP; return; }
		d->dst.width = 8;
		d->operation = OP_SX;
		break;
	case 0x68: case 0x6a:
		if (d->op16) { d->error = -EOPNOTSUPP; return; }
		d->operation = OP_PUSH;
		d->dst = literal(sign_value(immediate(d, op == 0x68 ? 4 : 1),
					   op == 0x68 ? 4 : 1), 8);
		break;
	case 0x80: case 0x81: case 0x83:
		width = op == 0x80 ? 1 : d->width;
		modrm(d, width, &d->dst, &reg, &group);
		d->operation = arithmetic(group);
		group = op == 0x83 ? 1 : width == 8 ? 4 : width;
		d->src = literal(sign_value(immediate(d, group), group), width);
		break;
	case 0x84: case 0x85:
		modrm(d, op == 0x84 ? 1 : d->width, &d->dst, &d->src, &group);
		d->operation = OP_TEST;
		break;
	case 0x88: case 0x89: case 0x8a: case 0x8b:
		modrm(d, (op & 1) ? d->width : 1, &rm, &reg, &group);
		d->dst = (op & 2) ? reg : rm;
		d->src = (op & 2) ? rm : reg;
		d->operation = OP_MOV;
		break;
	case 0x8d:
		modrm(d, d->width, &d->src, &d->dst, &group);
		d->operation = OP_LEA;
		if (!d->src.memory) d->error = -EOPNOTSUPP;
		break;
	case 0xa8: case 0xa9:
		width = op == 0xa8 ? 1 : d->width;
		d->operation = OP_TEST;
		d->dst = reg_operand(d, 0, width);
		d->src = literal(sign_value(immediate(d, width == 8 ? 4 : width),
					 width == 8 ? 4 : width), width);
		break;
	case 0xc6: case 0xc7:
		width = op == 0xc6 ? 1 : d->width;
		modrm(d, width, &d->dst, &reg, &group);
		if (group) { d->error = -EOPNOTSUPP; return; }
		d->operation = OP_MOV;
		d->src = literal(sign_value(immediate(d, width == 8 ? 4 : width),
					 width == 8 ? 4 : width), width);
		break;
	case 0xc3: case 0xc2:
		if (d->op16) { d->error = -EOPNOTSUPP; return; }
		d->operation = OP_RET;
		if (op == 0xc2) d->adjustment = immediate(d, 2);
		break;
	case 0xc9:
		if (d->op16) { d->error = -EOPNOTSUPP; return; }
		d->operation = OP_LEAVE;
		break;
	case 0xe8: case 0xe9: case 0xeb:
		d->operation = op == 0xe8 ? OP_CALL : OP_JMP;
		d->src = literal(sign_value(immediate(d, op == 0xeb ? 1 : 4),
					   op == 0xeb ? 1 : 4), 8);
		/* Relative branch operands use this otherwise irrelevant tag. */
		d->src.rip_relative = true;
		break;
	case 0xf6: case 0xf7:
		width = op == 0xf6 ? 1 : d->width;
		modrm(d, width, &d->dst, &reg, &group);
		if (!group) {
			d->operation = OP_TEST;
			d->src = literal(sign_value(immediate(d, width == 8 ? 4 : width),
						 width == 8 ? 4 : width), width);
		} else if (group == 2 || group == 3) {
			d->operation = group == 2 ? OP_NOT : OP_NEG;
		} else d->error = -EOPNOTSUPP;
		break;
	case 0xfe: case 0xff:
		modrm(d, op == 0xfe ? 1 : d->width, &d->dst, &reg, &group);
		if (group < 2) d->operation = group ? OP_DEC : OP_INC;
		else if (op == 0xff && (group == 2 || group == 4 || group == 6)) {
			if (d->op16) { d->error = -EOPNOTSUPP; return; }
			d->dst.width = 8;
			d->src = d->dst;
			d->operation = group == 2 ? OP_CALL : group == 4 ? OP_JMP : OP_PUSH;
		} else d->error = -EOPNOTSUPP;
		break;
	case 0x0f:
		second = byte(d);
		if (d->rep) {
			if (second == 0x1e && byte(d) == 0xfa) d->operation = OP_NONE;
			else d->error = -EOPNOTSUPP;
			return;
		}
		if (second >= 0x80 && second <= 0x8f) {
			d->operation = OP_JCC;
			d->condition = second & 15;
			d->src = literal(sign_value(immediate(d, 4), 4), 8);
		} else if (second >= 0x40 && second <= 0x4f) {
			modrm(d, d->width, &d->src, &d->dst, &group);
			d->condition = second & 15;
			d->operation = OP_CMOV;
		} else if (second >= 0x90 && second <= 0x9f) {
			modrm(d, 1, &d->dst, &reg, &group);
			d->condition = second & 15;
			d->operation = OP_SET;
		} else if (second == 0xb6 || second == 0xb7 ||
			   second == 0xbe || second == 0xbf) {
			modrm(d, (second & 1) ? 2 : 1, &d->src, &d->dst, &group);
			d->dst = reg_operand(d, group | ((d->rex & 4) ? 8 : 0), d->width);
			d->operation = (second & 8) ? OP_SX : OP_ZX;
		} else if (second == 0x1f) {
			modrm(d, d->width, &rm, &reg, &group);
			d->operation = OP_NONE;
			if (group) d->error = -EOPNOTSUPP;
		} else if (second == 0xae) {
			second = byte(d);
			if (second == 0xe8) d->operation = OP_LFENCE;
			else if (second == 0xf0) d->operation = OP_MFENCE;
			else if (second == 0xf8) d->operation = OP_SFENCE;
			else d->error = -EOPNOTSUPP;
		} else d->error = -EOPNOTSUPP;
		break;
	default: d->error = -EOPNOTSUPP;
	}
}

static unsigned long address(struct decoded *d, const struct operand *o)
{
	struct kd_regs *r = d->state->regs;
	unsigned long value = o->displacement;

	if (o->rip_relative) value += r->ip + d->length;
	if (o->has_base) value += *reg_slot(r, o->base);
	if (o->has_index) value += *reg_slot(r, o->index) << o->scale;
	return value;
}

static int read_operand(struct decoded *d, const struct operand *o, u64 *out)
{
	u64 value = 0;

	if (o->literal) value = o->immediate;
	else if (o->memory) {
		if (d->state->ops->read(d->state->context, address(d, o), &value, o->width))
			return -EFAULT;
	} else value = *reg_slot(d->state->regs, o->reg) >> (o->high8 ? 8 : 0);
	*out = value & width_mask(o->width);
	return 0;
}

static int write_operand(struct decoded *d, const struct operand *o, u64 value)
{
	unsigned long *slot;
	u64 mask = width_mask(o->width);

	value &= mask;
	if (o->memory)
		return d->state->ops->write(d->state->context, address(d, o), &value, o->width);
	slot = reg_slot(d->state->regs, o->reg);
	if (o->width == 4 || o->width == 8) *slot = value;
	else if (o->high8) *slot = (*slot & ~(mask << 8)) | (value << 8);
	else *slot = (*slot & ~mask) | value;
	return 0;
}

static bool condition(unsigned int cc, unsigned long flags)
{
	bool cf = flags & F_CF, zf = flags & F_ZF;
	bool sf = flags & F_SF, of = flags & F_OF, pf = flags & F_PF;

	switch (cc) {
	case 0: return of;
	case 1: return !of;
	case 2: return cf;
	case 3: return !cf;
	case 4: return zf;
	case 5: return !zf;
	case 6: return cf || zf;
	case 7: return !cf && !zf;
	case 8: return sf;
	case 9: return !sf;
	case 10: return pf;
	case 11: return !pf;
	case 12: return sf != of;
	case 13: return sf == of;
	case 14: return zf || sf != of;
	default: return !zf && sf == of;
	}
}

static unsigned long result_flags(u64 value, unsigned int width)
{
	unsigned long flags = 0;
	u8 parity = value;

	parity ^= parity >> 4;
	parity ^= parity >> 2;
	parity ^= parity >> 1;
	if (!(parity & 1)) flags |= F_PF;
	if (!(value & width_mask(width))) flags |= F_ZF;
	if (value & (1ULL << (width * 8 - 1))) flags |= F_SF;
	return flags;
}

static u64 calculate(struct decoded *d, u64 a, u64 b, unsigned long *flags)
{
	u64 value, mask = width_mask(d->dst.width);
	u64 sign = 1ULL << (d->dst.width * 8 - 1);
	u64 carry = *flags & F_CF ? 1 : 0;
	unsigned long f = 0;
	bool subtract = false, logical = false;

	switch (d->operation) {
	case OP_INC: b = 1; fallthrough;
	case OP_ADD: value = (a + b) & mask; f = value < a ? F_CF : 0; break;
	case OP_ADC:
		value = (a + b + carry) & mask;
		f = (value < a || (carry && value == a)) ? F_CF : 0;
		break;
	case OP_DEC: b = 1; fallthrough;
	case OP_CMP: case OP_SUB: subtract = true; value = (a - b) & mask;
		f = a < b ? F_CF : 0; break;
	case OP_SBB:
		subtract = true; value = (a - b - carry) & mask;
		f = (a < b || (carry && a == b)) ? F_CF : 0; break;
	case OP_NEG:
		b = a; a = 0; subtract = true; value = (-b) & mask;
		f = b ? F_CF : 0; break;
	case OP_OR: logical = true; value = a | b; break;
	case OP_XOR: logical = true; value = a ^ b; break;
	default: logical = true; value = a & b; break;
	}
	if (!logical) {
		if ((a ^ b ^ value) & 0x10) f |= F_AF;
		if ((subtract ? (a ^ b) : ~(a ^ b)) & (a ^ value) & sign) f |= F_OF;
	} else {
		/* Logical AF is architecturally undefined; retain its old value. */
		f |= *flags & F_AF;
	}
	f |= result_flags(value, d->dst.width);
	if (d->operation == OP_INC || d->operation == OP_DEC)
		f = (f & ~F_CF) | (*flags & F_CF);
	*flags = (*flags & ~F_ARITH) | f;
	return value;
}

static enum kd_reached_result execute(struct decoded *d)
{
	struct kd_reached_state *s = d->state;
	struct kd_regs *r = s->regs;
	u64 a = 0, b = 0, value = 0, word;
	unsigned long flags = r->flags, next = r->ip + d->length;
	unsigned long target = next, sp = r->sp;
	u8 edge = KD_REACHED_FALLTHROUGH;
	bool write = false;

	switch (d->operation) {
	case OP_NONE: break;
	case OP_PAUSE: cpu_relax(); break;
	case OP_LFENCE: asm volatile("lfence" ::: "memory"); break;
	case OP_MFENCE: asm volatile("mfence" ::: "memory"); break;
	case OP_SFENCE: asm volatile("sfence" ::: "memory"); break;
	case OP_LEA: value = address(d, &d->src); write = true; break;
	case OP_MOV: case OP_ZX: case OP_SX: case OP_CMOV:
		if (read_operand(d, &d->src, &value)) return KD_REACHED_MEMORY;
		if (d->operation == OP_SX) value = sign_value(value, d->src.width);
		/* CMOV reads its memory source even when the condition is false. */
		write = d->operation != OP_CMOV || condition(d->condition, flags);
		if (!write && d->dst.width == 4) {
			value = *reg_slot(r, d->dst.reg);
			write = true;
		}
		break;
	case OP_SET: value = condition(d->condition, flags); write = true; break;
	case OP_PUSH:
		if (read_operand(d, &d->dst, &value)) return KD_REACHED_MEMORY;
		word = value;
		if (s->ops->write(s->context, sp - 8, &word, 8)) return KD_REACHED_MEMORY;
		r->sp = sp - 8;
		break;
	case OP_POP:
		if (s->ops->read(s->context, sp, &word, 8)) return KD_REACHED_MEMORY;
		/* Only register POP is decoded. POP RSP overwrites the increment. */
		r->sp = sp + 8;
		write_operand(d, &d->dst, word);
		break;
	case OP_LEAVE:
		if (s->ops->read(s->context, r->bp, &word, 8)) return KD_REACHED_MEMORY;
		r->sp = r->bp + 8;
		r->bp = word;
		break;
	case OP_JCC:
		target = condition(d->condition, flags) ? next + d->src.immediate : next;
		edge = KD_REACHED_JCC;
		break;
	case OP_CALL: case OP_JMP:
		/* Reading a CALL [RSP] operand must precede the source return push. */
		if (read_operand(d, &d->src, &value)) return KD_REACHED_MEMORY;
		target = value + (d->src.rip_relative && d->src.literal ? next : 0);
		if (d->operation == OP_CALL) {
			word = next;
			if (s->ops->write(s->context, sp - 8, &word, 8)) return KD_REACHED_MEMORY;
			r->sp = sp - 8;
			edge = KD_REACHED_CALL;
		} else edge = KD_REACHED_JUMP;
		break;
	case OP_RET:
		if (s->ops->read(s->context, sp, &word, 8)) return KD_REACHED_MEMORY;
		target = word;
		r->sp = sp + 8 + d->adjustment;
		edge = KD_REACHED_RETURN;
		break;
	default:
		if (read_operand(d, &d->dst, &a)) return KD_REACHED_MEMORY;
		if (d->operation == OP_NOT) value = ~a;
		else {
			if (d->operation != OP_INC && d->operation != OP_DEC &&
			    d->operation != OP_NEG && read_operand(d, &d->src, &b))
				return KD_REACHED_MEMORY;
			value = calculate(d, a, b, &flags);
		}
		write = d->operation != OP_CMP && d->operation != OP_TEST;
	}
	if (write && write_operand(d, &d->dst, value)) return KD_REACHED_MEMORY;
	r->flags = flags;
	r->ip = target;
	s->event.next_ip = next;
	s->event.target = target;
	s->event.edge = edge;
	--s->budget;
	return edge == KD_REACHED_FALLTHROUGH ? KD_REACHED_NEXT : KD_REACHED_EDGE;
}

enum kd_reached_result kd_reached_step(struct kd_reached_state *s)
{
	struct decoded d = { .state = s };
	enum kd_reached_result result;
	unsigned int i;

	if (!s || !s->regs || !s->ops || !s->ops->fetch || !s->ops->read ||
	    !s->ops->write || s->packet_state != KD_PACKET_FULL)
		return KD_REACHED_PACKET;
	s->event.source_ip = s->regs->ip;
	s->event.next_ip = s->regs->ip;
	s->event.target = s->regs->ip;
	s->event.edge = KD_REACHED_FALLTHROUGH;
	s->event.length = 0;
	s->event.sequence = ++s->sequence;
	if (!s->budget) result = KD_REACHED_BUDGET;
	else {
		decode(&d);
		s->event.length = d.length;
		for (i = 0; i < d.length; ++i) s->event.bytes[i] = d.bytes[i];
		result = d.error == -ENODATA ? KD_REACHED_SOURCE :
			 d.error ? KD_REACHED_UNSUPPORTED : execute(&d);
	}
	s->event.result = result;
	return result;
}

enum kd_reached_result kd_reached_run(struct kd_reached_state *s,
				    unsigned int instruction_limit)
{
	enum kd_reached_result result;
	unsigned int i;

	if (!instruction_limit)
		return KD_REACHED_PACKET;
	if (instruction_limit > KD_REACHED_SEGMENT_MAX)
		instruction_limit = KD_REACHED_SEGMENT_MAX;
	for (i = 0; i < instruction_limit; ++i) {
		result = kd_reached_step(s);
		if (result != KD_REACHED_NEXT) return result;
	}
	if (!s || !s->regs || !s->ops || !s->ops->fetch || !s->ops->read ||
	    !s->ops->write || s->packet_state != KD_PACKET_FULL)
		return KD_REACHED_PACKET;
	s->event.source_ip = s->regs->ip;
	s->event.next_ip = s->regs->ip;
	s->event.target = s->regs->ip;
	s->event.edge = KD_REACHED_FALLTHROUGH;
	s->event.length = 0;
	s->event.sequence = ++s->sequence;
	s->event.result = KD_REACHED_EDGE;
	return KD_REACHED_EDGE;
}

int kd_reached_begin(struct kd_reached_state *s, struct kd_regs *r,
		     unsigned int packet_state, u64 budget)
{
	if (!s || !r || (packet_state != KD_PACKET_FULL &&
			 packet_state != KD_PACKET_MINIMAL))
		return -EINVAL;
	if (packet_state == KD_PACKET_MINIMAL) {
		/* The clobber entry defines only IP/SP/BP. Every other GPR is a
		 * compiler output/clobber, so choose zero without reading its slot.
		 * This also materializes the successful killable result AX=0.
		 * Arithmetic flags are compiler-clobbered; no hardware IRQ/DF state
		 * is imported from these software flags onto the executor CPU.
		 */
		r->r15 = 0; r->r14 = 0; r->r13 = 0; r->r12 = 0;
		r->r11 = 0; r->bx = 0; r->r10 = 0; r->r9 = 0;
		r->r8 = 0; r->ax = 0; r->cx = 0; r->dx = 0;
		r->si = 0; r->di = 0;
		r->orig_ax = 0; r->cs = 0; r->flags = 2; r->ss = 0;
	}
	s->regs = r;
	s->packet_state = KD_PACKET_FULL;
	s->budget = budget;
	s->sequence = 0;
	return 0;
}
