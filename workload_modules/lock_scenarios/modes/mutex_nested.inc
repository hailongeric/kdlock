/*
 * Nested mutex A/B bodies and GS roles; real owners are retained (mode 4/11).
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* These mutex-only role barriers may share a CPU. Yield so another role can
 * publish its queue link or native ACK; unlike spin tests, no raw lock/pin is
 * held here. A sleeping native mutex does not prohibit cond_resched().
 */
static __always_inline void kd_nested_mutex_relax(void)
{
	cpu_relax();
	cond_resched();
}

static noinline void prepare_nested_mutex_role(void)
{
	while (!atomic_read(&mutex_inner_holder_ready) ||
	       !atomic_read(&mutex_inner_direct_waiting) ||
	       !atomic_read(&mutex_outer_holder_ready) ||
	       !atomic_read(&mutex_outer_direct_waiting))
		kd_nested_mutex_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_a) < 1)
		kd_nested_mutex_relax();
}

static noinline void run_nested_mutex_cs(unsigned long work_load)
{
	unsigned long j;
	int lock_ret = 0;
	volatile int dummy_computation = 0;
	volatile unsigned long stack_cookie = KD_MUTEX_STACK_OLD;
	struct kd_resume_record *record = kd_resume_begin();

	if (native_stack_change && READ_ONCE(native_stack_armed))
		kd_stack_change_prepare(record, &stack_cookie);
	kd_ooo_dependency_prepare(record);
	if (native_pending_contended)
		smp_store_release(&pending_mutex_record, record);
	atomic_set(&mutex_outer_nested_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	if (native_resume_stage == 5) {
		if (READ_ONCE(native_depth_armed)) {
			for (j = 0; j < work_load; j++)
				dummy_computation++;
			kd_resume_depth_mutex(record);
		} else {
			kd_resume_probe(record, 5);
			kd_cs_step(KD_CS_MUTEX_B);
		}
		goto unlock_outer;
	}
	kd_resume_before_pending_lock(record);
	atomic_set(&mutex_inner_nested_waiting, 1);
	smp_mb__after_atomic();
	/* Keep the real cancellable API as the generated CALL-miss target. Its
	 * -EINTR suffix runs on the original waiter, not a combiner-side service.
	 */
	if (native_waiter_api == 1)
		lock_ret = mutex_lock_interruptible(&nested_mutex_b);
	else if (native_waiter_api == 2)
		lock_ret = mutex_lock_killable(&nested_mutex_b);
	else
		mutex_lock(&nested_mutex_b);
	if (lock_ret) {
		kd_waiter_signal_cancelled(record, lock_ret);
		goto unlock_outer;
	}
	if (native_stack_change && READ_ONCE(native_stack_armed))
		kd_stack_change_observe(record, READ_ONCE(stack_cookie));
	kd_resume_after_pending_lock(record);

	kd_cs_step(KD_CS_MUTEX_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;

	if (READ_ONCE(jit_mutex_ooo)) {
		mutex_unlock(&nested_mutex_a);
		kd_cs_step(KD_CS_MUTEX_B);
		mutex_unlock(&nested_mutex_b);
		goto nested_mutex_done;
	}
	if (READ_ONCE(native_resume_ooo) == 3 && record) {
		kd_ooo_pending_mutex_enter(record);
		kd_resume_probe(record, 3);
		kd_ooo_checkpoint(record, true, 1);
		kd_cs_step(KD_CS_MUTEX_B);
		kd_ooo_pending_mutex_leave();
		mutex_unlock(&nested_mutex_b);
		kd_ooo_checkpoint(record, true, 2);
		goto nested_mutex_done;
	}
	if (READ_ONCE(native_resume_ooo) == 2 && record) {
		kd_ooo_jit_prefix(record);
		mutex_unlock(&nested_mutex_a);
		kd_resume_probe(record, 3);
		goto mutex_ooo_after_a;
	}
	kd_resume_probe(record, 3);
	if (READ_ONCE(native_resume_ooo) == 1) {
		kd_ooo_checkpoint(record, true, 0);
		mutex_unlock(&nested_mutex_a);
mutex_ooo_after_a:
		kd_ooo_checkpoint(record, true, 1);
		kd_cs_step(KD_CS_MUTEX_B);
		mutex_unlock(&nested_mutex_b);
		kd_ooo_checkpoint(record, true, 2);
		goto nested_mutex_done;
	}
	mutex_unlock(&nested_mutex_b);
	kd_resume_probe(record, 2);
unlock_outer:
	mutex_unlock(&nested_mutex_a);
nested_mutex_done:
	if (native_pending_contended && READ_ONCE(pending_mutex_observed) &&
	    record == READ_ONCE(pending_mutex_record)) {
		bool valid = record->task == current && !preempt_count() &&
			     !irqs_disabled() && record->before == 1 &&
			     record->called == 1 && record->after == 1;

		/* The last ACK permits this waiter to leave. Do not inspect the
		 * completed frame or assume its owner already released physical A.
		 */
		if (!valid)
			atomic_inc(&resume_failures);
		pr_info("kd_pending mutex complete: task=%d waiter=%lx cpu=%u preempt=%u irq=%u record=%ld before=%u called=%u after=%u value=%lx valid=%u\n",
			current->pid, (unsigned long)current,
			raw_smp_processor_id(), preempt_count(),
			irqs_disabled(), record - resume_records,
			record->before, record->called, record->after,
			record->value, valid);
	}
	if (native_stack_change && READ_ONCE(native_stack_armed))
		kd_stack_change_complete(record);
	/* Signals are delivered to userspace only after this native suffix and ACK. */
	kd_waiter_signal_complete(record);
	if (native_resume_rename)
		kd_test_rename("klock_test");
}

static noinline void run_gs_nested_mutex_cs(unsigned long work_load)
{
	struct kd_gs_probe_state probe;
	unsigned long j;
	volatile int dummy_computation = 0;

	kd_gs_probe_prepare(&probe);
	atomic_set(&mutex_outer_nested_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	atomic_set(&mutex_inner_nested_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_b);

	kd_gs_probe_in_cs(&probe);
	kd_cs_step(KD_CS_MUTEX_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;

	mutex_unlock(&nested_mutex_b);
	mutex_unlock(&nested_mutex_a);
	kd_gs_probe_finish(&probe, true);
}

static noinline void run_nested_mutex_role(unsigned long work_load,
					   bool synchronized, bool gs_context)
{
	if (synchronized)
		prepare_nested_mutex_role();
	if (gs_context)
		run_gs_nested_mutex_cs(work_load);
	else
		run_nested_mutex_cs(work_load);
}
