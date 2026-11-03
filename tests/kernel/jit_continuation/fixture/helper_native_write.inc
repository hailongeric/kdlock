/* SPDX-License-Identifier: GPL-2.0 */
/* Native writers retain ownership beyond their returning primitive calls. */
#include <linux/rwsem.h>

static DECLARE_RWSEM(helper_native_write_a);
static DECLARE_RWSEM(helper_native_write_b);
static struct jit_native_write_event helper_native_write_events[JIT_NATIVE_WRITE_EVENTS];
static u64 helper_native_write_count, helper_native_write_body_after;
static u64 helper_native_write_attempts, helper_native_write_grants;
static u64 helper_native_write_progress, helper_native_write_progress_pid, helper_native_write_progress_cpu;

static struct jit_native_write_event *helper_native_write_begin(struct rw_semaphore *sem, unsigned int operation)
{
	u64 index = READ_ONCE(helper_native_write_count);
	struct jit_native_write_event *event;
	unsigned long marker;

	if (index >= JIT_NATIVE_WRITE_EVENTS) {
		atomic_inc(&failures);
		return NULL;
	}
	event = &helper_native_write_events[index];
	event->operation = operation;
	event->object = (unsigned long)sem;
	event->pid = current->pid;
	event->cpu = raw_smp_processor_id();
	event->stack_address = (unsigned long)&marker;
	event->preempt_before = preempt_count();
	event->rcu_before = helper_native_rcu_depth();
	event->irqs_before = irqs_disabled();
	event->switches_before = current->nvcsw + current->nivcsw;
	if (current->pid != READ_ONCE(killable_slots[1].pid) ||
	    READ_ONCE(helper_slots[1].origin_stack) != (unsigned long)task_stack_page(current) ||
	    (unsigned long)&marker < (unsigned long)task_stack_page(current) ||
	    (unsigned long)&marker >= (unsigned long)task_stack_page(current) + THREAD_SIZE ||
	    (sem != &helper_native_write_a && sem != &helper_native_write_b))
		atomic_inc(&failures);
	return event;
}

static void helper_native_write_end(struct jit_native_write_event *event)
{
	if (!event)
		return;
	event->preempt_after = preempt_count();
	event->rcu_after = helper_native_rcu_depth();
	event->irqs_after = irqs_disabled();
	event->switches_after = current->nvcsw + current->nivcsw;
	if (raw_smp_processor_id() != event->cpu)
		atomic_inc(&failures);
	smp_store_release(&helper_native_write_count, READ_ONCE(helper_native_write_count) + 1);
}

static __attribute__((noipa)) noinline notrace void
jit_test_native_write_lock(struct rw_semaphore *sem)
{
	struct jit_native_write_event *event = helper_native_write_begin(sem, 1);

	smp_store_release(&helper_native_write_attempts, READ_ONCE(helper_native_write_attempts) + 1);
	down_write(sem);
	smp_store_release(&helper_native_write_grants, READ_ONCE(helper_native_write_grants) + 1);
	helper_native_write_end(event);
}

static __attribute__((noipa)) noinline notrace void
jit_test_native_write_unlock(struct rw_semaphore *sem)
{
	struct jit_native_write_event *event = helper_native_write_begin(sem, 2);

	up_write(sem);
	helper_native_write_end(event);
}

static void helper_native_write_hold(void)
{
	unsigned long deadline = jiffies + 30 * HZ;

	down_write(&helper_native_write_a);
	atomic64_or(JIT_KILLABLE_RELEASE_NATIVE_WRITE, &killable_holders);
	while (!(READ_ONCE(killable_release) & JIT_KILLABLE_RELEASE_NATIVE_WRITE)) {
		if (time_after(jiffies, deadline)) {
			atomic_inc(&failures);
			break;
		}
		schedule_timeout_uninterruptible(1);
	}
	up_write(&helper_native_write_a);
	atomic64_andnot(JIT_KILLABLE_RELEASE_NATIVE_WRITE, &killable_holders);
}

static void helper_native_write_reset(void)
{
	memset(helper_native_write_events, 0, sizeof(helper_native_write_events));
	WRITE_ONCE(helper_native_write_count, 0);
	WRITE_ONCE(helper_native_write_body_after, 0);
	WRITE_ONCE(helper_native_write_attempts, 0);
	WRITE_ONCE(helper_native_write_grants, 0);
	WRITE_ONCE(helper_native_write_progress, 0);
	WRITE_ONCE(helper_native_write_progress_pid, 0);
	WRITE_ONCE(helper_native_write_progress_cpu, 0);
}

static noinline long helper_native_write_snapshot(void __user *user)
{
	struct jit_native_write_snapshot state = {
		.version = 1, .errors = atomic_read(&failures),
		.count = smp_load_acquire(&helper_native_write_count),
		.body_after = READ_ONCE(helper_native_write_body_after),
		.lock_a = (unsigned long)&helper_native_write_a, .lock_b = (unsigned long)&helper_native_write_b,
		.stack_low = READ_ONCE(helper_slots[1].origin_stack),
		.stack_high = READ_ONCE(helper_slots[1].origin_stack) + THREAD_SIZE,
		.attempts = smp_load_acquire(&helper_native_write_attempts),
		.grants = smp_load_acquire(&helper_native_write_grants),
		.holder_active = !!(atomic64_read(&killable_holders) & JIT_KILLABLE_RELEASE_NATIVE_WRITE),
	};
	unsigned long flags;
	unsigned int i;

	state.progress = smp_load_acquire(&helper_native_write_progress);
	state.progress_pid = READ_ONCE(helper_native_write_progress_pid);
	state.progress_cpu = READ_ONCE(helper_native_write_progress_cpu);
	/* Public Native wait-list membership is observed only under its own lock;
	 * the static fixture object outlives every snapshot and held acquisition. */
	raw_spin_lock_irqsave(&helper_native_write_a.wait_lock, flags);
	state.native_waiters = !list_empty(&helper_native_write_a.wait_list);
	raw_spin_unlock_irqrestore(&helper_native_write_a.wait_lock, flags);
	if (state.count > JIT_NATIVE_WRITE_EVENTS)
		return -EOVERFLOW;
	for (i = 0; i < state.count; ++i) {
#define WRITE_COPY(name) state.events[i].name = READ_ONCE(helper_native_write_events[i].name)
		WRITE_COPY(operation); WRITE_COPY(object); WRITE_COPY(pid); WRITE_COPY(cpu); WRITE_COPY(stack_address);
		WRITE_COPY(preempt_before); WRITE_COPY(preempt_after); WRITE_COPY(rcu_before); WRITE_COPY(rcu_after);
		WRITE_COPY(irqs_before); WRITE_COPY(irqs_after); WRITE_COPY(switches_before); WRITE_COPY(switches_after);
#undef WRITE_COPY
	}
	return copy_to_user(user, &state, sizeof(state)) ? -EFAULT : 0;
}
