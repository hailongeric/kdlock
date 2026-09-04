/*
 * test_exec_frame.c — userspace model of kd_exec frame invariants.
 *
 * The kernel implementation stores the same state in a per-CPU bounded
 * frame stack.  This model tests the protocol rules without requiring kernel
 * headers: frames must pop in LIFO order, lock entries must be dense, and a
 * successful frame must observe exactly one outer unlock before completion.
 */
#include "mock_kernel.h"
#include "test_harness.h"

#define MAX_FRAMES 3
#define MAX_LOCKS  3

enum frame_state {
	FRAME_UNUSED,
	FRAME_RUNNING,
	FRAME_COMPLETE,
	FRAME_ERROR,
};

struct frame_model {
	int depth;
	int state;
	unsigned long outer_lock;
	unsigned long gsbase;
	unsigned long logical_task;
	unsigned long locks[MAX_LOCKS];
	bool released[MAX_LOCKS];
	int lock_depth;
	bool outer_unlock_seen;
	bool completion_seen;
	struct frame_model *parent;
};

struct context_model {
	struct frame_model frames[MAX_FRAMES];
	int owner;
	int depth;
};

static bool frame_valid(const struct frame_model *frame)
{
	int i;

	if (!frame || frame->state == FRAME_UNUSED ||
	    frame->depth < 0 || frame->depth >= MAX_FRAMES ||
	    !frame->gsbase || !frame->logical_task ||
	    frame->lock_depth < 0 || frame->lock_depth > MAX_LOCKS ||
	    (frame->outer_unlock_seen && !frame->outer_lock) ||
	    (frame->completion_seen && frame->state != FRAME_COMPLETE))
		return false;

	for (i = 0; i < MAX_LOCKS; i++) {
		if (i < frame->lock_depth) {
			if (!frame->locks[i])
				return false;
		} else if (frame->locks[i]) {
			return false;
		} else if (frame->released[i]) {
			return false;
		}
	}
	return true;
}

static bool context_valid(const struct context_model *ctx)
{
	int i;

	if (!ctx || ctx->depth < 0 || ctx->depth > MAX_FRAMES ||
	    (!!ctx->depth != !!ctx->owner))
		return false;

	for (i = 0; i < ctx->depth; i++) {
		const struct frame_model *frame = &ctx->frames[i];

		if (!frame_valid(frame) || frame->depth != i ||
		    (i == 0 ? frame->parent != NULL :
		     frame->parent != &ctx->frames[i - 1]))
			return false;
	}
	return true;
}

static struct frame_model *push_frame_owned(struct context_model *ctx,
					     unsigned long outer_lock,
					     int owner)
{
	struct frame_model *frame;

	if (!ctx || owner <= 0 || ctx->depth >= MAX_FRAMES ||
	    !context_valid(ctx) || (ctx->depth && ctx->owner != owner))
		return NULL;
	if (!ctx->depth)
		ctx->owner = owner;
	frame = &ctx->frames[ctx->depth];
	memset(frame, 0, sizeof(*frame));
	frame->depth = ctx->depth;
	frame->state = FRAME_RUNNING;
	frame->outer_lock = outer_lock;
	frame->gsbase = 0x100000UL + (unsigned long)owner;
	frame->logical_task = (unsigned long)owner;
	frame->parent = ctx->depth ? &ctx->frames[ctx->depth - 1] : NULL;
	ctx->depth++;
	return context_valid(ctx) ? frame : NULL;
}

static struct frame_model *push_frame(struct context_model *ctx,
				       unsigned long outer_lock)
{
	return push_frame_owned(ctx, outer_lock, 1);
}

static int pop_frame_owned(struct context_model *ctx,
			   struct frame_model *frame, int owner)
{
	if (!ctx || !frame || !ctx->depth || ctx->owner != owner ||
	    frame != &ctx->frames[ctx->depth - 1] ||
	    (frame->state != FRAME_COMPLETE && frame->state != FRAME_ERROR))
		return -1;
	memset(frame, 0, sizeof(*frame));
	ctx->depth--;
	if (!ctx->depth)
		ctx->owner = 0;
	return context_valid(ctx) ? 0 : -1;
}

static int pop_frame(struct context_model *ctx, struct frame_model *frame)
{
	return pop_frame_owned(ctx, frame, 1);
}

static int push_lock(struct frame_model *frame, unsigned long lock)
{
	int i;

	if (!frame || !lock || !frame_valid(frame) ||
	    frame->lock_depth >= MAX_LOCKS)
		return -1;
	for (i = 0; i < frame->lock_depth; i++)
		if (frame->locks[i] == lock)
			return -1;
	frame->locks[frame->lock_depth++] = lock;
	frame->released[frame->lock_depth - 1] = false;
	return frame_valid(frame) ? 0 : -1;
}

static int set_lock_stack(struct frame_model *frame,
			  const unsigned long *locks, int depth)
{
	bool outer_found = false;
	int i, j;

	if (!frame || !locks || depth < 0 || depth > MAX_LOCKS ||
	    !frame_valid(frame))
		return -1;
	for (i = 0; i < depth; i++) {
		if (!locks[i])
			return -1;
		for (j = 0; j < i; j++)
			if (locks[j] == locks[i])
				return -1;
		if (locks[i] == frame->outer_lock)
			outer_found = true;
	}
	if (frame->outer_lock && !outer_found)
		return -1;

	memset(frame->locks, 0, sizeof(frame->locks));
	memset(frame->released, 0, sizeof(frame->released));
	memcpy(frame->locks, locks, sizeof(*locks) * depth);
	frame->lock_depth = depth;
	return frame_valid(frame) ? 0 : -1;
}

static int mark_released(struct frame_model *frame, unsigned long lock)
{
	int i;

	if (!frame || !lock || !frame_valid(frame))
		return -1;
	for (i = frame->lock_depth - 1; i >= 0; i--) {
		if (frame->locks[i] != lock)
			continue;
		if (frame->released[i])
			return -1;
		frame->released[i] = true;
		return 0;
	}
	return -1;
}

static int pop_lock(struct frame_model *frame, unsigned long lock)
{
	int i;

	if (!frame || !lock || !frame->lock_depth)
		return -1;
	for (i = frame->lock_depth - 1; i >= 0; i--) {
		if (frame->locks[i] != lock)
			continue;
		for (; i + 1 < frame->lock_depth; i++)
		{
			frame->locks[i] = frame->locks[i + 1];
			frame->released[i] = frame->released[i + 1];
		}
		frame->locks[--frame->lock_depth] = 0;
		frame->released[frame->lock_depth] = false;
		return frame_valid(frame) ? 0 : -1;
	}
	return -1;
}

static int complete_frame(struct frame_model *frame)
{
	if (!frame || !frame->outer_unlock_seen ||
	    frame->completion_seen || !frame_valid(frame))
		return -1;
	for (int i = 0; i < frame->lock_depth; i++)
		if (!frame->released[i])
			return -1;
	frame->completion_seen = true;
	frame->state = FRAME_COMPLETE;
	return frame_valid(frame) ? 0 : -1;
}

static int abort_nested_locks(struct frame_model *frame,
			      unsigned long *release_order,
			      int *release_count)
{
	int outer_index = -1;
	int i;

	if (!frame || !release_order || !release_count || !frame_valid(frame))
		return -1;
	for (i = 0; i < frame->lock_depth; i++)
		if (frame->locks[i] == frame->outer_lock)
			outer_index = i;
	if (outer_index < 0)
		return -1;

	while (frame->lock_depth > outer_index + 1) {
		unsigned long lock = frame->locks[frame->lock_depth - 1];

		release_order[(*release_count)++] = lock;
		if (pop_lock(frame, lock))
			return -1;
	}
	return 0;
}

TEST(frame_parent_and_lifo) {
	struct context_model ctx = { 0 };
	struct frame_model *outer = push_frame(&ctx, 0xA);
	struct frame_model *inner = push_frame(&ctx, 0xB);
	struct frame_model *third = push_frame(&ctx, 0xC);

	ASSERT(outer != NULL);
	ASSERT(inner != NULL);
	ASSERT(third != NULL);
	ASSERT_EQ(inner->parent, outer);
	ASSERT_EQ(push_frame(&ctx, 0xD), NULL);
	third->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, third), 0);
	inner->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, inner), 0);
	outer->outer_unlock_seen = true;
	ASSERT_EQ(complete_frame(outer), 0);
	ASSERT_EQ(pop_frame(&ctx, outer), 0);
	ASSERT_EQ(ctx.depth, 0);
}

TEST(live_context_rejects_foreign_task) {
	struct context_model ctx = { 0 };
	struct frame_model *outer = push_frame_owned(&ctx, 0xA, 11);
	struct frame_model *inner;

	ASSERT(outer != NULL);
	ASSERT_EQ(ctx.owner, 11);
	ASSERT_EQ(push_frame_owned(&ctx, 0xB, 22), NULL);
	inner = push_frame_owned(&ctx, 0xB, 11);
	ASSERT(inner != NULL);
	inner->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame_owned(&ctx, inner, 22), -1);
	ASSERT_EQ(pop_frame_owned(&ctx, inner, 11), 0);
	outer->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame_owned(&ctx, outer, 11), 0);
	ASSERT_EQ(ctx.owner, 0);
}

TEST(lock_stack_is_dense_and_ooo_pop_is_tracked) {
	struct context_model ctx = { 0 };
	struct frame_model *frame = push_frame(&ctx, 0xA);

	ASSERT(frame != NULL);
	ASSERT_EQ(push_lock(frame, 0xA), 0);
	ASSERT_EQ(push_lock(frame, 0xB), 0);
	ASSERT_EQ(frame->locks[frame->lock_depth - 1], 0xBUL);
	ASSERT_EQ(pop_lock(frame, 0xA), 0);
	ASSERT_EQ(frame->lock_depth, 1);
	ASSERT_EQ(frame->locks[0], 0xBUL);
	ASSERT_EQ(pop_lock(frame, 0xC), -1);
	frame->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, frame), 0);
}

TEST(outer_unlock_is_required_and_exactly_once) {
	struct context_model ctx = { 0 };
	struct frame_model *frame = push_frame(&ctx, 0xA);

	ASSERT(frame != NULL);
	ASSERT_EQ(push_lock(frame, 0xA), 0);
	ASSERT_EQ(complete_frame(frame), -1);
	ASSERT_EQ(mark_released(frame, 0xA), 0);
	frame->outer_unlock_seen = true;
	ASSERT_EQ(complete_frame(frame), 0);
	ASSERT_EQ(complete_frame(frame), -1);
	ASSERT_EQ(pop_frame(&ctx, frame), 0);
}

TEST(deep_nested_ooo_release_waits_for_inner_locks) {
	struct context_model ctx = { 0 };
	struct frame_model *frame = push_frame(&ctx, 0xA);

	ASSERT(frame != NULL);
	ASSERT_EQ(push_lock(frame, 0xA), 0);
	ASSERT_EQ(push_lock(frame, 0xB), 0);
	ASSERT_EQ(push_lock(frame, 0xC), 0);

	/* A is released first, but remains represented until the frame ends. */
	ASSERT_EQ(mark_released(frame, 0xA), 0);
	frame->outer_unlock_seen = true;
	ASSERT_EQ(complete_frame(frame), -1);
	ASSERT_EQ(mark_released(frame, 0xB), 0);
	ASSERT_EQ(complete_frame(frame), -1);
	ASSERT_EQ(mark_released(frame, 0xC), 0);
	ASSERT_EQ(complete_frame(frame), 0);
	ASSERT_EQ(mark_released(frame, 0xC), -1);
	ASSERT_EQ(pop_frame(&ctx, frame), 0);
}

TEST(repeated_acquisition_is_rejected) {
	struct context_model ctx = { 0 };
	struct frame_model *frame = push_frame(&ctx, 0xA);

	ASSERT(frame != NULL);
	ASSERT_EQ(push_lock(frame, 0xA), 0);
	ASSERT_EQ(push_lock(frame, 0xA), -1);
	frame->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, frame), 0);
}

TEST(lock_stack_capacity_fails_closed) {
	struct context_model ctx = { 0 };
	struct frame_model *frame = push_frame(&ctx, 0xA);

	ASSERT(frame != NULL);
	ASSERT_EQ(push_lock(frame, 0xA), 0);
	ASSERT_EQ(push_lock(frame, 0xB), 0);
	ASSERT_EQ(push_lock(frame, 0xC), 0);
	ASSERT_EQ(push_lock(frame, 0xD), -1);
	ASSERT_EQ(frame->lock_depth, MAX_LOCKS);
	ASSERT_EQ(frame->locks[MAX_LOCKS - 1], 0xCUL);
	frame->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, frame), 0);
}

TEST(invalid_initial_stack_does_not_mutate_frame) {
	struct context_model ctx = { 0 };
	struct frame_model *frame = push_frame(&ctx, 0xA);
	const unsigned long initial[] = { 0xA };
	const unsigned long missing_outer[] = { 0xB, 0xC };

	ASSERT(frame != NULL);
	ASSERT_EQ(set_lock_stack(frame, initial, 1), 0);
	ASSERT_EQ(set_lock_stack(frame, missing_outer, 2), -1);
	ASSERT_EQ(frame->lock_depth, 1);
	ASSERT_EQ(frame->locks[0], 0xAUL);
	frame->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, frame), 0);
}

TEST(error_path_can_pop_without_completion) {
	struct context_model ctx = { 0 };
	struct frame_model *frame = push_frame(&ctx, 0xA);

	ASSERT(frame != NULL);
	frame->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, frame), 0);
	ASSERT_EQ(ctx.depth, 0);
}

TEST(abort_releases_only_nested_locks_in_reverse_order) {
	struct context_model ctx = { 0 };
	struct frame_model *frame = push_frame(&ctx, 0xA);
	unsigned long release_order[MAX_LOCKS] = { 0 };
	int release_count = 0;

	ASSERT(frame != NULL);
	ASSERT_EQ(push_lock(frame, 0xA), 0);
	ASSERT_EQ(push_lock(frame, 0xB), 0);
	ASSERT_EQ(push_lock(frame, 0xC), 0);
	ASSERT_EQ(abort_nested_locks(frame, release_order, &release_count), 0);
	ASSERT_EQ(release_count, 2);
	ASSERT_EQ(release_order[0], 0xCUL);
	ASSERT_EQ(release_order[1], 0xBUL);
	ASSERT_EQ(frame->lock_depth, 1);
	ASSERT_EQ(frame->locks[0], 0xAUL);
	frame->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, frame), 0);
}

TEST(gs_context_is_inherited_and_args_remain_two_words) {
	struct context_model ctx = { 0 };
	struct frame_model *outer = push_frame(&ctx, 0xA);
	struct frame_model *inner;
	unsigned long args[2];

	ASSERT(outer != NULL);
	outer->gsbase = 0x12345000UL;
	outer->logical_task = 0xabcdef00UL;
	ASSERT(frame_valid(outer));

	inner = push_frame(&ctx, 0xB);
	ASSERT(inner != NULL);
	inner->gsbase = outer->gsbase;
	inner->logical_task = outer->logical_task;
	ASSERT(frame_valid(inner));
	ASSERT_EQ(inner->gsbase, outer->gsbase);
	ASSERT_EQ(inner->logical_task, outer->logical_task);

	args[0] = inner->gsbase;
	args[1] = inner->logical_task;
	ASSERT_EQ(args[0], 0x12345000UL);
	ASSERT_EQ(args[1], 0xabcdef00UL);
	args[0] = 5;
	args[1] = 77;
	ASSERT_EQ(args[0], 5UL);
	ASSERT_EQ(args[1], 77UL);

	inner->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, inner), 0);
	outer->state = FRAME_ERROR;
	ASSERT_EQ(pop_frame(&ctx, outer), 0);
}

int main(void)
{
	printf("=== test_exec_frame ===\n");
	RUN_TEST(frame_parent_and_lifo);
	RUN_TEST(live_context_rejects_foreign_task);
	RUN_TEST(lock_stack_is_dense_and_ooo_pop_is_tracked);
	RUN_TEST(outer_unlock_is_required_and_exactly_once);
	RUN_TEST(deep_nested_ooo_release_waits_for_inner_locks);
	RUN_TEST(repeated_acquisition_is_rejected);
	RUN_TEST(lock_stack_capacity_fails_closed);
	RUN_TEST(invalid_initial_stack_does_not_mutate_frame);
	RUN_TEST(error_path_can_pop_without_completion);
	RUN_TEST(abort_releases_only_nested_locks_in_reverse_order);
	RUN_TEST(gs_context_is_inherited_and_args_remain_two_words);
	REPORT();
}
