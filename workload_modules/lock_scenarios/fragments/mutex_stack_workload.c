// SPDX-License-Identifier: GPL-2.0
#include <linux/sched/task_stack.h>

/* Opt-in extension of the seven-role mode-4 workload. A native B owner writes
 * a deliberately shared, live caller-local word only after the real combiner
 * has queued on B. No frame, CALL token or fault-injection knob is modified. */
#define KD_MUTEX_STACK_OLD 0x123456789abcdef0UL
#define KD_MUTEX_STACK_NEW 0x0fedcba987654321UL
static bool native_stack_change;
static bool native_stack_armed;
module_param(native_stack_change, bool, 0444);
module_param(native_stack_armed, bool, 0644);
MODULE_PARM_DESC(
	native_stack_change,
	"Mode 4 stage 4: native B owner changes the waiter's exposed stack word");
MODULE_PARM_DESC(native_stack_armed,
		 "Publish the stack word only after outer-A JIT promotion");

static struct {
	struct kd_resume_record *record;
	volatile unsigned long *slot;
	unsigned long owner;
	unsigned int writes, reads, completed;
} kd_stack_change;

static noinline void kd_stack_change_prepare(struct kd_resume_record *record,
					     volatile unsigned long *slot)
{
	if (!record || record->task != current || kd_stack_change.record) {
		atomic_inc(&resume_failures);
		return;
	}
	kd_stack_change.slot = slot;
	/* Publication precedes A's enqueue. The waiter keeps this local alive
	 * through both unlock ACKs; the B owner must not write until it sees the
	 * distinct physical A owner waiting in B's native wait_list. */
	smp_store_release(&kd_stack_change.record, record);
	pr_info("kd_stack publish: task=%d waiter=%lx slot=%lx old=%lx record=%lu\n",
		current->pid, (unsigned long)current, (unsigned long)slot,
		READ_ONCE(*slot), (unsigned long)(record - resume_records));
}

static noinline void kd_stack_change_wait(void)
{
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		struct kd_resume_record *record =
			smp_load_acquire(&kd_stack_change.record);
		unsigned long owner = kd_test_mutex_owner(&nested_mutex_a);
		struct mutex_waiter *waiter;
		unsigned long flags;
		bool found = false;

		raw_spin_lock_irqsave(&nested_mutex_b.wait_lock, flags);
		list_for_each_entry(waiter, &nested_mutex_b.wait_list, list) {
			if (record && owner &&
			    (unsigned long)waiter->task == owner &&
			    waiter->task != record->task) {
				found = true;
				break;
			}
		}
		raw_spin_unlock_irqrestore(&nested_mutex_b.wait_lock, flags);
		if (found) {
			volatile unsigned long *slot = kd_stack_change.slot;
			unsigned long address = (unsigned long)slot;
			unsigned long base =
				(unsigned long)task_stack_page(record->task);
			bool valid =
				base && base <= ~0UL - THREAD_SIZE &&
				address >= base &&
				address <= base + THREAD_SIZE - sizeof(*slot) &&
				IS_ALIGNED(address, sizeof(*slot)) &&
				owner != (unsigned long)current &&
				kd_test_mutex_owner(&nested_mutex_a) == owner &&
				kd_test_mutex_owner(&nested_mutex_b) ==
					(unsigned long)current &&
				!strcmp(current->comm, "kd_native") &&
				READ_ONCE(record->before) == 1 &&
				!READ_ONCE(record->called) &&
				!READ_ONCE(record->after) &&
				!kd_stack_change.writes;
			unsigned long old = valid ? READ_ONCE(*slot) : 0;

			valid = valid && old == KD_MUTEX_STACK_OLD;
			if (valid) {
				kd_stack_change.owner = owner;
				WRITE_ONCE(*slot, KD_MUTEX_STACK_NEW);
				smp_store_release(&kd_stack_change.writes, 1);
			} else {
				atomic_inc(&resume_failures);
			}
			pr_info("kd_stack changed: task=%d waiter=%lx slot=%lx old=%lx new=%lx combiner=%lx combiner_pid=%d holder=%lx holder_pid=%d holder_comm=%s outer=%lx lock=%lx queued=1 valid=%u\n",
				record->task->pid, (unsigned long)record->task,
				address, old, valid ? READ_ONCE(*slot) : 0,
				owner, ((struct task_struct *)owner)->pid,
				(unsigned long)current, current->pid,
				current->comm, (unsigned long)&nested_mutex_a,
				(unsigned long)&nested_mutex_b, valid);
			return;
		}
		if (time_after_eq(jiffies, deadline)) {
			/* Release B normally even when the expected topology fails.
			 * Missing the real wait-list observation is a failed test. */
			atomic_inc(&resume_failures);
			pr_err("kd_stack error: combiner did not queue on B\n");
			return;
		}
		cond_resched();
	}
}

static __attribute__((noipa)) noinline void
kd_stack_change_observe(struct kd_resume_record *record, unsigned long value)
{
	unsigned long a_owner = kd_test_mutex_owner(&nested_mutex_a);
	unsigned long b_owner = kd_test_mutex_owner(&nested_mutex_b);
	bool valid = record && record == kd_stack_change.record &&
		     record->task == current &&
		     smp_load_acquire(&kd_stack_change.writes) == 1 &&
		     !kd_stack_change.reads && value == KD_MUTEX_STACK_NEW &&
		     a_owner == kd_stack_change.owner && b_owner == a_owner &&
		     a_owner && a_owner != (unsigned long)current &&
		     record->before == 1 && !record->called && !record->after;

	/* This native-only observer is after the mutex CALL. Its own CALL miss
	 * could also reach native code, so the external oracle additionally
	 * requires the distinct stack-change exit and an unchanged NORMAL entry. */
	if (!valid)
		atomic_inc(&resume_failures);
	kd_stack_change.reads++;
	pr_info("kd_stack observed: task=%d waiter=%lx value=%lx a_owner=%lx b_owner=%lx reads=%u valid=%u\n",
		current->pid, (unsigned long)current, value, a_owner, b_owner,
		kd_stack_change.reads, valid);
}

static noinline void kd_stack_change_complete(struct kd_resume_record *record)
{
	bool valid =
		record && record == kd_stack_change.record &&
		record->task == current && kd_stack_change.reads == 1 &&
		!kd_stack_change.completed && record->before == 1 &&
		record->called == 1 && record->after == 1 &&
		record->value ==
			((((unsigned long)(record - resume_records) + 1) * 3 +
			  17) ^
			 0x5a5a);

	if (!valid)
		atomic_inc(&resume_failures);
	kd_stack_change.completed++;
	/* Called after A's unlock returns, while the local is still alive. The
	 * unload report below only uses scalars; it never reads an expired slot. */
	pr_info("kd_stack complete: task=%d completed=%u valid=%u\n",
		current->pid, kd_stack_change.completed, valid);
}

static void kd_stack_change_report(void)
{
	if (native_stack_change)
		pr_info("kd_stack stats: writes=%u reads=%u completed=%u\n",
			kd_stack_change.writes, kd_stack_change.reads,
			kd_stack_change.completed);
}
