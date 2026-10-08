/* SPDX-License-Identifier: GPL-2.0 */
/* Original six-register mutex trampoline and public acquisition; preserve CALL/RSP and preemption pairing. */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void
__komb_mutex_lock(struct komb_mutex *lock)
{
	register int ret_val;
	asm volatile("pushq %%rbp\n"
		     "pushq %%rbx\n"
		     "pushq %%r12\n"
		     "pushq %%r13\n"
		     "pushq %%r14\n"
		     "pushq %%r15\n"
		     :
		     :
		     : "memory");
	asm volatile("callq %P0\n"
		     "movq %%rsp, %c1(%%rax)\n"
		     :
		     : "i"(get_komb_mutex_node),
		       "i"(offsetof(struct komb_mutex_node, rsp))
		     : "memory");
	asm volatile("callq %P0\n"
		     "movq (%%rax), %%rsp\n"
		     "pushq %%rdi\n"
		     :
		     : "i"(get_shadow_stack_ptr)
		     : "memory");

	ret_val = komb_mutex_lock_slowpath(lock);
	if (ret_val) {
		asm volatile("popq %%rdi\n"
			     "callq %P0\n"
			     "movq (%%rax), %%rsp\n"
			     "popq %%r15\n"
			     "popq %%r14\n"
			     "popq %%r13\n"
			     "popq %%r12\n"
			     "popq %%rbx\n"
			     "popq %%rbp\n"
			     "retq\n"
			     :
			     : "i"(get_shadow_stack_ptr)
			     : "memory");
	} else {
		asm volatile("popq %%rdi\n"
			     "callq %P0\n"
			     "movq %%rsp, (%%rax)\n"
			     :
			     : "i"(get_shadow_stack_ptr)
			     : "memory");
		asm volatile("callq %P0\n"
			     "movq %c1(%%rax), %%rsp\n"
			     :
			     : "i"(get_komb_mutex_node),
			       "i"(offsetof(struct komb_mutex_node, rsp))
			     : "memory");
		asm volatile("popq %%r15\n"
			     "popq %%r14\n"
			     "popq %%r13\n"
			     "popq %%r12\n"
			     "popq %%rbx\n"
			     "popq %%rbp\n"
			     "retq\n"
			     :
			     :
			     : "memory");
	}
}
#pragma GCC pop_options

__attribute__((noipa)) noinline notrace void
komb_mutex_lock(struct komb_mutex *lock)
{
	int ret;

	ret = cmpxchg(&lock->locked, 0, 1);
	if (likely(ret == 0)) {

		return;
	}

	preempt_disable();
	struct komb_mutex_node *curr_node = get_komb_mutex_node(lock);
	curr_node->socket_id = numa_node_id();

	__komb_mutex_lock(lock);

	if (tc_mutex_current()->komb_curr_waiter_task) {
		struct komb_mutex_node *curr_node =
			tc_mutex_task(tc_mutex_current()->komb_curr_waiter_task)->komb_mutex_node;

		if ((struct komb_mutex *)curr_node->lock == lock) {
#ifdef DEBUG_KOMB
			BUG_ON(lock->locked != _Q_LOCKED_COMBINER_VAL);
#endif
			struct komb_mutex_node *next_node =
				get_next_node(curr_node);
			if (next_node == NULL)
				tc_mutex_current()->komb_next_waiter_task = NULL;
			else
				tc_mutex_current()->komb_next_waiter_task =
					next_node->task_struct_ptr;
		}

		wake_up_waiter(curr_node);

		if (tc_mutex_current()->komb_prev_waiter_task) {
			struct komb_mutex_node *prev_node =
				tc_mutex_task(tc_mutex_current()->komb_prev_waiter_task)->komb_mutex_node;

#ifdef DEBUG_KOMB
			BUG_ON(prev_node->lock != lock);
#endif
			print_debug("Waking up prev waiter: %d\n", prev_node->cpuid);
			wake_up_waiter(prev_node);
			clear_locked_set_completed(prev_node);
			tc_mutex_current()->komb_prev_waiter_task = NULL;
		}
	}

	preempt_enable();
}
