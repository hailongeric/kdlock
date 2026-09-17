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
	if (frame->spin_simple && !frame->complex_ready)
		return frame->request_frame && !frame->parent && !frame->depth &&
		       frame->gsbase && frame->logical_task && frame->outer_lock_addr &&
		       (state == KD_EXEC_FRAME_RUNNING ||
			(state == KD_EXEC_FRAME_COMPLETE && frame->completion_seen));
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

	/* Slots outside the live prefix are deliberately left untouched on reuse. */
	for (i = 0; i < frame->jit_lock_depth; i++) {
		if (!frame->jit_lock_addr[i] ||
		    frame->jit_lock_kind[i] <= KD_EXEC_LOCK_NONE ||
		    frame->jit_lock_kind[i] > KD_EXEC_LOCK_NATIVE)
			return false;
	}

	return true;
}

static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state);

static bool kd_exec_context_validate(const struct kd_exec_context *ctx)
{
	unsigned int i;
	const struct kd_exec_frame *frame;

	if (!ctx || ctx->depth > KD_EXEC_MAX_NESTING ||
	    (!!ctx->depth != !!ctx->owner) || (!!ctx->depth != !!ctx->top))
		return false;

	frame = ctx->top;
	for (i = ctx->depth; i; i--) {
		if (!kd_exec_frame_validate(frame) || frame->depth != i - 1)
			return false;
		frame = frame->parent;
	}

	return !frame;
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
	return ctx->top;
}

bool kd_exec_context_busy(void)
{
	struct kd_exec_context *ctx = kd_exec_current_context();

	return ctx->depth && ctx->owner != current;
}

/* The producer owns the unqueued request. Inactive arrays and register bytes
 * are deliberately untouched; their live depths and packet producer own them. */
/* Materialize branch-local discriminators once. Never clear inactive arrays or
 * copy the shared register packet. A pristine single-lock ledger is implicit
 * until the first service/control boundary requires an explicit owner record. */
void kd_exec_frame_prepare_complex(struct kd_exec_frame *frame)
{
	if (frame->complex_ready)
		return;
	frame->continuation_ip = 0;
	frame->continuation_sp = 0;
	frame->logical_pid = frame->logical_task->pid;
	frame->delegated_lock_addr = 0;
	frame->resume_target = NULL;
	frame->remote_request = NULL;
	frame->held_lock_depth = frame->spin_simple ? 1 : 0;
	frame->outer_lock_depth = frame->held_lock_depth;
	frame->outer_lock_index = frame->spin_simple ? 0 : KD_EXEC_MAX_LOCK_DEPTH;
	frame->jit_lock_depth = frame->held_lock_depth;
	frame->outer_unlock_seen = false;
	frame->outer_unlock_hook = NULL;
	frame->control_call.phase = KD_CALL_NONE;
	frame->native_request = NULL;
	frame->remote_result = KD_EXEC_REMOTE_IDLE;
	INIT_LIST_HEAD(&frame->native_link);
	if (frame->spin_simple) {
		frame->jit_lock_addr[0] = frame->outer_lock_addr;
		frame->jit_lock_kind[0] = KD_EXEC_LOCK_QUEUE_OWNER;
		frame->jit_lock_node[0] = NULL;
		frame->jit_lock_released[0] = false;
	}
	frame->complex_ready = true;
}

void kd_exec_frame_prepare(struct kd_exec_frame *frame, unsigned long entry_ip,
			   unsigned long lock, unsigned long gsbase,
			   struct task_struct *task)
{
	frame->regs_ref = &frame->regs;
	frame->entry_ip = entry_ip;
	frame->outer_lock_addr = lock;
	frame->gsbase = gsbase;
	frame->logical_task = task;
	frame->parent = NULL;
	frame->depth = 0;
	frame->executed = false;
	frame->mutex_backend = false;
	frame->spin_simple = false;
	frame->request_frame = true;
	frame->batch_lease = false;
	frame->complex_ready = false;
	frame->regs_borrowed = false;
	frame->completion_seen = false;
	frame->state = KD_EXEC_FRAME_RUNNING;
}

int kd_exec_frame_bind(struct kd_exec_frame *frame, unsigned int lock_depth,
		       bool batch_lease)
{
	struct kd_exec_context *ctx = kd_exec_current_context();

	if (!frame || !frame->request_frame || !frame->gsbase ||
	    !frame->logical_task || frame->executed ||
	    lock_depth > KD_EXEC_MAX_LOCK_DEPTH ||
	    ctx->depth >= KD_EXEC_MAX_NESTING ||
	    (!!ctx->depth != !!ctx->owner) ||
	    (ctx->depth && ctx->owner != current))
		return -EINVAL;
	/* Admission can close during a batch. Its enclosing lease retains source
	 * storage, but never permits a new request after closure was observed. */
	if (batch_lease ? !kd_source_is_open() : !kd_source_frame_get())
		return -EBUSY;
	frame->parent = ctx->top;
	frame->depth = ctx->depth;
	frame->spin_simple = !frame->complex_ready && !ctx->depth && lock_depth == 1;
	if (!frame->spin_simple) {
		kd_exec_frame_prepare_complex(frame);
		frame->held_lock_depth = lock_depth;
		frame->outer_lock_depth = lock_depth;
	}
	frame->batch_lease = batch_lease;
	frame->state = KD_EXEC_FRAME_RUNNING;
	ctx->owner = current;
	ctx->top = frame;
	ctx->depth++;
	return 0;
}

/* Reserve fixed storage and its source/provider lease together. Failure leaves
 * the caller's packet and existing context intact; no frame is published. */
static struct kd_exec_frame *kd_exec_frame_push_internal(
		   const struct pt_regs *regs, unsigned long entry_ip,
		   unsigned long outer_lock_addr, void *waiter,
		   void *outgoing_rsp_ptr, unsigned int held_lock_depth,
		   unsigned long gsbase, struct task_struct *logical_task,
		   struct pt_regs *borrowed_regs)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	struct kd_exec_frame *frame;
	bool first_frame;

	(void)waiter;
	(void)outgoing_rsp_ptr;
	if (!regs || !gsbase || !logical_task ||
	    held_lock_depth > KD_EXEC_MAX_LOCK_DEPTH ||
	    ctx->depth >= KD_EXEC_MAX_NESTING ||
	    (!!ctx->depth != !!ctx->owner) ||
#ifdef KDLOCK_SELFTEST
	    !kd_exec_context_validate(ctx) ||
#endif
	    (ctx->depth && ctx->owner != current))
		return NULL;
	/* Atomic admission and closure order retirement against every new frame. */
	if (!kd_source_frame_get())
		return NULL;

	first_frame = ctx->depth == 0;
	if (first_frame)
		ctx->owner = current;
	frame = &ctx->frames[ctx->depth];
	/* Initialize every readable discriminator, not the inactive arrays or
	 * branch-local payloads. Only an unnested physical spin root may borrow;
	 * complex dispatch takes a private packet before node reuse on native ACK.
	 * control_call's payload is initialized by kd_call_begin before use;
	 * saved_combiner is initialized only by the spin complex-path producer. */
	frame->regs_borrowed = first_frame && held_lock_depth == 1 &&
			       borrowed_regs;
	if (!frame->regs_borrowed)
		frame->regs = *regs;
	frame->entry_ip = entry_ip;
	frame->outer_lock_addr = outer_lock_addr;
	frame->continuation_ip = 0;
	if (frame->regs_borrowed)
		frame->borrowed_regs = borrowed_regs;
	else
		frame->continuation_sp = 0;
	frame->gsbase = gsbase;
	frame->logical_task = logical_task;
	frame->logical_pid = logical_task->pid;
	frame->regs_ref = NULL;
	frame->delegated_lock_addr = 0;
	frame->parent = kd_exec_current_frame();
	frame->resume_target = NULL;
	frame->remote_request = NULL;
	frame->depth = ctx->depth;
	frame->held_lock_depth = held_lock_depth;
	frame->outer_lock_depth = held_lock_depth;
	frame->outer_lock_index = KD_EXEC_MAX_LOCK_DEPTH;
	frame->jit_lock_depth = 0;
	frame->outer_unlock_seen = false;
	frame->completion_seen = false;
	frame->executed = false;
	frame->mutex_backend = false;
	frame->spin_simple = false;
	frame->request_frame = false;
	frame->complex_ready = true;
	frame->batch_lease = false;
	frame->outer_unlock_hook = NULL;
	frame->control_call.phase = KD_CALL_NONE;
	frame->native_request = NULL;
	frame->state = KD_EXEC_FRAME_RUNNING;
	frame->remote_result = 0;
	/* Even an unborrowed frame needs an empty routing head: terminal state
	 * alone must not authorize freeing a still-registered native frame. */
	INIT_LIST_HEAD(&frame->native_link);
	ctx->top = frame;
	ctx->depth++;

#ifdef KDLOCK_SELFTEST
	if (!kd_exec_context_validate(ctx)) {
		ctx->depth--;
		ctx->top = frame->parent;
		frame->state = KD_EXEC_FRAME_UNUSED;
		if (first_frame)
			ctx->owner = NULL;
		kd_source_frame_put();
		return NULL;
	}
#endif

	return frame;
}

struct kd_exec_frame *
kd_exec_frame_push(const struct pt_regs *regs, unsigned long entry_ip,
		   unsigned long outer_lock_addr, void *waiter,
		   void *outgoing_rsp_ptr, unsigned int held_lock_depth,
		   unsigned long gsbase, struct task_struct *logical_task)
{
	return kd_exec_frame_push_internal(regs, entry_ip, outer_lock_addr,
		waiter, outgoing_rsp_ptr, held_lock_depth, gsbase, logical_task, NULL);
}

struct kd_exec_frame *
kd_exec_frame_push_spin(struct pt_regs *regs, unsigned long entry_ip,
		       unsigned long outer_lock_addr, void *waiter,
		       void *outgoing_rsp_ptr, unsigned int held_lock_depth,
		       unsigned long gsbase, struct task_struct *logical_task)
{
	return kd_exec_frame_push_internal(regs, entry_ip, outer_lock_addr,
		waiter, outgoing_rsp_ptr, held_lock_depth, gsbase, logical_task, regs);
}

/* Retire only after remote dependencies and native routing/requests are gone.
 * A terminal state must not discard an outstanding owner ACK or the frame's
 * source lease. Copy the final packet before retiring physical LIFO storage.
 * Inactive slots have no readers: depth, not zero-filled memory, owns them. */
int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	int state;

	if (!frame || !ctx->depth || ctx->owner != current ||
	    frame != ctx->top)
		return -EINVAL;

	state = kd_exec_frame_state(frame);
	if (frame->complex_ready &&
	    (kd_exec_frame_remote_pending(frame) || frame->resume_target ||
	    READ_ONCE(frame->remote_request) ||
	    READ_ONCE(frame->native_request) ||
	    !list_empty(&frame->native_link) ||
	    (state != KD_EXEC_FRAME_COMPLETE && state != KD_EXEC_FRAME_ERROR)))
		return -EBUSY;
	if (!frame->complex_ready &&
	    (state != KD_EXEC_FRAME_COMPLETE || !frame->completion_seen))
		return -EBUSY;

#ifdef KDLOCK_SELFTEST
	if (!kd_exec_context_validate(ctx))
		return -EBUSY;
	/* Observe task exit only after native ACKs, before the real frame/lease
	 * retires and this physical combiner can start the next logical root. */
	kd_exec_selftest_relay_pop(frame);
#endif
	/* Borrowed output already occupies the waiter's packet. Retirement must
	 * precede its release wake; no node access is allowed after that wake. */
	if (regs && regs != kd_exec_frame_regs(frame))
		*regs = *kd_exec_frame_regs(frame);
	ctx->depth--;
	ctx->top = frame->parent;
	frame->state = KD_EXEC_FRAME_UNUSED;
	if (!ctx->depth)
		ctx->owner = NULL;
	/* The source lease covers native/remote continuation until actual pop. */
	if (!frame->batch_lease)
		kd_source_frame_put();
#ifdef KDLOCK_SELFTEST
	if (!kd_exec_context_validate(ctx))
		return kd_exec_invariant_failure();
#endif
	return 0;
}

/* Only the first wrapper return of a single-lock physical root can use this
 * transition. The dispatcher already matched the spin unlock CALL and L.
 * Any service/nesting/native exit clears spin_simple before doing work, so
 * there are no child locks or remote publications to visit here. Physical L
 * remains owned by the batch until it publishes completion/handoff. */
int kd_exec_frame_complete_single_spin(struct kd_exec_frame *frame)
{
	if (!frame || !frame->spin_simple || !frame->executed ||
	    frame->mutex_backend || frame->parent || frame->depth ||
	    frame->completion_seen ||
	    kd_exec_frame_regs(frame)->di != frame->outer_lock_addr)
		return -EINVAL;
	if (frame->complex_ready) {
		if (frame->jit_lock_depth != 1 || frame->outer_lock_index != 0)
			return -EINVAL;
		frame->jit_lock_released[0] = true;
		frame->outer_unlock_seen = true;
	}
	frame->completion_seen = true;
	kd_exec_frame_set_state(frame, KD_EXEC_FRAME_COMPLETE);
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
	if (regs != kd_exec_frame_regs(frame))
		*kd_exec_frame_regs(frame) = *regs;
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
#include "../tests/kernel/execution/exec_capacity_probe.c"
#endif
