// SPDX-License-Identifier: GPL-2.0
/*
 * Original-waiter native continuation and owner-serviced final unlock ACKs.
 * Private implementation included only by kd_exec.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

bool kd_exec_frame_can_borrow_locks(const struct kd_exec_frame *frame)
{
	/* A suspended request has retained acquisition records but no current
	 * physical activation. Only its explicit owner service may act on them. */
	if (frame && kd_exec_frame_continuation(frame) &&
	    kd_exec_frame_continuation(frame)->state != KD_CONT_BOUND)
		return false;
	/* Service-owned records have their own exact release path. Legacy native
	 * suffix registration must not treat the one-entry compatibility vector
	 * as the complete linked acquisition set. */
	if (frame && kd_exec_frame_continuation(frame) &&
	    kd_exec_frame_continuation(frame)->service_ops)
		return false;
	if (!kd_exec_frame_validate(frame) || frame->completion_seen ||
	    kd_exec_frame_state(frame) == KD_EXEC_FRAME_ERROR ||
	    frame->outer_lock_index >= frame->jit_lock_depth ||
	    frame->jit_lock_addr[frame->outer_lock_index] !=
		    frame->outer_lock_addr ||
	    frame->jit_lock_released[frame->outer_lock_index] !=
		    frame->outer_unlock_seen)
		return false;
	return !frame->outer_unlock_seen ||
	       kd_exec_frame_has_unreleased_nested(frame);
}

unsigned int kd_exec_mutex_spin_count(const struct kd_exec_frame *frame)
{
	unsigned int i, count = 0;

	if (!frame || !frame->mutex_backend || !frame->complex_ready)
		return 0;
	for (i = frame->outer_lock_index + 1; i < frame->jit_lock_depth; i++)
		count += frame->jit_lock_kind[i] == KD_EXEC_LOCK_MUTEX_SPIN &&
			 !frame->jit_lock_released[i];
	return count;
}

bool kd_exec_mutex_transfer_allowed(const struct kd_exec_frame *frame)
{
	return frame && frame->mutex_backend && frame->complex_ready &&
		frame->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 &&
		!frame->parent && !frame->depth && !frame->request_frame &&
		kd_exec_frame_can_borrow_locks(frame) && !frame->outer_unlock_seen &&
		frame->outer_lock_index == 0 && frame->jit_lock_depth == 1 &&
		frame->jit_lock_kind[0] == KD_EXEC_LOCK_QUEUE_OWNER &&
		frame->jit_lock_node[0] == (void *)frame->outer_lock_addr &&
		frame->outer_unlock_hook && !frame->outer_unlock_hook->released &&
		frame->control_call.phase == KD_CALL_PENDING &&
		!kd_exec_frame_remote_pending(frame) && !frame->resume_target &&
		!frame->remote_request && !frame->native_request &&
		list_empty(&frame->native_link) && !frame->mutex_mixed.transferred;
}

/* The native wake supplies a stable frame reference. The executor retains its
 * source lease and route until this task's real physical unlock is acknowledged. */
int kd_exec_mutex_transfer_pickup(struct kd_exec_frame *frame)
{
	int ret;

	if (!frame || !frame->mutex_backend || !frame->mutex_mixed.transferred ||
	    frame->logical_task != current || frame->mutex_mixed.picked_up)
		return -EINVAL;
	ret = kd_mutex_transfer_pickup((struct kd_mutex *)frame->outer_lock_addr);
	if (!ret)
		smp_store_release(&frame->mutex_mixed.picked_up, true);
	return ret;
}

#ifdef KDLOCK_SELFTEST
#include "../../tests/kernel/execution/exec_relay_exit_probe.c"
#endif

/* Retained scopes use this same registry and O-stack request storage. Their
 * linked owner set is resolved by typed callbacks, not the legacy vector. */
int kd_exec_native_service_begin(struct kd_exec_frame *frame)
{
	struct kd_exec_continuation *cont = frame ? kd_exec_frame_continuation(frame) : NULL;
	unsigned long flags;

	if (!kd_exec_cont_valid(cont) || !cont->service_ops || !cont->service_ops->native_match ||
	    !cont->service_ops->native_release || !cont->service_ops->native_finished ||
	    cont->state != KD_CONT_SUSPENDED || cont->resume_executor != current ||
	    cont->executor || !frame->executed || frame->completion_seen ||
	    frame->logical_task == current || frame->packet_state != KD_PACKET_FULL ||
	    !kd_exec_frame_regs(frame)->ip || !kd_exec_frame_regs(frame)->sp ||
	    kd_exec_frame_regs(frame)->orig_ax != KD_REG_ORIGIN_SUFFIX_TAG ||
	    !kd_exec_cont_no_stack_service(frame))
		return -EINVAL;
	raw_spin_lock_irqsave(&kd_native_lock, flags);
	cont->native_accepted = false;
	list_add(&frame->native_link, &kd_native_frames);
	raw_spin_unlock_irqrestore(&kd_native_lock, flags);
	atomic64_inc(&kd_native_started);
	return 0;
}

static void kd_exec_native_service_request_wait(struct kd_native_request *request)
{
	while (!smp_load_acquire(&request->done)) {
		cpu_relax();
		if (!preempt_count() && !irqs_disabled() && need_resched())
			cond_resched();
	}
	/* Only O-stack data remains valid after the final E acknowledgment. */
	BUG_ON(request->result);
}

int kd_exec_native_accept(struct kd_exec_frame *frame)
{
	struct kd_native_request request = {
		.route.operation = KD_NATIVE_OPERATION_ACCEPT,
	};
	struct kd_exec_continuation *cont;
	unsigned long flags;

	/* The initial READY transport retains this exact frame until acceptance.
	 * The caller has already copied every packet/completion field it needs. */
	raw_spin_lock_irqsave(&kd_native_lock, flags);
	cont = frame ? kd_exec_frame_continuation(frame) : NULL;
	if (!kd_exec_cont_valid(cont) || !cont->service_ops || frame->logical_task != current ||
	    list_empty(&frame->native_link) || frame->native_request ||
	    cont->native_accepted || cont->state != KD_CONT_SUSPENDED) {
		raw_spin_unlock_irqrestore(&kd_native_lock, flags);
		return -EINVAL;
	}
	smp_store_release(&frame->native_request, &request);
	raw_spin_unlock_irqrestore(&kd_native_lock, flags);
	kd_exec_native_service_request_wait(&request);
	/* Do not inspect frame: E may already have retired it. */
	return 0;
}

bool kd_exec_native_service_active(struct task_struct *task)
{
	struct kd_exec_frame *frame;
	unsigned long flags;
	bool found = false;

	if (list_empty(&kd_native_frames))
		return false;
	raw_spin_lock_irqsave(&kd_native_lock, flags);
	list_for_each_entry(frame, &kd_native_frames, native_link) {
		struct kd_exec_continuation *cont = kd_exec_frame_continuation(frame);

		if (frame->logical_task == task && cont && cont->service_ops) {
			found = true;
			break;
		}
	}
	raw_spin_unlock_irqrestore(&kd_native_lock, flags);
	return found;
}

bool kd_exec_native_service_owned(unsigned long object)
{
	struct kd_exec_frame *frame;
	struct kd_exec_native_route route;
	unsigned long flags;
	bool found = false;

	if (list_empty(&kd_native_frames))
		return false;
	raw_spin_lock_irqsave(&kd_native_lock, flags);
	list_for_each_entry(frame, &kd_native_frames, native_link) {
		struct kd_exec_continuation *cont = kd_exec_frame_continuation(frame);

		if (frame->logical_task == current && cont && cont->service_ops &&
		    cont->service_ops->native_match && cont->native_accepted &&
		    cont->service_ops->native_match(cont->service_scope, object,
			KD_NATIVE_OPERATION_WRITE_OWNED, &route)) {
			found = true;
			break;
		}
	}
	raw_spin_unlock_irqrestore(&kd_native_lock, flags);
	return found;
}

bool kd_exec_native_service_unlock(unsigned long object,
	enum kd_exec_native_operation operation)
{
	struct kd_native_request request = { .lock_addr = object };
	struct kd_exec_frame *frame;
	unsigned long flags;
	bool found = false;
	bool caller_atomic = preempt_count() || irqs_disabled();

#ifdef CONFIG_PREEMPT_RCU
	caller_atomic |= READ_ONCE(current->rcu_read_lock_nesting) != 0;
#endif
	if (list_empty(&kd_native_frames))
		return false;
	BUG_ON(operation != KD_NATIVE_OPERATION_MUTEX_UNLOCK &&
	       operation != KD_NATIVE_OPERATION_RWSEM_UP_WRITE &&
	       operation != KD_NATIVE_OPERATION_RWSEM_DOWNGRADE &&
	       operation != KD_NATIVE_OPERATION_RWSEM_UP_READ);
	raw_spin_lock_irqsave(&kd_native_lock, flags);
	list_for_each_entry(frame, &kd_native_frames, native_link) {
		struct kd_exec_continuation *cont = kd_exec_frame_continuation(frame);

		if (frame->logical_task != current || !cont || !cont->service_ops ||
		    !cont->service_ops->native_match || !cont->native_accepted ||
		    !cont->service_ops->native_match(cont->service_scope, object,
			operation, &request.route))
			continue;
		/* Unlike an anonymous reader decrement, this operation waits for E's
		 * physical writer release and wakeups. A proxied read tail is admitted
		 * only in ordinary task context; never fall through to a reader credit
		 * when that exact route is found in an unsupported atomic context. */
		BUG_ON(operation == KD_NATIVE_OPERATION_RWSEM_UP_READ && caller_atomic);
		BUG_ON(frame->native_request);
		smp_store_release(&frame->native_request, &request);
		found = true;
		break;
	}
	raw_spin_unlock_irqrestore(&kd_native_lock, flags);
	if (found)
		kd_exec_native_service_request_wait(&request);
	return found;
}

static int kd_exec_native_service_wait(struct kd_exec_frame *frame)
{
	struct kd_exec_continuation *cont = kd_exec_frame_continuation(frame);

	BUG_ON(!cont || !cont->service_ops || cont->state != KD_CONT_SUSPENDED ||
	       cont->resume_executor != current);
	for (;;) {
		struct kd_native_request *request = smp_load_acquire(&frame->native_request);

		if (request) {
			unsigned long flags;
			bool finished;
			int ret;

			if (request->route.operation == KD_NATIVE_OPERATION_ACCEPT) {
				BUG_ON(cont->native_accepted);
				cont->native_accepted = true;
				ret = 0;
			} else {
				BUG_ON(!cont->native_accepted);
				/* Actual owner operations never run under the registry guard. */
				ret = cont->service_ops->native_release(cont->service_scope,
					&request->route);
				atomic64_inc(&kd_native_unlocks);
			}
			finished = cont->native_accepted &&
				cont->service_ops->native_finished(cont->service_scope);
			raw_spin_lock_irqsave(&kd_native_lock, flags);
			BUG_ON(frame->native_request != request);
			WRITE_ONCE(frame->native_request, NULL);
			if (finished || ret)
				list_del_init(&frame->native_link);
			raw_spin_unlock_irqrestore(&kd_native_lock, flags);
			request->result = ret;
			/* Last access: O may immediately discard its request/frame pointer. */
			smp_store_release(&request->done, true);
			if (finished || ret)
				return ret;
		}
		cpu_relax();
		if (need_resched())
			cond_resched();
	}
}

/* Publish routing only for a validated continuation packet. This function
 * neither transfers ownership nor jumps to source. A mutex batch may exchange
 * its physical owner afterwards, before publishing the native waiter wake. */
int kd_exec_native_begin(struct kd_exec_frame *frame, bool mutex)
{
	unsigned long flags;
	unsigned int i, remaining = 0;
	bool relay = !mutex && frame &&
		     smp_load_acquire(&frame->remote_result) ==
			     KD_EXEC_REMOTE_NATIVE &&
		     frame->control_call.phase == KD_CALL_COMPLETE;
	bool checked_mutex =
		mutex && frame &&
		frame->control_call.phase == KD_CALL_STACK_CHANGED &&
		kd_call_after_matches(&frame->control_call, kd_exec_frame_regs(frame)->ip,
				      kd_exec_frame_regs(frame)->sp);
	bool checked_spin = !mutex && frame &&
			    frame->control_call.phase == KD_CALL_SPIN_NATIVE &&
			    kd_call_after_matches(&frame->control_call,
						  kd_exec_frame_regs(frame)->ip,
						  kd_exec_frame_regs(frame)->sp);
	int ret;

	if ((!kd_exec_frame_can_borrow_locks(frame) &&
	     !(relay && kd_exec_frame_validate(frame) &&
	       !frame->completion_seen &&
	       kd_exec_frame_state(frame) != KD_EXEC_FRAME_ERROR &&
	       kd_exec_frame_locks_released(frame) &&
	       frame->jit_lock_addr[frame->outer_lock_index] ==
		       frame->outer_lock_addr)) ||
	    !kd_exec_frame_regs(frame)->ip || !kd_exec_frame_regs(frame)->sp ||
	    frame->logical_task == current || frame->mutex_backend != mutex ||
	    (frame->control_call.phase == KD_CALL_PENDING &&
	     (!frame->control_call.return_ip ||
	      kd_exec_frame_regs(frame)->ip != frame->control_call.target ||
	      kd_exec_frame_regs(frame)->sp != frame->control_call.stack)))
		return -EINVAL;
	/* These distinct tags authorize validated post-control boundaries. The
	 * original owner retains acquired locks; the waiter must not call the
	 * completed lock/unlock again. Other COMPLETE/partial phases stay refused. */
	if (frame->control_call.phase != KD_CALL_NONE &&
	    frame->control_call.phase != KD_CALL_PENDING && !relay &&
	    !checked_mutex && !checked_spin)
		return -EINVAL;
	for (i = frame->outer_lock_index; i < frame->jit_lock_depth; i++)
		remaining += !frame->jit_lock_released[i];
	if (!mutex) {
		ret = kd_spin_entry_borrow_get(&frame->spin_origin);
		if (ret)
			return ret;
	}
	frame->native_request = NULL;
	frame->logical_pid = frame->logical_task->pid;
	INIT_LIST_HEAD(&frame->native_link);
	if (remaining) {
		raw_spin_lock_irqsave(&kd_native_lock, flags);
		list_add(&frame->native_link, &kd_native_frames);
		raw_spin_unlock_irqrestore(&kd_native_lock, flags);
	}
	atomic64_inc(&kd_native_started);
	pr_info("kd_native begin: task=%d outer=%lx entry=%lx ip=%lx sp=%lx held=%u mutex=%u cpu=%u outer_released=%u remaining=%u\n",
		frame->logical_task->pid, frame->outer_lock_addr,
		frame->entry_ip, kd_exec_frame_regs(frame)->ip, kd_exec_frame_regs(frame)->sp,
		frame->jit_lock_depth - frame->outer_lock_index, mutex,
		raw_smp_processor_id(), frame->outer_unlock_seen, remaining);
#ifdef KDLOCK_SELFTEST
	kd_exec_selftest_relay_arm(frame, remaining);
#endif
	return 0;
}

/* Routing describes physical locks; the ticket separately retains executors.
 * No new route can appear after the root publishes NATIVE_READY. */
bool kd_exec_native_pending(struct task_struct *task)
{
	struct kd_exec_frame *frame;
	unsigned long flags;
	bool pending = false;

	raw_spin_lock_irqsave(&kd_native_lock, flags);
	list_for_each_entry(frame, &kd_native_frames, native_link)
		if (!frame->mutex_backend && frame->logical_task == task) {
			pending = true;
			break;
		}
	raw_spin_unlock_irqrestore(&kd_native_lock, flags);
	return pending;
}

/* Called on the original waiter's stack. A matching retained owner must finish
 * the unlock before this local request can disappear on return. */
bool kd_exec_native_unlock(unsigned long lock_addr, bool mutex)
{
	struct kd_native_request request = { .lock_addr = lock_addr };
	struct kd_exec_frame *frame;
	unsigned long flags;
	bool found = false;

	if (mutex && kd_exec_native_service_unlock(lock_addr,
		KD_NATIVE_OPERATION_MUTEX_UNLOCK))
		return true;
	if (list_empty(&kd_native_frames))
		return false;
	raw_spin_lock_irqsave(&kd_native_lock, flags);
	list_for_each_entry(frame, &kd_native_frames, native_link) {
		unsigned int i;

		if (frame->logical_task != current)
			continue;
		/* Retained scopes are handled above through their full owner list. */
		if (kd_exec_frame_continuation(frame) &&
		    kd_exec_frame_continuation(frame)->service_ops)
			continue;
		/* Ancestors copied into a remote B frame still belong to A's
		 * executor. Only route the locks owned by this particular frame. */
		for (i = frame->outer_lock_index; i < frame->jit_lock_depth;
		     i++) {
			if (frame->jit_lock_addr[i] != lock_addr ||
			    frame->jit_lock_released[i])
				continue;
			request.mixed_spin = frame->mutex_backend &&
				frame->jit_lock_kind[i] == KD_EXEC_LOCK_MUTEX_SPIN;
			if (mutex != (frame->mutex_backend && !request.mixed_spin))
				continue;
			request.owner_release = frame->mutex_backend &&
				frame->mutex_mixed.transferred && i == frame->outer_lock_index;
			BUG_ON(frame->native_request);
			smp_store_release(&frame->native_request, &request);
			found = true;
			break;
		}
		if (found)
			break;
	}
	raw_spin_unlock_irqrestore(&kd_native_lock, flags);
	if (!found)
		return false;
	if (request.owner_release) {
		/* Ownership has really moved to this task. The old executor may
		 * observe completion only after this owner releases both A and gate. */
		request.result = _kd_mutex_unlock_checked((struct kd_mutex *)lock_addr);
		smp_store_release(&request.owner_released, true);
	}

	/* The acknowledgment lives on the waiter's native stack, not in the
	 * executor frame, which may be retired as soon as it acknowledges. */
	while (!smp_load_acquire(&request.done)) {
		cpu_relax();
		/* An out-of-order A unlock may still hold a restored logical B pin. */
		if (mutex && !preempt_count())
			cond_resched();
	}
	BUG_ON(request.result);
	if (request.mixed_spin) {
		/* The executor retired its physical ticket before ACK. This is the
		 * original task's separately restored logical spin acquisition pin. */
		preempt_enable();
	} else if (!mutex && !kd_exec_native_pending(current)) {
		request.spin_last = true;
		kd_spin_native_retire(&request.spin_origin);
	}
	/* The executor's completion log may follow its release-store. Observe
	 * acknowledgment on the waiter, using only its still-live stack data. */
	pr_info("kd_native ack: task=%d lock=%lx mutex=%u last_spin=%u\n",
		current->pid, request.lock_addr, mutex, request.spin_last);
	return true;
}

static int kd_exec_native_finish(struct kd_exec_frame *frame)
{
	int ret;

#ifdef KDLOCK_SELFTEST
	kd_exec_selftest_relay_finish(frame);
#endif
	ret = frame->mutex_backend ? kd_exec_remote_complete(frame) : 0;

	if (ret)
		return ret;
	atomic64_inc(&kd_native_completed);
	/* Capture identity was established before NATIVE_READY; retirement follows. */
	pr_info("kd_native complete: task=%d outer=%lx mutex=%u\n",
		frame->logical_pid, frame->outer_lock_addr,
		frame->mutex_backend);
	return 0;
}

/* The executor pauses its batch here, servicing the waiter's unlocks. A
 * transferred mutex is already owned by the waiter; only its real release is
 * acknowledged here. Other physical locks stay owned by this executor.
 * Remove routing/references before the final release ACK; an awakened waiter
 * may immediately return, exit, or discard its request storage. */
int kd_exec_native_wait(struct kd_exec_frame *frame)
{
	u64 start = kd_exe_native_timing_start();
	bool mutex = frame->mutex_backend;
	int result;

	if (kd_exec_frame_continuation(frame) &&
	    kd_exec_frame_continuation(frame)->service_ops)
		return kd_exec_native_service_wait(frame);
	/* Publication precedes this entry: an already-running waiter prefix is
	 * outside this interval. Include unlock/finish work and error returns;
	 * nested relay waits overlap and must not be summed as wall time. */
	for (;;) {
		struct kd_native_request *request =
			smp_load_acquire(&frame->native_request);

		if (request && (!request->owner_release ||
				 smp_load_acquire(&request->owner_released))) {
			unsigned long flags;
			bool complete, local_complete;
			int ret;

			if (request->owner_release) {
				ret = request->result;
				if (!smp_load_acquire(&frame->mutex_mixed.picked_up) ||
				    !frame->mutex_mixed.transferred ||
				    request->lock_addr != frame->outer_lock_addr ||
				    kd_exec_frame_has_unreleased_nested(frame))
					ret = -EINVAL;
				if (!ret) {
					/* This records an acknowledged physical unlock, never a
					 * synthetic release at the ownership-transfer point. */
					frame->outer_unlock_hook->released = true;
					ret = kd_exec_frame_record_event(frame,
						KD_EXEC_EVENT_OUTER_UNLOCK, NULL);
				}
			} else if (request->lock_addr == frame->outer_lock_addr)
				ret = kd_exec_frame_record_event(
					frame, KD_EXEC_EVENT_OUTER_UNLOCK,
					NULL);
			else if (request->mixed_spin)
				ret = kd_mutex_jit_spin_unlock_ctx(
					(raw_spinlock_t *)request->lock_addr, frame);
			else if (frame->mutex_backend)
				ret = kd_mutex_jit_nested_unlock_ctx(
					(struct kd_mutex *)request->lock_addr,
					frame);
			else
				ret = kd_spin_jit_nested_unlock_ctx(
					(raw_spinlock_t *)request->lock_addr,
					frame);
			complete = kd_exec_frame_can_complete(frame);
			local_complete = kd_exec_frame_locks_released(frame);
			atomic64_inc(&kd_native_unlocks);
			WRITE_ONCE(frame->native_request, NULL);
			if (local_complete || ret < 0) {
				raw_spin_lock_irqsave(&kd_native_lock, flags);
				list_del_init(&frame->native_link);
				raw_spin_unlock_irqrestore(&kd_native_lock,
							   flags);
			}
			if (local_complete && frame->mutex_backend)
				kd_mutex_task_put(frame->logical_task);
			if (!frame->mutex_backend)
				request->spin_origin = frame->spin_origin;
			if (complete && ret >= 0)
				ret = kd_exec_native_finish(frame);
			request->result = ret < 0 ? ret : 0;
			/* Last access: the waiter can return and discard request. */
			smp_store_release(&request->done, true);
			if (ret < 0) {
				result = ret;
				break;
			}
			if (complete) {
				result = 0;
				break;
			}
		}
		if (kd_exec_frame_can_complete(frame)) {
			result = kd_exec_native_finish(frame);
			break;
		}
		cpu_relax();
		/* A retained mixed spin ticket forbids scheduling this executor even
		 * though its root is a sleepable mutex. Its own final ACK retires the
		 * physical pin before this check can make scheduling legal again. */
		if (frame->mutex_backend && need_resched() &&
		    !kd_exec_mutex_spin_count(frame)) {
			preempt_enable();
			cond_resched();
			preempt_disable();
		}
	}
	/* No request/task access after the final ACK; the caller still owns its
	 * frame, but only the captured backend is needed for this observation. */
	kd_exe_native_timing_end(mutex, start);
	return result;
}
