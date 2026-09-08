/* SPDX-License-Identifier: GPL-2.0 */
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

struct task_struct {
	int pid;
};
struct list_head {
	struct list_head *next, *prev;
};
#include "frame_types.h"

static struct kd_exec_context kd_exec_context[2];
static struct task_struct owners[] = { { 11 }, { 12 } };
static struct task_struct waiters[KD_EXEC_MAX_NESTING];
static struct task_struct *current = &owners[0];
static unsigned int cpu, checks, failures;
static unsigned long kd_exec_invariant_failures;
static char report[1024];
typedef unsigned int atomic_t;
#define ATOMIC_INIT(value) (value)
#define atomic_read(p) (*(p))
#define raw_smp_processor_id() cpu
#define preempt_count() 1
#define irqs_disabled() false
#define pr_info(...) ((void)snprintf(report, sizeof(report), __VA_ARGS__))

static unsigned int atomic_cmpxchg(atomic_t *value, unsigned int old,
				   unsigned int replacement)
{
	unsigned int before = *value;

	if (before == old)
		*value = replacement;
	return before;
}

#define this_cpu_ptr(p) (&(*(p))[cpu])
#define READ_ONCE(x) (x)
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, value) (*(p) = (value))
#define atomic64_inc(p) (++*(p))
#define WARN_ON_ONCE(x) ((void)(x))
static unsigned int probe_calls;

static struct kd_exec_frame *
counted_frame_push(const struct pt_regs *regs, unsigned long entry,
		   unsigned long outer, void *waiter, void *outgoing,
		   unsigned int held, unsigned long gs,
		   struct task_struct *task)
{
	probe_calls++;
	return kd_exec_frame_push(regs, entry, outer, waiter, outgoing, held,
				  gs, task);
}

#include "frame_code.h"

#define CHECK(expr)                                                     \
	do {                                                            \
		checks++;                                               \
		if (!(expr)) {                                          \
			fprintf(stderr, "FAIL line %d: %s\n", __LINE__, \
				#expr);                                 \
			failures++;                                     \
		}                                                       \
	} while (0)

static struct pt_regs registers(unsigned int seed)
{
	struct pt_regs regs;
	unsigned char *bytes = (unsigned char *)&regs;
	unsigned int i;

	for (i = 0; i < sizeof(regs); i++)
		bytes[i] = 1 + (seed + i) % 254;
	return regs;
}

static struct kd_exec_frame *push(unsigned int index)
{
	struct pt_regs regs = registers(index);
	struct kd_exec_context before = *kd_exec_current_context();
	struct kd_exec_frame *frame;

	waiters[index].pid = 100 + index;
	frame = kd_exec_frame_push(&regs, 0x1000 + index, 0x2000 + index,
				   &waiters[index], &waiters[index], index + 1,
				   0x3000 + index, &waiters[index]);
	CHECK(frame == &kd_exec_current_context()->frames[index]);
	if (!frame)
		return NULL;
	CHECK(frame->parent ==
	      (index ? &kd_exec_current_context()->frames[index - 1] : NULL));
	CHECK(!memcmp(before.frames, kd_exec_current_context()->frames,
		      index * sizeof(*frame)));
	CHECK(!memcmp(&frame->regs, &regs, sizeof(regs)));
	CHECK(frame->depth == index && frame->held_lock_depth == index + 1);
	CHECK(frame->entry_ip == 0x1000 + index &&
	      frame->outer_lock_addr == 0x2000 + index);
	CHECK(frame->gsbase == 0x3000 + index &&
	      frame->logical_task == &waiters[index]);
	CHECK(frame->logical_pid == 100 + (int)index &&
	      frame->waiter == &waiters[index]);
	CHECK(frame->outgoing_rsp_ptr == &waiters[index]);
	CHECK(kd_exec_current_frame() == frame && !kd_exec_context_busy());
	CHECK(kd_exec_current_context()->owner == current);
	CHECK(kd_exec_context_validate(kd_exec_current_context()));
	/* Fields not interpreted by admission still must survive a full refusal. */
	memset(&frame->saved_combiner, 0x50 + index,
	       sizeof(frame->saved_combiner));
	return frame;
}

static void refused(const struct pt_regs *regs, unsigned long gs,
		    struct task_struct *task, unsigned int held)
{
	struct kd_exec_context before = *kd_exec_current_context();
	struct kd_exec_frame *frame = kd_exec_current_frame();

	CHECK(!kd_exec_frame_push(regs, 0x1000, 0x2000, task, task, held, gs,
				  task));
	CHECK(!memcmp(&before, kd_exec_current_context(), sizeof(before)));
	CHECK(kd_exec_current_frame() == frame);
}

static void exercise(unsigned int depth)
{
	struct pt_regs regs = registers(99), output;
	struct kd_exec_context *ctx = kd_exec_current_context();
	struct kd_exec_frame *frame;
	unsigned int i;

	kd_exec_context_reset(ctx);
	CHECK(!kd_exec_current_frame() && !kd_exec_context_busy());
	for (i = 0; i < depth; i++) {
		if (!push(i))
			return;
	}
	refused(NULL, 1, current, 1);
	refused(&regs, 0, current, 1);
	refused(&regs, 1, NULL, 1);
	if (depth == KD_EXEC_MAX_NESTING) {
		for (i = 0; i < 4; i++)
			refused(&regs, 1, current, 1);
	} else {
		refused(&regs, 1, current, KD_EXEC_MAX_LOCK_DEPTH + 1);
	}
	if (depth) {
		current = &owners[1];
		CHECK(kd_exec_context_busy() && !kd_exec_current_frame());
		refused(&regs, 1, current, 1);
		current = &owners[0];
		frame = kd_exec_current_frame();
		CHECK(frame == &ctx->frames[depth - 1]);
		/* Invalid lower state is a separate refusal, not pool exhaustion. */
		ctx->frames[0].gsbase = 0;
		refused(&regs, 1, current, 1);
		ctx->frames[0].gsbase = 0x3000;
		CHECK(kd_exec_frame_pop(frame, NULL) == -EBUSY);
		if (depth > 1)
			CHECK(kd_exec_frame_pop(&ctx->frames[0], NULL) ==
			      -EINVAL);
	}
	while (ctx->depth) {
		struct kd_exec_context before;

		frame = kd_exec_current_frame();
		regs = frame->regs;
		kd_exec_frame_set_state(frame, KD_EXEC_FRAME_ERROR);
		before = *ctx;
		CHECK(kd_exec_frame_pop(frame, &output) == 0);
		CHECK(!memcmp(&regs, &output, sizeof(regs)));
		CHECK(!memcmp(before.frames, ctx->frames,
			      ctx->depth * sizeof(*frame)));
		CHECK(!memcmp(frame, &(struct kd_exec_frame){ 0 },
			      sizeof(*frame)));
		CHECK(kd_exec_context_validate(ctx));
	}
	CHECK(!ctx->owner && !kd_exec_current_frame());
}

static void probe(unsigned int depth, unsigned int invalid)
{
	struct kd_exec_context *ctx;
	struct kd_exec_context before;
	struct kd_exec_frame *frame;
	unsigned int i;

	cpu = 0;
	current = &owners[0];
	ctx = kd_exec_current_context();
	kd_exec_context_reset(ctx);
	memset(&kd_capacity, 0, sizeof(kd_capacity));
	kd_capacity_claimed = 0;
	probe_calls = 0;
	for (i = 0; i < depth; i++) {
		if (!push(i))
			return;
	}
	frame = kd_exec_current_frame();
	if (invalid == 1)
		current = &owners[1];
	if (invalid == 2)
		ctx->frames[0].gsbase = 0;
	before = *ctx;
	kd_exec_selftest_capacity_probe(frame);
	kd_exec_selftest_capacity_report();
	CHECK(!memcmp(&before, ctx, sizeof(before)));
	CHECK(probe_calls ==
	      (unsigned int)(depth == KD_EXEC_MAX_NESTING && !invalid));
	if (depth < KD_EXEC_MAX_NESTING) {
		CHECK(!kd_capacity_claimed && !kd_capacity.attempted &&
		      !kd_capacity.ready);
		CHECK(strstr(report, "claimed=0 ready=0 attempted=0"));
	} else {
		CHECK(kd_capacity_claimed == 1 && kd_capacity.ready);
		CHECK(kd_capacity.attempted == !invalid);
		CHECK(kd_capacity.valid_before == !invalid);
		if (!invalid) {
			CHECK(kd_capacity.rejected && kd_capacity.unchanged &&
			      kd_capacity.valid_after);
			CHECK(!memcmp(&kd_capacity.before, &before,
				      sizeof(before)));
			CHECK(kd_capacity.depth == depth &&
			      kd_capacity.cpu == cpu);
			CHECK(kd_capacity.entry == frame->entry_ip &&
			      kd_capacity.outer == frame->outer_lock_addr);
			CHECK(kd_capacity.task == frame->logical_pid &&
			      kd_capacity.owner == current->pid);
			CHECK(strstr(
				report,
				"claimed=1 ready=1 attempted=1 rejected=1 unchanged=1"));
			/* A second callback must not overwrite the first probe's evidence. */
			ctx->frames[0].regs.ax = 0;
			kd_exec_selftest_capacity_probe(frame);
			CHECK(probe_calls == 1);
			CHECK(!memcmp(&kd_capacity.before, &before,
				      sizeof(before)));
			CHECK(kd_capacity.unchanged);
		}
	}
	current = &owners[0];
	kd_exec_context_reset(ctx);
}

int main(void)
{
	unsigned int depth, cycle;

	CHECK(sizeof(struct pt_regs) == 168 &&
	      sizeof(struct kd_exec_frame) == 656);
	for (cycle = 0; cycle < 3; cycle++) {
		for (depth = 0; depth <= KD_EXEC_MAX_NESTING; depth++) {
			for (cpu = 0; cpu < 2; cpu++) {
				struct kd_exec_context other =
					kd_exec_context[1 - cpu];

				exercise(depth);
				CHECK(!memcmp(&other, &kd_exec_context[1 - cpu],
					      sizeof(other)));
			}
		}
	}
	for (depth = 0; depth <= KD_EXEC_MAX_NESTING; depth++)
		probe(depth, 0);
	probe(KD_EXEC_MAX_NESTING, 1);
	probe(KD_EXEC_MAX_NESTING, 2);
	CHECK(kd_exec_invariant_failures == 0);
	printf("production frame capacity: checks=%u failures=%u regs=%zu frame=%zu context=%zu\n",
	       checks, failures, sizeof(struct pt_regs),
	       sizeof(struct kd_exec_frame), sizeof(struct kd_exec_context));
	return failures ? 1 : 0;
}
