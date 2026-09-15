// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Virtual nested waiters, remote completion and out-of-order unlock results.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* Build a virtual waiter packet from a logical frame for nested delegation.
 * Parent frame lock vector is copied so nested ownership checks remain consistent.
 */
static int kd_spin_prepare_jit_node(struct kd_spin_node *node,
				    struct kd_spin_jit_context *context,
				    struct qspinlock *lock,
				    const struct pt_regs *regs,
				    struct kd_exec_frame *parent)
{
	unsigned int i, depth;

	if (!node || !context || !lock || !regs || !parent ||
	    !kd_exec_frame_validate(parent))
		return -EINVAL;

	depth = kd_exec_frame_lock_depth(parent);
	if (depth >= KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;

	node->regs = *regs;
	node->gsbase = parent->gsbase;
	node->task_struct_ptr = parent->logical_task;
	node->spin_origin = parent->spin_origin;
	node->jit_waiter = true;
	node->pinned_context = false;
	node->jit_context = context;
	context->requester = parent;
	context->lock_depth = depth + 1;
	for (i = 0; i < depth; i++) {
		context->lock_addr[i] = parent->jit_lock_addr[i];
		context->lock_kind[i] = parent->jit_lock_kind[i];
		context->lock_node[i] = parent->jit_lock_node[i];
		context->lock_released[i] = parent->jit_lock_released[i];
	}
	context->lock_addr[depth] = (unsigned long)lock;
	context->lock_kind[depth] = KD_EXEC_LOCK_QUEUE_OWNER;
	context->lock_node[depth] = node;
	context->lock_released[depth] = false;
	return 0;
}

/* Restore a virtual node's continuation after the callee returns from nested
 * critical-section execution.
 */
static int kd_spin_advance_jit_node(struct kd_spin_node *node,
				    struct pt_regs *regs)
{
	unsigned long return_ip;

	if (!node || !regs || !node->regs.sp)
		return -EINVAL;
	return_ip = READ_ONCE(*(unsigned long *)node->regs.sp);
	if (!return_ip)
		return -EINVAL;
	node->regs.sp += sizeof(unsigned long);
	node->regs.ip = return_ip;
	*regs = node->regs;
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
		*regs = node->regs;
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
	struct kd_spin_ref request = { 0 };
	struct qspinlock *word;
	struct kd_spin_node *base, *node;
	struct kd_spin_jit_context *contexts;
	u32 tail;
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
				  &request);
#ifdef KDLOCK_SELFTEST
	if (refusal_probe)
		kd_spin_selftest_virtual_end(&request, regs, parent, ret);
#endif
	if (ret)
		return ret;
	word = kd_spin_word(lock);
	if (atomic_cmpxchg_acquire(&word->val, 0, _Q_LOCKED_VAL_HL) == 0) {
		kd_spin_claim_origin(lock);
		parent->control_call.phase = KD_CALL_ACQUIRED;
		return KD_SPIN_NESTED_ACQUIRED;
	}

	base = this_cpu_ptr(&kd_spin_nodes[0]);
	contexts = *this_cpu_ptr(&kd_spin_jit_contexts);
#ifdef KDLOCK_SELFTEST
	/* Exercise real post-ticket cancellation before any node is published. */
	refusal_probe = kd_spin_selftest_virtual_begin(
		lock, &request, regs, parent, &contexts, initial_preempt);
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
	node = base + idx;
	tail = encode_tail(smp_processor_id(), idx);

	node->locked = true;
	node->completed = false;
	node->next = NULL;
	node->tail = tail;
	node->socket_id = numa_node_id();
	node->cpuid = smp_processor_id();
	node->rsp = regs->sp;
	node->lock = lock;
	node->task_struct_ptr = NULL;
	node->gsbase = 0;
	node->irqs_disabled = false;
	node->exec_frame = NULL;
	node->jit_retry = false;
	node->native_resume = false;
	node->native_regs_decoded = false;
	ret = kd_spin_prepare_jit_node(node, &contexts[idx], lock, regs,
				       parent);
	if (ret) {
		base->count--;
		kd_spin_selftest_node_event(KD_NODE_PREPARE_CANCEL);
		goto cancel;
	}

	kd_spin_diag_record(
		lock, KD_SPIN_DIAG_SLOWPATH,
		kd_spin_lock_stack_depth(this_cpu_ptr(&local_shadow_stack)));
	parent->control_call.phase = KD_CALL_ENTERED;
	smp_store_release(&parent->remote_result, KD_EXEC_REMOTE_WAITING);
	ret = __kd_spin_lock_longjmp(lock, tail, node);
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_refusal_return(parent, node, ret);
#endif
	if (ret == 5) {
		BUG_ON(smp_load_acquire(&parent->remote_result) !=
		       KD_EXEC_REMOTE_NATIVE);
		*regs = node->regs;
		parent->control_call.phase = KD_CALL_COMPLETE;
		/* Retire B's physical request, not the logical waiter's native ref. */
		BUG_ON(kd_spin_entry_end(&request));
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
	BUG_ON(kd_spin_entry_end(&request));
	return ret;
cancel:
	BUG_ON(kd_spin_entry_end(&request));
#ifdef KDLOCK_SELFTEST
	if (refusal_probe)
		kd_spin_selftest_virtual_end(&request, regs, parent, ret);
#endif
	return ret;
}

/* Resolve nested unlock for a delegated spinlock and propagate OOO condition.
 * For normal fast-path release it only pops the logical shadow stack entry.
 */
int kd_spin_nested_unlock(struct qspinlock *lock)
{
	bool ooo;

	if (!lock)
		return -EINVAL;

	kd_spin_unlock(lock);
	ooo = kd_spin_is_ooo(lock);
	if (ooo)
		return KD_SPIN_NESTED_UNLOCK_OOO;

	return kd_spin_nested_shadow_pop(lock);
}
