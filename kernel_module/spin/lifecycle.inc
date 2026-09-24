// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Per-CPU allocation, partial-init rollback and drained shutdown reporting.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* Page-aligned allocations otherwise put every CPU's root packet in the
 * same L1 sets. Use only the unused continuation-area tail to spread roots;
 * the allocation length and the upper 8 KiB polling stack stay unchanged.
 * The current 8512-byte stack admits 60 cache-line colors. A stride of 13
 * visits all of them over consecutive CPU identifiers before repeating. */
static size_t kd_spin_continuation_offset(unsigned int cpu)
{
	const size_t colors = 1 +
		(KD_SPIN_CONT_BYTES - sizeof(struct kd_spin_continuation_stack)) /
		L1_CACHE_BYTES;

	return ((unsigned long)cpu * 13 % colors) * L1_CACHE_BYTES;
}

static void kd_spinlock_free_percpu(void)
{
	int cpu;

	for_each_possible_cpu(cpu) {
		struct kd_spin_cpu_state *stack =
			per_cpu_ptr(&kd_spin_cpu, cpu);

		/* The continuation pointer may be interior. The unchanged polling
		 * stack top retains the allocation base, also during partial init. */
		if (stack->wait_stack_top)
			vfree((char *)stack->wait_stack_top - KD_SPIN_STORAGE_BYTES);
		*per_cpu_ptr(&kd_spin_continuations, cpu) = NULL;
		stack->wait_stack_top = NULL;
	}
	free_percpu(kd_spin_diag_cpu);
	kd_spin_diag_cpu = NULL;
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

	/* Protect both the in-node notification split and adjacent array slots. */
	BUILD_BUG_ON(__alignof__(struct kd_spin_node) < L1_CACHE_BYTES);
	BUILD_BUG_ON(__alignof__(kd_spin_nodes) < 2 * L1_CACHE_BYTES);
	BUILD_BUG_ON(sizeof(struct kd_spin_node) != 2 * L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_spin_node, completed) != L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_spin_node, locked) != L1_CACHE_BYTES + 1);
	BUILD_BUG_ON(sizeof(kd_spinlock_t) != sizeof(u32));
	/* Preserve pair separation within each diagnostic slot and across slots. */
	BUILD_BUG_ON(__alignof__(struct kd_spin_diag_slot) != 2 * L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_spin_diag_slot, waiter_count) != 2 * L1_CACHE_BYTES);
	BUILD_BUG_ON(sizeof(struct kd_spin_diag_slot) != 4 * L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_spin_continuation, frame.packet_state) >= 2 * L1_CACHE_BYTES);
	BUILD_BUG_ON(sizeof(struct kd_spin_continuation) % L1_CACHE_BYTES);
	BUILD_BUG_ON(sizeof(struct kd_spin_continuation) > 768);
	BUILD_BUG_ON(sizeof(struct kd_spin_continuation_stack) > KD_SPIN_CONT_BYTES);
	BUILD_BUG_ON(__alignof__(struct kd_spin_continuation_stack) > L1_CACHE_BYTES);
	BUILD_BUG_ON(KD_SPIN_CONT_BYTES % L1_CACHE_BYTES);
	BUILD_BUG_ON(KD_SPIN_WAIT_STACK_SIZE % L1_CACHE_BYTES);
	if (kd_spin_prefetch_mode > 2)
		return -EINVAL;

	for (i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
		atomic_long_set(&kd_spin_diag_slots[i].addr, 0);
		atomic_set(&kd_spin_diag_slots[i].waiter_count, 0);
		atomic_set(&kd_spin_diag_slots[i].jit_disabled, 0);
	}

#ifdef KDLOCK_SELFTEST
	ret = kd_spin_selftest_nodes_init();
	if (ret)
		return ret;
#endif
	/* Keep diagnostic storage outside the kernel's fixed module per-CPU
	 * reservation. Allocate once at startup, never on a request path. */
	kd_spin_diag_cpu = alloc_percpu(struct kd_spin_diag_cpu);
	if (!kd_spin_diag_cpu)
		goto err_free;
	for_each_possible_cpu(i) {
		struct kd_spin_cpu_state *ptr = per_cpu_ptr(&kd_spin_cpu, i);
		void *wait_stack;

		memset(per_cpu_ptr(kd_spin_diag_cpu, i), 0,
		       sizeof(struct kd_spin_diag_cpu));

		/* Allocate once, outside the lock path, as in TCLock komb_init(). */
		wait_stack = vzalloc(KD_SPIN_STORAGE_BYTES);
		if (!wait_stack)
			goto err_free;
		*per_cpu_ptr(&kd_spin_continuations, i) =
			(void *)((char *)wait_stack + kd_spin_continuation_offset(i));
		ptr->wait_stack_top = (char *)wait_stack + KD_SPIN_STORAGE_BYTES;
		*per_cpu_ptr(&kd_spin_native_root, i) = NULL;

		for (j = 0; j < 8; j++)
			ptr->lock_addr[j] = 0;
		ptr->node_count = 0;
		ptr->curr_cs_cpu = -1;
#ifdef NUMA_AWARE
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
#endif

		*per_cpu_ptr(&kd_spin_resume_nodes, i) = NULL;

		for (j = 0; j < MAX_NODES; j++) {
			struct kd_spin_node *node =
				per_cpu_ptr(&kd_spin_nodes[j], i);

			node->execution = NULL;

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
	u64 overflow = 0, invariant_failures = 0;
	u64 batch_entries = 0, ww_jumps = 0;

	for_each_possible_cpu(cpu) {
		struct kd_spin_continuation_stack *stack =
			*per_cpu_ptr(&kd_spin_continuations, cpu);

		for (i = 0; i < stack->top; i++)
			BUG_ON(!smp_load_acquire(&stack->records[i].retired));
		BUG_ON(*per_cpu_ptr(&kd_spin_native_root, cpu));
		batch_entries += per_cpu_ptr(kd_spin_diag_cpu, cpu)->batch_entries;
		ww_jumps += per_cpu_ptr(kd_spin_diag_cpu, cpu)->ww_jumps;
		overflow += per_cpu_ptr(kd_spin_diag_cpu, cpu)->overflow;
		invariant_failures +=
			per_cpu_ptr(kd_spin_diag_cpu, cpu)->invariant_failures;
	}

#ifdef KDLOCK_SELFTEST
	kd_spin_selftest_nodes_report();
	kd_spin_selftest_frames_report();
	kd_spin_selftest_refusal_report();
#ifdef NUMA_AWARE
	kd_spin_selftest_deferred_report();
#endif
#endif
	/* The caller already drained requests; this is an exact final oracle,
	 * not a live admission or module-lifetime decision. */
	invariant_failures += kd_spin_diag_waiter_mismatches();
	KD_PR_INFO("kd_spin batch: entries=%llu ww_jumps=%llu\n",
		   (unsigned long long)batch_entries, (unsigned long long)ww_jumps);
	KD_PR_INFO("kd_spin diag overflow=%lld\n",
		   (long long)overflow);
	KD_PR_INFO("kd_spin diag invariant_failures=%lld\n",
		   (long long)invariant_failures);
	for (i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
		struct kd_spin_diag_slot *slot = &kd_spin_diag_slots[i];
		struct kd_spin_diag_counts sum;
		unsigned long addr =
			(unsigned long)atomic_long_read(&slot->addr);

		if (!addr)
			continue;
		kd_spin_diag_sum(i, &sum);
		KD_PR_INFO(
			"kd_spin lock stats: lock=%lx depth=%d slowpath=%lld "
			"combiner=%lld jit_success=%lld jit_not_ready=%lld "
			"nested_lock=%lld "
			"nested_unlock=%lld nested_remote=%lld "
			"native_fallback=%lld ooo_unlock=%lld "
			"jit_disabled=%d waiters=%lld\n",
			addr, sum.max_depth,
			(long long)sum.event[KD_SPIN_DIAG_SLOWPATH],
			(long long)sum.event[KD_SPIN_DIAG_COMBINER],
			(long long)sum.event[KD_SPIN_DIAG_JIT_SUCCESS],
			(long long)sum.event[KD_SPIN_DIAG_JIT_NOT_READY],
			(long long)sum.event[KD_SPIN_DIAG_NESTED_LOCK],
			(long long)sum.event[KD_SPIN_DIAG_NESTED_UNLOCK],
			(long long)sum.event[KD_SPIN_DIAG_NESTED_REMOTE],
			(long long)sum.event[KD_SPIN_DIAG_NATIVE_FALLBACK],
			(long long)sum.event[KD_SPIN_DIAG_OOO_UNLOCK],
			atomic_read(&slot->jit_disabled),
			(long long)(sum.waiter_enter - sum.waiter_exit));
	}

	kd_spinlock_free_percpu();
}
