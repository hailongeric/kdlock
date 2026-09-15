/*
 * Mode-3 native/mixed admission and contention, including interruptible APIs.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* A valid native ordering, but incompatible with either single-kind JIT
 * frame. Keep the acquisition site separate from ordinary mode 3. */
static noinline void run_mixed_mutex_cs(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	mutex_lock(&global_mutex);
	if (atomic_inc_return(&mutex_inside) != 1)
		atomic_inc(&mutex_overlaps);
	kd_cs_step(KD_CS_MUTEX_GLOBAL);
	/* Warm only A first, so B cannot shorten the global promotion window.
	 * Admission must still scan this branch before the test arms it. */
	if (READ_ONCE(mixed_lock_probe) == 2) {
		spin_lock(&global_lock);
		kd_cs_step(KD_CS_SPIN_GLOBAL);
		for (j = 0; j < work_load; j++)
			dummy_computation++;
		spin_unlock(&global_lock);
	}
	atomic_dec(&mutex_inside);
	mutex_unlock(&global_mutex);
}

#include "../fragments/context_lock_workload.c"

static int run_mutex_contention_test(unsigned long loop_count,
				     unsigned long work_load, unsigned int role)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	if (READ_ONCE(mixed_lock_probe)) {
		for (i = 0; i < loop_count; i++) {
			if (context_lock_probe == 1)
				kd_context_mutex_irqsave(work_load);
			else if (context_lock_probe == 2)
				kd_context_mutex_bh(work_load);
			else if (context_lock_probe == 3)
				kd_context_mutex_percpu(work_load);
			else if (context_lock_probe == 4)
				kd_context_mutex_percpu_regs(work_load);
			else if (context_lock_probe == 5)
				kd_context_mutex_percpu_flow(work_load);
			else if (context_lock_probe == 6)
				kd_context_mutex_percpu_cmov(work_load);
			else if (context_lock_probe == 7)
				kd_context_mutex_percpu_rotate(work_load);
			else if (context_lock_probe == 8)
				kd_context_mutex_percpu_implicit(work_load);
			else if (context_lock_probe == 9)
				kd_context_mutex_percpu_spill(work_load);
			else
				run_mixed_mutex_cs(work_load);
		}
		return 0;
	}

	for (i = 0; i < loop_count; i++) {
		struct kd_resume_record *record = kd_resume_begin();

		int ret;

		switch (role & 0x20000000U ? role & 3U : 0) {
		case 1:
			while (!mutex_trylock(&global_mutex))
				cond_resched();
			break;
		case 2:
			ret = mutex_lock_interruptible(&global_mutex);
			if (ret)
				return ret;
			break;
		case 3:
			ret = mutex_lock_killable(&global_mutex);
			if (ret)
				return ret;
			break;
		default:
			mutex_lock(&global_mutex);
		}

		if (atomic_inc_return(&mutex_inside) != 1)
			atomic_inc(&mutex_overlaps);
		kd_cs_step(KD_CS_MUTEX_GLOBAL);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		kd_resume_probe(record, 1);
		atomic_dec(&mutex_inside);
		if (unlikely(mutex_signal_race))
			kd_signal_owner_unlock(false);
		mutex_unlock(&global_mutex);
		if (unlikely(mutex_signal_race))
			kd_signal_owner_unlock(true);
		if (native_resume_rename)
			kd_test_rename("klock_test");
	}
	return 0;
}
