// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Virtual nested waiters, remote completion and out-of-order unlock results.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* Share the logical packet, but prepare the child's independent owner ledger
 * directly in stable request storage. The producer owns this frame until
 * publication; no intermediate context copy is needed before remote binding.
 */
static int kd_spin_prepare_jit_node(struct kd_spin_node *node,
				    struct kd_spin_jit_context *context,
				    struct qspinlock *lock,
				    struct pt_regs *regs,
				    struct kd_exec_frame *parent)
{
	unsigned int i, depth;
	struct kd_exec_frame *frame;
	struct kd_spin_exec_request *owner;

	if (!node || !context || !lock || !regs || !parent ||
	    !kd_exec_frame_validate(parent) ||
	    (parent->request_frame && regs != kd_exec_frame_regs(parent)))
		return -EINVAL;

	depth = kd_exec_frame_lock_depth(parent);
	if (depth >= KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;

	frame = &node->execution->frame;
	kd_exec_frame_prepare(frame, parent->entry_ip, (unsigned long)lock,
		parent->gsbase, parent->logical_task);
	kd_exec_frame_prepare_complex(frame);
	frame->regs_ref = regs;
	frame->entry_abi = parent->entry_abi;
	frame->packet_state = KD_PACKET_FULL;
	frame->spin_origin = parent->spin_origin;
	/* Production roots reside in request storage. Legacy component probes
	 * keep their parent frame synchronously alive instead. */
	if (parent->request_frame) {
		owner = container_of(regs, struct kd_spin_exec_request, frame.regs);
		atomic_inc(&owner->users);
		node->execution->packet_owner = owner;
	}
	node->execution->jit_waiter = true;
	node->execution->pinned_context = false;
	node->execution->jit_context = context;
	context->requester = parent;
	context->lock_depth = depth + 1;
	for (i = 0; i < depth; i++) {
		frame->jit_lock_addr[i] = parent->jit_lock_addr[i];
		frame->jit_lock_kind[i] = parent->jit_lock_kind[i];
		frame->jit_lock_node[i] = parent->jit_lock_node[i];
		frame->jit_lock_released[i] = parent->jit_lock_released[i];
	}
	frame->jit_lock_addr[depth] = (unsigned long)lock;
	frame->jit_lock_kind[depth] = KD_EXEC_LOCK_QUEUE_OWNER;
	frame->jit_lock_node[depth] = node;
	frame->jit_lock_released[depth] = false;
	kd_spin_prepare_prefetch(node, regs);
	return 0;
}

/* Restore a virtual node's continuation after the callee returns from nested
 * critical-section execution.
 */
static int kd_spin_advance_jit_node(struct kd_spin_node *node,
				    struct pt_regs *regs)
{
	unsigned long return_ip;

	if (!node || !regs || !node->execution->frame.regs_ref->sp)
		return -EINVAL;
	return_ip = READ_ONCE(*(unsigned long *)node->execution->frame.regs_ref->sp);
	if (!return_ip)
		return -EINVAL;
	node->execution->frame.regs_ref->sp += sizeof(unsigned long);
	node->execution->frame.regs_ref->ip = return_ip;
	return 0;
}

/* Complete the virtual-node resume decision after delegated nested execution:
 * parent done -> return to parent unlock path, else restore caller continuation.
 */
static int kd_spin_finish_remote_node(struct kd_spin_node *node,
				      struct pt_regs *regs,
				      struct kd_exec_frame *parent)
{
	if (smp_load_acquire(&parent->remote_result) != KD_EXEC_REMOTE_DONE)
		return -EINVAL;
	/* The physical waiter trampoline still needs the final unlock CALL word.
	 * Consume it only when this parent will resume more translated code. */
	if (kd_exec_frame_can_complete(parent)) {
		return KD_SPIN_NESTED_PARENT_OOO;
	}
	if (kd_spin_advance_jit_node(node, regs))
		return -EINVAL;
	return KD_SPIN_NESTED_DELEGATED;
}

/* Register a nested spinlock request in logical parent frame and run queue protocol.
 * Returns acquired/delegated markers used by the parent CALL continuation handling.
 */
int kd_spin_nested_lock(struct qspinlock *lock, struct pt_regs *regs,
			struct kd_exec_frame *parent)
{
	struct kd_spin_request request = { 0 };
	struct qspinlock *word;
	struct kd_spin_node *base, *node;
	struct kd_spin_jit_context *contexts;
	struct kd_spin_exec_request *execution;
	u32 tail;
	unsigned long irq_flags;
	int idx, ret;
#ifdef KDLOCK_SELFTEST
	int initial_preempt = preempt_count();
	bool refusal_probe = false;
#endif

	if (!lock || !regs || !parent)
		return -EINVAL;
	if (kd_exec_frame_remote_pending(parent) ||
	    READ_ONCE(parent->remote_request))
		return -EBUSY;
	parent->remote_result = KD_EXEC_REMOTE_IDLE;

#ifdef KDLOCK_SELFTEST
	/* NULL requests select only the read-only pre-allocation observer. The
	 * context/node injection probes still start after a ticket is reserved.
	 */
	contexts = *this_cpu_ptr(&kd_spin_jit_contexts);
	refusal_probe = kd_spin_selftest_virtual_begin(
		lock, NULL, regs, parent, &contexts, initial_preempt);
#endif
	ret = kd_spin_entry_begin((raw_spinlock_t *)lock, KD_SPIN_ENTRY_VIRTUAL,
				  &request.ref);
#ifdef KDLOCK_SELFTEST
	if (refusal_probe)
		kd_spin_selftest_virtual_end(&request.ref, regs, parent, ret);
#endif
	if (ret)
		return ret;
	word = request.word = kd_spin_request_word(&request.ref);
	if (atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL) == 0) {
		kd_spin_claim_origin(&request);
		parent->control_call.phase = KD_CALL_ACQUIRED;
		return KD_SPIN_NESTED_ACQUIRED;
	}

	base = this_cpu_ptr(&kd_spin_nodes[0]);
	contexts = *this_cpu_ptr(&kd_spin_jit_contexts);
#ifdef KDLOCK_SELFTEST
	/* Exercise real post-ticket cancellation before any node is published. */
	refusal_probe = kd_spin_selftest_virtual_begin(
		lock, &request.ref, regs, parent, &contexts, initial_preempt);
#endif
	if (!contexts) {
		kd_spin_selftest_node_event(KD_NODE_CONTEXT_MISSING);
		ret = -ENOMEM;
		goto cancel;
	}
	idx = base->count++;
	if (unlikely(idx < 0 || idx >= MAX_NODES)) {
		base->count--;
		kd_spin_selftest_node_event(KD_NODE_VIRTUAL_FULL);
		ret = -E2BIG;
		goto cancel;
	}
	kd_spin_selftest_node_event(KD_NODE_VIRTUAL_RESERVE);
	execution = kd_spin_request_reserve();
	if (!execution) {
		base->count--;
		ret = -ENOMEM;
		goto cancel;
	}
	node = base + idx;
	node->execution = execution;
	tail = encode_tail(smp_processor_id(), idx);

	node->locked = true;
	node->completed = false;
	node->next = NULL;
	node->tail = tail;
	node->socket_id = numa_node_id();
	node->cpuid = smp_processor_id();
	node->rsp = regs->sp;

	node->execution->frame.logical_task = NULL;
	node->execution->frame.gsbase = 0;
	node->execution->irq_flags = 0; /* Virtual nodes never restore the physical waiter. */

	node->execution->jit_retry = false;
	node->execution->native_resume = false;
	node->execution->native_regs_decoded = false;
	ret = kd_spin_prepare_jit_node(node, &contexts[idx], lock, regs,
				       parent);
	if (ret) {
		kd_spin_request_put(execution);
		base->count--;
		kd_spin_selftest_node_event(KD_NODE_PREPARE_CANCEL);
		goto cancel;
	}

	kd_spin_diag_record(
		lock, KD_SPIN_DIAG_SLOWPATH,
		kd_spin_lock_stack_depth(this_cpu_ptr(&local_shadow_stack)));
	parent->control_call.phase = KD_CALL_ENTERED;
	parent->delegated_lock_addr = (unsigned long)lock;
	smp_store_release(&parent->remote_result, KD_EXEC_REMOTE_WAITING);
	/* The executor's C stack is independent of the logical waiter stack.
	 * Keep this entire queue/combiner interval IRQ-off, then restore it. */
	local_irq_save(irq_flags);
	ret = __kd_spin_lock_longjmp(lock, tail, node, &request);
	local_irq_restore(irq_flags);
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_refusal_return(parent, node, ret);
#endif
	/* The parent already owns the packet. A native child retains its extra
	 * user until ACK/pop, independently of this queue user's lifetime. */
	kd_spin_request_put(execution);
	if (ret == 5) {
		BUG_ON(smp_load_acquire(&parent->remote_result) !=
		       KD_EXEC_REMOTE_NATIVE);
		parent->control_call.phase = KD_CALL_COMPLETE;
		/* Retire B's physical request, not the logical waiter's native ref. */
		BUG_ON(kd_spin_entry_end(&request.ref));
		return KD_SPIN_NESTED_NATIVE;
	}
	if (ret == 0) {
		parent->remote_result = KD_EXEC_REMOTE_IDLE;
		parent->control_call.phase = KD_CALL_ACQUIRED;
		return KD_SPIN_NESTED_ACQUIRED;
	}
	if (ret == 2) {
		parent->remote_result = KD_EXEC_REMOTE_IDLE;
		parent->control_call.phase = KD_CALL_ACQUIRED;
		return KD_SPIN_NESTED_ACQUIRED_QUEUE;
	}
	if (ret != 1 && ret != 3)
		return -EIO;
	ret = kd_spin_finish_remote_node(node, regs, parent);
	parent->control_call.phase = KD_CALL_COMPLETE;
	BUG_ON(kd_spin_entry_end(&request.ref));
	return ret;
cancel:
	BUG_ON(kd_spin_entry_end(&request.ref));
#ifdef KDLOCK_SELFTEST
	if (refusal_probe)
		kd_spin_selftest_virtual_end(&request.ref, regs, parent, ret);
#endif
	return ret;
}

/* Resolve nested unlock for a delegated spinlock and propagate OOO condition.
 * For normal fast-path release it only pops the logical shadow stack entry.
 */
int kd_spin_nested_unlock(struct qspinlock *lock)
{
	struct kd_spin_request request;
	bool ooo;

	if (!lock)
		return -EINVAL;

	request = kd_spin_unlock_lookup(lock);
	kd_spin_unlock_request(lock, &request);
	ooo = READ_ONCE(request.word->locked) == _Q_UNLOCKED_OOO_VAL;
	if (ooo)
		return KD_SPIN_NESTED_UNLOCK_OOO;

	return kd_spin_nested_shadow_pop(lock);
}
