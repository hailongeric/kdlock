// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Delegated body execution, outer release and bounded combiner batches.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

struct kd_spin_batch {
	struct kd_exec_outer_unlock outer;
	struct kd_spin_node *next;
	struct kd_spin_request *request;
};

/* A's executor keeps its ticket pin and local frame stack, not ownership of
 * A. No published successor can be inspected again by this detached batch. */
static int kd_spin_release_outer(struct kd_exec_frame *frame,
				 struct kd_exec_outer_unlock *hook)
{
	struct kd_spin_batch *batch =
		container_of(hook, struct kd_spin_batch, outer);
	struct qspinlock *lock = (struct qspinlock *)frame->outer_lock_addr;
	struct qspinlock *word = batch->request->word;
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	struct kd_spin_node *next = batch->next;
	unsigned int i, remaining = 0;
	int ret;

	if (frame->mutex_backend || !next || !next->task_struct_ptr ||
	    frame->jit_lock_kind[frame->outer_lock_index] !=
		    KD_EXEC_LOCK_QUEUE_OWNER ||
	    READ_ONCE(word->locked) != _Q_LOCKED_COMBINER_VAL)
		return -EINVAL;
#ifdef NUMA_AWARE
	if (ptr->local_queue_head) {
		if (!ptr->local_queue_tail)
			return -EINVAL;
		ptr->local_queue_tail->next = next;
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_splice(lock, next, true);
#endif
		next = ptr->local_queue_head;
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
		frame->saved_combiner.local_queue_head = NULL;
		frame->saved_combiner.local_queue_tail = NULL;
	}
#endif
	for (i = frame->outer_lock_index; i < frame->jit_lock_depth; i++)
		remaining += !frame->jit_lock_released[i];
	/* Log before L opens: a native successor may run immediately afterward. */
	pr_info("kd_spin outer release: task=%d owner=%d owner_task=%lx cpu=%u outer=%lx next_task=%d next_cpu=%d remaining=%u remote=%u\n",
		frame->logical_task->pid, current->pid, (unsigned long)current,
		raw_smp_processor_id(), frame->outer_lock_addr,
		next->task_struct_ptr->pid, next->cpuid, remaining,
		kd_exec_frame_remote_pending(frame));
	ret = kd_spin_entry_release_origin(&batch->request->ref);
	if (ret)
		return ret;
	kd_spin_debug_ooo_unlock(lock, kd_spin_lock_stack_depth(ptr));
	smp_store_release(&word->locked, 0);
	smp_store_release(&next->locked, 0);
	return 0;
}

/* Reclaim the original waiter's outer lock on return from a native/remote
 * delegation run. The holder must reacquire origin scheduling only, never
 * open a new queue fast path through this packet.
 */
static void kd_spin_reclaim_outer(struct kd_spin_request *request)
{
	/* Like node-capacity fallback, wait for all of S, including pending/tail.
	 * Reentering the stack-switch slowpath would overwrite our live C stack. */
	while (!kd_spin_trylock(request->word))
		cpu_relax();
	BUG_ON(kd_spin_entry_reclaim(&request->ref));
}

#pragma GCC push_options
#pragma GCC optimize("O3")
/*
 * Execute one waiter critical section in JIT mode.
 * For native waiters run until outer unlock or delegated native path and publish
 * the corresponding transition so combiner state and successor continuation stay
 * deterministic.
 */
__attribute__((noipa)) noinline notrace static int
execute_cs(struct qspinlock *lock, struct kd_spin_node *curr_node,
	   struct kd_spin_batch *batch)
{
	struct qspinlock *word = batch->request->word;
	struct kd_exec_frame *frame;
	int ret_flag;
	struct kd_exe_info *exe;
	unsigned int frame_lock_depth;
	struct kd_spin_jit_context *jit_context = curr_node->jit_context;
	unsigned long entry_ip;
	u64 queue_end;
	bool abort_cleaned = false;
#ifdef KDLOCK_SELFTEST
	int frame_event;
#endif

	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	ptr->curr_cs_cpu = curr_node->cpuid;

	/* A plain waiter cannot describe locks/context pinned before this request.
	 * Keep its private-queue position, but let it execute on its own stack. */
	if (!curr_node->jit_waiter && curr_node->pinned_context) {
		pr_warn_ratelimited(
			"[KD_JIT][WARN] reason=PINNED_NATIVE_WAITER task=%d cpu=%d lock=%px\n",
			curr_node->task_struct_ptr->pid, curr_node->cpuid,
			lock);
		return KD_EXE_NO_RUN;
	}
	if (kd_spin_jit_is_disabled(lock)) {
		kd_spin_diag_record(lock, KD_SPIN_DIAG_NATIVE_FALLBACK,
				    kd_spin_lock_stack_depth(ptr));
		return KD_EXE_NO_RUN;
	}

#ifdef DEBUG_KD_SPIN
	BUG_ON(curr_node->cpuid == smp_processor_id());
#endif

	/* Physical packets are fully prepared before the waiter publishes next. */
	if (!curr_node->jit_waiter && !curr_node->native_regs_decoded)
		return KD_EXE_RUN_ERROR;
	if (curr_node->jit_waiter && (!jit_context || !jit_context->requester))
		return KD_EXE_RUN_ERROR;
	/* B is a continuation in A's admitted code. An independent B translation
	 * starts at lexical depth one and can stop at an inherited A unlock. */
	entry_ip = curr_node->jit_waiter ? jit_context->requester->entry_ip :
					   curr_node->regs->ip;
	exe = kd_exe_find_ready(0, entry_ip);
	if (!exe) {
		kd_spin_debug_jit_not_ready(lock,
					    kd_spin_lock_stack_depth(ptr));
		kd_exe_add(0, entry_ip, KD_EXE_LOCK_SPIN);
		return KD_EXE_NO_RUN;
	}
	print_debug(
		"r15 %lx r14 %lx r13 %lx r12 %lx bx %lx bp %lx ip %lx sp %lx\n",
		curr_node->regs->r15, curr_node->regs->r14, curr_node->regs->r13,
		curr_node->regs->r12, curr_node->regs->bx, curr_node->regs->bp,
		curr_node->regs->ip, curr_node->regs->sp);
	frame_lock_depth = curr_node->jit_waiter ?
				   jit_context->lock_depth :
				   kd_spin_lock_stack_depth(ptr);
	frame = &curr_node->execution->frame;
	if (kd_exec_frame_bind(frame, frame_lock_depth, true)) {
		KD_PR_ERR("spin JIT frame stack overflow lock=%px\n", lock);
		return KD_EXE_RUN_ERROR;
	}
	curr_node->exec_frame = frame;
	frame->spin_origin = curr_node->spin_origin;
	if ((curr_node->jit_waiter &&
	     kd_exec_frame_set_lock_entries(
		     frame, jit_context->lock_addr, jit_context->lock_kind,
		     jit_context->lock_node, jit_context->lock_released,
		     jit_context->lock_depth)) ||
	    (!curr_node->jit_waiter &&
	     kd_exec_frame_set_lock_stack(frame,
					  (const unsigned long *)ptr->lock_addr,
					  kd_spin_lock_stack_depth(ptr)))) {
		KD_PR_ERR("spin JIT frame lock stack invalid lock=%px\n", lock);
		kd_exec_frame_abort(frame);
		curr_node->exec_frame = NULL;
		if (kd_exec_frame_pop(frame, NULL))
			KD_PR_ERR("spin JIT frame abort pop failed lock=%px\n",
				  lock);
		return KD_EXE_RUN_ERROR;
	}
	/* The generic ledger initializes only its live prefix. Keep one entry
	 * for a simple root so promotion to nested/native needs no reconstruction;
	 * delay the large combiner snapshot until the first non-final exit. */
	frame->spin_simple = !curr_node->jit_waiter && !frame->parent &&
			     frame_lock_depth == 1;
	if (!frame->spin_simple)
		kd_spin_capture_combiner_state(&frame->saved_combiner, ptr);
	frame->outer_unlock_hook = &batch->outer;
	if (curr_node->jit_waiter) {
		frame->resume_target = jit_context->requester;
		BUG_ON(!frame->resume_target ||
		       frame->resume_target->logical_task !=
			       frame->logical_task ||
		       smp_load_acquire(&frame->resume_target->remote_result) !=
			       KD_EXEC_REMOTE_WAITING);
		pr_info("kd_remote start: task=%d cpu=%u entry=%lx ip=%lx outer=%lx parent_outer=%lx owner_task=%lx\n",
			frame->logical_pid, raw_smp_processor_id(),
			frame->entry_ip, kd_exec_frame_regs(frame)->ip, frame->outer_lock_addr,
			frame->resume_target->outer_lock_addr,
			(unsigned long)current);
	}
#ifdef KDLOCK_SELFTEST
	frame_event = kd_spin_selftest_frame_begin(frame);
#endif
	queue_end = kd_exe_queue_timing_start();
#ifdef KDLOCK_SELFTEST
	/* Exercise only an unexecuted child; never interrupt a live JIT body. */
	if (!kd_spin_selftest_refuse(frame, curr_node, &ret_flag))
#endif
		ret_flag = kd_exe_on_call_hl_entry(
			exe, kd_exec_frame_regs(frame), frame->entry_ip,
			frame->outer_lock_addr);
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_frame_end(frame_event, frame, ret_flag);
	kd_spin_selftest_refusal_end(frame, ret_flag);
#endif
	/* A pre-body refusal is still waiting. Once a body ran, use its saved
	 * dispatch boundary and consume metadata before native/completion wake. */
	if (frame->executed)
		kd_exe_queue_timing_end(false, &curr_node->queued_at_ns, queue_end);
	if (ret_flag == KD_EXE_RUN_TO_UNLOCK && frame->spin_simple) {
		BUG_ON(kd_exec_frame_complete_single_spin(frame));
		goto finish_frame;
	}
	if (ret_flag == KD_EXE_RUN_NATIVE) {
		/* Remote publication can release an ancestor before this node is
		 * woken. Start before both publications, not only local locked=0. */
		u64 handoff_start = kd_exe_native_timing_start();
		struct kd_spin_exec_request *execution = curr_node->execution;

		BUG_ON(kd_exec_native_begin(frame, false));
		/* Publish the extra owner user before either native wake. The queue
		 * slot and original task can disappear before this owner unbinds. */
		atomic_inc(&execution->users);
		BUG_ON(kd_exec_remote_native(frame));
		curr_node->exec_frame = NULL;
		WRITE_ONCE(curr_node->native_resume, true);
		smp_store_release(&curr_node->locked, 0);
		/* The waiter may reuse its queue slot after this publication. */
		BUG_ON(kd_exec_native_wait(frame));
		kd_exe_native_handoff_timing_end(false, handoff_start);
		BUG_ON(kd_spin_jit_nested_cleanup(frame));
		BUG_ON(!kd_spin_combiner_state_matches(&frame->saved_combiner,
						       ptr));
		BUG_ON(kd_exec_frame_complete(frame));
		BUG_ON(kd_exec_frame_pop(frame, NULL));
		kd_spin_request_put(execution);
		return KD_EXE_NATIVE_DONE;
	}
	if (ret_flag != KD_EXE_RUN_TO_UNLOCK && frame->executed) {
		KD_PR_ERR(
			"spin JIT non-continuable exit: entry=%lx ip=%lx ret=%d\n",
			frame->entry_ip, kd_exec_frame_regs(frame)->ip, ret_flag);
		BUG();
	}
	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		if (!frame->outer_unlock_seen &&
		    kd_exec_frame_record_event(
			    frame, KD_EXEC_EVENT_OUTER_UNLOCK, kd_exec_frame_regs(frame))) {
			KD_PR_ERR(
				"spin JIT outer unlock event invalid lock=%px\n",
				lock);
			ret_flag = KD_EXE_RUN_ERROR;
		} else if (kd_spin_jit_nested_cleanup(frame)) {
			KD_PR_ERR("spin JIT nested cleanup invalid lock=%px\n",
				  lock);
			ret_flag = KD_EXE_RUN_ERROR;
		}
	}
	if (ret_flag != KD_EXE_RUN_TO_UNLOCK) {
		BUG_ON(frame->executed);
		if (kd_spin_jit_abort_cleanup(frame)) {
			KD_PR_ERR(
				"spin JIT abort cleanup failed lock=%px depth=%u\n",
				lock, frame->depth);
			kd_spin_diag_invariant_failure();
		}
		abort_cleaned = true;
	}
	if (!frame->spin_simple &&
	    !kd_spin_combiner_state_matches(&frame->saved_combiner, ptr)) {
		KD_PR_ERR(
			"nested combiner state restore mismatch lock=%px depth=%u\n",
			lock, frame->depth);
		kd_spin_diag_invariant_failure();
		ret_flag = KD_EXE_RUN_ERROR;
	}
	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		if (kd_exec_frame_complete(frame)) {
			KD_PR_ERR(
				"spin JIT frame completion invalid lock=%px\n",
				lock);
			ret_flag = KD_EXE_RUN_ERROR;
		}
	}
	if (ret_flag != KD_EXE_RUN_TO_UNLOCK) {
		BUG_ON(frame->executed);
		if (!abort_cleaned && kd_spin_jit_abort_cleanup(frame)) {
			KD_PR_ERR(
				"spin JIT late abort cleanup failed lock=%px depth=%u\n",
				lock, frame->depth);
			kd_spin_diag_invariant_failure();
		}
		if (kd_exec_frame_abort(frame))
			KD_PR_ERR(
				"spin JIT frame error transition failed lock=%px\n",
				lock);
	}
finish_frame:
	/* Only a native waiter needs the saved-entry return trampoline. A
	 * virtual waiter acquires B and continues its existing parent frame. */
	curr_node->jit_retry = !curr_node->jit_waiter &&
			       ret_flag != KD_EXE_RUN_TO_UNLOCK;
	if (curr_node->jit_retry)
		KD_PR_INFO(
			"spin JIT retry regs: node=%px cpu=%d ip=%lx failed_ip=%lx\n",
			curr_node, curr_node->cpuid, curr_node->regs->ip,
			ret_flag == KD_EXE_RUN_TO_UNLOCK ?
				0UL :
				frame->continuation_ip);
	curr_node->exec_frame = NULL;
	if (!frame->spin_simple) {
		if (ret_flag == KD_EXE_RUN_TO_UNLOCK)
			BUG_ON(kd_exec_remote_complete(frame));
		else
			kd_exec_remote_cancel(frame);
	}
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_refusal_cancel(frame);
#endif
	if (kd_exec_frame_pop(frame, NULL)) {
		KD_PR_ERR("spin JIT frame pop mismatch lock=%px\n", lock);
		BUG();
	}

	if (ret_flag == KD_EXE_RUN_TO_UNLOCK) {
		kd_spin_debug_jit_success(lock, kd_spin_lock_stack_depth(ptr));
		KD_PR_DEBUG("delegation ok lock=%px depth=%u\n", lock,
			    kd_spin_lock_stack_depth(ptr));
	} else {
		KD_PR_DEBUG("error return exe run error\n");
		if (ret_flag == KD_EXE_RUN_ERROR)
			kd_spin_jit_disable(lock);
		return ret_flag;
	}



	if (!batch->outer.released && word->locked == _Q_UNLOCKED_OOO_VAL) {
		print_debug("Combiner got control back OOO unlock\n");

#ifdef KD_SPIN_STATS
		this_cpu_inc(ooo_combiner_count);
#endif

		/* JIT waiters carry their continuation in pt_regs.  The native
		 * TCLock path copies a real RSP here, but the combiner's base node
		 * deliberately has rsp == NULL while run_combiner() is active. */
		ptr->prev_cs_cpu = -1;
		ptr->curr_cs_cpu = -1;
		word->locked = _Q_LOCKED_COMBINER_VAL;
	}
	return 0;
}
#pragma GCC pop_options

#pragma GCC push_options
#pragma GCC optimize("O3")
/*
 * Combiner loop over the currently-formed queue segment.
 * Stops at batch boundary, native handoff, OOO release, or JIT failure and
 * leaves the lock in a state expected by the successor waiter.
 */
__attribute__((noipa)) noinline notrace static void
run_combiner(struct qspinlock *lock, struct kd_spin_node *curr_node,
	     struct kd_spin_request *request)
{
#ifdef DEBUG_KD_SPIN
	BUG_ON(curr_node == NULL);
#endif
	struct kd_spin_node *next_node = curr_node->next;
	struct kd_spin_batch batch = {
		.outer.release = kd_spin_release_outer,
		.request = request,
	};
	int counter = 0;

	if (next_node == NULL || check_irq_node(curr_node) ||
	    check_irq_node(next_node) || !kd_source_frame_get()) {
		set_locked(request->word);
		/*
		 * Make this node spin on the locked variable and then it will
		 * become the combiner.
		 */
		smp_store_release(&curr_node->locked, false);
		smp_mb();
		return;
	}

	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	kd_spin_debug_combiner(lock, kd_spin_lock_stack_depth(ptr));

	while (curr_node) {
#ifdef NUMA_AWARE
		struct kd_spin_node *saved_tail = ptr->local_queue_tail;
#endif
		counter++;

		next_node = get_next_node(curr_node);
		batch.next = next_node;
		batch.outer.released = false;

		int exe_flag = execute_cs(lock, curr_node, &batch);

#ifdef NUMA_AWARE
		if (exe_flag == KD_EXE_NO_RUN || exe_flag == KD_EXE_RUN_ERROR) {
#ifdef KDLOCK_SELFTEST
			struct kd_spin_node *discarded_tail =
				ptr->local_queue_tail;
#endif
			/* The rejected waiter's next still owns this scan's followers.
			 * Discard only speculative deferrals; the final splice attaches
			 * any previously committed prefix to the rejected waiter. */
			if (!saved_tail)
				ptr->local_queue_head = NULL;
			ptr->local_queue_tail = saved_tail;
#ifdef KDLOCK_SELFTEST
			if (discarded_tail != saved_tail)
				kd_spin_selftest_restore(lock, curr_node,
							 discarded_tail,
							 exe_flag);
#endif
		}
#endif
		if (exe_flag == KD_EXE_NO_RUN) {
			print_debug("can't assembly\n");
			next_node = curr_node;
			break;
		}
		if (exe_flag == KD_EXE_RUN_ERROR) {
			print_debug("run error\n");
			/* No JIT body ran. Keep the packet queued and uncompleted until
			 * it acquires the lock. Native packets may need ret4; virtual
			 * packets use the ordinary acquired return to their parent. */
			next_node = curr_node;
			break;
		}

		if (exe_flag != KD_EXE_NATIVE_DONE)
			clear_locked_set_completed(curr_node);

		if (batch.outer.released) {
			/* B and this logical frame have finished. A's queue was already
			 * published; only reacquire for our own original request. */
			kd_spin_reclaim_outer(request);
			kd_source_frame_put();
			return;
		}

		if (next_node == NULL || next_node->next == NULL ||
		    counter >= kd_combiner_batch_size)
			break;

		curr_node = next_node;
	}

#ifdef NUMA_AWARE
	if (ptr->local_queue_head != NULL) {
		ptr->local_queue_tail->next = next_node;
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_splice(lock, next_node, false);
#endif
		next_node = ptr->local_queue_head;
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
	}
#endif

	print_debug("After combiner %d, next node: %d\n", smp_processor_id(),
		    next_node->cpuid);

#ifdef DEBUG_KD_SPIN
	BUG_ON(next_node == NULL);
#endif

	set_locked(request->word);

	/* Publish the finished queue splice before successor acquisition. This
	 * is the last node access: its waiter can immediately reuse the slot. */
	smp_store_release(&next_node->locked, false);
	/* One lease covers the complete synchronous batch, including native ACK
	 * waits and every child unbind. New requests still check admission. */
	kd_source_frame_put();
}
#pragma GCC pop_options
