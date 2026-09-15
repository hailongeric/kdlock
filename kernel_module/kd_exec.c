// SPDX-License-Identifier: GPL-2.0

/* Shared spin/mutex execution ledger and original-waiter rendezvous.
 * A frame records logical state; its physical executor retains native locks.
 * Native/remote requests are stack objects whose done ACK is the final access.
 * The bounded per-CPU frame stack belongs to one physical task at a time.
 * This file owns frame push/pop, validation and event transitions; the
 * execution/{native,remote,lock_ledger}.inc components own rendezvous and
 * lock-vector operations while sharing these private counters/state. */
#include <linux/percpu.h>
#include <linux/atomic.h>
#include <linux/bug.h>
#include <linux/kernel.h>
#include <linux/sched.h>
#include <linux/string.h>
#include <linux/smp.h>

#include "exe.h"
#include "kd_exec.h"
#include "kd_source.h"
#include "kd_lock.h"
#include "kd_spinlock.h"

static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_exec_context, kd_exec_context);
static atomic64_t kd_exec_invariant_failures;

struct kd_native_request {
	unsigned long lock_addr;
	struct kd_spin_ref spin_origin;
	int result;
	bool done;
	bool spin_last;
};

static LIST_HEAD(kd_native_frames);
static DEFINE_RAW_SPINLOCK(kd_native_lock);
static atomic64_t kd_native_started;
static atomic64_t kd_native_completed;
static atomic64_t kd_native_unlocks;

#include "execution/remote.inc"

#include "execution/native.inc"

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
	       state == KD_EXEC_FRAME_COMPLETE || state == KD_EXEC_FRAME_ERROR;
}

bool kd_exec_frame_validate(const struct kd_exec_frame *frame)
{
	unsigned int i;
	int state;

	if (!frame)
		return false;

	state = kd_exec_frame_state(frame);
	if (!kd_exec_frame_state_is_active(state) ||
	    frame->depth >= KD_EXEC_MAX_NESTING || !frame->gsbase ||
	    !frame->logical_task ||
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

static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state);

static bool kd_exec_context_validate(const struct kd_exec_context *ctx)
{
	unsigned int i;

	if (!ctx || ctx->depth > KD_EXEC_MAX_NESTING ||
	    (!!ctx->depth != !!ctx->owner))
		return false;

	for (i = 0; i < KD_EXEC_MAX_NESTING; i++) {
		const struct kd_exec_frame *frame = &ctx->frames[i];

		if (i >= ctx->depth) {
			if (kd_exec_frame_state(frame) != KD_EXEC_FRAME_UNUSED)
				return false;
			continue;
		}

		if (!kd_exec_frame_validate(frame) || frame->depth != i ||
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
	atomic64_set(&kd_native_started, 0);
	atomic64_set(&kd_native_completed, 0);
	atomic64_set(&kd_native_unlocks, 0);
	for_each_possible_cpu(cpu)
		kd_exec_context_reset(per_cpu_ptr(&kd_exec_context, cpu));
}

void kd_exec_context_exit(void)
{
	int cpu;

	BUG_ON(!list_empty(&kd_native_frames));
	pr_info("kd_native stats: started=%lld completed=%lld unlocks=%lld\n",
		(long long)atomic64_read(&kd_native_started),
		(long long)atomic64_read(&kd_native_completed),
		(long long)atomic64_read(&kd_native_unlocks));
	for_each_possible_cpu(cpu) {
		struct kd_exec_context *ctx =
			per_cpu_ptr(&kd_exec_context, cpu);

		if (!kd_exec_context_validate(ctx))
			kd_exec_invariant_failure();
		kd_exec_context_reset(per_cpu_ptr(&kd_exec_context, cpu));
	}
	pr_info("kd_exec invariant_failures=%lld\n",
		(long long)atomic64_read(&kd_exec_invariant_failures));
}

static struct kd_exec_context *kd_exec_current_context(void)
{
	return this_cpu_ptr(&kd_exec_context);
}

struct kd_exec_frame *kd_exec_current_frame(void)
{
	struct kd_exec_context *ctx = kd_exec_current_context();

	if (!ctx->depth || ctx->owner != current)
		return NULL;
	return &ctx->frames[ctx->depth - 1];
}

bool kd_exec_context_busy(void)
{
	struct kd_exec_context *ctx = kd_exec_current_context();

	return ctx->depth && ctx->owner != current;
}

/* Reserve fixed storage and its source/provider lease together. Failure leaves
 * the caller's packet and existing context intact; no frame is published. */
struct kd_exec_frame *
kd_exec_frame_push(const struct pt_regs *regs, unsigned long entry_ip,
		   unsigned long outer_lock_addr, void *waiter,
		   void *outgoing_rsp_ptr, unsigned int held_lock_depth,
		   unsigned long gsbase, struct task_struct *logical_task)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	struct kd_exec_frame *frame;
	bool first_frame;

	if (!regs || !gsbase || !logical_task ||
	    ctx->depth >= KD_EXEC_MAX_NESTING ||
	    !kd_exec_context_validate(ctx) ||
	    (ctx->depth && ctx->owner != current))
		return NULL;
	/* Closing and this get serialize so retirement cannot miss a new frame. */
	if (!kd_source_frame_get())
		return NULL;

	first_frame = ctx->depth == 0;
	if (first_frame)
		ctx->owner = current;
	frame = &ctx->frames[ctx->depth];
	memset(frame, 0, sizeof(*frame));
	frame->regs = *regs;
	frame->entry_ip = entry_ip;
	frame->outer_lock_addr = outer_lock_addr;
	frame->gsbase = gsbase;
	frame->logical_task = logical_task;
	frame->logical_pid = logical_task->pid;
	frame->waiter = waiter;
	frame->outgoing_rsp_ptr = outgoing_rsp_ptr;
	frame->parent = kd_exec_current_frame();
	frame->depth = ctx->depth;
	frame->held_lock_depth = held_lock_depth;
	frame->outer_lock_depth = held_lock_depth;
	frame->outer_lock_index = KD_EXEC_MAX_LOCK_DEPTH;
	frame->state = KD_EXEC_FRAME_RUNNING;
	frame->remote_result = 0;
	/* Even an unborrowed frame needs an empty routing head: terminal state
	 * alone must not authorize freeing a still-registered native frame. */
	INIT_LIST_HEAD(&frame->native_link);
	ctx->depth++;

	if (!kd_exec_context_validate(ctx)) {
		ctx->depth--;
		memset(frame, 0, sizeof(*frame));
		if (first_frame)
			ctx->owner = NULL;
		kd_source_frame_put();
		return NULL;
	}

	return frame;
}

/* Retire only after remote dependencies and native routing/requests are gone.
 * A terminal state must not discard an outstanding owner ACK or the frame's
 * source lease. Copy the final packet before clearing physical LIFO storage. */
int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	int state;

	if (!frame || !ctx->depth || ctx->owner != current ||
	    frame != &ctx->frames[ctx->depth - 1])
		return -EINVAL;

	state = kd_exec_frame_state(frame);
	if (kd_exec_frame_remote_pending(frame) || frame->resume_target ||
	    READ_ONCE(frame->remote_request) ||
	    READ_ONCE(frame->native_request) ||
	    !list_empty(&frame->native_link) ||
	    (state != KD_EXEC_FRAME_COMPLETE && state != KD_EXEC_FRAME_ERROR) ||
	    !kd_exec_context_validate(ctx))
		return -EBUSY;

#ifdef KDLOCK_SELFTEST
	/* Observe task exit only after native ACKs, before the real frame/lease
	 * retires and this physical combiner can start the next logical root. */
	kd_exec_selftest_relay_pop(frame);
#endif
	if (regs)
		*regs = frame->regs;
	ctx->depth--;
	memset(frame, 0, sizeof(*frame));
	if (!ctx->depth)
		ctx->owner = NULL;
	/* The source lease covers native/remote continuation until actual pop. */
	kd_source_frame_put();
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

#include "execution/lock_ledger.inc"

int kd_exec_frame_record_event(struct kd_exec_frame *frame,
			       enum kd_exec_event event,
			       const struct pt_regs *regs)
{
	int state, ret;

	if (!frame || !kd_exec_frame_validate(frame))
		return -EINVAL;

	state = kd_exec_frame_state(frame);
	if (state == KD_EXEC_FRAME_COMPLETE || state == KD_EXEC_FRAME_ERROR)
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
		ret = kd_exec_frame_lock_mark_released(frame,
						       frame->outer_lock_addr);
		if (!ret && frame->outer_unlock_hook &&
		    (kd_exec_frame_has_unreleased_nested(frame) ||
		     kd_exec_frame_remote_pending(frame))) {
			struct kd_exec_outer_unlock *hook =
				frame->outer_unlock_hook;

			if (!hook->release || hook->released)
				return -EINVAL;
			ret = hook->release(frame, hook);
			if (!ret)
				hook->released = true;
		}
		return ret;
	case KD_EXEC_EVENT_COMPLETE:
		if (!kd_exec_frame_can_complete(frame) ||
		    frame->completion_seen)
			return -EINVAL;
		frame->completion_seen = true;
		kd_exec_frame_set_state(frame, KD_EXEC_FRAME_COMPLETE);
		return kd_exec_frame_validate(frame) ?
			       0 :
			       kd_exec_invariant_failure();
	case KD_EXEC_EVENT_ERROR:
		if (frame->completion_seen)
			return -EALREADY;
		kd_exec_frame_set_state(frame, KD_EXEC_FRAME_ERROR);
		return kd_exec_frame_validate(frame) ?
			       0 :
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

static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)
{
	if (!frame)
		return;
	smp_store_release(&frame->state, state);
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/exec_capacity_probe.c"
#endif
