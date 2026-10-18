// SPDX-License-Identifier: GPL-2.0
/*
 * Owned-object nested acquisition records. The executor retains each physical
 * owner through the matching logical release or final continuation ACK.
 */
static int kd_owned_nested_lock(struct kd_mutex *lock)
{
	if (!lock || irqs_disabled() || preempt_count() != 1)
		return -EINVAL;
	if (kd_owned_mutex_owned(lock, current))
		return -EDEADLK;
	preempt_enable();
	kd_mutex_lock(lock);
	preempt_disable();
	BUG_ON(!kd_owned_mutex_owned(lock, current));
	return 0;
}

static int kd_owned_nested_unlock(struct kd_mutex *lock)
{
	if (!lock || !kd_owned_mutex_owned(lock, current))
		return -EPERM;
	/* An occupied executor frame prevents recursive unlock batching. */
	kd_mutex_unlock(lock);
	return 0;
}

int kd_owned_mutex_jit_nested_lock_ctx(struct kd_mutex *lock, struct kd_regs *regs,
				 struct kd_exec_frame *frame)
{
	int ret;

	if (!lock || !regs || !regs->sp || !frame || !frame->owned_mutex ||
	    !kd_exec_frame_validate(frame))
		return -EINVAL;
	ret = kd_jit_begin_call(frame, regs);
	if (ret)
		return ret;
	if (kd_exec_frame_lock_contains(frame, (unsigned long)lock))
		return -EDEADLK;
	if (kd_exec_frame_lock_depth(frame) >= KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;
	if (!READ_ONCE(*(unsigned long *)regs->sp))
		return -EINVAL;
	ret = kd_exec_frame_record_event(frame, KD_EXEC_EVENT_NESTED_LOCK,
					 regs);
	if (ret)
		return ret;
	if (unlikely(cmpxchg(&kd_jit_fail_pending_lock, 2, 0) == 2))
		return -E2BIG;

	frame->control_call.phase = KD_CALL_ENTERED;
	ret = kd_owned_nested_lock(lock);
	if (ret)
		return ret;
	frame->control_call.phase = KD_CALL_ACQUIRED;
	ret = kd_exec_frame_lock_push(frame, (unsigned long)lock,
				      KD_EXEC_LOCK_OWNED, lock);
	if (ret) {
		BUG_ON(kd_owned_nested_unlock(lock));
		return ret;
	}
	/* The CALL is consumed only after the physical lock and its record exist. */
	ret = kd_jit_advance_call(frame, regs);
	if (!ret)
		frame->control_call.phase = KD_CALL_COMPLETE;
	return ret ? ret : 1;
}

int kd_owned_mutex_jit_nested_unlock_ctx(struct kd_mutex *lock,
				   struct kd_exec_frame *frame)
{
	int ret;

	if (!lock || !frame || !frame->owned_mutex ||
	    !kd_exec_frame_validate(frame))
		return -EINVAL;
	if (kd_exec_frame_lock_kind(frame, (unsigned long)lock) !=
		    KD_EXEC_LOCK_OWNED ||
	    kd_exec_frame_lock_node(frame, (unsigned long)lock) != lock)
		return -ENOENT;
	ret = kd_exec_frame_record_event(frame, KD_EXEC_EVENT_NESTED_UNLOCK,
					 NULL);
	if (ret)
		return ret;
	ret = kd_owned_nested_unlock(lock);
	return ret ? ret : kd_exec_frame_lock_pop(frame, (unsigned long)lock);
}

int kd_owned_mutex_jit_abort_cleanup(struct kd_exec_frame *frame)
{
	if (!frame || !frame->owned_mutex || !kd_exec_frame_validate(frame) ||
	    frame->outer_lock_index >= frame->jit_lock_depth)
		return -EINVAL;

	while (frame->jit_lock_depth > frame->outer_lock_index + 1) {
		unsigned int i = frame->jit_lock_depth - 1;
		struct kd_mutex *lock =
			(struct kd_mutex *)frame->jit_lock_addr[i];
		int ret;

		if (frame->jit_lock_kind[i] != KD_EXEC_LOCK_OWNED ||
		    frame->jit_lock_node[i] != lock)
			return -EINVAL;
		if (!frame->jit_lock_released[i]) {
			ret = kd_owned_nested_unlock(lock);
			if (ret)
				return ret;
		}
		ret = kd_exec_frame_lock_pop(frame, (unsigned long)lock);
		if (ret)
			return ret;
	}
	return 0;
}
