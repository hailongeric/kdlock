// SPDX-License-Identifier: GPL-2.0
/* Included only by the workload module. No fabricated signals or queue words. */
#include <linux/delay.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>

#define KD_SIGNAL_ROLE 0x10000000U
static unsigned int mutex_signal_probe;
module_param(mutex_signal_probe, uint, 0444);
MODULE_PARM_DESC(
	mutex_signal_probe,
	"Mode 3 signal probe: 1/2=interruptible head/tail, 3/4=killable head/tail");
static bool mutex_signal_armed;
module_param(mutex_signal_armed, bool, 0644);
static bool mutex_signal_abort;
module_param(mutex_signal_abort, bool, 0644);
static unsigned int mutex_signal_phase;
module_param(mutex_signal_phase, uint, 0444);
static unsigned int mutex_signal_private;
module_param(mutex_signal_private, uint, 0444);
module_param(mutex_signal_race, bool, 0444);
static bool mutex_signal_release;
module_param(mutex_signal_release, bool, 0644);
static bool mutex_signal_handoff;
module_param(mutex_signal_handoff, bool, 0444);

static struct {
	struct task_struct *task;
	int result;
	unsigned int entered, unlocked;
	bool finished;
} signal_participants[2]; /* 0=signal candidate, 1=survivor */
static unsigned long signal_owner;
static int signal_owner_pid;
static atomic_t signal_failures = ATOMIC_INIT(0);
static unsigned int signal_nonfatal_checks;

static bool kd_signal_check(bool valid, int line)
{
	if (!valid) {
		atomic_inc(&signal_failures);
		pr_err("kd_signal error: line=%d phase=%u task=%d owner=%lx\n",
		       line, mutex_signal_phase, current->pid,
		       kd_test_mutex_owner(&global_mutex));
	}
	return valid;
}
#define KD_SIGNAL_CHECK(condition) kd_signal_check(!!(condition), __LINE__)

struct kd_signal_queue {
	unsigned int count;
	int cancel, survivor;
	unsigned long owner, word;
};

static struct kd_signal_queue kd_signal_queue(void)
{
	struct kd_signal_queue result = { .cancel = -1, .survivor = -1 };
	struct mutex_waiter *waiter;
	unsigned long flags;

	raw_spin_lock_irqsave(&global_mutex.wait_lock, flags);
	result.word = atomic_long_read(&global_mutex.owner);
	result.owner = result.word & ~0x7UL;
	list_for_each_entry(waiter, &global_mutex.wait_list, list) {
		if (waiter->task == READ_ONCE(signal_participants[0].task))
			result.cancel = result.count;
		if (waiter->task == READ_ONCE(signal_participants[1].task))
			result.survivor = result.count;
		result.count++;
	}
	raw_spin_unlock_irqrestore(&global_mutex.wait_lock, flags);
	return result;
}

static bool kd_signal_pause(unsigned long deadline)
{
	if (READ_ONCE(mutex_signal_abort))
		return false;
	if (!KD_SIGNAL_CHECK(time_before(jiffies, deadline)))
		return false;
	usleep_range(1000, 2000);
	return true;
}

static bool kd_signal_wait_queue(unsigned int count, int cancel, int survivor)
{
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		struct kd_signal_queue q = kd_signal_queue();

		if (!KD_SIGNAL_CHECK(q.owner == signal_owner &&
				     !preempt_count() && !irqs_disabled()))
			return false;
		if (q.count == count && q.cancel == cancel &&
		    q.survivor == survivor) {
			pr_info("kd_signal queue: count=%u cancel=%d survivor=%d owner=%lx waiter=%d\n",
				q.count, q.cancel, q.survivor, q.owner,
				current->pid);
			return true;
		}
		if (!kd_signal_pause(deadline))
			return false;
	}
}

static bool kd_signal_request_handoff(bool head)
{
	struct task_struct *first =
		READ_ONCE(signal_participants[head ? 0 : 1].task);
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		struct kd_signal_queue q = kd_signal_queue();

		if (!KD_SIGNAL_CHECK(q.owner == signal_owner && q.count == 2 &&
				     q.cancel == (head ? 0 : 1) &&
				     q.survivor == (head ? 1 : 0)))
			return false;
		/* Linux's resumed first waiter requests HANDOFF itself. Never write
		 * its owner word, queue links or task state from this fixture. */
		if (q.word & 0x2UL) {
			pr_info("kd_signal handoff: first=%d owner=%lx word=%lx queued=%u\n",
				first->pid, q.owner, q.word, q.count);
			return true;
		}
		wake_up_process(first);
		if (!kd_signal_pause(deadline))
			return false;
	}
}

static void kd_signal_owner_gate(void)
{
	unsigned long deadline = jiffies + 10 * HZ;
	struct kd_signal_queue q = kd_signal_queue();

	if (!KD_SIGNAL_CHECK(q.owner == signal_owner && q.count == 2 &&
			     !preempt_count() && !irqs_disabled()))
		return;
	pr_info("kd_signal gate: task=%d owner=%lx word=%lx queued=%u\n",
		current->pid, q.owner, q.word, q.count);
	smp_store_release(&mutex_signal_phase, 7);
	while (!READ_ONCE(mutex_signal_release)) {
		if (READ_ONCE(mutex_signal_abort) ||
		    !KD_SIGNAL_CHECK(time_before(jiffies, deadline)))
			return;
		cpu_relax();
		cond_resched();
	}
	smp_store_release(&mutex_signal_phase, 8);
}

/* Bracket the real owner's mutex_unlock, not the logical waiter's ACK. */
static noinline void kd_signal_owner_unlock(bool done)
{
	struct kd_signal_queue q;
	u64 ns;

	if (current->pid != READ_ONCE(signal_owner_pid))
		return;
	ns = ktime_get_ns();
	q = kd_signal_queue();
	if (!done)
		KD_SIGNAL_CHECK(mutex_signal_phase == 8 &&
				q.owner == signal_owner && q.survivor >= 0 &&
				q.count >= 1 && q.count <= 2 &&
				(!mutex_signal_handoff || (q.word & 0x2UL)));
	pr_info("kd_signal unlock: done=%u task=%d owner=%lx word=%lx queued=%u ns=%llu\n",
		done, current->pid, q.owner, q.word, q.count, ns);
	if (done)
		smp_store_release(&mutex_signal_phase, 9);
}

/* Hold L until three private nodes queue: combiner, delegated waiter and tail.
 * The initial holder releases L normally; the queue head becomes its real owner. */
static void kd_signal_hold(struct kd_resume_record *record)
{
	unsigned long owner, deadline, observed = 0;
	bool head = mutex_signal_probe & 1;
	struct task_struct *cancel;

	if (!mutex_signal_probe || !READ_ONCE(mutex_signal_armed))
		return;
	owner = kd_test_mutex_owner(&global_mutex);
	if (owner == (unsigned long)current) {
		if (mutex_signal_race && mutex_signal_phase == 6 &&
		    current->pid == signal_owner_pid) {
			kd_signal_owner_gate();
			return;
		}
		if (mutex_signal_phase)
			return;
		smp_store_release(&mutex_signal_phase, 1);
		deadline = jiffies + 10 * HZ;
		for (;;) {
			int queued = kd_mutex_debug_waiter_count(&global_mutex);

			if (!KD_SIGNAL_CHECK(queued >= 0))
				return;
			smp_store_release(&mutex_signal_private, queued);
			if (queued == 3)
				break;
			if (!kd_signal_pause(deadline))
				return;
		}
		return;
	}
	if (!KD_SIGNAL_CHECK(owner && record->task == current &&
			     mutex_signal_phase == 1))
		return;
	signal_owner = owner;
	/* This task cannot exit while retaining the original mutex. */
	signal_owner_pid = ((struct task_struct *)owner)->pid;
	pr_info("kd_signal borrowed: waiter=%d task=%lx owner_pid=%d owner=%lx lock=%lx\n",
		current->pid, (unsigned long)current, signal_owner_pid, owner,
		(unsigned long)&global_mutex);
	smp_store_release(&mutex_signal_phase, 2);
	if (!kd_signal_wait_queue(1, head ? 0 : -1, head ? -1 : 0))
		return;
	smp_store_release(&mutex_signal_phase, 3);
	if (!kd_signal_wait_queue(2, head ? 0 : 1, head ? 1 : 0))
		return;
	cancel = READ_ONCE(signal_participants[0].task);
	smp_store_release(&mutex_signal_phase, 4);
	deadline = jiffies + 10 * HZ;
	if (mutex_signal_probe >= 3) {
		/* A pending nonfatal signal must leave TASK_KILLABLE in the real
		 * queue for a bounded observation window, not merely at one instant. */
		for (;;) {
			struct kd_signal_queue q = kd_signal_queue();

			if (!KD_SIGNAL_CHECK(
				    q.owner == owner && q.count == 2 &&
				    q.cancel == (head ? 0 : 1) &&
				    q.survivor == (head ? 1 : 0) &&
				    !smp_load_acquire(
					    &signal_participants[0].finished)))
				return;
			if (signal_pending(cancel) &&
			    !fatal_signal_pending(cancel) &&
			    READ_ONCE(cancel->__state) == TASK_KILLABLE) {
				if (!observed)
					observed = jiffies;
				signal_nonfatal_checks++;
				if (time_after_eq(jiffies,
						  observed + max(1, HZ / 20)))
					break;
			}
			if (!kd_signal_pause(deadline))
				return;
		}
		pr_info("kd_signal nonfatal: cancel=%d checks=%u pending=1 fatal=0 queued=2 owner=%lx\n",
			cancel->pid, signal_nonfatal_checks, owner);
		smp_store_release(&mutex_signal_phase, 5);
	}
	if (mutex_signal_race) {
		if (mutex_signal_handoff && !kd_signal_request_handoff(head))
			return;
		pr_info("kd_signal ready: waiter=%d owner=%lx handoff=%u\n",
			current->pid, owner, mutex_signal_handoff);
		smp_store_release(&mutex_signal_phase, 6);
		return;
	}
	deadline = jiffies + 10 * HZ;
	while (!smp_load_acquire(&signal_participants[0].finished))
		if (!kd_signal_pause(deadline))
			return;
	if (!KD_SIGNAL_CHECK(signal_participants[0].result == -EINTR &&
			     !signal_participants[0].entered &&
			     !signal_participants[0].unlocked))
		return;
	if (!kd_signal_wait_queue(1, -1, 0))
		return;
	pr_info("kd_signal cancelled: cancel=%d waiter=%d ret=%d owner=%lx entered=0 unlocked=0\n",
		cancel->pid, current->pid, signal_participants[0].result,
		owner);
	smp_store_release(&mutex_signal_phase, 6);
}

static int kd_signal_run(unsigned int role)
{
	int ret;
	u64 returned_ns;
	unsigned long acquired_owner;
	bool pending, fatal;

	if (role > 1 || !READ_ONCE(mutex_signal_armed) ||
	    smp_load_acquire(&mutex_signal_phase) < 2)
		return -EINVAL;
	get_task_struct(current);
	if (cmpxchg(&signal_participants[role].task, NULL, current)) {
		put_task_struct(current);
		return -EALREADY;
	}
	pr_info("kd_signal arrive: role=%u task=%d comm=%s\n", role,
		current->pid, current->comm);
	ret = mutex_signal_probe <= 2 ?
		      mutex_lock_interruptible(&global_mutex) :
		      mutex_lock_killable(&global_mutex);
	returned_ns = ktime_get_ns();
	acquired_owner = kd_test_mutex_owner(&global_mutex);
	pending = signal_pending(current);
	fatal = fatal_signal_pending(current);
	if (!ret) {
		signal_participants[role].entered++;
		KD_SIGNAL_CHECK((role == 1 || mutex_signal_race) &&
				acquired_owner == (unsigned long)current);
		if (atomic_inc_return(&mutex_inside) != 1)
			atomic_inc(&mutex_overlaps);
		kd_cs_step(KD_CS_MUTEX_GLOBAL);
		atomic_dec(&mutex_inside);
		mutex_unlock(&global_mutex);
		signal_participants[role].unlocked++;
	}
	KD_SIGNAL_CHECK(!preempt_count() && !irqs_disabled());
	signal_participants[role].result = ret;
	pr_info("kd_signal result: role=%u task=%d ret=%d entered=%u unlocked=%u ns=%llu pending=%u fatal=%u self=%lx owner=%lx\n",
		role, current->pid, ret, signal_participants[role].entered,
		signal_participants[role].unlocked, returned_ns, pending, fatal,
		(unsigned long)current, acquired_owner);
	smp_store_release(&signal_participants[role].finished, true);
	return ret;
}

static int kd_signal_init(void)
{
	if (mutex_signal_probe > 4 || mutex_signal_armed ||
	    mutex_signal_release ||
	    (mutex_signal_race && !mutex_signal_probe) ||
	    (mutex_signal_handoff && !mutex_signal_race) ||
	    (mutex_signal_probe &&
	     (native_resume_stage != 1 || native_resume_rename ||
	      native_pending_contended || mixed_lock_probe ||
	      context_lock_probe || spin_route_probe || spin_chain_depth)))
		return -EINVAL;
	return 0;
}

static void kd_signal_report(void)
{
	struct kd_signal_queue q;
	int i;

	if (!mutex_signal_probe)
		return;
	q = kd_signal_queue();
	KD_SIGNAL_CHECK(
		mutex_signal_phase == (mutex_signal_race ? 9 : 6) &&
		!mutex_signal_abort && !q.word && !q.count &&
		signal_participants[0].finished &&
		(signal_participants[0].result == -EINTR ||
		 (mutex_signal_race && !signal_participants[0].result)) &&
		signal_participants[0].entered ==
			!signal_participants[0].result &&
		signal_participants[0].unlocked ==
			!signal_participants[0].result &&
		signal_participants[1].finished &&
		!signal_participants[1].result &&
		signal_participants[1].entered == 1 &&
		signal_participants[1].unlocked == 1);
	pr_info("kd_signal stats: probe=%u phase=%u failures=%d nonfatal=%u owner=%lx word=%lx queued=%u\n",
		mutex_signal_probe, mutex_signal_phase,
		atomic_read(&signal_failures), signal_nonfatal_checks, q.owner,
		q.word, q.count);
	for (i = 0; i < ARRAY_SIZE(signal_participants); i++)
		if (signal_participants[i].task)
			put_task_struct(signal_participants[i].task);
}
