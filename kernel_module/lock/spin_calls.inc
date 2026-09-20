/*
 * Nested spin CALL routing, private tickets, out-of-order release and cleanup.
 * Private implementation included only by kd_lock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static int kd_spin_jit_nested_lock_common(raw_spinlock_t *lock,
					  struct pt_regs *regs,
					  struct kd_exec_frame *frame)
{
	struct kd_exec_frame *active_frame = frame;
	bool promoted;
	int ret;

	if (!lock)
		return -EINVAL;

	promoted = kd_hotlock_is_promoted((unsigned long)lock);
	if (!active_frame)
		active_frame = kd_exec_current_frame();
	if (regs && kd_jit_begin_call(active_frame, regs))
		return -EINVAL;

	if (active_frame) {
		if (kd_exec_frame_lock_contains(active_frame,
						(unsigned long)lock))
			return -EDEADLK;
		if (kd_exec_frame_lock_depth(active_frame) >=
		    KD_EXEC_MAX_LOCK_DEPTH)
			return -E2BIG;
	}

	/* The CPU's combiner stack can be fuller than this logical frame. */
	if (!kd_spin_nested_shadow_has_space())
		return -E2BIG;

	if (!regs || !regs->sp)
		goto fallback;
	if (!active_frame || kd_jit_advance_call(active_frame, regs))
		return -EINVAL;
	if (promoted && !kd_exe_is_ready(0, regs->ip))
		kd_exe_add(0, regs->ip, KD_EXE_LOCK_SPIN);

	if (kd_exec_frame_record_event(active_frame, KD_EXEC_EVENT_NESTED_LOCK,
				       regs))
		return -EINVAL;
	/* Exercise the real staged-RIP case without publishing a B request. */
	if (unlikely(cmpxchg(&kd_jit_fail_pending_lock, 1, 0) == 1))
		return -E2BIG;

	if (promoted) {
		enum kd_exec_lock_kind kind;

		ret = kd_spin_nested_lock((struct qspinlock *)lock, regs,
					  active_frame);
		if (ret < 0)
			return ret;
		if (ret == KD_SPIN_NESTED_NATIVE)
			return KD_EXE_KNOWN_NATIVE;

		kd_spin_debug_nested_lock(lock, false);
		if (ret == KD_SPIN_NESTED_DELEGATED ||
		    ret == KD_SPIN_NESTED_PARENT_OOO) {
			kd_spin_debug_nested_unlock(lock);
			kd_spin_debug_nested_remote(lock);
			kd_exec_frame_save_continuation(active_frame, regs);
			if (ret == KD_SPIN_NESTED_PARENT_OOO) {
				if (!kd_exec_frame_can_complete(active_frame))
					return -EINVAL;
				return KD_EXE_KNOWN_OUTER_UNLOCK;
			}
			return KD_JIT_NESTED_REMOTE;
		}
		kind = ret == KD_SPIN_NESTED_ACQUIRED_QUEUE ?
			       KD_EXEC_LOCK_QUEUE_OWNER :
			       KD_EXEC_LOCK_FAST;

		ret = kd_spin_nested_shadow_push((struct qspinlock *)lock);
		if (ret) {
			kd_spin_unlock_protocol((struct qspinlock *)lock);
			return ret;
		}
		if (kd_exec_frame_lock_push(active_frame, (unsigned long)lock,
					    kind, NULL)) {
			kd_spin_unlock_protocol((struct qspinlock *)lock);
			kd_spin_nested_shadow_remove((struct qspinlock *)lock);
			return -E2BIG;
		}
		if ((kind == KD_EXEC_LOCK_FAST ||
		     kind == KD_EXEC_LOCK_QUEUE_OWNER) &&
		    unlikely(cmpxchg(&kd_spin_jit_fail_after_nested_lock, 1,
				     0) == 1)) {
			KD_PR_INFO(
				"spin JIT injected failure after nested lock=%px outer=%lx val=%x kind=%d\n",
				lock, active_frame->outer_lock_addr,
				atomic_read(&((struct qspinlock *)lock)->val),
				kind);
			return -EIO;
		}
		active_frame->control_call.phase = KD_CALL_COMPLETE;
		return KD_JIT_NESTED_CONSUMED;
	}

fallback:
	if (active_frame && !regs &&
	    kd_exec_frame_record_event(active_frame, KD_EXEC_EVENT_NESTED_LOCK,
				       NULL))
		return -EINVAL;

	kd_hotlock_record((unsigned long)lock);
	if (active_frame)
		active_frame->control_call.phase = KD_CALL_ENTERED;
	origin_raw_spin_lock(lock);
	if (active_frame)
		active_frame->control_call.phase = KD_CALL_ACQUIRED;
	if (kd_spin_nested_shadow_push((struct qspinlock *)lock)) {
		origin_raw_spin_unlock(lock);
		return -E2BIG;
	}
	if (active_frame &&
	    kd_exec_frame_lock_push(active_frame, (unsigned long)lock,
				    KD_EXEC_LOCK_NATIVE, NULL)) {
		kd_spin_nested_shadow_remove((struct qspinlock *)lock);
		origin_raw_spin_unlock(lock);
		return -E2BIG;
	}
	kd_spin_debug_nested_lock(lock, true);
	if (active_frame)
		active_frame->control_call.phase = KD_CALL_COMPLETE;
	return regs ? KD_JIT_NESTED_CONSUMED : KD_JIT_NESTED_NATIVE;
}

int kd_spin_jit_nested_lock_ctx(raw_spinlock_t *lock, struct pt_regs *regs,
				struct kd_exec_frame *frame)
{
#ifdef KDLOCK_SELFTEST
	bool pressure = kd_spin_selftest_shadow_begin(lock, regs, frame);
	int ret = kd_spin_jit_nested_lock_common(lock, regs, frame);

	if (pressure)
		kd_spin_selftest_shadow_end(regs, frame, ret);
	return ret;
#else
	return kd_spin_jit_nested_lock_common(lock, regs, frame);
#endif
}

int kd_spin_jit_nested_unlock_ctx(raw_spinlock_t *lock,
				  struct kd_exec_frame *frame)
{
	struct kd_exec_frame *active_frame = frame;
	enum kd_exec_lock_kind kind;
	unsigned int i;

	if (!lock)
		return -EINVAL;
	if (!active_frame)
		active_frame = kd_exec_current_frame();
	if (!kd_exec_frame_validate(active_frame) ||
	    active_frame->outer_lock_index >= active_frame->jit_lock_depth)
		return -EINVAL;
	for (i = 0; i < active_frame->outer_lock_index; i++) {
		int ret;

		if (active_frame->jit_lock_addr[i] != (unsigned long)lock)
			continue;
		if (active_frame->jit_lock_released[i])
			return -EALREADY;
		ret = kd_exec_remote_unlock(active_frame, (unsigned long)lock);
		return ret ? ret :
			     kd_exec_frame_lock_mark_released(
				     active_frame, (unsigned long)lock);
	}

	kind = kd_exec_frame_lock_kind(active_frame, (unsigned long)lock);
	if (kind == KD_EXEC_LOCK_NONE)
		return -ENOENT;

	if (kd_exec_frame_record_event(active_frame,
				       KD_EXEC_EVENT_NESTED_UNLOCK, NULL))
		return -EINVAL;

	if (kind == KD_EXEC_LOCK_NATIVE) {
		kd_spin_debug_nested_unlock(lock);
		origin_raw_spin_unlock(lock);
		if (kd_spin_nested_shadow_remove((struct qspinlock *)lock))
			return -EINVAL;
		if (kd_exec_frame_lock_pop(active_frame, (unsigned long)lock))
			return -EINVAL;
		if (kd_exec_frame_can_complete(active_frame))
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		return 0;
	}

	kd_spin_debug_nested_unlock(lock);
	{
		int unlock_ret =
			kd_spin_nested_unlock((struct qspinlock *)lock);

		if (unlock_ret < 0)
			return unlock_ret;
		if (unlock_ret == KD_SPIN_NESTED_UNLOCK_OOO)
			return kd_exec_frame_lock_mark_released(
				active_frame, (unsigned long)lock);
	}
	if (kd_exec_frame_lock_pop(active_frame, (unsigned long)lock))
		return -EINVAL;
	if (kd_exec_frame_can_complete(active_frame))
		return KD_EXE_KNOWN_OUTER_UNLOCK;
	return 0;
}

int kd_spin_jit_outer_unlock_ooo_ctx(raw_spinlock_t *lock, struct pt_regs *regs,
				     struct kd_exec_frame *frame)
{
	if (!lock || !frame || frame->outer_lock_addr != (unsigned long)lock ||
	    !kd_exec_frame_has_unreleased_nested(frame))
		return -EINVAL;

	if (kd_exec_frame_record_event(frame, KD_EXEC_EVENT_OUTER_UNLOCK, regs))
		return -EINVAL;

	/* The local batch callback already opened L/S. Never mark a successor's
	 * scheduling word OOO after publication. Inherited ancestors use the
	 * logical-parent request protocol above, never another CPU's ticket. */
	if (frame->outer_unlock_hook && frame->outer_unlock_hook->released)
		return 0;
	kd_spin_unlock_protocol((struct qspinlock *)lock);
	return 0;
}

int kd_spin_jit_nested_cleanup(struct kd_exec_frame *frame)
{
	unsigned int i;

	if (!frame || !kd_exec_frame_can_complete(frame))
		return -EINVAL;

	for (i = frame->jit_lock_depth; i > frame->outer_lock_index + 1; i--) {
		unsigned long lock_addr = frame->jit_lock_addr[i - 1];
		int ret;

		if (!frame->jit_lock_released[i - 1])
			return -EBUSY;
		ret = kd_spin_nested_shadow_remove(
			(struct qspinlock *)lock_addr);
		if (ret && ret != -ENOENT)
			return ret;
		ret = kd_exec_frame_lock_pop(frame, lock_addr);
		if (ret)
			return ret;
	}

	return 0;
}

int kd_spin_jit_abort_cleanup(struct kd_exec_frame *frame)
{
	unsigned int cleaned = 0;

	if (!frame || !kd_exec_frame_validate(frame) ||
	    frame->outer_lock_index >= frame->jit_lock_depth)
		return -EINVAL;

	while (frame->jit_lock_depth > frame->outer_lock_index + 1) {
		unsigned int index = frame->jit_lock_depth - 1;
		unsigned long lock_addr = frame->jit_lock_addr[index];
		enum kd_exec_lock_kind kind = frame->jit_lock_kind[index];
		bool released = frame->jit_lock_released[index];
		int before = atomic_read(&((struct qspinlock *)lock_addr)->val);
		int ret;

		if (!released) {
			if (kind == KD_EXEC_LOCK_NATIVE) {
				kd_spin_debug_nested_unlock(
					(raw_spinlock_t *)lock_addr);
				origin_raw_spin_unlock(
					(raw_spinlock_t *)lock_addr);
			} else if (kind == KD_EXEC_LOCK_FAST ||
				   kind == KD_EXEC_LOCK_QUEUE_OWNER) {
				kd_spin_debug_nested_unlock(
					(raw_spinlock_t *)lock_addr);
				ret = kd_spin_nested_unlock(
					(struct qspinlock *)lock_addr);
				if (ret < 0)
					return ret;
				if (ret == KD_SPIN_NESTED_UNLOCK_OK)
					goto pop_entry;
			} else {
				return -EINVAL;
			}
		}

		/* OOO unlocks and native locks retain a shadow entry. */
		ret = kd_spin_nested_shadow_remove(
			(struct qspinlock *)lock_addr);
		if (ret && ret != -ENOENT)
			return ret;

pop_entry:
		ret = kd_exec_frame_lock_pop(frame, lock_addr);
		if (ret)
			return ret;
		KD_PR_INFO(
			"spin JIT abort release: lock=%lx kind=%d was_released=%d before=%x after=%x\n",
			lock_addr, kind, released, before,
			atomic_read(&((struct qspinlock *)lock_addr)->val));
		cleaned++;
	}
	if (cleaned)
		KD_PR_INFO("spin JIT abort cleanup: outer=%lx released=%u\n",
			   frame->outer_lock_addr, cleaned);

	return 0;
}
