/* Frame preparation, binding, push/pop and ordinary-root retirement.
 * Private to kd_exec.c: preserve physical LIFO and last-reader/ACK lifetimes. */
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
	frame->entry_abi = KD_ENTRY_ABI_LEGACY;
	frame->packet_state = KD_PACKET_FULL;
	frame->entry_ip = entry_ip;
	frame->outer_lock_addr = lock;
	frame->gsbase = gsbase;
	frame->logical_task = task;
	frame->parent = NULL;
	frame->depth = 0;
	frame->executed = false;
	frame->role = KD_ROLE_WAITER;
#ifdef KDLOCK_SELFTEST
 if (kd_hotlock_role_trace)
  pr_info("kd_hotlock role: address=%lx request=%px role=WAITER\n", frame->outer_lock_addr, frame);
#endif
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
	frame->role = KD_ROLE_COMBINER;
#ifdef KDLOCK_SELFTEST
 if (kd_hotlock_role_trace)
  pr_info("kd_hotlock role: address=%lx request=%px role=COMBINER type=%s\n",
          frame->outer_lock_addr, frame, frame->mutex_backend ? "mutex" : "spin");
#endif
	return 0;
}

/* Reserve fixed storage and its source/provider lease together. Failure leaves
 * the caller's packet and existing context intact; no frame is published. */
static struct kd_exec_frame *kd_exec_frame_push_internal(
		   const struct pt_regs *regs, unsigned long entry_ip,
		   unsigned long outer_lock_addr, unsigned int held_lock_depth,
		   unsigned long gsbase, struct task_struct *logical_task,
		   struct pt_regs *borrowed_regs)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	struct kd_exec_frame *frame;
	bool first_frame;

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
	 * branch-local payloads. Only an unnested physical root may borrow;
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
	frame->entry_abi = KD_ENTRY_ABI_LEGACY;
	frame->packet_state = KD_PACKET_FULL;
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
	frame->role = KD_ROLE_WAITER;
#ifdef KDLOCK_SELFTEST
 if (kd_hotlock_role_trace)
  pr_info("kd_hotlock role: address=%lx request=%px role=WAITER\n", frame->outer_lock_addr, frame);
#endif
	frame->mutex_backend = false;
	frame->spin_simple = false;
	frame->request_frame = false;
	frame->complex_ready = true;
	frame->batch_lease = false;
	frame->outer_unlock_hook = NULL;
	frame->control_call.phase = KD_CALL_NONE;
	frame->native_request = NULL;
	frame->role = KD_ROLE_COMBINER;
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
		frame->role = KD_ROLE_DONE;
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
		   unsigned long outer_lock_addr, unsigned int held_lock_depth,
		   unsigned long gsbase, struct task_struct *logical_task)
{
	return kd_exec_frame_push_internal(regs, entry_ip, outer_lock_addr,
		held_lock_depth, gsbase, logical_task, NULL);
}

struct kd_exec_frame *
kd_exec_frame_push_borrowed(struct pt_regs *regs, unsigned long entry_ip,
		       unsigned long outer_lock_addr, unsigned int held_lock_depth,
		       unsigned long gsbase, struct task_struct *logical_task)
{
	return kd_exec_frame_push_internal(regs, entry_ip, outer_lock_addr,
		held_lock_depth, gsbase, logical_task, regs);
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
	frame->role = KD_ROLE_DONE;
	frame->state = KD_EXEC_FRAME_UNUSED;
	if (!ctx->depth)
		ctx->owner = NULL;
	/* The source lease covers native/remote continuation until actual pop. */
	if (!frame->batch_lease)
		kd_source_frame_put();
#ifdef KDLOCK_SELFTEST
	kd_exec_selftest_relay_retired(frame);
#endif
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
static __always_inline int kd_exec_complete_single_spin(struct kd_exec_frame *frame)
{
	if (!frame || !frame->spin_simple || !frame->executed ||
	    frame->mutex_backend || frame->parent || frame->depth ||
	    frame->completion_seen ||
	    (frame->packet_state == KD_PACKET_COMPLETE ?
	     frame->entry_abi != KD_ENTRY_ABI_SPIN_CLOBBER_V1 :
	     (frame->packet_state != KD_PACKET_FULL ||
	      kd_exec_frame_regs(frame)->di != frame->outer_lock_addr)))
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

int kd_exec_frame_complete_single_spin(struct kd_exec_frame *frame)
{
	return kd_exec_complete_single_spin(frame);
}

/* A normal batch root has no parent, remote/native publication or private
 * source lease to retire. Validate its physical owner and final packet using
 * the same terminal check as the generic path, then unbind in one operation.
 * The queue layer still owns completion publication and successor selection. */
int kd_exec_frame_retire_single_spin(struct kd_exec_frame *frame)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	int ret;

	if (!frame || frame->complex_ready || !frame->batch_lease ||
	    ctx->depth != 1 || ctx->owner != current || ctx->top != frame)
		return -EINVAL;
	/* Share all terminal checks without a second out-of-line call per body. */
	ret = kd_exec_complete_single_spin(frame);
	if (ret)
		return ret;
	ctx->depth = 0;
	ctx->top = NULL;
	ctx->owner = NULL;
	frame->role = KD_ROLE_DONE;
	frame->state = KD_EXEC_FRAME_UNUSED;
	return 0;
}
