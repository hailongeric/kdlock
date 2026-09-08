// SPDX-License-Identifier: GPL-2.0
/* Real task/CPU pins and native locks, but modeled frame notifications.
 * This is not the legacy queue/JIT/native-resume integration test.
 */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/moduleparam.h>
#include <linux/sched/task.h>

static bool kd_entry_test_enabled;
module_param_named(spin_entry_selftest, kd_entry_test_enabled, bool, 0444);
static int kd_entry_test_cpus[2] = { 0, 1 };
module_param_array_named(spin_entry_cpus, kd_entry_test_cpus, int, NULL, 0444);

static struct {
	raw_spinlock_t locks[KD_SPIN_ENTRY_SLOTS + 1];
	struct kd_spin_ref waiter;
	struct completion start;
	struct completion done[2];
	atomic_t failures;
	bool abort;
	bool waiter_ready;
	bool owner_ready;
	bool release_a;
	bool ack_a;
	bool release_b;
	bool owner_done;
	bool retained_pin;
	bool retained_b;
	unsigned int notifications;
} kd_entry_test;

static bool kd_entry_check(bool ok, int line)
{
	if (!ok) {
		atomic_inc(&kd_entry_test.failures);
		pr_err("kd_spin entry selftest error: line=%d cpu=%d preempt=%x\n",
		       line, raw_smp_processor_id(), preempt_count());
	}
	return ok;
}

#define KD_ENTRY_CHECK(condition) kd_entry_check(!!(condition), __LINE__)
/* Never let init return while workers retain physical locks or live tickets. */
#define KD_ENTRY_REQUIRE(condition) BUG_ON(!KD_ENTRY_CHECK(condition))

static bool kd_entry_wait(bool *flag, bool draining)
{
	unsigned long deadline = jiffies + 5 * HZ;

	while (!smp_load_acquire(flag)) {
		if (!draining && READ_ONCE(kd_entry_test.abort))
			return false;
		if (time_after(jiffies, deadline)) {
			KD_ENTRY_CHECK(false);
			WRITE_ONCE(kd_entry_test.abort, true);
			return false;
		}
		cpu_relax();
		if (!preempt_count())
			cond_resched();
	}
	return true;
}

static void kd_entry_drop(struct kd_spin_ref *ref)
{
	struct kd_spin_gate *gate;

	if (!ref->entry)
		return;
	gate = kd_spin_entry_gate(ref);
	KD_ENTRY_REQUIRE(gate);
	KD_ENTRY_REQUIRE(kd_spin_entry_release_origin(ref) == 0);
	KD_ENTRY_CHECK(READ_ONCE(gate->word.locked) == 1);
	smp_store_release(&gate->word.val.counter, 0);
	KD_ENTRY_REQUIRE(kd_spin_entry_end(ref) == 0);
}

static void kd_entry_owner(void)
{
	struct kd_spin_ref a = { 0 }, b = { 0 };
	struct kd_spin_gate *gate;
	unsigned int registered = 0;
	bool last = false;

	KD_ENTRY_REQUIRE(kd_spin_entry_begin(&kd_entry_test.locks[0],
					     KD_SPIN_ENTRY_HOOK, &a) == 0);
	KD_ENTRY_REQUIRE(kd_spin_entry_begin(&kd_entry_test.locks[1],
					     KD_SPIN_ENTRY_VIRTUAL, &b) == 0);
	gate = kd_spin_entry_gate(&a);
	KD_ENTRY_REQUIRE(gate);
	WRITE_ONCE(gate->word.locked, 1);
	gate = kd_spin_entry_gate(&b);
	KD_ENTRY_REQUIRE(gate);
	WRITE_ONCE(gate->word.locked, 1);
	KD_ENTRY_REQUIRE(kd_spin_entry_claim(&a) == 0);
	KD_ENTRY_REQUIRE(kd_spin_entry_claim(&b) == 0);
	KD_ENTRY_CHECK(preempt_count() == 2 && !irqs_disabled());
	if (!kd_entry_wait(&kd_entry_test.waiter_ready, false))
		goto drain;
	KD_ENTRY_REQUIRE(kd_spin_entry_borrow_get(&kd_entry_test.waiter) == 0);
	registered++;
	KD_ENTRY_REQUIRE(kd_spin_entry_borrow_get(&kd_entry_test.waiter) == 0);
	registered++;
	smp_store_release(&kd_entry_test.owner_ready, true);
	if (!kd_entry_wait(&kd_entry_test.release_a, false))
		goto drain;
	kd_entry_drop(&a);
	KD_ENTRY_CHECK(preempt_count() == 1);
	KD_ENTRY_REQUIRE(
		kd_spin_entry_borrow_put(&kd_entry_test.waiter, &last) == 0);
	registered--;
	KD_ENTRY_CHECK(!last);
	kd_entry_test.notifications++;
	smp_store_release(&kd_entry_test.ack_a, true);
	kd_entry_wait(&kd_entry_test.release_b, false);
drain:
	kd_entry_drop(&a);
	kd_entry_drop(&b);
	while (registered) {
		KD_ENTRY_REQUIRE(kd_spin_entry_borrow_put(&kd_entry_test.waiter,
							  &last) == 0);
		registered--;
		kd_entry_test.notifications++;
	}
	KD_ENTRY_CHECK(preempt_count() == 0 && !irqs_disabled());
	smp_store_release(&kd_entry_test.owner_done, true);
}

static void kd_entry_waiter(void)
{
	struct kd_spin_ref ref = { 0 }, found = { 0 };

	KD_ENTRY_REQUIRE(kd_spin_entry_begin(&kd_entry_test.locks[0],
					     KD_SPIN_ENTRY_HOOK, &ref) == 0);
	kd_entry_test.waiter = ref;
	smp_store_release(&kd_entry_test.waiter_ready, true);
	if (!kd_entry_wait(&kd_entry_test.owner_ready, false))
		goto drain;
	KD_ENTRY_REQUIRE(kd_spin_entry_mark_native(&ref) == 0);
	KD_ENTRY_CHECK(kd_spin_entry_native_active());
	KD_ENTRY_CHECK(kd_spin_entry_find(&kd_entry_test.locks[0], &found) &&
		       found.entry == ref.entry &&
		       found.sequence == ref.sequence);
	KD_ENTRY_CHECK(kd_spin_entry_end(&ref) == -EBUSY);
	smp_store_release(&kd_entry_test.release_a, true);
	if (!kd_entry_wait(&kd_entry_test.ack_a, false))
		goto drain;
	kd_entry_test.retained_pin = preempt_count() == 1 &&
				     kd_spin_entry_native_active() &&
				     kd_spin_entry_task_active();
	kd_entry_test.retained_b = raw_spin_is_locked(&kd_entry_test.locks[1]);
	KD_ENTRY_CHECK(kd_entry_test.retained_pin && kd_entry_test.retained_b);
	KD_ENTRY_CHECK(!raw_spin_is_locked(&kd_entry_test.locks[0]));
	KD_ENTRY_CHECK(kd_spin_entry_end(&ref) == -EBUSY);
	smp_store_release(&kd_entry_test.release_b, true);
drain:
	KD_ENTRY_REQUIRE(kd_entry_wait(&kd_entry_test.owner_done, true));
	KD_ENTRY_CHECK(preempt_count() == 1 && !irqs_disabled());
	KD_ENTRY_REQUIRE(kd_spin_entry_end(&ref) == 0);
	KD_ENTRY_CHECK(preempt_count() == 0 && !irqs_disabled());
	KD_ENTRY_CHECK(!kd_spin_entry_task_active() &&
		       !kd_spin_entry_native_active());
}

static int kd_entry_worker(void *arg)
{
	unsigned int worker = (unsigned long)arg;

	wait_for_completion(&kd_entry_test.start);
	if (!READ_ONCE(kd_entry_test.abort)) {
		if (worker == 0)
			kd_entry_owner();
		else
			kd_entry_waiter();
	}
	complete(&kd_entry_test.done[worker]);
	return 0;
}

static void kd_entry_capacity_test(void)
{
	struct kd_spin_ref refs[KD_SPIN_ENTRY_SLOTS] = { 0 };
	struct kd_spin_ref extra = { 0 }, stale;
	unsigned int i;

	KD_ENTRY_REQUIRE(preempt_count() == 0 && !irqs_disabled());
	for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++)
		KD_ENTRY_REQUIRE(kd_spin_entry_begin(&kd_entry_test.locks[i],
						     KD_SPIN_ENTRY_HOOK,
						     &refs[i]) == 0);
	KD_ENTRY_CHECK(preempt_count() == KD_SPIN_ENTRY_SLOTS);
	KD_ENTRY_CHECK(
		kd_spin_entry_begin(&kd_entry_test.locks[KD_SPIN_ENTRY_SLOTS],
				    KD_SPIN_ENTRY_HOOK, &extra) == -E2BIG);
	KD_ENTRY_CHECK(kd_spin_entry_begin(&kd_entry_test.locks[0],
					   KD_SPIN_ENTRY_HOOK,
					   &extra) == -EDEADLK);
	stale = refs[0];
	KD_ENTRY_REQUIRE(kd_spin_entry_end(&refs[0]) == 0);
	KD_ENTRY_REQUIRE(kd_spin_entry_begin(&kd_entry_test.locks[0],
					     KD_SPIN_ENTRY_HOOK,
					     &refs[0]) == 0);
	KD_ENTRY_CHECK(stale.entry == refs[0].entry &&
		       stale.sequence != refs[0].sequence);
	KD_ENTRY_CHECK(kd_spin_entry_end(&stale) == -ESTALE);
	for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++)
		KD_ENTRY_REQUIRE(kd_spin_entry_end(&refs[i]) == 0);
	KD_ENTRY_CHECK(preempt_count() == 0 && !irqs_disabled());
}

int kd_spin_entry_selftest(void)
{
	struct task_struct *workers[2] = { NULL };
	unsigned int i;
	int ret = 0;

	if (!kd_entry_test_enabled)
		return 0;
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		int cpu = kd_entry_test_cpus[i];

		if (cpu < 0 || cpu >= nr_cpu_ids || !cpu_online(cpu) ||
		    !cpumask_test_cpu(cpu, current->cpus_ptr))
			return -EINVAL;
	}
	if (kd_entry_test_cpus[0] == kd_entry_test_cpus[1])
		return -EINVAL;
	for (i = 0; i < ARRAY_SIZE(kd_entry_test.locks); i++)
		raw_spin_lock_init(&kd_entry_test.locks[i]);
	kd_entry_capacity_test();
	init_completion(&kd_entry_test.start);
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		init_completion(&kd_entry_test.done[i]);
		workers[i] = kthread_create(kd_entry_worker,
					    (void *)(unsigned long)i,
					    "kd_entry_%u", i);
		if (IS_ERR(workers[i])) {
			ret = PTR_ERR(workers[i]);
			workers[i] = NULL;
			WRITE_ONCE(kd_entry_test.abort, true);
			break;
		}
		kthread_bind(workers[i], kd_entry_test_cpus[i]);
		get_task_struct(workers[i]);
		wake_up_process(workers[i]);
	}
	complete_all(&kd_entry_test.start);
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		if (!workers[i])
			continue;
		if (!wait_for_completion_timeout(&kd_entry_test.done[i],
						 10 * HZ)) {
			KD_ENTRY_CHECK(false);
			WRITE_ONCE(kd_entry_test.abort, true);
			wait_for_completion(&kd_entry_test.done[i]);
		}
		kthread_stop(workers[i]);
		put_task_struct(workers[i]);
	}
	if (ret)
		return ret;
	KD_ENTRY_CHECK(!kd_entry_test.abort &&
		       kd_entry_test.notifications == 2);
	KD_ENTRY_CHECK(kd_entry_test.retained_pin && kd_entry_test.retained_b);
	KD_ENTRY_CHECK(kd_spin_entries_check_idle() == 0);
	KD_ENTRY_CHECK(kd_spin_gates_check_idle() == 0);
	pr_info("kd_spin entry selftest: cpus=%d,%d capacity=%u notifications=%u retained_pin=%u retained_b=%u failures=%d JIT=0\n",
		kd_entry_test_cpus[0], kd_entry_test_cpus[1],
		KD_SPIN_ENTRY_SLOTS, kd_entry_test.notifications,
		kd_entry_test.retained_pin, kd_entry_test.retained_b,
		atomic_read(&kd_entry_test.failures));
	return atomic_read(&kd_entry_test.failures) ? -EINVAL : 0;
}
