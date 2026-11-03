// SPDX-License-Identifier: GPL-2.0
/* Exact x86 instruction effects for reached scalar and locked operations.
 * The caller retains and qualifies ordinary RAM. One source RMW is one actual
 * CPU RMW; no retry loop or split load/store is used. Only source arithmetic
 * flags are imported, retaining the executor's actual IRQ/DF context. */
#include <linux/errno.h>
#include <asm/asm.h>
#include "kd_reached.h"

static unsigned long kd_reached_input_flags(unsigned long source)
{
	unsigned long native;

	asm volatile("pushfq; popq %0" : "=r"(native) : : "memory");
	return (native & ~KD_REG_ARITHMETIC_FLAGS) |
		(source & KD_REG_ARITHMETIC_FLAGS);
}

#define KD_ATOMIC_BINARY(insn, suffix, part, type) \
	asm_goto_output("pushq %[flags]; popfq\n\t1: " insn suffix " %" part "[value], %[memory]\n\t" \
		"pushfq; popq %[output]\n\t" _ASM_EXTABLE(1b, %l[fault]) \
		: [memory] "+m"(*(type *)address), [value] "+r"(value), [output] "=r"(output) \
		: [flags] "r"(flags) : "cc", "memory" : fault)
#define KD_ATOMIC_UNARY(insn, suffix, type) \
	asm_goto_output("pushq %[flags]; popfq\n\t1: " insn suffix " %[memory]\n\t" \
		"pushfq; popq %[output]\n\t" _ASM_EXTABLE(1b, %l[fault]) \
		: [memory] "+m"(*(type *)address), [output] "=r"(output) \
		: [flags] "r"(flags) : "cc", "memory" : fault)
#define KD_ATOMIC_CMP(suffix, part, type) \
	asm_goto_output("pushq %[flags]; popfq\n\t1: lock cmpxchg" suffix " %" part "[value], %[memory]\n\t" \
		"pushfq; popq %[output]\n\t" _ASM_EXTABLE(1b, %l[fault]) \
		: [memory] "+m"(*(type *)address), [accumulator] "+a"(accumulator), [output] "=r"(output) \
		: [value] "r"(value), [flags] "r"(flags) : "cc", "memory" : fault)
#define KD_ATOMIC_BIT(insn, suffix, part, type) \
	asm_goto_output("pushq %[flags]; popfq\n\t1: " insn suffix " %" part "[value], %[memory]\n\t" \
		"pushfq; popq %[output]\n\t" _ASM_EXTABLE(1b, %l[fault]) \
		: [memory] "+m"(*(type *)address), [output] "=r"(output) \
		: [value] "r"(value), [flags] "r"(flags) : "cc", "memory" : fault)
#define KD_ATOMIC_BIT_WIDTH(suffix, part, type) do { \
	switch (operation) { \
	case KD_REACHED_ATOMIC_BTS_UNLOCKED: KD_ATOMIC_BIT("bts", suffix, part, type); break; \
	case KD_REACHED_ATOMIC_BTR_UNLOCKED: KD_ATOMIC_BIT("btr", suffix, part, type); break; \
	case KD_REACHED_ATOMIC_BTC_UNLOCKED: KD_ATOMIC_BIT("btc", suffix, part, type); break; \
	case KD_REACHED_ATOMIC_BTS_LOCKED: KD_ATOMIC_BIT("lock bts", suffix, part, type); break; \
	case KD_REACHED_ATOMIC_BTR_LOCKED: KD_ATOMIC_BIT("lock btr", suffix, part, type); break; \
	case KD_REACHED_ATOMIC_BTC_LOCKED: KD_ATOMIC_BIT("lock btc", suffix, part, type); break; \
	default: return -EOPNOTSUPP; \
	} \
} while (0)

#define KD_ATOMIC_WIDTH(suffix, part, type) do { \
	switch (operation) { \
	case KD_REACHED_ATOMIC_ADD: KD_ATOMIC_BINARY("lock add", suffix, part, type); break; \
	case KD_REACHED_ATOMIC_SUB: KD_ATOMIC_BINARY("lock sub", suffix, part, type); break; \
	case KD_REACHED_ATOMIC_INC: KD_ATOMIC_UNARY("lock inc", suffix, type); break; \
	case KD_REACHED_ATOMIC_DEC: KD_ATOMIC_UNARY("lock dec", suffix, type); break; \
	case KD_REACHED_ATOMIC_XADD: KD_ATOMIC_BINARY("lock xadd", suffix, part, type); break; \
	case KD_REACHED_ATOMIC_XCHG: KD_ATOMIC_BINARY("xchg", suffix, part, type); break; \
	case KD_REACHED_ATOMIC_CMPXCHG: KD_ATOMIC_CMP(suffix, part, type); break; \
	default: return -EOPNOTSUPP; \
	} \
} while (0)

int kd_reached_atomic_apply(void *address, unsigned int width,
	enum kd_reached_atomic_op operation, u64 input, u64 accumulator,
	unsigned long input_flags, u64 *old, unsigned long *output_flags)
{
	unsigned long flags = kd_reached_input_flags(input_flags), output;
	u64 value = input;

	if (!address || !old || !output_flags)
		return -EINVAL;
	if (operation >= KD_REACHED_ATOMIC_BTS_UNLOCKED && operation <= KD_REACHED_ATOMIC_BTC_LOCKED) {
		/* The qualified callback address already selects the complete word. */
		value &= width * 8 - 1;
		switch (width) {
		case 2: KD_ATOMIC_BIT_WIDTH("w", "w", u16); break;
		case 4: KD_ATOMIC_BIT_WIDTH("l", "k", u32); break;
		case 8: KD_ATOMIC_BIT_WIDTH("q", "", u64); break;
		default: return -EOPNOTSUPP;
		}
	} else {
		switch (width) {
		case 1: KD_ATOMIC_WIDTH("b", "b", u8); break;
		case 2: KD_ATOMIC_WIDTH("w", "w", u16); break;
		case 4: KD_ATOMIC_WIDTH("l", "k", u32); break;
		case 8: KD_ATOMIC_WIDTH("q", "", u64); break;
		default: return -EINVAL;
		}
	}
	*old = operation == KD_REACHED_ATOMIC_CMPXCHG ? accumulator : value;
	*output_flags = (input_flags & ~KD_REG_ARITHMETIC_FLAGS) |
		(output & KD_REG_ARITHMETIC_FLAGS);
	return 0;
fault:
	return -EFAULT;
}

#define KD_SCALAR_SHIFT(insn, suffix, part) \
	asm volatile("pushq %[flags]; popfq; " insn suffix " %%cl,%" part "[value]; " \
		"pushfq; popq %[output]" \
		: [value] "+r"(value), [output] "=r"(output) \
		: "c"((unsigned int)right), [flags] "r"(flags) : "cc", "memory")
#define KD_SCALAR_MUL(suffix, part) \
	asm volatile("pushq %[flags]; popfq; imul" suffix " %" part "[right],%" part "[value]; " \
		"pushfq; popq %[output]" \
		: [value] "+r"(value), [output] "=r"(output) \
		: [right] "r"(right), [flags] "r"(flags) : "cc", "memory")
#define KD_SCALAR_BIT(insn, suffix, part) \
	asm volatile("pushq %[flags]; popfq; " insn suffix " %" part "[right],%" part "[value]; " \
		"pushfq; popq %[output]" \
		: [value] "+r"(value), [output] "=r"(output) \
		: [right] "r"(right), [flags] "r"(flags) : "cc", "memory")
#define KD_SCALAR_MEMORY_BT(suffix, part, type) \
	asm volatile("pushq %[flags]; popfq; bt" suffix " %" part "[right],%[word]; " \
		"pushfq; popq %[output]" : [output] "=r"(output) \
		: [word] "m"(*(type *)&value), [right] "r"(right), [flags] "r"(flags) \
		: "cc", "memory")
#define KD_BIT_WIDTH(suffix, part) do { \
	switch (operation) { \
	case KD_REACHED_SCALAR_BT: KD_SCALAR_BIT("bt", suffix, part); break; \
	case KD_REACHED_SCALAR_BTS: KD_SCALAR_BIT("bts", suffix, part); break; \
	case KD_REACHED_SCALAR_BTR: KD_SCALAR_BIT("btr", suffix, part); break; \
	case KD_REACHED_SCALAR_BTC: KD_SCALAR_BIT("btc", suffix, part); break; \
	default: return -EOPNOTSUPP; \
	} \
} while (0)
#define KD_SCAN_WIDTH(suffix, part) do { \
	switch (operation) { \
	case KD_REACHED_SCALAR_BSF: KD_SCALAR_BIT("bsf", suffix, part); break; \
	case KD_REACHED_SCALAR_BSR: KD_SCALAR_BIT("bsr", suffix, part); break; \
	case KD_REACHED_SCALAR_TZCNT: KD_SCALAR_BIT("tzcnt", suffix, part); break; \
	case KD_REACHED_SCALAR_LZCNT: KD_SCALAR_BIT("lzcnt", suffix, part); break; \
	default: return -EOPNOTSUPP; \
	} \
} while (0)
#define KD_SCALAR_WIDTH(suffix, part) do { \
	switch (operation) { \
	case KD_REACHED_SCALAR_ROL: KD_SCALAR_SHIFT("rol", suffix, part); break; \
	case KD_REACHED_SCALAR_ROR: KD_SCALAR_SHIFT("ror", suffix, part); break; \
	case KD_REACHED_SCALAR_RCL: KD_SCALAR_SHIFT("rcl", suffix, part); break; \
	case KD_REACHED_SCALAR_RCR: KD_SCALAR_SHIFT("rcr", suffix, part); break; \
	case KD_REACHED_SCALAR_SHL: KD_SCALAR_SHIFT("shl", suffix, part); break; \
	case KD_REACHED_SCALAR_SHR: KD_SCALAR_SHIFT("shr", suffix, part); break; \
	case KD_REACHED_SCALAR_SAR: KD_SCALAR_SHIFT("sar", suffix, part); break; \
	default: return -EOPNOTSUPP; \
	} \
} while (0)

int kd_reached_scalar_apply(unsigned int width, enum kd_reached_scalar_op operation,
	u64 left, u64 right, unsigned long input_flags, u64 *result,
	unsigned long *output_flags)
{
	unsigned long flags = kd_reached_input_flags(input_flags), output;
	u64 value = left;

	if (!result || !output_flags)
		return -EINVAL;
	if (operation >= KD_REACHED_SCALAR_BT && operation <= KD_REACHED_SCALAR_BTC) {
		switch (width) {
		case 2: KD_BIT_WIDTH("w", "w"); break;
		case 4: KD_BIT_WIDTH("l", "k"); break;
		case 8: KD_BIT_WIDTH("q", ""); break;
		default: return -EOPNOTSUPP;
		}
	} else if (operation == KD_REACHED_SCALAR_BT_MEMORY) {
		/* The caller has loaded one qualified source word. Mask before the
		 * Native memory-form BT so it reads only this private retained word. */
		right &= width * 8 - 1;
		switch (width) {
		case 2: KD_SCALAR_MEMORY_BT("w", "w", u16); break;
		case 4: KD_SCALAR_MEMORY_BT("l", "k", u32); break;
		case 8: KD_SCALAR_MEMORY_BT("q", "", u64); break;
		default: return -EOPNOTSUPP;
		}
	} else if (operation >= KD_REACHED_SCALAR_BSF && operation <= KD_REACHED_SCALAR_LZCNT) {
		switch (width) {
		case 2: KD_SCAN_WIDTH("w", "w"); break;
		case 4: KD_SCAN_WIDTH("l", "k"); break;
		case 8: KD_SCAN_WIDTH("q", ""); break;
		default: return -EOPNOTSUPP;
		}
	} else if (operation == KD_REACHED_SCALAR_IMUL) {
		switch (width) {
		case 2: KD_SCALAR_MUL("w", "w"); break;
		case 4: KD_SCALAR_MUL("l", "k"); break;
		case 8: KD_SCALAR_MUL("q", ""); break;
		default: return -EOPNOTSUPP;
		}
	} else {
		switch (width) {
		case 1: KD_SCALAR_WIDTH("b", "b"); break;
		case 2: KD_SCALAR_WIDTH("w", "w"); break;
		case 4: KD_SCALAR_WIDTH("l", "k"); break;
		case 8: KD_SCALAR_WIDTH("q", ""); break;
		default: return -EINVAL;
		}
	}
	*result = value;
	*output_flags = (input_flags & ~KD_REG_ARITHMETIC_FLAGS) |
		(output & KD_REG_ARITHMETIC_FLAGS);
	return 0;
}
