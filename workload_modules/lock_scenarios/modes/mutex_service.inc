/*
 * Mode-5 bounded services and the separate post-promotion CALL-quota phase.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static void run_api_in_mutex_test(unsigned long loop_count,
				  unsigned long work_load)
{
	unsigned long i, j;
	unsigned long now;
	unsigned int call, repeats = READ_ONCE(mode5_call_quota) ? 17 : 1;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		mutex_lock(&global_mutex);

		kd_cs_step(KD_CS_MUTEX_GLOBAL);
		/* The counter before this loop detects entry replay. Count every
		 * returned service so skipping/repeating the pending CALL also fails. */
		for (call = 0; call < repeats; call++) {
			now = (unsigned long)ktime_get_ns();
			dummy_computation ^= (int)(now & 0xffff);
			if (now)
				mode5_api_calls++;
		}
		if (now)
			mode5_api_observations++;
		/* Keep the scalar call after the complete clock loop: quota still
		 * exits at clock 17, and its waiter executes this native suffix once.
		 */
		kd_scalar_service_step(mode5_api_observations,
				       &mode5_scalar_calls, &mode5_scalar_failures);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		mutex_unlock(&global_mutex);
		/* Outside the translated scope: observe the original caller only
		 * after native completion/owner ACK, never read current inside JIT. */
		if (repeats > 1)
			pr_info("kd_hostcall quota done: task=%d repeats=%u cpu=%u preempt=%u irq=%u\n",
				current->pid, repeats, raw_smp_processor_id(),
				preempt_count(), irqs_disabled());
	}
}
