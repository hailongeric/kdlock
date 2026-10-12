// SPDX-License-Identifier: GPL-2.0
/* Included by kd_mutex.c only in SELFTEST builds. Exercise actual sleep/wake,
 * native ownership and per-CPU reservation. This constructs result packets;
 * returned JIT bodies are checked separately by the benchmark. */
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/kthread.h>
#include <linux/workqueue.h>
#include "kd_hotlock.h"

static bool mutex_wait_selftest;
module_param(mutex_wait_selftest, bool, 0444);
static unsigned int mutex_wait_cpu;
module_param(mutex_wait_cpu, uint, 0444);

struct kd_wait_test {
	struct completion start, entered, done;
	struct kd_mutex_node *node;
	struct kd_mutex gate;
	struct mutex original;
	unsigned int round;
	int errors;
};

static int kd_wait_test_worker(void *data)
{
	struct kd_wait_test *test = data;
	struct kd_mutex_node *node;
	unsigned int i;

	/* Reserve exactly as an ordinary queued task does; the slot and its
	 * migration pin survive all scheduler transitions until final release. */
	migrate_disable();
	preempt_disable();
	node = kd_mutex_reserve_node();
	BUG_ON(!node);
	node->task_struct_ptr = current;
	test->node = node;
	preempt_enable();
	complete(&test->done);
	for (i = 0; i < 1024; i++) {
		wait_for_completion(&test->start);
		preempt_disable();
		complete(&test->entered);
		kd_mutex_wait_for_result(node);
		test->errors += node->regs.ip != i + 1 || !node->completed;
		preempt_enable();
		complete(&test->done);
	}
	preempt_disable();
	kd_mutex_release_node(node);
	preempt_enable();
	wait_for_completion(&test->start);
	preempt_disable();
	complete(&test->entered);
	kd_mutex_wait_and_lock(&test->gate);
	test->errors += test->gate.physical_owner != current ||
		!kd_origin_mutex_owned(&test->original, current);
	_kd_mutex_unlock(&test->gate);
	preempt_enable();
	migrate_enable();
	complete(&test->done);
	/* kthread_stop owns the final task-reference rendezvous. */
	while (!kthread_should_stop()) {
		set_current_state(TASK_INTERRUPTIBLE);
		if (!kthread_should_stop())
			schedule();
		__set_current_state(TASK_RUNNING);
	}
	return 0;
}

static long kd_wait_test_cpu_progress(void *arg)
{
	return raw_smp_processor_id() == mutex_wait_cpu;
}

/* Drive the real sampler through hot -> cold while a result reservation or
 * gate waiter on this CPU is outstanding. Only admission observations are
 * synthetic; the parked task, pin, owner, result publication and drain are real. */
static long kd_wait_test_cool(void *arg)
{
	struct kd_wait_test *test = arg;
	unsigned long address = (unsigned long)&test->original;
	unsigned int i;
	bool hot, cold;

	preempt_disable();
	for (i = 0; i < 4096; i++) {
		kd_hotlock_mutex_entry();
		kd_hotlock_record_mutex_pinned(address);
	}
	hot = kd_hotlock_query_mutex(address);
	/* Exceed even the largest admitted threshold, without changing policy. */
	for (i = 0; i < 256 * 1024; i++)
		kd_hotlock_mutex_entry();
	for (i = 0; i < 1024; i++) {
		kd_hotlock_mutex_entry();
		kd_hotlock_record_mutex_pinned(address);
	}
	cold = !kd_hotlock_query_mutex(address);
	preempt_enable();
	return hot && cold;
}

int kd_mutex_wait_selftest(void)
{
	struct kd_wait_test test = {};
	struct task_struct *task;
	unsigned int i, wake_count = 0;
	struct rcuwait *wake[16];
	unsigned long switches;
	bool blocked_result = false, blocked_gate, deferred_progress = false;

	if (!mutex_wait_selftest)
		return 0;
	if (mutex_wait_cpu >= nr_cpu_ids ||
	    !cpu_online(mutex_wait_cpu))
		return -EINVAL;
	init_completion(&test.start);
	init_completion(&test.entered);
	init_completion(&test.done);
	mutex_init(&test.original);
	kd_mutex_init(&test.gate);
	test.gate.origin_mutex_addr = (unsigned long)&test.original;
	task = kthread_create(kd_wait_test_worker, &test, "kd_wait_probe");
	if (IS_ERR(task))
		return PTR_ERR(task);
	kthread_bind(task, mutex_wait_cpu);
	wake_up_process(task);
	wait_for_completion(&test.done);
	switches = READ_ONCE(task->nvcsw);
	for (i = 0; i < 1024; i++) {
		test.node->regs.ip = 0;
		test.node->completed = 0;
		test.node->locked = KD_MUTEX_WAITING;
		complete(&test.start);
		wait_for_completion(&test.entered);
		if (!i) {
			msleep(30);
			/* The timed recheck briefly runs once per tick. Sample a real
			 * parked interval instead of requiring one exact instant. */
			for (int attempt = 0; attempt < 100 && !blocked_result; attempt++) {
				blocked_result = READ_ONCE(task->__state) == TASK_UNINTERRUPTIBLE &&
					rcuwait_active(test.node->wait);
				if (!blocked_result)
					usleep_range(50, 100);
			}
			test.errors += !blocked_result;
			/* Work on the parked waiter's CPU must make progress. */
			test.errors += work_on_cpu(mutex_wait_cpu, kd_wait_test_cpu_progress, NULL) != 1;
			test.errors += work_on_cpu(mutex_wait_cpu, kd_wait_test_cool, &test) != 1;
			test.errors += !test.node->locked || test.node->completed;
		} else if (!(i & 7)) {
			udelay(i & 63);
		}
		WRITE_ONCE(test.node->regs.ip, i + 1);
		if (!(i & 15)) {
			kd_mutex_defer_result(test.node, wake, &wake_count);
			if (!i) {
				/* Model a later body depending on this completed caller.
				 * Its wake stays buffered until the caller makes progress. */
				wait_for_completion(&test.done);
				deferred_progress = true;
			}
			kd_mutex_flush_wakes(wake, &wake_count);
		} else {
			kd_mutex_clear_locked_set_completed(test.node);
		}
		if (i)
			wait_for_completion(&test.done);
	}
	/* The controller owns the actual Linux mutex and gate across its sleep. */
	test.gate.locked = _Q_LOCKED_VAL;
	kd_mutex_claim_origin(&test.gate);
	complete(&test.start);
	wait_for_completion(&test.entered);
	msleep(30);
	blocked_gate = READ_ONCE(task->__state) == TASK_UNINTERRUPTIBLE &&
		waitqueue_active(&test.gate.gate_wait);
	test.errors += !blocked_gate;
	test.errors += work_on_cpu(mutex_wait_cpu, kd_wait_test_cpu_progress, NULL) != 1;
	test.errors += work_on_cpu(mutex_wait_cpu, kd_wait_test_cool, &test) != 1;
	test.errors += !test.gate.locked || !kd_origin_mutex_owned(&test.original, current);
	_kd_mutex_unlock(&test.gate);
	wait_for_completion(&test.done);
	switches = READ_ONCE(task->nvcsw) - switches;
	kthread_stop(task);
	test.errors += !kd_mutex_check_idle() || test.gate.locked ||
		test.gate.physical_owner || mutex_is_locked(&test.original);
	pr_info("kd_mutex wait probe: rounds=1024 result_sleep=%d gate_sleep=%d switches=%lu errors=%d jit_bodies=0 deferred_progress=%d cooling=2\n",
		blocked_result, blocked_gate, switches, test.errors, deferred_progress);
	return test.errors ? -EINVAL : 0;
}
