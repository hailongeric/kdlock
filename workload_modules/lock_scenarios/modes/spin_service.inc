/*
 * Mode-2 bounded service CALLs inside the original spin critical section.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static void run_api_in_lock_test(unsigned long loop_count,
				 unsigned long work_load)
{
	unsigned long i, j;
	unsigned long now;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&global_lock);

		kd_cs_step(KD_CS_SPIN_GLOBAL);
		now = (unsigned long)ktime_get_ns();
		dummy_computation ^= (int)(now & 0xffff);
		if (now)
			mode2_api_observations++;
		kd_scalar_service_step(mode2_api_observations,
				       &mode2_scalar_calls, &mode2_scalar_failures);

		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&global_lock);
	}
}
