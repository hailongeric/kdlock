// SPDX-License-Identifier: GPL-2.0-only
/* Task-owned auxiliary reservation for the original-backend root prefix. */
#include <linux/bug.h>
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/sched/task_stack.h>
#include <asm/page.h>

#include "jit.h"
#include "native_entry.h"

static bool overlaps(unsigned long low, unsigned long high,
		     unsigned long other_low, unsigned long other_high)
{
	return low < other_high && other_low < high;
}

static bool outside_stacks(const struct kd_mutex_entry *entry,
			   const void *object, unsigned long bytes)
{
	unsigned long low = (unsigned long)object;
	unsigned long high = low + bytes;

	return high >= low &&
	       !overlaps(low, high, entry->source_low, entry->source_high) &&
	       !overlaps(low, high, entry->control_low, entry->control_high);
}

static bool native_owned(struct kd_task_root_context *root,
			 struct kd_execution_binding *binding)
{
	return root && root->attached && root->task == current &&
	       kd_state_is_current(&root->core, binding) &&
	       binding->kind == KD_EXECUTION_NATIVE && root->core.origin == current;
}

int kd_mutex_prepare_entry(struct kd_mutex_entry *entry,
		 struct kd_execution_binding *native_binding,
		 kd_mutex_entry_run_fn run, void *context,
		 unsigned long required_control_bytes)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	unsigned long source_low, source_high, source_sp;
	struct kd_mutex_entry candidate;

	if (!entry || !run || required_control_bytes < sizeof(unsigned long))
		return -EINVAL;
	if (!in_task() || in_atomic() || irqs_disabled())
		return -EWOULDBLOCK;
	if (!native_owned(root, native_binding))
		return -EPERM;
	if (root->aux_entry || root->core.exit_image || root->core.exit_use ||
	    root->core.exit_holder ||
	    (root->core.operation.phase != KD_OPERATION_IDLE &&
	     root->core.operation.phase != KD_OPERATION_RESUMABLE))
		return -EBUSY;
	source_low = (unsigned long)task_stack_page(current);
	source_high = source_low + THREAD_SIZE;
	asm volatile("movq %%rsp, %0" : "=r"(source_sp));
	if (!source_low || source_high <= source_low ||
	    source_sp < source_low + sizeof(unsigned long) || source_sp > source_high ||
	    root->aux_low >= root->aux_high || root->aux_current <= root->aux_low ||
	    root->aux_current > root->aux_high || (root->aux_current & 15) ||
	    required_control_bytes > root->aux_current - root->aux_low ||
	    overlaps(source_low, source_high, root->aux_low, root->aux_high))
		return -EINVAL;

	/* Construct only the small descriptor. No canonical source packet is
	 * copied or cleared; its declared inputs arrive after the stack switch.
	 */
	candidate.control_top = root->aux_current;
	candidate.run = run;
	candidate.task = current;
	candidate.control_low = root->aux_low;
	candidate.control_high = root->aux_high;
	candidate.source_low = source_low;
	candidate.source_high = source_high;
	candidate.context = context;
	candidate.phase = KD_MUTEX_ENTRY_PREPARED;
	if (!outside_stacks(&candidate, entry, sizeof(*entry)) ||
	    !outside_stacks(&candidate, root, sizeof(*root)) ||
	    !outside_stacks(&candidate, native_binding, sizeof(*native_binding)))
		return -EINVAL;
	/* Only current mutates its task-owned reservation. No registry or source
	 * executor lookup is involved; borrowed execution uses node->state.
	 */
	*entry = candidate;
	WRITE_ONCE(root->aux_entry, entry);
	return 0;
}

int kd_mutex_cancel_entry(struct kd_mutex_entry *entry,
		 struct kd_execution_binding *native_binding)
{
	struct kd_task_root_context *root = kd_task_root_context_current();

	if (!in_task() || in_atomic() || irqs_disabled())
		return -EWOULDBLOCK;
	if (!native_owned(root, native_binding))
		return -EPERM;
	if (!entry || root->aux_entry != entry || entry->task != current ||
	    entry->phase != KD_MUTEX_ENTRY_PREPARED)
		return -ESTALE;
	/* Before the prefix only: caller excludes an active/abandoned callback.
	 * Native binding identity alone cannot prove this private control phase.
	 */
	entry->phase = KD_MUTEX_ENTRY_PRIVATE;
	WRITE_ONCE(root->aux_entry, NULL);
	return 0;
}

extern void __noreturn kd_native_resume(struct kd_regs *regs);

void __noreturn kd_mutex_resume_entry(struct kd_mutex_entry *entry,
		 struct kd_execution_binding *native_binding,
		 void (*done)(void *context), void *context)
{
	struct kd_task_root_context *root = kd_task_root_context_current();
	struct kd_thread_state *state;

	BUG_ON(!in_task() || in_atomic() || irqs_disabled());
	BUG_ON(!native_owned(root, native_binding));
	BUG_ON(!entry || root->aux_entry != entry || entry->task != current ||
	       entry->control_top != root->aux_current ||
	       entry->phase != KD_MUTEX_ENTRY_ENTERED);
	BUG_ON(!outside_stacks(entry, native_binding, sizeof(*native_binding)));
	state = &root->core;
	BUG_ON(state->exit_image || state->exit_use || state->exit_holder ||
	       (state->operation.phase != KD_OPERATION_IDLE &&
		state->operation.phase != KD_OPERATION_RESUMABLE));
	BUG_ON(state->regs.sp < entry->source_low + sizeof(unsigned long) ||
	       state->regs.sp > entry->source_high);
	/* This task cannot enter another source prefix until the final jump.
	 * IRQ/atomic entry is outside this ordinary-task lane. No C return may
	 * reclaim the abandoned auxiliary frames after canonical native resume.
	 */
	entry->phase = KD_MUTEX_ENTRY_COMPLETE;
	WRITE_ONCE(root->aux_entry, NULL);
	/* Final entry/native-binding access ended above. The exact actor cleanup
	 * can permit control reuse; only stable task-core regs are read afterward.
	 */
	if (done)
		done(context);
	kd_native_resume(&state->regs);
}
