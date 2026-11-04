/* SPDX-License-Identifier: GPL-2.0 */
/* Reference begin/run adapter with observed scalar-core and readiness calls.
 * This proves frame/packet bookkeeping, not actual lock or instruction effects. */
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint64_t u64;
#include "kd_reached.h"

#define THREAD_SIZE 1024UL
#define BASE 0x100000UL
#define ENTRY 0xffffffff81000100UL
#define CHECK(expression) do { \
	++checks; \
	if (!(expression)) { \
		fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #expression); \
		exit(1); \
	} \
} while (0)

struct kd_wait_request {
	void *identity;
	u64 generation;
};
struct kd_exec_continuation {
	struct kd_exec_continuation *root;
	struct kd_wait_request *request;
	struct kd_regs *packet;
	u64 generation;
	unsigned long stack_base;
};
struct kd_exec_frame {
	struct kd_exec_continuation *continuation;
	struct kd_regs *packet;
	unsigned int entry_abi, packet_state;
	unsigned long entry_ip, continuation_ip, continuation_sp;
	bool executed;
};

static struct kd_regs packet, other_packet;
static struct kd_wait_request request;
static struct kd_exec_continuation continuation;
static struct kd_exec_frame frame;
static struct kd_reached_state state;
static const struct kd_reached_ops kd_reached_frame_ops;
static unsigned int checks, begin_calls, run_calls, save_calls;
static unsigned int simulated_progress, seen_limit;
static enum kd_reached_result simulated_result;
static bool ready;
static int begin_result;
static char first_identity, next_identity;

static bool kd_reached_frame_ready(struct kd_exec_frame *candidate)
{
	return ready && candidate == &frame;
}

static struct kd_regs *kd_exec_frame_regs(struct kd_exec_frame *candidate)
{
	return candidate->packet;
}

static struct kd_exec_continuation *
kd_exec_frame_continuation(struct kd_exec_frame *candidate)
{
	return candidate->continuation;
}

static void kd_exec_frame_save_continuation(struct kd_exec_frame *candidate,
	const struct kd_regs *regs)
{
	++save_calls;
	CHECK(candidate == &frame && regs == &packet);
	candidate->continuation_ip = regs->ip;
	candidate->continuation_sp = regs->sp;
}

int kd_reached_begin(struct kd_reached_state *candidate, struct kd_regs *regs,
	unsigned int packet_state, u64 budget)
{
	++begin_calls;
	CHECK(candidate == &state && regs == &packet);
	CHECK(packet_state == KD_PACKET_FULL || packet_state == KD_PACKET_MINIMAL);
	if (begin_result)
		return begin_result;
	candidate->regs = regs;
	candidate->packet_state = KD_PACKET_FULL;
	candidate->budget = budget;
	candidate->sequence = 0;
	return 0;
}

enum kd_reached_result kd_reached_run(struct kd_reached_state *candidate,
	unsigned int instruction_limit)
{
	++run_calls;
	seen_limit = instruction_limit;
	CHECK(candidate == &state && candidate->regs == &packet);
	CHECK(candidate->budget >= simulated_progress);
	candidate->budget -= simulated_progress;
	candidate->sequence += simulated_progress;
	if (simulated_progress) {
		candidate->regs->ip += simulated_progress;
		candidate->regs->sp -= 8;
		candidate->regs->ax = 0xface;
	}
	return simulated_result;
}

#include "production.h"

static void reset(void)
{
	/* No live packet exists across fixture resets. */
	memset(&packet, 0, sizeof(packet));
	memset(&other_packet, 0, sizeof(other_packet));
	memset(&frame, 0, sizeof(frame));
	memset(&state, 0, sizeof(state));
	request.identity = &first_identity;
	request.generation = 7;
	continuation.root = &continuation;
	continuation.request = &request;
	continuation.packet = &packet;
	continuation.generation = request.generation;
	continuation.stack_base = BASE;
	packet.ip = ENTRY;
	packet.sp = BASE + 128;
	packet.bp = BASE + 160;
	frame.continuation = &continuation;
	frame.packet = &packet;
	frame.entry_ip = ENTRY;
	frame.entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	frame.packet_state = KD_PACKET_MINIMAL;
	ready = true;
	begin_calls = run_calls = save_calls = 0;
	simulated_progress = seen_limit = 0;
	simulated_result = KD_REACHED_SOURCE;
	begin_result = 0;
}

static void begin_valid(void)
{
	CHECK(!kd_exe_reached_begin(&frame, &state, 19));
	CHECK(begin_calls == 1 && frame.packet_state == KD_PACKET_FULL);
	CHECK(state.regs == &packet && state.context == &frame);
	CHECK(state.ops == &kd_reached_frame_ops && state.budget == 19);
	CHECK(state.owner_identity == request.identity);
	CHECK(state.owner_generation == request.generation);
}

static void entry_checks(void)
{
	reset();
	begin_valid();
	reset();
	packet.ip++;
	CHECK(kd_exe_reached_begin(&frame, &state, 19) == -EINVAL);
	CHECK(!begin_calls && frame.packet_state == KD_PACKET_MINIMAL);
	reset();
	packet.sp = BASE - 1;
	CHECK(kd_exe_reached_begin(&frame, &state, 19) == -EINVAL);
	CHECK(!begin_calls && !state.regs);
	reset();
	packet.sp = BASE + THREAD_SIZE - sizeof(unsigned long) + 1;
	CHECK(kd_exe_reached_begin(&frame, &state, 19) == -EINVAL);
	CHECK(!begin_calls && !state.regs);
	reset();
	continuation.stack_base = ULONG_MAX - THREAD_SIZE + 1;
	packet.sp = continuation.stack_base;
	CHECK(kd_exe_reached_begin(&frame, &state, 19) == -EINVAL);
	CHECK(!begin_calls && !state.regs);
	reset();
	frame.packet = &other_packet;
	CHECK(kd_exe_reached_begin(&frame, &state, 19) == -EINVAL);
	CHECK(!begin_calls && !state.regs);
	reset();
	frame.executed = true;
	CHECK(kd_exe_reached_begin(&frame, &state, 19) == -EINVAL);
	CHECK(!begin_calls);
	reset();
	CHECK(kd_exe_reached_begin(&frame, &state, 0) == -EINVAL);
	CHECK(!begin_calls);
	reset();
	begin_result = -EINVAL;
	CHECK(kd_exe_reached_begin(&frame, &state, 19) == -EINVAL);
	CHECK(begin_calls == 1 && frame.packet_state == KD_PACKET_MINIMAL);
}

static void reused_frame_checks(void)
{
	reset(); begin_valid();
	++request.generation;
	++continuation.generation;
	CHECK(kd_exe_reached_run(&frame, &state, 4) == KD_REACHED_PACKET);
	CHECK(!run_calls && !save_calls && !frame.executed && state.budget == 19);
	request.generation = state.owner_generation;
	continuation.generation = state.owner_generation;
	request.identity = &next_identity;
	CHECK(kd_exe_reached_run(&frame, &state, 4) == KD_REACHED_PACKET);
	CHECK(!run_calls && !save_calls && !frame.executed && state.budget == 19);
	request.identity = &first_identity;
	CHECK(kd_exe_reached_run(&frame, &state, 4) == KD_REACHED_SOURCE);
	CHECK(run_calls == 1 && !save_calls);
}

static void progress_checks(void)
{
	const enum kd_reached_result stops[] = {
		KD_REACHED_SOURCE, KD_REACHED_UNSUPPORTED, KD_REACHED_MEMORY,
	};
	unsigned int index;
	for (index = 0; index < sizeof(stops) / sizeof(stops[0]); ++index) {
		reset(); begin_valid();
		simulated_result = stops[index];
		simulated_progress = 2;
		CHECK(kd_exe_reached_run(&frame, &state, 4) == stops[index]);
		CHECK(run_calls == 1 && save_calls == 1 && frame.executed);
		CHECK(frame.continuation_ip == ENTRY + 2);
		CHECK(frame.continuation_sp == BASE + 120 && packet.ax == 0xface);
		CHECK(state.budget == 17 && begin_calls == 1 && seen_limit == 4);
	}
	reset(); begin_valid();
	CHECK(kd_exe_reached_run(&frame, &state, 4) == KD_REACHED_SOURCE);
	CHECK(run_calls == 1 && !save_calls && !frame.executed);
	CHECK(!frame.continuation_ip && !frame.continuation_sp);
	CHECK(packet.ip == ENTRY && packet.sp == BASE + 128 && state.budget == 19);
	reset(); begin_valid();
	simulated_progress = 1;
	simulated_result = KD_REACHED_EDGE;
	CHECK(kd_exe_reached_run(&frame, &state, 1) == KD_REACHED_EDGE);
	CHECK(state.budget == 18 && state.sequence == 1);
	simulated_result = KD_REACHED_SOURCE;
	CHECK(kd_exe_reached_run(&frame, &state, 2) == KD_REACHED_SOURCE);
	CHECK(state.budget == 17 && state.sequence == 2);
	CHECK(begin_calls == 1 && run_calls == 2 && save_calls == 2);
}

static void routing_checks(void)
{
	reset(); begin_valid();
	ready = false;
	CHECK(kd_exe_reached_run(&frame, &state, 4) == KD_REACHED_PACKET);
	CHECK(!run_calls);
	ready = true;
	CHECK(kd_exe_reached_run(&frame, &state, 0) == KD_REACHED_PACKET);
	CHECK(kd_exe_reached_run(&frame, &state, 65) == KD_REACHED_PACKET);
	CHECK(!run_calls);
	state.context = NULL;
	CHECK(kd_exe_reached_run(&frame, &state, 4) == KD_REACHED_PACKET);
	CHECK(!run_calls);
	state.context = &frame;
	state.regs = &other_packet;
	CHECK(kd_exe_reached_run(&frame, &state, 4) == KD_REACHED_PACKET);
	CHECK(!run_calls);
	state.regs = &packet;
	state.ops = NULL;
	CHECK(kd_exe_reached_run(&frame, &state, 4) == KD_REACHED_PACKET);
	CHECK(!run_calls);
	state.ops = &kd_reached_frame_ops;
	frame.packet_state = KD_PACKET_MINIMAL;
	CHECK(kd_exe_reached_run(&frame, &state, 4) == KD_REACHED_PACKET);
	CHECK(!run_calls);
}

int main(void)
{
	entry_checks();
	reused_frame_checks();
	progress_checks();
	routing_checks();
	printf("reference instruction adapter: %u checks, 0 failures\n", checks);
	return 0;
}
