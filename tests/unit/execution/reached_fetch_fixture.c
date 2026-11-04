/* SPDX-License-Identifier: GPL-2.0 */
/* Exact production fetch; source residency and family refs are observed
 * substitutes here. Separate component fixtures prove their own lifetimes. */
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
#define KD_REACHED_MAX_BYTES 15
#define CHECK(test) do { ++checks; if (!(test)) { \
	fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #test); exit(1); } } while (0)

struct kd_family_ref { bool valid; };
struct kd_family_instruction {
	unsigned long source_ip;
	unsigned long generation;
	u8 length, bytes[KD_REACHED_MAX_BYTES];
};
struct kd_reached_session {
	bool initialized;
	struct kd_family_ref authority;
	const struct kd_family_instruction *fetch_instruction;
	unsigned long fetch_ip;
	u8 fetch_length;
	u8 fetch_bytes[KD_REACHED_MAX_BYTES];
};
struct kd_regs { unsigned long ip; };
struct kd_exec_continuation {
	bool reached_active;
	struct kd_reached_session *reached;
	struct kd_regs *packet;
};
struct kd_exec_frame { struct kd_exec_continuation *continuation; };

static u8 source[32];
static struct kd_family_instruction cached;
static struct kd_reached_session session;
static struct kd_regs packet;
static struct kd_exec_continuation continuation;
static struct kd_exec_frame frame;
static unsigned int checks, pin_calls, copy_calls, candidate_calls;
static unsigned int available, maximum_pin, maximum_copy;
static unsigned int pin_sizes[16], copy_sizes[16];
static bool ready;

static bool kd_reached_frame_ready(struct kd_exec_frame *candidate)
{
	return ready && candidate == &frame;
}

static struct kd_exec_continuation *
kd_exec_frame_continuation(struct kd_exec_frame *candidate)
{
	return candidate->continuation;
}

static const struct kd_family_instruction *
kd_family_cache_candidate(const struct kd_family_ref *authority, unsigned long address)
{
	++candidate_calls;
	CHECK(authority == &session.authority);
	return authority->valid && address == cached.source_ip ? &cached : NULL;
}

static bool readable(unsigned long address, unsigned int size)
{
	unsigned long base = (unsigned long)source;

	return address >= base && address - base <= available &&
		size <= available - (address - base);
}

static int kd_source_pin_text_range(unsigned long address, unsigned int size)
{
	CHECK(pin_calls < 16);
	pin_sizes[pin_calls++] = size;
	return readable(address, size) && size <= maximum_pin ? 0 : -EFAULT;
}

static int copy_from_kernel_nofault(void *out, const void *in, unsigned int size)
{
	CHECK(copy_calls < 16);
	copy_sizes[copy_calls++] = size;
	if (!readable((unsigned long)in, size) || size > maximum_copy)
		return -EFAULT;
	memcpy(out, in, size);
	return 0;
}

#include "production.h"

static void reset(void)
{
	source[0] = 0x48; source[1] = 0x89; source[2] = 0xe5; source[3] = 0x90;
	cached.source_ip = (unsigned long)source;
	cached.length = 3;
	memcpy(cached.bytes, source, cached.length);
	cached.generation = 11;
	session.initialized = session.authority.valid = true;
	session.fetch_instruction = NULL;
	session.fetch_length = 0;
	packet.ip = (unsigned long)source;
	continuation.reached_active = true;
	continuation.reached = &session;
	continuation.packet = &packet;
	frame.continuation = &continuation;
	ready = true;
	pin_calls = copy_calls = candidate_calls = 0;
	available = sizeof(source);
	maximum_pin = maximum_copy = KD_REACHED_MAX_BYTES;
}

static void fresh_candidate(void)
{
	u8 output[4] = { 0 };

	reset();
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, output, 1));
	CHECK(output[0] == 0x48 && !session.fetch_instruction && session.fetch_length == 15);
	CHECK(pin_calls == 1 && copy_calls == 1 && candidate_calls == 0);
	CHECK(pin_sizes[0] == 15 && copy_sizes[0] == 15);
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip + 1, output, 2));
	CHECK(output[0] == 0x89 && output[1] == 0xe5);
	CHECK(pin_calls == 1 && copy_calls == 1 && candidate_calls == 0);
	/* The optional window contains actual source bytes, including this
	 * decoder request beyond the old cache record's complete length. */
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip + 2, output, 2));
	CHECK(output[0] == 0xe5 && output[1] == 0x90 && pin_calls == 1 && copy_calls == 1);
	source[14] = 0xaa; source[15] = 0xbb;
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip + 14, output, 2));
	CHECK(output[0] == 0xaa && output[1] == 0xbb && pin_calls == 2 && copy_calls == 2);
}

static void changed_between_steps(void)
{
	u8 value;

	reset();
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, &value, 1));
	/* Change the input before starting a new step at its source PC. No
	 * concurrent text change inside a partially decoded step is modeled. */
	source[1] = 0x8b;
	pin_calls = copy_calls = candidate_calls = 0;
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, &value, 1));
	CHECK(value == 0x48 && !session.fetch_instruction);
	CHECK(pin_calls == 1 && copy_calls == 1 && pin_sizes[0] == 15 && copy_sizes[0] == 15);
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip + 1, &value, 1));
	CHECK(value == 0x8b && cached.bytes[1] == 0x89);
	CHECK(pin_calls == 1 && copy_calls == 1 && candidate_calls == 0);
}

static void unavailable_complete_candidate(void)
{
	u8 value;

	reset(); maximum_pin = 1;
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, &value, 1));
	CHECK(value == source[0] && !session.fetch_instruction);
	CHECK(pin_calls == 3 && copy_calls == 1 && pin_sizes[0] == 15 &&
		pin_sizes[1] == 3 && pin_sizes[2] == 1 && !session.fetch_length);
	reset(); maximum_copy = 1;
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, &value, 1));
	CHECK(value == source[0] && !session.fetch_instruction && !session.fetch_length &&
		pin_calls == 3 && copy_calls == 3);
	reset(); available = 1;
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, &value, 1));
	CHECK(value == source[0] && !session.fetch_instruction && !session.fetch_length &&
		pin_calls == 3 && copy_calls == 1);
	reset(); available = 3;
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, &value, 1));
	CHECK(value == source[0] && session.fetch_instruction == &cached && !session.fetch_length &&
		pin_calls == 2 && copy_calls == 1);
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip + 2, &value, 1));
	CHECK(value == 0xe5 && pin_calls == 2 && copy_calls == 1);
	reset(); available = 1; source[0] = 0x90;
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, &value, 1));
	CHECK(value == 0x90 && !session.fetch_length && pin_calls == 3 && copy_calls == 1);
	CHECK(kd_reached_frame_fetch(&frame, packet.ip + 1, &value, 1) == -EFAULT);
}

static void authority_and_bounds(void)
{
	u8 value = 0xaa;

	reset(); session.authority.valid = false;
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, &value, 1));
	CHECK(value == source[0] && !session.fetch_instruction && candidate_calls == 0);
	CHECK(pin_calls == 1 && copy_calls == 1 && pin_sizes[0] == 15);
	reset(); ready = false;
	CHECK(kd_reached_frame_fetch(&frame, packet.ip, &value, 1) == -EINVAL);
	CHECK(!pin_calls && !copy_calls && !candidate_calls);
	reset();
	CHECK(kd_reached_frame_fetch(&frame, packet.ip, &value, 0) == -EINVAL);
	CHECK(kd_reached_frame_fetch(&frame, packet.ip, &value, 16) == -EINVAL);
	CHECK(kd_reached_frame_fetch(&frame, ULONG_MAX, &value, 1) == -EINVAL);
	CHECK(!pin_calls && !copy_calls && !candidate_calls);
	continuation.reached_active = false;
	CHECK(!kd_reached_frame_fetch(&frame, packet.ip, &value, 1));
	CHECK(!candidate_calls && pin_calls == 1 && copy_calls == 1);
}

int main(void)
{
	fresh_candidate();
	changed_between_steps();
	unavailable_complete_candidate();
	authority_and_bounds();
	printf("production reached fetch: %u checks, 0 failures\n", checks);
	return 0;
}
