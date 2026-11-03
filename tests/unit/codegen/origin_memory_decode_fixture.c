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
		.flags = op >= KD_ORIGIN_MEMORY_LOAD ? KD_ORIGIN_MEMORY_READ : 0 };
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
};

static int reached_read(void *context, unsigned long address, void *out,
	unsigned int size)
{
	struct reached_source *source = context;

	++source->calls;
	if (size != 1 || address < 0x1000 || address - 0x1000 >= source->length)
		return -ENODATA;
	*(u8 *)out = source->bytes[address - 0x1000];
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
	};
	const char *rejected[] = { "64ff00", "f06548ff00", "656748ff00", "6566ff00",
		"65ff10", "65ffff", "65ff04", "65ff05000000" };

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
	CHECK(!syscall(SYS_arch_prctl, ARCH_GET_GS, &saved_gs));
	CHECK(!syscall(SYS_arch_prctl, ARCH_SET_GS, cpu_data));
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
	CHECK(!syscall(SYS_arch_prctl, ARCH_SET_GS, saved_gs));
	printf("production GS memory decoder: %u checks passed\n", checks);
	return 0;
}
