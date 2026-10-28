// SPDX-License-Identifier: GPL-2.0
/* Only ordinary, unpinned spin controls are serviced inside a mutex image.
 * The executor never waits for the inner lock. An exact ticket is acquired
 * before one CAS and cancelled on a miss; the source CALL remains pending. */
int kd_mutex_jit_spin_lock_ctx(raw_spinlock_t *lock, struct kd_regs *regs,
			      struct kd_exec_frame *frame)
{
	struct kd_spin_ref ref = { 0 };
	unsigned int index;
	int ret;

	if (!lock || !regs || !frame || !frame->mutex_backend ||
	    !kd_exec_frame_can_borrow_locks(frame))
		return -EINVAL;
	ret = kd_jit_begin_call(frame, regs);
	if (ret)
		return ret;
	/* No acquisition or source instruction has happened at these boundaries.
	 * A native continuation retains prior owners instead of replaying entry. */
	if (frame->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	    kd_exec_frame_lock_contains(frame, (unsigned long)lock) ||
	    frame->jit_lock_depth == KD_EXEC_MAX_LOCK_DEPTH) {
		kd_exec_frame_save_continuation(frame, regs);
		return KD_EXE_KNOWN_NATIVE;
	}
	ret = kd_exec_frame_record_event(frame, KD_EXEC_EVENT_NESTED_LOCK, regs);
	if (ret)
		return ret;
	ret = kd_spin_nested_try_once(lock, &ref);
	if (ret) {
		if (ret == -EAGAIN && kd_exec_mutex_transfer_allowed(frame))
			frame->mutex_mixed.transfer_requested = true;
		kd_exec_frame_save_continuation(frame, regs);
		return KD_EXE_KNOWN_NATIVE;
	}
	index = frame->jit_lock_depth;
	frame->control_call.phase = KD_CALL_ACQUIRED;
	ret = kd_exec_frame_lock_push(frame, (unsigned long)lock,
				      KD_EXEC_LOCK_MUTEX_SPIN, ref.entry);
	if (ret) {
		BUG_ON(kd_spin_nested_release_exact(lock, &ref));
		return ret;
	}
	frame->mutex_mixed.spin_sequence[index] = ref.sequence;
	ret = kd_jit_advance_call(frame, regs);
	if (!ret)
		frame->control_call.phase = KD_CALL_COMPLETE;
	return ret ? ret : 1;
}

int kd_mutex_jit_spin_unlock_ctx(raw_spinlock_t *lock,
				struct kd_exec_frame *frame)
{
	unsigned int i;

	if (!frame || !frame->mutex_backend || !kd_exec_frame_validate(frame))
		return -EINVAL;
	for (i = frame->outer_lock_index + 1; i < frame->jit_lock_depth; i++) {
		struct kd_spin_ref ref;
		int ret;

		if (frame->jit_lock_addr[i] != (unsigned long)lock)
			continue;
		if (frame->jit_lock_kind[i] != KD_EXEC_LOCK_MUTEX_SPIN ||
		    frame->jit_lock_released[i])
			return -EINVAL;
		ref.entry = frame->jit_lock_node[i];
		ref.sequence = frame->mutex_mixed.spin_sequence[i];
		ret = kd_exec_frame_record_event(frame, KD_EXEC_EVENT_NESTED_UNLOCK, NULL);
		if (!ret)
			ret = kd_spin_nested_release_exact(lock, &ref);
		return ret ? ret : kd_exec_frame_lock_pop(frame, (unsigned long)lock);
	}
	return -ENOENT;
}
