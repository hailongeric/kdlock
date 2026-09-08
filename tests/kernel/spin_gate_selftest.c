// SPDX-License-Identifier: GPL-2.0
/* Opt-in native-L/private-word component test, before hook installation. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/moduleparam.h>
#include <linux/sched/task.h>

static bool kd_gate_test_enabled;
module_param_named(spin_gate_selftest, kd_gate_test_enabled, bool, 0444);
static int kd_gate_test_cpus[4] = { 0, 1, 2, 3 };
module_param_array_named(spin_gate_cpus, kd_gate_test_cpus, int, NULL, 0444);

#define KD_GATE_TEST_LOOPS 128
#define KD_GATE_TEST_WORD 0x7abc0003U

static struct {
	raw_spinlock_t origin;
	struct kd_spin_gate *gate;
	struct completion start;
	struct completion sequence_done;
	struct completion done[4];
	atomic_t failures;
	atomic_t inside;
	unsigned int operations;
	unsigned int counts[4];
	unsigned int native_waits;
	bool abort;
	bool native_owner_ready;
	bool gate_owner_ready;
	bool native_entered;
} kd_gate_test;

static bool kd_gate_check(bool ok, int line)
{
	if (!ok) {
		atomic_inc(&kd_gate_test.failures);
		pr_err("kd_spin gate selftest error: line=%d cpu=%d\n", line,
		       raw_smp_processor_id());
	}
	return ok;
}

#define KD_GATE_CHECK(condition) kd_gate_check(!!(condition), __LINE__)

#define KD_GATE_WAIT(condition)                                       \
	({                                                            \
		unsigned long deadline = jiffies + 5 * HZ;            \
		bool ready;                                           \
		while (!(ready = !!(condition)) &&                    \
		       !READ_ONCE(kd_gate_test.abort)) {              \
			if (time_after(jiffies, deadline)) {          \
				KD_GATE_CHECK(condition);             \
				WRITE_ONCE(kd_gate_test.abort, true); \
				break;                                \
			}                                             \
			cpu_relax();                                  \
			if (!preempt_count() && !irqs_disabled())     \
				cond_resched();                       \
		}                                                     \
		ready;                                                \
	})

static bool kd_gate_native_contended(void)
{
	struct orig_qspinlock *word = (void *)&kd_gate_test.origin;

	return atomic_read(&word->val) & ~_Q_LOCKED_MASK_HL;
}

static void kd_gate_enter(unsigned int worker)
{
	unsigned int i;

	KD_GATE_CHECK(atomic_cmpxchg(&kd_gate_test.inside, 0, 1) == 0);
	kd_gate_test.operations++;
	kd_gate_test.counts[worker]++;
	for (i = 0; i < 128; i++)
		cpu_relax();
}

static void kd_gate_leave(void)
{
	KD_GATE_CHECK(atomic_xchg(&kd_gate_test.inside, 0) == 1);
}

static bool kd_gate_take(struct kd_spin_hold *hold)
{
	preempt_disable();
	if (!KD_GATE_CHECK(atomic_cmpxchg_acquire(&kd_gate_test.gate->word.val,
						  0, KD_GATE_TEST_WORD) == 0)) {
		preempt_enable();
		WRITE_ONCE(kd_gate_test.abort, true);
		return false;
	}
	if (!KD_GATE_CHECK(kd_spin_gate_claim(kd_gate_test.gate, hold) == 0)) {
		smp_store_release(&kd_gate_test.gate->word.val.counter, 0);
		preempt_enable();
		WRITE_ONCE(kd_gate_test.abort, true);
		return false;
	}
	KD_GATE_CHECK(preempt_count() == 1 && !irqs_disabled());
	KD_GATE_CHECK((unsigned int)atomic_read(&kd_gate_test.gate->word.val) ==
		      KD_GATE_TEST_WORD);
	return true;
}

static void kd_gate_drop_origin(struct kd_spin_hold *hold)
{
	/* Do not return from module init with a live owner on an error path. */
	BUG_ON(!KD_GATE_CHECK(kd_spin_gate_release(hold) == 0));
	KD_GATE_CHECK(preempt_count() == 1);
	KD_GATE_CHECK((unsigned int)atomic_read(&kd_gate_test.gate->word.val) ==
		      KD_GATE_TEST_WORD);
}

static void kd_gate_drop_word(void)
{
	smp_store_release(&kd_gate_test.gate->word.val.counter, 0);
	preempt_enable();
	KD_GATE_CHECK(preempt_count() == 0 && !irqs_disabled());
}

static void kd_gate_sequences(unsigned int worker)
{
	struct kd_spin_hold hold = { 0 };

	if (worker == 1) {
		__raw_spin_lock(&kd_gate_test.origin);
		kd_gate_enter(worker);
		smp_store_release(&kd_gate_test.native_owner_ready, true);
		if (KD_GATE_WAIT(kd_gate_native_contended()))
			kd_gate_test.native_waits++;
		kd_gate_leave();
		__raw_spin_unlock(&kd_gate_test.origin);
		if (!KD_GATE_WAIT(
			    smp_load_acquire(&kd_gate_test.gate_owner_ready)))
			return;
		__raw_spin_lock(&kd_gate_test.origin);
		kd_gate_enter(worker);
		/* A native waiter must enter even while the private gate stays shut. */
		KD_GATE_CHECK(atomic_read(&kd_gate_test.gate->word.val) != 0);
		smp_store_release(&kd_gate_test.native_entered, true);
		kd_gate_leave();
		__raw_spin_unlock(&kd_gate_test.origin);
	} else if (worker == 0) {
		if (!KD_GATE_WAIT(
			    smp_load_acquire(&kd_gate_test.native_owner_ready)))
			goto out;
		if (!kd_gate_take(&hold))
			goto out;
		kd_gate_enter(worker);
		kd_gate_leave();
		kd_gate_drop_origin(&hold);
		kd_gate_drop_word();
		if (!kd_gate_take(&hold))
			goto out;
		kd_gate_enter(worker);
		smp_store_release(&kd_gate_test.gate_owner_ready, true);
		if (KD_GATE_WAIT(kd_gate_native_contended()))
			kd_gate_test.native_waits++;
		kd_gate_leave();
		kd_gate_drop_origin(&hold);
		KD_GATE_WAIT(smp_load_acquire(&kd_gate_test.native_entered));
		kd_gate_drop_word();
out:
		complete_all(&kd_gate_test.sequence_done);
	}
	wait_for_completion(&kd_gate_test.sequence_done);
}

static int kd_gate_worker(void *arg)
{
	unsigned int worker = (unsigned long)arg;
	unsigned int i;

	wait_for_completion(&kd_gate_test.start);
	if (READ_ONCE(kd_gate_test.abort))
		goto done;
	kd_gate_sequences(worker);
	for (i = 0; i < KD_GATE_TEST_LOOPS && !READ_ONCE(kd_gate_test.abort);
	     i++) {
		struct kd_spin_hold hold = { 0 };
		unsigned long flags = 0;

		KD_GATE_CHECK(preempt_count() == 0 && !irqs_disabled());
		if (worker == 0) {
			if (!kd_gate_take(&hold))
				break;
		} else if (worker == 1) {
			__raw_spin_lock(&kd_gate_test.origin);
			KD_GATE_CHECK(preempt_count() == 1 && !irqs_disabled());
		} else if (worker == 2) {
			__raw_spin_lock_bh(&kd_gate_test.origin);
			KD_GATE_CHECK(softirq_count() && !irqs_disabled());
		} else {
			flags = __raw_spin_lock_irqsave(&kd_gate_test.origin);
			KD_GATE_CHECK(preempt_count() == 1 && irqs_disabled());
		}
		kd_gate_enter(worker);
		kd_gate_leave();
		if (worker == 0) {
			kd_gate_drop_origin(&hold);
			kd_gate_drop_word();
		} else if (worker == 1) {
			__raw_spin_unlock(&kd_gate_test.origin);
		} else if (worker == 2) {
			__raw_spin_unlock_bh(&kd_gate_test.origin);
		} else {
			__raw_spin_unlock_irqrestore(&kd_gate_test.origin,
						     flags);
		}
		KD_GATE_CHECK(preempt_count() == 0 && !irqs_disabled());
		cond_resched();
	}
done:
	complete(&kd_gate_test.done[worker]);
	return 0;
}

int kd_spin_gate_selftest(void)
{
	struct task_struct *workers[4] = { NULL };
	unsigned int i, j;
	int ret = 0;

	if (!kd_gate_test_enabled)
		return 0;
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		int cpu = kd_gate_test_cpus[i];

		if (cpu < 0 || cpu >= nr_cpu_ids || !cpu_online(cpu) ||
		    !cpumask_test_cpu(cpu, current->cpus_ptr))
			return -EINVAL;
		for (j = 0; j < i; j++)
			if (cpu == kd_gate_test_cpus[j])
				return -EINVAL;
	}
	raw_spin_lock_init(&kd_gate_test.origin);
	kd_gate_test.gate = kd_spin_gate_get(&kd_gate_test.origin);
	if (!kd_gate_test.gate)
		return -ENOMEM;
	init_completion(&kd_gate_test.start);
	init_completion(&kd_gate_test.sequence_done);
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		init_completion(&kd_gate_test.done[i]);
		workers[i] = kthread_create(kd_gate_worker,
					    (void *)(unsigned long)i,
					    "kd_gate_%u", i);
		if (IS_ERR(workers[i])) {
			ret = PTR_ERR(workers[i]);
			workers[i] = NULL;
			WRITE_ONCE(kd_gate_test.abort, true);
			break;
		}
		kthread_bind(workers[i], kd_gate_test_cpus[i]);
		get_task_struct(workers[i]);
		wake_up_process(workers[i]);
	}
	complete_all(&kd_gate_test.start);
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		if (!workers[i])
			continue;
		if (!wait_for_completion_timeout(&kd_gate_test.done[i],
						 10 * HZ)) {
			KD_GATE_CHECK(false);
			WRITE_ONCE(kd_gate_test.abort, true);
			/* Never free code while a published native waiter is live. */
			wait_for_completion(&kd_gate_test.done[i]);
		}
		kthread_stop(workers[i]);
		put_task_struct(workers[i]);
	}
	if (ret)
		return ret;
	KD_GATE_CHECK(kd_gate_test.native_waits == 2);
	KD_GATE_CHECK(kd_gate_test.native_entered && !kd_gate_test.abort);
	KD_GATE_CHECK(kd_gate_test.operations == 4 * KD_GATE_TEST_LOOPS + 4);
	for (i = 0; i < ARRAY_SIZE(workers); i++)
		KD_GATE_CHECK(kd_gate_test.counts[i] ==
			      KD_GATE_TEST_LOOPS + (i < 2 ? 2 : 0));
	KD_GATE_CHECK(!atomic_read(&kd_gate_test.inside));
	KD_GATE_CHECK(kd_spin_gates_check_idle() == 0);
	pr_info("kd_spin gate selftest: cpus=%d,%d,%d,%d sequences=2 native_waits=%u loops=%u operations=%u native_while_gate_held=%u failures=%d\n",
		kd_gate_test_cpus[0], kd_gate_test_cpus[1],
		kd_gate_test_cpus[2], kd_gate_test_cpus[3],
		kd_gate_test.native_waits, KD_GATE_TEST_LOOPS,
		kd_gate_test.operations, kd_gate_test.native_entered,
		atomic_read(&kd_gate_test.failures));
	return atomic_read(&kd_gate_test.failures) ? -EINVAL : 0;
}
