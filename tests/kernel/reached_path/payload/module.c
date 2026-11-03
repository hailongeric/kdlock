// SPDX-License-Identifier: GPL-2.0
#include <linux/completion.h>
#include <linux/errno.h>
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
	unsigned long max_fetch;
	bool fail_write;
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

	if (address < DATA || address - DATA > sizeof(f->memory) ||
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
