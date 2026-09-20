// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Gate initialization, per-CPU stack allocation, rollback and drained teardown.
 * Private implementation included only by kd_mutex.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

void kd_mutex_init(struct kd_mutex *lock)
{
	lock->tail = 0;
	atomic_set(&lock->state, 0);
	lock->physical_owner = NULL;
	lock->origin_mutex_addr = 0;
	atomic_set(&lock->waiter_count, 0);
}

static void kd_mutex_free_percpu_stacks(void)
{
	int cpu;

	for_each_possible_cpu(cpu) {
		struct kd_mutex_cpu_state *shadow =
			per_cpu_ptr(&kd_mutex_shadows, cpu);
		int slot;

		for (slot = 0; slot < KD_MUTEX_MAX_NODES; slot++) {
			struct kd_mutex_node *node =
				per_cpu_ptr(&kd_mutex_nodes[slot], cpu);

			vfree(node->shadow_stack_base);
			node->shadow_stack_base = NULL;
			node->shadow_stack_ptr = 0;
		}
		shadow->node_slots = 0;
		shadow->resume_node = NULL;
	}
}

int kd_mutex_init_percpu(void)
{
	int i, j;

	/* Per-CPU alignment alone does not isolate the four array elements. */
	BUILD_BUG_ON(__alignof__(struct kd_mutex_node) < L1_CACHE_BYTES);
	BUILD_BUG_ON(sizeof(struct kd_mutex_node) != 4 * L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_mutex_node, completed) != L1_CACHE_BYTES);
	BUILD_BUG_ON(offsetof(struct kd_mutex_node, locked) != L1_CACHE_BYTES + 1);

	atomic64_set(&kd_mutex_slowpath_count, 0);
	atomic64_set(&kd_mutex_combiner_count, 0);
	atomic64_set(&kd_mutex_handoff_count, 0);
	atomic64_set(&kd_mutex_jit_success_count, 0);
	atomic64_set(&kd_mutex_jit_not_ready_count, 0);
	atomic64_set(&kd_mutex_jit_failure_count, 0);
	atomic64_set(&kd_mutex_jit_resume_count, 0);
	atomic64_set(&kd_mutex_frame_failure_count, 0);
	atomic64_set(&kd_mutex_node_overflow_count, 0);
	atomic64_set(&kd_mutex_multi_slot_count, 0);
	atomic64_set(&kd_mutex_context_busy_count, 0);
	atomic64_set(&kd_mutex_nested_lock_count, 0);
	atomic64_set(&kd_mutex_nested_fast_count, 0);
	atomic64_set(&kd_mutex_nested_queued_count, 0);
	atomic64_set(&kd_mutex_nested_jit_count, 0);
	atomic64_set(&kd_mutex_origin_acquires, 0);
	atomic64_set(&kd_mutex_origin_releases, 0);
	atomic64_set(&kd_mutex_nested_unlock_count, 0);
	atomic64_set(&kd_mutex_nested_abort_release_count, 0);
	atomic_set(&kd_mutex_active_waiters, 0);
	atomic_set(&kd_mutex_max_waiters, 0);
	atomic_set(&kd_mutex_reserved_nodes, 0);

	for_each_possible_cpu(i) {
		struct kd_mutex_cpu_state *p = per_cpu_ptr(&kd_mutex_shadows, i);

		memset(per_cpu_ptr(&kd_mutex_nodes[0], i), 0,
		       sizeof(struct kd_mutex_node) * KD_MUTEX_MAX_NODES);
		memset(p, 0, sizeof(*p));
		p->node_slots = 0;
		p->resume_node = NULL;
		for (j = 0; j < KD_MUTEX_MAX_NODES; j++) {
			struct kd_mutex_node *node =
				per_cpu_ptr(&kd_mutex_nodes[j], i);
			void *node_stack = vzalloc(KD_MUTEX_SHADOW_STACK_SIZE);

			node->slot = j;
			node->shadow_stack_base = node_stack;
			if (!node_stack) {
				KD_PR_ERR(
					"kd_mutex: waiter stack allocation failed on cpu %d slot %d\n",
					i, j);
				goto err_free;
			}
			node->shadow_stack_ptr =
				(uint64_t)((char *)node_stack +
					   KD_MUTEX_SHADOW_STACK_SIZE - 8);
		}
	}

	return 0;

err_free:
	kd_mutex_free_percpu_stacks();
	return -ENOMEM;
}

bool kd_mutex_check_idle(void)
{
	return !atomic_read(&kd_mutex_active_waiters) &&
	       !atomic_read(&kd_mutex_reserved_nodes);
}

void kd_mutex_exit(void)
{
	int i;

	KD_PR_INFO(
		"kd_mutex stats: slowpath=%lld combiner=%lld handoff=%lld "
		"jit_success=%lld jit_not_ready=%lld jit_failure=%lld "
		"jit_resume=%lld frame_failure=%lld node_overflow=%lld "
		"multi_slot=%lld context_busy=%lld nested_lock=%lld "
		"nested_fast=%lld nested_queued=%lld nested_jit=%lld "
		"nested_unlock=%lld nested_abort_release=%lld "
		"active_waiters=%d max_waiters=%d "
		"reserved_nodes=%d origin_acquires=%lld origin_releases=%lld\n",
		(long long)atomic64_read(&kd_mutex_slowpath_count),
		(long long)atomic64_read(&kd_mutex_combiner_count),
		(long long)atomic64_read(&kd_mutex_handoff_count),
		(long long)atomic64_read(&kd_mutex_jit_success_count),
		(long long)atomic64_read(&kd_mutex_jit_not_ready_count),
		(long long)atomic64_read(&kd_mutex_jit_failure_count),
		(long long)atomic64_read(&kd_mutex_jit_resume_count),
		(long long)atomic64_read(&kd_mutex_frame_failure_count),
		(long long)atomic64_read(&kd_mutex_node_overflow_count),
		(long long)atomic64_read(&kd_mutex_multi_slot_count),
		(long long)atomic64_read(&kd_mutex_context_busy_count),
		(long long)atomic64_read(&kd_mutex_nested_lock_count),
		(long long)atomic64_read(&kd_mutex_nested_fast_count),
		(long long)atomic64_read(&kd_mutex_nested_queued_count),
		(long long)atomic64_read(&kd_mutex_nested_jit_count),
		(long long)atomic64_read(&kd_mutex_nested_unlock_count),
		(long long)atomic64_read(&kd_mutex_nested_abort_release_count),
		atomic_read(&kd_mutex_active_waiters),
		atomic_read(&kd_mutex_max_waiters),
		atomic_read(&kd_mutex_reserved_nodes),
		(long long)atomic64_read(&kd_mutex_origin_acquires),
		(long long)atomic64_read(&kd_mutex_origin_releases));

	for_each_possible_cpu(i) {
		struct kd_mutex_cpu_state *p = per_cpu_ptr(&kd_mutex_shadows, i);

		if (READ_ONCE(p->node_slots))
			KD_PR_ERR("kd_mutex: cpu %d leaked waiter slots=%lx\n",
				  i, READ_ONCE(p->node_slots));
	}
	kd_mutex_free_percpu_stacks();
}
