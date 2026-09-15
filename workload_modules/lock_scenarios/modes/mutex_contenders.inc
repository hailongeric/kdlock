/*
 * Independent mutex holder/waiter roles, queue observations and role dispatch.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static noinline void run_inner_mutex_direct_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_inner_holder_ready))
		kd_nested_mutex_relax();
	atomic_set(&mutex_inner_direct_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_b);
	kd_cs_step(KD_CS_MUTEX_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_b);
}

/* B's owner observes the original waiter in the real kernel wait_list,
 * rather than mistaking a pre-lock flag or the combiner for that waiter.
 * On timeout release B and fail the oracle instead of stranding the test. */
static noinline void wait_for_pending_mutex_waiter(void)
{
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		struct kd_resume_record *record =
			smp_load_acquire(&pending_mutex_record);
		struct mutex_waiter *waiter;
		unsigned long flags;
		bool found = false;

		raw_spin_lock_irqsave(&nested_mutex_b.wait_lock, flags);
		list_for_each_entry(waiter, &nested_mutex_b.wait_list, list) {
			if (record && waiter->task == record->task) {
				found = true;
				break;
			}
		}
		raw_spin_unlock_irqrestore(&nested_mutex_b.wait_lock, flags);
		if (found) {
			unsigned long a_owner =
				kd_test_mutex_owner(&nested_mutex_a);
			unsigned long b_owner =
				kd_test_mutex_owner(&nested_mutex_b);
			bool valid = a_owner &&
				     a_owner != (unsigned long)record->task &&
				     a_owner != (unsigned long)current &&
				     b_owner == (unsigned long)current &&
				     READ_ONCE(record->before) == 1 &&
				     !READ_ONCE(record->called) &&
				     !READ_ONCE(record->after);

			if (!valid || pending_mutex_observed)
				atomic_inc(&resume_failures);
			pending_mutex_observed++;
			pending_mutex_a_owner = a_owner;
			pr_info("kd_pending mutex blocked: task=%d waiter=%lx a_owner=%lx b_owner=%lx queued=1 valid=%u holder_comm=%s\n",
				record->task->pid, (unsigned long)record->task,
				a_owner, b_owner, valid, current->comm);
			kd_waiter_signal_send(record);
			return;
		}
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&resume_failures);
			pr_err("kd_pending mutex: original waiter did not queue on B\n");
			return;
		}
		cond_resched();
	}
}

/* Counted contention can precede the actual sleep. Hold B until its real
 * wait_list contains A's physical owner, so sharing a CPU cannot turn the
 * scheduling gate into a successful but uncontended JIT run. Snapshot task
 * identity under wait_lock; do not retain/dereference a waiter afterward. */
static noinline void wait_for_nested_mutex_executor(void)
{
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		struct mutex_waiter *waiter;
		unsigned long flags, a_owner, b_owner;
		unsigned int executor_cpu = 0;
		pid_t executor_pid = 0;

		raw_spin_lock_irqsave(&nested_mutex_b.wait_lock, flags);
		a_owner = kd_test_mutex_owner(&nested_mutex_a);
		b_owner = kd_test_mutex_owner(&nested_mutex_b);
		list_for_each_entry(waiter, &nested_mutex_b.wait_list, list) {
			if ((unsigned long)waiter->task == a_owner) {
				executor_pid = waiter->task->pid;
				executor_cpu = task_cpu(waiter->task);
				break;
			}
		}
		raw_spin_unlock_irqrestore(&nested_mutex_b.wait_lock, flags);
		if (executor_pid) {
			bool valid = b_owner == (unsigned long)current &&
				     a_owner != b_owner &&
				     executor_cpu == raw_smp_processor_id() &&
				     !preempt_count() && !irqs_disabled();

			if (!valid)
				atomic_inc(&resume_failures);
			pr_info("kd_nested mutex blocked: holder=%d b_owner=%lx executor=%d a_owner=%lx cpu=%u executor_cpu=%u a=%lx b=%lx queued=1 valid=%u\n",
				current->pid, b_owner, executor_pid, a_owner,
				raw_smp_processor_id(), executor_cpu,
				(unsigned long)&nested_mutex_a,
				(unsigned long)&nested_mutex_b, valid);
			return;
		}
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&resume_failures);
			pr_err("kd_nested mutex: A executor did not queue on B\n");
			return;
		}
		cond_resched();
	}
}

static noinline void run_inner_mutex_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&mutex_inner_holder_ready, 0);
	atomic_set(&mutex_inner_direct_waiting, 0);
	atomic_set(&mutex_inner_nested_waiting, 0);
	atomic_set(&mutex_inner_trailing_waiting, 0);
	smp_mb__after_atomic();

	mutex_lock(&nested_mutex_b);
	atomic_set(&mutex_inner_holder_ready, 1);
	smp_mb__after_atomic();
	while (!atomic_read(&mutex_inner_direct_waiting) ||
	       !atomic_read(&mutex_inner_nested_waiting) ||
	       !atomic_read(&mutex_inner_trailing_waiting))
		kd_nested_mutex_relax();
	if (native_stack_change) {
		kd_stack_change_wait();
	} else if (native_pending_contended) {
		wait_for_pending_mutex_waiter();
	} else if (mutex_nested_schedule) {
		wait_for_nested_mutex_executor();
	} else {
		/* The ordinary nested JIT case waits for the A executor, not
		 * for the original waiter used by pending-CALL continuation. */
		while (!kd_mutex_debug_nested_waiters())
			kd_nested_mutex_relax();
	}
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	kd_cs_step(KD_CS_MUTEX_B);
	/* The native B owner brackets its real release; a sysfs trigger alone
	 * cannot prove when a cancelled/acquired waiter was allowed to proceed.
	 */
	kd_waiter_race_unlock(false);
	mutex_unlock(&nested_mutex_b);
	kd_waiter_race_unlock(true);
}

static noinline void run_inner_mutex_trailing_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_inner_nested_waiting))
		kd_nested_mutex_relax();
	atomic_set(&mutex_inner_trailing_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_b);
	kd_cs_step(KD_CS_MUTEX_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_b);
}

static noinline void run_outer_mutex_direct_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_outer_holder_ready))
		kd_nested_mutex_relax();
	atomic_set(&mutex_outer_direct_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	kd_cs_step(KD_CS_MUTEX_A);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_a);
}

static noinline void run_outer_mutex_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&mutex_outer_holder_ready, 0);
	atomic_set(&mutex_outer_direct_waiting, 0);
	atomic_set(&mutex_outer_nested_waiting, 0);
	atomic_set(&mutex_outer_trailing_waiting, 0);
	smp_mb__after_atomic();

	mutex_lock(&nested_mutex_a);
	atomic_set(&mutex_outer_holder_ready, 1);
	smp_mb__after_atomic();
	while (!atomic_read(&mutex_outer_direct_waiting) ||
	       !atomic_read(&mutex_outer_nested_waiting) ||
	       !atomic_read(&mutex_outer_trailing_waiting))
		kd_nested_mutex_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_a) < 3)
		kd_nested_mutex_relax();
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	kd_cs_step(KD_CS_MUTEX_A);
	mutex_unlock(&nested_mutex_a);
}

static noinline void run_outer_mutex_trailing_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_outer_nested_waiting))
		kd_nested_mutex_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_a) < 2)
		kd_nested_mutex_relax();
	if (READ_ONCE(mutex_ooo_dependency) == 1)
		kd_ooo_dependency_hold();
	atomic_set(&mutex_outer_trailing_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	if (READ_ONCE(mutex_ooo_dependency) == 1)
		kd_ooo_dependency_observe();
	kd_cs_step(KD_CS_MUTEX_A);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_a);
	if (READ_ONCE(mutex_ooo_dependency) == 1)
		mutex_unlock(&ooo_mutex_locks[6]);
}

static void run_nested_mutex_test(unsigned long loop_count,
				  unsigned long work_load, unsigned int role,
				  bool gs_context)
{
	unsigned long i;
	unsigned int sync_role = role & ~MODE_ROLE_SYNCHRONIZED;
	bool synchronized = role & MODE_ROLE_SYNCHRONIZED;

	/* Correlate requested affinity with actual tasks, not only userspace
	 * placement. This runs before acquisition, outside the translated CS.
	 */
	if (synchronized && native_pending_contended)
		pr_info("kd_pending mutex role: role=%u task=%d self=%lx cpu=%u preempt=%u irq=%u\n",
			sync_role, current->pid, (unsigned long)current,
			raw_smp_processor_id(), preempt_count(),
			irqs_disabled());
	if (synchronized && mutex_nested_schedule)
		pr_info("kd_nested mutex role: role=%u task=%d self=%lx cpu=%u preempt=%u irq=%u\n",
			sync_role, current->pid, (unsigned long)current,
			raw_smp_processor_id(), preempt_count(),
			irqs_disabled());
	for (i = 0; i < loop_count; i++) {
		if (!synchronized || sync_role == 0)
			run_nested_mutex_role(work_load, synchronized,
					      gs_context);
		else if (sync_role == 1)
			run_inner_mutex_holder_role(work_load);
		else if (sync_role == 2)
			run_inner_mutex_direct_role(work_load);
		else if (sync_role == 3)
			run_outer_mutex_holder_role(work_load);
		else if (sync_role == 4)
			run_outer_mutex_direct_role(work_load);
		else if (sync_role == 5)
			run_inner_mutex_trailing_role(work_load);
		else if (sync_role == 6)
			run_outer_mutex_trailing_role(work_load);
		else if (sync_role == 7 && !gs_context)
			run_mutex_native_dependency_role();
	}
	/* This runs on the original task after its unlock/restore, not in JIT. */
	if (synchronized && mutex_nested_schedule)
		pr_info("kd_nested mutex done: role=%u task=%d self=%lx cpu=%u preempt=%u irq=%u\n",
			sync_role, current->pid, (unsigned long)current,
			raw_smp_processor_id(), preempt_count(),
			irqs_disabled());
}
