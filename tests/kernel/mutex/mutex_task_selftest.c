// SPDX-License-Identifier: GPL-2.0
/* Exercise production task membership, native requests and RCU reclamation
 * before hooks are published. Only the continuation packet and outer batch
 * callback are fixtures: this test never executes JIT or switches stacks. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>

#include "kd_exec.h"
#include "kd_segment.h"

static bool kd_task_test_enabled;
module_param_named(mutex_task_selftest, kd_task_test_enabled, bool, 0444);
static int kd_task_test_cpus[3] = { 0, 1, 2 };
module_param_array_named(mutex_task_cpus, kd_task_test_cpus, int, NULL, 0444);

static struct {
	struct mutex locks[2];
	struct kd_exec_frame frame;
	struct kd_exec_outer_unlock outer_hook;
	struct task_struct *workers[3];
	struct completion start;
	struct completion done[3];
	atomic_t failures;
	unsigned long gsbase;
	unsigned int frees_before;
	unsigned int acks;
	bool outer_first;
	bool registry_stress;
	bool abort;
	bool waiter_ready;
	bool published;
	bool reader_ready;
	bool native_ready;
	bool waiter_done;
} kd_task_test;

static bool kd_task_check(bool ok, int line)
{
	if (!ok) {
		atomic_inc(&kd_task_test.failures);
		pr_err("kd_mutex task selftest error: line=%d cpu=%d outer_first=%u preempt=%x\n",
		       line, raw_smp_processor_id(), kd_task_test.outer_first,
		       preempt_count());
	}
	return ok;
}

#define KD_TASK_CHECK(condition) kd_task_check(!!(condition), __LINE__)
/* Returning from failed init with live requests/RCU readers would unload their
 * code. Broken protocol prerequisites must fail-stop in the recovery guest. */
#define KD_TASK_REQUIRE(condition) BUG_ON(!KD_TASK_CHECK(condition))

static void kd_task_wait(bool *flag, bool rcu_reader)
{
	unsigned long deadline = jiffies + 5 * HZ;

	while (!smp_load_acquire(flag)) {
		KD_TASK_REQUIRE(!time_after(jiffies, deadline));
		cpu_relax();
		if (!rcu_reader && !preempt_count())
			cond_resched();
	}
}

static unsigned int kd_task_refs(struct task_struct *task)
{
	struct kd_mutex_task_bucket *bucket = kd_mutex_task_bucket(task);
	struct kd_mutex_task *entry;
	unsigned long flags;
	unsigned int refs = 0;

	raw_spin_lock_irqsave(&bucket->lock, flags);
	hlist_for_each_entry(entry, &bucket->tasks, link) {
		if (entry->task == task) {
			refs = entry->refs;
			break;
		}
	}
	raw_spin_unlock_irqrestore(&bucket->lock, flags);
	return refs;
}

static int kd_task_release_outer(struct kd_exec_frame *frame,
				 struct kd_exec_outer_unlock *hook)
{
	struct mutex *lock = &kd_task_test.locks[0];

	/* There is no queue batch in this probe. Use its callback slot solely to
	 * release real A when the production event handler observes early A unlock. */
	KD_TASK_REQUIRE(frame == &kd_task_test.frame &&
			hook == &kd_task_test.outer_hook);
	KD_TASK_REQUIRE(kd_origin_mutex_owned(lock, current));
	kd_origin_mutex_unlock(lock, _RET_IP_);
	return 0;
}

static void kd_task_owner(void)
{
	struct task_struct *waiter = kd_task_test.workers[1];
	struct kd_exec_frame *frame = &kd_task_test.frame;
	unsigned long locks[] = { (unsigned long)&kd_task_test.locks[0],
				  (unsigned long)&kd_task_test.locks[1] };
	enum kd_exec_lock_kind kinds[] = { KD_EXEC_LOCK_QUEUE_OWNER,
					   KD_EXEC_LOCK_NATIVE };
	void *nodes[] = { NULL, &kd_task_test.locks[1] };
	s64 failures = KD_MUTEX_STAT_READ(kd_mutex_task_failures);

	kd_task_wait(&kd_task_test.waiter_ready, false);
	kd_origin_mutex_lock(&kd_task_test.locks[0]);
	kd_origin_mutex_lock(&kd_task_test.locks[1]);
	/* Allocation refusal must not publish routing or acquire a task record.
	 * Two successful gets share one entry; the non-final put keeps it alive. */
	WRITE_ONCE(kd_mutex_task_fail_once, 1);
	KD_TASK_REQUIRE(!kd_mutex_task_get(waiter));
	KD_TASK_CHECK(!kd_mutex_task_active(waiter) &&
		      !kd_mutex_task_count());
	KD_TASK_CHECK(KD_MUTEX_STAT_READ(kd_mutex_task_failures) == failures + 1);
	KD_TASK_REQUIRE(kd_mutex_task_get(waiter));
	KD_TASK_REQUIRE(kd_mutex_task_get(waiter));
	KD_TASK_CHECK(kd_task_refs(waiter) == 2 &&
		      kd_mutex_task_count() == 1);
	kd_mutex_task_put(waiter);
	KD_TASK_CHECK(kd_task_refs(waiter) == 1);
	smp_store_release(&kd_task_test.published, true);
	kd_task_wait(&kd_task_test.reader_ready, false);

	/* These nonzero RIP/RSP fields admit the native protocol, but are never
	 * jumped to. Real generated-code/continuation tests remain separate gates. */
	kd_exec_frame_regs(frame)->ip = (unsigned long)kd_task_owner;
	kd_exec_frame_regs(frame)->sp = (unsigned long)&frame->regs;
	frame->entry_ip = kd_exec_frame_regs(frame)->ip;
	frame->gsbase = kd_task_test.gsbase;
	frame->logical_task = waiter;
	frame->outer_lock_addr = locks[0];
	frame->outer_lock_depth = 1;
	frame->held_lock_depth = 2;
	frame->state = KD_EXEC_FRAME_RUNNING;
	frame->mutex_backend = true;
	kd_task_test.outer_hook.release = kd_task_release_outer;
	frame->outer_unlock_hook = &kd_task_test.outer_hook;
	/* kd_task_round zeroed the ordinary native frame and routing fields.
	 * This manual two-lock probe is already materialized, not a borrowed
	 * pristine ABI2 batch. Publish that fact only after its list is valid. */
	INIT_LIST_HEAD(&frame->native_link);
	frame->complex_ready = true;
	KD_TASK_REQUIRE(kd_exec_frame_set_lock_entries(frame, locks, kinds,
						       nodes, NULL, 2) == 0);
	preempt_disable();
	KD_TASK_REQUIRE(kd_exec_native_begin(frame, true) == 0);
	KD_TASK_CHECK(kd_task_refs(waiter) == 1);
	smp_store_release(&kd_task_test.native_ready, true);
	KD_TASK_REQUIRE(kd_exec_native_wait(frame) == 0);
	KD_TASK_REQUIRE(kd_exec_frame_complete(frame) == 0);
	KD_TASK_CHECK(list_empty(&frame->native_link) &&
		      !frame->native_request);
	preempt_enable();

	/* In B->A order the owner's batch still holds physical A after logical
	 * completion. Keep it stable until the waiter checks the final ACK. */
	kd_task_wait(&kd_task_test.waiter_done, false);
	KD_TASK_CHECK(kd_task_test.outer_hook.released ==
		      kd_task_test.outer_first);
	if (!kd_task_test.outer_hook.released) {
		KD_TASK_REQUIRE(
			kd_origin_mutex_owned(&kd_task_test.locks[0], current));
		kd_origin_mutex_unlock(&kd_task_test.locks[0], _RET_IP_);
	}
	KD_TASK_CHECK(!mutex_is_locked(&kd_task_test.locks[0]) &&
		      !mutex_is_locked(&kd_task_test.locks[1]));
}

static void kd_task_waiter(void)
{
	unsigned int first = kd_task_test.outer_first ? 0 : 1;
	unsigned int last = 1 - first;
	struct task_struct *owner = kd_task_test.workers[0];

	preempt_disable();
	kd_task_test.gsbase = kd_read_kernel_gsbase();
	preempt_enable();
	smp_store_release(&kd_task_test.waiter_ready, true);
	kd_task_wait(&kd_task_test.native_ready, false);
	KD_TASK_CHECK(kd_mutex_task_reroute(current) &&
		      kd_task_refs(current) == 1);
	KD_TASK_CHECK(kd_origin_mutex_owned(&kd_task_test.locks[0], owner) &&
		      kd_origin_mutex_owned(&kd_task_test.locks[1], owner));
	KD_TASK_REQUIRE(kd_exec_native_unlock(
		(unsigned long)&kd_task_test.locks[first], true));
	kd_task_test.acks++;
	KD_TASK_CHECK(!mutex_is_locked(&kd_task_test.locks[first]));
	KD_TASK_CHECK(kd_origin_mutex_owned(&kd_task_test.locks[last], owner));
	KD_TASK_CHECK(kd_mutex_task_reroute(current) &&
		      kd_task_refs(current) == 1);
	KD_TASK_CHECK(atomic_read(&kd_mutex_task_test_frees) ==
		      kd_task_test.frees_before);
	KD_TASK_REQUIRE(kd_exec_native_unlock(
		(unsigned long)&kd_task_test.locks[last], true));
	kd_task_test.acks++;
	/* The release-published ACK must follow record removal, but the old RCU
	 * reader still pins its memory. A duplicate request must no longer route. */
	KD_TASK_CHECK(!kd_mutex_task_reroute(current) &&
		      !kd_task_refs(current));
	KD_TASK_CHECK(!kd_mutex_task_count());
	KD_TASK_CHECK(atomic_read(&kd_mutex_task_test_frees) ==
		      kd_task_test.frees_before);
	KD_TASK_CHECK(!kd_exec_native_unlock(
		(unsigned long)&kd_task_test.locks[last], true));
	KD_TASK_CHECK(!mutex_is_locked(&kd_task_test.locks[1]));
	KD_TASK_CHECK(
		kd_task_test.outer_first ?
			!mutex_is_locked(&kd_task_test.locks[0]) :
			kd_origin_mutex_owned(&kd_task_test.locks[0], owner));
	smp_store_release(&kd_task_test.waiter_done, true);
}

static void kd_task_reader(void)
{
	struct task_struct *waiter = kd_task_test.workers[1];
	struct kd_mutex_task *entry, *saved = NULL;

	kd_task_wait(&kd_task_test.published, false);
	rcu_read_lock();
	hlist_for_each_entry_rcu(entry, &kd_mutex_task_bucket(waiter)->tasks, link) {
		if (entry->task == waiter) {
			saved = entry;
			break;
		}
	}
	KD_TASK_REQUIRE(saved && READ_ONCE(saved->refs) == 1);
	smp_store_release(&kd_task_test.reader_ready, true);
	/* A real read-side critical section spans both owner ACKs. Do not sleep
	 * here, including on voluntary/non-preemptible RCU configurations. */
	kd_task_wait(&kd_task_test.waiter_done, true);
	KD_TASK_CHECK(atomic_read(&kd_mutex_task_test_frees) ==
		      kd_task_test.frees_before);
	KD_TASK_CHECK(saved->task == waiter && READ_ONCE(saved->refs) == 0);
	KD_TASK_CHECK(!kd_mutex_task_active(waiter));
	rcu_read_unlock();
}

static void kd_task_registry_stress(void)
{
	struct task_struct *shared = kd_task_test.workers[0];
	unsigned int i;

	/* The parent retains one shared reference across all workers. Concurrent
	 * increments/decrements must neither lose it nor remove its membership.
	 * Each other worker also repeatedly inserts/removes its own exact task. */
	for (i = 0; i < 4096; i++) {
		KD_TASK_REQUIRE(kd_mutex_task_get(shared));
		KD_TASK_REQUIRE(kd_mutex_task_get(current));
		KD_TASK_CHECK(kd_mutex_task_active(shared) &&
			      kd_mutex_task_active(current) && !kd_mutex_tasks_idle());
		kd_mutex_task_put(current);
		kd_mutex_task_put(shared);
		if (!(i & 63))
			cond_resched();
	}
}

static int kd_task_worker(void *arg)
{
	unsigned int worker = (unsigned long)arg;

	wait_for_completion(&kd_task_test.start);
	if (!READ_ONCE(kd_task_test.abort)) {
		if (kd_task_test.registry_stress)
			kd_task_registry_stress();
		else if (worker == 0)
			kd_task_owner();
		else if (worker == 1)
			kd_task_waiter();
		else
			kd_task_reader();
	}
	complete(&kd_task_test.done[worker]);
	return 0;
}

static int kd_task_round(bool outer_first, bool registry_stress)
{
	unsigned int i;
	int ret = 0;

	memset(&kd_task_test, 0, sizeof(kd_task_test));
	atomic_set(&kd_task_test.failures, 0);
	kd_task_test.outer_first = outer_first;
	kd_task_test.registry_stress = registry_stress;
	kd_task_test.frees_before = atomic_read(&kd_mutex_task_test_frees);
	for (i = 0; i < ARRAY_SIZE(kd_task_test.locks); i++)
		mutex_init(&kd_task_test.locks[i]);
	init_completion(&kd_task_test.start);
	for (i = 0; i < ARRAY_SIZE(kd_task_test.workers); i++) {
		struct task_struct *worker;

		init_completion(&kd_task_test.done[i]);
		worker = kthread_create(kd_task_worker,
					(void *)(unsigned long)i, "kd_mtask_%u",
					i);
		if (IS_ERR(worker)) {
			ret = PTR_ERR(worker);
			WRITE_ONCE(kd_task_test.abort, true);
			break;
		}
		kd_task_test.workers[i] = worker;
		kthread_bind(worker, kd_task_test_cpus[i]);
		get_task_struct(worker);
		wake_up_process(worker);
	}
	if (registry_stress && !ret)
		KD_TASK_REQUIRE(kd_mutex_task_get(kd_task_test.workers[0]));
	complete_all(&kd_task_test.start);
	for (i = 0; i < ARRAY_SIZE(kd_task_test.workers); i++) {
		struct task_struct *worker = kd_task_test.workers[i];

		if (!worker)
			continue;
		KD_TASK_REQUIRE(wait_for_completion_timeout(
			&kd_task_test.done[i], 10 * HZ));
		kthread_stop(worker);
		put_task_struct(worker);
	}
	if (registry_stress && !ret) {
		KD_TASK_CHECK(kd_task_refs(kd_task_test.workers[0]) == 1);
		KD_TASK_CHECK(kd_mutex_task_count() == 1);
		kd_mutex_task_put(kd_task_test.workers[0]);
	}
	/* Drain the production callback before observing its count, reusing the
	 * fixture, or returning an init error that can unload this module's text. */
	rcu_barrier();
	if (ret)
		return ret;
	if (registry_stress) {
		KD_TASK_CHECK(kd_mutex_tasks_idle());
		KD_TASK_CHECK(atomic_read(&kd_mutex_task_test_frees) ==
			      kd_task_test.frees_before + 8193);
		pr_info("kd_mutex registry stress: workers=3 iterations=4096 deferred_frees=%u failures=%d jit_bodies=0\n",
			atomic_read(&kd_mutex_task_test_frees) - kd_task_test.frees_before,
			atomic_read(&kd_task_test.failures));
		return atomic_read(&kd_task_test.failures) ? -EINVAL : 0;
	}
	KD_TASK_CHECK(kd_task_test.acks == 2 && kd_mutex_tasks_idle());
	KD_TASK_CHECK(!kd_mutex_task_count());
	KD_TASK_CHECK(atomic_read(&kd_mutex_task_test_frees) ==
		      kd_task_test.frees_before + 1);
	pr_info("kd_mutex task selftest round: order=%s acks=%u deferred_frees=%u failures=%d jit_bodies=0\n",
		outer_first ? "A-B" : "B-A", kd_task_test.acks,
		atomic_read(&kd_mutex_task_test_frees) -
			kd_task_test.frees_before,
		atomic_read(&kd_task_test.failures));
	return atomic_read(&kd_task_test.failures) ? -EINVAL : 0;
}

int kd_mutex_task_selftest(void)
{
	unsigned int i, j;
	int ret = 0;

	if (!kd_task_test_enabled)
		return 0;
	/* Three distinct online CPUs let the real RCU reader stay non-sleeping
	 * while the physical owner and original waiter exchange native requests. */
	cpus_read_lock();
	for (i = 0; i < ARRAY_SIZE(kd_task_test_cpus); i++) {
		int cpu = kd_task_test_cpus[i];

		if (cpu < 0 || cpu >= nr_cpu_ids || !cpu_online(cpu) ||
		    !cpumask_test_cpu(cpu, current->cpus_ptr)) {
			ret = -EINVAL;
			goto out;
		}
		for (j = 0; j < i; j++) {
			if (cpu == kd_task_test_cpus[j]) {
				ret = -EINVAL;
				goto out;
			}
		}
	}
	ret = kd_task_round(false, true);
	if (!ret)
		ret = kd_task_round(false, false);
	if (!ret)
		ret = kd_task_round(true, false);
	if (!ret)
		pr_info("kd_mutex task selftest: cpus=%d,%d,%d orders=2 acks=4 deferred_frees=2 failures=0 jit_bodies=0\n",
			kd_task_test_cpus[0], kd_task_test_cpus[1],
			kd_task_test_cpus[2]);
out:
	cpus_read_unlock();
	return ret;
}
