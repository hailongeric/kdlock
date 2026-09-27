// SPDX-License-Identifier: GPL-2.0
/* Public IRQ/BH API consumer. No provider selftest hooks or translation are
 * needed: these APIs must execute on the physical caller even when contended. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/err.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/spinlock.h>

#include "kd_spin_direct.h"

#define IRQ_TEST_WORKERS 4
#define IRQ_TEST_ITERATIONS 10000

enum irq_test_mode {
	IRQ_TEST_SAVE,
	IRQ_TEST_IRQ,
	IRQ_TEST_BH,
	IRQ_TEST_PLAIN,
};

struct irq_test_state {
	unsigned int preempt;
	unsigned int native;
	unsigned int softirq;
	bool irq_off;
	kd_spinlock_t *fast;
};

struct irq_test_worker {
	struct task_struct *task;
	struct completion ready;
	struct completion done;
	unsigned int id;
	unsigned int completed;
	int cpu;
};

static DEFINE_KD_SPINLOCK(shared_lock);
static struct irq_test_worker workers[IRQ_TEST_WORKERS];
static DECLARE_COMPLETION(start);
static atomic_t failures = ATOMIC_INIT(0);
static atomic_t first_failure = ATOMIC_INIT(0);
static bool abort_test;
static u64 shared_counter;

/* Record failures without printing or sleeping inside the protected region.
 * Every acquisition still reaches its matching release before aborting. */
static void irq_test_check(bool pass, unsigned int line)
{
	if (likely(pass))
		return;
	atomic_inc(&failures);
	atomic_cmpxchg(&first_failure, 0, line);
	WRITE_ONCE(abort_test, true);
}

#define CHECK(condition) irq_test_check(!!(condition), __LINE__)

/* Single-thread checks hold get_cpu(); workers are bound before waking. Thus
 * the same per-CPU drain record is sampled before and after an unpinned API. */
static struct irq_test_state irq_test_snapshot(int cpu)
{
	struct kd_spin_fast_cpu *fast = per_cpu_ptr(&kd_spin_fast_cpu, cpu);
	struct irq_test_state state = {
		.preempt = preempt_count(),
		.native = READ_ONCE(fast->nondelegated),
		.softirq = softirq_count(),
		.irq_off = irqs_disabled(),
		.fast = READ_ONCE(fast->held),
	};

	return state;
}

static void irq_test_inside(kd_spinlock_t *lock,
			    const struct irq_test_state *before,
			    enum irq_test_mode mode)
{
	unsigned int offset = mode == IRQ_TEST_BH ?
		SOFTIRQ_LOCK_OFFSET : PREEMPT_DISABLE_OFFSET;

	CHECK(preempt_count() == before->preempt + offset);
	CHECK(irqs_disabled() ==
	      (mode == IRQ_TEST_SAVE || mode == IRQ_TEST_IRQ || before->irq_off));
	CHECK(softirq_count() == before->softirq +
	      (mode == IRQ_TEST_BH ? SOFTIRQ_DISABLE_OFFSET : 0));
	CHECK(this_cpu_read(kd_spin_fast_cpu.nondelegated) == before->native + 1);
	CHECK(this_cpu_read(kd_spin_fast_cpu.held) == before->fast);
	CHECK(READ_ONCE(lock->locked) == KD_SPIN_DIRECT_NATIVE_HELD);
}

static void irq_test_restored(const struct irq_test_state *before, int cpu)
{
	struct irq_test_state after = irq_test_snapshot(cpu);

	CHECK(after.preempt == before->preempt);
	CHECK(after.softirq == before->softirq);
	CHECK(after.irq_off == before->irq_off);
	CHECK(after.native == before->native);
	CHECK(after.fast == before->fast);
}

/* The plain arm deliberately uses the existing byte-5 API, so every arm
 * shares the same physical word without needing a prepared JIT entry. */
static void irq_test_one(kd_spinlock_t *lock, enum irq_test_mode mode,
			 int cpu, bool increment)
{
	struct irq_test_state before = irq_test_snapshot(cpu);
	unsigned long flags = 0;
	unsigned int pause;

	switch (mode) {
	case IRQ_TEST_SAVE:
		kd_spin_lock_irqsave(lock, flags);
		CHECK(irqs_disabled_flags(flags) == before.irq_off);
		break;
	case IRQ_TEST_IRQ:
		CHECK(!before.irq_off);
		kd_spin_lock_irq(lock);
		break;
	case IRQ_TEST_BH:
		kd_spin_lock_bh(lock);
		break;
	case IRQ_TEST_PLAIN:
		preempt_disable();
		kd_spin_direct_native_lock_inline(lock);
		break;
	}
	irq_test_inside(lock, &before, mode);
	if (increment) {
		shared_counter++;
		/* Encourage overlapping requests without a rendezvous or sleep
		 * while IRQs/BH/preemption are disabled. This is not an MCS oracle. */
		for (pause = 0; pause < 32; pause++)
			cpu_relax();
	}
	switch (mode) {
	case IRQ_TEST_SAVE:
		kd_spin_unlock_irqrestore(lock, flags);
		break;
	case IRQ_TEST_IRQ:
		kd_spin_unlock_irq(lock);
		break;
	case IRQ_TEST_BH:
		kd_spin_unlock_bh(lock);
		break;
	case IRQ_TEST_PLAIN:
		kd_spin_direct_native_unlock(lock);
		break;
	}
	irq_test_restored(&before, cpu);
}

static void irq_test_uncontended(void)
{
	kd_spinlock_t outer = KD_SPINLOCK_INITIALIZER;
	kd_spinlock_t inner = KD_SPINLOCK_INITIALIZER;
	struct irq_test_state before, nested;
	unsigned long flags, saved;
	int cpu = get_cpu();

	before = irq_test_snapshot(cpu);
	CHECK(!before.irq_off && !before.softirq);
	irq_test_one(&outer, IRQ_TEST_SAVE, cpu, false);
	irq_test_one(&outer, IRQ_TEST_IRQ, cpu, false);
	irq_test_one(&outer, IRQ_TEST_BH, cpu, false);
	irq_test_one(&outer, IRQ_TEST_PLAIN, cpu, false);

	/* irqsave must preserve an already-disabled entry and keep separate
	 * saved flags for nested locks; the inner release must leave IRQs off. */
	local_irq_save(saved);
	irq_test_one(&outer, IRQ_TEST_SAVE, cpu, false);
	local_irq_restore(saved);
	kd_spin_lock_irqsave(&outer, flags);
	irq_test_inside(&outer, &before, IRQ_TEST_SAVE);
	nested = irq_test_snapshot(cpu);
	irq_test_one(&inner, IRQ_TEST_SAVE, cpu, false);
	irq_test_one(&inner, IRQ_TEST_PLAIN, cpu, false);
	irq_test_restored(&nested, cpu);
	kd_spin_unlock_irqrestore(&outer, flags);
	irq_test_restored(&before, cpu);

	/* Both a surrounding BH-disable region and another BH lock retain
	 * their own nesting level after the inner API returns. */
	local_bh_disable();
	irq_test_one(&outer, IRQ_TEST_BH, cpu, false);
	local_bh_enable();
	kd_spin_lock_bh(&outer);
	irq_test_inside(&outer, &before, IRQ_TEST_BH);
	irq_test_one(&inner, IRQ_TEST_BH, cpu, false);
	kd_spin_unlock_bh(&outer);
	irq_test_restored(&before, cpu);
	CHECK(!atomic_read(&outer.val) && !atomic_read(&inner.val));
	put_cpu();
}

static int irq_test_thread(void *arg)
{
	struct irq_test_worker *worker = arg;
	struct irq_test_state before = irq_test_snapshot(worker->cpu);
	unsigned int i;

	CHECK(raw_smp_processor_id() == worker->cpu);
	CHECK(!before.irq_off && !before.preempt && !before.softirq);
	complete(&worker->ready);
	wait_for_completion(&start);
	for (i = 0; i < IRQ_TEST_ITERATIONS && !READ_ONCE(abort_test); i++) {
		irq_test_one(&shared_lock, (i + worker->id) % 4,
			     worker->cpu, true);
		worker->completed++;
		if (!(i & 127))
			cond_resched();
	}
	irq_test_restored(&before, worker->cpu);
	complete(&worker->done);
	return 0;
}

static unsigned int irq_test_choose_cpus(void)
{
	static const int preferred[] = { 0, 1, 20, 21 };
	unsigned int count = 0, i;
	int cpu;

	for (i = 0; i < ARRAY_SIZE(preferred); i++) {
		cpu = preferred[i];
		if (cpu >= nr_cpu_ids || !cpu_online(cpu))
			continue;
		workers[count++].cpu = cpu;
	}
	for_each_online_cpu(cpu) {
		if (count == IRQ_TEST_WORKERS)
			break;
		/* Four IDs need no NR_CPUS-sized mask on the kernel stack. */
		for (i = 0; i < count; i++)
			if (workers[i].cpu == cpu)
				break;
		if (i != count)
			continue;
		workers[count++].cpu = cpu;
	}
	return count;
}

static int __init irq_test_init(void)
{
	unsigned int count = 0, created = 0, i;
	u64 completed = 0;
	int ret = 0;

	irq_test_uncontended();
	if (atomic_read(&failures)) {
		ret = -EINVAL;
		goto report;
	}
	/* Hold hotplug stable through binding and joining, never from a worker
	 * or a critical section. All ready notifications precede start release. */
	cpus_read_lock();
	count = irq_test_choose_cpus();
	if (count < 3) {
		ret = -ENODEV;
		goto unlock_cpus;
	}
	for (i = 0; i < count; i++) {
		struct irq_test_worker *worker = &workers[i];

		worker->id = i;
		init_completion(&worker->ready);
		init_completion(&worker->done);
		worker->task = kthread_create(irq_test_thread, worker,
					      "kd_irq_api/%u", i);
		if (IS_ERR(worker->task)) {
			ret = PTR_ERR(worker->task);
			worker->task = NULL;
			WRITE_ONCE(abort_test, true);
			break;
		}
		kthread_bind(worker->task, worker->cpu);
		get_task_struct(worker->task);
		created++;
		wake_up_process(worker->task);
	}
	for (i = 0; i < created; i++) {
		if (!wait_for_completion_timeout(&workers[i].ready, 10 * HZ)) {
			ret = -ETIMEDOUT;
			WRITE_ONCE(abort_test, true);
		}
	}
	complete_all(&start);
	for (i = 0; i < created; i++) {
		struct irq_test_worker *worker = &workers[i];

		if (!wait_for_completion_timeout(&worker->done, 10 * HZ)) {
			ret = -ETIMEDOUT;
			WRITE_ONCE(abort_test, true);
			wait_for_completion(&worker->done);
		}
		kthread_stop(worker->task);
		put_task_struct(worker->task);
		worker->task = NULL;
		completed += worker->completed;
	}
	CHECK(shared_counter == completed);
	CHECK(!atomic_read(&shared_lock.val));
	if (!ret) {
		CHECK(completed == (u64)count * IRQ_TEST_ITERATIONS);
		CHECK(!READ_ONCE(abort_test));
		if (atomic_read(&failures))
			ret = -EINVAL;
	}
unlock_cpus:
	cpus_read_unlock();
report:
	if (ret) {
		pr_err("kd_spin irq_api: FAIL error=%d failures=%d first_line=%d completed=%llu counter=%llu\n",
		       ret, atomic_read(&failures), atomic_read(&first_failure),
		       (unsigned long long)completed,
		       (unsigned long long)shared_counter);
		return ret;
	}
	pr_info("kd_spin irq_api: PASS workers=%u cpus=%d,%d,%d,%d iterations=%u counter=%llu variants=irqsave,irq,bh,plain-byte5 nested=irqsave,bh prior=irqoff,bhoff MCS=unobserved JIT=0\n",
		count, workers[0].cpu, workers[1].cpu, workers[2].cpu,
		count > 3 ? workers[3].cpu : -1, IRQ_TEST_ITERATIONS,
		(unsigned long long)shared_counter);
	return 0;
}

static void __exit irq_test_exit(void)
{
	/* Every worker was joined before module init returned. */
}

module_init(irq_test_init);
module_exit(irq_test_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KD spin IRQ/BH API context and mixed contention test");
