/*
 * Isolated mode-9 abort roles; fault diagnosis is not an ordinary benchmark.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static noinline void run_abort_target_role(unsigned long work_load,
					   bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	if (synchronized) {
		while (!atomic_read(&outer_holder_ready) ||
		       atomic_read(&outer_direct_waiting) < 2)
			cpu_relax();
		while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 1)
			cpu_relax();
		atomic_set(&outer_nested_waiting, 1);
		smp_mb__after_atomic();
	}
	spin_lock(&nested_lock_a);
	spin_lock(&nested_lock_b);
	kd_cs_step(KD_CS_SPIN_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_b);
	spin_unlock(&nested_lock_a);
}

static noinline void run_abort_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&outer_holder_ready, 0);
	atomic_set(&outer_direct_waiting, 0);
	atomic_set(&outer_nested_waiting, 0);
	atomic_set(&outer_trailing_waiting, 0);
	smp_mb__after_atomic();

	spin_lock(&nested_lock_a);
	atomic_set(&outer_holder_ready, 1);
	smp_mb__after_atomic();
	while (atomic_read(&outer_direct_waiting) < 2 ||
	       !atomic_read(&outer_nested_waiting) ||
	       !atomic_read(&outer_trailing_waiting))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 3)
		cpu_relax();
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	kd_cs_step(KD_CS_SPIN_A);
	spin_unlock(&nested_lock_a);
}

static noinline void run_abort_trailing_role(unsigned long work_load,
					     bool synchronized)
{
	if (synchronized) {
		while (!atomic_read(&outer_nested_waiting))
			cpu_relax();
		while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 2)
			cpu_relax();
		atomic_set(&outer_trailing_waiting, 1);
		smp_mb__after_atomic();
	}
	run_outer_direct_role(work_load, false);
}

static void run_abort_recovery_spinlock_test(unsigned long loop_count,
					     unsigned long work_load,
					     unsigned int role)
{
	unsigned long i;
	unsigned int sync_role = role & ~MODE_ROLE_SYNCHRONIZED;
	bool synchronized = role & MODE_ROLE_SYNCHRONIZED;

	for (i = 0; i < loop_count; i++) {
		if (sync_role == 0)
			run_abort_target_role(work_load, synchronized);
		else if (synchronized && sync_role == 1)
			run_abort_holder_role(work_load);
		else if (sync_role == 4)
			run_abort_trailing_role(work_load, synchronized);
		else
			run_outer_direct_role(work_load, synchronized);
	}
}

/* Exercise a genuine scalar argument and its consumed result, not a second
 * zero-argument clock. With low < 2*root+1 and root < 2^32, root^2+low fits
 * u64 and has floor(sqrt(...)) == root. High argument bits and bit 31 of the
 * unsigned result expose truncation/sign-extension mistakes across the CALL.
 * Keep this inline so only the kernel math helper leaves the generated CS.
 */
static __always_inline void kd_scalar_service_step(unsigned long sequence,
						 unsigned long *calls,
						 unsigned long *failures)
{
	unsigned long low = sequence & 0xffff;
	unsigned long root = 0x80000000UL + low;
	unsigned long result = int_sqrt(root * root + low);

	(*calls)++;
	if (result != root)
		(*failures)++;
}
