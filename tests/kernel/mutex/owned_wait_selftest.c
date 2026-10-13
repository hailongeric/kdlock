// SPDX-License-Identifier: GPL-2.0
/* Private SELFTEST inclusion. Real reservation/FIFO/scheduler, constructed
 * unstarted packet: no JIT body or generated continuation is claimed. */
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/kthread.h>

static bool owned_mutex_wait_selftest;
module_param(owned_mutex_wait_selftest, bool, 0444);
static unsigned int owned_mutex_wait_cpu;
module_param(owned_mutex_wait_cpu, uint, 0444);

struct kd_owned_wait_test {
	struct kd_mutex lock;
	struct completion queued, done;
	bool hot, cold, acquired;
};

static int kd_owned_wait_test_worker(void *data)
{
	struct kd_owned_wait_test *test = data;
	struct kd_owned_mutex_node *node;
	unsigned int i;
	bool admitted = false;

	BUG_ON(!kd_mutex_task_get(current));
	migrate_disable();
	preempt_disable();
	node = kd_owned_mutex_reserve(&test->lock);
	BUG_ON(!node);
	node->lock = &test->lock;
	node->waiter.task = current;
	node->waiter.kind = KD_OWNED_MUTEX_DELEGATE;
	node->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	node->packet_state = KD_PACKET_MINIMAL;
	node->regs.sp = node->regs.ip = 0; /* Guaranteed pre-body refusal. */
	node->result = 0x100;
	node->native_resume = false;
	this_cpu_ptr(kd_owned_mutex_cpus)->active_waiters++;
	BUG_ON(kd_owned_mutex_publish(&test->lock, &node->waiter));
	/* Actual admission cooling while the published FIFO node and its task
	 * reference remain outstanding; no synthetic counter retires that node. */
	for (i = 0; i < 4096; i++) {
		kd_hotlock_owned_mutex_entry();
		admitted = kd_hotlock_record_owned_mutex_pinned((unsigned long)&test->lock);
	}
	test->hot = admitted;
	for (i = 0; i < 256 * 1024; i++)
		kd_hotlock_owned_mutex_entry();
	for (i = 0; i < 1024; i++) {
		kd_hotlock_owned_mutex_entry();
		admitted = kd_hotlock_record_owned_mutex_pinned((unsigned long)&test->lock);
	}
	test->cold = !admitted;
	BUG_ON(list_empty(&node->waiter.list));
	complete(&test->queued);
	kd_owned_mutex_wait_result(node);
	BUG_ON(!kd_owned_mutex_pickup(&test->lock, &node->waiter));
	test->acquired = kd_owned_mutex_owned(&test->lock, current);
	kd_owned_mutex_release(&test->lock);
	this_cpu_ptr(kd_owned_mutex_cpus)->active_waiters--;
	kd_owned_mutex_unreserve(node);
	preempt_enable();
	migrate_enable();
	kd_mutex_task_put(current);
	complete(&test->done);
	while (!kthread_should_stop()) {
		set_current_state(TASK_INTERRUPTIBLE);
		if (!kthread_should_stop())
			schedule();
		__set_current_state(TASK_RUNNING);
	}
	return 0;
}

int kd_owned_mutex_wait_selftest(void)
{
	struct kd_owned_wait_test test = {};
	struct task_struct *worker;
	unsigned long parks;
	unsigned int tries = 1000;
	bool slept;

	if (!owned_mutex_wait_selftest)
		return 0;
	if (!cpu_online(owned_mutex_wait_cpu))
		return -EINVAL;
	kd_mutex_init(&test.lock);
	init_completion(&test.queued);
	init_completion(&test.done);
	kd_mutex_lock(&test.lock);
	parks = READ_ONCE(per_cpu(kd_owned_mutex_parks, owned_mutex_wait_cpu));
	worker = kthread_create(kd_owned_wait_test_worker, &test, "kd_owned_wait");
	if (IS_ERR(worker)) {
		kd_mutex_unlock(&test.lock);
		return PTR_ERR(worker);
	}
	kthread_bind(worker, owned_mutex_wait_cpu);
	wake_up_process(worker);
	wait_for_completion(&test.queued);
	while (READ_ONCE(per_cpu(kd_owned_mutex_parks, owned_mutex_wait_cpu)) == parks && tries--)
		usleep_range(100, 200);
	slept = READ_ONCE(per_cpu(kd_owned_mutex_parks, owned_mutex_wait_cpu)) > parks;
	kd_mutex_unlock(&test.lock);
	wait_for_completion(&test.done);
	kthread_stop(worker);
	BUG_ON(!test.hot || !test.cold || !test.acquired || !slept ||
	       !kd_owned_mutex_is_idle(&test.lock) || !kd_owned_mutex_check_idle() ||
	       !kd_mutex_tasks_idle());
	pr_info("kd_owned_mutex wait probe: queued_cooling=1 result_sleep=1 pickup=1 drained=1 jit_bodies=0\n");
	return 0;
}
