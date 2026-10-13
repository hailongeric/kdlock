/*
 * Known spin/mutex CALL handling, continuation advancement and stack checks.
 * Private implementation included only by exe.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static int is_end_point(unsigned long addr)
{
	int i;

	for (i = 0; i < end_point_count; i++)
		if (addr == end_points[i])
			return 1;
	return 0;
}

static int is_outer_lock_unlock(struct kd_regs *regs,
				unsigned long outer_lock_addr)
{
	if (regs->ip != raw_spin_unlock_addr &&
	    regs->ip != clobber_spin_unlock_addr &&
	    regs->ip != cold_spin_unlock_addr &&
	    regs->ip != mutex_unlock_addr && regs->ip != clobber_mutex_unlock_addr &&
	    regs->ip != direct_mutex_unlock_addr)
		return 0;
	if (!outer_lock_addr)
		return 1;
	return regs->di == outer_lock_addr;
}

static int advance_after_known_call(struct kd_regs *regs)
{
	unsigned long return_ip;

	if (regs->sp == 0)
		return -EINVAL;

	return_ip = READ_ONCE(*(unsigned long *)regs->sp);
	regs->sp += sizeof(unsigned long);
	regs->ip = return_ip;
	return 1;
}

static int advance_and_save_continuation(struct kd_exec_frame *frame,
					 struct kd_regs *regs)
{
	int ret = advance_after_known_call(regs);

	if (ret > 0 && frame)
		kd_exec_frame_save_continuation(frame, regs);
	return ret;
}

static int finish_acquired_spin_call(struct kd_exec_frame *frame,
				     struct kd_regs *regs, int result)
{
	const struct kd_call_state *call;
	unsigned long base, end, return_ip, lock;
	unsigned int index;

	/* Only the local post-acquisition EIO boundary can use this path. A
	 * generic ACQUIRED tag is insufficient: partial ledger publication,
	 * remote requests, a changed CALL word or another owner stay fail-stop.
	 * Nothing is undone and B must never be acquired a second time. */
	if (result != -EIO || !frame || frame->mutex_backend ||
	    !kd_exec_frame_can_borrow_locks(frame) ||
	    frame->logical_task == current ||
	    kd_exec_frame_remote_pending(frame) || frame->remote_request ||
	    frame->jit_lock_depth <= frame->outer_lock_index + 1)
		return result;
	call = &frame->control_call;
	if (call->phase != KD_CALL_ACQUIRED ||
	    (call->target != raw_spin_lock_addr &&
	     call->target != clobber_spin_lock_addr &&
	     call->target != pinned_spin_lock_addr) ||
	    !kd_call_after_matches(call, regs->ip, regs->sp))
		return result;
	index = frame->jit_lock_depth - 1;
	lock = frame->jit_lock_addr[index];
	if (!lock || lock != regs->di || frame->jit_lock_released[index] ||
	    frame->jit_lock_node[index] ||
	    (frame->jit_lock_kind[index] != KD_EXEC_LOCK_FAST &&
	     frame->jit_lock_kind[index] != KD_EXEC_LOCK_QUEUE_OWNER) ||
	    kd_spin_debug_owner((raw_spinlock_t *)lock) !=
		    (unsigned long)current ||
	    !(kd_spin_debug_word((raw_spinlock_t *)lock) & 0xff))
		return result;
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return result;
	end = base + THREAD_SIZE;
	if (call->stack < base || call->stack > end - sizeof(return_ip) ||
	    copy_from_kernel_nofault(&return_ip, (void *)call->stack,
				     sizeof(return_ip)) ||
	    return_ip != call->return_ip)
		return result;
	frame->control_call.phase = KD_CALL_SPIN_NATIVE;
	kd_exec_frame_save_continuation(frame, regs);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=SPIN_ACQUIRED_NATIVE entry=0x%lx target=0x%lx lock=0x%lx ip=0x%lx sp=0x%lx call_sp=0x%lx return=0x%lx owner=0x%lx task=%d\n",
		frame->entry_ip, call->target, lock, regs->ip, regs->sp,
		call->stack, return_ip, (unsigned long)current,
		frame->logical_task->pid);
	return KD_EXE_KNOWN_NATIVE;
}

static int finish_known_lock_call(struct kd_exec_frame *frame,
				  struct kd_regs *regs, int result)
{
	unsigned long staged_ip = regs->ip, staged_sp = regs->sp;
	int acquired = finish_acquired_spin_call(frame, regs, result);

	if (acquired != result)
		return acquired;

	if (result >= 0 || !kd_exec_frame_can_borrow_locks(frame) ||
	    !kd_call_resume_pending(&frame->control_call, result, &regs->ip,
				    &regs->sp))
		return result;
	kd_exec_frame_save_continuation(frame, regs);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=PENDING_LOCK_NATIVE entry=0x%lx target=0x%lx sp=0x%lx return=0x%lx staged_ip=0x%lx staged_sp=0x%lx mutex=%u error=%d outer_released=%u task=%d\n",
		frame->entry_ip, regs->ip, regs->sp,
		frame->control_call.return_ip, staged_ip, staged_sp,
		frame->mutex_backend, result, frame->outer_unlock_seen,
		frame->logical_task->pid);
	return KD_EXE_KNOWN_NATIVE;
}

static int kd_mutex_stack_prepare(struct kd_exec_frame *frame,
				  struct kd_regs *regs,
				  struct kd_mutex_call_stack *saved)
{
	unsigned long base, end, return_ip;

	/* The waiter cannot retire its kernel stack before this delegated request
	 * completes. Bound every read to that stack, not the combiner's shadow
	 * stack, and do not infer that the range is private to the waiter. */
	if (!kd_exec_frame_can_borrow_locks(frame) || !frame->mutex_backend ||
	    frame->logical_task == current)
		return -EINVAL;
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return -EFAULT;
	end = base + THREAD_SIZE;
	if (regs->sp < base || regs->sp > end - sizeof(return_ip) ||
	    copy_from_kernel_nofault(&return_ip, (void *)regs->sp,
				     sizeof(return_ip)))
		return -EFAULT;
	if (kd_call_begin(&saved->call, regs->ip, regs->sp, return_ip))
		return -EINVAL;
	frame->control_call = saved->call;
	if (end - regs->sp - sizeof(return_ip) < sizeof(saved->bytes)) {
		/* No control side effect yet: use the real PENDING packet, not a
		 * fabricated allocation failure or an entry replay. */
		kd_exec_frame_save_continuation(frame, regs);
		atomic64_inc(&kd_mutex_stack_unavailable);
		pr_warn_ratelimited(
			"[KD_JIT][WARN] reason=MUTEX_STACK_UNAVAILABLE entry=0x%lx target=0x%lx sp=0x%lx task=%d\n",
			frame->entry_ip, regs->ip, regs->sp,
			frame->logical_task->pid);
		return KD_EXE_KNOWN_NATIVE;
	}
	return copy_from_kernel_nofault(saved->bytes,
					(void *)(regs->sp + sizeof(return_ip)),
					sizeof(saved->bytes)) ?
		       -EFAULT :
		       0;
}

static int kd_mutex_stack_finish(struct kd_exec_frame *frame,
				 struct kd_regs *regs,
				 const struct kd_mutex_call_stack *saved)
{
	unsigned char after[KD_MUTEX_CALL_STACK_BYTES];
	unsigned long return_ip;
	const struct kd_call_state *call = &frame->control_call;

	/* Compare after the real operation, never restore its writes. A changed
	 * CALL token or post-CALL packet is not an authorized native continuation. */
	if (call->phase != KD_CALL_COMPLETE ||
	    call->target != saved->call.target ||
	    call->stack != saved->call.stack ||
	    call->return_ip != saved->call.return_ip ||
	    !kd_call_after_matches(call, regs->ip, regs->sp) ||
	    copy_from_kernel_nofault(&return_ip, (void *)call->stack,
				     sizeof(return_ip)) ||
	    return_ip != call->return_ip ||
	    copy_from_kernel_nofault(after, (void *)regs->sp, sizeof(after)))
		return -EINVAL;
	if (!memcmp(saved->bytes, after, sizeof(after))) {
		atomic64_inc(&kd_mutex_stack_equal);
		return 1;
	}
	if (!kd_exec_frame_can_borrow_locks(frame))
		return -EINVAL;
	frame->control_call.phase = KD_CALL_STACK_CHANGED;
	kd_exec_frame_save_continuation(frame, regs);
	atomic64_inc(&kd_mutex_stack_changed);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=MUTEX_STACK_CHANGED entry=0x%lx target=0x%lx ip=0x%lx sp=0x%lx task=%d\n",
		frame->entry_ip, call->target, regs->ip, regs->sp,
		frame->logical_task->pid);
	return KD_EXE_KNOWN_NATIVE;
}

static int handle_known_mutex_call(struct kd_exec_frame *frame,
				   struct kd_regs *regs,
				   unsigned long outer_lock_addr)
{
	struct kd_mutex_call_stack saved;
	int ret;

	/* Final outer completion does not resume this JIT, so needs no memory
	 * preservation check. All other local mutex controls use one checkpoint. */
	if ((regs->ip == mutex_unlock_addr || regs->ip == clobber_mutex_unlock_addr ||
	     regs->ip == direct_mutex_unlock_addr) && regs->di == outer_lock_addr &&
	    !kd_exec_frame_has_unreleased_nested(frame))
		return KD_EXE_KNOWN_OUTER_UNLOCK;
	ret = kd_mutex_stack_prepare(frame, regs, &saved);
	if (ret)
		return ret;
	if (regs->ip == mutex_lock_addr || regs->ip == clobber_mutex_lock_addr ||
	    regs->ip == direct_mutex_lock_addr || regs->ip == contended_mutex_lock_addr) {
		ret = kd_mutex_jit_nested_lock_ctx((struct mutex *)regs->di,
						   regs, frame);
		ret = finish_known_lock_call(frame, regs, ret);
	} else {
		frame->control_call.phase = KD_CALL_ENTERED;
		if (regs->di == outer_lock_addr) {
			/* Opening A may let another batch run while B stays owned. */
			ret = kd_exec_frame_record_event(
				frame, KD_EXEC_EVENT_OUTER_UNLOCK, regs);
		} else {
			ret = kd_mutex_jit_nested_unlock_ctx(
				(struct mutex *)regs->di, frame);
			if (!ret)
				kd_mutex_note_nested_jit();
		}
		if (ret)
			return ret;
		/* The waiter's completion trampoline consumes the final B CALL. */
		if (kd_exec_frame_can_complete(frame))
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		ret = advance_and_save_continuation(frame, regs);
		if (ret > 0)
			frame->control_call.phase = KD_CALL_COMPLETE;
	}
	if (ret != 1)
		return ret;
	return kd_mutex_stack_finish(frame, regs, &saved);
}

static int handle_known_call(struct kd_regs *regs,
			     unsigned long outer_lock_addr)
{
	struct kd_exec_frame *frame = kd_exec_current_frame();
	int ret;

	if (frame)
		frame->control_call.phase = KD_CALL_NONE;

	/* The outer-only return-valued entry is not a nested void lock service.
	 * Admission rejects it; retain the same boundary in generic recovery. */
	if (regs->ip == outer_mutex_lock_addr ||
	    regs->ip == prepared_mutex_lock_addr ||
	    regs->ip == preflight_mutex_lock_addr)
		return -EOPNOTSUPP;

	/* Backend-specific lock stacks cannot represent mixed spin/mutex nesting.
	 * In particular, never enter a sleeping mutex service from a spin frame. */
	if (frame &&
	    ((frame->mutex_backend && ((regs->ip == raw_spin_lock_addr ||
		     regs->ip == clobber_spin_lock_addr ||
		     regs->ip == pinned_spin_lock_addr) ||
				       (regs->ip == raw_spin_unlock_addr ||
		     regs->ip == clobber_spin_unlock_addr ||
		     regs->ip == cold_spin_unlock_addr))) ||
	     (!frame->mutex_backend && mutex_lock_addr && mutex_unlock_addr &&
	      (regs->ip == mutex_lock_addr || regs->ip == clobber_mutex_lock_addr ||
	       regs->ip == direct_mutex_lock_addr || regs->ip == contended_mutex_lock_addr ||
	       regs->ip == mutex_unlock_addr ||
	       regs->ip == clobber_mutex_unlock_addr || regs->ip == direct_mutex_unlock_addr))))
		return -EOPNOTSUPP;

	if ((regs->ip == raw_spin_lock_addr ||
		     regs->ip == clobber_spin_lock_addr ||
		     regs->ip == pinned_spin_lock_addr)) {
		ret = kd_spin_jit_nested_lock_ctx((raw_spinlock_t *)regs->di,
						  regs, frame);
		return finish_known_lock_call(frame, regs, ret);
	}

	if ((regs->ip == raw_spin_unlock_addr ||
		     regs->ip == clobber_spin_unlock_addr ||
		     regs->ip == cold_spin_unlock_addr)) {
		if (regs->di == outer_lock_addr) {
			/* An early outer unlock is a real OOO release.  Keep executing
			 * until every nested lock has released, then finish A once. */
			if (frame &&
			    kd_exec_frame_has_unreleased_nested(frame)) {
				ret = kd_spin_jit_outer_unlock_ooo_ctx(
					(raw_spinlock_t *)regs->di, regs,
					frame);
				if (ret)
					return ret;
				return advance_and_save_continuation(frame,
								     regs);
			}
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		}
		ret = kd_spin_jit_nested_unlock_ctx((raw_spinlock_t *)regs->di,
						    frame);
		return ret ? ret : advance_and_save_continuation(frame, regs);
	}

	if (!mutex_lock_addr || !mutex_unlock_addr)
		return 0;

	if (regs->ip != mutex_lock_addr && regs->ip != clobber_mutex_lock_addr &&
	    regs->ip != direct_mutex_lock_addr && regs->ip != contended_mutex_lock_addr &&
	    regs->ip != mutex_unlock_addr &&
	    regs->ip != clobber_mutex_unlock_addr && regs->ip != direct_mutex_unlock_addr)
		return 0;

	return handle_known_mutex_call(frame, regs, outer_lock_addr);
}

/* Include control classification, blocking and nested execution, but not the
 * backend's later original-waiter native suffix/ACK wait after dispatch exits. */
static int kd_jit_timed_control(struct kd_regs *regs, unsigned long outer)
{
	u64 start = kd_jit_timing_start();
	int ret = handle_known_call(regs, outer);

	kd_jit_timing_end(KD_JIT_TIME_CONTROL, start);
	return ret;
}
