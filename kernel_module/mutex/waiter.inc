// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Queue waiting and nested native acquisition; preserve owner/ACK semantics.
 * Private implementation included only by kd_mutex.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* --------------------------------------------------------------------------
 * Slowpath: queue as waiter, spin, possibly become combiner
 * -------------------------------------------------------------------------- */
/* Local and captured requests have one completely linked publication.
 * The physical helper consumes this same membership on its ready grant. */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
__kd_mutex_lock_slowpath(struct kd_mutex *lock, int tail,
			 struct kd_mutex_node *curr_node)
{
	struct kd_mutex_node *next_node = NULL;
	struct kd_mutex_cpu_state *ptr = this_cpu_ptr(&kd_mutex_shadows);
	(void)tail;
	curr_node->queued_at_ns = kd_exe_queue_timing_start();
	kd_mutex_waiter_enter(lock, curr_node);
	kd_mutex_queue_publish(lock, curr_node);

	{

		mutex_debug("Mutex waiter spinning\n");
	wait_again:
		kd_mutex_wait_for_result(curr_node);
		if (unlikely(READ_ONCE(curr_node->native_resume))) {
			if (READ_ONCE(curr_node->native_resume) == KD_MUTEX_RESUME_INSTRUCTION) {
				kd_mutex_origin_instruction_waiter(curr_node);
				goto wait_again;
			}
			BUG_ON(READ_ONCE(curr_node->native_resume) != KD_MUTEX_RESUME_NATIVE);
			WRITE_ONCE(ptr->resume_node, curr_node);
			kd_mutex_waiter_exit(lock, curr_node);
			return 5;
		}

		/* CS was processed by combiner via JIT sandbox → done */
		if (curr_node->completed) {
			WRITE_ONCE(ptr->resume_node, curr_node);
			kd_mutex_waiter_exit(lock, curr_node);
			return 3;
		}
		/* Fall through: become combiner */
	}

	/* --- become lock holder / combiner --- */
	kd_mutex_wait_and_lock_node(lock, curr_node);
	/* End at physical acquisition, before processing another waiter's CS. */
	kd_exe_queue_timing_end(true, &curr_node->queued_at_ns,
				kd_exe_queue_timing_start());

	next_node = kd_mutex_queue_start_batch(lock);
	if (!next_node)
		goto release;

	/* --- combiner path --- */
	kd_mutex_run_combiner(lock, next_node);

	BUG_ON(kd_mutex_gate_read(lock) != KD_MUTEX_GATE_HELD);

release:
	kd_mutex_waiter_exit(lock, curr_node);
	return 2;
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Slowpath entry: init node, queue, may become combiner
 * -------------------------------------------------------------------------- */
__attribute__((noipa)) noinline notrace static int
kd_mutex_lock_slowpath(struct kd_mutex *lock, struct kd_mutex_node *curr_node)
{
	this_cpu_inc(kd_mutex_slowpath_count);
	return __kd_mutex_lock_slowpath(lock, curr_node->tail, curr_node);
}

int kd_mutex_nested_lock(struct kd_mutex *lock)
{
	if (WARN_ON_ONCE(!lock || irqs_disabled()))
		return -EINVAL;
	if (kd_origin_mutex_owned(lock, current))
		return -EDEADLK;

	this_cpu_inc(kd_mutex_nested_lock_count);
	/* A owns this CPU's frame stack across scheduling. The active-task
	 * registry routes unrelated reentrant acquisitions to local KD execution. */
	preempt_enable();
	if (kd_mutex_trylock(lock)) {
		this_cpu_inc(kd_mutex_nested_fast_count);
	} else {
		this_cpu_inc(kd_mutex_nested_queued_count);
		atomic_inc(&kd_mutex_nested_waiters);
		kd_origin_mutex_lock(lock);
		atomic_dec(&kd_mutex_nested_waiters);
	}
	preempt_disable();
	BUG_ON(!kd_origin_mutex_owned(lock, current));
	return 0;
}

int kd_mutex_nested_unlock(struct kd_mutex *lock)
{
	kd_origin_mutex_unlock(lock, _RET_IP_);
	this_cpu_inc(kd_mutex_nested_unlock_count);
	return 0;
}

/* Called only when translated execution reaches B's unlock, not by a native
 * continuation. This proves the sandbox resumed after the native acquisition. */
void kd_mutex_note_nested_jit(void)
{
	this_cpu_inc(kd_mutex_nested_jit_count);
}

void kd_mutex_note_nested_abort_release(void)
{
	this_cpu_inc(kd_mutex_nested_abort_release_count);
}
