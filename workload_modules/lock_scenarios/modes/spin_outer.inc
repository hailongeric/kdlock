/*
 * Holder/successor roles and mode-8 routing for independent A/B contention.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static noinline void run_inner_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&inner_holder_ready, 0);
	atomic_set(&inner_direct_waiting, 0);
	atomic_set(&inner_nested_waiting, 0);
	atomic_set(&inner_trailing_waiting, 0);
	smp_mb__after_atomic();

	spin_lock(&nested_lock_b);
	atomic_set(&inner_holder_ready, 1);
	smp_mb__after_atomic();
	if (native_pending_contended) {
		wait_for_pending_spin_waiter();
		kd_gate_capacity_hold();
	} else {
		while (atomic_read(&inner_direct_waiting) < 2 ||
		       !atomic_read(&inner_nested_waiting) ||
		       !atomic_read(&inner_trailing_waiting))
			cpu_relax();
		while (kd_spin_debug_waiter_count(&nested_lock_b.rlock) < 3)
			cpu_relax();
	}
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	kd_cs_step(KD_CS_SPIN_B);
	spin_unlock(&nested_lock_b);
}

static noinline void prepare_inner_trailing_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&inner_nested_waiting))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_b.rlock) < 2)
		cpu_relax();
	atomic_set(&inner_trailing_waiting, 1);
	smp_mb__after_atomic();
}

static noinline void run_inner_trailing_role(unsigned long work_load,
					     bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_inner_trailing_role(synchronized);
	spin_lock(&nested_lock_b);
	kd_cs_step(KD_CS_SPIN_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_b);
}

static noinline void prepare_outer_direct_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&outer_holder_ready))
		cpu_relax();
	atomic_inc(&outer_direct_waiting);
	smp_mb__after_atomic();
}

static noinline void run_outer_direct_role(unsigned long work_load,
					   bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	/* Extra tickets belong to this physical candidate, not the JIT waiter. */
	kd_ticket_hold(synchronized, true);
	prepare_outer_direct_role(synchronized);
	spin_lock(&nested_lock_a);
	kd_cs_step(KD_CS_SPIN_A);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_a);
	kd_ticket_hold(synchronized, false);
}

static noinline void run_outer_holder_role(unsigned long work_load)
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

static noinline void prepare_outer_trailing_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&outer_nested_waiting))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 2)
		cpu_relax();
	atomic_set(&outer_trailing_waiting, 1);
	smp_mb__after_atomic();
}

static noinline void run_outer_trailing_role(unsigned long work_load,
					     bool synchronized)
{
	unsigned long j;
	volatile int dummy_computation = 0;
	spinlock_t *dependency = remote_spin_deep ? &remote_lock_d :
						    &nested_lock_c;

	prepare_outer_trailing_role(synchronized);
	if (READ_ONCE(remote_spin_ooo) && !remote_spin_native_owner)
		spin_lock(dependency);
	spin_lock(&nested_lock_a);
	if (READ_ONCE(remote_spin_ooo) && !remote_spin_native_owner) {
		if (remote_spin_deep) {
			spin_lock(&nested_lock_b);
			kd_remote_chain_observe();
			kd_cs_step(KD_CS_SPIN_B);
			spin_unlock(&nested_lock_b);
		} else {
			kd_remote_ooo_observe();
		}
	}
	kd_cs_step(KD_CS_SPIN_A);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_a);
	if (READ_ONCE(remote_spin_ooo) && !remote_spin_native_owner)
		spin_unlock(dependency);
}

#include "../fragments/spin_acquired_workload.c"

static void run_inner_contention_spinlock_test(unsigned long loop_count,
					       unsigned long work_load,
					       unsigned int role,
					       bool gs_context)
{
	unsigned long i;
	unsigned int sync_role =
		role & ~(MODE_ROLE_SYNCHRONIZED | MODE_ROLE_OUTER_ONLY);
	bool synchronized = role & MODE_ROLE_SYNCHRONIZED;
	bool outer_only = role & MODE_ROLE_OUTER_ONLY;

	for (i = 0; i < loop_count; i++) {
		if (sync_role == 0) {
			if (gs_context && !outer_only)
				run_gs_spin_nested_role(work_load,
							synchronized);
			else
				run_inner_nested_role(work_load, synchronized,
						      outer_only);
		} else if (synchronized && sync_role == 1)
			run_inner_holder_role(work_load);
		else if (synchronized && sync_role == 3)
			run_outer_holder_role(work_load);
		else if (sync_role == 4 || sync_role == 6)
			run_outer_direct_role(work_load, synchronized);
		else if (sync_role == 7)
			run_inner_trailing_role(work_load, synchronized);
		else if (sync_role == 8)
			run_outer_trailing_role(work_load, synchronized);
		else if (sync_role == 9)
			kd_remote_ooo_native_owner();
		else if (sync_role == 10 && synchronized)
			kd_remote_c_holder_role();
		else if (sync_role == 11 || sync_role == 12)
			kd_remote_c_direct_role(work_load, synchronized);
		else if (sync_role == 13 && synchronized)
			kd_remote_c_trailing_role();
		else
			run_inner_direct_role(work_load, synchronized);
	}
}
