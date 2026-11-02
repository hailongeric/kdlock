/* SPDX-License-Identifier: GPL-2.0 */
/* Native task observations are separate from translated scalar body effects. */
#include <linux/rcupdate.h>
#include <linux/spinlock.h>

static DEFINE_RAW_SPINLOCK(helper_native_lock);
static struct jit_native_event helper_native_events[JIT_NATIVE_EVENTS];
static u64 helper_native_count, helper_native_body_after;

static unsigned int helper_native_rcu_depth(void)
{
#ifdef CONFIG_PREEMPT_RCU
	return READ_ONCE(current->rcu_read_lock_nesting);
#else
	return 0;
#endif
}

static struct jit_native_event *helper_native_begin(unsigned int operation)
{
	u64 index = READ_ONCE(helper_native_count);
	struct jit_native_event *event;
	unsigned long stack_marker;

	if (index >= JIT_NATIVE_EVENTS) {
		atomic_inc(&failures);
		return NULL;
	}
	event = &helper_native_events[index];
	event->operation = operation;
	event->pid = current->pid;
	event->stack_address = (unsigned long)&stack_marker;
	event->preempt_before = preempt_count();
	event->rcu_before = helper_native_rcu_depth();
	event->irqs_before = irqs_disabled();
	if (current->pid != READ_ONCE(killable_slots[1].pid) ||
	    READ_ONCE(helper_slots[1].origin_stack) != (unsigned long)task_stack_page(current) ||
	    (unsigned long)&stack_marker < (unsigned long)task_stack_page(current) ||
	    (unsigned long)&stack_marker >= (unsigned long)task_stack_page(current) + THREAD_SIZE)
		atomic_inc(&failures);
	return event;
}

static void helper_native_end(struct jit_native_event *event, unsigned long result)
{
	if (!event)
		return;
	event->preempt_after = preempt_count();
	event->rcu_after = helper_native_rcu_depth();
	event->irqs_after = irqs_disabled();
	event->result = result;
	smp_store_release(&helper_native_count, READ_ONCE(helper_native_count) + 1);
}

static __attribute__((noipa)) noinline notrace void
jit_test_native_spin_lock(raw_spinlock_t *lock)
{
	struct jit_native_event *event = helper_native_begin(JIT_NATIVE_SPIN_LOCK);

	raw_spin_lock(lock);
	helper_native_end(event, 0);
}

static __attribute__((noipa)) noinline notrace unsigned long
jit_test_native_spin_try(raw_spinlock_t *lock)
{
	struct jit_native_event *event = helper_native_begin(JIT_NATIVE_SPIN_TRY);
	unsigned long result = raw_spin_trylock(lock);

	helper_native_end(event, result);
	return result;
}

static __attribute__((noipa)) noinline notrace void
jit_test_native_spin_unlock(raw_spinlock_t *lock)
{
	struct jit_native_event *event = helper_native_begin(JIT_NATIVE_SPIN_UNLOCK);

	raw_spin_unlock(lock);
	helper_native_end(event, 0);
}

static __attribute__((noipa)) noinline notrace void jit_test_native_rcu_lock(void)
{
	struct jit_native_event *event = helper_native_begin(JIT_NATIVE_RCU_LOCK);

	rcu_read_lock();
	helper_native_end(event, 0);
}

static __attribute__((noipa)) noinline notrace void jit_test_native_rcu_unlock(void)
{
	struct jit_native_event *event = helper_native_begin(JIT_NATIVE_RCU_UNLOCK);

	rcu_read_unlock();
	helper_native_end(event, 0);
}

static noinline long helper_native_snapshot(void __user *user)
{
	struct jit_native_snapshot state = {
		.version = 1, .count = smp_load_acquire(&helper_native_count),
		.errors = atomic_read(&failures), .lock_address = (unsigned long)&helper_native_lock,
		.body_after = READ_ONCE(helper_native_body_after),
		.stack_low = READ_ONCE(helper_slots[1].origin_stack),
		.stack_high = READ_ONCE(helper_slots[1].origin_stack) + THREAD_SIZE,
	};
	unsigned int i;

	if (state.count > JIT_NATIVE_EVENTS)
		return -EOVERFLOW;
	for (i = 0; i < state.count; ++i) {
#define NATIVE_COPY(name) state.events[i].name = READ_ONCE(helper_native_events[i].name)
		NATIVE_COPY(operation); NATIVE_COPY(pid); NATIVE_COPY(stack_address);
		NATIVE_COPY(preempt_before); NATIVE_COPY(preempt_after);
		NATIVE_COPY(rcu_before); NATIVE_COPY(rcu_after);
		NATIVE_COPY(irqs_before); NATIVE_COPY(irqs_after); NATIVE_COPY(result);
#undef NATIVE_COPY
	}
	return copy_to_user(user, &state, sizeof(state)) ? -EFAULT : 0;
}
