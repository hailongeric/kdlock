// SPDX-License-Identifier: GPL-2.0

#include <linux/percpu.h>
#include <linux/atomic.h>
#include <linux/bug.h>
#include <linux/kernel.h>
#include <linux/string.h>
#include <linux/smp.h>

#include "kd_exec.h"

static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_exec_context, kd_exec_context);
static atomic64_t kd_exec_invariant_failures;

static int kd_exec_invariant_failure(void)
{
	atomic64_inc(&kd_exec_invariant_failures);
	WARN_ON_ONCE(1);
	return -EINVAL;
}

static bool kd_exec_frame_state_is_active(int state)
{
	return state == KD_EXEC_FRAME_RUNNING ||
	       state == KD_EXEC_FRAME_WAITING_LOCK ||
	       state == KD_EXEC_FRAME_RESUME ||
	       state == KD_EXEC_FRAME_COMPLETE ||
	       state == KD_EXEC_FRAME_ERROR;
}

bool kd_exec_frame_validate(const struct kd_exec_frame *frame)
{
	unsigned int i;
	int state;

	if (!frame)
		return false;

	state = kd_exec_frame_state(frame);
	if (!kd_exec_frame_state_is_active(state) ||
	    frame->depth >= KD_EXEC_MAX_NESTING ||
	    frame->held_lock_depth > KD_EXEC_MAX_LOCK_DEPTH ||
	    frame->outer_lock_depth > KD_EXEC_MAX_LOCK_DEPTH ||
	    frame->jit_lock_depth > KD_EXEC_MAX_LOCK_DEPTH ||
	    frame->outer_lock_depth > frame->held_lock_depth ||
	    (state == KD_EXEC_FRAME_RESUME &&
	     (!frame->continuation_ip || !frame->continuation_sp)) ||
	    (frame->outer_unlock_seen && !frame->outer_lock_addr) ||
	    (state == KD_EXEC_FRAME_COMPLETE && !frame->completion_seen) ||
	    (frame->completion_seen &&
	     (state != KD_EXEC_FRAME_COMPLETE || !frame->outer_unlock_seen)))
		return false;
	if (frame->jit_lock_depth && frame->outer_lock_addr &&
	    frame->outer_lock_index >= frame->jit_lock_depth)
		return false;
	if (!frame->jit_lock_depth &&
	    frame->outer_lock_index != KD_EXEC_MAX_LOCK_DEPTH)
		return false;

	for (i = 0; i < KD_EXEC_MAX_LOCK_DEPTH; i++) {
		if (i < frame->jit_lock_depth) {
			if (!frame->jit_lock_addr[i] ||
			    frame->jit_lock_kind[i] <= KD_EXEC_LOCK_NONE ||
			    frame->jit_lock_kind[i] > KD_EXEC_LOCK_NATIVE)
				return false;
		} else if (frame->jit_lock_addr[i] ||
			   frame->jit_lock_kind[i] != KD_EXEC_LOCK_NONE ||
			   frame->jit_lock_node[i] ||
			   frame->jit_lock_released[i]) {
			return false;
		}
	}

	return true;
}

bool kd_exec_context_validate(const struct kd_exec_context *ctx)
{
	unsigned int i;

	if (!ctx || ctx->depth > KD_EXEC_MAX_NESTING)
		return false;

	for (i = 0; i < KD_EXEC_MAX_NESTING; i++) {
		const struct kd_exec_frame *frame = &ctx->frames[i];

		if (i >= ctx->depth) {
			if (kd_exec_frame_state(frame) != KD_EXEC_FRAME_UNUSED)
				return false;
			continue;
		}

		if (!kd_exec_frame_validate(frame) ||
		    frame->depth != i ||
		    (i == 0 ? frame->parent != NULL :
		     frame->parent != &ctx->frames[i - 1]))
			return false;
	}

	return true;
}

static void kd_exec_context_reset(struct kd_exec_context *ctx)
{
	memset(ctx, 0, sizeof(*ctx));
}

void kd_exec_context_init(void)
{
	int cpu;

	atomic64_set(&kd_exec_invariant_failures, 0);
	for_each_possible_cpu(cpu)
		kd_exec_context_reset(per_cpu_ptr(&kd_exec_context, cpu));
}

void kd_exec_context_exit(void)
{
	int cpu;

	for_each_possible_cpu(cpu) {
		struct kd_exec_context *ctx = per_cpu_ptr(&kd_exec_context, cpu);

		if (!kd_exec_context_validate(ctx))
			kd_exec_invariant_failure();
		kd_exec_context_reset(per_cpu_ptr(&kd_exec_context, cpu));
	}
	pr_info("kd_exec invariant_failures=%lld\n",
		(long long)atomic64_read(&kd_exec_invariant_failures));
}

struct kd_exec_context *kd_exec_current_context(void)
{
	return this_cpu_ptr(&kd_exec_context);
}

struct kd_exec_frame *kd_exec_current_frame(void)
{
	struct kd_exec_context *ctx = kd_exec_current_context();

	if (!ctx->depth)
		return NULL;
	return &ctx->frames[ctx->depth - 1];
}

struct kd_exec_frame *kd_exec_frame_push(const struct pt_regs *regs,
					 unsigned long entry_ip,
					 unsigned long outer_lock_addr,
					 void *waiter,
					 void *outgoing_rsp_ptr,
					 unsigned int held_lock_depth)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	struct kd_exec_frame *frame;

	if (!regs || ctx->depth >= KD_EXEC_MAX_NESTING ||
	    !kd_exec_context_validate(ctx))
		return NULL;

	frame = &ctx->frames[ctx->depth];
	memset(frame, 0, sizeof(*frame));
	frame->regs = *regs;
	frame->entry_ip = entry_ip;
	frame->outer_lock_addr = outer_lock_addr;
	frame->waiter = waiter;
	frame->outgoing_rsp_ptr = outgoing_rsp_ptr;
	frame->parent = kd_exec_current_frame();
	frame->depth = ctx->depth;
	frame->held_lock_depth = held_lock_depth;
	frame->outer_lock_depth = held_lock_depth;
	frame->outer_lock_index = KD_EXEC_MAX_LOCK_DEPTH;
	frame->state = KD_EXEC_FRAME_RUNNING;
	frame->remote_result = 0;
	ctx->depth++;

	if (!kd_exec_context_validate(ctx)) {
		ctx->depth--;
		memset(frame, 0, sizeof(*frame));
		return NULL;
	}

	return frame;
}

int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	int state;

	if (!frame || !ctx->depth ||
	    frame != &ctx->frames[ctx->depth - 1])
		return -EINVAL;

	state = kd_exec_frame_state(frame);
	if ((state != KD_EXEC_FRAME_COMPLETE &&
	     state != KD_EXEC_FRAME_ERROR) ||
	    !kd_exec_context_validate(ctx))
		return -EBUSY;

	if (regs)
		*regs = frame->regs;
	ctx->depth--;
	memset(frame, 0, sizeof(*frame));
	if (!kd_exec_context_validate(ctx))
		return kd_exec_invariant_failure();
	return 0;
}

void kd_exec_frame_save_continuation(struct kd_exec_frame *frame,
				     const struct pt_regs *regs)
{
	if (!frame || !regs)
		return;

	if (!kd_exec_frame_validate(frame))
		return;

	frame->continuation_ip = regs->ip;
	frame->continuation_sp = regs->sp;
	frame->regs = *regs;
	kd_exec_frame_set_state(frame, KD_EXEC_FRAME_RESUME);
}

void kd_exec_frame_save_call_continuation(struct kd_exec_frame *frame,
					  const struct pt_regs *regs)
{
	unsigned long return_ip;

	if (!frame || !regs || !regs->sp ||
	    !kd_exec_frame_validate(frame))
		return;

	/*
	 * regs->sp points at the return address of the intercepted call.  Save
	 * the post-call state so a nested lock can suspend A without retaining
	 * the raw lock function as its resume point.
	 */
	return_ip = READ_ONCE(*(unsigned long *)regs->sp);
	if (!return_ip)
		return;

	frame->continuation_ip = return_ip;
	frame->continuation_sp = regs->sp + sizeof(unsigned long);
	frame->regs = *regs;
	kd_exec_frame_set_state(frame, KD_EXEC_FRAME_RESUME);
}

int kd_exec_frame_set_lock_entries(
	struct kd_exec_frame *frame,
	const unsigned long *lock_addr,
	const enum kd_exec_lock_kind *lock_kind,
	void *const *lock_node,
	const bool *lock_released,
	unsigned int depth)
{
	unsigned int i;
	unsigned int outer_index = KD_EXEC_MAX_LOCK_DEPTH;

	if (!frame || (depth && !lock_addr))
		return -EINVAL;
	if (depth > KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;
	for (i = 0; i < depth; i++) {
		unsigned int j;

		if (!lock_addr[i])
			return -EINVAL;
		if (lock_kind &&
		    (lock_kind[i] <= KD_EXEC_LOCK_NONE ||
		     lock_kind[i] > KD_EXEC_LOCK_NATIVE))
			return -EINVAL;
		for (j = 0; j < i; j++)
			if (lock_addr[j] == lock_addr[i])
				return -EDEADLK;
		if (lock_addr[i] == frame->outer_lock_addr)
			outer_index = i;
	}
	if (frame->outer_lock_addr &&
	    outer_index == KD_EXEC_MAX_LOCK_DEPTH)
		return -ENOENT;

	memset(frame->jit_lock_addr, 0, sizeof(frame->jit_lock_addr));
	memset(frame->jit_lock_kind, 0, sizeof(frame->jit_lock_kind));
	memset(frame->jit_lock_node, 0, sizeof(frame->jit_lock_node));
	memset(frame->jit_lock_released, 0, sizeof(frame->jit_lock_released));
	for (i = 0; i < depth; i++) {
		frame->jit_lock_addr[i] = lock_addr[i];
		frame->jit_lock_kind[i] = lock_kind ? lock_kind[i] :
			KD_EXEC_LOCK_QUEUE_OWNER;
		frame->jit_lock_node[i] = lock_node ? lock_node[i] : NULL;
		frame->jit_lock_released[i] = lock_released ?
			lock_released[i] : false;
	}
	frame->jit_lock_depth = depth;
	frame->outer_lock_index = outer_index;
	return kd_exec_frame_validate(frame) ? 0 : kd_exec_invariant_failure();
}

int kd_exec_frame_set_lock_stack(struct kd_exec_frame *frame,
				 const unsigned long *lock_addr,
				 unsigned int depth)
{
	return kd_exec_frame_set_lock_entries(frame, lock_addr, NULL, NULL,
					      NULL, depth);
}

int kd_exec_frame_lock_push(struct kd_exec_frame *frame,
			    unsigned long lock_addr,
			    enum kd_exec_lock_kind kind,
			    void *lock_node)
{
	if (!frame || !lock_addr ||
	    kind <= KD_EXEC_LOCK_NONE || kind > KD_EXEC_LOCK_NATIVE ||
	    !kd_exec_frame_validate(frame))
		return -EINVAL;
	if (frame->jit_lock_depth >= KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;
	if (kd_exec_frame_lock_contains(frame, lock_addr))
		return -EDEADLK;

	frame->jit_lock_addr[frame->jit_lock_depth] = lock_addr;
	frame->jit_lock_kind[frame->jit_lock_depth] = kind;
	frame->jit_lock_node[frame->jit_lock_depth] = lock_node;
	frame->jit_lock_released[frame->jit_lock_depth] = false;
	frame->jit_lock_depth++;
	frame->held_lock_depth++;
	return 0;
}

unsigned int kd_exec_frame_lock_depth(const struct kd_exec_frame *frame)
{
	if (!frame)
		return 0;
	return frame->jit_lock_depth;
}

int kd_exec_frame_lock_pop(struct kd_exec_frame *frame,
			   unsigned long lock_addr)
{
	unsigned int i, removed;
	bool removed_outer;

	if (!frame || !lock_addr || !frame->jit_lock_depth)
		return -EINVAL;

	for (i = frame->jit_lock_depth; i > 0; i--) {
		if (frame->jit_lock_addr[i - 1] != lock_addr)
			continue;
		removed = i - 1;
		removed_outer = removed == frame->outer_lock_index;

		for (; i < frame->jit_lock_depth; i++) {
			frame->jit_lock_addr[i - 1] = frame->jit_lock_addr[i];
			frame->jit_lock_kind[i - 1] = frame->jit_lock_kind[i];
			frame->jit_lock_node[i - 1] = frame->jit_lock_node[i];
			frame->jit_lock_released[i - 1] = frame->jit_lock_released[i];
		}
		frame->jit_lock_addr[frame->jit_lock_depth - 1] = 0;
		frame->jit_lock_kind[frame->jit_lock_depth - 1] =
			KD_EXEC_LOCK_NONE;
		frame->jit_lock_node[frame->jit_lock_depth - 1] = NULL;
		frame->jit_lock_released[frame->jit_lock_depth - 1] = false;
		frame->jit_lock_depth--;
		if (frame->held_lock_depth)
			frame->held_lock_depth--;
		if (removed_outer)
			frame->outer_lock_index = KD_EXEC_MAX_LOCK_DEPTH;
		else if (frame->outer_lock_index > removed &&
		    frame->outer_lock_index < KD_EXEC_MAX_LOCK_DEPTH)
			frame->outer_lock_index--;
		return kd_exec_frame_validate(frame) ? 0 :
			kd_exec_invariant_failure();
	}

	return -ENOENT;
}

int kd_exec_frame_lock_mark_released(struct kd_exec_frame *frame,
				     unsigned long lock_addr)
{
	unsigned int i;

	if (!frame || !lock_addr || !kd_exec_frame_validate(frame))
		return -EINVAL;

	for (i = frame->jit_lock_depth; i > 0; i--) {
		if (frame->jit_lock_addr[i - 1] != lock_addr)
			continue;
		if (frame->jit_lock_released[i - 1])
			return -EALREADY;
		frame->jit_lock_released[i - 1] = true;
		return 0;
	}

	return -ENOENT;
}

bool kd_exec_frame_lock_released(const struct kd_exec_frame *frame,
					unsigned long lock_addr)
{
	unsigned int i;

	if (!frame || !lock_addr)
		return false;

	for (i = frame->jit_lock_depth; i > 0; i--)
		if (frame->jit_lock_addr[i - 1] == lock_addr)
			return frame->jit_lock_released[i - 1];

	return false;
}

unsigned long kd_exec_frame_lock_top(const struct kd_exec_frame *frame)
{
	if (!frame || !frame->jit_lock_depth)
		return 0;
	return frame->jit_lock_addr[frame->jit_lock_depth - 1];
}

enum kd_exec_lock_kind
kd_exec_frame_lock_kind(const struct kd_exec_frame *frame,
			unsigned long lock_addr)
{
	unsigned int i;

	if (!frame || !lock_addr)
		return KD_EXEC_LOCK_NONE;

	for (i = frame->jit_lock_depth; i > 0; i--)
		if (frame->jit_lock_addr[i - 1] == lock_addr)
			return frame->jit_lock_kind[i - 1];

	return KD_EXEC_LOCK_NONE;
}

void *kd_exec_frame_lock_node(const struct kd_exec_frame *frame,
			      unsigned long lock_addr)
{
	unsigned int i;

	if (!frame || !lock_addr)
		return NULL;

	for (i = frame->jit_lock_depth; i > 0; i--)
		if (frame->jit_lock_addr[i - 1] == lock_addr)
			return frame->jit_lock_node[i - 1];

	return NULL;
}

bool kd_exec_frame_lock_contains(const struct kd_exec_frame *frame,
					 unsigned long lock_addr)
{
	unsigned int i;

	if (!frame || !lock_addr)
		return false;

	for (i = 0; i < frame->jit_lock_depth; i++)
		if (frame->jit_lock_addr[i] == lock_addr)
			return true;
	return false;
}

bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)
{
	unsigned int i;

	if (!frame || frame->outer_lock_index >= frame->jit_lock_depth)
		return false;

	for (i = frame->outer_lock_index + 1; i < frame->jit_lock_depth; i++)
		if (!frame->jit_lock_released[i])
			return true;

	return false;
}

bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)
{
	unsigned int i;

	if (!frame || !frame->outer_unlock_seen ||
	    frame->outer_lock_index >= frame->jit_lock_depth)
		return false;

	for (i = frame->outer_lock_index; i < frame->jit_lock_depth; i++)
		if (!frame->jit_lock_released[i])
			return false;

	return true;
}

int kd_exec_frame_record_event(struct kd_exec_frame *frame,
			       enum kd_exec_event event,
			       const struct pt_regs *regs)
{
	int state;

	if (!frame || !kd_exec_frame_validate(frame))
		return -EINVAL;

	state = kd_exec_frame_state(frame);
	if (state == KD_EXEC_FRAME_COMPLETE ||
	    state == KD_EXEC_FRAME_ERROR)
		return -EALREADY;

	switch (event) {
	case KD_EXEC_EVENT_CONTINUE:
	case KD_EXEC_EVENT_NESTED_LOCK:
	case KD_EXEC_EVENT_NESTED_UNLOCK:
		return 0;
	case KD_EXEC_EVENT_OUTER_UNLOCK:
		if (!frame->outer_lock_addr || frame->outer_unlock_seen ||
		    (regs && regs->di != frame->outer_lock_addr))
			return -EINVAL;
		frame->outer_unlock_seen = true;
		return kd_exec_frame_lock_mark_released(frame,
							frame->outer_lock_addr);
	case KD_EXEC_EVENT_COMPLETE:
		if (!kd_exec_frame_can_complete(frame) || frame->completion_seen)
			return -EINVAL;
		frame->completion_seen = true;
		kd_exec_frame_set_state(frame, KD_EXEC_FRAME_COMPLETE);
		return kd_exec_frame_validate(frame) ? 0 :
			kd_exec_invariant_failure();
	case KD_EXEC_EVENT_ERROR:
		if (frame->completion_seen)
			return -EALREADY;
		kd_exec_frame_set_state(frame, KD_EXEC_FRAME_ERROR);
		return kd_exec_frame_validate(frame) ? 0 :
			kd_exec_invariant_failure();
	default:
		return -EINVAL;
	}
}

int kd_exec_frame_complete(struct kd_exec_frame *frame)
{
	return kd_exec_frame_record_event(frame, KD_EXEC_EVENT_COMPLETE, NULL);
}

int kd_exec_frame_abort(struct kd_exec_frame *frame)
{
	return kd_exec_frame_record_event(frame, KD_EXEC_EVENT_ERROR, NULL);
}

int kd_exec_frame_state(const struct kd_exec_frame *frame)
{
	if (!frame)
		return KD_EXEC_FRAME_ERROR;
	return smp_load_acquire(&frame->state);
}

void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)
{
	if (!frame)
		return;
	smp_store_release(&frame->state, state);
}
