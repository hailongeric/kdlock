// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Delegated mutex bodies, detached outer batches and successor publication.
 * Private implementation included only by kd_mutex.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

struct kd_mutex_batch {
	struct kd_exec_outer_unlock outer;
	struct kd_mutex_node *next;
};

/* The successor is still queued and cannot reuse its node or caller stack
 * before this batch publishes a wake. Fetch its read-mostly header, the saved
 * SP/BP packet lines, and the two stack lines around the virtual return slot.
 * Do this before the current body; never chase a successor after handoff. */
static void kd_mutex_prefetch_successor(struct kd_mutex_node *next)
{
	unsigned long sp;

	if (!next)
		return;
	prefetch(next);
	prefetch(&next->regs.sp);
	prefetch(&next->regs.bp);
	sp = READ_ONCE(next->regs.sp);
	if (sp) {
		prefetch((void *)sp);
		prefetch((void *)(sp - 64));
	}
}

/* Detach A's queue while this executor still owns B. The saved successor is
 * never touched again after publication; it may complete and reuse its slot. */
static int kd_mutex_release_outer(struct kd_exec_frame *frame,
				  struct kd_exec_outer_unlock *hook)
{
	struct kd_mutex_batch *batch =
		container_of(hook, struct kd_mutex_batch, outer);
	struct kd_mutex *lock = frame->jit_lock_node[frame->outer_lock_index];
	unsigned int i, remaining = 0;
	int ret;

	if (!frame->mutex_backend || !lock || !batch->next ||
	    !batch->next->task_struct_ptr ||
	    frame->jit_lock_kind[frame->outer_lock_index] !=
		    KD_EXEC_LOCK_QUEUE_OWNER ||
	    frame->outer_lock_addr != lock->origin_mutex_addr ||
	    READ_ONCE(lock->locked) != _Q_LOCKED_COMBINER_VAL)
		return -EINVAL;
	for (i = frame->outer_lock_index; i < frame->jit_lock_depth; i++)
		remaining += !frame->jit_lock_released[i];
	/* A native successor can run as soon as L opens. Log release intent
	 * before that point, as on the spin path; the observer proves progress. */
	pr_info("kd_mutex outer release: task=%d owner=%d owner_task=%lx outer=%lx next_task=%d remaining=%u\n",
		frame->logical_task->pid, current->pid, (unsigned long)current,
		frame->outer_lock_addr,
		batch->next->task_struct_ptr->pid, remaining);
	ret = _kd_mutex_unlock_checked(lock);
	if (ret)
		return ret;
	smp_store_release(&batch->next->locked, 0);
	return 0;
}

/* --------------------------------------------------------------------------
 * JIT-sandbox execution of a waiter's critical section
 *
 * The kernel's mutex_lock saves ALL callee-saved registers before capturing
 * ret_rsp (confirmed via disassembly).  Stack layout at ret_rsp:
 *   [0] = lock ptr / padding    [4] = saved r14
 *   [1] = saved rbx             [5] = saved r15
 *   [2] = saved r12             [6] = saved rbp (caller's)
 *   [3] = saved r13             [7] = return address (CS entry)
 * Only legacy callers use that layout. Versioned callers explicitly supply
 * their post-CALL IP/SP/BP and must never decode a compiler-generated frame.
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
execute_cs(struct kd_mutex *lock, struct kd_mutex_node *curr_node,
	   struct kd_mutex_batch *batch)
{
	void *incoming_rsp_ptr = (void *)curr_node->regs.sp;
	struct kd_exec_frame *frame;
	struct kd_exe_info *exe;
	struct pt_regs retry_regs, *regs;
	bool clobber = curr_node->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	unsigned long lock_addr[1];
	enum kd_exec_lock_kind lock_kind[1];
	void *lock_node[1];
	int ret_flag;
	int frame_ret;
	u64 queue_end;

	BUG_ON(READ_ONCE(lock->physical_owner) != current);
	BUG_ON(!kd_origin_mutex_owned((struct mutex *)lock->origin_mutex_addr,
				      current));
	if (!incoming_rsp_ptr)
		return KD_EXE_RUN_ERROR;
	if (!kd_mutex_jit_is_enabled())
		return KD_EXE_NO_RUN;

	if (!clobber) {
		curr_node->regs.bx = ((unsigned long *)incoming_rsp_ptr)[1];
		curr_node->regs.r12 = ((unsigned long *)incoming_rsp_ptr)[2];
		curr_node->regs.r13 = ((unsigned long *)incoming_rsp_ptr)[3];
		curr_node->regs.r14 = ((unsigned long *)incoming_rsp_ptr)[4];
		curr_node->regs.r15 = ((unsigned long *)incoming_rsp_ptr)[5];
		curr_node->regs.bp = ((unsigned long *)incoming_rsp_ptr)[6];
		curr_node->regs.ip = ((unsigned long *)incoming_rsp_ptr)[7];
		curr_node->regs.sp = (unsigned long)incoming_rsp_ptr + 64;
	}
	if (!curr_node->regs.ip ||
	    (curr_node->saved_ret_addr &&
	     curr_node->regs.ip != curr_node->saved_ret_addr)) {
		this_cpu_inc(kd_mutex_frame_failure_count);
		return KD_EXE_RUN_ERROR;
	}

	mutex_debug("JIT exec waiter cpu %d ip %lx sp %lx\n", (curr_node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1,
		    curr_node->regs.ip, curr_node->regs.sp);

	exe = kd_exe_find_ready(0, curr_node->regs.ip);
	if (!exe) {
		this_cpu_inc(kd_mutex_jit_not_ready_count);
		/* A missing/cold image is an unstarted request, not a progressed
		 * frame failure. Keep its identity distinct from context refusal. */
		KD_PR_DEBUG("mutex JIT not ready: task=%d waiter=%d entry=%lx lock=%lx cpu=%u\n",
			    current->pid, curr_node->task_struct_ptr->pid,
			    curr_node->regs.ip, lock->origin_mutex_addr,
			    raw_smp_processor_id());
		kd_exe_add_abi(0, curr_node->regs.ip, KD_EXE_LOCK_MUTEX,
			       curr_node->entry_abi);
		return KD_EXE_NO_RUN;
	}
	if (kd_exec_context_busy()) {
		/* A scheduled mutex combiner owns this CPU's frame stack. The
		 * current waiter must use queue handoff without touching it.
		 * Identify the unexecuted request so a busy refusal cannot be
		 * mistaken for missing translation or a progressed JIT failure. */
		this_cpu_inc(kd_mutex_context_busy_count);
		KD_PR_DEBUG(
			"mutex JIT context busy: task=%d waiter=%d entry=%lx lock=%lx cpu=%u\n",
			current->pid, curr_node->task_struct_ptr->pid,
			curr_node->regs.ip, lock->origin_mutex_addr,
			raw_smp_processor_id());
		return KD_EXE_NO_RUN;
	}

	if (!clobber)
		retry_regs = curr_node->regs;
	if (clobber)
		frame = kd_exec_frame_push_borrowed(
			&curr_node->regs, curr_node->regs.ip, lock->origin_mutex_addr, 1,
			curr_node->gsbase, curr_node->task_struct_ptr);
	else
		frame = kd_exec_frame_push(
			&curr_node->regs, curr_node->regs.ip, lock->origin_mutex_addr, 1,
			curr_node->gsbase, curr_node->task_struct_ptr);
	if (!frame) {
		this_cpu_inc(kd_mutex_frame_failure_count);
		return KD_EXE_RUN_ERROR;
	}

	lock_addr[0] = lock->origin_mutex_addr;
	frame->mutex_backend = true;
	frame->entry_abi = curr_node->entry_abi;
	frame->packet_state = curr_node->packet_state;
	lock_kind[0] = KD_EXEC_LOCK_QUEUE_OWNER;
	lock_node[0] = lock;
	frame_ret = kd_exec_frame_set_lock_entries(
		frame, lock_addr, lock_kind, lock_node, NULL, 1);
	if (frame_ret) {
		this_cpu_inc(kd_mutex_frame_failure_count);
		KD_PR_ERR("mutex JIT frame lock entry invalid: %d\n",
			  frame_ret);
		frame_ret = kd_exec_frame_abort(frame);
		if (!frame_ret)
			frame_ret = kd_exec_frame_pop(frame, NULL);
		if (unlikely(frame_ret)) {
			this_cpu_inc(kd_mutex_frame_failure_count);
			KD_PR_ERR(
				"mutex JIT invalid-frame cleanup failed: %d\n",
				frame_ret);
			/* A live invalid frame poisons every later translation on this
			 * CPU, so native continuation is no longer safe. */
			BUG();
		}
		return KD_EXE_RUN_ERROR;
	}

	frame->outer_unlock_hook = &batch->outer;
	queue_end = kd_exe_queue_timing_start();
	regs = kd_exec_frame_regs(frame);
	ret_flag = kd_exe_on_call_hl_entry(exe, regs, frame->entry_ip,
					   frame->outer_lock_addr);
	regs = kd_exec_frame_regs(frame);
	/* Refused dispatches remain queued. Account a real body's pre-dispatch
	 * endpoint before the waiter can resume and recycle its slot. */
	if (frame->executed)
		kd_exe_queue_timing_end(true, &curr_node->queued_at_ns, queue_end);
	if (ret_flag == KD_EXE_RUN_NATIVE) {
		/* Include borrowing/publication before the waiter can run; the
		 * inner owner-wait timer starts too late to cover that prefix. */
		u64 handoff_start = kd_exe_native_timing_start();

		BUG_ON(kd_exec_native_begin(frame, true));
		BUG_ON(frame->regs_borrowed || frame->packet_state != KD_PACKET_FULL);
		curr_node->regs = *regs;
		curr_node->packet_state = KD_PACKET_FULL;
		WRITE_ONCE(curr_node->native_resume, true);
		smp_store_release(&curr_node->locked, 0);
		/* Neither this frame nor its combiner may touch curr_node again. */
		BUG_ON(kd_exec_native_wait(frame));
		kd_exe_native_handoff_timing_end(true, handoff_start);
		BUG_ON(kd_exec_frame_complete(frame));
		BUG_ON(kd_exec_frame_pop(frame, NULL));
		return KD_EXE_NATIVE_DONE;
	}
	if (ret_flag != KD_EXE_RUN_TO_UNLOCK && frame->executed) {
		KD_PR_ERR("mutex JIT non-continuable exit: entry=%lx ip=%lx ret=%d\n",
			  frame->entry_ip, regs->ip, ret_flag);
		BUG();
	}
	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		frame_ret = 0;
		if (!frame->outer_unlock_seen)
			frame_ret = kd_exec_frame_record_event(
				frame, KD_EXEC_EVENT_OUTER_UNLOCK,
				frame->packet_state == KD_PACKET_COMPLETE ? NULL : regs);
		if (!frame_ret)
			frame_ret = kd_exec_frame_complete(frame);
		if (unlikely(frame_ret)) {
			this_cpu_inc(kd_mutex_frame_failure_count);
			KD_PR_ERR(
				"mutex JIT committed frame transition failed: %d\n",
				frame_ret);
			/* The translated CS has already reached its outer unlock. A
			 * native retry would execute its side effects twice. */
			BUG();
		}
	}

	if (ret_flag != KD_EXE_RUN_TO_UNLOCK) {
		frame_ret = kd_mutex_jit_abort_cleanup(frame);
		if (unlikely(frame_ret)) {
			this_cpu_inc(kd_mutex_frame_failure_count);
			KD_PR_ERR("mutex JIT nested abort cleanup failed: %d\n",
				  frame_ret);
			BUG();
		}
		if (kd_exec_frame_state(frame) != KD_EXEC_FRAME_COMPLETE &&
		    kd_exec_frame_abort(frame))
			this_cpu_inc(kd_mutex_frame_failure_count);
		if (!clobber)
			*regs = retry_regs;
	}

	curr_node->packet_state = frame->packet_state;
	frame_ret = kd_exec_frame_pop(frame, &curr_node->regs);
	if (frame_ret) {
		this_cpu_inc(kd_mutex_frame_failure_count);
		KD_PR_ERR("mutex JIT frame pop failed: %d\n", frame_ret);
		if (ret_flag == KD_EXE_RUN_TO_UNLOCK)
			BUG();
		return KD_EXE_RUN_ERROR;
	}

	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		KD_PR_DEBUG("mutex JIT delegation ok\n");
		return 0;
	}

	this_cpu_inc(kd_mutex_jit_failure_count);
	KD_PR_DEBUG("mutex JIT delegation failed: %d\n", ret_flag);
	return ret_flag;
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Combiner loop: execute CS for each queued waiter via JIT sandbox
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static void
run_combiner(struct kd_mutex *lock, struct kd_mutex_node *curr_node)
{
	struct kd_mutex_node *next_node = NULL;
	struct kd_mutex_batch batch = {
		.outer.release = kd_mutex_release_outer,
	};
	int counter = 0;

	this_cpu_inc(kd_mutex_combiner_count);

	if (!curr_node || !curr_node->next) {
		/* Only one waiter — pass lock directly, no delegation needed */
		this_cpu_inc(kd_mutex_handoff_count);
		set_locked(lock);
		if (curr_node)
			smp_store_release(&curr_node->locked, 0);
		return;
	}

	while (curr_node) {
		counter++;
		next_node = curr_node->next;
		batch.next = next_node;
		batch.outer.released = false;
		kd_mutex_prefetch_successor(next_node);

		int exe_flag = execute_cs(lock, curr_node, &batch);

		if (exe_flag != 0 && exe_flag != KD_EXE_NATIVE_DONE) {
			/*
			 * Only execute_cs() returning 0 means the sandbox reached
			 * mutex_unlock. Any other status must fall back without marking
			 * the waiter completed.
			 * Hand the lock to this waiter so it can execute
			 * its own CS as the new combiner.
			 */
			this_cpu_inc(kd_mutex_handoff_count);
			next_node = curr_node;
			break;
		}

		if (exe_flag != KD_EXE_NATIVE_DONE) {
			this_cpu_inc(kd_mutex_jit_success_count);
			clear_locked_set_completed(curr_node);
		}

		if (batch.outer.released) {
			/* A's queue already runs independently. B and the frame are
			 * now finished; reacquire A for our own original request.
			 * Do not inspect or wake the old successor a second time. */
			kd_mutex_wait_and_lock(lock);
			return;
		}

		if (exe_flag == KD_EXE_NATIVE_DONE ||
		    !next_node || !next_node->next ||
		    counter >= kd_mutex_batch_size)
			break;

		curr_node = next_node;
	}

	/* Pass lock to the next waiter who will become the new combiner.
	 * next_node is guaranteed non-NULL: either it's the failed curr_node,
	 * or it was validated as non-NULL before the break above. */
	set_locked(lock);
	if (next_node)
		smp_store_release(&next_node->locked, 0);
}
#pragma GCC pop_options
