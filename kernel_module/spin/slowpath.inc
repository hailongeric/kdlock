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
 *  0/2/4 -> delegated completion / queue acquisition / retry-path variants,
 *  1/3   -> waiters resumed from JIT completion/native,
 *  5     -> native relay wait.
 */
__attribute__((noipa)) noinline notrace static int
__kd_spin_lock_longjmp(struct qspinlock *lock, int tail,
		       register struct kd_spin_node *curr_node)
{
	struct qspinlock *word = kd_spin_word(lock);
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
#ifdef NUMA_AWARE
	struct kd_spin_node *prev_local_queue_head;
	struct kd_spin_node *prev_local_queue_tail;
#endif

	/* Publish the clock with the node, before any combiner can service it. */
	curr_node->queued_at_ns = kd_exe_queue_timing_start();
	old_tail = xchg_tail(lock, tail);
	kd_spin_diag_waiter_enter(lock);

	if (old_tail & _Q_TAIL_MASK_HL) {
		prev_node = decode_tail(old_tail);
#ifdef KDLOCK_SELFTEST
		/* Publication can let the predecessor finish and recycle its node. */
		int previous_task = prev_node->task_struct_ptr->pid;
		int previous_cpu = prev_node->cpuid;
#endif

		prev_node->next = curr_node;
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_link(curr_node, prev_node, previous_task,
				      previous_cpu);
#endif

		while (smp_load_acquire(&curr_node->locked)) {
			if (curr_node->jit_waiter) {
				kd_spin_selftest_node_event(
					KD_NODE_REMOTE_POLL);
				kd_exec_remote_poll(
					curr_node->jit_context->requester);
			}
			cpu_relax();
		}
		smp_rmb();
		if (READ_ONCE(curr_node->native_resume)) {
			this_cpu_ptr(&kd_spin_nodes[0])->count--;
			kd_spin_selftest_node_event(KD_NODE_NATIVE_RETURN);
			kd_spin_diag_waiter_exit(lock);
			kd_spin_set_resume_node(curr_node);
			return 5;
		}

		struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

		if (curr_node->completed) {
			print_debug("wakeup\n");
#ifdef ENABLE_IRQS_CHECK
			if (curr_node->irqs_disabled) {
				ptr->irqs_disabled = curr_node->irqs_disabled;
			}
#endif
			for (j = 7; j >= 0; j--)
				if (ptr->lock_addr[j] != 0)
					break;

			this_cpu_ptr(&kd_spin_nodes[0])->count--;
			kd_spin_selftest_node_event(KD_NODE_REMOTE_RETURN);

			if (!curr_node->jit_waiter && j >= 0) {
				parent_lock =
					(struct qspinlock *)(unsigned long)
						ptr->lock_addr[j];
#ifdef DEBUG_KD_SPIN
				BUG_ON(parent_lock == lock);
#endif
				if (kd_spin_is_ooo(parent_lock)) {
					print_debug("Waiter unlocked OOO\n");
					kd_spin_diag_waiter_exit(lock);
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
			kd_spin_diag_waiter_exit(lock);
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
	    atomic_try_cmpxchg_relaxed(&word->val, &val, _Q_LOCKED_VAL_HL))
		goto release; /* No contention */

	/* Either somebody is queued behind us or _Q_PENDING_VAL_HL is set */
	check_and_set_combiner(lock);
	kd_spin_claim_origin(lock);
	/* This request now owns Linux L. Record before releasing/reusing its node
	 * to process followers; the combiner's batch is not this queue interval. */
	kd_exe_queue_timing_end(false, &curr_node->queued_at_ns,
				kd_exe_queue_timing_start());

	/*
	 * contended path; wait for next if not observed yet, release.
	 */
	smp_cond_load_relaxed_sched(&curr_node->next, (VAL));
	next_node = curr_node->next;
#ifdef DEBUG_KD_SPIN
	BUG_ON(next_node == NULL);
#endif
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	j = kd_spin_lock_stack_depth(ptr);
	if (unlikely(j >= ARRAY_SIZE(ptr->lock_addr))) {
		/*
		 * Keep native ownership without entering another combiner. The
		 * successor may wait on the physical lock, but cannot acquire it
		 * until our caller unlocks. No saved context has been changed and
		 * the common exit releases this node exactly once.
		 */
		set_locked(lock);
		smp_store_release(&next_node->locked, false);
		goto release;
	}

	prev_cs_cpu = ptr->curr_cs_cpu;
	ptr->curr_cs_cpu = -1;

	ptr->irqs_disabled = false;

#ifdef DEBUG_KD_SPIN
	BUG_ON(ptr->prev_cs_cpu != -1);
#endif
	/*
	 * curr_node at the head of the queue.
	 * Release the node and run_combiner.
	 */
	this_cpu_ptr(&kd_spin_nodes[0])->count--;
	kd_spin_selftest_node_event(KD_NODE_COMBINER_ENTER);
	prev_locked_val = word->locked;
#ifdef DEBUG_KD_SPIN
	BUG_ON(prev_locked_val >= _Q_LOCKED_COMBINER_VAL);
#endif
	word->locked = _Q_LOCKED_COMBINER_VAL;
	prev_rsp = curr_node->rsp;
	curr_node->rsp = 0;

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

	run_combiner(lock, next_node);

#ifdef DEBUG_KD_SPIN
	BUG_ON(this_cpu_ptr(&local_shadow_stack)->lock_addr[j] !=
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

	kd_spin_diag_waiter_exit(lock);
	kd_spin_set_resume_node(curr_node);
	return READ_ONCE(curr_node->jit_retry) ? 4 : 2;
release:
	kd_spin_claim_origin(lock);
	kd_exe_queue_timing_end(false, &curr_node->queued_at_ns,
				kd_exe_queue_timing_start());
	/*
	 * release the node
	 */
	this_cpu_ptr(&kd_spin_nodes[0])->count--;
	kd_spin_selftest_node_event(KD_NODE_HEAD_RETURN);
	kd_spin_diag_waiter_exit(lock);
	kd_spin_set_resume_node(curr_node);
	return READ_ONCE(curr_node->jit_retry) ? 4 : 0;
}
#pragma GCC pop_options

/*
 * Slowpath entry for promoted locks:
 * allocates a per-CPU node, initializes queue state, and either waits or runs
 * combiner depending on queue position and contention.
 */
__attribute__((noipa)) noinline notrace static int
__kd_spin_lock_slowpath(struct qspinlock *lock)
{
	struct kd_spin_node *base, *curr_node;
	struct kd_spin_native_input *input;
	int tail, idx;

	base = this_cpu_ptr(&kd_spin_nodes[0]);
	kd_spin_diag_record(
		lock, KD_SPIN_DIAG_SLOWPATH,
		kd_spin_lock_stack_depth(this_cpu_ptr(&local_shadow_stack)));
	idx = base->count++;
	if (unlikely(idx >= MAX_NODES)) {
		base->count--;
		kd_spin_selftest_node_event(KD_NODE_NATIVE_FULL);
		while (!kd_spin_trylock(lock))
			cpu_relax();
		return 0;
	}
	kd_spin_selftest_node_event(KD_NODE_NATIVE_RESERVE);
	curr_node = base + idx;
	input = this_cpu_ptr(&kd_spin_native_inputs);
	tail = encode_tail(smp_processor_id(), idx);

	/*
	 * Initialize curr_node
	 */
	curr_node->locked = true;
	curr_node->completed = false;
	curr_node->next = NULL;
	curr_node->tail = tail;
	curr_node->socket_id = numa_node_id();
	curr_node->cpuid = smp_processor_id();
	curr_node->rsp = READ_ONCE(input->rsp);
	curr_node->regs.sp = READ_ONCE(input->regs_sp);
	curr_node->irqs_disabled = false;
	curr_node->lock = lock;
	curr_node->task_struct_ptr = current;
	curr_node->gsbase = kd_read_kernel_gsbase();
	curr_node->exec_frame = NULL;
	curr_node->jit_waiter = false;
	curr_node->jit_retry = false;
	curr_node->native_resume = false;
	curr_node->pinned_context = (preempt_count() & PREEMPT_MASK) != 1;
	curr_node->native_regs_decoded = false;
	curr_node->jit_context = NULL;
	BUG_ON(!kd_spin_entry_find((raw_spinlock_t *)lock,
				   &curr_node->spin_origin));

	return __kd_spin_lock_longjmp(lock, tail, curr_node);
}

/*
 * Public API
 */

/* Free all spin-related per-CPU resources and shadow-node state.
 * Callers must ensure no active delegations remain before draining.
 */
