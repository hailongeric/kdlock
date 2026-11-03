// SPDX-License-Identifier: GPL-2.0
#include <linux/completion.h>
#include <linux/errno.h>
#include <linux/irqflags.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/module.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/sched/task_stack.h>
#include <linux/string.h>
#include "kd_reached.h"

#define CODE 0x100000UL
#define DATA ((unsigned long)f->memory)
#define CHECK(test) do { if (!(test)) { failure_line = __LINE__; return -EINVAL; } ++checks; } while (0)

struct fixture {
	struct kd_regs regs;
	struct kd_reached_state state;
	u8 code[64];
	u64 memory[32];
	unsigned int code_size;
	unsigned int fetches;
	unsigned int reads;
	unsigned int writes;
	unsigned int atomics;
	unsigned int atomic_attempts, atomic_operation;
	u64 atomic_input;
	unsigned long max_fetch;
	bool fail_read;
	bool fail_write;
	bool fail_atomic;
};

static DECLARE_COMPLETION(finished);
static unsigned int checks, failure_line;
static int result, executor_pid, origin_pid;
static unsigned long executor_stack, origin_source_stack;
static u64 source_fetches;

static int source_fetch(void *context, unsigned long address, void *out, unsigned int size)
{
	struct fixture *f = context;

	if (size != 1 || address < CODE || address - CODE >= f->code_size)
		return -ENODATA;
	++f->fetches;
	++source_fetches;
	f->max_fetch = max(f->max_fetch, address);
	memcpy(out, f->code + address - CODE, size);
	return 0;
}

static int source_read(void *context, unsigned long address, void *out, unsigned int size)
{
	struct fixture *f = context;

	if (f->fail_read || address < DATA || address - DATA > sizeof(f->memory) ||
	    size > sizeof(f->memory) - (address - DATA)) return -EFAULT;
	++f->reads;
	memcpy(out, (u8 *)f->memory + address - DATA, size);
	return 0;
}

static int source_write(void *context, unsigned long address, const void *in, unsigned int size)
{
	struct fixture *f = context;

	if (f->fail_write || address < DATA || address - DATA > sizeof(f->memory) ||
	    size > sizeof(f->memory) - (address - DATA)) return -EFAULT;
	++f->writes;
	memcpy((u8 *)f->memory + address - DATA, in, size);
	return 0;
}

static const struct kd_reached_ops operations = {
	.fetch = source_fetch, .read = source_read, .write = source_write,
};

static int source_atomic(void *context, unsigned long address, unsigned int width,
	enum kd_reached_atomic_op operation, u64 input, u64 accumulator,
	unsigned long input_flags, u64 *old, unsigned long *output_flags)
{
	struct fixture *f = context;
	int status;

	++f->atomic_attempts;
	f->atomic_operation = operation;
	f->atomic_input = input;
	if (f->fail_atomic || address < DATA || address - DATA > sizeof(f->memory) ||
	    width > sizeof(f->memory) - (address - DATA)) return -EFAULT;
	status = kd_reached_atomic_apply((void *)address, width, operation, input,
		accumulator, input_flags, old, output_flags);
	if (!status) ++f->atomics;
	return status;
}

static const struct kd_reached_ops atomic_operations = {
	.fetch = source_fetch, .read = source_read, .write = source_write,
	.atomic = source_atomic,
};

static void prepare(struct fixture *f, const u8 *code, unsigned int length)
{
	/* Test storage may be cleared; the production engine never clears or copies
	 * a continuation packet. This fixture has no live packet at preparation. */
	memset(f, 0, sizeof(*f));
	memcpy(f->code, code, length);
	f->code_size = length;
	f->regs.ip = CODE;
	f->regs.sp = DATA + 128;
	f->regs.bp = DATA + 160;
	f->regs.flags = 0x202;
	f->state.ops = &operations;
	f->state.context = f;
	kd_reached_begin(&f->state, &f->regs, KD_PACKET_FULL, 100);
}

static int entry_test(struct fixture *f)
{
	static const u8 nop[] = { 0x90 };
	unsigned long ip, sp, bp;

	prepare(f, nop, sizeof(nop));
	ip = f->regs.ip; sp = f->regs.sp; bp = f->regs.bp;
	f->regs.ax = ~0UL; f->regs.r15 = ~0UL; f->regs.di = ~0UL;
	f->regs.flags = ~0UL;
	CHECK(!kd_reached_begin(&f->state, &f->regs, KD_PACKET_MINIMAL, 7));
	CHECK(f->regs.ip == ip && f->regs.sp == sp && f->regs.bp == bp);
	CHECK(!f->regs.ax && !f->regs.r15 && !f->regs.di && f->regs.flags == 2);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->state.budget == 6);
	f->state.packet_state = KD_PACKET_MINIMAL;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_PACKET);
	return 0;
}

/* Read Native arithmetic flags immediately after the actual width operation.
 * Carry input is loaded independently of C compiler flags. */
#define NATIVE_WIDTH(insn, width, a, b, c, flags) do { \
	if ((width) == 1) asm volatile("btq $0,%[carry]; " insn "b %b[src],%b[dst]; pushfq; popq %[out]" \
		: [dst] "+q"(a), [out] "=r"(flags) : [src] "q"(b), [carry] "r"(c) : "cc", "memory"); \
	else if ((width) == 2) asm volatile("btq $0,%[carry]; " insn "w %w[src],%w[dst]; pushfq; popq %[out]" \
		: [dst] "+r"(a), [out] "=r"(flags) : [src] "r"(b), [carry] "r"(c) : "cc", "memory"); \
	else if ((width) == 4) asm volatile("btq $0,%[carry]; " insn "l %k[src],%k[dst]; pushfq; popq %[out]" \
		: [dst] "+r"(a), [out] "=r"(flags) : [src] "r"(b), [carry] "r"(c) : "cc", "memory"); \
	else asm volatile("btq $0,%[carry]; " insn "q %[src],%[dst]; pushfq; popq %[out]" \
		: [dst] "+r"(a), [out] "=r"(flags) : [src] "r"(b), [carry] "r"(c) : "cc", "memory"); \
} while (0)

static void native_arithmetic(unsigned int operation, unsigned int width,
			      u64 *value, u64 b, u64 carry, unsigned long *flags)
{
	u64 a = *value;
	unsigned long f;

	switch (operation) {
	case 0: NATIVE_WIDTH("add", width, a, b, carry, f); break;
	case 1: NATIVE_WIDTH("or", width, a, b, carry, f); break;
	case 2: NATIVE_WIDTH("adc", width, a, b, carry, f); break;
	case 3: NATIVE_WIDTH("sbb", width, a, b, carry, f); break;
	case 4: NATIVE_WIDTH("and", width, a, b, carry, f); break;
	case 5: NATIVE_WIDTH("sub", width, a, b, carry, f); break;
	case 6: NATIVE_WIDTH("xor", width, a, b, carry, f); break;
	default: NATIVE_WIDTH("cmp", width, a, b, carry, f); break;
	}
	*value = a;
	*flags = f;
}

static int arithmetic_test(struct fixture *f)
{
	static const u64 values[] = {
		0, 1, 0x7f, 0x80, 0xff, 0x7fff, 0x8000, 0xffff,
		0x7fffffff, 0x80000000, 0xffffffff,
		0x7fffffffffffffffULL, 0x8000000000000000ULL, ~0ULL,
	};
	u8 code[3];
	unsigned int width, operation, i, j, carry, length;
	u64 value, other;
	unsigned long native_flags, mask;

	for (width = 1; width <= 8; width *= 2)
	for (operation = 0; operation < 8; ++operation)
	for (i = 0; i < ARRAY_SIZE(values); ++i)
	for (j = 0; j < ARRAY_SIZE(values); ++j)
	for (carry = 0; carry < 2; ++carry) {
		length = 0;
		if (width == 8) code[length++] = 0x48;
		if (width == 2) code[length++] = 0x66;
		code[length++] = operation * 8 + (width == 1 ? 0 : 1);
		code[length++] = 0xd8; /* source BX, destination AX */
		prepare(f, code, length);
		f->regs.ax = value = values[i];
		f->regs.bx = other = values[j];
		f->regs.flags |= carry;
		native_arithmetic(operation, width, &value, other, carry, &native_flags);
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(f->regs.ax == value);
		mask = KD_REG_ARITHMETIC_FLAGS;
		if (operation == 1 || operation == 4 || operation == 6) mask &= ~0x10UL;
		if ((f->regs.flags ^ native_flags) & mask) {
			pr_err("KD_REACHED_TEST arithmetic op=%u width=%u a=%llx b=%llx carry=%u got=%lx native=%lx\n",
				operation, width, values[i], values[j], carry, f->regs.flags, native_flags);
			CHECK(false);
		}
		CHECK((f->regs.flags & ~KD_REG_ARITHMETIC_FLAGS) == 0x202);
	}
	return 0;
}

static int edge_test(struct fixture *f)
{
	static const u8 jcc[] = { 0x75, 0x7f };
	static const u8 call_rsp[] = { 0xff, 0x14, 0x24 };
	static const u8 call_rsp_minus[] = { 0xff, 0x54, 0x24, 0xf8 };
	static const u8 direct_call[] = { 0xe8, 0x12, 0, 0, 0 };
	static const u8 jump[] = { 0xeb, 0x7f };
	static const u8 ret[] = { 0xc3 };
	static const u8 ret_adjust[] = { 0xc2, 0x10, 0 };
	u64 old;

	prepare(f, jcc, sizeof(jcc));
	f->regs.flags |= 0x40;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 2 && f->fetches == 2 && f->max_fetch == CODE + 1);
	prepare(f, jcc, sizeof(jcc));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 2 + 127 && f->fetches == 2);
	prepare(f, call_rsp, sizeof(call_rsp));
	f->memory[16] = CODE + 33;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 33 && f->regs.sp == DATA + 120);
	CHECK(f->memory[15] == CODE + 3 && f->memory[16] == CODE + 33);
	/* The target itself occupies the slot overwritten by the CALL push. */
	prepare(f, call_rsp_minus, sizeof(call_rsp_minus));
	f->memory[15] = CODE + 34;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 34 && f->memory[15] == CODE + 4);
	prepare(f, direct_call, sizeof(direct_call));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 5 + 18 && f->memory[15] == CODE + 5);
	prepare(f, jump, sizeof(jump));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 129 && f->regs.sp == DATA + 128 && !f->writes);
	/* No JIT CALL preceded this inherited source return word. */
	prepare(f, ret, sizeof(ret));
	f->memory[16] = CODE + 57;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 57 && f->regs.sp == DATA + 136 && !f->writes);
	prepare(f, ret_adjust, sizeof(ret_adjust));
	f->memory[16] = CODE + 58;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 58 && f->regs.sp == DATA + 152);
	prepare(f, call_rsp_minus, sizeof(call_rsp_minus));
	f->memory[15] = old = CODE + 49;
	f->fail_write = true;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(f->regs.ip == CODE && f->regs.sp == DATA + 128 && f->memory[15] == old);
	return 0;
}

static int scalar_test(struct fixture *f)
{
	static const u8 scalar[] = {
		0x48, 0x8d, 0x44, 0x8b, 0xf8, /* lea -8(RBX,RCX,4),RAX */
		0x48, 0x89, 0x10, /* mov RDX,(RAX) */
		0x0f, 0xb6, 0x60, 0x01, /* movzx byte 1(RAX),ESP */
	};
	static const u8 rip[] = { 0x48, 0x8d, 0x05, 0x10, 0, 0, 0 };
	static const u8 ah[] = { 0xb4, 0x5a };
	static const u8 spl[] = { 0x40, 0xb4, 0x5a };
	static const u8 cmov[] = { 0x0f, 0x44, 0xc3 };
	static const u8 sx[] = { 0x48, 0x0f, 0xbe, 0xe0 };
	static const u8 push_pop[] = { 0x54, 0x5c };
	static const u8 leave[] = { 0xc9 };
	static const u8 instructions[] = { 0xf3, 0x90, 0x0f, 0xae, 0xe8,
		0x0f, 0xae, 0xf0, 0x0f, 0xae, 0xf8, 0xf3, 0x0f, 0x1e, 0xfa };

	prepare(f, scalar, sizeof(scalar));
	f->regs.bx = DATA + 8; f->regs.cx = 4; f->regs.dx = 0x1122334455667788;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->regs.ax == DATA + 16);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->memory[2] == f->regs.dx);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->regs.sp == 0x77);
	prepare(f, rip, sizeof(rip));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->regs.ax == CODE + 23);
	prepare(f, ah, sizeof(ah)); f->regs.ax = 0x11223344;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->regs.ax == 0x11225a44);
	prepare(f, spl, sizeof(spl));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT &&
	      f->regs.sp == (((DATA + 128) & ~0xffUL) | 0x5a));
	prepare(f, cmov, sizeof(cmov)); f->regs.ax = ~0UL; f->regs.bx = 12;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->regs.ax == 0xffffffff);
	prepare(f, sx, sizeof(sx)); f->regs.ax = 0x80;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->regs.sp == ~0x7fUL);
	prepare(f, push_pop, sizeof(push_pop));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->memory[15] == DATA + 128);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->regs.sp == DATA + 128);
	prepare(f, leave, sizeof(leave)); f->memory[20] = 0x1234;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK(f->regs.sp == DATA + 168 && f->regs.bp == 0x1234);
	prepare(f, instructions, sizeof(instructions));
	CHECK(kd_reached_run(&f->state, 5) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + sizeof(instructions) && f->state.budget == 95);
	return 0;
}

static int stop_test(struct fixture *f)
{
	static const u8 lock[] = { 0xf0, 0x48, 0x01, 0x18 };
	static const u8 atomic[] = { 0x48, 0x87, 0x18 };
	static const u8 truncated[] = { 0x48, 0xb8, 1 };
	static const u8 nop[] = { 0x90, 0x90, 0x90 };
	struct kd_regs before;
	u8 bounded[KD_REACHED_SEGMENT_MAX];
	enum kd_reached_result step_result;
	unsigned int prior_preempt;

	prepare(f, lock, sizeof(lock)); f->regs.ax = DATA;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes);
	prepare(f, atomic, sizeof(atomic)); f->regs.ax = DATA;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes);
	prepare(f, truncated, sizeof(truncated));
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_SOURCE);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && f->fetches == 3);
	prepare(f, nop, sizeof(nop)); f->state.budget = 2;
	CHECK(kd_reached_run(&f->state, 1) == KD_REACHED_EDGE && f->regs.ip == CODE + 1);
	CHECK(f->state.budget == 1);
	CHECK(kd_reached_run(&f->state, 1) == KD_REACHED_EDGE && f->regs.ip == CODE + 2);
	CHECK(!f->state.budget);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_BUDGET && f->fetches == 2);
	memset(bounded, 0x90, sizeof(bounded));
	prepare(f, bounded, sizeof(bounded));
	prior_preempt = preempt_count();
	preempt_disable();
	step_result = kd_reached_run(&f->state, ~0U);
	preempt_enable();
	CHECK(step_result == KD_REACHED_EDGE && preempt_count() == prior_preempt);
	CHECK(f->regs.ip == CODE + KD_REACHED_SEGMENT_MAX);
	CHECK(f->fetches == KD_REACHED_SEGMENT_MAX && f->state.budget == 100 - KD_REACHED_SEGMENT_MAX);
	CHECK(kd_reached_run(&f->state, 0) == KD_REACHED_PACKET);
	return 0;
}

static int supplementation_test(struct fixture *f)
{
	static const u8 entry[] = { 0x48, 0xff, 0xc0, 0xeb, 0x0b };
	static const u8 target[] = { 0x48, 0xc7, 0xc3, 0x77, 0, 0, 0, 0xc3 };
	static const u8 truncated[] = { 0x48, 0xb8, 1 };
	static const u8 rest[] = { 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88 };
	struct kd_regs reached;
	u64 budget;

	/* Commit the prefix once. The selected target has no available bytes yet,
	 * and no untouched target is explored to prepare the initial segment. */
	prepare(f, entry, sizeof(entry));
	f->regs.ax = 10;
	f->memory[16] = CODE + 40;
	CHECK(kd_reached_run(&f->state, 64) == KD_REACHED_EDGE);
	CHECK(f->regs.ax == 11 && f->regs.ip == CODE + 16 && f->state.budget == 98);
	CHECK(f->fetches == sizeof(entry) && f->max_fetch == CODE + sizeof(entry) - 1);
	reached = f->regs; budget = f->state.budget;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_SOURCE);
	CHECK(!memcmp(&reached, &f->regs, sizeof(reached)) && f->state.budget == budget);
	/* Supplement only the reached code. The unavailable gap is never decoded.
	 * Keep the same state, source stack, E task, budget and committed prefix. */
	memcpy(f->code + 16, target, sizeof(target));
	f->code_size = 16 + sizeof(target);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK(f->regs.bx == 0x77 && f->regs.ax == 11 && f->regs.ip == CODE + 23);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 40 && f->regs.sp == DATA + 136 && f->regs.ax == 11);
	CHECK(f->state.budget == 96 && f->fetches == sizeof(entry) + sizeof(target));
	/* A partially available instruction is retried without any earlier source
	 * effect being repeated or any public acquisition result being rewritten. */
	prepare(f, truncated, sizeof(truncated));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_SOURCE && f->state.budget == 100);
	CHECK(f->regs.ip == CODE && !f->regs.ax);
	memcpy(f->code + sizeof(truncated), rest, sizeof(rest));
	f->code_size += sizeof(rest);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK(f->regs.ip == CODE + 10 && f->regs.ax == 0x8877665544332201ULL);
	CHECK(f->state.budget == 99);
	return 0;
}

#define ORACLE_ATOMIC_BINARY(insn, suffix, part) \
	asm volatile("pushq %[flags]; popfq; " insn suffix " %" part "[source],%[memory]; pushfq; popq %[output]" \
		: [source] "+r"(source), [memory] "+m"(*memory), [output] "=r"(output) \
		: [flags] "r"(flags) : "cc", "memory")
#define ORACLE_ATOMIC_UNARY(insn, suffix) \
	asm volatile("pushq %[flags]; popfq; " insn suffix " %[memory]; pushfq; popq %[output]" \
		: [memory] "+m"(*memory), [output] "=r"(output) \
		: [flags] "r"(flags) : "cc", "memory")
#define ORACLE_ATOMIC_CMP(suffix, part) \
	asm volatile("pushq %[flags]; popfq; lock cmpxchg" suffix " %" part "[source],%[memory]; pushfq; popq %[output]" \
		: [accumulator] "+a"(accumulator), [memory] "+m"(*memory), [output] "=r"(output) \
		: [source] "r"(source), [flags] "r"(flags) : "cc", "memory")
#define ORACLE_ATOMIC_WIDTH(suffix, part) do { \
	switch (operation) { \
	case KD_REACHED_ATOMIC_ADD: ORACLE_ATOMIC_BINARY("lock add", suffix, part); break; \
	case KD_REACHED_ATOMIC_SUB: ORACLE_ATOMIC_BINARY("lock sub", suffix, part); break; \
	case KD_REACHED_ATOMIC_AND: ORACLE_ATOMIC_BINARY("lock and", suffix, part); break; \
	case KD_REACHED_ATOMIC_OR: ORACLE_ATOMIC_BINARY("lock or", suffix, part); break; \
	case KD_REACHED_ATOMIC_XOR: ORACLE_ATOMIC_BINARY("lock xor", suffix, part); break; \
	case KD_REACHED_ATOMIC_INC: ORACLE_ATOMIC_UNARY("lock inc", suffix); break; \
	case KD_REACHED_ATOMIC_DEC: ORACLE_ATOMIC_UNARY("lock dec", suffix); break; \
	case KD_REACHED_ATOMIC_XADD: ORACLE_ATOMIC_BINARY("lock xadd", suffix, part); break; \
	case KD_REACHED_ATOMIC_XCHG: ORACLE_ATOMIC_BINARY("xchg", suffix, part); break; \
	default: ORACLE_ATOMIC_CMP(suffix, part); break; \
	} \
} while (0)

static void native_atomic(unsigned int width, enum kd_reached_atomic_op operation,
	u64 *memory, u64 *source_value, u64 *accumulator_value,
	unsigned long input_flags, unsigned long *result_flags)
{
	u64 source = *source_value, accumulator = *accumulator_value;
	unsigned long flags, output;

	asm volatile("pushfq; popq %0" : "=r"(flags) : : "memory");
	flags = (flags & ~KD_REG_ARITHMETIC_FLAGS) | (input_flags & KD_REG_ARITHMETIC_FLAGS);
	switch (width) {
	case 1: ORACLE_ATOMIC_WIDTH("b", "b"); break;
	case 2: ORACLE_ATOMIC_WIDTH("w", "w"); break;
	case 4: ORACLE_ATOMIC_WIDTH("l", "k"); break;
	default: ORACLE_ATOMIC_WIDTH("q", ""); break;
	}
	*source_value = source;
	*accumulator_value = accumulator;
	*result_flags = output;
}

static int atomic_test(struct fixture *f)
{
	static const u64 values[] = { 0, 1, 0x80, 0x80000000, ~0ULL };
	unsigned int width, operation, i, j, match, length;
	u8 code[6];
	u64 memory, source, accumulator;
	unsigned long flags, mask;
	struct kd_regs before;

	for (width = 1; width <= 8; width *= 2)
	for (operation = KD_REACHED_ATOMIC_ADD; operation <= KD_REACHED_ATOMIC_CMPXCHG; ++operation)
	for (i = 0; i < ARRAY_SIZE(values); ++i)
	for (j = 0; j < ARRAY_SIZE(values); ++j)
	for (match = 0; match < 2; ++match) {
		length = 0;
		if (operation != KD_REACHED_ATOMIC_XCHG) code[length++] = 0xf0;
		if (width == 2) code[length++] = 0x66;
		if (width == 8) code[length++] = 0x48;
		if (operation == KD_REACHED_ATOMIC_XADD || operation == KD_REACHED_ATOMIC_CMPXCHG) {
			code[length++] = 0x0f;
			code[length++] = (operation == KD_REACHED_ATOMIC_XADD ? 0xc0 : 0xb0) + (width != 1);
		} else if (operation == KD_REACHED_ATOMIC_INC || operation == KD_REACHED_ATOMIC_DEC) {
			code[length++] = width == 1 ? 0xfe : 0xff;
		} else if (operation == KD_REACHED_ATOMIC_XCHG) {
			code[length++] = width == 1 ? 0x86 : 0x87;
		} else {
			code[length++] = (operation == KD_REACHED_ATOMIC_SUB ? 0x28 : 0) + (width != 1);
		}
		code[length++] = operation == KD_REACHED_ATOMIC_INC ? 0x07 :
			operation == KD_REACHED_ATOMIC_DEC ? 0x0f : 0x1f; /* (RDI), source BX */
		prepare(f, code, length);
		f->state.ops = &atomic_operations;
		f->regs.di = DATA;
		f->regs.bx = source = values[j];
		f->memory[0] = memory = values[i];
		mask = width == 8 ? ~0UL : (1UL << (width * 8)) - 1;
		f->regs.ax = accumulator = (values[i] & mask) ^ (match ? 0 : 1);
		if (width < 8) f->regs.ax = accumulator |= 0xabcdefff00000000ULL & ~mask;
		f->regs.flags = 0x202 | (match ? KD_REG_ARITHMETIC_FLAGS : 0);
		native_atomic(width, operation, &memory, &source, &accumulator, f->regs.flags, &flags);
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(f->memory[0] == memory && f->regs.ax == accumulator && f->regs.bx == source);
		CHECK(!((f->regs.flags ^ flags) & KD_REG_ARITHMETIC_FLAGS));
		CHECK(f->atomics == 1 && !f->reads && !f->writes);
	}
	/* Failed callback is an unexecuted RMW, with the whole packet intact. */
	prepare(f, (u8[]){ 0xf0, 0x0f, 0xc1, 0x1f }, 4);
	f->state.ops = &atomic_operations;
	f->regs.di = DATA;
	f->fail_atomic = true;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->atomics && f->state.budget == 100);
	return 0;
}

#define ORACLE_SHIFT(insn, suffix, part) \
	asm volatile("pushq %[flags]; popfq; " insn suffix " %%cl,%" part "[value]; pushfq; popq %[output]" \
		: [value] "+r"(value), [output] "=r"(output) \
		: "c"(count), [flags] "r"(flags) : "cc", "memory")
#define ORACLE_SHIFT_WIDTH(suffix, part) do { \
	switch (group) { \
	case 0: ORACLE_SHIFT("rol", suffix, part); break; \
	case 1: ORACLE_SHIFT("ror", suffix, part); break; \
	case 2: ORACLE_SHIFT("rcl", suffix, part); break; \
	case 3: ORACLE_SHIFT("rcr", suffix, part); break; \
	case 4: ORACLE_SHIFT("shl", suffix, part); break; \
	case 5: ORACLE_SHIFT("shr", suffix, part); break; \
	default: ORACLE_SHIFT("sar", suffix, part); break; \
	} \
} while (0)

static u64 native_shift(unsigned int width, unsigned int group, u64 value,
	unsigned int count, unsigned long input_flags, unsigned long *result_flags)
{
	unsigned long flags, output;

	asm volatile("pushfq; popq %0" : "=r"(flags) : : "memory");
	flags = (flags & ~KD_REG_ARITHMETIC_FLAGS) | (input_flags & KD_REG_ARITHMETIC_FLAGS);
	switch (width) {
	case 1: ORACLE_SHIFT_WIDTH("b", "b"); break;
	case 2: ORACLE_SHIFT_WIDTH("w", "w"); break;
	case 4: ORACLE_SHIFT_WIDTH("l", "k"); break;
	default: ORACLE_SHIFT_WIDTH("q", ""); break;
	}
	*result_flags = output;
	return value;
}

static int shift_multiply_test(struct fixture *f)
{
	static const u64 values[] = { 0, 1, 0x80, 0x80000000, ~0ULL };
	static const unsigned int counts[] = { 0, 1, 7, 8, 16, 31, 32, 63, 64, 65 };
	u8 code[5];
	unsigned int width, group, i, j, length;
	u64 expected, right;
	unsigned long flags;

	for (width = 1; width <= 8; width *= 2)
	for (group = 0; group < 8; ++group)
	for (i = 0; i < ARRAY_SIZE(values); ++i)
	for (j = 0; j < ARRAY_SIZE(counts); ++j) {
		if (group == 6) continue;
		length = 0;
		if (width == 2) code[length++] = 0x66;
		if (width == 8) code[length++] = 0x48;
		code[length++] = width == 1 ? 0xd2 : 0xd3;
		code[length++] = 0xc3 | (group << 3); /* source countCL, destinationBX */
		prepare(f, code, length);
		f->regs.bx = values[i];
		f->regs.cx = counts[j];
		f->regs.flags |= KD_REG_ARITHMETIC_FLAGS;
		expected = native_shift(width, group, values[i], counts[j], f->regs.flags, &flags);
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(f->regs.bx == expected);
		CHECK(!((f->regs.flags ^ flags) & KD_REG_ARITHMETIC_FLAGS));
	}
	for (width = 2; width <= 8; width *= 2)
	for (i = 0; i < ARRAY_SIZE(values); ++i)
	for (j = 0; j < ARRAY_SIZE(values); ++j) {
		length = 0;
		if (width == 2) code[length++] = 0x66;
		if (width == 8) code[length++] = 0x48;
		code[length++] = 0x0f; code[length++] = 0xaf; code[length++] = 0xd8;
		prepare(f, code, length);
		f->regs.bx = expected = values[i];
		f->regs.ax = right = values[j];
		if (width == 2)
			asm volatile("imulw %w[right],%w[value]; pushfq; popq %[flags]"
				: [value] "+r"(expected), [flags] "=r"(flags) : [right] "r"(right) : "cc", "memory");
		else if (width == 4)
			asm volatile("imull %k[right],%k[value]; pushfq; popq %[flags]"
				: [value] "+r"(expected), [flags] "=r"(flags) : [right] "r"(right) : "cc", "memory");
		else
			asm volatile("imulq %[right],%[value]; pushfq; popq %[flags]"
				: [value] "+r"(expected), [flags] "=r"(flags) : [right] "r"(right) : "cc", "memory");
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->regs.bx == expected);
		CHECK(!((f->regs.flags ^ flags) & 0x801));
	}
	prepare(f, (u8[]){0x48, 0x6b, 0xc3, 0xf9}, 4);
	f->regs.bx = 9;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && f->regs.ax == (u64)-63);
	prepare(f, (u8[]){0xf9, 0x9f, 0xf5, 0x9e, 0xf8}, 5);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && (f->regs.flags & 1));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && ((f->regs.ax >> 8) & 0xff) == 3);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && !(f->regs.flags & 1));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && (f->regs.flags & 1));
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT && !(f->regs.flags & 1));
	return 0;
}

#define ORACLE_BIT(insn, suffix, part) \
	asm volatile("pushq %[flags]; popfq; " insn suffix " %" part "[index],%" part "[value]; pushfq; popq %[output]" \
		: [value] "+r"(value), [output] "=r"(output) \
		: [index] "r"(index), [flags] "r"(flags) : "cc", "memory")
#define ORACLE_BIT_WIDTH(suffix, part) do { \
	switch (operation) { \
	case 0: ORACLE_BIT("bt", suffix, part); break; \
	case 1: ORACLE_BIT("bts", suffix, part); break; \
	case 2: ORACLE_BIT("btr", suffix, part); break; \
	default: ORACLE_BIT("btc", suffix, part); break; \
	} \
} while (0)

static u64 native_bit(unsigned int width, unsigned int operation, u64 value,
	u64 index, unsigned long input_flags, unsigned long *result_flags)
{
	unsigned long flags, output;

	asm volatile("pushfq; popq %0" : "=r"(flags) : : "memory");
	flags = (flags & ~KD_REG_ARITHMETIC_FLAGS) | (input_flags & KD_REG_ARITHMETIC_FLAGS);
	switch (width) {
	case 2: ORACLE_BIT_WIDTH("w", "w"); break;
	case 4: ORACLE_BIT_WIDTH("l", "k"); break;
	default: ORACLE_BIT_WIDTH("q", ""); break;
	}
	*result_flags = output;
	return value;
}

static int bit_test(struct fixture *f)
{
	static const u64 values[] = { 0, 1, 0x80, 0x80000000, 1ULL << 63, ~0ULL };
	static const u64 indices[] = { 0, 1, 7, 15, 16, 31, 32, 63, 64, 127, 255, ~0ULL };
	unsigned int width, operation, i, j, form, length;
	u8 code[6];
	u64 expected, index;
	unsigned long flags;
	struct kd_regs before;

	/* Exact reached instruction from the inline preemption-count fixture:
	 * BTR $31,RDX clears its sampled need-resched bit before comparison. */
	prepare(f, (u8[]){ 0x48, 0x0f, 0xba, 0xf2, 0x1f }, 5);
	f->regs.dx = 0x80000001;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK(f->regs.dx == 1 && (f->regs.flags & 1) && f->regs.ip == CODE + 5);

	for (width = 2; width <= 8; width *= 2)
	for (operation = 0; operation < 4; ++operation)
	for (i = 0; i < ARRAY_SIZE(values); ++i)
	for (j = 0; j < ARRAY_SIZE(indices); ++j)
	for (form = 0; form < 2; ++form) {
		length = 0;
		if (width == 2) code[length++] = 0x66;
		if (width == 8) code[length++] = 0x48;
		code[length++] = 0x0f;
		if (form) {
			code[length++] = 0xba;
			code[length++] = 0xe3 | (operation << 3); /* destinationBX, /4..7 */
			code[length++] = (u8)indices[j];
		} else {
			code[length++] = 0xa3 + (operation << 3);
			code[length++] = 0xcb; /* indexCX, destinationBX */
		}
		prepare(f, code, length);
		f->regs.bx = values[i];
		f->regs.cx = indices[j];
		f->regs.flags |= (j & 1) ? KD_REG_ARITHMETIC_FLAGS : 0;
		index = form ? (u8)indices[j] : indices[j];
		expected = native_bit(width, operation, values[i], index, f->regs.flags, &flags);
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(f->regs.bx == expected && f->regs.cx == indices[j]);
		/* CF is the selected old bit and ZF is unchanged. Other arithmetic
		 * flags are undefined; the implementation exports actual Native flags. */
		CHECK(!((f->regs.flags ^ flags) & 0x41));
	}
	for (operation = 1; operation < 4; ++operation) {
		code[0] = 0x48; code[1] = 0x0f; code[2] = 0xba;
		code[3] = 0x20 | (operation << 3); code[4] = 63; /* memory(RAX) */
		prepare(f, code, 5);
		f->regs.ax = DATA;
		before = f->regs;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
		CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes);
	}
	prepare(f, (u8[]){ 0xf0, 0x48, 0x0f, 0xba, 0xeb, 63 }, 6);
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes);
	return 0;
}

#define ORACLE_STOS(insn) do { \
	if (repeated) \
		asm volatile("pushq %[flags]; popfq; rep " insn "; pushfq; popq %[output]; cld" \
			: "+D"(destination), "+c"(count), [output] "=r"(output) \
			: "a"(value), [flags] "r"(flags) : "cc", "memory"); \
	else \
		asm volatile("pushq %[flags]; popfq; " insn "; pushfq; popq %[output]; cld" \
			: "+D"(destination), "+c"(count), [output] "=r"(output) \
			: "a"(value), [flags] "r"(flags) : "cc", "memory"); \
} while (0)

static void native_stos(unsigned int width, bool repeated,
	unsigned long *destination_io, unsigned long *count_io, u64 value,
	unsigned long input_flags, unsigned long *result_flags)
{
	unsigned long destination = *destination_io, count = *count_io;
	unsigned long flags, output, irq_flags;

	/* The oracle installs DF only inside the single asm block. No C or
	 * ordinary interrupt handler runs before its final CLD. Source IF and
	 * other execution state are never copied onto the executor CPU. */
	local_irq_save(irq_flags);
	asm volatile("pushfq; popq %0" : "=r"(flags) : : "memory");
	flags = (flags & ~(KD_REG_ARITHMETIC_FLAGS | 0x400UL)) |
		(input_flags & (KD_REG_ARITHMETIC_FLAGS | 0x400UL));
	switch (width) {
	case 1: ORACLE_STOS("stosb"); break;
	case 2: ORACLE_STOS("stosw"); break;
	case 4: ORACLE_STOS("stosl"); break;
	default: ORACLE_STOS("stosq"); break;
	}
	local_irq_restore(irq_flags);
	*destination_io = destination;
	*count_io = count;
	*result_flags = output;
}

static int stos_test(struct fixture *f)
{
	static const unsigned int counts[] = { 0, 1, 2, 5, 8, 31 };
	static const u64 value = 0xfedcba9876543210ULL;
	u64 expected[ARRAY_SIZE(f->memory)];
	struct kd_regs before;
	unsigned int width, repeated, direction, i, length, stores, offset, steps;
	unsigned long destination, count, flags, input_flags;
	u8 code[4];

	for (width = 1; width <= 8; width *= 2)
	for (repeated = 0; repeated < 2; ++repeated)
	for (direction = 0; direction < 2; ++direction)
	for (i = 0; i < ARRAY_SIZE(counts); ++i) {
		length = 0;
		if (repeated) code[length++] = 0xf3;
		if (width == 2) code[length++] = 0x66;
		if (width == 8) code[length++] = 0x48;
		code[length++] = width == 1 ? 0xaa : 0xab;
		prepare(f, code, length);
		memset(f->memory, 0xa5, sizeof(f->memory));
		memset(expected, 0xa5, sizeof(expected));
		stores = repeated ? counts[i] : 1;
		steps = stores ? stores : 1;
		offset = direction && stores ? (stores - 1) * width : 0;
		f->regs.di = DATA + offset;
		f->regs.cx = counts[i];
		f->regs.ax = value;
		f->regs.flags = input_flags = 0x202 | KD_REG_ARITHMETIC_FLAGS |
			(direction ? 0x400UL : 0);
		destination = (unsigned long)expected + offset;
		count = counts[i];
		native_stos(width, repeated, &destination, &count, value, input_flags, &flags);
		CHECK(kd_reached_run(&f->state, steps) == KD_REACHED_EDGE);
		CHECK(f->regs.ip == CODE + length && f->state.budget == 100 - steps);
		CHECK(!memcmp(f->memory, expected, sizeof(expected)));
		CHECK(f->regs.di - DATA == destination - (unsigned long)expected);
		CHECK(f->regs.cx == count && f->regs.ax == value);
		CHECK(f->regs.flags == input_flags &&
			!((f->regs.flags ^ flags) & (KD_REG_ARITHMETIC_FLAGS | 0x400UL)));
		CHECK(f->writes == stores && !f->reads && !f->atomics);
	}
	/* An empty REP never consults even an invalid destination. */
	prepare(f, (u8[]){ 0xf3, 0x48, 0xab }, 3);
	f->regs.di = ~0UL;
	f->fail_write = true;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK(f->regs.di == ~0UL && !f->regs.cx && !f->writes && f->regs.ip == CODE + 3);
	/* A large count cannot extend the 64-step segment. Resumption starts at
	 * exactly the first unexecuted element and consumes the remaining count. */
	prepare(f, (u8[]){ 0xf3, 0xaa }, 2);
	f->regs.di = DATA; f->regs.cx = 80; f->regs.ax = value;
	CHECK(kd_reached_run(&f->state, ~0U) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE && f->regs.di == DATA + 64 && f->regs.cx == 16);
	CHECK(f->writes == 64 && f->state.budget == 36);
	((u8 *)f->memory)[0] = 0x6b;
	CHECK(kd_reached_run(&f->state, 16) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 2 && f->regs.di == DATA + 80 && !f->regs.cx);
	CHECK(f->writes == 80 && f->state.budget == 20 && ((u8 *)f->memory)[0] == 0x6b);
	/* A later store failure retains the earlier prefix. Neither callback
	 * failure nor the retry may replay already completed source stores. */
	prepare(f, (u8[]){ 0xf3, 0x48, 0xab }, 3);
	f->regs.di = DATA; f->regs.cx = 8; f->regs.ax = value;
	CHECK(kd_reached_run(&f->state, 3) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE && f->regs.di == DATA + 24 && f->regs.cx == 5);
	f->memory[0] = 0x76543210;
	f->fail_write = true;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && f->writes == 3 && f->state.budget == 97);
	CHECK(f->memory[0] == 0x76543210 && f->memory[1] == value && f->memory[2] == value);
	f->fail_write = false;
	CHECK(kd_reached_run(&f->state, 5) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 3 && f->regs.di == DATA + 64 && !f->regs.cx);
	CHECK(f->writes == 8 && f->state.budget == 92 && f->memory[0] == 0x76543210);
	for (i = 1; i < 8; ++i) CHECK(f->memory[i] == value);
	/* LOCK and address-size string variants retain explicit no-effect refusal. */
	prepare(f, (u8[]){ 0xf0, 0xf3, 0x48, 0xab }, 4);
	f->regs.di = DATA; f->regs.cx = 2;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->writes);
	prepare(f, (u8[]){ 0x67, 0xf3, 0x48, 0xab }, 4);
	f->regs.di = DATA; f->regs.cx = 2;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->writes);
	return 0;
}

#define ORACLE_MOVS(insn) do { \
	if (repeated) \
		asm volatile("pushq %[flags]; popfq; rep " insn "; pushfq; popq %[output]; cld" \
			: "+S"(source), "+D"(destination), "+c"(count), [output] "=r"(output) \
			: [flags] "r"(flags) : "cc", "memory"); \
	else \
		asm volatile("pushq %[flags]; popfq; " insn "; pushfq; popq %[output]; cld" \
			: "+S"(source), "+D"(destination), "+c"(count), [output] "=r"(output) \
			: [flags] "r"(flags) : "cc", "memory"); \
} while (0)

static void native_movs(unsigned int width, bool repeated, unsigned long *source_io,
	unsigned long *destination_io, unsigned long *count_io,
	unsigned long input_flags, unsigned long *result_flags)
{
	unsigned long source = *source_io, destination = *destination_io, count = *count_io;
	unsigned long flags, output, irq_flags;

	/* As in the STOS oracle, DF is present only inside one asm block with
	 * ordinary interrupts disabled, and CLD precedes every return to C. */
	local_irq_save(irq_flags);
	asm volatile("pushfq; popq %0" : "=r"(flags) : : "memory");
	flags = (flags & ~(KD_REG_ARITHMETIC_FLAGS | 0x400UL)) |
		(input_flags & (KD_REG_ARITHMETIC_FLAGS | 0x400UL));
	switch (width) {
	case 1: ORACLE_MOVS("movsb"); break;
	case 2: ORACLE_MOVS("movsw"); break;
	case 4: ORACLE_MOVS("movsl"); break;
	default: ORACLE_MOVS("movsq"); break;
	}
	local_irq_restore(irq_flags);
	*source_io = source;
	*destination_io = destination;
	*count_io = count;
	*result_flags = output;
}

static int movs_test(struct fixture *f)
{
	static const unsigned int counts[] = { 0, 1, 2, 5, 8 };
	static const u64 accumulator = 0xfedcba9876543210ULL;
	u64 expected[ARRAY_SIZE(f->memory)];
	struct kd_regs before;
	unsigned int width, repeated, direction, layout, i, j, length, elements, steps;
	unsigned int source_offset, destination_offset, tail;
	unsigned long source, destination, count, flags, input_flags;
	u8 code[4];

	for (width = 1; width <= 8; width *= 2)
	for (repeated = 0; repeated < 2; ++repeated)
	for (direction = 0; direction < 2; ++direction)
	for (layout = 0; layout < 6; ++layout)
	for (i = 0; i < ARRAY_SIZE(counts); ++i) {
		length = 0;
		if (repeated) code[length++] = 0xf3;
		if (width == 2) code[length++] = 0x66;
		if (width == 8) code[length++] = 0x48;
		code[length++] = width == 1 ? 0xa4 : 0xa5;
		prepare(f, code, length);
		for (j = 0; j < sizeof(f->memory); ++j)
			((u8 *)f->memory)[j] = ((u8 *)expected)[j] = j * 37 + 11;
		source_offset = layout ? 64 : 0;
		switch (layout) {
		case 0: destination_offset = 128; break; /* disjoint */
		case 1: destination_offset = 64; break; /* identical */
		case 2: destination_offset = 65; break; /* overlap by bytes */
		case 3: destination_offset = 63; break;
		case 4: destination_offset = 64 + width; break; /* overlap by elements */
		default: destination_offset = 64 - width; break;
		}
		elements = repeated ? counts[i] : 1;
		steps = elements ? elements : 1;
		tail = direction && elements ? (elements - 1) * width : 0;
		f->regs.si = DATA + source_offset + tail;
		f->regs.di = DATA + destination_offset + tail;
		f->regs.cx = counts[i]; f->regs.ax = accumulator;
		f->regs.flags = input_flags = 0x202 | KD_REG_ARITHMETIC_FLAGS |
			(direction ? 0x400UL : 0);
		source = (unsigned long)expected + source_offset + tail;
		destination = (unsigned long)expected + destination_offset + tail;
		count = counts[i];
		native_movs(width, repeated, &source, &destination, &count, input_flags, &flags);
		CHECK(kd_reached_run(&f->state, steps) == KD_REACHED_EDGE);
		CHECK(f->regs.ip == CODE + length && f->state.budget == 100 - steps);
		CHECK(!memcmp(f->memory, expected, sizeof(expected)));
		CHECK(f->regs.si - DATA == source - (unsigned long)expected &&
			f->regs.di - DATA == destination - (unsigned long)expected);
		CHECK(f->regs.cx == count && f->regs.ax == accumulator);
		CHECK(f->regs.flags == input_flags &&
			!((f->regs.flags ^ flags) & (KD_REG_ARITHMETIC_FLAGS | 0x400UL)));
		CHECK(f->reads == elements && f->writes == elements && !f->atomics);
	}
	/* A zero-count copy cannot access either invalid source address. */
	prepare(f, (u8[]){ 0xf3, 0xa4 }, 2);
	f->regs.si = ~0UL; f->regs.di = ~0UL;
	f->fail_read = true; f->fail_write = true;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK(f->regs.si == ~0UL && f->regs.di == ~0UL && !f->regs.cx &&
		!f->reads && !f->writes && f->regs.ip == CODE + 2);
	/* The segment limit counts elements, not just decoded string opcodes. */
	prepare(f, (u8[]){ 0xf3, 0xa4 }, 2);
	for (i = 0; i < 80; ++i) ((u8 *)f->memory)[i] = i + 1;
	f->regs.si = DATA; f->regs.di = DATA + 128; f->regs.cx = 80;
	CHECK(kd_reached_run(&f->state, ~0U) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE && f->regs.si == DATA + 64 &&
		f->regs.di == DATA + 192 && f->regs.cx == 16);
	CHECK(f->reads == 64 && f->writes == 64 && f->state.budget == 36);
	((u8 *)f->memory)[128] = 0x6b;
	CHECK(kd_reached_run(&f->state, 16) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 2 && f->regs.si == DATA + 80 &&
		f->regs.di == DATA + 208 && !f->regs.cx);
	CHECK(f->reads == 80 && f->writes == 80 && f->state.budget == 20 &&
		((u8 *)f->memory)[128] == 0x6b);
	for (i = 1; i < 80; ++i) CHECK(((u8 *)f->memory)[128 + i] == i + 1);
	/* A source-read failure and a later store failure retire no element.
	 * In particular, the store failure must not advance SI after its read. */
	prepare(f, (u8[]){ 0xf3, 0x48, 0xa5 }, 3);
	for (i = 0; i < 8; ++i) f->memory[i] = 0x1111000000000000ULL + i;
	f->regs.si = DATA; f->regs.di = DATA + 128; f->regs.cx = 8;
	CHECK(kd_reached_run(&f->state, 3) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE && f->regs.si == DATA + 24 &&
		f->regs.di == DATA + 152 && f->regs.cx == 5);
	f->memory[16] = 0x76543210;
	before = f->regs;
	f->fail_read = true;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && f->reads == 3 &&
		f->writes == 3 && f->state.budget == 97);
	f->fail_read = false; f->fail_write = true;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && f->reads == 4 &&
		f->writes == 3 && f->state.budget == 97);
	CHECK(f->memory[16] == 0x76543210 && f->memory[17] == f->memory[1] &&
		f->memory[18] == f->memory[2]);
	f->fail_write = false;
	CHECK(kd_reached_run(&f->state, 5) == KD_REACHED_EDGE);
	CHECK(f->regs.ip == CODE + 3 && f->regs.si == DATA + 64 &&
		f->regs.di == DATA + 192 && !f->regs.cx);
	CHECK(f->reads == 9 && f->writes == 8 && f->state.budget == 92 &&
		f->memory[16] == 0x76543210);
	for (i = 1; i < 8; ++i) CHECK(f->memory[16 + i] == f->memory[i]);
	prepare(f, (u8[]){ 0xf0, 0xf3, 0xa4 }, 3);
	f->regs.si = DATA; f->regs.di = DATA + 128; f->regs.cx = 2;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes);
	prepare(f, (u8[]){ 0x67, 0xf3, 0xa4 }, 3);
	f->regs.si = DATA; f->regs.di = DATA + 128; f->regs.cx = 2;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes);
	return 0;
}

#define ORACLE_CS_XOR(bytes) \
	asm volatile(".byte " bytes "; pushfq; popq %[flags]" \
		: "+a"(value), [flags] "=r"(flags) : "b"(source) : "cc", "memory")

static u64 native_cs_xor(unsigned int form, u64 value, u64 source,
	unsigned long *output_flags)
{
	unsigned long flags;

	switch (form) {
	case 0: ORACLE_CS_XOR("0x66,0x2e,0x2e,0x31,0xd8"); break;
	case 1: ORACLE_CS_XOR("0x2e,0x2e,0x2e,0x31,0xd8"); break;
	case 2: ORACLE_CS_XOR("0x2e,0x2e,0x48,0x31,0xd8"); break;
	case 3: ORACLE_CS_XOR("0x48,0x2e,0x31,0xd8"); break;
	case 4: ORACLE_CS_XOR("0x2e,0x48,0x66,0x31,0xd8"); break;
	default: ORACLE_CS_XOR("0x2e,0x48,0x33,0xc3"); break;
	}
	*output_flags = flags;
	return value;
}

static int cs_padding_test(struct fixture *f)
{
	static const u64 values[] = { 0, 1, 0x80000000, 0xfedcba9876543210ULL, ~0ULL };
	static const struct {
		u8 length, bytes[10];
	} xors[] = {
		{ 5, { 0x66, 0x2e, 0x2e, 0x31, 0xd8 } },
		{ 5, { 0x2e, 0x2e, 0x2e, 0x31, 0xd8 } },
		{ 5, { 0x2e, 0x2e, 0x48, 0x31, 0xd8 } },
		/* A legacy prefix after REX cancels that earlier REX. */
		{ 4, { 0x48, 0x2e, 0x31, 0xd8 } },
		{ 5, { 0x2e, 0x48, 0x66, 0x31, 0xd8 } },
		{ 4, { 0x2e, 0x48, 0x33, 0xc3 } },
	}, nops[] = {
		{ 2, { 0x2e, 0x90 } },
		{ 5, { 0x2e, 0x2e, 0x2e, 0x2e, 0x90 } },
		{ 4, { 0x2e, 0x0f, 0x1f, 0x00 } },
		{ 6, { 0x2e, 0x0f, 0x1f, 0x44, 0x00, 0x00 } },
		{ 10, { 0x66, 0x2e, 0x0f, 0x1f, 0x84, 0x00, 0, 0, 0, 0 } },
	}, unsupported[] = {
		{ 4, { 0x2e, 0x48, 0x31, 0x18 } }, /* XOR to memory */
		{ 4, { 0x2e, 0x48, 0x33, 0x18 } }, /* XOR from memory */
		{ 4, { 0x2e, 0x48, 0x01, 0xd8 } }, /* ADD registers */
		{ 3, { 0x2e, 0xf3, 0x90 } },
		{ 4, { 0x2e, 0x0f, 0x1f, 0x08 } }, /* invalid NOP group */
		{ 4, { 0x2e, 0x0f, 0x1e, 0xfa } },
		{ 4, { 0x2e, 0xf0, 0x31, 0xd8 } },
		{ 3, { 0x2e, 0x41, 0x90 } }, /* XCHG AX,R8 */
	};
	struct kd_regs before;
	unsigned long flags, native_value;
	unsigned int form, i, j;
	u64 value;

	/* Exact live static-call return-zero instruction; this clears all of AX,
	 * including its high half, rather than silently treating CS as a NOP. */
	prepare(f, (u8[]){ 0x2e, 0x2e, 0x2e, 0x31, 0xc0 }, 5);
	f->regs.ax = ~0UL;
	native_value = ~0UL;
	asm volatile(".byte 0x2e,0x2e,0x2e,0x31,0xc0; pushfq; popq %1"
		: "+a"(native_value), "=r"(flags) : : "cc", "memory");
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK(f->regs.ax == native_value && !f->regs.ax && f->regs.ip == CODE + 5);
	CHECK(!((f->regs.flags ^ flags) & (KD_REG_ARITHMETIC_FLAGS & ~0x10UL)));
	CHECK(f->fetches == 5 && !f->reads && !f->writes);
	for (form = 0; form < ARRAY_SIZE(xors); ++form)
	for (i = 0; i < ARRAY_SIZE(values); ++i)
	for (j = 0; j < ARRAY_SIZE(values); ++j) {
		prepare(f, xors[form].bytes, xors[form].length);
		f->regs.ax = values[i]; f->regs.bx = values[j];
		f->regs.flags |= KD_REG_ARITHMETIC_FLAGS;
		value = native_cs_xor(form, values[i], values[j], &flags);
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(f->regs.ax == value && f->regs.bx == values[j]);
		CHECK(!((f->regs.flags ^ flags) & (KD_REG_ARITHMETIC_FLAGS & ~0x10UL)));
		CHECK((f->regs.flags & ~KD_REG_ARITHMETIC_FLAGS) == 0x202);
		CHECK(f->fetches == xors[form].length && f->regs.ip == CODE + xors[form].length);
		CHECK(!f->reads && !f->writes && !f->atomics);
	}
	for (i = 0; i < ARRAY_SIZE(nops); ++i) {
		prepare(f, nops[i].bytes, nops[i].length);
		f->regs.ax = ~0UL; f->regs.di = ~0UL;
		f->regs.flags |= KD_REG_ARITHMETIC_FLAGS;
		before = f->regs;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(f->regs.ip == CODE + nops[i].length && f->fetches == nops[i].length);
		before.ip = f->regs.ip;
		CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes);
	}
	/* Native long NOP accesses no data, even with a noncanonical encoded
	 * effective address (AX + AX here, under either 48- or 57-bit VA). */
	native_value = 0x4000000000000001UL;
	asm volatile("pushfq; popq %[before]; .byte 0x66,0x2e,0x0f,0x1f,0x84,0x00,0,0,0,0; pushfq; popq %[after]"
		: [before] "=&r"(value), [after] "=r"(flags) : "a"(native_value) : "memory");
	CHECK(value == flags);
	for (i = 0; i < ARRAY_SIZE(unsupported); ++i) {
		prepare(f, unsupported[i].bytes, unsupported[i].length);
		f->regs.ax = DATA; f->regs.bx = DATA;
		before = f->regs;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
		CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes && !f->atomics);
		CHECK(f->state.budget == 100);
	}
	prepare(f, (u8[]){ 0x2e, 0x0f, 0x1f, 0x84, 0x00, 0x00 }, 6);
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_SOURCE);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && f->fetches == 6 && !f->reads && !f->writes);
	prepare(f, (u8[]){ 0x2e, 0x0f }, 2);
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_SOURCE);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && f->fetches == 2 && !f->reads && !f->writes);
	return 0;
}

static int cs_branch_test(struct fixture *f)
{
	static const struct { u8 length, bytes[15], target; } branches[] = {
		{ 5, { 0x2e, 0x2e, 0x2e, 0xff, 0xd0 }, 0 }, /* exact CALL AX */
		{ 4, { 0x2e, 0x41, 0xff, 0xd0 }, 1 }, /* R8 */
		{ 4, { 0x41, 0x2e, 0xff, 0xd0 }, 0 }, /* CS cancels REX */
		{ 5, { 0x41, 0x2e, 0x41, 0xff, 0xd0 }, 1 },
		{ 3, { 0x2e, 0xff, 0xd4 }, 2 }, /* source RSP before push */
		{ 4, { 0x2e, 0x41, 0xff, 0xd4 }, 3 }, /* R12 */
		{ 15, { 0 }, 0 }, /* thirteen CS prefixes, bounded by source length */
	}, refused[] = {
		{ 3, { 0x2e, 0xff, 0x10 }, 0 }, /* memory CALL */
		{ 3, { 0x2e, 0xff, 0x20 }, 0 }, /* memory JMP */
		{ 3, { 0x2e, 0xff, 0xc0 }, 0 }, /* INC */
		{ 3, { 0x2e, 0xff, 0xc8 }, 0 }, /* DEC */
		{ 3, { 0x2e, 0xff, 0x18 }, 0 }, /* far CALL */
		{ 3, { 0x2e, 0xff, 0x28 }, 0 }, /* far JMP */
		{ 3, { 0x2e, 0xff, 0xf0 }, 0 }, /* PUSH */
		{ 3, { 0x2e, 0xff, 0xf8 }, 0 }, /* undefined FF group */
		{ 4, { 0x66, 0x2e, 0xff, 0xd0 }, 0 },
		{ 4, { 0x2e, 0x66, 0xff, 0xe0 }, 0 },
		{ 4, { 0x2e, 0xf0, 0xff, 0xd0 }, 0 },
		{ 4, { 0xf3, 0x2e, 0xff, 0xe0 }, 0 },
		{ 4, { 0x2e, 0xf2, 0xff, 0xd0 }, 0 },
	}, truncated[] = {
		{ 1, { 0x2e }, 0 }, { 2, { 0x2e, 0xff }, 0 },
		{ 3, { 0x2e, 0x41, 0xff }, 0 },
	};
	struct kd_regs before, expected;
	u64 memory[ARRAY_SIZE(f->memory)];
	unsigned long target;
	unsigned int form, jump, length, i;
	u8 code[15];

	/* Component control-flow checks use virtual source addresses; they do
	 * not execute a Native indirect branch or claim target text eligibility. */
	for (form = 0; form < ARRAY_SIZE(branches); ++form)
	for (jump = 0; jump < 2; ++jump) {
		length = branches[form].length;
		memcpy(code, branches[form].bytes, length);
		if (length == 15) {
			memset(code, 0x2e, 13); code[13] = 0xff; code[14] = 0xd0;
		}
		if (jump) code[length - 1] += 0x10;
		prepare(f, code, length);
		f->regs.ax = CODE + 32; f->regs.r8 = CODE + 40; f->regs.r12 = CODE + 48;
		f->regs.flags |= KD_REG_ARITHMETIC_FLAGS;
		f->code[32] = f->code[40] = f->code[48] = 0xc3;
		f->code_size = 49;
		f->memory[15] = 0x123456789abcdef0ULL;
		memcpy(memory, f->memory, sizeof(memory));
		target = branches[form].target == 1 ? f->regs.r8 :
			branches[form].target == 2 ? f->regs.sp :
			branches[form].target == 3 ? f->regs.r12 : f->regs.ax;
		before = expected = f->regs;
		expected.ip = target;
		if (!jump) { expected.sp -= 8; memory[15] = CODE + length; }
		CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
		CHECK(!memcmp(&expected, &f->regs, sizeof(expected)));
		CHECK(!memcmp(memory, f->memory, sizeof(memory)));
		CHECK(f->state.event.source_ip == CODE && f->state.event.next_ip == CODE + length &&
			f->state.event.target == target && f->state.event.length == length &&
			f->state.event.edge == (jump ? KD_REACHED_JUMP : KD_REACHED_CALL));
		CHECK(!memcmp(f->state.event.bytes, code, length) && f->fetches == length &&
			f->max_fetch == CODE + length - 1 && !f->reads && f->writes == !jump &&
			!f->atomics && f->state.budget == 99);
		/* RSP supplies its pre-push value even though this fixture does not
		 * supply instruction text at that virtual stack address. */
		if (!jump && branches[form].target != 2) {
			CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
			before.ip = CODE + length;
			CHECK(!memcmp(&before, &f->regs, sizeof(before)) && f->reads == 1 &&
				f->writes == 1 && f->state.budget == 98);
		}
	}
	/* A near register target is a full 64-bit value even without REX.W.
	 * Stop at the edge; these artificial addresses are not source text. */
	for (form = 0; form < 2; ++form) {
		prepare(f, branches[form].bytes, branches[form].length);
		target = 0xffffffff81234567UL;
		f->regs.ax = f->regs.r8 = target;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
		CHECK(f->regs.ip == target && f->memory[15] == CODE + branches[form].length &&
			f->regs.sp == DATA + 120 && !f->reads && f->writes == 1);
	}
	prepare(f, branches[0].bytes, branches[0].length);
	f->regs.ax = CODE + 32; f->fail_write = true;
	f->memory[15] = 0x123456789abcdef0ULL;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes &&
		f->memory[15] == 0x123456789abcdef0ULL && f->state.budget == 100);
	for (i = 0; i < ARRAY_SIZE(refused); ++i) {
		prepare(f, refused[i].bytes, refused[i].length);
		f->regs.ax = DATA; before = f->regs;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
		CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes &&
			!f->atomics && f->state.budget == 100);
	}
	for (i = 0; i < ARRAY_SIZE(truncated); ++i) {
		prepare(f, truncated[i].bytes, truncated[i].length);
		before = f->regs;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_SOURCE);
		CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes &&
			f->fetches == truncated[i].length && f->state.budget == 100);
	}
	return 0;
}


static int cs_relative_test(struct fixture *f)
{
	static const struct { u8 length, bytes[9]; bool call; } forms[] = {
		{ 6, { 0x2e, 0xe8, 26, 0, 0, 0 }, true },
		{ 8, { 0x2e, 0x2e, 0x2e, 0xe8, 24, 0, 0, 0 }, true },
		{ 7, { 0x48, 0x2e, 0xe8, 25, 0, 0, 0 }, true },
		{ 7, { 0x2e, 0x48, 0xe8, 25, 0, 0, 0 }, true },
		{ 6, { 0x2e, 0xe9, 26, 0, 0, 0 }, false },
		{ 3, { 0x2e, 0xeb, 29 }, false },
	}, bad[] = {
		{ 7, { 0x2e, 0x66, 0xe8, 0, 0, 0, 0 }, true },
		{ 7, { 0x2e, 0xf0, 0xe8, 0, 0, 0, 0 }, true },
		{ 7, { 0xf3, 0x2e, 0xe9, 0, 0, 0, 0 }, false },
	};
	struct kd_regs before, expected;
	unsigned int i, length;
	long offsets[] = { -1, -2147483647L - 1, 2147483647L };
	u8 code[] = { 0x2e, 0xe8, 0, 0, 0, 0 };

	/* Virtual source control-flow checks include the exact prefixed CALL
	 * word and a complete return. These are separate from Native arithmetic
	 * comparisons elsewhere in the same fixture. */
	for (i = 0; i < ARRAY_SIZE(forms); ++i) {
		prepare(f, forms[i].bytes, forms[i].length);
		f->code[32] = 0xc3; f->code_size = 33;
		f->regs.flags |= KD_REG_ARITHMETIC_FLAGS;
		before = expected = f->regs;
		expected.ip = CODE + 32;
		if (forms[i].call) expected.sp -= 8;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
		CHECK(!memcmp(&expected, &f->regs, sizeof(expected)));
		CHECK(f->state.event.next_ip == CODE + forms[i].length &&
			f->state.event.edge == (forms[i].call ? KD_REACHED_CALL : KD_REACHED_JUMP));
		CHECK(f->fetches == forms[i].length && !f->reads &&
			f->writes == forms[i].call && f->state.budget == 99);
		if (forms[i].call) {
			CHECK(f->memory[15] == CODE + forms[i].length);
			CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
			before.ip += forms[i].length;
			CHECK(!memcmp(&before, &f->regs, sizeof(before)) && f->reads == 1);
		} else CHECK(!f->memory[15]);
	}
	for (i = 0; i < ARRAY_SIZE(offsets); ++i) {
		u32 displacement = offsets[i];
		for (length = 0; length < 4; ++length) code[2 + length] = displacement >> (8 * length);
		prepare(f, code, sizeof(code));
		CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE);
		CHECK(f->regs.ip == CODE + sizeof(code) + offsets[i] &&
			f->memory[15] == CODE + sizeof(code));
	}
	prepare(f, (u8[]){ 0x2e, 0xeb, 0xfd }, 3);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_EDGE && f->regs.ip == CODE && !f->writes);
	for (length = 1; length < sizeof(code); ++length) {
		prepare(f, code, length); before = f->regs;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_SOURCE);
		CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes &&
			f->state.budget == 100);
	}
	prepare(f, forms[0].bytes, forms[0].length);
	f->fail_write = true; before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->writes && f->state.budget == 100);
	for (i = 0; i < ARRAY_SIZE(bad); ++i) {
		prepare(f, bad[i].bytes, bad[i].length); before = f->regs;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
		CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->writes && !f->reads &&
			f->state.budget == 100);
	}
	return 0;
}

#define ORACLE_SCAN(insn, suffix, part) \
	asm volatile("pushq %[flags]; popfq; " insn suffix " %" part "[source],%" part "[value]; pushfq; popq %[output]" \
		: [value] "+r"(value), [output] "=r"(output) \
		: [source] "r"(source), [flags] "r"(flags) : "cc", "memory")
#define ORACLE_SCAN_WIDTH(suffix, part) do { \
	switch (operation) { \
	case 0: ORACLE_SCAN("bsf", suffix, part); break; \
	case 1: ORACLE_SCAN("bsr", suffix, part); break; \
	case 2: ORACLE_SCAN("tzcnt", suffix, part); break; \
	default: ORACLE_SCAN("lzcnt", suffix, part); break; \
	} \
} while (0)

static u64 native_scan(unsigned int width, unsigned int operation, u64 value,
	u64 source, unsigned long input_flags, unsigned long *result_flags)
{
	unsigned long flags, output;

	asm volatile("pushfq; popq %0" : "=r"(flags) : : "memory");
	flags = (flags & ~KD_REG_ARITHMETIC_FLAGS) | (input_flags & KD_REG_ARITHMETIC_FLAGS);
	switch (width) {
	case 2: ORACLE_SCAN_WIDTH("w", "w"); break;
	case 4: ORACLE_SCAN_WIDTH("l", "k"); break;
	default: ORACLE_SCAN_WIDTH("q", ""); break;
	}
	*result_flags = output;
	return value;
}

static int scan_test(struct fixture *f)
{
	static const u64 sources[] = { 0, 1, 2, 0x8000, 0x10000, 0x80000000,
		0x100000000ULL, 1ULL << 63, ~0ULL };
	static const u64 seeds[] = { 0, ~0ULL, 0xabcdefff00000000ULL, 0x1234567890abcdefULL };
	struct kd_regs before;
	unsigned int width, operation, form, i, j, length;
	unsigned long flags;
	u64 value;
	u8 code[5];

	/* Exact reached bitmap instruction; the already tested nonzero branch
	 * supplies RCX as both source and destination on the executor. */
	prepare(f, (u8[]){ 0xf3, 0x48, 0x0f, 0xbc, 0xc9 }, 5);
	f->regs.cx = 0x100000000ULL;
	value = native_scan(8, 2, f->regs.cx, f->regs.cx, f->regs.flags, &flags);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK(f->regs.cx == value && f->regs.ip == CODE + 5 && f->fetches == 5);
	CHECK(!((f->regs.flags ^ flags) & KD_REG_ARITHMETIC_FLAGS));
	for (width = 2; width <= 8; width *= 2)
	for (operation = 0; operation < 4; ++operation)
	for (form = 0; form < 2; ++form)
	for (i = 0; i < ARRAY_SIZE(sources); ++i)
	for (j = 0; j < ARRAY_SIZE(seeds); ++j) {
		length = 0;
		if (operation >= 2) code[length++] = 0xf3;
		if (width == 2) code[length++] = 0x66;
		if (width == 8) code[length++] = 0x48;
		code[length++] = 0x0f;
		code[length++] = 0xbc + (operation & 1);
		code[length++] = form ? 0x1f : 0xd8; /* source (DI)/AX, destination BX */
		prepare(f, code, length);
		f->regs.ax = f->memory[0] = sources[i];
		f->regs.bx = seeds[j]; f->regs.di = DATA;
		f->regs.flags |= (i & 1) ? KD_REG_ARITHMETIC_FLAGS : 0;
		value = native_scan(width, operation, seeds[j], sources[i], f->regs.flags, &flags);
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(f->regs.bx == value && f->regs.ax == sources[i]);
		/* Include actual Native undefined flags and zero-source destinations.
		 * A generic width4 write would incorrectly impose an extra truncation. */
		CHECK(!((f->regs.flags ^ flags) & KD_REG_ARITHMETIC_FLAGS));
		CHECK((f->regs.flags & ~KD_REG_ARITHMETIC_FLAGS) == 0x202);
		CHECK(f->regs.ip == CODE + length && f->fetches == length && f->state.budget == 99);
		CHECK(f->reads == form && !f->writes && !f->atomics && f->memory[0] == sources[i]);
	}
	prepare(f, (u8[]){ 0xf3, 0x48, 0x0f, 0xbc, 0x1f }, 5);
	f->regs.di = DATA; f->regs.bx = ~0UL; f->fail_read = true;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes && f->state.budget == 100);
	prepare(f, (u8[]){ 0xf0, 0xf3, 0x48, 0x0f, 0xbc, 0x1f }, 6);
	f->regs.di = DATA;
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && !f->reads && !f->writes);
	prepare(f, (u8[]){ 0xf3, 0x48, 0x0f, 0xbc }, 4);
	before = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_SOURCE);
	CHECK(!memcmp(&before, &f->regs, sizeof(before)) && f->fetches == 4 && !f->reads && !f->writes);
	return 0;
}

#define ORACLE_MEMORY_BT(suffix, part) \
	asm volatile("pushq %[flags]; popfq; bt" suffix " %" part "[index],(%[base]); pushfq; popq %[output]" \
		: [output] "=r"(output) : [base] "r"(base), [index] "r"(index), [flags] "r"(flags) \
		: "cc", "memory")
#define ORACLE_MEMORY_BT_IMMEDIATE_WIDTH(number, prefix) \
	asm volatile("pushq %[flags]; popfq; .byte " prefix "0x0f,0xba,0x27," #number "; pushfq; popq %[output]" \
		: [output] "=r"(output) : [base] "D"(base), [flags] "r"(flags) : "cc", "memory")
#define ORACLE_MEMORY_BT_IMMEDIATE(number) do { \
	switch (width) { \
	case 2: ORACLE_MEMORY_BT_IMMEDIATE_WIDTH(number, "0x66,"); break; \
	case 4: ORACLE_MEMORY_BT_IMMEDIATE_WIDTH(number, ""); break; \
	default: ORACLE_MEMORY_BT_IMMEDIATE_WIDTH(number, "0x48,"); break; \
	} \
} while (0)

static unsigned long native_memory_bt(unsigned int width, bool immediate,
	unsigned long base, u64 index, unsigned long input_flags)
{
	unsigned long flags, output;

	asm volatile("pushfq; popq %0" : "=r"(flags) : : "memory");
	flags = (flags & ~KD_REG_ARITHMETIC_FLAGS) | (input_flags & KD_REG_ARITHMETIC_FLAGS);
	if (immediate) {
		switch (index) {
		case 0: ORACLE_MEMORY_BT_IMMEDIATE(0); break;
		case 7: ORACLE_MEMORY_BT_IMMEDIATE(7); break;
		case 15: ORACLE_MEMORY_BT_IMMEDIATE(15); break;
		case 16: ORACLE_MEMORY_BT_IMMEDIATE(16); break;
		case 31: ORACLE_MEMORY_BT_IMMEDIATE(31); break;
		case 32: ORACLE_MEMORY_BT_IMMEDIATE(32); break;
		case 63: ORACLE_MEMORY_BT_IMMEDIATE(63); break;
		case 64: ORACLE_MEMORY_BT_IMMEDIATE(64); break;
		case 127: ORACLE_MEMORY_BT_IMMEDIATE(127); break;
		default: ORACLE_MEMORY_BT_IMMEDIATE(255); break;
		}
	} else {
		switch (width) {
		case 2: ORACLE_MEMORY_BT("w", "w"); break;
		case 4: ORACLE_MEMORY_BT("l", "k"); break;
		default: ORACLE_MEMORY_BT("q", ""); break;
		}
	}
	return output;
}

static int memory_bit_test(struct fixture *f)
{
	static const s64 indices[] = { -127, -65, -64, -33, -32, -17, -16, -1,
		0, 1, 7, 15, 16, 31, 32, 63, 64, 127 };
	static const u8 immediates[] = { 0, 7, 15, 16, 31, 32, 63, 64, 127, 255 };
	struct kd_regs expected;
	u64 memory[ARRAY_SIZE(f->memory)];
	u64 index;
	unsigned long flags;
	unsigned int width, form, pattern, i, j, length, count;
	u8 code[5];

	/* Exact reached zone-node test, including RAX index and RDX base. */
	prepare(f, (u8[]){ 0x48, 0x0f, 0xa3, 0x02 }, 4);
	f->regs.ax = 65; f->regs.dx = DATA + 128; f->memory[17] = 2;
	flags = native_memory_bt(8, false, f->regs.dx, f->regs.ax, f->regs.flags);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK((f->regs.flags & 1) && !((f->regs.flags ^ flags) & KD_REG_ARITHMETIC_FLAGS));
	CHECK(f->regs.ax == 65 && f->regs.dx == DATA + 128 && f->reads == 1 && !f->writes);
	for (width = 2; width <= 8; width *= 2)
	for (form = 0; form < 2; ++form)
	for (pattern = 0; pattern < 3; ++pattern) {
		count = form ? ARRAY_SIZE(immediates) : ARRAY_SIZE(indices);
		for (i = 0; i < count; ++i) {
			length = 0;
			if (width == 2) code[length++] = 0x66;
			if (width == 8) code[length++] = 0x48;
			code[length++] = 0x0f;
			code[length++] = form ? 0xba : 0xa3;
			code[length++] = form ? 0x27 : 0x0f; /* memory(DI), imm8 or indexCX */
			if (form) code[length++] = immediates[i];
			prepare(f, code, length);
			for (j = 0; j < sizeof(f->memory); ++j)
				((u8 *)f->memory)[j] = pattern == 0 ? 0 : pattern == 1 ? 0xff : j * 37 + 11;
			memcpy(memory, f->memory, sizeof(memory));
			index = form ? immediates[i] : (u64)indices[i];
			f->regs.di = DATA + 128; f->regs.cx = index;
			f->regs.flags |= (i & 1) ? KD_REG_ARITHMETIC_FLAGS : 0;
			expected = f->regs;
			flags = native_memory_bt(width, form, f->regs.di, index, f->regs.flags);
			expected.flags = (expected.flags & ~KD_REG_ARITHMETIC_FLAGS) |
				(flags & KD_REG_ARITHMETIC_FLAGS);
			expected.ip += length;
			CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
			CHECK(!memcmp(&expected, &f->regs, sizeof(expected)));
			CHECK(f->reads == 1 && !f->writes && !f->atomics);
			CHECK(!memcmp(memory, f->memory, sizeof(memory)));
			CHECK(f->fetches == length && f->state.budget == 99);
		}
	}
	prepare(f, (u8[]){ 0x48, 0x0f, 0xa3, 0x0f }, 4);
	f->regs.di = DATA + 128; f->regs.cx = 1ULL << 63;
	expected = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&expected, &f->regs, sizeof(expected)) && !f->reads && !f->writes && f->state.budget == 100);
	prepare(f, (u8[]){ 0x48, 0x0f, 0xa3, 0x0f }, 4);
	f->regs.di = DATA + 128; f->regs.cx = -1; f->fail_read = true;
	expected = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&expected, &f->regs, sizeof(expected)) && !f->reads && !f->writes && f->state.budget == 100);
	prepare(f, (u8[]){ 0xf0, 0x48, 0x0f, 0xa3, 0x0f }, 5);
	f->regs.di = DATA + 128;
	expected = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&expected, &f->regs, sizeof(expected)) && !f->reads && !f->writes);
	return 0;
}

#define ORACLE_MEMORY_BIT_REG(insn, suffix, part) do { \
	if (locked) \
		asm volatile("pushq %[flags]; popfq; lock " insn suffix " %" part "[index],(%[base]); pushfq; popq %[output]" \
			: [output] "=r"(output) : [base] "r"(base), [index] "r"(index), [flags] "r"(flags) : "cc", "memory"); \
	else \
		asm volatile("pushq %[flags]; popfq; " insn suffix " %" part "[index],(%[base]); pushfq; popq %[output]" \
			: [output] "=r"(output) : [base] "r"(base), [index] "r"(index), [flags] "r"(flags) : "cc", "memory"); \
} while (0)
#define ORACLE_MEMORY_BIT_REG_WIDTH(suffix, part) do { \
	switch (operation) { \
	case 0: ORACLE_MEMORY_BIT_REG("bts", suffix, part); break; \
	case 1: ORACLE_MEMORY_BIT_REG("btr", suffix, part); break; \
	default: ORACLE_MEMORY_BIT_REG("btc", suffix, part); break; \
	} \
} while (0)
/* Raw immediate bytes prevent an assembler from moving high bit-index bits
 * into a displacement. The oracle must match the actual source encoding. */
#define ORACLE_MEMORY_BIT_IMM_BYTES(number, prefix, modrm) do { \
	if (locked) \
		asm volatile("pushq %[flags]; popfq; .byte 0xf0," prefix "0x0f,0xba," modrm "," #number "; pushfq; popq %[output]" \
			: [output] "=r"(output) : [base] "D"(base), [flags] "r"(flags) : "cc", "memory"); \
	else \
		asm volatile("pushq %[flags]; popfq; .byte " prefix "0x0f,0xba," modrm "," #number "; pushfq; popq %[output]" \
			: [output] "=r"(output) : [base] "D"(base), [flags] "r"(flags) : "cc", "memory"); \
} while (0)
#define ORACLE_MEMORY_BIT_IMM_OP(number, prefix) do { \
	switch (operation) { \
	case 0: ORACLE_MEMORY_BIT_IMM_BYTES(number, prefix, "0x2f"); break; \
	case 1: ORACLE_MEMORY_BIT_IMM_BYTES(number, prefix, "0x37"); break; \
	default: ORACLE_MEMORY_BIT_IMM_BYTES(number, prefix, "0x3f"); break; \
	} \
} while (0)
#define ORACLE_MEMORY_BIT_IMM(number) do { \
	switch (width) { \
	case 2: ORACLE_MEMORY_BIT_IMM_OP(number, "0x66,"); break; \
	case 4: ORACLE_MEMORY_BIT_IMM_OP(number, ""); break; \
	default: ORACLE_MEMORY_BIT_IMM_OP(number, "0x48,"); break; \
	} \
} while (0)

static unsigned long native_memory_bit_update(unsigned int width, unsigned int operation,
	bool locked, bool immediate, unsigned long base, u64 index, unsigned long input_flags)
{
	unsigned long flags, output;

	asm volatile("pushfq; popq %0" : "=r"(flags) : : "memory");
	flags = (flags & ~KD_REG_ARITHMETIC_FLAGS) | (input_flags & KD_REG_ARITHMETIC_FLAGS);
	if (immediate) {
		switch (index) {
		case 0: ORACLE_MEMORY_BIT_IMM(0); break;
		case 3: ORACLE_MEMORY_BIT_IMM(3); break;
		case 5: ORACLE_MEMORY_BIT_IMM(5); break;
		case 15: ORACLE_MEMORY_BIT_IMM(15); break;
		case 16: ORACLE_MEMORY_BIT_IMM(16); break;
		case 31: ORACLE_MEMORY_BIT_IMM(31); break;
		case 32: ORACLE_MEMORY_BIT_IMM(32); break;
		case 63: ORACLE_MEMORY_BIT_IMM(63); break;
		case 64: ORACLE_MEMORY_BIT_IMM(64); break;
		default: ORACLE_MEMORY_BIT_IMM(255); break;
		}
	} else {
		switch (width) {
		case 2: ORACLE_MEMORY_BIT_REG_WIDTH("w", "w"); break;
		case 4: ORACLE_MEMORY_BIT_REG_WIDTH("l", "k"); break;
		default: ORACLE_MEMORY_BIT_REG_WIDTH("q", ""); break;
		}
	}
	return output;
}

static int memory_bit_update_test(struct fixture *f)
{
	struct kd_regs expected;
	u64 memory[ARRAY_SIZE(f->memory)], index;
	unsigned long flags;
	s32 displacement;
	unsigned int operation, width, locked, immediate, sample, pattern, length, i;
	u8 code[6];
	u8 alias_code[] = { 0x66, 0x0f, 0xab, 0xbf, 0, 0, 0, 0 };

	/* Bounded grid: signed register offsets cross both word boundaries;
	 * immediate encodings remain inside the original word, including 255. */
	for (operation = 0; operation < 3; ++operation)
	for (width = 2; width <= 8; width *= 2)
	for (locked = 0; locked < 2; ++locked)
	for (immediate = 0; immediate < 2; ++immediate)
	for (sample = 0; sample < 4; ++sample)
	for (pattern = 0; pattern < 2; ++pattern) {
		index = immediate ? (sample == 0 ? 0 : sample == 1 ? width * 8 - 1 :
			sample == 2 ? width * 8 : 255) :
			(sample == 0 ? -(s64)(width * 8 + 1) : sample == 1 ? -1LL :
			 sample == 2 ? (s64)(width * 8 - 1) : (s64)(width * 8));
		length = 0;
		if (locked) code[length++] = 0xf0;
		if (width == 2) code[length++] = 0x66;
		if (width == 8) code[length++] = 0x48;
		code[length++] = 0x0f;
		code[length++] = immediate ? 0xba : 0xab + operation * 8;
		code[length++] = immediate ? 0x2f + operation * 8 : 0x0f;
		if (immediate) code[length++] = index;
		prepare(f, code, length);
		f->state.ops = &atomic_operations;
		memset(f->memory, pattern ? 0xff : 0, sizeof(f->memory));
		memcpy(memory, f->memory, sizeof(memory));
		f->regs.di = DATA + 128; f->regs.cx = index;
		f->regs.ax = 0x123456789abcdef0ULL;
		if (pattern) f->regs.flags |= KD_REG_ARITHMETIC_FLAGS;
		expected = f->regs;
		flags = native_memory_bit_update(width, operation, locked, immediate,
			(unsigned long)memory + 128, index, f->regs.flags);
		expected.flags = (expected.flags & ~KD_REG_ARITHMETIC_FLAGS) |
			(flags & KD_REG_ARITHMETIC_FLAGS);
		expected.ip += length;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(!memcmp(&expected, &f->regs, sizeof(expected)));
		CHECK(!memcmp(memory, f->memory, sizeof(memory)));
		CHECK(f->atomic_attempts == 1 && f->atomics == 1 && !f->reads && !f->writes &&
			f->atomic_operation == KD_REACHED_ATOMIC_BTS_UNLOCKED + operation + locked * 3 &&
			f->atomic_input == (index & (width * 8 - 1)));
		CHECK(f->fetches == length && f->state.budget == 99);
	}
	/* RDI is both the address base and the signed 16-bit index. Its exact
	 * pre-instruction value selects the word; no index GPR is rewritten. */
	displacement = -(((s16)(DATA + 128) >> 4) * 2);
	for (i = 0; i < 4; ++i) alias_code[4 + i] = (u32)displacement >> (8 * i);
	prepare(f, alias_code, sizeof(alias_code));
	f->state.ops = &atomic_operations;
	f->regs.di = DATA + 128;
	memcpy(memory, f->memory, sizeof(memory)); expected = f->regs;
	flags = native_memory_bit_update(2, 0, false, false,
		(unsigned long)memory + 128 + displacement, f->regs.di, f->regs.flags);
	expected.flags = (expected.flags & ~KD_REG_ARITHMETIC_FLAGS) | (flags & KD_REG_ARITHMETIC_FLAGS);
	expected.ip += sizeof(alias_code);
	CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
	CHECK(!memcmp(&expected, &f->regs, sizeof(expected)) && !memcmp(memory, f->memory, sizeof(memory)));
	CHECK(f->atomic_attempts == 1 && f->atomics == 1 && !f->reads && !f->writes && f->state.budget == 99);
	/* Exact two consecutive reached stack-flag updates commit once each. */
	prepare(f, (u8[]){ 0x48, 0x0f, 0xba, 0x6d, 0xe0, 3,
		0x48, 0x0f, 0xba, 0x6d, 0xe0, 5 }, 12);
	f->state.ops = &atomic_operations;
	for (i = 0; i < 2; ++i) {
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(f->memory[16] == (i ? 0x28 : 8) && f->regs.ip == CODE + 6 * (i + 1) &&
			f->atomic_attempts == i + 1 && f->atomics == i + 1 && !f->reads && !f->writes);
	}
	/* Missing callback, failed RMW and refused address cannot commit data,
	 * GPRs, flags or a budget unit. No ordinary load/store substitutes. */
	for (sample = 0; sample < 3; ++sample) {
		prepare(f, (u8[]){ 0x48, 0x0f, 0xba, 0x6d, 0xe0, 3 }, 6);
		if (sample) f->state.ops = &atomic_operations;
		f->fail_atomic = sample == 1;
		if (sample == 2) f->regs.bp = DATA + sizeof(f->memory) + 32;
		f->memory[16] = 0x123456789abcdef0ULL;
		memcpy(memory, f->memory, sizeof(memory)); expected = f->regs;
		CHECK(kd_reached_step(&f->state) == (sample ? KD_REACHED_MEMORY : KD_REACHED_UNSUPPORTED));
		CHECK(!memcmp(&expected, &f->regs, sizeof(expected)) &&
			!memcmp(memory, f->memory, sizeof(memory)) && f->state.budget == 100);
		CHECK(f->atomic_attempts == !!sample && !f->atomics && !f->reads && !f->writes);
	}
	return 0;
}


static int locked_logic_test(struct fixture *f)
{
	static const u64 values[] = { 0, 0x55, 0x8080, ~0ULL };
	static const u8 immediates[] = { 0, 1, 0x80, 0xf7 };
	static const u8 opcodes[] = { 0x20, 0x08, 0x30 }, groups[] = { 4, 1, 6 };
	struct kd_regs expected;
	u64 memory, source, accumulator;
	unsigned long flags;
	unsigned int op, width, i, j, imm, length;
	u8 code[7];

	for (op = 0; op < 3; ++op)
	for (width = 1; width <= 8; width *= 2)
	for (i = 0; i < ARRAY_SIZE(values); ++i)
	for (j = 0; j < ARRAY_SIZE(values); ++j)
	for (imm = 0; imm < 2; ++imm) {
		length = 0; code[length++] = 0xf0;
		if (width == 2) code[length++] = 0x66;
		if (width == 8) code[length++] = 0x48;
		code[length++] = imm ? (width == 1 ? 0x80 : 0x83) : opcodes[op] + (width != 1);
		code[length++] = imm ? (groups[op] << 3) | 7 : 0x0f;
		if (imm) code[length++] = immediates[j];
		prepare(f, code, length); f->state.ops = &atomic_operations;
		f->regs.di = DATA; f->regs.cx = values[j];
		f->regs.flags |= KD_REG_ARITHMETIC_FLAGS;
		memory = f->memory[0] = values[i]; f->memory[1] = 0x123456789abcdef0ULL;
		source = imm ? (u64)(s64)(s8)immediates[j] : values[j]; accumulator = 0;
		expected = f->regs;
		native_atomic(width, KD_REACHED_ATOMIC_AND + op, &memory, &source,
			&accumulator, f->regs.flags, &flags);
		expected.flags = (expected.flags & ~KD_REG_ARITHMETIC_FLAGS) | (flags & KD_REG_ARITHMETIC_FLAGS);
		expected.ip += length;
		CHECK(kd_reached_step(&f->state) == KD_REACHED_NEXT);
		CHECK(!memcmp(&expected, &f->regs, sizeof(expected)));
		CHECK(f->memory[0] == memory && f->memory[1] == 0x123456789abcdef0ULL);
		CHECK(f->atomics == 1 && f->atomic_attempts == 1 && !f->reads && !f->writes &&
			f->atomic_operation == KD_REACHED_ATOMIC_AND + op && f->state.budget == 99);
	}
	prepare(f, (u8[]){ 0xf0, 0x80, 0x27, 0xf7 }, 4);
	f->regs.di = DATA; expected = f->regs;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_UNSUPPORTED);
	CHECK(!memcmp(&expected, &f->regs, sizeof(expected)) && !f->reads && !f->writes);
	f->state.ops = &atomic_operations; f->fail_atomic = true;
	CHECK(kd_reached_step(&f->state) == KD_REACHED_MEMORY);
	CHECK(!memcmp(&expected, &f->regs, sizeof(expected)) && !f->atomics && f->state.budget == 100);
	return 0;
}

static int worker(void *argument)
{
	struct fixture *f = argument;
	unsigned long marker;

	executor_pid = task_pid_nr(current);
	executor_stack = (unsigned long)&marker;
	origin_source_stack = DATA;
	if (object_is_on_stack(f)) {
		result = -EINVAL;
		failure_line = __LINE__;
	} else result = entry_test(f);
	if (!result) result = arithmetic_test(f);
	if (!result) result = edge_test(f);
	if (!result) result = scalar_test(f);
	if (!result) result = stop_test(f);
	if (!result) result = supplementation_test(f);
	if (!result) result = atomic_test(f);
	if (!result) result = locked_logic_test(f);
	if (!result) result = shift_multiply_test(f);
	if (!result) result = bit_test(f);
	if (!result) result = stos_test(f);
	if (!result) result = movs_test(f);
	if (!result) result = cs_padding_test(f);
	if (!result) result = cs_branch_test(f);
	if (!result) result = cs_relative_test(f);
	if (!result) result = scan_test(f);
	if (!result) result = memory_bit_test(f);
	if (!result) result = memory_bit_update_test(f);
	complete(&finished);
	while (!kthread_should_stop())
		schedule_timeout_interruptible(HZ);
	return 0;
}

static int __init reached_test_init(void)
{
	/* O's module-loading stack and fixture remain live until E has joined. */
	struct fixture f;
	struct task_struct *task;

	origin_pid = task_pid_nr(current);
	task = kthread_run(worker, &f, "kd_reached_test");
	if (IS_ERR(task)) return PTR_ERR(task);
	/* The component has a finite test count and no external protocol wait.
	 * kthread_stop joins before any module text/storage can be released. */
	if (!wait_for_completion_timeout(&finished, 30 * HZ)) {
		kthread_stop(task);
		return -ETIMEDOUT;
	}
	kthread_stop(task);
	pr_info("KD_REACHED_TEST result=%s cases=%u executor_pid=%d origin_pid=%d source_fetches=%llu checks=%u failure_line=%u executor_stack=%lx origin_source_stack=%lx\n",
		result ? "FAIL" : "PASS", checks, executor_pid, origin_pid, source_fetches,
		checks, failure_line, executor_stack, origin_source_stack);
	if (executor_pid == origin_pid) return -EINVAL;
	return result;
}

static void __exit reached_test_exit(void) { }
module_init(reached_test_init);
module_exit(reached_test_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KD reached scalar execution fixture");
