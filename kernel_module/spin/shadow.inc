// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Nested lock-vector push/pop, saved combiner state and invariant checks.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static inline unsigned int
kd_spin_lock_stack_depth(const struct shadow_stack *ptr)
{
	unsigned int depth = 0;

	while (depth < ARRAY_SIZE(ptr->lock_addr) &&
	       READ_ONCE(ptr->lock_addr[depth]) != 0)
		depth++;

	return depth;
}

bool kd_spin_nested_shadow_has_space(void)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);

	return kd_spin_lock_stack_depth(ptr) < ARRAY_SIZE(ptr->lock_addr);
}

/* Register a nested lock ownership record for this CPU's combiner stack.
 * The stack is used to validate outer-unlock ordering and out-of-order unlock
 * checks during delegated nested execution.
 */
int kd_spin_nested_shadow_push(struct qspinlock *lock)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	unsigned int depth;

	if (!lock)
		return -EINVAL;

	depth = kd_spin_lock_stack_depth(ptr);
	if (depth >= ARRAY_SIZE(ptr->lock_addr))
		return -E2BIG;

	if (kd_exec_frame_lock_depth(kd_exec_current_frame()) &&
	    kd_exec_frame_lock_contains(kd_exec_current_frame(),
					(unsigned long)lock))
		return -EDEADLK;

	WRITE_ONCE(ptr->lock_addr[depth], (uint64_t)lock);
	kd_spin_diag_validate_lock_stack(ptr);
	return 0;
}

/* Remove one lock from the nested shadow stack, allowing arbitrary hole compaction.
 * This keeps lock addresses topologically ordered in lock-depth tracking.
 */
int kd_spin_nested_shadow_remove(struct qspinlock *lock)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	unsigned int depth, i;

	if (!lock)
		return -EINVAL;

	depth = kd_spin_lock_stack_depth(ptr);
	for (i = 0; i < depth; i++) {
		if (ptr->lock_addr[i] != (uint64_t)lock)
			continue;

		for (; i + 1 < depth; i++)
			ptr->lock_addr[i] = ptr->lock_addr[i + 1];
		ptr->lock_addr[depth - 1] = 0;
		kd_spin_diag_validate_lock_stack(ptr);
		return 0;
	}

	return -ENOENT;
}

/* Pop requires exact top-of-stack match; used when this lock is the current
 * nesting boundary being released.
 */
static int kd_spin_nested_shadow_pop(struct qspinlock *lock)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	unsigned int depth;

	if (!lock)
		return -EINVAL;
	depth = kd_spin_lock_stack_depth(ptr);
	if (!depth || ptr->lock_addr[depth - 1] != (uint64_t)lock)
		return -EINVAL;
	return kd_spin_nested_shadow_remove(lock);
}

static void kd_spin_capture_combiner_state(struct kd_combiner_state *saved,
					   const struct shadow_stack *ptr)
{
	unsigned int i;

	for (i = 0; i < KD_EXEC_MAX_LOCK_DEPTH; i++)
		saved->lock_addr[i] = READ_ONCE(ptr->lock_addr[i]);
	saved->lock_depth = kd_spin_lock_stack_depth(ptr);
	saved->curr_cs_cpu = ptr->curr_cs_cpu;
	saved->prev_cs_cpu = ptr->prev_cs_cpu;
	saved->local_shadow_stack_ptr = ptr->local_shadow_stack_ptr;
#ifdef NUMA_AWARE
	saved->local_queue_head = ptr->local_queue_head;
	saved->local_queue_tail = ptr->local_queue_tail;
#else
	saved->local_queue_head = NULL;
	saved->local_queue_tail = NULL;
#endif
	saved->irqs_disabled = ptr->irqs_disabled;
}

static bool
kd_spin_combiner_state_matches(const struct kd_combiner_state *saved,
			       const struct shadow_stack *ptr)
{
	unsigned int i;

	if (!saved || !ptr ||
	    saved->lock_depth != kd_spin_lock_stack_depth(ptr) ||
	    saved->curr_cs_cpu != ptr->curr_cs_cpu ||
	    saved->prev_cs_cpu != ptr->prev_cs_cpu ||
	    saved->local_shadow_stack_ptr != ptr->local_shadow_stack_ptr ||
	    saved->irqs_disabled != ptr->irqs_disabled)
		return false;
#ifdef NUMA_AWARE
	if (saved->local_queue_head != ptr->local_queue_head ||
	    saved->local_queue_tail != ptr->local_queue_tail)
		return false;
#endif
	for (i = 0; i < KD_EXEC_MAX_LOCK_DEPTH; i++) {
		if (saved->lock_addr[i] != READ_ONCE(ptr->lock_addr[i]))
			return false;
	}
	return true;
}

void kd_spin_jit_prepare_complex(struct kd_exec_frame *frame)
{
	/* Before the first service/control exit only translated waiter code has
	 * run; it has not changed this executor's combiner metadata. Capture now,
	 * before nested acquisition, hostcall or native/remote publication. */
	if (frame->spin_simple) {
		kd_exec_frame_prepare_complex(frame);
		kd_exec_frame_own_regs(frame);
		kd_spin_capture_combiner_state(&frame->saved_combiner,
					       this_cpu_ptr(&local_shadow_stack));
		frame->spin_simple = false;
	}
}

static __always_inline void kd_spin_diag_invariant_failure(void)
{
	this_cpu_inc(kd_spin_diag_cpu->invariant_failures);
	WARN_ON_ONCE(1);
}

static void kd_spin_diag_validate_lock_stack(const struct shadow_stack *ptr)
{
	bool hole_seen = false;
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(ptr->lock_addr); i++) {
		if (READ_ONCE(ptr->lock_addr[i]) != 0) {
			if (hole_seen)
				kd_spin_diag_invariant_failure();
		} else {
			hole_seen = true;
		}
	}
}

/* Verify a candidate unlock matches the latest expected nesting index.
 * Detects accidental reordering before mutating spin/qspin states.
 */
static void kd_spin_diag_validate_outer_unlock(const struct shadow_stack *ptr,
					       struct qspinlock *lock,
					       struct qspinlock *word, int my_idx, int max_idx)
{
	if (my_idx < 0)
		return;

	if (my_idx > max_idx ||
	    ptr->lock_addr[my_idx] != (uint64_t)(unsigned long)lock)
		kd_spin_diag_invariant_failure();

	if (my_idx == max_idx &&
	    READ_ONCE(word->locked) != _Q_LOCKED_COMBINER_VAL)
		kd_spin_diag_invariant_failure();
}
