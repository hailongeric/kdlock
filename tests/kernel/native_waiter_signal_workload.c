// SPDX-License-Identifier: GPL-2.0
/* Workload only: a real signal must not abandon an uninterruptible native
 * suffix after JIT stores. B stays owned until the original waiter is observed
 * still queued with its signal pending; no signal flag or lock word is forged.
 */
#include <linux/sched/signal.h>

static int native_waiter_signal;
module_param(native_waiter_signal, int, 0444);
MODULE_PARM_DESC(
	native_waiter_signal,
	"Mode 4 stage 4: send SIGUSR1(10)/SIGKILL(9) to the native B waiter");

static struct {
	struct kd_resume_record *record;
	unsigned int delivered, samples, acquired, completed, failures;
} kd_waiter_signal;

static bool kd_waiter_signal_check(bool valid, int line)
{
	if (!valid) {
		kd_waiter_signal.failures++;
		atomic_inc(&resume_failures);
		pr_err("kd_waiter signal error: line=%d task=%d signal=%d\n",
		       line, current->pid, native_waiter_signal);
	}
	return valid;
}
#define KD_WAITER_SIGNAL_CHECK(condition) \
	kd_waiter_signal_check(!!(condition), __LINE__)

static bool kd_waiter_signal_queued(struct task_struct *task)
{
	struct mutex_waiter *waiter;
	unsigned long flags;
	bool queued = false;

	/* Read the real Linux wait_list under its guard, never a pre-CALL flag. */
	raw_spin_lock_irqsave(&nested_mutex_b.wait_lock, flags);
	list_for_each_entry(waiter, &nested_mutex_b.wait_list, list) {
		if (waiter->task == task) {
			queued = true;
			break;
		}
	}
	raw_spin_unlock_irqrestore(&nested_mutex_b.wait_lock, flags);
	return queued;
}

static void kd_waiter_signal_send(struct kd_resume_record *record)
{
	unsigned long deadline = jiffies + 5 * HZ;
	struct task_struct *task = record->task;
	bool fatal = native_waiter_signal == SIGKILL;

	if (!native_waiter_signal)
		return;
	if (!KD_WAITER_SIGNAL_CHECK(!kd_waiter_signal.record &&
				    task != current && task->pid == task->tgid))
		return;
	kd_waiter_signal.record = record;
	if (!KD_WAITER_SIGNAL_CHECK(send_sig(native_waiter_signal, task, 0) ==
				    0))
		return;
	kd_waiter_signal.delivered++;
	/* A single-thread ioctl client cannot exit while this uninterruptible B
	 * acquisition is unfinished. Do not add a test-owned task ref that could
	 * conceal a missing production lifetime reference after the final ACK.
	 */
	while (kd_waiter_signal.samples < 128) {
		bool pending = signal_pending(task);
		bool is_fatal = fatal_signal_pending(task);

		if (!KD_WAITER_SIGNAL_CHECK(
			    kd_waiter_signal_queued(task) &&
			    kd_test_mutex_owner(&nested_mutex_a) ==
				    pending_mutex_a_owner &&
			    kd_test_mutex_owner(&nested_mutex_b) ==
				    (unsigned long)current &&
			    !READ_ONCE(task->exit_state) &&
			    READ_ONCE(record->before) == 1 &&
			    !READ_ONCE(record->called) &&
			    !READ_ONCE(record->after)))
			return;
		if (pending && is_fatal == fatal &&
		    (READ_ONCE(task->__state) & TASK_UNINTERRUPTIBLE))
			kd_waiter_signal.samples++;
		if (!KD_WAITER_SIGNAL_CHECK(time_before(jiffies, deadline)))
			return;
		cond_resched();
	}
	pr_info("kd_waiter signal queued: task=%d signal=%d samples=%u pending=1 fatal=%u queued=1 a_owner=%lx b_owner=%lx before=%u called=%u after=%u\n",
		task->pid, native_waiter_signal, kd_waiter_signal.samples,
		fatal, pending_mutex_a_owner, (unsigned long)current,
		record->before, record->called, record->after);
}

static void kd_waiter_signal_acquired(struct kd_resume_record *record)
{
	if (!native_waiter_signal || !record ||
	    record != kd_waiter_signal.record)
		return;
	KD_WAITER_SIGNAL_CHECK(
		record->task == current && kd_waiter_signal.delivered == 1 &&
		kd_waiter_signal.samples == 128 && !kd_waiter_signal.acquired &&
		signal_pending(current) &&
		!!fatal_signal_pending(current) ==
			(native_waiter_signal == SIGKILL) &&
		kd_test_mutex_owner(&nested_mutex_a) == pending_mutex_a_owner &&
		kd_test_mutex_owner(&nested_mutex_b) == (unsigned long)current);
	kd_waiter_signal.acquired++;
	pr_info("kd_waiter signal acquired: task=%d signal=%d pending=%u fatal=%u\n",
		current->pid, native_waiter_signal, !!signal_pending(current),
		!!fatal_signal_pending(current));
}

/* This marker executes after the real A unlock returns from the owner ACK.
 * A may still belong to its batch owner; require only that this waiter owns
 * neither lock. Never access record->task later after a fatal userspace exit.
 */
static noinline void kd_waiter_signal_complete(struct kd_resume_record *record)
{
	unsigned long expected;

	/* kd_resume_begin already reports record exhaustion; do not dereference
	 * its NULL result just because the runtime signal probe is still unarmed.
	 */
	if (!native_waiter_signal || !record ||
	    record != kd_waiter_signal.record)
		return;
	expected = (((unsigned long)(record - resume_records) + 1) * 3 + 17) ^
		   0x5a5a;
	KD_WAITER_SIGNAL_CHECK(
		record->task == current && kd_waiter_signal.acquired == 1 &&
		!kd_waiter_signal.completed && signal_pending(current) &&
		!!fatal_signal_pending(current) ==
			(native_waiter_signal == SIGKILL) &&
		record->before == 1 && record->called == 1 &&
		record->after == 1 && record->value == expected &&
		kd_test_mutex_owner(&nested_mutex_a) !=
			(unsigned long)current &&
		kd_test_mutex_owner(&nested_mutex_b) != (unsigned long)current);
	kd_waiter_signal.completed++;
	pr_info("kd_waiter signal complete: task=%d signal=%d pending=%u fatal=%u before=%u called=%u after=%u record=%lu value=%lx\n",
		current->pid, native_waiter_signal, !!signal_pending(current),
		!!fatal_signal_pending(current), record->before, record->called,
		record->after, (unsigned long)(record - resume_records),
		record->value);
}

static void kd_waiter_signal_report(void)
{
	if (!native_waiter_signal)
		return;
	KD_WAITER_SIGNAL_CHECK(kd_waiter_signal.delivered == 1 &&
			       kd_waiter_signal.samples == 128 &&
			       kd_waiter_signal.acquired == 1 &&
			       kd_waiter_signal.completed == 1);
	pr_info("kd_waiter signal stats: signal=%d delivered=%u samples=%u acquired=%u completed=%u failures=%u\n",
		native_waiter_signal, kd_waiter_signal.delivered,
		kd_waiter_signal.samples, kd_waiter_signal.acquired,
		kd_waiter_signal.completed, kd_waiter_signal.failures);
}

#undef KD_WAITER_SIGNAL_CHECK
