/* SPDX-License-Identifier: GPL-2.0 */
/* Parking CAS, wakeup and registered context access; keep task references through wake completion. */
static inline void schedule_out_curr_task(void)
{
	preempt_enable();
	schedule();
	preempt_disable();
}

static inline void park_waiter(struct komb_mutex_node *node)
{
	__set_current_state(TASK_INTERRUPTIBLE);

	if (cmpxchg(&node->completed, KOMB_WAITER_UNPROCESSED,
		    KOMB_WAITER_PARKED) != KOMB_WAITER_UNPROCESSED) {
		__set_current_state(TASK_RUNNING);
		return;
	}
	tc_mutex_current()->parks++;
	schedule_out_curr_task();
	__set_current_state(TASK_RUNNING);
}

static inline void wake_up_waiter(struct komb_mutex_node *node)
{
	u8 old_val = xchg(&node->completed, KOMB_WAITER_PROCESSING);

	if (old_val == KOMB_WAITER_PARKED) {
		struct task_struct *task = node->task_struct_ptr;
		get_task_struct(task);
		wake_up_process(task);
		put_task_struct(task);
	}
}

void komb_mutex_init(struct komb_mutex *lock)
{
	lock->tail = NULL;
	atomic_set(&lock->state, 0);
	lock->combiner_task = NULL;
}

static __always_inline void
clear_locked_set_completed(struct komb_mutex_node *node)
{
	WRITE_ONCE(node->completed, KOMB_WAITER_PROCESSED);
	WRITE_ONCE(node->locked, 0);
}

static __always_inline void set_locked(struct komb_mutex *lock)
{
	WRITE_ONCE(lock->locked, 1);
}

/*
 * lock -> rdi
 */
__attribute__((noipa)) noinline notrace static void *
get_shadow_stack_ptr(struct komb_mutex *lock)
{
	return &tc_mutex_current()->komb_stack_curr_ptr;
}

__attribute__((noipa)) noinline notrace static struct komb_mutex_node *
get_komb_mutex_node(struct komb_mutex *lock)
{
	return ((struct komb_mutex_node *)(tc_mutex_current()->komb_mutex_node));
}
