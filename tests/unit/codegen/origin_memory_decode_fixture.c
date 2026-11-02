/* SPDX-License-Identifier: GPL-2.0 */
/* Production decoder/EA only. CPU/context service is a separate live check. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int8_t s8;
typedef int32_t s32;
#include "kd_regs.h"
#include "kd_origin_memory.h"
#include "kd_image.h"

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
#include "production.h"

static unsigned int checks;
#define CHECK(value) do { ++checks; if (!(value)) { \
	fprintf(stderr, "FAIL line=%u: %s\n", __LINE__, #value); exit(1); } } while (0)

static struct kd_origin_memory_site site(const char *hex, u8 op, u8 width)
{
	struct kd_origin_memory_site result = { .ip = 0x1000, .operation = op, .width = width };
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
	const struct { const char *hex; u8 op, width; unsigned long expected; } accepted[] = {
		{ "65ff00", 1, 32, 0x1000 },
		{ "6548ff08", 2, 64, 0x1000 },
		{ "6549ff45f0", 1, 64, 0x4ff0 },
		{ "654bff44e520", 1, 64, 0x5030 },
		{ "65ff05fcffffff", 1, 32, 0x1003 },
		{ "6548ff0c25f0ffffff", 2, 64, ~15UL },
		{ "6548ff0424", 1, 64, 0x6000 },
	};
	const char *rejected[] = { "64ff00", "f06548ff00", "656748ff00", "6566ff00",
		"65ff10", "65ffff", "65ff04", "65ff05000000" };

	for (i = 0; i < sizeof(accepted) / sizeof(accepted[0]); ++i) {
		input = site(accepted[i].hex, accepted[i].op, accepted[i].width);
		CHECK(!kd_origin_memory_decode(&input, &regs, &address));
		CHECK(address == accepted[i].expected);
	}
	for (i = 0; i < sizeof(rejected) / sizeof(rejected[0]); ++i) {
		input = site(rejected[i], 1, 32);
		CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	}
	input = site("65ff00", 1, 32);
	input.reserved = 1;
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	input.reserved = 0;
	input.opcode[15] = 1;
	CHECK(kd_origin_memory_decode(&input, &regs, &address) == -EPROTO);
	input.opcode[15] = 0;
	input.next_ip++;
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
	printf("production GS memory decoder: %u checks passed\n", checks);
	return 0;
}
