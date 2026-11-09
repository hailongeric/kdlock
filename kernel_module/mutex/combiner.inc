// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Delegated mutex bodies, detached outer batches and successor publication.
 * Private implementation included only by kd_mutex.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

#include "batch_diag.inc"

struct kd_mutex_batch {
	struct kd_mutex *lock; /* enclosing invocation keeps the object live */
	struct kd_exec_outer_unlock outer;
	struct kd_mutex_node *next;
	/* A queue tail can receive a delayed successor link until it is retired.
	 * This exact flag prevents a second access after native waiter wake/reuse. */
	struct kd_mutex_node *current_node;
	bool current_retired;
	bool current_handoff;
	bool current_rebound;
	/* Immutable slot identity; readiness/code are rechecked per request. */
	struct kd_exe_info *exe;
	unsigned int deferred_count;
	unsigned int scan_left;
	int numa_node;
	KD_MUTEX_DIAG_MEMBER
};

/* NUMA selection reorders only completely published members under the common
 * guard. Remote requests remain visible to cancellation/retirement. A local
 * waiter is a boundary: it is never bypassed to dispatch a foreign body. */
static struct kd_mutex_node *
kd_mutex_batch_select(struct kd_mutex_batch *batch, struct kd_mutex_node *node)
{
	struct kd_wait_queue queue = kd_mutex_wait_queue(batch->lock);
	struct kd_wait_node *first = kd_mutex_request_member(node);
	struct kd_wait_node *scan;
	unsigned long flags;

	if (batch->numa_node < 0 || node->numa_node == batch->numa_node)
		return node;
	flags = _raw_spin_lock_irqsave(queue.guard);
	BUG_ON(first->queue_head != queue.head);
	scan = kd_wait_next_locked(&queue, first);
	while (scan && batch->scan_left && !scan->request->admission &&
	       scan->request->may_delegate &&
	       scan->request->state == KD_WAIT_QUEUED) {
		struct kd_mutex_node *candidate = scan->request->context;

		batch->scan_left--;
		if (candidate->numa_node == batch->numa_node) {
			kd_wait_move_before_locked(&queue, scan, first);
			node = candidate;
			break;
		}
		batch->deferred_count++;
		KD_MUTEX_DIAG_DEFERRED(batch);
		scan = kd_wait_next_locked(&queue, scan);
	}
	_raw_spin_unlock_irqrestore(queue.guard, flags);
	KD_MUTEX_DIAG_SCAN_END(batch, node);
	return node;
}

/* There is no private deferred chain to splice. Pending members never left
 * the canonical queue, including at native handoff and early outer release. */
static struct kd_mutex_node *
kd_mutex_batch_rejoin(struct kd_mutex_batch *batch, struct kd_mutex_node *next)
{
	(void)batch;
	return next;
}

static struct kd_exe_info *
kd_mutex_batch_find_ready(struct kd_mutex_batch *batch, unsigned long ip)
{
	struct kd_exe_info *exe = batch->exe;

	if (!exe || READ_ONCE(exe->RIP) != ip ||
	    READ_ONCE(exe->lock_kind) != KD_EXE_LOCK_MUTEX) {
		exe = kd_get_exe(0, ip);
		batch->exe = exe;
	}
	return kd_exe_entry_is_ready(exe, 0, ip) ? exe : NULL;
}

/* The successor is still queued and cannot reuse its node or caller stack
 * before this batch publishes a wake. Fetch its read-mostly header, the saved
 * packet line and the stack lines around the virtual return slot. The aligned
 * IP/SP/BP and virtual GPR slots share one line which the JIT will write; avoid
 * fetching it read-only and then upgrading ownership in the current body.
 * Do this before the current body; never chase a successor after handoff. */
static void kd_mutex_prefetch_successor(struct kd_mutex_node *next)
{
	unsigned long sp;

	if (!next)
		return;
	prefetch(next);
	prefetchw(&next->entry_abi);
	prefetchw(&next->regs);
	sp = READ_ONCE(next->regs.sp);
	if (sp) {
		prefetchw((void *)sp);
		prefetchw((void *)(sp - sizeof(unsigned long)));
	}
}

/* An unlinked last node is eligible only under the explicit minimal ABI.
 * Legacy/FULL last waiters retain the established physical handoff boundary. */
static bool kd_mutex_batch_can_execute(struct kd_mutex_node *node)
{
	return node && (kd_mutex_queue_successor(node->lock, node) ||
		(node->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 &&
		 node->packet_state == KD_PACKET_MINIMAL));
}

/* Commit only when the retained executor actually owns exclusion. Image
 * lookup and frame preparation happen first; neither is acquisition. */
static bool kd_mutex_proxy_grant(struct kd_wait_request *request, void *argument)
{
	struct kd_mutex *lock = argument;

	return request->may_delegate && kd_mutex_delegation_owned(lock, current);
}

static void kd_mutex_proxy_begin(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	struct kd_mutex_wait_record *record = kd_mutex_wait_record(node);
	struct kd_wait_queue queue = kd_mutex_wait_queue(lock);
	unsigned long flags = _raw_spin_lock_irqsave(queue.guard);

	BUG_ON(!kd_wait_select_locked(&queue, &record->request,
				     &record->selection, current));
	BUG_ON(kd_wait_decide_locked(&queue, &record->request,
				    record->request.generation,
				    kd_mutex_proxy_grant, lock) != KD_WAIT_GRANTED);
	kd_wait_set_state_locked(&record->request, KD_WAIT_EXECUTING);
	if (!lock->wait_head)
		atomic_long_andnot(7UL, &lock->owner);
	_raw_spin_unlock_irqrestore(queue.guard, flags);
}

/* Before public outer release, transfer lifecycle custody to retained slot
 * storage. A nested suffix may outlive the outer lock object, so completion
 * must never reacquire that object's queue guard. The batch keeps the exact
 * slot/frame alive; this transfer does not claim body completion. */
static void kd_mutex_batch_detach_current(struct kd_mutex *lock,
					struct kd_mutex_batch *batch)
{
	struct kd_mutex_wait_record *record;
	unsigned long flags;

	if (batch->current_rebound)
		return;
	record = kd_mutex_wait_record(batch->current_node);
	flags = _raw_spin_lock_irqsave(&lock->wait_lock);
	BUG_ON(record->member.queue_head ||
	       record->request.guard != &lock->wait_lock);
	kd_wait_selection_drop_locked(&record->request, &record->selection);
	kd_wait_rebind_locked(&record->request, &record->lifecycle_guard);
	_raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
	batch->next = kd_mutex_queue_first(lock);
	batch->current_rebound = true;
}

/* Membership ended at the committed grant. Completion or explicit retained
 * legacy handoff ends this request's execution authority before result wake. */
static void kd_mutex_batch_retire_current(struct kd_mutex *lock,
					struct kd_mutex_batch *batch)
{
	struct kd_mutex_wait_record *record;
	unsigned long flags;

	BUG_ON(batch->lock != lock);
	if (batch->current_retired)
		return;
	kd_mutex_batch_detach_current(lock, batch);
	record = kd_mutex_wait_record(batch->current_node);
	flags = _raw_spin_lock_irqsave(&record->lifecycle_guard);
	if (batch->current_handoff) {
		kd_wait_handoff_locked(&record->request);
	} else {
		kd_wait_set_state_locked(&record->request, KD_WAIT_RELEASED);
		kd_wait_set_state_locked(&record->request, KD_WAIT_RETURN_ACK);
	}
	_raw_spin_unlock_irqrestore(&record->lifecycle_guard, flags);
	batch->current_retired = true;
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

	if (!frame->mutex_backend || !lock ||
	    frame->jit_lock_kind[frame->outer_lock_index] !=
		    KD_EXEC_LOCK_QUEUE_OWNER ||
	    frame->outer_lock_addr != (unsigned long)lock ||
	    batch->lock != lock ||
	    kd_mutex_gate_read(lock) != KD_MUTEX_GATE_COMBINER)
		return -EINVAL;
	/* A terminal request may have no successor. Remove its published tail
	 * before opening A; future old_tail=0 arrivals poll A's gate themselves. */
	kd_mutex_batch_detach_current(lock, batch);
	batch->next = kd_mutex_batch_rejoin(batch, batch->next);
	if (batch->next && !batch->next->task_struct_ptr)
		return -EINVAL;
	for (i = frame->outer_lock_index; i < frame->jit_lock_depth; i++)
		remaining += !frame->jit_lock_released[i];
	/* A native successor can run as soon as L opens. Log release intent
	 * before that point, as on the spin path; the observer proves progress. */
	pr_info("kd_mutex outer release: task=%d owner=%d owner_task=%lx outer=%lx next_task=%d remaining=%u\n",
		frame->logical_task->pid, current->pid, (unsigned long)current,
		frame->outer_lock_addr,
		batch->next ? batch->next->task_struct_ptr->pid : 0, remaining);
	ret = _kd_mutex_unlock_checked(lock);
	if (ret)
		return ret;
	/* A common head observes FREE itself. It may already have completed and
	 * reused its slot, so the releasing executor cannot touch saved nodes. */
	return 0;
}

#include "origin_instruction.inc"

/* --------------------------------------------------------------------------
 * JIT-sandbox execution of a waiter's critical section
 *
 * The captured legacy mutex_lock saved ALL callee-saved registers before capturing
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
kd_mutex_execute_cs(struct kd_mutex *lock, struct kd_mutex_node *curr_node,
	   struct kd_mutex_batch *batch)
{
	void *incoming_rsp_ptr = (void *)curr_node->regs.sp;
	struct kd_exec_frame *frame;
	struct kd_exe_info *exe;
	struct kd_jit_batch_call call;
	struct kd_regs retry_regs, *regs;
	bool clobber = curr_node->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	unsigned long lock_addr[1];
	enum kd_exec_lock_kind lock_kind[1];
	void *lock_node[1];
	int ret_flag;
	int frame_ret;
	u64 queue_end;

	BUG_ON(!kd_mutex_delegation_owned(lock, current));
	BUG_ON(!kd_origin_mutex_owned(lock,
				      current));
	if (!incoming_rsp_ptr)
		return KD_EXE_RUN_ERROR;

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

	exe = kd_mutex_batch_find_ready(batch, curr_node->regs.ip);
	if (!exe) {
		this_cpu_inc(kd_mutex_jit_not_ready_count);
		/* A missing/cold image is an unstarted request, not a progressed
		 * frame failure. Keep its identity distinct from context refusal. */
		KD_PR_DEBUG("mutex JIT not ready: task=%d waiter=%d entry=%lx lock=%lx cpu=%u\n",
			    current->pid, curr_node->task_struct_ptr->pid,
			    curr_node->regs.ip, (unsigned long)lock,
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
			curr_node->regs.ip, (unsigned long)lock,
			raw_smp_processor_id());
		return KD_EXE_NO_RUN;
	}

	if (!clobber)
		retry_regs = curr_node->regs;
	/* The enclosing batch retains source residency through the last ACK/pop.
	 * Legacy/nested roots keep their private frame lease and generic setup. */
	frame = clobber && curr_node->packet_state == KD_PACKET_MINIMAL ?
		kd_exec_frame_push_mutex_batch(&curr_node->regs, curr_node->regs.ip,
			curr_node->gsbase, curr_node->task_struct_ptr, lock,
			&batch->outer) : NULL;
	if (frame)
		goto prepared;
	if (clobber)
		frame = kd_exec_frame_push_borrowed(
			&curr_node->regs, curr_node->regs.ip, (unsigned long)lock, 1,
			curr_node->gsbase, curr_node->task_struct_ptr);
	else
		frame = kd_exec_frame_push(
			&curr_node->regs, curr_node->regs.ip, (unsigned long)lock, 1,
			curr_node->gsbase, curr_node->task_struct_ptr);
	if (!frame) {
		this_cpu_inc(kd_mutex_frame_failure_count);
		return KD_EXE_RUN_ERROR;
	}

	lock_addr[0] = (unsigned long)lock;
	frame->mutex_backend = true;
	frame->mutex_mixed.transfer_requested = false;
	frame->mutex_mixed.transferred = false;
	frame->mutex_mixed.picked_up = false;
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
prepared:
	kd_mutex_proxy_begin(lock, curr_node);
	queue_end = kd_exe_queue_timing_start();
	regs = kd_exec_frame_regs(frame);
	if (frame->batch_lease && kd_exe_mutex_batch_prepare(exe, frame, &call)) {
		frame->executed = true;
		kd_jit_clobber_call_v1(&call);
		if (kd_exe_mutex_batch_completed(&call, frame)) {
			kd_exe_queue_timing_end(true, &curr_node->queued_at_ns, queue_end);
			BUG_ON(kd_exec_frame_retire_mutex_batch(frame, lock));
			curr_node->packet_state = KD_PACKET_COMPLETE;
			return 0;
		}
		/* FULL, or a checked pre-entry refusal: the pending return is
		 * consumed once by the existing dispatcher, never re-entered. */
		ret_flag = kd_exe_mutex_batch_resume(exe, &call);
	} else {
		ret_flag = kd_exe_on_call_hl_entry(exe, regs, frame->entry_ip,
						 frame->outer_lock_addr);
	}
	regs = kd_exec_frame_regs(frame);
	/* Account a real body's pre-dispatch endpoint before the result wake.
	 * A post-grant refusal retains the acquired continuation below. */
	if (frame->executed)
		kd_exe_queue_timing_end(true, &curr_node->queued_at_ns, queue_end);
	if (ret_flag != KD_EXE_RUN_TO_UNLOCK && !frame->executed) {
		/* The request already won physical acquisition. A later pre-body
		 * dispatch refusal cannot cancel it or publish it as an unacquired
		 * waiter. Deliver that exact acquired continuation through the
		 * retained legacy owner service without replaying a body. */
		BUG_ON(kd_exec_frame_prepare_mutex_complex(frame));
		if (frame->regs_borrowed && frame->packet_state == KD_PACKET_MINIMAL) {
			unsigned long entry_ip = regs->ip, entry_sp = regs->sp;
			unsigned long entry_bp = regs->bp;

			BUG_ON(entry_ip != curr_node->saved_ret_addr ||
			       entry_sp != curr_node->regs.sp);
			frame->regs_borrowed = false;
			frame->regs_ref = NULL;
			frame->regs.ip = entry_ip;
			frame->regs.sp = entry_sp;
			frame->regs.bp = entry_bp;
			frame->continuation_sp = 0;
			regs = &frame->regs;
		}
		ret_flag = KD_EXE_RUN_NATIVE;
	}
	if (ret_flag == KD_EXE_RUN_NATIVE) {
		/* Include borrowing/publication before the waiter can run; the
		 * inner owner-wait timer starts too late to cover that prefix. */
		u64 handoff_start = kd_exe_native_timing_start();
		bool transfer = frame->mutex_mixed.transfer_requested &&
			kd_exec_mutex_transfer_allowed(frame);

		BUG_ON(kd_exec_native_begin(frame, true));
		BUG_ON(frame->regs_borrowed ||
		       (frame->packet_state != KD_PACKET_FULL &&
			frame->packet_state != KD_PACKET_MINIMAL));
		if (frame->packet_state == KD_PACKET_FULL)
			curr_node->regs = *regs;
		curr_node->packet_state = frame->packet_state;
		/* Native resume releases/reuses the node before owner ACK returns.
		 * Finish every possible predecessor link before that publication. */
		batch->current_handoff = true;
		kd_mutex_batch_retire_current(lock, batch);
		curr_node->native_spin_pins = kd_exec_mutex_spin_count(frame);
		curr_node->native_transfer = NULL;
		if (transfer) {
			/* Queue and source ownership survive the real owner exchange.
			 * No unlocked state is exposed between the executed prefix and
			 * the original task's suffix. Retain this frame until its ACK. */
			BUG_ON(kd_mutex_transfer_owner(lock, frame->logical_task));
			frame->mutex_mixed.transferred = true;
			curr_node->native_transfer = frame;
			pr_info("kd_mutex transfer: outer=%lx executor=%d owner=%d target=%lx pending=1\n",
				frame->outer_lock_addr, current->pid,
				frame->logical_task->pid, frame->control_call.target);
			/* The next head may wait for A, but cannot acquire its occupied
			 * gate. The old combiner never touches this chain after wake. */
			/* Actual release will notify the next canonical head. */
			batch->next = NULL;
		}
		WRITE_ONCE(curr_node->native_resume, KD_MUTEX_RESUME_NATIVE);
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
kd_mutex_run_combiner(struct kd_mutex *lock, struct kd_mutex_node *curr_node)
{
	struct kd_mutex_node *next_node = NULL;
	struct kd_mutex_batch batch = {
		.lock = lock,
		.outer.release = kd_mutex_release_outer,
		.scan_left = 64,
#ifdef NUMA_AWARE
		.numa_node = numa_node_id(),
#else
		.numa_node = -1,
#endif
	};
	int counter = 0;

	this_cpu_inc(kd_mutex_combiner_count);

	if (KD_MUTEX_DIAG_CONDITION(&batch, !kd_mutex_batch_can_execute(curr_node),
				    KD_MUTEX_DIAG_INITIAL_UNEXECUTABLE) ||
	    KD_MUTEX_DIAG_CONDITION(&batch, !kd_source_frame_get(),
				    KD_MUTEX_DIAG_SOURCE_REFUSAL)) {
		/* Keep unsupported last packets and source refusal on native handoff. */
		this_cpu_inc(kd_mutex_handoff_count);
		kd_mutex_set_locked(lock);
		kd_mutex_queue_handoff(lock);
		KD_MUTEX_DIAG_FINISH(&batch);
		return;
	}

	while (curr_node) {
		curr_node = kd_mutex_batch_select(&batch, curr_node);
		next_node = curr_node;
		/* Keep a real terminal tail while private deferred nodes exist.
		 * A substantial remote cohort receives the next physical owner;
		 * that owner can serve the cohort on its own socket. */
		if (batch.deferred_count &&
		    (counter >= KDLOCK_MUTEX_NUMA_BOUNDARY ||
		     (curr_node->numa_node != batch.numa_node &&
		      !kd_mutex_queue_successor(lock, curr_node)))) {
			if (batch.deferred_count >= 8) {
				KD_MUTEX_DIAG_STOP(&batch,
					counter >= KDLOCK_MUTEX_NUMA_BOUNDARY ? KD_MUTEX_DIAG_NUMA_BOUNDARY :
					KD_MUTEX_DIAG_NUMA_TAIL);
				break;
			}
			/* Small prefixes cannot amortize owner transfer. Rejoin before
			 * execution, then service the rest in FIFO order. The total cap,
			 * refusal, native and early-outer boundaries remain unchanged. */
			curr_node = kd_mutex_batch_rejoin(&batch, curr_node);
			batch.numa_node = -1;
			KD_MUTEX_DIAG_SMALL_FIFO(&batch);
		}
		counter++;
		next_node = kd_mutex_queue_successor(lock, curr_node);
		batch.next = next_node;
		batch.current_node = curr_node;
		batch.current_retired = false;
		batch.current_handoff = false;
		batch.current_rebound = false;
		batch.outer.released = false;
		kd_mutex_prefetch_successor(next_node);
		KD_MUTEX_DIAG_REQUEST(&batch, curr_node);

		int exe_flag = kd_mutex_execute_cs(lock, curr_node, &batch);
		KD_MUTEX_DIAG_RESULT(&batch, exe_flag);

		if (exe_flag != 0 && exe_flag != KD_EXE_NATIVE_DONE) {
			/*
			 * Only kd_mutex_execute_cs() returning 0 means the sandbox reached
			 * mutex_unlock. Any other status must fall back without marking
			 * the waiter completed.
			 * Hand the lock to this waiter so it can execute
			 * its own CS as the new combiner.
			 */
			this_cpu_inc(kd_mutex_handoff_count);
			next_node = curr_node;
			KD_MUTEX_DIAG_STOP(&batch, KD_MUTEX_DIAG_EXECUTION_REFUSAL);
			break;
		}

		if (exe_flag != KD_EXE_NATIVE_DONE) {
			kd_mutex_batch_retire_current(lock, &batch);
			this_cpu_inc(kd_mutex_jit_success_count);
			kd_mutex_clear_locked_set_completed(curr_node);
		}

		if (batch.outer.released) {
			/* A's queue already runs independently. B and the frame are
			 * now finished; reacquire A for our own original request.
			 * Do not inspect or wake the old successor a second time. */
			kd_mutex_wait_and_lock(lock);
			KD_MUTEX_DIAG_STOP(&batch, KD_MUTEX_DIAG_EARLY_OUTER_RELEASE);
			KD_MUTEX_DIAG_FINISH(&batch);
			kd_source_frame_put();
			return;
		}

		/* A terminal tail may have gained a successor while its body ran.
		 * After publication, never read the completed/reused current node. */
		next_node = batch.next;
		if (KD_MUTEX_DIAG_CONDITION(&batch, exe_flag == KD_EXE_NATIVE_DONE,
					    KD_MUTEX_DIAG_NATIVE_DONE) ||
		    KD_MUTEX_DIAG_CONDITION(&batch, counter >= kd_mutex_batch_size,
					    KD_MUTEX_DIAG_TOTAL_CAP) ||
		    KD_MUTEX_DIAG_CONDITION(&batch, !kd_mutex_batch_can_execute(next_node),
				next_node ? KD_MUTEX_DIAG_UNSUPPORTED_TAIL : KD_MUTEX_DIAG_EMPTY_TAIL))
			break;

		curr_node = next_node;
	}

	/* The failed current request or a retained successor becomes queue head.
	 * An empty retired tail needs no wake; future heads already poll the gate.
	 * Keep the real mutex and gate for this physical owner's original body. */
	next_node = kd_mutex_batch_rejoin(&batch, next_node);
	kd_mutex_set_locked(lock);
	kd_mutex_queue_handoff(lock);
	KD_MUTEX_DIAG_FINISH(&batch);
	/* Includes synchronous native continuation and final physical owner ACK. */
	kd_source_frame_put();
}
#pragma GCC pop_options
