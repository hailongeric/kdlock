/* SPDX-License-Identifier: GPL-2.0 */
/* Execute generated lowering only. Deliberate CALL-token inspection/mutation
 * below is an adversarial oracle, outside the admitted native-C caller promise.
 * No kernel helper, provider, physical-lock or source-lifetime proof is mocked
 * into an acceptance claim by this userspace executable. */
#include <limits.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#include "kd_regs.h"
#include "kd_jit_batch.h"
#include "exe_info.h"

extern unsigned char kd_native_wrapper[], kd_native_image_end[];
extern void fixture_invoke_clobber(struct kd_jit_batch_call *);
extern int fixture_hostile_strcmp(const char *, const char *);
extern long fixture_hostile_pad(char *, const char *, size_t);

unsigned long fixture_kind, fixture_attempted, fixture_completed, fixture_requested;
unsigned long fixture_return_flags, fixture_alignment_errors;
unsigned long fixture_precall_flags, fixture_helper_entry_flags, fixture_helper_entry_rcx;
unsigned long fixture_helper_output_flags, fixture_return_rcx, fixture_exit_flags, fixture_exit_rcx;
unsigned long fixture_invoke_padding, fixture_wrapper_stack_residue;
unsigned long fixture_terminal;
static unsigned long cmp_calls, pad_calls, corrupt_token;
static unsigned long *source_token;
static uintptr_t expected_di, expected_si, expected_cx;
static unsigned int checks, failures;

#define CHECK(condition) do { \
	checks++; \
	if (!(condition)) { \
		failures++; \
		fprintf(stderr, "line %u failed: %s\n", (unsigned int)__LINE__, #condition); \
	} \
} while (0)

_Static_assert(offsetof(struct kd_jit_batch_call, direct_strcmp) == 96, "strcmp result offset");
_Static_assert(offsetof(struct kd_jit_batch_call, direct_pad) == 104, "pad result offset");
#define ARITHMETIC_FLAGS 0x8d5UL /* CF, PF, AF, ZF, SF, OF */

static void check_helper_entry(void)
{
	CHECK((fixture_precall_flags & ARITHMETIC_FLAGS) == 0x890);
	CHECK((fixture_helper_entry_flags & ARITHMETIC_FLAGS) ==
	      (fixture_precall_flags & ARITHMETIC_FLAGS));
	CHECK(fixture_helper_entry_rcx == expected_cx);
}

int fixture_strcmp_body(const char *left, const char *right)
{
	check_helper_entry();
	CHECK((uintptr_t)left == expected_di && (uintptr_t)right == expected_si);
	CHECK(*source_token == 0x1005);
	cmp_calls++;
	while (*left && *left == *right) {
		left++;
		right++;
	}
	if (corrupt_token)
		*source_token = 0xabcdef;
	return (unsigned char)*left - (unsigned char)*right;
}

long fixture_pad_body(char *destination, const char *source, size_t count)
{
	size_t length = 0;

	check_helper_entry();
	CHECK((uintptr_t)destination == expected_di && (uintptr_t)source == expected_si && count == 64);
	CHECK(*source_token == 0x2005);
	pad_calls++;
	while (length + 1 < count && source[length]) {
		destination[length] = source[length];
		length++;
	}
	destination[length] = 0;
	if (corrupt_token)
		*source_token = 0xabcdef;
	if (source[length])
		return -7; /* -E2BIG, the original API's truncation result. */
	memset(destination + length + 1, 0, count - length - 1);
	return (long)length;
}

static void relocate(void)
{
	unsigned char *base = kd_native_wrapper;
	uintptr_t image_start = (uintptr_t)kd_native_wrapper;
	uintptr_t image_end = (uintptr_t)kd_native_image_end;
	size_t size;
	const unsigned char *footer;
	uint32_t offset, count;
	unsigned int footer_count = 0;
	long page = sysconf(_SC_PAGESIZE);
	uintptr_t first = image_start & ~((uintptr_t)page - 1);
	uintptr_t limit = (image_end + page - 1) & ~((uintptr_t)page - 1);

	/* The end label is a distinct linker symbol, not an array whose negative
	 * subscripts are valid C. Bound the byte span, then derive every read from
	 * the image's start rather than reading before the end-symbol object. */
	CHECK(image_end > image_start && image_end - image_start >= 64 &&
	      image_end - image_start <= KD_CODE_BLOCK_SIZE);
	if (failures)
		exit(1);
	size = image_end - image_start;
	footer = base + size - 16;
	CHECK(!memcmp(base + 41, "KDAB", 4));
	CHECK(base[45] == 1 && base[46] == 2 && base[47] == 28);
	CHECK(!memcmp(footer, "KDNC0001", 8));
	for (size_t index = 0; index + 8 <= size; index++)
		if (!memcmp(base + index, "KDNC0001", 8))
			footer_count++;
	CHECK(footer_count == 1);
	memcpy(&offset, footer + 8, 4);
	memcpy(&count, footer + 12, 4);
	CHECK(count == 2 && offset == size - 16 - count * 16);
	if (failures)
		exit(1);
	CHECK(mprotect((void *)first, limit - first, PROT_READ | PROT_WRITE | PROT_EXEC) == 0);
	for (unsigned int index = 0; index < count; index++) {
		uint32_t call_offset, service;
		uint64_t continuation;
		uintptr_t target;
		int64_t displacement;
		int32_t encoded;
		unsigned char *record = base + offset + index * 16;

		memcpy(&call_offset, record, 4);
		memcpy(&service, record + 4, 4);
		memcpy(&continuation, record + 8, 8);
		CHECK(service == index + 4);
		CHECK(continuation == (service == 4 ? 0x1005 : 0x2005));
		CHECK(call_offset >= 48 && call_offset + 5 <= offset && base[call_offset] == 0xe8);
		memcpy(&encoded, base + call_offset + 1, 4);
		CHECK(encoded == 0);
		target = service == 4 ? (uintptr_t)fixture_hostile_strcmp : (uintptr_t)fixture_hostile_pad;
		displacement = (int64_t)target - (int64_t)(uintptr_t)(base + call_offset + 5);
		CHECK(displacement >= INT32_MIN && displacement <= INT32_MAX);
		if (failures)
			exit(1);
		encoded = (int32_t)displacement;
		memcpy(base + call_offset + 1, &encoded, 4);
	}
	CHECK(mprotect((void *)first, limit - first, PROT_READ | PROT_EXEC) == 0);
}

static void reset_observations(void)
{
	fixture_attempted = fixture_completed = fixture_return_flags = fixture_alignment_errors = 0;
	fixture_precall_flags = fixture_helper_entry_flags = fixture_helper_entry_rcx = 0;
	fixture_helper_output_flags = fixture_return_rcx = fixture_exit_flags = fixture_exit_rcx = 0;
	fixture_wrapper_stack_residue = ~0UL;
	cmp_calls = pad_calls = 0;
}

static void check_case(unsigned long kind, unsigned long requested, const char *source,
		       const char *right, long expected_result, unsigned long corrupt, unsigned long seed)
{
	struct kd_regs packet, before;
	unsigned long stack[64], before_stack[64];
	unsigned char destination[66], expected_destination[64];
	unsigned int state = 1;
	unsigned long quota = kind ? 16 : 128;
	unsigned long expected_calls = corrupt ? 1 : (requested < quota ? requested : quota);
	unsigned long words[21];
	struct kd_jit_batch_call call = {
		.regs = &packet, .args = {0xfeed, 0xbeef}, .code = kd_native_wrapper + 32,
		.lock = 0x6000, .unlock = 0x7000, .entry_abi = 1, .packet_state = &state,
		.complete = 1, .direct_strcmp = ~0UL, .direct_pad = ~0UL,
	};

	for (unsigned int i = 0; i < 21; i++)
		words[i] = seed * 0x123456789UL + i * 0x10101UL;
	memcpy(&packet, words, sizeof(packet));
	for (unsigned int i = 0; i < 64; i++)
		stack[i] = 0x9000000000000000UL + i;
	memcpy(before_stack, stack, sizeof(stack));
	memset(destination, 0xa5, sizeof(destination));
	packet.ip = 0x1000;
	packet.sp = (unsigned long)&stack[32];
	packet.bp = (unsigned long)&stack[48];
	packet.di = kind ? (unsigned long)&destination[1] : (unsigned long)source;
	packet.si = kind ? (unsigned long)source : (unsigned long)right;
	packet.dx = kind ? 64 : packet.dx;
	before = packet;
	expected_di = packet.di;
	expected_si = packet.si;
	expected_cx = packet.cx;
	source_token = &stack[31];
	corrupt_token = corrupt;
	fixture_kind = kind;
	fixture_requested = requested;
	reset_observations();
	fixture_invoke_clobber(&call);
	CHECK(fixture_wrapper_stack_residue == (8 - fixture_invoke_padding));
	CHECK(state == (fixture_terminal ? 2U : 0U) && call.args[1] == 1);
	CHECK(fixture_alignment_errors == 0);
	CHECK(cmp_calls == (kind ? 0 : expected_calls));
	CHECK(pad_calls == (kind ? expected_calls : 0));
	CHECK(call.direct_strcmp == cmp_calls && call.direct_pad == pad_calls);
	CHECK(fixture_attempted == (corrupt ? 1 : expected_calls + (requested > quota)));
	CHECK(fixture_completed == (corrupt ? 0 : expected_calls));
	CHECK(call.args[0] == (corrupt ? 2UL : requested > quota ? 10UL : fixture_terminal ? 7UL : 0x1234UL));
	CHECK(packet.ip == (corrupt ? 0xabcdefUL : requested > quota ? (kind ? 0x4000UL : 0x3000UL) :
			    fixture_terminal ? 0x7777UL : 0x4444UL));
	CHECK(packet.sp == before.sp - (!corrupt && requested > quota ? 8 : 0));
	CHECK(packet.bp == before.bp);
	CHECK(stack[31] == (corrupt ? 0xabcdefUL : kind ? 0x2005UL : 0x1005UL));
	for (unsigned int i = 0; i < 64; i++)
		if (i != 31)
			CHECK(stack[i] == before_stack[i]);
	CHECK(packet.ax == (fixture_terminal ? before.ax : kind ? (unsigned long)expected_result :
			    (unsigned long)(unsigned int)expected_result));
	/* Every volatile except the actual result survives the native ABI call;
	 * the five logical special GPRs also remain in their own packet slots. */
	CHECK(packet.cx == before.cx && packet.dx == before.dx && packet.si == before.si && packet.di == before.di);
	CHECK(packet.r8 == before.r8 && packet.r9 == before.r9 && packet.r10 == before.r10 && packet.bx == before.bx);
	CHECK(packet.r11 == 0x1111222233334444UL && packet.r12 == 0x5555666677778888UL);
	CHECK(packet.r13 == before.r13 && packet.r14 == before.r14 && packet.r15 == before.r15);
	CHECK(packet.orig_ax == before.orig_ax && packet.cs == before.cs && packet.flags == before.flags && packet.ss == before.ss);
	CHECK((fixture_helper_output_flags & ARITHMETIC_FLAGS) == 0x55);
	if (!corrupt) {
		CHECK((fixture_return_flags & ARITHMETIC_FLAGS) ==
		      (fixture_helper_output_flags & ARITHMETIC_FLAGS));
		CHECK(fixture_return_rcx == before.cx);
	}
	if (corrupt || requested > quota) {
		unsigned long expected_flags = corrupt ? fixture_helper_output_flags : fixture_precall_flags;
		CHECK((fixture_exit_flags & ARITHMETIC_FLAGS) == (expected_flags & ARITHMETIC_FLAGS));
		CHECK(fixture_exit_rcx == before.cx);
	}
	if (kind) {
		size_t length = strlen(source);
		if (length > 63)
			length = 63;
		memset(expected_destination, 0, sizeof(expected_destination));
		memcpy(expected_destination, source, length);
		CHECK(destination[0] == 0xa5 && destination[65] == 0xa5);
		CHECK(!memcmp(destination + 1, expected_destination, 64));
	}
}

static void check_entry_refusal(void)
{
	struct kd_regs packet, before;
	unsigned long stack[64], args[2];
	unsigned int state;
	struct kd_jit_batch_call call = {
		.regs = &packet, .code = kd_native_wrapper + 32, .entry_abi = 1,
		.packet_state = &state, .complete = 1,
	};

	memset(&packet, 0x3c, sizeof(packet));
	packet.sp = (unsigned long)&stack[32];
	packet.bp = (unsigned long)&stack[48];
	packet.ip = 0x1000;
	before = packet;
	reset_observations();
	for (unsigned int offset = 0; offset <= 16; offset += 16) {
		args[0] = args[1] = ~0UL;
		((void (*)(struct kd_regs *, unsigned long *))(kd_native_wrapper + offset))(&packet, args);
		CHECK(args[0] == 6 && args[1] == 0 && !memcmp(&packet, &before, sizeof(packet)));
		CHECK(cmp_calls == 0 && pad_calls == 0);
	}
	/* Even a caller that fabricates MINIMAL cannot enter an interior source
	 * continuation through the production root-only generated dispatcher. */
	state = 1;
	packet.ip = 0x1005;
	fixture_invoke_clobber(&call);
	CHECK(state == 0 && call.args[0] == 2 && call.args[1] == 0 && packet.ip == 0x1005);
	CHECK(cmp_calls == 0 && pad_calls == 0 && call.direct_strcmp == 0 && call.direct_pad == 0);
	/* FULL is not an alternate path for resetting this invocation's quotas. */
	pid_t child = fork();
	CHECK(child >= 0);
	if (child == 0) {
		struct rlimit no_core = {0, 0};
		setrlimit(RLIMIT_CORE, &no_core);
		state = 0;
		packet.ip = 0x1000;
		fixture_invoke_clobber(&call);
		_exit(17);
	}
	if (child > 0) {
		int status = 0;
		CHECK(waitpid(child, &status, 0) == child);
		CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGILL);
	}
}

int main(void)
{
	char long_source[81];

	memset(long_source, 'z', 80);
	long_source[80] = 0;
	relocate();
	for (fixture_invoke_padding = 0; fixture_invoke_padding <= 8; fixture_invoke_padding += 8) {
		for (unsigned long seed = 1; seed <= 3; seed++) {
			fixture_terminal = 0;
			check_case(0, 1, "abc", "abd", -1, 0, seed);
			check_case(0, 1, "same", "same", 0, 0, seed);
			check_case(0, 1, "z", "a", 25, 0, seed);
			check_case(0, 128, "abc", "abd", -1, 0, seed);
			check_case(0, 129, "abc", "abd", -1, 0, seed);
			check_case(1, 1, "task", NULL, 4, 0, seed);
			check_case(1, 1, "", NULL, 0, 0, seed);
			check_case(1, 16, long_source, NULL, -7, 0, seed);
			check_case(1, 17, "task", NULL, 4, 0, seed);
			check_case(0, 1, "abc", "abd", -1, 1, seed);
			check_case(1, 1, "task", NULL, 4, 1, seed);
			/* Native helpers return straight to the reduced terminal unlock.
			 * AX/BX sentinels prove that no FULL export was substituted. */
			fixture_terminal = 1;
			check_case(0, 1, "abc", "abd", -1, 0, seed);
			check_case(1, 1, "task", NULL, 4, 0, seed);
		}
	}
	fixture_invoke_padding = 0;
	fixture_terminal = 0;
	check_entry_refusal();
	printf("native-call executable wrapper: %u checks, %u failures; userspace lowering only\n", checks, failures);
	return failures != 0;
}
