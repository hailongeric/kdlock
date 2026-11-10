/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_SOURCE_STACK_H
#define KDLOCK_SOURCE_STACK_H

#include "state.h"

struct task_struct;

/* Retained original kernel-stack storage, never a continuation or packet copy.
 * The active source actor serializes each word operation with every other
 * source/native actor. Residency does not give this record execution rights or
 * permit a task to exit while its live continuation still has users. This
 * record and callback backing stay outside source/auxiliary stacks and survive
 * every actor/observer; acquiring a stack hold does not retain this header.
 */
struct kd_source_stack {
	struct kd_source_stack_ops ops;
	struct task_struct *task;
	unsigned long low;
	unsigned long high;
	bool held;
};

/* Fresh private record on current, before source admission. Acquire a distinct
 * task reference and try_get_task_stack() hold. Success initializes exact
 * [low, high) bounds and synchronous single-word callbacks. Failure transfers
 * no hold and leaves the record untouched. The callbacks require an aligned
 * word entirely inside those bounds, retained record backing and the sole
 * source actor; they provide no arbitrary-address fault or fixup mechanism.
 */
int kd_source_stack_acquire_current(struct kd_source_stack *stack);

/* Parent-owned fresh child after dup_task_struct and before ANY publication,
 * execution or escaped observer. This acquires the CHILD stack/task, never
 * current's stack. Caller exclusively owns construction/failure cleanup.
 */
int kd_source_stack_acquire_unpublished(struct kd_source_stack *stack,
				       struct task_struct *child);

/* Serialized final use of a successfully acquired record, after every callback
 * and borrowed/native stack observer ended. Invalidate callbacks/metadata before
 * put_task_stack()/put_task_struct(); no record or stack access follows those
 * releases. Header/caller code must survive return. This is not a drain wait.
 */
void kd_source_stack_release(struct kd_source_stack *stack);

#endif
