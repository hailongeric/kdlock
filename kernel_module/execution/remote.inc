// SPDX-License-Identifier: GPL-2.0
/*
 * Remote frame requests and release/acquire ACKs between physical executors.
 * Private implementation included only by kd_exec.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

struct kd_remote_request {
	struct kd_exec_frame *sender;
	unsigned long lock_addr;
	int result;
	bool done;
};

bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)
{
	int state = frame ? smp_load_acquire(&frame->remote_result) :
			    KD_EXEC_REMOTE_IDLE;

	return state == KD_EXEC_REMOTE_WAITING ||
	       state == KD_EXEC_REMOTE_NATIVE;
}

int kd_exec_remote_unlock(struct kd_exec_frame *frame, unsigned long lock_addr)
{
	struct kd_remote_request request = { .sender = frame,
					     .lock_addr = lock_addr };
	struct kd_exec_frame *parent;

	if (!kd_exec_frame_validate(frame) || frame->mutex_backend ||
	    frame != kd_exec_current_frame() || !lock_addr)
		return -EINVAL;
	parent = frame->resume_target;
	if (!parent || !kd_exec_frame_validate(parent) ||
	    parent->mutex_backend ||
	    parent->logical_task != frame->logical_task ||
	    parent->outer_lock_index >= frame->outer_lock_index ||
	    smp_load_acquire(&parent->remote_result) !=
		    KD_EXEC_REMOTE_WAITING ||
	    parent->control_call.phase != KD_CALL_ENTERED ||
	    parent->delegated_lock_addr != frame->outer_lock_addr)
		return -EINVAL;
	if (cmpxchg(&parent->remote_request, NULL, &request))
		return -EBUSY;
	while (!smp_load_acquire(&request.done))
		cpu_relax();
	return request.result;
}

void kd_exec_remote_poll(struct kd_exec_frame *frame)
{
	struct kd_remote_request *request;
	int ret = -EINVAL;

	if (!frame || !(request = smp_load_acquire(&frame->remote_request)))
		return;
	if (frame == kd_exec_current_frame() &&
	    frame->remote_result == KD_EXEC_REMOTE_WAITING &&
	    request->sender->resume_target == frame &&
	    request->sender->logical_task == frame->logical_task) {
		if (request->lock_addr == frame->outer_lock_addr)
			ret = kd_exec_frame_record_event(
				frame, KD_EXEC_EVENT_OUTER_UNLOCK, NULL);
		else
			ret = kd_spin_jit_nested_unlock_ctx(
				(raw_spinlock_t *)request->lock_addr, frame);
	}
	pr_info("kd_remote unlock: task=%d cpu=%u outer=%lx lock=%lx result=%d\n",
		frame->logical_task->pid, raw_smp_processor_id(),
		frame->outer_lock_addr, request->lock_addr, ret);
	WRITE_ONCE(frame->remote_request, NULL);
	request->result = ret < 0 ? ret : 0;
	/* The sender can discard both its stack request and copied scope now. */
	smp_store_release(&request->done, true);
}

int kd_exec_remote_native(struct kd_exec_frame *frame)
{
	struct kd_exec_frame *parent = frame->resume_target;

	if (!parent)
		return 0;
	if (smp_load_acquire(&parent->remote_result) !=
		    KD_EXEC_REMOTE_WAITING ||
	    READ_ONCE(parent->remote_request))
		return -EINVAL;
	smp_store_release(&parent->remote_result, KD_EXEC_REMOTE_NATIVE);
	return 0;
}

int kd_exec_remote_complete(struct kd_exec_frame *frame)
{
	struct kd_exec_frame *parent = frame->resume_target;

	if (!parent)
		return 0;
	if (!kd_exec_frame_can_complete(frame) ||
	    !kd_exec_frame_remote_pending(parent) ||
	    READ_ONCE(parent->remote_request))
		return -EINVAL;
	frame->resume_target = NULL;
	/* Last parent access: its executor may immediately retire/reuse the frame. */
	smp_store_release(&parent->remote_result, KD_EXEC_REMOTE_DONE);
	return 0;
}

void kd_exec_remote_cancel(struct kd_exec_frame *frame)
{
	struct kd_exec_frame *parent = frame->resume_target;

	if (!parent)
		return;
	BUG_ON(frame->executed ||
	       parent->remote_result != KD_EXEC_REMOTE_WAITING ||
	       READ_ONCE(parent->remote_request));
	/* Cancel this unexecuted child, not its still-queued virtual request.
	 * A retry, local acquisition or native handoff still owns its disposition. */
	frame->resume_target = NULL;
}

/* DONE grants the parent permission to resume and retire. Detach and pop the
 * child first; after publication neither child nor its shared packet is read. */
int kd_exec_spin_retire(struct kd_exec_frame *frame, bool *retired)
{
	struct kd_exec_frame *parent = frame->complex_ready ? frame->resume_target : NULL;
	int ret;

	if (parent && (!kd_exec_frame_can_complete(frame) ||
	    !kd_exec_frame_remote_pending(parent) ||
	    READ_ONCE(parent->remote_request)))
		return -EINVAL;
	if (frame->complex_ready)
		frame->resume_target = NULL;
	ret = kd_exec_frame_pop(frame, NULL);
	if (ret)
		return ret;
	if (retired)
		smp_store_release(retired, true);
	if (parent)
		smp_store_release(&parent->remote_result, KD_EXEC_REMOTE_DONE);
	return 0;
}
