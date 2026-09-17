// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Per-CPU allocation, partial-init rollback and drained shutdown reporting.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static void kd_spinlock_free_percpu(void)
{
	int cpu;

	for_each_possible_cpu(cpu) {
		struct shadow_stack *stack =
			per_cpu_ptr(&local_shadow_stack, cpu);

		vfree(*per_cpu_ptr(&kd_spin_jit_contexts, cpu));
		*per_cpu_ptr(&kd_spin_jit_contexts, cpu) = NULL;
		vfree(*per_cpu_ptr(&kd_spin_requests, cpu));
		*per_cpu_ptr(&kd_spin_requests, cpu) = NULL;
		if (stack->wait_stack_top) {
			vfree((char *)stack->wait_stack_top - KD_SPIN_WAIT_STACK_SIZE);
			stack->wait_stack_top = NULL;
		}
		stack->local_shadow_stack_ptr = 0;
	}
#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_nodes_free();
#endif
}

/*
 * Initialize JIT/diagnostic state for all CPUs.
 * Any allocation failure rolls back partially created per-CPU state.
 */
int kd_spinlock_init(void)
{
	int i, j;
#ifdef KDLOCK_SELFTEST
	int ret;
#endif

	atomic64_set(&kd_spin_diag_overflow, 0);
	atomic64_set(&kd_spin_diag_invariant_failures, 0);
	for (i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
		atomic_long_set(&kd_spin_diag_slots[i].addr, 0);
		for (j = 0; j < KD_SPIN_DIAG_EVENT_COUNT; j++)
			atomic64_set(&kd_spin_diag_slots[i].event[j], 0);
		atomic_set(&kd_spin_diag_slots[i].max_depth, 0);
		atomic_set(&kd_spin_diag_slots[i].waiter_count, 0);
		atomic_set(&kd_spin_diag_slots[i].jit_disabled, 0);
	}

#ifdef KDLOCK_SELFTEST
	ret = kd_spin_selftest_nodes_init();
	if (ret)
		return ret;
#endif
	for_each_possible_cpu(i) {
		struct shadow_stack *ptr = per_cpu_ptr(&local_shadow_stack, i);
		struct kd_spin_jit_context *contexts;
		void *wait_stack;

		/* Allocate once, outside the lock path, as in TCLock komb_init(). */
		wait_stack = vzalloc(KD_SPIN_WAIT_STACK_SIZE);
		if (!wait_stack)
			goto err_free;
		ptr->wait_stack_top = (char *)wait_stack + KD_SPIN_WAIT_STACK_SIZE;

		contexts = vzalloc(array_size(MAX_NODES, sizeof(*contexts)));
		if (!contexts)
			goto err_free;
		*per_cpu_ptr(&kd_spin_jit_contexts, i) = contexts;
		*per_cpu_ptr(&kd_spin_requests, i) = vzalloc(array_size(
			KD_SPIN_REQUEST_SLOTS, sizeof(struct kd_spin_exec_request)));
		if (!*per_cpu_ptr(&kd_spin_requests, i))
			goto err_free;

		for (j = 0; j < 8; j++)
			ptr->lock_addr[j] = 0;
		ptr->local_shadow_stack_ptr = 0;
		ptr->curr_cs_cpu = -1;
		ptr->prev_cs_cpu = -1;
#ifdef NUMA_AWARE
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
#endif

		ptr->irqs_disabled = false;
		*per_cpu_ptr(&kd_spin_resume_nodes, i) = NULL;

		for (j = 0; j < MAX_NODES; j++) {
			struct kd_spin_node *node =
				per_cpu_ptr(&kd_spin_nodes[j], i);

			node->jit_waiter = false;
			node->jit_retry = false;
			node->native_regs_decoded = false;
			node->jit_context = NULL;
			node->execution = NULL;
			node->regs = NULL;
			node->gsbase = 0;
		}
	}

#ifdef KDLOCK_SELFTEST
	ret = kd_spin_shadow_selftest();
	if (ret) {
		kd_spinlock_free_percpu();
		return ret;
	}
#endif
	return 0;

err_free:
	kd_spinlock_free_percpu();
	return -ENOMEM;
}

/* Print per-lock accounting and release per-CPU resources.
 * Must be invoked after all active frames and waiters have drained.
 */
void kd_spinlock_exit(void)
{
	int i, cpu;

	for_each_possible_cpu(cpu) {
		struct kd_spin_exec_request *pool =
			*per_cpu_ptr(&kd_spin_requests, cpu);

		for (i = 0; i < KD_SPIN_REQUEST_SLOTS; i++)
			BUG_ON(atomic_read(&pool[i].users));
	}

#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_nodes_report();
	kd_spin_selftest_frames_report();
	kd_spin_selftest_refusal_report();
#ifdef NUMA_AWARE
	kd_spin_selftest_deferred_report();
#endif
#endif
	KD_PR_INFO("kd_spin diag overflow=%lld\n",
		   (long long)atomic64_read(&kd_spin_diag_overflow));
	KD_PR_INFO("kd_spin diag invariant_failures=%lld\n",
		   (long long)atomic64_read(&kd_spin_diag_invariant_failures));
	for (i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
		struct kd_spin_diag_slot *slot = &kd_spin_diag_slots[i];
		unsigned long addr =
			(unsigned long)atomic_long_read(&slot->addr);

		if (!addr)
			continue;
		KD_PR_INFO(
			"kd_spin lock stats: lock=%lx depth=%d slowpath=%lld "
			"combiner=%lld jit_success=%lld jit_not_ready=%lld "
			"nested_lock=%lld "
			"nested_unlock=%lld nested_remote=%lld "
			"native_fallback=%lld ooo_unlock=%lld "
			"jit_disabled=%d waiters=%d\n",
			addr, atomic_read(&slot->max_depth),
			(long long)atomic64_read(
				&slot->event[KD_SPIN_DIAG_SLOWPATH]),
			(long long)atomic64_read(
				&slot->event[KD_SPIN_DIAG_COMBINER]),
			(long long)atomic64_read(
				&slot->event[KD_SPIN_DIAG_JIT_SUCCESS]),
			(long long)atomic64_read(
				&slot->event[KD_SPIN_DIAG_JIT_NOT_READY]),
			(long long)atomic64_read(
				&slot->event[KD_SPIN_DIAG_NESTED_LOCK]),
			(long long)atomic64_read(
				&slot->event[KD_SPIN_DIAG_NESTED_UNLOCK]),
			(long long)atomic64_read(
				&slot->event[KD_SPIN_DIAG_NESTED_REMOTE]),
			(long long)atomic64_read(
				&slot->event[KD_SPIN_DIAG_NATIVE_FALLBACK]),
			(long long)atomic64_read(
				&slot->event[KD_SPIN_DIAG_OOO_UNLOCK]),
			atomic_read(&slot->jit_disabled),
			atomic_read(&slot->waiter_count));
	}

	kd_spinlock_free_percpu();
}
