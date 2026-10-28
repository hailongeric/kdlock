// SPDX-License-Identifier: GPL-2.0
/* Public local rwlock API consumer. No JIT, kernel patch or test hooks. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/delay.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/smp.h>
#include "kd_rwlock.h"

static DEFINE_KD_RWLOCK(lock);
static DEFINE_KD_RWLOCK(other);
static DECLARE_COMPLETION(reader_ready);
static DECLARE_COMPLETION(reader_done);
static DECLARE_COMPLETION(writer_done);
static atomic_t errors = ATOMIC_INIT(0);
static atomic_t first_error = ATOMIC_INIT(0);
static bool release_reader, irq_returned, writer_entered, abort_test;
static unsigned int irq_checks;

static void check(bool condition, unsigned int line)
{
	if (likely(condition))
		return;
	atomic_inc(&errors);
	atomic_cmpxchg(&first_error, 0, line);
}
#define CHECK(condition) check(!!(condition), __LINE__)

static void check_empty(void)
{
	CHECK(!kd_rwlock_state(&lock));
	CHECK(!atomic_read(&lock.gate.val));
}

/* A reader callback really interrupts the task holding the outer read. The
 * writer already owns the gate and has published WAITING. No sleeps, printk
 * or rendezvous occur while the callback owns the read or runs in hardirq. */
static void irq_reader(void *unused)
{
	unsigned int before = preempt_count();
	unsigned int native = this_cpu_read(kd_spin_fast_cpu.nondelegated);

	(void)unused;
	CHECK(in_hardirq() && irqs_disabled());
	CHECK(kd_rwlock_state(&lock) & KD_RWLOCK_WRITER_WAITING);
	CHECK(!READ_ONCE(writer_entered));
	kd_read_lock(&lock);
	CHECK(preempt_count() == before + PREEMPT_DISABLE_OFFSET);
	CHECK(kd_rwlock_state(&lock) ==
	      2 * KD_RWLOCK_READER_BIAS + KD_RWLOCK_WRITER_WAITING);
	CHECK(!READ_ONCE(writer_entered));
	CHECK(this_cpu_read(kd_spin_fast_cpu.nondelegated) == native);
	kd_read_unlock(&lock);
	CHECK(preempt_count() == before && irqs_disabled());
	irq_checks++;
	smp_store_release(&irq_returned, true);
}

static int reader(void *unused)
{
	unsigned long deadline;
	unsigned int before = preempt_count();

	(void)unused;
	kd_read_lock(&lock);
	CHECK(!irqs_disabled());
	complete(&reader_ready);
	deadline = jiffies + 5 * HZ;
	while (!smp_load_acquire(&release_reader) && time_before(jiffies, deadline))
		cpu_relax();
	CHECK(READ_ONCE(release_reader));
	kd_read_unlock(&lock);
	CHECK(preempt_count() == before && !irqs_disabled());
	complete(&reader_done);
	return 0;
}

static int writer(void *unused)
{
	unsigned long flags;
	unsigned int before = preempt_count();
	unsigned int native = this_cpu_read(kd_spin_fast_cpu.nondelegated);

	(void)unused;
	/* Local irqsave writer deliberately exercises the contended gate route. */
	kd_write_lock_irqsave(&lock, flags);
	WRITE_ONCE(writer_entered, true);
	CHECK(irqs_disabled() && preempt_count() == before + PREEMPT_DISABLE_OFFSET);
	CHECK(READ_ONCE(irq_returned) || READ_ONCE(abort_test));
	CHECK(this_cpu_read(kd_spin_fast_cpu.nondelegated) == native + 1);
	kd_write_unlock_irqrestore(&lock, flags);
	CHECK(preempt_count() == before && !irqs_disabled());
	CHECK(this_cpu_read(kd_spin_fast_cpu.nondelegated) == native);
	complete(&writer_done);
	return 0;
}

/* State checks run on the controller's pinned CPU. Each failure still reaches
 * the matching unlock, so diagnostics never replace physical ownership. */
static void local_pairs(void)
{
	unsigned long flags, inner_flags, saved;
	unsigned int before, native;
	int acquired;
	int cpu = get_cpu();

	(void)cpu;
	before = preempt_count();
	native = this_cpu_read(kd_spin_fast_cpu.nondelegated);
	kd_read_lock_irqsave(&lock, flags);
	CHECK(irqs_disabled() && preempt_count() == before + PREEMPT_DISABLE_OFFSET);
	kd_read_unlock_irqrestore(&lock, flags);
	CHECK(!irqs_disabled() && preempt_count() == before);
	local_irq_save(saved);
	kd_write_lock_irqsave(&lock, flags);
	CHECK(irqs_disabled_flags(flags));
	kd_read_lock_irqsave(&other, inner_flags);
	kd_read_unlock_irqrestore(&other, inner_flags);
	CHECK(irqs_disabled());
	kd_write_unlock_irqrestore(&lock, flags);
	CHECK(irqs_disabled());
	local_irq_restore(saved);
	kd_write_lock_irqsave(&lock, flags);
	kd_read_lock_irqsave(&other, inner_flags);
	CHECK(!irqs_disabled_flags(flags) && irqs_disabled_flags(inner_flags));
	kd_read_unlock_irqrestore(&other, inner_flags);
	CHECK(irqs_disabled());
	kd_write_unlock_irqrestore(&lock, flags);
	CHECK(!irqs_disabled());
	kd_read_lock_irq(&lock);
	CHECK(irqs_disabled());
	kd_read_unlock_irq(&lock);
	kd_write_lock_irq(&lock);
	CHECK(irqs_disabled());
	kd_write_unlock_irq(&lock);
	CHECK(!irqs_disabled());
	local_bh_disable();
	kd_read_lock_bh(&lock);
	CHECK(preempt_count() == before + SOFTIRQ_DISABLE_OFFSET + SOFTIRQ_LOCK_OFFSET);
	kd_write_lock_bh(&other);
	kd_write_unlock_bh(&other);
	kd_read_unlock_bh(&lock);
	local_bh_enable();
	CHECK(preempt_count() == before && !irqs_disabled());
	acquired = kd_read_trylock(&lock);
	CHECK(acquired);
	if (acquired) {
		CHECK(!kd_write_trylock(&lock));
		CHECK(!kd_write_trylock_irqsave(&lock, flags));
		CHECK(!irqs_disabled() && preempt_count() == before + PREEMPT_DISABLE_OFFSET);
		kd_read_unlock(&lock);
	}
	acquired = kd_write_trylock_irqsave(&lock, flags);
	CHECK(acquired);
	if (acquired) {
		CHECK(!kd_read_trylock(&lock));
		kd_write_unlock_irqrestore(&lock, flags);
	}
	acquired = kd_write_trylock(&lock);
	CHECK(acquired);
	if (acquired)
		kd_write_unlock(&lock);
	CHECK(preempt_count() == before && !irqs_disabled());
	CHECK(this_cpu_read(kd_spin_fast_cpu.nondelegated) == native);
	check_empty();
	CHECK(!kd_rwlock_state(&other) && !atomic_read(&other.gate.val));
	put_cpu();
}

static int __init probe_init(void)
{
	struct task_struct *r = NULL, *w = NULL;
	cpumask_var_t saved_mask;
	unsigned long deadline;
	int cpus[3], cpu, ret = 0;
	unsigned int count = 0;

	if (!alloc_cpumask_var(&saved_mask, GFP_KERNEL))
		return -ENOMEM;
	cpus_read_lock();
	for_each_online_cpu(cpu) {
		cpus[count++] = cpu;
		if (count == ARRAY_SIZE(cpus))
			break;
	}
	if (count != ARRAY_SIZE(cpus)) {
		ret = -ENODEV;
		goto out;
	}
	cpumask_copy(saved_mask, current->cpus_ptr);
	ret = set_cpus_allowed_ptr(current, cpumask_of(cpus[2]));
	if (ret)
		goto out;
	local_pairs();
	r = kthread_create(reader, NULL, "kd_rw_irq_read");
	if (IS_ERR(r)) {
		ret = PTR_ERR(r);
		r = NULL;
		goto restore;
	}
	get_task_struct(r);
	kthread_bind(r, cpus[0]);
	wake_up_process(r);
	if (!wait_for_completion_timeout(&reader_ready, 2 * HZ)) {
		ret = -ETIMEDOUT;
		goto join;
	}
	w = kthread_create(writer, NULL, "kd_rw_irq_write");
	if (IS_ERR(w)) {
		ret = PTR_ERR(w);
		w = NULL;
		goto join;
	}
	get_task_struct(w);
	kthread_bind(w, cpus[1]);
	wake_up_process(w);
	deadline = jiffies + HZ;
	while (!(kd_rwlock_state(&lock) & KD_RWLOCK_WRITER_WAITING) &&
	       time_before(jiffies, deadline))
		usleep_range(100, 200);
	if (!(kd_rwlock_state(&lock) & KD_RWLOCK_WRITER_WAITING)) {
		ret = -ETIMEDOUT;
		goto join;
	}
	/* Synchronous dispatch retains module text until the callback's actual
	 * return, including failure paths; a published flag alone is not an ACK. */
	ret = smp_call_function_single(cpus[0], irq_reader, NULL, true);
	if (ret)
		goto join;
	CHECK(smp_load_acquire(&irq_returned));
join:
	if (ret)
		WRITE_ONCE(abort_test, true);
	smp_store_release(&release_reader, true);
	/* Never return an init failure while a task or callback can still use
	 * module text. An API deadlock retains this load for snapshot recovery;
	 * a userspace timeout is not permission to free/unload these inputs. */
	if (r) {
		wait_for_completion(&reader_done);
		kthread_stop(r);
		put_task_struct(r);
	}
	if (w) {
		wait_for_completion(&writer_done);
		kthread_stop(w);
		put_task_struct(w);
	}
	check_empty();
	CHECK(irq_checks == 1 && READ_ONCE(writer_entered));
	if (atomic_read(&errors))
		ret = -EINVAL;
restore:
	if (set_cpus_allowed_ptr(current, saved_mask) && !ret)
		ret = -EINVAL;
out:
	cpus_read_unlock();
	free_cpumask_var(saved_mask);
	if (ret) {
		pr_err("kd_rwlock_irq_api_test FAIL ret=%d errors=%d first_line=%d\n",
		       ret, atomic_read(&errors), atomic_read(&first_error));
		return ret;
	}
	pr_info("kd_rwlock_irq_api_test PASS irq_readers=%u writers=1 errors=0 idle=1 JIT=0\n",
		irq_checks);
	return 0;
}

static void __exit probe_exit(void) { }
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KD local rwlock IRQ/BH and interrupt-reader ordering checks");
