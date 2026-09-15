/*
 * Inner-B participants, pending-lock observations and native/JIT continuation.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static noinline void prepare_inner_nested_role(bool synchronized,
					       struct kd_resume_record *record)
{
	int direct = native_pending_contended ? 1 : 2;

	/* Keep arming branches out of the caller's A acquisition site. */
	if (READ_ONCE(remote_spin_ooo)) {
		WRITE_ONCE(remote_ooo_waiter, current);
		WRITE_ONCE(remote_ooo_origin_cpu, raw_smp_processor_id());
		if (remote_spin_native_owner)
			while (!smp_load_acquire(&remote_ooo_c_ready))
				cpu_relax();
	}
	if (!synchronized)
		return;
	if (READ_ONCE(remote_spin_deep))
		kd_remote_c_prepare();
	/* Keep this branch outside the caller so warmup and contention share A's
	 * acquisition site, rather than registering only one compiler-split entry. */
	if (native_pending_contended && record)
		smp_store_release(&pending_spin_record, record);
	while (!atomic_read(&inner_holder_ready) ||
	       atomic_read(&inner_direct_waiting) < direct ||
	       !atomic_read(&outer_holder_ready) ||
	       atomic_read(&outer_direct_waiting) < 2)
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 1)
		cpu_relax();
	if (native_pending_contended) {
		/* One independent B contender owns the pending bit, not a node. */
		while (!(atomic_read(&nested_lock_b.rlock.raw_lock.val) &
			 _Q_PENDING_MASK))
			cpu_relax();
	} else {
		while (kd_spin_debug_waiter_count(&nested_lock_b.rlock) < 1)
			cpu_relax();
	}
}

static noinline void run_inner_nested_role(unsigned long work_load,
					   bool synchronized, bool outer_only)
{
	unsigned long j;
	unsigned int count = preempt_count();
	bool irq = irqs_disabled();
	volatile int dummy_computation = 0;
	struct kd_resume_record *record = outer_only ? NULL : kd_resume_begin();

	prepare_inner_nested_role(synchronized, record);
	atomic_set(&outer_nested_waiting, 1);
	smp_mb__after_atomic();
	spin_lock(&nested_lock_a);
	if (outer_only) {
		kd_cs_step(KD_CS_SPIN_A);
		spin_unlock(&nested_lock_a);
		return;
	}
	atomic_set(&inner_nested_waiting, 1);
	smp_mb__after_atomic();
	kd_resume_before_pending_lock(record);
	spin_lock(&nested_lock_b);
	kd_resume_after_pending_lock(record);
	kd_cs_step(KD_CS_SPIN_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	if (READ_ONCE(remote_spin_ooo) && READ_ONCE(remote_spin_deep)) {
		atomic_set(&remote_c_nested, 1);
		smp_mb__after_atomic();
		spin_lock(&nested_lock_c);
		kd_cs_step(KD_CS_SPIN_C);
		remote_ooo_prefix++;
		if (READ_ONCE(remote_spin_ooo) == 2)
			kd_resume_probe(record, 3);
		if (READ_ONCE(remote_spin_reverse))
			spin_unlock(&nested_lock_b);
		else
			spin_unlock(&nested_lock_a);
		if (READ_ONCE(remote_spin_ooo) == 4)
			kd_resume_probe(record, 3);
		if (READ_ONCE(remote_spin_reverse))
			spin_unlock(&nested_lock_a);
		else
			spin_unlock(&nested_lock_b);
		if (READ_ONCE(remote_spin_ooo) == 3)
			kd_resume_probe(record, 3);
		spin_lock(&remote_lock_d);
		remote_ooo_suffix++;
		kd_cs_step(KD_CS_SPIN_C);
		spin_unlock(&remote_lock_d);
		spin_unlock(&nested_lock_c);
		goto inner_done;
	}
	if (READ_ONCE(remote_spin_ooo)) {
		remote_ooo_prefix++;
		if (READ_ONCE(remote_spin_ooo) == 2)
			kd_resume_probe(record, 3);
		spin_unlock(&nested_lock_a);
		if (READ_ONCE(remote_spin_ooo) == 3)
			kd_resume_probe(record, 3);
		spin_lock(&nested_lock_c);
		remote_ooo_suffix++;
		kd_cs_step(KD_CS_SPIN_B);
		spin_unlock(&nested_lock_c);
		spin_unlock(&nested_lock_b);
		goto inner_done;
	}
	kd_resume_probe(record, 3);
	spin_unlock(&nested_lock_b);
	kd_resume_probe(record, 2);
	spin_unlock(&nested_lock_a);
inner_done:
	kd_spin_check_context(count, irq);
	if (native_resume_rename)
		kd_test_rename("klock_test");
}

static noinline void run_gs_spin_nested_role(unsigned long work_load,
					     bool synchronized)
{
	struct kd_gs_probe_state probe;
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_inner_nested_role(synchronized, NULL);
	kd_gs_probe_prepare(&probe);
	atomic_set(&outer_nested_waiting, 1);
	smp_mb__after_atomic();
	spin_lock(&nested_lock_a);
	atomic_set(&inner_nested_waiting, 1);
	smp_mb__after_atomic();
	spin_lock(&nested_lock_b);

	kd_gs_probe_in_cs(&probe);
	kd_cs_step(KD_CS_SPIN_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;

	spin_unlock(&nested_lock_b);
	spin_unlock(&nested_lock_a);
	kd_gs_probe_finish(&probe, false);
}

static noinline void prepare_inner_direct_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&inner_holder_ready))
		cpu_relax();
	atomic_inc(&inner_direct_waiting);
	smp_mb__after_atomic();
}

static noinline void run_inner_direct_role(unsigned long work_load,
					   bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_inner_direct_role(synchronized);
	/* Stage 4 needs a Linux pending-bit holder, not another private request.
	 * Keep registration on the ordinary call site during unsynchronized warmup. */
	if (native_pending_contended && synchronized) {
		__raw_spin_lock(&nested_lock_b.rlock);
		kd_cs_step(KD_CS_SPIN_B);
		for (j = 0; j < work_load; j++)
			dummy_computation++;
		__raw_spin_unlock(&nested_lock_b.rlock);
		return;
	}
	spin_lock(&nested_lock_b);
	kd_cs_step(KD_CS_SPIN_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_b);
}

#include "../fragments/spin_ticket_workload.c"
#include "../fragments/spin_gate_workload.c"

/* This fixture has one B pending-bit holder and one queued, CPU-pinned waiter.
 * While B is owned, its tail cannot drain or be replaced by another contender.
 * Observe the published tail, not merely a flag set before the lock CALL. */
static noinline void wait_for_pending_spin_waiter(void)
{
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		struct kd_resume_record *record =
			smp_load_acquire(&pending_spin_record);
		u32 b = atomic_read_acquire(&nested_lock_b.rlock.raw_lock.val);
		int cpu = (b >> _Q_TAIL_CPU_OFFSET) - 1;
		int queued = kd_spin_debug_waiter_count(&nested_lock_b.rlock);

		if (record && (b & _Q_TAIL_MASK) && queued == 0 &&
		    cpu == task_cpu(record->task)) {
			u32 a = atomic_read(&nested_lock_a.rlock.raw_lock.val);
			u32 a_private =
				kd_spin_debug_word(&nested_lock_a.rlock);
			bool valid = kd_test_spin_origin_locked(a) &&
				     (a_private & _Q_LOCKED_MASK) == 3 &&
				     kd_test_spin_origin_locked(b) &&
				     (b & _Q_PENDING_MASK) == _Q_PENDING_VAL &&
				     !(b & _Q_TAIL_IDX_MASK) &&
				     record->task != current &&
				     READ_ONCE(record->before) == 1 &&
				     !READ_ONCE(record->called) &&
				     !READ_ONCE(record->after);

			if (!valid || pending_spin_observed)
				atomic_inc(&resume_failures);
			smp_store_release(&pending_spin_observed, 1);
			pr_info("kd_pending spin blocked: task=%d cpu=%d holder_cpu=%d outer=%lx lock=%lx a_val=%x b_val=%x a_private=%x queued=%d valid=%u holder_comm=%s\n",
				record->task->pid, cpu, raw_smp_processor_id(),
				(unsigned long)&nested_lock_a,
				(unsigned long)&nested_lock_b, a, b, a_private,
				queued, valid, current->comm);
			return;
		}
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&resume_failures);
			pr_err("kd_pending spin: original waiter did not queue on B\n");
			return;
		}
		cpu_relax();
	}
}
