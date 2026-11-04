/* SPDX-License-Identifier: GPL-2.0 */
/* Production decoder/EA only. CPU/context service is a separate live check. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <asm/prctl.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int8_t s8;
typedef int32_t s32;
#include "kd_regs.h"
#include "kd_origin_memory.h"
#include "kd_image.h"
static int __preempt_count;

static unsigned int pins;
static int kd_source_pin_root(unsigned long address)
{
	++pins;
	return address ? 0 : -EINVAL;
}
static int copy_from_kernel_nofault(void *out, const void *in, unsigned long bytes)
{
	memcpy(out, in, bytes);
	return 0;
}
#define BUG() abort()
#include "production.h"

static unsigned int checks;
#define CHECK(value) do { ++checks; if (!(value)) { \
	fprintf(stderr, "FAIL line=%u: %s\n", __LINE__, #value); exit(1); } } while (0)

static struct kd_origin_memory_site site(const char *hex, u8 op, u8 width)
{
	struct kd_origin_memory_site result = { .ip = 0x1000, .operation = op, .width = width,
		.flags = op >= KD_ORIGIN_MEMORY_LOAD && op != KD_ORIGIN_MEMORY_ADD_MEMORY ?
			KD_ORIGIN_MEMORY_READ : 0 };
	unsigned int byte;

	while (*hex) {
		if (sscanf(hex, "%2x", &byte) != 1 || result.length == 16)
			abort();
		result.opcode[result.length++] = byte;
		hex += 2;
	}
	result.next_ip = result.ip + result.length;
	return result;
}

struct reached_source {
	const u8 *bytes;
	unsigned int length;
	unsigned int calls;
	unsigned long base;
};

static int reached_read(void *context, unsigned long address, void *out,
	unsigned int size)
{
	struct reached_source *source = context;
	unsigned long base = source->base ? source->base : 0x1000;

	++source->calls;
	if (size != 1 || address < base || address - base >= source->length)
		return -ENODATA;
	*(u8 *)out = source->bytes[address - base];
	return 0;
}

int main(void)
{
	struct kd_regs regs = { .ax = 0x1000, .cx = 3, .r12 = 2, .r13 = 0x5000, .sp = 0x6000 };
	struct kd_origin_memory_site input;
	unsigned long address;
	unsigned int i;
	u8 image_bytes[256] = { 0 };
	u8 native_bytes[] = { 0x65, 0x48, 0xff, 0x00 };
	struct kd_jit_image image = {
		.code = image_bytes, .length = 128 + 40 + 16,
		.requirements = KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_ORIGIN_MEMORY,
		.entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1,
	};
	struct kd_origin_memory_site *directory = (void *)(image_bytes + 128);
	struct kd_origin_memory_footer *footer = (void *)(image_bytes + image.length - 16);
	struct kd_origin_memory_read_footer *read_footer;
	struct kd_origin_memory operation = { 0 };
	unsigned long saved_gs;
	unsigned long cpu_data[2] = { 0x1234567880000000UL, 0 };
	const struct { const char *hex; u8 op, width; unsigned long expected; } accepted[] = {
		{ "65ff00", 1, 32, 0x1000 },
		{ "6548ff08", 2, 64, 0x1000 },
		{ "6549ff45f0", 1, 64, 0x4ff0 },
		{ "654bff44e520", 1, 64, 0x5030 },
		{ "65ff05fcffffff", 1, 32, 0x1003 },
		{ "6548ff0c25f0ffffff", 2, 64, ~15UL },
		{ "6548ff0424", 1, 64, 0x6000 },
		{ "65488b00", 3, 64, 0x1000 },
		{ "658b00", 3, 32, 0x1000 },
		{ "6566f74001ffff", 4, 16, 0x1001 },
		{ "65f700ffffffff", 4, 32, 0x1000 },
		{ "654f8b64a5f0", 3, 64, 0x4ff8 },
		{ "65482b10", 5, 64, 0x1000 },
		{ "652b10", 5, 32, 0x1000 },
		{ "65486300", 7, 64, 0x1000 },
		{ "654f6364a5f0", 7, 64, 0x4ff8 },
		{ "650110", 9, 32, 0x1000 },
		{ "65480104d5600e4284", 9, 64, 0xffffffff84420e60UL },
		{ "653b10", 10, 32, 0x1000 },
		{ "654f3b64a5f0", 10, 64, 0x4ff8 },
	};
	const char *rejected[] = { "64ff00", "f06548ff00", "656748ff00", "6566ff00",
		"65ff10", "65ffff", "65ff04", "65ff05000000", "656300", "6566486300" };

	for (i = 0; i < sizeof(accepted) / sizeof(accepted[0]); ++i) {
		struct kd_origin_memory_site reached;
		struct reached_source source;

		input = site(accepted[i].hex, accepted[i].op, accepted[i].width);
		CHECK(!kd_origin_memory_decode(&input, &regs, &address));
		CHECK(address == accepted[i].expected);
		source = (struct reached_source){ .bytes = input.opcode, .length = input.length };
		CHECK(!kd_origin_memory_reached_decode(&reached, input.ip, reached_read, &source));
		CHECK(!memcmp(&input, &reached, sizeof(input)));
		CHECK(source.calls == input.length);
		CHECK(!kd_origin_memory_decode(&reached, &regs, &address));
		CHECK(address == accepted[i].expected);
		/* A missing final byte cannot publish a service. Supplement only that
		 * reached instruction; no successor or whole-image directory is read. */
		source.length = input.length - 1;
		source.calls = 0;
		CHECK(kd_origin_memory_reached_decode(&reached, input.ip, reached_read, &source) == -ENODATA);
		CHECK(source.calls == input.length);
		source.length = input.length;
		source.calls = 0;
		CHECK(!kd_origin_memory_reached_decode(&reached, input.ip, reached_read, &source));
		CHECK(source.calls == input.length && !memcmp(&input, &reached, sizeof(input)));
	}
	{
		static const u8 ordinary[] = { 0x90, 0x65, 0xff, 0 };
		static const u8 atomic[] = { 0x65, 0xf0, 0xff, 0 };
		static const u8 duplicate[] = { 0x65, 0x65, 0xff, 0 };
		struct reached_source source = { .bytes = ordinary, .length = sizeof(ordinary) };
		CHECK(kd_origin_memory_reached_decode(&input, 0x1000, reached_read, &source) == -EOPNOTSUPP);
		CHECK(source.calls == 1);
		source = (struct reached_source){ .bytes = atomic, .length = sizeof(atomic) };
		CHECK(kd_origin_memory_reached_decode(&input, 0x1000, reached_read, &source) == -EOPNOTSUPP);
		CHECK(source.calls == 2);
		source = (struct reached_source){ .bytes = duplicate, .length = sizeof(duplicate) };
		CHECK(kd_origin_memory_reached_decode(&input, 0x1000, reached_read, &source) == -EOPNOTSUPP);
		CHECK(source.calls == 2);
		source.calls = 0;
		CHECK(kd_origin_memory_reached_decode(&input, ~0UL, reached_read, &source) == -EOPNOTSUPP);
		CHECK(!source.calls);
	}
	for (i = 0; i < sizeof(rejected) / sizeof(rejected[0]); ++i) {
		input = site(rejected[i], 1, 32);
		CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	}
	{
		/* Exact instructions in the first reached MM callee and its bounded
		 * normal-return tail. The policy is general, independent of this symbol. */
		const struct { const char *hex; u8 op; unsigned long ip; } actual[] = {
			{ "654c8b252649c102", KD_ORIGIN_MEMORY_LOAD, 0xffffffff817f66daUL },
			{ "65482b15f848c102", KD_ORIGIN_MEMORY_SUB, 0xffffffff817f6708UL },
			{ "6548031d7723be02", KD_ORIGIN_MEMORY_ADD, 0xffffffff81828ca9UL },
		};
		unsigned int item;
		for (item = 0; item < sizeof(actual) / sizeof(actual[0]); ++item) {
			struct kd_origin_memory_site reached;
			struct reached_source source;
			struct kd_memory_operand decoded;
			input = site(actual[item].hex, actual[item].op, 64);
			input.ip = actual[item].ip;
			input.next_ip = input.ip + input.length;
			source = (struct reached_source){ .bytes = input.opcode,
				.length = input.length, .base = input.ip };
			CHECK(!kd_origin_memory_reached_decode(&reached, input.ip, reached_read, &source));
			CHECK(source.calls == 8 && !memcmp(&input, &reached, sizeof(input)));
			CHECK(!kd_origin_memory_decode(&reached, &regs, &address));
			CHECK(address == (actual[item].op == KD_ORIGIN_MEMORY_ADD ?
				0xffffffff8440b028UL : 0xffffffff8440b008UL));
			CHECK(!kd_memory_operand_decode(&reached, &decoded) &&
				decoded.destination == (actual[item].op == KD_ORIGIN_MEMORY_ADD ? 3 : item ? 2 : 12));
		}
	}
	input = site("65ff00", 1, 32);
	input.flags = 1;
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	input.flags = 0;
	input.opcode[15] = 1;
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	input.opcode[15] = 0;
	input.next_ip++;
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	input = site("658b20", 3, 32);
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	input = site("65668b00", 3, 16);
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	input = site("658500", 4, 32);
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	input = site("65662b10", 5, 16);
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	input = site("65482b20", 5, 64);
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);

	*directory = site("6548ff00", 1, 64);
	directory->ip = (unsigned long)native_bytes;
	directory->next_ip = directory->ip + directory->length;
	directory->continuation_offset = 64;
	memcpy(footer->magic, "KDOM0001", 8);
	footer->offset = 128;
	footer->count = 1;
	CHECK(!kd_image_validate_memory_sites(&image));
	CHECK(pins == 3);
	footer->magic[0] = 'X';
	CHECK(kd_image_validate_memory_sites(&image) == -EPROTO);
	footer->magic[0] = 'K';
	directory->continuation_offset = 128;
	CHECK(kd_image_validate_memory_sites(&image) == -EPROTO);
	directory->continuation_offset = 64;
	native_bytes[3] = 8;
	CHECK(kd_image_validate_memory_sites(&image) == -EILSEQ);
	native_bytes[3] = 0;
	image.length += 40;
	directory[1] = directory[0];
	footer = (void *)(image_bytes + image.length - 16);
	memcpy(footer->magic, "KDOM0001", 8);
	footer->offset = 128;
	footer->count = 2;
	CHECK(kd_image_validate_memory_sites(&image) == -EPROTO);

	image.length = 128 + 40 + 24;
	image.requirements |= KD_IMAGE_REQUIRE_ORIGIN_CONTEXT_READ;
	*directory = site("658b00", 3, 32);
	memcpy(native_bytes, directory->opcode, 3);
	directory->ip = (unsigned long)native_bytes;
	directory->next_ip = directory->ip + directory->length;
	directory->continuation_offset = 64;
	read_footer = (void *)(image_bytes + image.length - sizeof(*read_footer));
	memcpy(read_footer->magic, "KDOM0002", 8);
	read_footer->offset = 128;
	read_footer->count = 1;
	read_footer->preempt_symbol = (unsigned long)&__preempt_count;
	CHECK(!kd_image_validate_memory_sites(&image));
	read_footer->preempt_symbol++;
	CHECK(kd_image_validate_memory_sites(&image) == -EPROTO);

	regs.sp = 0x6000;
	regs.ax = ~0UL;
	kd_memory_write_register(&regs, 0, 32, 0x1234567889abcdefUL);
	CHECK(regs.ax == 0x89abcdef && regs.sp == 0x6000);
	kd_memory_write_register(&regs, 15, 64, 0xfedcba9876543210UL);
	CHECK(regs.r15 == 0xfedcba9876543210UL && regs.sp == 0x6000);
	{
		struct kd_origin_memory_site task = site("0f01ee", KD_ORIGIN_MEMORY_TASK_READ, 32);
		struct kd_origin_memory_site decoded, invalid;
		static const u8 bytes[] = { 0x0f, 0x01, 0xee, 0x90 };
		struct reached_source source = { .bytes = bytes, .length = sizeof(bytes) };
		struct kd_regs before;
		u32 ax, bx, cx, dx, expected;
		const unsigned long patterns[] = { 2, 0x203, 0x897, 0xad7 };

		regs.cx = 1UL << 32;
		CHECK(!kd_origin_memory_reached_decode(&decoded, task.ip, reached_read, &source));
		CHECK(source.calls == 3 && !memcmp(&decoded, &task, sizeof(task)));
		CHECK(!kd_origin_memory_decode(&decoded, &regs, &address) && !address);
		regs.cx = 1;
		CHECK(kd_origin_memory_decode(&decoded, &regs, &address) == -EOPNOTSUPP);
		regs.cx = 1UL << 32;
		for (i = 0; i < 3; ++i) {
			source.length = i; source.calls = 0;
			CHECK(kd_origin_memory_reached_decode(&decoded, task.ip, reached_read, &source) == -ENODATA);
			CHECK(source.calls == i + 1);
		}
		invalid = task; invalid.width = 64;
		CHECK(kd_origin_memory_decode(&invalid, &regs, &address) == -EPROTO);
		invalid = task; invalid.flags = 0;
		CHECK(kd_origin_memory_decode(&invalid, &regs, &address) == -EPROTO);
		invalid = task; invalid.opcode[3] = 0x90;
		CHECK(kd_origin_memory_decode(&invalid, &regs, &address) == -EPROTO);
		invalid = task; invalid.opcode[2] = 0xef;
		CHECK(kd_origin_memory_decode(&invalid, &regs, &address) == -EPROTO);
		asm volatile("cpuid" : "=a"(ax), "=b"(bx), "=c"(cx), "=d"(dx)
			: "0"(7U), "2"(0U) : "memory");
		CHECK(cx & (1U << 4));
		asm volatile(".byte 0x0f, 0x01, 0xee" : "=a"(expected), "=d"(dx) : "c"(0U) : "memory");
		CHECK(dx == 0);
		before = regs;
		operation.site = &task;
		operation.packet = &regs;
		operation.source_value = 0;
		for (i = 0; i < sizeof(patterns) / sizeof(patterns[0]); ++i) {
			operation.input_flags = patterns[i];
			operation.result_value = operation.result_aux = ~0UL;
			kd_origin_memory_apply(&operation);
			CHECK(operation.result_value == expected && operation.result_aux == 0);
			CHECK(!memcmp(&before, &regs, sizeof(regs)));
			CHECK((operation.result_flags & KD_REG_ARITHMETIC_FLAGS) ==
				(patterns[i] & KD_REG_ARITHMETIC_FLAGS));
		}
	}
	CHECK(!syscall(SYS_arch_prctl, ARCH_GET_GS, &saved_gs));
	CHECK(!syscall(SYS_arch_prctl, ARCH_SET_GS, cpu_data));
	{
		const u32 values[] = { 0, 1, 0x7fffffff, 0x80000000, 0xffffffff };
		input = site("65486300", KD_ORIGIN_MEMORY_LOAD_SIGNED, 64);
		operation.site = &input;
		operation.effective_offset = 0;
		operation.input_flags = 0x897;
		for (i = 0; i < sizeof(values) / sizeof(values[0]); ++i) {
			cpu_data[0] = values[i];
			kd_origin_memory_apply(&operation);
			CHECK(operation.result_value == (unsigned long)(long)(s32)values[i]);
			CHECK((operation.result_flags & KD_REG_ARITHMETIC_FLAGS) ==
				(operation.input_flags & KD_REG_ARITHMETIC_FLAGS));
		}
		cpu_data[0] = 0x1234567880000000UL;
	}
	input = site("658b00", 3, 32);
	operation.site = &input;
	operation.input_flags = 0x897;
	kd_origin_memory_apply(&operation);
	CHECK(operation.result_value == 0x80000000UL);
	CHECK((operation.result_flags & KD_REG_ARITHMETIC_FLAGS) ==
		(operation.input_flags & KD_REG_ARITHMETIC_FLAGS));
	input = site("65488b00", 3, 64);
	kd_origin_memory_apply(&operation);
	CHECK(operation.result_value == cpu_data[0]);
	input = site("6566f74001ffff", 4, 16);
	operation.effective_offset = 1;
	operation.immediate = 0xffff;
	kd_origin_memory_apply(&operation);
	CHECK((operation.result_flags & 0x841) == 0x40);
	input = site("65f70001000000", 4, 32);
	operation.effective_offset = 0;
	operation.immediate = 1;
	kd_origin_memory_apply(&operation);
	CHECK((operation.result_flags & 0x841) == 0x40);
	{
		const unsigned long values[] = { 0, 1, 0x7fffffff, 0x80000000,
			0xffffffff, 0x8000000000000000UL, ~0UL };
		unsigned int width, left, right, arithmetic;
		unsigned long expected, native_flags, source_value;
		for (arithmetic = 0; arithmetic < 2; ++arithmetic)
		for (width = 32; width <= 64; width *= 2)
		for (left = 0; left < sizeof(values) / sizeof(values[0]); ++left)
		for (right = 0; right < sizeof(values) / sizeof(values[0]); ++right) {
			input = site(arithmetic ? (width == 32 ? "650310" : "65480310") :
				(width == 32 ? "652b10" : "65482b10"),
				arithmetic ? KD_ORIGIN_MEMORY_ADD : KD_ORIGIN_MEMORY_SUB, width);
			cpu_data[0] = source_value = values[right];
			expected = operation.source_value = values[left];
			operation.effective_offset = 0;
			operation.input_flags = 0x897;
			if (arithmetic && width == 32)
				asm volatile("addl %k[right],%k[left]; pushfq; popq %[flags]"
					: [left] "+r"(expected), [flags] "=r"(native_flags)
					: [right] "r"(source_value) : "cc", "memory");
			else if (arithmetic)
				asm volatile("addq %[right],%[left]; pushfq; popq %[flags]"
					: [left] "+r"(expected), [flags] "=r"(native_flags)
					: [right] "r"(source_value) : "cc", "memory");
			else if (width == 32)
				asm volatile("subl %k[right],%k[left]; pushfq; popq %[flags]"
					: [left] "+r"(expected), [flags] "=r"(native_flags)
					: [right] "r"(source_value) : "cc", "memory");
			else
				asm volatile("subq %[right],%[left]; pushfq; popq %[flags]"
					: [left] "+r"(expected), [flags] "=r"(native_flags)
					: [right] "r"(source_value) : "cc", "memory");
			kd_origin_memory_apply(&operation);
			CHECK(operation.result_value == expected && cpu_data[0] == source_value);
			CHECK(!((operation.result_flags ^ native_flags) & KD_REG_ARITHMETIC_FLAGS));
			regs.dx = ~0UL;
			kd_memory_write_register(&regs, 2, width, operation.result_value);
			CHECK(regs.dx == expected);
		}
	}
	{
		const unsigned long values[] = { 0, 1, 0x7fffffff, 0x80000000,
			0xffffffff, 0x8000000000000000UL, ~0UL };
		unsigned int width, left, right, arithmetic;
		struct kd_regs before = regs;
		for (arithmetic = 0; arithmetic < 2; ++arithmetic)
		for (width = 32; width <= 64; width *= 2)
		for (left = 0; left < sizeof(values) / sizeof(values[0]); ++left)
		for (right = 0; right < sizeof(values) / sizeof(values[0]); ++right) {
			unsigned long expected = values[left], source_value = values[right], native_flags;
			input = site(arithmetic ? (width == 32 ? "653b10" : "65483b10") :
				(width == 32 ? "650110" : "65480110"),
				arithmetic ? KD_ORIGIN_MEMORY_COMPARE : KD_ORIGIN_MEMORY_ADD_MEMORY, width);
			cpu_data[0] = values[left];
			operation.source_value = source_value;
			operation.effective_offset = operation.result_value = operation.result_aux = 0;
			operation.input_flags = 0x897;
			if (arithmetic && width == 32)
				asm volatile("cmpl %k[right],%k[left]; pushfq; popq %[flags]"
					: [flags] "=r"(native_flags)
					: [left] "r"(source_value), [right] "r"(expected) : "cc", "memory");
			else if (arithmetic)
				asm volatile("cmpq %[right],%[left]; pushfq; popq %[flags]"
					: [flags] "=r"(native_flags)
					: [left] "r"(source_value), [right] "r"(expected) : "cc", "memory");
			else if (width == 32) {
				asm volatile("addl %k[right],%k[left]; pushfq; popq %[flags]"
					: [left] "+r"(expected), [flags] "=r"(native_flags)
					: [right] "r"(source_value) : "cc", "memory");
				expected |= values[left] & ~0xffffffffUL;
			} else
				asm volatile("addq %[right],%[left]; pushfq; popq %[flags]"
					: [left] "+r"(expected), [flags] "=r"(native_flags)
					: [right] "r"(source_value) : "cc", "memory");
			kd_origin_memory_apply(&operation);
			CHECK(cpu_data[0] == expected && operation.source_value == source_value);
			CHECK(!((operation.result_flags ^ native_flags) & KD_REG_ARITHMETIC_FLAGS));
			CHECK(!operation.result_value && !operation.result_aux &&
				!memcmp(&before, &regs, sizeof(regs)));
		}
	}
	CHECK(!syscall(SYS_arch_prctl, ARCH_SET_GS, saved_gs));
	printf("production GS memory decoder: %u checks passed\n", checks);
	return 0;
}
