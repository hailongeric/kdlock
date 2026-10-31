/* SPDX-License-Identifier: GPL-2.0 */
/* Real unprepared gate/OSQ calls with a runnable holder on another CPU.
 * No provider hooks or images are installed. Observing an OSQ tail proves that
 * the scoped entry queued; a scheduler exit may race a signal, so exact branch
 * selection belongs to the deterministic primitive fixture, not this witness. */
struct gate_signal_result {
	u64 errors, cases, osq_observed, scoped_retired;
	u64 nonfatal_wait, fatal_cancel, interruptible_cancel, idle;
};
#define RUN_GATE_SIGNAL _IOR('S', 2, struct gate_signal_result)
static DEFINE_KD_RWSEM(signal_sem);
struct gate_signal_case {
	struct completion holder_entered, holder_done, waiter_ready, waiter_done;
	struct task_struct *holder, *waiter;
	bool release, expired, killable;
	int waiter_result;
};

static int gate_holder(void *data)
{
	struct gate_signal_case *c = data;
	unsigned long deadline;

	(kd_down_write)(&signal_sem);
	preempt_disable();
	deadline = jiffies + 2 * HZ;
	complete(&c->holder_entered);
	while (!smp_load_acquire(&c->release)) {
		if (time_after_eq(jiffies, deadline)) {
			WRITE_ONCE(c->expired, true);
			break;
		}
		cpu_relax();
	}
	preempt_enable();
	kd_up_write(&signal_sem);
	complete(&c->holder_done);
	return 0;
}

static int gate_signal_waiter(void *data)
{
	struct gate_signal_case *c = data;

	allow_signal(SIGUSR1);
	allow_signal(SIGKILL);
	complete(&c->waiter_ready);
	c->waiter_result = c->killable ? kd_down_write_killable(&signal_sem) :
		kd_down_write_interruptible(&signal_sem);
	if (!c->waiter_result)
		kd_up_write(&signal_sem);
	/* Both the outcome check and the join path observe this completion. */
	complete_all(&c->waiter_done);
	return 0;
}

static bool gate_holder_owns(struct gate_signal_case *c)
{
	return !READ_ONCE(c->expired) && !completion_done(&c->holder_done) &&
		(atomic_long_read(&signal_sem.gate.owner) & ~KD_MUTEX_OWNER_FLAGS) ==
		(unsigned long)c->holder &&
		atomic_long_read(&signal_sem.admission) == -1;
}

static int gate_signal_case_run(struct gate_signal_result *r, bool killable,
			       bool nonfatal_first, unsigned int holder_cpu,
			       unsigned int waiter_cpu)
{
	struct gate_signal_case c = { .killable = killable, .waiter_result = 1 };
	unsigned long deadline;
	bool observed = false, queued = false;
	int ret = 0;

	if (!kd_rwsem_is_idle(&signal_sem))
		return -EBUSY;
	kd_rwsem_init(&signal_sem);
	init_completion(&c.holder_entered);
	init_completion(&c.holder_done);
	init_completion(&c.waiter_ready);
	init_completion(&c.waiter_done);
	c.holder = kthread_create(gate_holder, &c, "kd_rwsem_holder");
	if (IS_ERR(c.holder))
		return PTR_ERR(c.holder);
	get_task_struct(c.holder);
	kthread_bind(c.holder, holder_cpu);
	wake_up_process(c.holder);
	if (!wait_for_completion_timeout(&c.holder_entered, 5 * HZ)) {
		check(false);
		goto join;
	}
	c.waiter = kthread_create(gate_signal_waiter, &c, "kd_rwsem_signal");
	if (IS_ERR(c.waiter)) {
		ret = PTR_ERR(c.waiter);
		c.waiter = NULL;
		goto join;
	}
	get_task_struct(c.waiter);
	kthread_bind(c.waiter, waiter_cpu);
	wake_up_process(c.waiter);
	if (!wait_for_completion_timeout(&c.waiter_ready, HZ)) {
		check(false);
		goto join;
	}
	/* Read only the queue tail value; never dereference an OSQ node sampled
	 * without its lifetime. A missed window is a failed observation. */
	deadline = jiffies + HZ / 2;
	do {
		if (atomic_read(&signal_sem.gate.osq.tail) && gate_holder_owns(&c)) {
			observed = true;
			break;
		}
		cpu_relax();
	} while (time_before(jiffies, deadline));
	check(observed);
	if (!observed)
		goto join;
	r->osq_observed++;
	check(!READ_ONCE(signal_sem.prepared_writes));
	check(!waitqueue_active(&signal_sem.phase_wait));
	check(!waitqueue_active(&signal_sem.reader_drain));
	check(!atomic_read(&signal_sem.gate.delegation_state));
	check(!READ_ONCE(signal_sem.gate.delegation_tail));
	check(!send_sig(nonfatal_first ? SIGUSR1 : SIGKILL, c.waiter, 1));
	if (killable && nonfatal_first) {
		deadline = jiffies + HZ / 2;
		do {
			queued = !atomic_read(&signal_sem.gate.osq.tail) &&
				READ_ONCE(signal_sem.gate.wait_head) &&
				(READ_ONCE(c.waiter->__state) == TASK_KILLABLE) &&
				!READ_ONCE(c.waiter->on_cpu);
			if (queued)
				break;
			msleep(1);
		} while (time_before(jiffies, deadline));
		check(queued && gate_holder_owns(&c));
		check(!completion_done(&c.waiter_done));
		if (queued && gate_holder_owns(&c))
			r->nonfatal_wait++;
		check(!send_sig(SIGKILL, c.waiter, 1));
	}
	check(wait_for_completion_timeout(&c.waiter_done, HZ / 2));
	check(c.waiter_result == -EINTR && gate_holder_owns(&c));
	check(!atomic_read(&signal_sem.gate.osq.tail));
	check(!READ_ONCE(signal_sem.gate.wait_head));
	if (completion_done(&c.waiter_done) && c.waiter_result == -EINTR &&
	    gate_holder_owns(&c) && !atomic_read(&signal_sem.gate.osq.tail) &&
	    !READ_ONCE(signal_sem.gate.wait_head)) {
		r->scoped_retired++;
		if (killable)
			r->fatal_cancel++;
		else
			r->interruptible_cancel++;
	}
join:
	/* Release before joining even after an observation timeout. A timeout
	 * never authorizes freeing task/case state: the ordinary joins may remain
	 * blocked if the provider is incorrect, and the runner must retain it. */
	smp_store_release(&c.release, true);
	if (c.waiter) {
		check(wait_for_completion_timeout(&c.waiter_done, 5 * HZ));
		check(!kthread_stop(c.waiter));
		put_task_struct(c.waiter);
	}
	check(wait_for_completion_timeout(&c.holder_done, 5 * HZ));
	check(!kthread_stop(c.holder));
	put_task_struct(c.holder);
	check(!c.expired);
	check(kd_rwsem_is_idle(&signal_sem));
	r->cases++;
	return ret;
}

static long run_gate_signal(void __user *user)
{
	struct gate_signal_result r = { 0 };
	unsigned int cpu, holder_cpu = nr_cpu_ids, waiter_cpu = nr_cpu_ids;
	int ret = 0;

	if (!kd_mutex_trylock(&control))
		return -EBUSY;
	atomic_set(&errors, 0);
	cpus_read_lock();
	migrate_disable();
	for_each_online_cpu(cpu) {
		if (cpu == raw_smp_processor_id())
			continue;
		if (holder_cpu == nr_cpu_ids)
			holder_cpu = cpu;
		else { waiter_cpu = cpu; break; }
	}
	if (waiter_cpu == nr_cpu_ids) {
		ret = -EINVAL;
		goto out;
	}
	ret = gate_signal_case_run(&r, false, true, holder_cpu, waiter_cpu);
	if (!ret && !atomic_read(&errors))
		ret = gate_signal_case_run(&r, true, false, holder_cpu, waiter_cpu);
	if (!ret && !atomic_read(&errors))
		ret = gate_signal_case_run(&r, true, true, holder_cpu, waiter_cpu);
	check(!ret && r.cases == 3);
	r.idle = kd_rwsem_is_idle(&signal_sem);
	check(r.idle);
	r.errors = atomic_read(&errors);
	if (!ret && copy_to_user(user, &r, sizeof(r)))
		ret = -EFAULT;
out:
	migrate_enable();
	cpus_read_unlock();
	kd_mutex_local_unlock(&control);
	return ret;
}
