// SPDX-License-Identifier: GPL-2.0
/* KDLOCK_SELFTEST only: init queue tests and opt-in runtime resource pressure. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/moduleparam.h>
#include <linux/sched/task.h>

#define KD_SHADOW_TEST_ROUNDS 8

static int kd_shadow_cpus[3] = { 0, 1, 2 };
module_param_array_named(spin_selftest_cpus, kd_shadow_cpus, int, NULL, 0444);
MODULE_PARM_DESC(spin_selftest_cpus,
		 "selftest-only owner, full-shadow head and successor CPUs");

static int kd_shadow_fill_once;
module_param_named(spin_selftest_fill_shadow, kd_shadow_fill_once, int, 0444);
MODULE_PARM_DESC(
	spin_selftest_fill_shadow,
	"selftest-only: fill local shadow with seven real locks at one JIT nested CALL");

static struct {
	raw_spinlock_t origin;
	struct qspinlock *lock;
	struct qspinlock *word;
	raw_spinlock_t held[8];
	raw_spinlock_t probe;
	struct completion start;
	struct completion done[3];
	struct kd_spin_node *head;
	struct kd_spin_node *successor;
	atomic_t failures;
	atomic_t inside;
	unsigned int value;
	unsigned int acquired;
	bool abort;
	bool owner_ready;
	bool head_ready;
	bool head_acquired;
	bool head_releasing;
	bool observed;
	bool successor_acquired;
	bool precheck;
} kd_shadow_test;

static bool kd_shadow_check(bool condition, const char *name, int line)
{
	if (!condition) {
		atomic_inc(&kd_shadow_test.failures);
		pr_err("kd_spin selftest error: cpu=%d line=%d check=%s\n",
		       raw_smp_processor_id(), line, name);
	}
	return condition;
}

#define KD_SHADOW_CHECK(condition) \
	kd_shadow_check(!!(condition), #condition, __LINE__)

static struct {
	struct kd_combiner_state saved;
	struct pt_regs regs;
	struct qspinlock *lock;
	unsigned int held;
	int preempt_count;
	int cpu;
} kd_shadow_pressure;

static void kd_shadow_release_pressure(void)
{
	while (kd_shadow_pressure.held) {
		unsigned int i = --kd_shadow_pressure.held;

		KD_SHADOW_CHECK(kd_spin_nested_shadow_remove(
					(void *)&kd_shadow_test.held[i]) == 0);
		__raw_spin_unlock(&kd_shadow_test.held[i]);
	}
}

bool kd_spin_selftest_shadow_begin(raw_spinlock_t *lock, struct pt_regs *regs,
				   struct kd_exec_frame *frame)
{
	struct shadow_stack *ptr;
	unsigned int i;
	bool ok;

	/* Read-only module parameter: one runtime request, never rearmed in flight. */
	if (READ_ONCE(kd_shadow_fill_once) != 1 || !lock || !regs || !frame ||
	    !frame->executed || !kd_exec_frame_validate(frame) ||
	    preempt_model_preemptible() ||
	    cmpxchg(&kd_shadow_fill_once, 1, 0) != 1)
		return false;

	kd_shadow_pressure.preempt_count = preempt_count();
	preempt_disable();
	kd_shadow_pressure.cpu = smp_processor_id();
	ptr = this_cpu_ptr(&local_shadow_stack);
	kd_shadow_pressure.held = 0;
	kd_shadow_pressure.lock = (void *)lock;
	kd_shadow_pressure.regs = *regs;
	kd_spin_capture_combiner_state(&kd_shadow_pressure.saved, ptr);
	ok = KD_SHADOW_CHECK(kd_spin_lock_stack_depth(ptr) == 1);
	ok &= KD_SHADOW_CHECK(kd_exec_frame_lock_depth(frame) == 1);
	ok &= KD_SHADOW_CHECK(ptr->lock_addr[0] == frame->outer_lock_addr);
	ok &= KD_SHADOW_CHECK(this_cpu_ptr(&kd_spin_nodes[0])->count == 0);
	ok &= KD_SHADOW_CHECK(atomic_read(&kd_shadow_pressure.lock->val) == 0);
	if (!ok)
		goto fail;
	for (i = 0; i < 7; i++) {
		/* Bypass target-task hooks; only these private native locks are added. */
		__raw_spin_lock(&kd_shadow_test.held[i]);
		if (!KD_SHADOW_CHECK(kd_spin_nested_shadow_push(
					     (void *)&kd_shadow_test.held[i]) ==
				     0)) {
			__raw_spin_unlock(&kd_shadow_test.held[i]);
			goto fail;
		}
		kd_shadow_pressure.held++;
	}
	return true;
fail:
	kd_shadow_release_pressure();
	preempt_enable();
	return false;
}

void kd_spin_selftest_shadow_end(struct pt_regs *regs,
				 struct kd_exec_frame *frame, int result)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	unsigned int local = kd_spin_lock_stack_depth(ptr);
	unsigned int held = kd_shadow_pressure.held;
	bool physical = true, unchanged, restored;
	unsigned int i;

	for (i = 0; i < held; i++)
		physical &= raw_spin_is_locked(&kd_shadow_test.held[i]);
	unchanged = !memcmp(regs, &kd_shadow_pressure.regs, sizeof(*regs));
	KD_SHADOW_CHECK(result == -E2BIG &&
			frame->control_call.phase == KD_CALL_PENDING);
	KD_SHADOW_CHECK(held == 7 && local == 8 && physical);
	KD_SHADOW_CHECK(unchanged && frame->executed);
	KD_SHADOW_CHECK(kd_exec_frame_lock_depth(frame) == 1);
	KD_SHADOW_CHECK(smp_processor_id() == kd_shadow_pressure.cpu);
	KD_SHADOW_CHECK(this_cpu_ptr(&kd_spin_nodes[0])->count == 0);
	KD_SHADOW_CHECK(atomic_read(&kd_shadow_pressure.lock->val) == 0);
	KD_SHADOW_CHECK(READ_ONCE(kd_spin_word((void *)frame->outer_lock_addr)
					  ->locked) == _Q_LOCKED_COMBINER_VAL);
	KD_SHADOW_CHECK(
		raw_spin_is_locked((raw_spinlock_t *)frame->outer_lock_addr));

	/* Only test-owned resources leave here; A stays locked for native rendezvous. */
	kd_shadow_release_pressure();
	restored =
		kd_spin_combiner_state_matches(&kd_shadow_pressure.saved, ptr);
	KD_SHADOW_CHECK(restored);
	KD_SHADOW_CHECK(preempt_count() ==
			kd_shadow_pressure.preempt_count + 1);
	pr_info("kd_spin shadow pressure: task=%d entry=%lx outer=%lx lock=%lx target=%lx cpu=%d logical=%u local=%u held=%u physical=%u ret=%d phase=%u regs=%u restored=%u executed=%u failures=%d\n",
		frame->logical_task->pid, frame->entry_ip,
		frame->outer_lock_addr, (unsigned long)kd_shadow_pressure.lock,
		regs->ip, kd_shadow_pressure.cpu,
		kd_exec_frame_lock_depth(frame), local, held, physical, result,
		frame->control_call.phase, unchanged, restored, frame->executed,
		atomic_read(&kd_shadow_test.failures));
	preempt_enable();
}

/* Oracle timeouts release known owners; published queue nodes must still drain. */
#define KD_SHADOW_WAIT(condition)                                       \
	({                                                              \
		unsigned long deadline = jiffies + 5 * HZ;              \
		bool ready;                                             \
		while (!(ready = !!(condition)) &&                      \
		       !READ_ONCE(kd_shadow_test.abort)) {              \
			if (time_after(jiffies, deadline)) {            \
				KD_SHADOW_CHECK(condition);             \
				WRITE_ONCE(kd_shadow_test.abort, true); \
				break;                                  \
			}                                               \
			cpu_relax();                                    \
		}                                                       \
		ready;                                                  \
	})

static void kd_shadow_enter(unsigned int previous)
{
	KD_SHADOW_CHECK(raw_spin_is_locked(&kd_shadow_test.origin));
	KD_SHADOW_CHECK(atomic_cmpxchg(&kd_shadow_test.inside, 0, 1) == 0);
	KD_SHADOW_CHECK(kd_shadow_test.value == previous);
	kd_shadow_test.value++;
	kd_shadow_test.acquired++;
}

static void kd_shadow_unlock(void)
{
	KD_SHADOW_CHECK(atomic_xchg(&kd_shadow_test.inside, 0) == 1);
	kd_spin_unlock(kd_shadow_test.lock);
}

static void kd_shadow_owner(void)
{
	struct kd_spin_node *head, *successor;

	if (!KD_SHADOW_CHECK(kd_spin_trylock(kd_shadow_test.lock))) {
		WRITE_ONCE(kd_shadow_test.abort, true);
		return;
	}
	kd_spin_claim_origin(kd_shadow_test.lock);
	kd_shadow_enter(0);
	smp_store_release(&kd_shadow_test.owner_ready, true);
	if (!KD_SHADOW_WAIT(kd_spin_debug_waiter_count(
				    (raw_spinlock_t *)kd_shadow_test.lock) ==
			    2)) {
		kd_shadow_unlock();
		return;
	}
	head = smp_load_acquire(&kd_shadow_test.head);
	successor = smp_load_acquire(&kd_shadow_test.successor);
	if (!KD_SHADOW_CHECK(head && successor) ||
	    !KD_SHADOW_WAIT(READ_ONCE(head->next) == successor)) {
		WRITE_ONCE(kd_shadow_test.abort, true);
		kd_shadow_unlock();
		return;
	}
	KD_SHADOW_CHECK(READ_ONCE(head->count) == 1);
	KD_SHADOW_CHECK(READ_ONCE(successor->count) == 1);
	KD_SHADOW_CHECK(READ_ONCE(head->rsp) != 0);
	KD_SHADOW_CHECK(READ_ONCE(successor->rsp) != 0);
	kd_shadow_unlock();

	/* A third CPU observes the awakened successor behind a still-owned lock. */
	if (!KD_SHADOW_WAIT(smp_load_acquire(&kd_shadow_test.head_acquired)))
		return;
	KD_SHADOW_CHECK(READ_ONCE(kd_shadow_test.word->locked) == 1);
	KD_SHADOW_CHECK(!READ_ONCE(successor->locked));
	KD_SHADOW_CHECK(!READ_ONCE(successor->completed));
	KD_SHADOW_CHECK(READ_ONCE(successor->count) == 1);
	KD_SHADOW_CHECK(!READ_ONCE(kd_shadow_test.successor_acquired));
	if (!KD_SHADOW_CHECK(!kd_spin_trylock(kd_shadow_test.lock)))
		kd_spin_unlock(kd_shadow_test.lock);
	smp_store_release(&kd_shadow_test.observed, true);
}

static noinline void kd_shadow_return_site(void)
{
	/* An actual text address for a CALL frame; never executed by this test. */
	barrier();
}

static bool kd_shadow_check_admission(void)
{
	unsigned long stack[] = { (unsigned long)kd_shadow_return_site,
				  0xfeed };
	unsigned long outer = (unsigned long)&kd_shadow_test.held[0];
	enum kd_exec_lock_kind kind = KD_EXEC_LOCK_NATIVE;
	struct pt_regs regs = { .ip = (unsigned long)_raw_spin_lock,
				.sp = (unsigned long)stack,
				.ax = 0x1234 };
	struct pt_regs before = regs;
	struct kd_exec_frame *frame;
	bool ok;
	int ret;

	frame = kd_exec_frame_push(&regs, stack[0], outer, current, NULL, 1,
				   kd_read_kernel_gsbase(), current);
	if (!KD_SHADOW_CHECK(frame != NULL))
		return false;
	ret = kd_exec_frame_set_lock_entries(frame, &outer, &kind, NULL, NULL,
					     1);
	ok = KD_SHADOW_CHECK(ret == 0);
	if (!ok)
		goto pop;
	/* Eight real local locks, but only one belongs to this logical frame. */
	ret = kd_spin_jit_nested_lock_ctx(&kd_shadow_test.probe, &regs, frame);
	ok &= KD_SHADOW_CHECK(ret == -E2BIG);
	ok &= KD_SHADOW_CHECK(frame->control_call.phase == KD_CALL_PENDING);
	ok &= KD_SHADOW_CHECK(kd_exec_frame_lock_depth(frame) == 1);
	ok &= KD_SHADOW_CHECK(!memcmp(&regs, &before, sizeof(regs)));
	ok &= KD_SHADOW_CHECK(stack[0] ==
				      (unsigned long)kd_shadow_return_site &&
			      stack[1] == 0xfeed);
	ok &= KD_SHADOW_CHECK(!raw_spin_is_locked(&kd_shadow_test.probe));
pop:
	/* This pre-entry test frame never executes or owns the other seven locks. */
	ok &= KD_SHADOW_CHECK(kd_exec_frame_abort(frame) == 0);
	ok &= KD_SHADOW_CHECK(kd_exec_frame_pop(frame, NULL) == 0);
	return ok;
}

static void kd_shadow_head(void)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	struct kd_combiner_state saved;
	struct kd_spin_node *node = this_cpu_ptr(&kd_spin_nodes[0]);
	unsigned int depth = 0, i;

	if (!KD_SHADOW_WAIT(smp_load_acquire(&kd_shadow_test.owner_ready)))
		return;
	for (i = 0; i < ARRAY_SIZE(kd_shadow_test.held); i++) {
		struct qspinlock *lock = (void *)&kd_shadow_test.held[i];

		raw_spin_lock_nested(&kd_shadow_test.held[i], i);
		if (!KD_SHADOW_CHECK(kd_spin_nested_shadow_push(lock) == 0)) {
			raw_spin_unlock(&kd_shadow_test.held[i]);
			WRITE_ONCE(kd_shadow_test.abort, true);
			goto out;
		}
		depth++;
		KD_SHADOW_CHECK(raw_spin_is_locked(&kd_shadow_test.held[i]));
	}
	KD_SHADOW_CHECK(!kd_spin_nested_shadow_has_space());
	kd_shadow_test.precheck = kd_shadow_check_admission();
	if (!kd_shadow_test.precheck) {
		WRITE_ONCE(kd_shadow_test.abort, true);
		goto out;
	}
	kd_spin_capture_combiner_state(&saved, ptr);
	smp_store_release(&kd_shadow_test.head, node);
	smp_store_release(&kd_shadow_test.head_ready, true);

	/* Real stack switch, real node reservation and real xchg-tail publication. */
	kd_spin_lock_slowpath(kd_shadow_test.lock, 0);
	KD_SHADOW_CHECK(kd_spin_combiner_state_matches(&saved, ptr));
	KD_SHADOW_CHECK(node->count == 0);
	KD_SHADOW_CHECK(node->rsp &&
			node->rsp == this_cpu_ptr(&kd_spin_native_inputs)->rsp);
	KD_SHADOW_CHECK(READ_ONCE(kd_shadow_test.word->locked) == 1);
	kd_shadow_enter(1);
	smp_store_release(&kd_shadow_test.head_acquired, true);
	KD_SHADOW_WAIT(smp_load_acquire(&kd_shadow_test.observed));
	KD_SHADOW_CHECK(!READ_ONCE(kd_shadow_test.successor_acquired));
	smp_store_release(&kd_shadow_test.head_releasing, true);
	kd_shadow_unlock();
out:
	while (depth) {
		struct qspinlock *lock = (void *)&kd_shadow_test.held[--depth];

		KD_SHADOW_CHECK(kd_spin_nested_shadow_remove(lock) == 0);
		raw_spin_unlock(&kd_shadow_test.held[depth]);
	}
}

static void kd_shadow_successor(void)
{
	struct kd_spin_node *node = this_cpu_ptr(&kd_spin_nodes[0]);

	if (!KD_SHADOW_WAIT(smp_load_acquire(&kd_shadow_test.head_ready) &&
			    kd_spin_debug_waiter_count(
				    (raw_spinlock_t *)kd_shadow_test.lock) ==
				    1))
		return;
	smp_store_release(&kd_shadow_test.successor, node);
	kd_spin_lock_slowpath(kd_shadow_test.lock, 0);
	KD_SHADOW_CHECK(smp_load_acquire(&kd_shadow_test.head_releasing));
	KD_SHADOW_CHECK(node->count == 0);
	KD_SHADOW_CHECK(node->rsp &&
			node->rsp == this_cpu_ptr(&kd_spin_native_inputs)->rsp);
	KD_SHADOW_CHECK(READ_ONCE(kd_shadow_test.word->tail) == 0);
	kd_shadow_enter(2);
	smp_store_release(&kd_shadow_test.successor_acquired, true);
	kd_shadow_unlock();
}

static int kd_shadow_worker(void *argument)
{
	unsigned long role = (unsigned long)argument;
	struct kd_spin_ref ref = { 0 };

	wait_for_completion(&kd_shadow_test.start);
	if (READ_ONCE(kd_shadow_test.abort))
		goto done;
	preempt_disable();
	BUG_ON(kd_spin_entry_begin(&kd_shadow_test.origin, KD_SPIN_ENTRY_HOOK,
				   &ref));
	KD_SHADOW_CHECK(smp_processor_id() == kd_shadow_cpus[role]);
	KD_SHADOW_CHECK(this_cpu_ptr(&kd_spin_nodes[0])->count == 0);
	KD_SHADOW_CHECK(!kd_exec_current_frame());
	KD_SHADOW_CHECK(
		!kd_spin_lock_stack_depth(this_cpu_ptr(&local_shadow_stack)));
	if (role == 0)
		kd_shadow_owner();
	else if (role == 1)
		kd_shadow_head();
	else
		kd_shadow_successor();
	KD_SHADOW_CHECK(this_cpu_ptr(&kd_spin_nodes[0])->count == 0);
	KD_SHADOW_CHECK(!kd_exec_current_frame());
	KD_SHADOW_CHECK(
		!kd_spin_lock_stack_depth(this_cpu_ptr(&local_shadow_stack)));
	if (kd_spin_entry_find(&kd_shadow_test.origin, &ref))
		BUG_ON(kd_spin_entry_end(&ref));
	preempt_enable();
done:
	complete(&kd_shadow_test.done[role]);
	return 0;
}

static int kd_shadow_round(unsigned int round)
{
	struct task_struct *workers[3] = {};
	unsigned int i;
	int ret = 0;

	memset(&kd_shadow_test, 0, sizeof(kd_shadow_test));
	raw_spin_lock_init(&kd_shadow_test.origin);
	kd_shadow_test.lock = (void *)&kd_shadow_test.origin;
	if (!kd_spin_gate_get(&kd_shadow_test.origin))
		return -ENOMEM;
	kd_shadow_test.word = kd_spin_word(kd_shadow_test.lock);
	init_completion(&kd_shadow_test.start);
	for (i = 0; i < ARRAY_SIZE(kd_shadow_test.held); i++)
		raw_spin_lock_init(&kd_shadow_test.held[i]);
	raw_spin_lock_init(&kd_shadow_test.probe);
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		init_completion(&kd_shadow_test.done[i]);
		workers[i] = kthread_create(kd_shadow_worker,
					    (void *)(unsigned long)i,
					    "kd_shadow_%u", i);
		if (IS_ERR(workers[i])) {
			ret = PTR_ERR(workers[i]);
			workers[i] = NULL;
			WRITE_ONCE(kd_shadow_test.abort, true);
			break;
		}
		get_task_struct(workers[i]);
		kthread_bind(workers[i], kd_shadow_cpus[i]);
		wake_up_process(workers[i]);
	}
	complete_all(&kd_shadow_test.start);
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		if (!workers[i])
			continue;
		if (!wait_for_completion_timeout(&kd_shadow_test.done[i],
						 10 * HZ)) {
			pr_err("kd_spin selftest: worker %u not drained; recovery may be required\n",
			       i);
			WRITE_ONCE(kd_shadow_test.abort, true);
			ret = -ETIMEDOUT;
		}
		/* Never free module code while a published queue node is still live. */
		kthread_stop(workers[i]);
		put_task_struct(workers[i]);
	}
	if (ret)
		return ret;
	KD_SHADOW_CHECK(atomic_read(&kd_shadow_test.word->val) == 0);
	KD_SHADOW_CHECK(!raw_spin_is_locked(&kd_shadow_test.origin));
	KD_SHADOW_CHECK(atomic_read(&kd_shadow_test.inside) == 0);
	KD_SHADOW_CHECK(kd_shadow_test.value == 3 &&
			kd_shadow_test.acquired == 3);
	KD_SHADOW_CHECK(kd_shadow_test.precheck && kd_shadow_test.observed &&
			kd_shadow_test.successor_acquired &&
			!kd_shadow_test.abort);
	KD_SHADOW_CHECK(kd_spin_debug_waiter_count(
				(raw_spinlock_t *)kd_shadow_test.lock) == 0);
	for (i = 0; i < ARRAY_SIZE(kd_shadow_test.held); i++)
		KD_SHADOW_CHECK(!raw_spin_is_locked(&kd_shadow_test.held[i]));
	pr_info("kd_spin selftest: round=%u cpus=%d,%d,%d held=8 precheck=%u acquired=%u observed=%u value=%u failures=%d\n",
		round, kd_shadow_cpus[0], kd_shadow_cpus[1], kd_shadow_cpus[2],
		kd_shadow_test.precheck, kd_shadow_test.acquired,
		kd_shadow_test.observed, kd_shadow_test.value,
		atomic_read(&kd_shadow_test.failures));
	return atomic_read(&kd_shadow_test.failures) ? -EINVAL : 0;
}

static int kd_spin_shadow_selftest(void)
{
	unsigned int i, j;
	int ret = 0;

	if (kd_shadow_fill_once < 0 || kd_shadow_fill_once > 1)
		return -EINVAL;
	if (kd_frame_capacity_probe && !kd_frame_trace)
		return -EINVAL;
	if ((kd_shadow_fill_once || kd_frame_trace) &&
	    preempt_model_preemptible())
		return -EOPNOTSUPP;
#ifdef CONFIG_DEBUG_LOCK_ALLOC
	/* Runtime pressure uses the matching guest's unhooked plain-lock helpers. */
	if (kd_shadow_fill_once)
		return -EOPNOTSUPP;
#endif
	cpus_read_lock();
	for (i = 0; i < ARRAY_SIZE(kd_shadow_cpus); i++) {
		if (kd_shadow_cpus[i] < 0 || kd_shadow_cpus[i] >= nr_cpu_ids ||
		    !cpu_online(kd_shadow_cpus[i])) {
			ret = -EINVAL;
			goto out;
		}
		for (j = 0; j < i; j++) {
			if (kd_shadow_cpus[i] == kd_shadow_cpus[j]) {
				ret = -EINVAL;
				goto out;
			}
		}
	}
	for (i = 0; i < KD_SHADOW_TEST_ROUNDS; i++) {
		ret = kd_shadow_round(i);
		if (ret)
			break;
	}
out:
	cpus_read_unlock();
	return ret;
}
