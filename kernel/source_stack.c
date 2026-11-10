// SPDX-License-Identifier: GPL-2.0-only
/* Exact retained original-stack words for the current source actor. */
#include <linux/bug.h>
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/overflow.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/sched/task_stack.h>

#include "source_stack.h"

static unsigned long *stack_word(struct kd_source_stack *stack,
				unsigned long address)
{
	BUG_ON(!stack->held || (address & (sizeof(unsigned long) - 1)) ||
	       address < stack->low || address > stack->high - sizeof(unsigned long));
	return (unsigned long *)address;
}

static unsigned long read_word(void *context, unsigned long address)
{
	return READ_ONCE(*stack_word(context, address));
}

static void write_word(void *context, unsigned long address, unsigned long value)
{
	WRITE_ONCE(*stack_word(context, address), value);
}

static int acquire_stack(struct kd_source_stack *stack, struct task_struct *task)
{
	unsigned long low, high;
	void *base;

	if (!stack || !task)
		return -EINVAL;
	/* Linux v7.0 sched/task_stack.h names this try_get_task_stack(). */
	base = try_get_task_stack(task);
	if (!base)
		return -ESRCH;
	low = (unsigned long)base;
	if (!low || check_add_overflow(low, (unsigned long)THREAD_SIZE, &high) ||
	    high - low < sizeof(unsigned long)) {
		put_task_stack(task);
		return -EOVERFLOW;
	}
	get_task_struct(task);
	stack->task = task;
	stack->low = low;
	stack->high = high;
	stack->held = true;
	stack->ops.read_word = read_word;
	stack->ops.write_word = write_word;
	stack->ops.context = stack;
	return 0;
}

int kd_source_stack_acquire_current(struct kd_source_stack *stack)
{
	return acquire_stack(stack, current);
}

int kd_source_stack_acquire_unpublished(struct kd_source_stack *stack,
				       struct task_struct *child)
{
	if (!child || child == current)
		return -EINVAL;
	return acquire_stack(stack, child);
}

void kd_source_stack_release(struct kd_source_stack *stack)
{
	struct task_struct *task;

	BUG_ON(!stack || !stack->held);
	task = stack->task;
	stack->held = false;
	stack->task = NULL;
	stack->low = 0;
	stack->high = 0;
	stack->ops.read_word = NULL;
	stack->ops.write_word = NULL;
	stack->ops.context = NULL;
	/* Caller drained all users; no record/stack access follows either put. */
	put_task_stack(task);
	put_task_struct(task);
}
