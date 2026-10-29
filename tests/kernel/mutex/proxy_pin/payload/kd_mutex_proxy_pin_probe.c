// SPDX-License-Identifier: GPL-2.0
/* A queued delegation producer must eventually allow another task on its CPU
 * to run after its initial spin budget. The owner releases after a bounded
 * deadline even on the old indefinitely pinned protocol, so a failed observation
 * does not strand the test's own workers.
 * No prepared image or daemon is used: this probes queued scheduling only. */
#include <linux/module.h>
#include <linux/kthread.h>
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/cpu.h>
#include <linux/sched/task.h>
#include <linux/preempt.h>
#include <linux/irqflags.h>
#include "kd_mutex_api.h"
#include "kd_mutex_state.h"
#include "kd_lock.h"

static DEFINE_KD_MUTEX(lock);
static DECLARE_COMPLETION(owner_ready);
static DECLARE_COMPLETION(owner_start);
static DECLARE_COMPLETION(owner_release);
static DECLARE_COMPLETION(witness_done);
static struct completion warm_done[4], producer_start[4];
static atomic_t owner_released = ATOMIC_INIT(0);
static atomic_t witness_before_release = ATOMIC_INIT(0);
static unsigned int effects;
static unsigned int warm_effects;

/* Same-task observations outside lock calls. The controller reads them only
 * after joining every created task; these do not infer state inside a JIT body. */
static struct {
	unsigned int preempt, migration, irq, cpu;
	bool valid;
} contexts[5][3];

static void context_take(unsigned int role, unsigned int phase)
{
	contexts[role][phase].preempt = preempt_count();
	contexts[role][phase].migration = current->migration_disabled;
	contexts[role][phase].irq = irqs_disabled();
	contexts[role][phase].cpu = raw_smp_processor_id();
	contexts[role][phase].valid = true;
}

static bool context_check(void)
{
	unsigned int role, phase;
	bool clean = true;

	for (role = 0; role < 5; role++)
		for (phase = 0; phase < 3; phase++) {
			if (role == 4 && phase == 1)
				continue;
			clean &= contexts[role][phase].valid &&
				!contexts[role][phase].preempt &&
				!contexts[role][phase].migration &&
				!contexts[role][phase].irq &&
				contexts[role][phase].cpu == (role == 4 ? 3 : role);
			pr_info("kd_mutex_proxy_context: role=%u phase=%u cpu=%u preempt=%u migration=%u irq=%u valid=%u\n",
				role, phase, contexts[role][phase].cpu,
				contexts[role][phase].preempt,
				contexts[role][phase].migration,
				contexts[role][phase].irq,
				contexts[role][phase].valid);
		}
	return clean;
}

static __attribute__((noipa)) void warm_up(void)
{
	unsigned int i, cpu = raw_smp_processor_id();

	/* Real same-object contention on every producer CPU selects the ordinary
	 * admission path. No test writes the provider's heat or ownership state. */
	for (i = 0; i < 100000; i++) {
		kd_mutex_lock(&lock);
		warm_effects++;
		kd_mutex_unlock(&lock);
	}
	complete(&warm_done[cpu]);
}

static __attribute__((noipa)) int owner(void *unused)
{
	(void)unused;
	context_take(0, 0);
	warm_up();
	context_take(0, 1);
	wait_for_completion(&owner_start);
	kd_mutex_lock(&lock);
	effects++;
	complete(&owner_ready);
	wait_for_completion_timeout(&owner_release, 5 * HZ);
	atomic_set(&owner_released, 1);
	kd_mutex_unlock(&lock);
	context_take(0, 2);
	return 0;
}

static __attribute__((noipa)) int producer(void *unused)
{
	unsigned int cpu = raw_smp_processor_id();

	(void)unused;
	context_take(cpu, 0);
	warm_up();
	context_take(cpu, 1);
	wait_for_completion(&producer_start[cpu]);
	kd_mutex_lock(&lock);
	effects++;
	kd_mutex_unlock(&lock);
	context_take(cpu, 2);
	return 0;
}

static int witness(void *unused)
{
	(void)unused;
	context_take(4, 0);
	atomic_set(&witness_before_release, !atomic_read(&owner_released));
	context_take(4, 2);
	complete(&witness_done);
	return 0;
}

static struct task_struct *start(int (*fn)(void *), unsigned int cpu, const char *name)
{
	struct task_struct *task;

	(void)name;
	task = kthread_create(fn, NULL, "kd_proxy");

	if (!IS_ERR(task)) {
		get_task_struct(task);
		kthread_bind(task, cpu);
		wake_up_process(task);
	}
	return task;
}

static bool wait_queued(unsigned int count)
{
	unsigned long deadline = jiffies + HZ;

	while (kd_mutex_debug_waiter_count(&lock) < count && time_before(jiffies, deadline))
		msleep(1);
	return kd_mutex_debug_waiter_count(&lock) >= count;
}

static int __init probe_init(void)
{
	struct task_struct *tasks[5] = {};
	int result = -EINVAL, i, created = 0;
	bool queued = false, scheduled = false, context_ok;
	unsigned long deadline;

	if (!cpu_online(0) || !cpu_online(1) || !cpu_online(2) || !cpu_online(3))
		return -ENODEV;
	for (i = 0; i < 4; i++) {
		init_completion(&warm_done[i]);
		init_completion(&producer_start[i]);
	}
	tasks[created++] = start(owner, 0, "owner");
	if (IS_ERR(tasks[0]))
		goto join;
	for (i = 1; i < 4; i++) {
		tasks[created++] = start(producer, i, "producer");
		if (IS_ERR(tasks[i]))
			goto join;
	}
	for (i = 0; i < 4; i++)
		if (!wait_for_completion_timeout(&warm_done[i], 15 * HZ))
			goto join;
	complete(&owner_start);
	if (!wait_for_completion_timeout(&owner_ready, HZ))
		goto join;
	/* CPU 2 reserves the delegation gate while blocked on the real owner.
	 * CPU 1 is then the published queue head and CPU 3 waits behind it. */
	complete(&producer_start[2]);
	deadline = jiffies + HZ;
	while (kd_mutex_gate_read(&lock) != KD_MUTEX_GATE_ACQUIRING &&
	       time_before(jiffies, deadline))
		msleep(1);
	if (kd_mutex_gate_read(&lock) != KD_MUTEX_GATE_ACQUIRING)
		goto join;
	complete(&producer_start[1]);
	if (!wait_queued(1))
		goto join;
	complete(&producer_start[3]);
	if (!wait_queued(2))
		goto join;
	queued = true;
	tasks[created++] = start(witness, 3, "witness");
	if (IS_ERR(tasks[4]))
		goto join;
	scheduled = wait_for_completion_timeout(&witness_done, HZ) &&
		atomic_read(&witness_before_release);
join:
	complete_all(&owner_start);
	for (i = 0; i < 4; i++)
		complete_all(&producer_start[i]);
	complete_all(&owner_release);
	for (i = 0; i < created; i++)
		if (!IS_ERR_OR_NULL(tasks[i])) {
			kthread_stop(tasks[i]);
			put_task_struct(tasks[i]);
		}
	context_ok = context_check();
	if (queued && scheduled && context_ok && effects == 4 && warm_effects == 400000 && kd_mutex_is_idle(&lock) &&
	    !kd_mutex_debug_waiter_count(&lock))
		result = 0;
	pr_info("kd_mutex_proxy_pin: queued=%u scheduled=%u effects=%u warm=%u idle=%u context=%u result=%d\n",
		queued, scheduled, effects, warm_effects, kd_mutex_is_idle(&lock), context_ok, result);
	return result;
}
static void __exit probe_exit(void) {}
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KD queued mutex producer preemption probe");
