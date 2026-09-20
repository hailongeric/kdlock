/* Progressed JIT exits and nested/native/remote completion.
 * Included by combiner.inc after its batch/outer-release helpers.
 * Keep compiler attributes, option pragmas and assembly in this translation unit. */
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
	struct kd_spin_jit_context *jit_context = &curr_node->execution->jit_context;
	unsigned long entry_ip;
	u64 queue_end;
	bool abort_cleaned = false;
#ifdef KDLOCK_SELFTEST
	int frame_event;
#endif

	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);

	if (batch->pending) {
		frame = &curr_node->execution->frame;
		exe = batch->exe;
		queue_end = batch->queue_end;
#ifdef KDLOCK_SELFTEST
		frame_event = batch->frame_event;
#endif
		ret_flag = kd_exe_spin_batch_resume(exe, &batch->call);
		frame->outer_unlock_hook = &batch->outer;
		batch->pending = false;
		goto dispatched;
	}

	ptr->curr_cs_cpu = curr_node->cpuid;

	/* A plain waiter cannot describe locks/context pinned before this request.
	 * Keep its private-queue position, but let it execute on its own stack. */
	if (!curr_node->execution->jit_waiter && curr_node->execution->pinned_context) {
		pr_warn_ratelimited(
			"[KD_JIT][WARN] reason=PINNED_NATIVE_WAITER task=%d cpu=%d lock=%px\n",
			curr_node->execution->frame.logical_task->pid, curr_node->cpuid,
			lock);
		return KD_EXE_NO_RUN;
	}
	if (kd_spin_jit_is_disabled(batch->diag)) {
		kd_spin_diag_record(lock, KD_SPIN_DIAG_NATIVE_FALLBACK,
				    kd_spin_lock_stack_depth(ptr));
		return KD_EXE_NO_RUN;
	}

#ifdef DEBUG_KD_SPIN
	BUG_ON(curr_node->cpuid == smp_processor_id());
#endif

	/* Physical packets are fully prepared before the waiter publishes next. */
	if (!curr_node->execution->jit_waiter && !curr_node->execution->native_regs_decoded)
		return KD_EXE_RUN_ERROR;
	if (curr_node->execution->jit_waiter && !jit_context->requester)
		return KD_EXE_RUN_ERROR;
	/* B is a continuation in A's admitted code. An independent B translation
	 * starts at lexical depth one and can stop at an inherited A unlock. */
	entry_ip = curr_node->execution->jit_waiter ? jit_context->requester->entry_ip :
					   curr_node->execution->frame.regs_ref->ip;
	exe = kd_spin_batch_find_ready(batch, entry_ip);
	if (!exe) {
		kd_spin_debug_jit_not_ready(batch->diag,
					    kd_spin_lock_stack_depth(ptr));
		kd_exe_add_abi(0, entry_ip, KD_EXE_LOCK_SPIN,
		               curr_node->execution->frame.entry_abi);
		return KD_EXE_NO_RUN;
	}
	if (curr_node->execution->frame.packet_state == KD_PACKET_FULL)
	print_debug(
		"r15 %lx r14 %lx r13 %lx r12 %lx bx %lx bp %lx ip %lx sp %lx\n",
		curr_node->execution->frame.regs_ref->r15, curr_node->execution->frame.regs_ref->r14, curr_node->execution->frame.regs_ref->r13,
		curr_node->execution->frame.regs_ref->r12, curr_node->execution->frame.regs_ref->bx, curr_node->execution->frame.regs_ref->bp,
		curr_node->execution->frame.regs_ref->ip, curr_node->execution->frame.regs_ref->sp);
	frame_lock_depth = curr_node->execution->jit_waiter ?
				   jit_context->lock_depth :
				   kd_spin_lock_stack_depth(ptr);
	frame = &curr_node->execution->frame;
	if (kd_exec_frame_bind(frame, frame_lock_depth, true)) {
		KD_PR_ERR("spin JIT frame stack overflow lock=%px\n", lock);
		return KD_EXE_RUN_ERROR;
	}

	kd_exec_frame_prepare_complex(frame);
	if ((curr_node->execution->jit_waiter &&
	     kd_exec_frame_set_lock_entries(
		     frame, frame->jit_lock_addr, frame->jit_lock_kind,
		     frame->jit_lock_node, frame->jit_lock_released,
		     jit_context->lock_depth)) ||
	    (!curr_node->execution->jit_waiter &&
	     kd_exec_frame_set_lock_stack(frame,
					  (const unsigned long *)ptr->lock_addr,
					  kd_spin_lock_stack_depth(ptr)))) {
		KD_PR_ERR("spin JIT frame lock stack invalid lock=%px\n", lock);
		kd_exec_frame_abort(frame);

		if (kd_exec_frame_pop(frame, NULL))
			KD_PR_ERR("spin JIT frame abort pop failed lock=%px\n",
				  lock);
		return KD_EXE_RUN_ERROR;
	}
	/* The generic ledger initializes only its live prefix. Keep one entry
	 * for a simple root so promotion to nested/native needs no reconstruction;
	 * delay the large combiner snapshot until the first non-final exit. */
	frame->spin_simple = !curr_node->execution->jit_waiter && !frame->parent &&
			     frame_lock_depth == 1;
	if (!frame->spin_simple)
		kd_spin_capture_combiner_state(&frame->saved_combiner, ptr);
	frame->outer_unlock_hook = &batch->outer;
	if (curr_node->execution->jit_waiter) {
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
dispatched:
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_frame_end(frame_event, frame, ret_flag);
	kd_spin_selftest_refusal_end(frame, ret_flag);
#endif
	/* A pre-body refusal is still waiting. Once a body ran, use its saved
	 * dispatch boundary and consume metadata before native/completion wake. */
	if (frame->executed)
		kd_exe_queue_timing_end(false, &curr_node->execution->queued_at_ns, queue_end);
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

		WRITE_ONCE(curr_node->execution->native_resume, true);
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
	curr_node->execution->jit_retry = !curr_node->execution->jit_waiter &&
			       ret_flag != KD_EXE_RUN_TO_UNLOCK;
	if (curr_node->execution->jit_retry)
		KD_PR_INFO(
			"spin JIT retry regs: node=%px cpu=%d ip=%lx failed_ip=%lx\n",
			curr_node, curr_node->cpuid, curr_node->execution->frame.regs_ref->ip,
			ret_flag == KD_EXE_RUN_TO_UNLOCK ?
				0UL :
				frame->continuation_ip);

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
		kd_spin_debug_jit_success(batch->diag, kd_spin_lock_stack_depth(ptr));
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
		ptr->curr_cs_cpu = -1;
		word->locked = _Q_LOCKED_COMBINER_VAL;
	}
	return 0;
}
#pragma GCC pop_options
