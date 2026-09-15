// SPDX-License-Identifier: GPL-2.0
/* Four real ioctl callers, with L/S queue witnesses before owner release. */
#include <linux/sched/task.h>
static unsigned int spin_route_probe;
module_param(spin_route_probe, uint, 0444);
MODULE_PARM_DESC(
	spin_route_probe,
	"Mode 0 routing: 1=late promotion, 2=owner rename, 3=native-to-target, 4=queued rename");
static unsigned int spin_route_ready;
module_param(spin_route_ready, uint, 0444);
static bool spin_route_abort;
module_param(spin_route_abort, bool, 0644);
static int spin_route_cpus[4] = { 0, 1, 2, 3 };
module_param_array(spin_route_cpus, int, NULL, 0444);
static atomic_t route_roles = ATOMIC_INIT(0);
static atomic_t route_failures = ATOMIC_INIT(0);
static unsigned int route_phase;
static atomic_t route_finished = ATOMIC_INIT(0);
static unsigned int route_entries[4];
static struct task_struct *route_waiter;

static unsigned int kd_route_tail_cpu(u32 word)
{
	return (word & _Q_TAIL_CPU_MASK) >> _Q_TAIL_CPU_OFFSET;
}

static bool kd_route_native_waiting(u32 word, int cpu)
{
	return (word & _Q_PENDING_MASK) || kd_route_tail_cpu(word) == cpu + 1;
}

static bool kd_route_wait(unsigned int phase)
{
	unsigned long deadline = jiffies + 5 * HZ;
	bool native_owner = spin_route_probe == 1 || spin_route_probe == 3;

	while (!READ_ONCE(spin_route_abort)) {
		u32 original = atomic_read(&global_lock.rlock.raw_lock.val);
		u32 private = kd_spin_debug_word(&global_lock.rlock);
		bool ready, first, second;

		if (native_owner) {
			first = (private & _Q_LOCKED_MASK) == 1 &&
				kd_route_native_waiting(original,
							spin_route_cpus[1]);
			second = private & _Q_PENDING_MASK;
		} else {
			first = private & _Q_PENDING_MASK;
			second = kd_route_tail_cpu(private) ==
					 spin_route_cpus[3] + 1 &&
				 kd_spin_debug_waiter_count(
					 &global_lock.rlock) == 1;
		}

		if (!phase) {
			ready = smp_load_acquire(&route_phase) == 2;
		} else if (phase == 3) {
			ready = first;
		} else if (phase == 1) {
			ready = first && second;
		} else {
			/* The second native waiter must really publish a Linux tail;
			 * a started flag alone does not prove a blocking lock attempt. */
			ready = native_owner ?
					kd_route_tail_cpu(original) ==
						spin_route_cpus[2] + 1 :
					kd_route_native_waiting(
						original, spin_route_cpus[2]);
		}
		if (ready)
			return true;
		if (time_after(jiffies, deadline)) {
			atomic_inc(&route_failures);
			WRITE_ONCE(spin_route_abort, true);
			pr_err("kd_route timeout: scenario=%u phase=%u cpu=%d original=%x private=%x\n",
			       spin_route_probe, phase, raw_smp_processor_id(),
			       original, private);
			break;
		}
		cpu_relax();
	}
	return false;
}

static void kd_route_owner(void)
{
	struct task_struct *waiter;
	u32 original, private;

	smp_store_release(&spin_route_ready, 1);
	if (!kd_route_wait(1))
		return;
	smp_store_release(&route_phase, 2);
	if (!kd_route_wait(2))
		return;
	original = atomic_read(&global_lock.rlock.raw_lock.val);
	private = kd_spin_debug_word(&global_lock.rlock);
	pr_info("kd_route queued: scenario=%u owner=%d original=%x private=%x private_waiters=%d target_cpu=%d native_cpu=%d queued_cpu=%d original_tail_cpu=%u private_tail_cpu=%u original_pending=%u private_pending=%u\n",
		spin_route_probe, current->pid, original, private,
		kd_spin_debug_waiter_count(&global_lock.rlock),
		spin_route_cpus[1], spin_route_cpus[2], spin_route_cpus[3],
		kd_route_tail_cpu(original), kd_route_tail_cpu(private),
		!!(original & _Q_PENDING_MASK), !!(private & _Q_PENDING_MASK));
	if (spin_route_probe == 2)
		kd_test_rename("kd_renamed");
	else if (spin_route_probe == 3)
		kd_test_rename("klock_test");
	else if (spin_route_probe == 4) {
		/* L is still held and the target is observed in S. Its task ref
		 * remains live until it acquires and then releases this same L. */
		waiter = smp_load_acquire(&route_waiter);
		if (!waiter) {
			atomic_inc(&route_failures);
			return;
		}
		task_lock(waiter);
		strscpy(waiter->comm, "kd_renamed", TASK_COMM_LEN);
		task_unlock(waiter);
		pr_info("kd_route queued rename: task=%d cpu=%d private=%x\n",
			waiter->pid, task_cpu(waiter),
			kd_spin_debug_word(&global_lock.rlock));
	}
}

static __attribute__((noipa)) noinline int kd_route_run(unsigned int role)
{
	char original_comm[TASK_COMM_LEN];
	unsigned int count = preempt_count();
	bool irq = irqs_disabled();
	int cpu = raw_smp_processor_id();
	u32 original, private;

	if (role > 3 || cpu != spin_route_cpus[role] || count || irq)
		return -EINVAL;
	if (atomic_fetch_or(1U << role, &route_roles) & (1U << role))
		return -EALREADY;
	get_task_comm(original_comm, current);
	if (role == 2 && !kd_route_wait(0))
		return -ECANCELED;
	if (role == 3 && !kd_route_wait(3))
		return -ECANCELED;
	if (role == 3) {
		get_task_struct(current);
		smp_store_release(&route_waiter, current);
	}
	if (role == 2)
		__raw_spin_lock(&global_lock.rlock);
	else
		spin_lock(&global_lock);
	kd_spin_oracle_enter();
	route_entries[role]++;
	original = atomic_read(&global_lock.rlock.raw_lock.val);
	private = kd_spin_debug_word(&global_lock.rlock);
	pr_info("kd_route owned: scenario=%u role=%u task=%d comm=%s cpu=%d original=%x private=%x preempt=%u\n",
		spin_route_probe, role, current->pid, current->comm, cpu,
		original, private, preempt_count());
	if (preempt_count() != count + 1 || irqs_disabled() != irq)
		atomic_inc(&route_failures);
	if (!role) {
		if ((spin_route_probe == 1 || spin_route_probe == 3) ?
			    private != 0 :
			    (private & _Q_LOCKED_MASK) != 1)
			atomic_inc(&route_failures);
		kd_route_owner();
	}
	kd_cs_step(KD_CS_SPIN_GLOBAL);
	atomic_dec(&spin_inside);
	if (role == 2)
		__raw_spin_unlock(&global_lock.rlock);
	else
		spin_unlock(&global_lock);
	kd_spin_check_context(count, irq);
	if (strcmp(current->comm, original_comm))
		kd_test_rename(original_comm);
	if (role == 3) {
		WRITE_ONCE(route_waiter, NULL);
		put_task_struct(current);
	}
	pr_info("kd_route departed: scenario=%u role=%u task=%d cpu=%d preempt=%u irq=%u\n",
		spin_route_probe, role, current->pid, raw_smp_processor_id(),
		preempt_count(), irqs_disabled());
	atomic_or(1U << role, &route_finished);
	return READ_ONCE(spin_route_abort) ? -ECANCELED : 0;
}

static int kd_route_init(void)
{
	unsigned int i, j;

	if (!spin_route_probe)
		return 0;
	if (spin_route_probe > 4 || native_resume_stage || spin_chain_depth ||
	    mixed_lock_probe || context_lock_probe)
		return -EINVAL;
	for (i = 0; i < 4; i++) {
		if (spin_route_cpus[i] < 0 ||
		    spin_route_cpus[i] >= nr_cpu_ids ||
		    !cpu_online(spin_route_cpus[i]))
			return -EINVAL;
		for (j = 0; j < i; j++)
			if (spin_route_cpus[i] == spin_route_cpus[j])
				return -EINVAL;
	}
	return 0;
}

static void kd_route_report(void)
{
	if (spin_route_probe)
		pr_info("kd_route summary: scenario=%u roles=%d finished=%u entries=%u,%u,%u,%u failures=%d original=%x private=%x waiters=%d\n",
			spin_route_probe, atomic_read(&route_roles),
			atomic_read(&route_finished), route_entries[0],
			route_entries[1], route_entries[2], route_entries[3],
			atomic_read(&route_failures),
			atomic_read(&global_lock.rlock.raw_lock.val),
			kd_spin_debug_word(&global_lock.rlock),
			kd_spin_debug_waiter_count(&global_lock.rlock));
}
