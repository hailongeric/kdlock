// SPDX-License-Identifier: GPL-2.0
/*
 * Stack allocation is CPU-local and bounded. Retired holes below a live top
 * are not reused or moved. Acquire retired before overwriting remote storage.
 */
static void kd_spin_continuation_collapse(struct kd_spin_continuation_stack *stack)
{
	while (stack->top &&
	       smp_load_acquire(&stack->records[stack->top - 1].retired))
		stack->top--;
}

static struct kd_spin_continuation *kd_spin_continuation_reserve(void)
{
	struct kd_spin_continuation_stack *stack =
		*this_cpu_ptr(&kd_spin_continuations);
	struct kd_spin_continuation *record;

	if (!stack)
		return NULL;
	kd_spin_continuation_collapse(stack);
	if (stack->top == KD_SPIN_CONT_SLOTS)
		return NULL;
	record = &stack->records[stack->top++];
	record->storage = stack;
	record->retired = false;
	return record;
}

static void kd_spin_continuation_release(struct kd_spin_continuation *record)
{
	struct kd_spin_continuation_stack *stack = record->storage;

	BUG_ON(stack != *this_cpu_ptr(&kd_spin_continuations) ||
	       record->retired);
	smp_store_release(&record->retired, true);
	kd_spin_continuation_collapse(stack);
}
