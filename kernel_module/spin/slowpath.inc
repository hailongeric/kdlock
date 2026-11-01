// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Queue-head waiting, nested combiner restoration and native node admission.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

#pragma GCC push_options
#pragma GCC optimize("O3")
/*
 * Core queue+combiner protocol entry.
 * Returns:
 *  0/2   -> queue acquisition (without/with a combiner batch),
 *  4     -> acquired pre-body retry,
 *  1/3   -> virtual waiter completion,
 *  5     -> virtual native relay.
 * Physical completion/native wake abandons these C frames in wait.inc.
 */
__attribute__((noipa)) noinline notrace static int
__kd_spin_lock_longjmp(struct qspinlock *lock, int tail,
		       register struct kd_spin_node *curr_node,
		       struct kd_spin_request *request)
{
	struct qspinlock *word = request->word;
	register struct kd_spin_node *prev_node = NULL, *next_node = NULL;
	struct qspinlock *parent_lock;
	int old_tail, val, j;

	/*
	 * These values remain live while a nested waiter or combiner runs. Keep
	 * their storage in this frame so the parent combiner can restore them.
	 */
	uint32_t prev_cs_cpu;
	bool prev_locked_val;
	uint64_t prev_rsp;
	struct kd_spin_continuation *prev_execution;
#ifdef NUMA_AWARE
	struct kd_spin_node *prev_local_queue_head;
	struct kd_spin_node *prev_local_queue_tail;
#endif

	/* Publish the clock with the node, before any combiner can service it. */
	curr_node->execution->queued_at_ns = kd_exe_queue_timing_start();
	old_tail = xchg_tail(word, tail);
	kd_spin_diag_waiter_enter(curr_node->execution->diag);

	if (old_tail & _Q_TAIL_MASK_HL) {
		prev_node = decode_tail(old_tail);
#ifdef KDLOCK_SELFTEST
		/* Publication can let the predecessor finish and recycle its node. */
		int previous_task = prev_node->execution ?
			prev_node->execution->frame.logical_task->pid : 0;
		int previous_cpu = prev_node->cpuid;
#endif

#ifdef KDLOCK_SELFTEST
		/* Observe before publication: the physical waiter cannot call C
		 * once a remote executor is allowed to overwrite its old frames. */
		kd_spin_selftest_link(curr_node, prev_node, previous_task,
				      previous_cpu);
#endif
		if (curr_node->execution->frame.spin_kind != KD_SPIN_CONT_VIRTUAL) {
			kd_spin_publish_wait(curr_node, prev_node,
				this_cpu_ptr(&kd_spin_cpu)->wait_stack_top);
			/* Only an unexecuted queue-head handoff returns here. */
			goto queue_head;
		}
		smp_store_release(&prev_node->next, curr_node);

		/* This is a virtual waiter: its independent executor stack stays live
		 * while the child runs. Poll the mailbox inline on the empty path, but
		 * service every observed request so ancestor unlock/ACK can progress. */
		struct kd_exec_frame *requester = curr_node->execution->jit_context.requester;

		while (smp_load_acquire(&curr_node->locked)) {
			kd_spin_selftest_node_event(KD_NODE_REMOTE_POLL);
			if (smp_load_acquire(&requester->remote_request))
				kd_exec_remote_poll(requester);
			cpu_relax();
		}
		smp_rmb();
		if ((READ_ONCE(curr_node->execution->result) == KD_SPIN_RES_NATIVE_READY)) {
			kd_spin_selftest_node_event(KD_NODE_NATIVE_RETURN);
			kd_spin_diag_waiter_exit(curr_node->execution->diag);
			kd_spin_set_resume_node(curr_node);
			return 5;
		}

		struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);

		if (curr_node->completed) {
			print_debug("wakeup\n");
			for (j = 7; j >= 0; j--)
				if (ptr->lock_addr[j] != 0)
					break;

			kd_spin_selftest_node_event(KD_NODE_REMOTE_RETURN);

			if (curr_node->execution->frame.spin_kind != KD_SPIN_CONT_VIRTUAL && j >= 0) {
				parent_lock =
					(struct qspinlock *)(unsigned long)
						ptr->lock_addr[j];
#ifdef DEBUG_KD_SPIN
				BUG_ON(parent_lock == lock);
#endif
				if (kd_spin_is_ooo(parent_lock)) {
					print_debug("Waiter unlocked OOO\n");
					kd_spin_diag_waiter_exit(curr_node->execution->diag);
					kd_spin_set_resume_node(curr_node);
					return 1;
				}
			}

			prefetchw((void *)(unsigned long)curr_node->rsp);
			prefetchw((void *)(unsigned long)(curr_node->rsp + 64));
			prefetchw(
				(void *)(unsigned long)(curr_node->rsp + 128));
			prefetchw(
				(void *)(unsigned long)(curr_node->rsp + 192));
			prefetchw(
				(void *)(unsigned long)(curr_node->rsp + 256));
			prefetchw(
				(void *)(unsigned long)(curr_node->rsp + 320));
			kd_spin_diag_waiter_exit(curr_node->execution->diag);
			kd_spin_set_resume_node(curr_node);
			return 3;
		}
	}

	/*
	 * we're at the head of the waitqueue, wait for the owner & pending to
	 * go away.
	 *
	 * *,x,y -> *,0,0
	 *
	 * this wait loop must use a load-acquire such that we match the
	 * store-release that clears the locked bit and create lock
	 * sequentiality; this is because the set_locked() function below
	 * does not imply a full barrier.
	 *
	 */

queue_head:
	val = atomic_cond_read_acquire(&word->val,
				       !(VAL & _Q_LOCKED_PENDING_MASK));

	/*
	 * claim the lock:
	 *
	 * n,0,0 -> 0,0,1 : lock, uncontended
	 * *,*,0 -> *,*,1 : lock, contended
	 *
	 * If the queue head is the only one in the queue (lock value == tail)
	 * and nobody is pending, clear the tail code and grab the lock.
	 * Otherwise, we only need to grab the lock.
	 */

	if (((val & _Q_TAIL_MASK_HL) == tail) &&
	    atomic_try_cmpxchg_relaxed(&word->val, &val, _Q_LOCKED_VAL_HL)) {
		goto release; /* No contention */
	}

	/* Either somebody is queued behind us or _Q_PENDING_VAL_HL is set */
	check_and_set_combiner(word);
	kd_spin_claim_origin(request);
	/* This request now owns Linux L. Record before releasing/reusing its node
	 * to process followers; the combiner's batch is not this queue interval. */
	kd_exe_queue_timing_end(false, &curr_node->execution->queued_at_ns,
				kd_exe_queue_timing_start());

	/*
	 * contended path; wait for next if not observed yet, release.
	 */
	smp_cond_load_relaxed_sched(&curr_node->next, (VAL));
	next_node = curr_node->next;
#ifdef DEBUG_KD_SPIN
	BUG_ON(next_node == NULL);
#endif
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);

	j = kd_spin_lock_stack_depth(ptr);
	if (unlikely(j >= ARRAY_SIZE(ptr->lock_addr))) {
		/*
		 * Keep native ownership without entering another combiner. The
		 * successor may wait on the physical lock, but cannot acquire it
		 * until our caller unlocks. No saved context has been changed and
		 * the common exit releases this node exactly once.
		 */
		set_locked(word);
		smp_store_release(&next_node->locked, false);
		goto release;
	}

	prev_cs_cpu = ptr->curr_cs_cpu;
	ptr->curr_cs_cpu = -1;

	/*
	 * curr_node at the head of the queue.
	 * Release the node and run_combiner.
	 */
	prev_locked_val = word->locked;
#ifdef DEBUG_KD_SPIN
	BUG_ON(prev_locked_val >= _Q_LOCKED_COMBINER_VAL);
#endif
	word->locked = _Q_LOCKED_COMBINER_VAL;
	prev_rsp = curr_node->rsp;
	prev_execution = curr_node->execution;
	curr_node->rsp = 0;
	barrier();
	this_cpu_dec(kd_spin_cpu.node_count);
	kd_spin_selftest_node_event(KD_NODE_COMBINER_ENTER);

#ifdef NUMA_AWARE
	prev_local_queue_head = ptr->local_queue_head;
	prev_local_queue_tail = ptr->local_queue_tail;

#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_queue_context(lock, true);
#endif
	ptr->local_queue_head = NULL;
	ptr->local_queue_tail = NULL;
#endif

	ptr->lock_addr[j] = (uint64_t)(unsigned long)lock;
	kd_spin_diag_validate_lock_stack(ptr);

	/* The owner continuation survives node reuse; carry its immutable slot
	 * without looking through a recyclable node or a follower's packet. */
	run_combiner(lock, next_node, request, prev_execution->diag);
	/* Nested users returned; reserve this slot before touching it again. */
	this_cpu_inc(kd_spin_cpu.node_count);
	barrier();
	kd_spin_selftest_node_event(KD_NODE_COMBINER_RESERVE);

#ifdef DEBUG_KD_SPIN
	BUG_ON(this_cpu_ptr(&kd_spin_cpu)->lock_addr[j] !=
	       (uint64_t)(unsigned long)lock);
#endif

	ptr->lock_addr[j] = 0;
	kd_spin_diag_validate_lock_stack(ptr);

#ifdef NUMA_AWARE
	ptr->local_queue_head = prev_local_queue_head;
	ptr->local_queue_tail = prev_local_queue_tail;
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_queue_context(lock, false);
#endif
#endif

	curr_node->rsp = prev_rsp;
	curr_node->execution = prev_execution;

	if (word->locked == _Q_UNLOCKED_OOO_VAL) {
		if (prev_cs_cpu != -1) {
			print_debug("Waking up %d\n", prev_cs_cpu);
			clear_locked_set_completed(
				per_cpu_ptr(&kd_spin_nodes[0], prev_cs_cpu));
		}
		ptr->curr_cs_cpu = -1;
	} else {
		ptr->curr_cs_cpu = prev_cs_cpu;
	}
	word->locked = prev_locked_val;

	kd_spin_diag_waiter_exit(curr_node->execution->diag);
	kd_spin_set_resume_node(curr_node);
	return (READ_ONCE(curr_node->execution->result) == KD_SPIN_RES_RETRY) ? 4 : 2;
release:
	kd_spin_claim_origin(request);
	kd_exe_queue_timing_end(false, &curr_node->execution->queued_at_ns,
				kd_exe_queue_timing_start());
	/* Producer retains the node through its final return-state reads. */
	kd_spin_selftest_node_event(KD_NODE_HEAD_RETURN);
	kd_spin_diag_waiter_exit(curr_node->execution->diag);
	kd_spin_set_resume_node(curr_node);
	return (READ_ONCE(curr_node->execution->result) == KD_SPIN_RES_RETRY) ? 4 : 0;
}
#pragma GCC pop_options

/*
 * Slowpath entry for promoted locks:
 * allocates a per-CPU node, initializes queue state, and either waits or runs
 * combiner depending on queue position and contention.
 */
__attribute__((noipa)) noinline notrace static int
__kd_spin_lock_slowpath(struct qspinlock *lock, struct kd_spin_request *request,
		       const struct kd_spin_native_input *input)
{
	struct qspinlock *word = request->word;
	struct kd_spin_node *base, *curr_node;
	struct kd_spin_continuation *execution;
	struct kd_spin_diag_slot *diag;
	int tail, idx, ret;

	base = this_cpu_ptr(&kd_spin_nodes[0]);
	diag = kd_spin_diag_find((unsigned long)lock);
	kd_spin_diag_record_slot(
		diag, KD_SPIN_DIAG_SLOWPATH,
		kd_spin_lock_stack_depth(this_cpu_ptr(&kd_spin_cpu)));
	idx = this_cpu_inc_return(kd_spin_cpu.node_count) - 1;
	barrier();
	if (unlikely(idx >= MAX_NODES)) {
		this_cpu_dec(kd_spin_cpu.node_count);
		kd_spin_selftest_node_event(KD_NODE_NATIVE_FULL);
		while (!kd_spin_trylock(word))
			cpu_relax();
		kd_spin_claim_origin(request);
		return 0;
	}
	execution = kd_spin_continuation_reserve();
	if (unlikely(!execution)) {
		this_cpu_dec(kd_spin_cpu.node_count);
		/* Continuation exhaustion does not exhaust independent MCS nodes. */
		kd_spin_acquire_nondelegated(word);
		kd_spin_claim_origin(request);
		return 0;
	}
	kd_spin_selftest_node_event(KD_NODE_NATIVE_RESERVE);
	curr_node = base + idx;
	curr_node->execution = execution;
	execution->diag = diag;
	curr_node->execution->frame.regs_ref = &execution->frame.regs;
	tail = encode_tail(smp_processor_id(), idx);

	/*
	 * Initialize curr_node
	 */
	curr_node->locked = true;
	curr_node->completed = false;
	curr_node->next = NULL;
	curr_node->socket_id = numa_node_id();
	curr_node->read_admission = NULL;
	curr_node->cpuid = smp_processor_id();
	curr_node->proxy_context = kd_spin_proxy_context();
	curr_node->rsp = READ_ONCE(input->rsp);
	curr_node->execution->frame.regs_ref->sp = READ_ONCE(input->regs_sp);

	curr_node->execution->frame.logical_task = current;
	curr_node->execution->frame.gsbase = kd_read_kernel_gsbase();

	curr_node->execution->frame.spin_kind = KD_SPIN_CONT_ROOT;
	curr_node->execution->result = KD_SPIN_RES_QUEUED;
	curr_node->execution->frame.spin_regs_decoded = false;
	curr_node->execution->jit_context.requester = NULL;
	if (kd_entry_abi_spin_clobber(input->entry_abi)) {
		/* No prologue parsing or GPR capture: the caller spilled live values. */
		execution->frame.regs.ip = input->ip;
		execution->frame.regs.bp = input->bp;
		execution->frame.spin_regs_decoded = true;
	} else {
		kd_spin_prepare_regs(curr_node);
	}
	kd_exec_frame_prepare(&execution->frame, curr_node->execution->frame.regs_ref->ip,
		(unsigned long)lock, curr_node->execution->frame.gsbase, current);
	execution->frame.entry_abi = input->entry_abi;
	execution->frame.packet_state = kd_entry_abi_spin_clobber(input->entry_abi) ?
		KD_PACKET_MINIMAL : KD_PACKET_FULL;
	execution->frame.spin_origin = request->ref;
	kd_spin_prepare_prefetch(curr_node, &execution->frame.regs);

	ret = __kd_spin_lock_longjmp(lock, tail, curr_node, request);
	/* Delegated waiters reclaim in restore assembly after the final packet
	 * load. An intact head return can release its continuation here. */
	if (ret == 0 || ret == 2) {
		kd_spin_continuation_release(execution);
		barrier();
		this_cpu_dec(kd_spin_cpu.node_count);
		kd_spin_selftest_node_event(KD_NODE_RELEASE);
	}
	return ret;
}

/*
 * Public API
 */

/* Free all spin-related per-CPU resources and shadow-node state.
 * Callers must ensure no active delegations remain before draining.
 */
