/* SPDX-License-Identifier: GPL-2.0-only */
/* Included only by the two reader-family fixtures. Source helpers inline into
 * the exported ordinary body; native probes are deliberately outside it.
 */
#define RW_READ_READ 5U
#define RW_WRITE_READ 6U
#define RW_READ_WRITE 7U
#define RW_REPEAT_READ 8U
#define RW_DOWNGRADE 9U
#define RW_DOWNGRADE_MISS 10U
#define RW_NESTED_DOWNGRADE 11U
#define RW_READ_MISS 12U
#ifdef KD_FIXTURE_RWSEM
static unsigned long coordination_spins;
module_param(coordination_spins, ulong, 0444);
MODULE_PARM_DESC(coordination_spins, "Explicit finite source-reader coordination iteration bound");
#endif


static void notrace rw_native_context(struct fixture_worker *worker, unsigned int held)
{
#ifdef KD_FIXTURE_ATOMIC
	fixture_spin_sample(worker, held);
#else
	(void)held;
	if (current != worker->expected_task || irqs_disabled() || in_atomic()) {
		worker->rw_errors++;
		worker->error = -EUCLEAN;
	}
#endif
}

noinline notrace __visible void fixture_rw_native_checkpoint(struct fixture_worker *worker)
{
	worker->rw_native_checks++;
	rw_native_context(worker, worker->mode == RW_READ_MISS ? 2 : 0);
	if (current != worker->expected_task) {
		worker->rw_errors++;
		worker->error = -EUCLEAN;
	}
}

/* Distinct objects for nesting. Only RW_REPEAT_READ repeats a real shared
 * credit on A, with no pending writer. No write-held read bypass is used.
 */
static __always_inline void fixture_rw_source(struct fixture_worker *worker)
{
	unsigned int index = worker->index;
#ifdef KD_FIXTURE_RWSEM
	unsigned long attempt;
#endif

	worker->seen_before = current;
	if (worker->mode == RW_READ_READ || worker->mode == RW_REPEAT_READ) {
		fixture_read_acquire(&lock_a[index]);
		fixture_read_acquire(worker->mode == RW_REPEAT_READ ? &lock_a[index] : &lock_b[index]);
		worker->rw_effects++;
		READ_ONCE(step_entry)(worker);
		fixture_read_release(worker->mode == RW_REPEAT_READ ? &lock_a[index] : &lock_b[index]);
		worker->rw_effects++;
		READ_ONCE(step_entry)(worker);
		fixture_read_release(&lock_a[index]);
	} else if (worker->mode == RW_WRITE_READ) {
		fixture_lock_acquire(&lock_a[index]);
		WRITE_ONCE(protected_a[index], READ_ONCE(protected_a[index]) + 1);
		READ_ONCE(step_entry)(worker);
		worker->rw_read_attempts++;
		fixture_read_acquire(&lock_b[index]);
		worker->rw_effects++;
		READ_ONCE(step_entry)(worker);
		fixture_read_release(&lock_b[index]);
		READ_ONCE(step_entry)(worker);
		fixture_lock_release(&lock_a[index]);
	} else if (worker->mode == RW_READ_WRITE) {
		worker->rw_read_attempts++;
		fixture_read_acquire(&lock_a[index]);
		worker->rw_effects++;
		READ_ONCE(step_entry)(worker);
		fixture_lock_acquire(&lock_b[index]);
		WRITE_ONCE(protected_b[index], READ_ONCE(protected_b[index]) + 1);
		READ_ONCE(step_entry)(worker);
		fixture_lock_release(&lock_b[index]);
		READ_ONCE(step_entry)(worker);
		fixture_read_release(&lock_a[index]);
	} else if (worker->mode == RW_READ_MISS) {
		fixture_lock_acquire(&lock_a[index]);
		WRITE_ONCE(protected_a[index], READ_ONCE(protected_a[index]) + 1);
		READ_ONCE(step_entry)(worker);
		worker->rw_read_attempts++;
		fixture_read_acquire(&lock_b[index]);
		worker->rw_effects++;
		READ_ONCE(step_entry)(worker);
		fixture_rw_native_checkpoint(worker);
		fixture_read_release(&lock_b[index]);
		fixture_lock_release(&lock_a[index]);
#ifdef KD_FIXTURE_RWSEM
	} else {
		fixture_lock_acquire(&lock_a[index]);
		WRITE_ONCE(protected_a[index], READ_ONCE(protected_a[index]) + 1);
		READ_ONCE(step_entry)(worker);
		if (worker->mode == RW_NESTED_DOWNGRADE) {
			fixture_lock_acquire(&lock_b[index]);
			WRITE_ONCE(protected_b[index], READ_ONCE(protected_b[index]) + 1);
			READ_ONCE(step_entry)(worker);
			fixture_downgrade(&lock_b[index]);
		} else {
			fixture_downgrade(&lock_a[index]);
		}
		worker->rw_effects++;
		WRITE_ONCE(rw_downgraded, true);
		if (worker->mode == RW_DOWNGRADE_MISS)
			fixture_rw_native_checkpoint(worker);
		for (attempt = 0; attempt < READ_ONCE(coordination_spins) &&
		     READ_ONCE(rw_probe_needed) && !READ_ONCE(rw_probe_attempted); ++attempt)
			cpu_relax();
		if (READ_ONCE(rw_probe_needed) && !READ_ONCE(rw_probe_attempted))
			worker->error = -ETIMEDOUT;
		READ_ONCE(step_entry)(worker);
		fixture_read_release(worker->mode == RW_NESTED_DOWNGRADE ? &lock_b[index] : &lock_a[index]);
		/* The selected writer scope ended. This actual external CALL must
		 * start on native W at the exact post-up_read continuation.
		 */
		fixture_rw_native_checkpoint(worker);
		worker->rw_post_effects++;
		if (worker->mode == RW_NESTED_DOWNGRADE)
			fixture_lock_release(&lock_a[index]);
#endif
	}
}

static bool notrace rw_wait_flag(struct fixture_worker *worker, bool *flag)
{
	u64 start = ktime_get_mono_fast_ns();
	u64 budget = (u64)holder_timeout_ms * NSEC_PER_MSEC;

	while (!smp_load_acquire(flag)) {
		if (ktime_get_mono_fast_ns() - start >= budget) {
			worker->error = -ETIMEDOUT;
			return false;
		}
#ifdef KD_FIXTURE_ATOMIC
		cpu_relax();
#else
		cond_resched();
#endif
	}
	return true;
}

static void notrace fixture_rw_native_scene(struct fixture_worker *worker)
{
	unsigned int role = worker->role;
	bool writer = rw_scene_mode == 2 ? role == 0 : role == 2;
#ifdef KD_FIXTURE_RWSEM
	bool conversion = rw_scene_mode == 1 && role == 0;
#else
	bool conversion = false;
#endif

	WRITE_ONCE(rw_attempt[role], true);
	if (writer || conversion) {
		fixture_lock_acquire(&lock_a[0]);
		rw_native_context(worker, 1);
		if (READ_ONCE(rw_writer) || READ_ONCE(rw_inside[0]) ||
		    READ_ONCE(rw_inside[1]) || READ_ONCE(rw_inside[2]))
			worker->rw_errors++;
		WRITE_ONCE(rw_writer, role + 1);
		smp_store_release(&rw_stage[role], 1);
#ifdef KD_FIXTURE_RWSEM
		if (conversion) {
			rw_wait_flag(worker, &rw_convert);
			WRITE_ONCE(rw_writer, 0);
			fixture_downgrade(&lock_a[0]);
			WRITE_ONCE(rw_inside[role], true);
			smp_store_release(&rw_stage[role], 2);
			rw_wait_flag(worker, &rw_release[role]);
			WRITE_ONCE(rw_inside[role], false);
			fixture_read_release(&lock_a[0]);
		} else
#endif
		{
			rw_wait_flag(worker, &rw_release[role]);
			WRITE_ONCE(protected_a[0], READ_ONCE(protected_a[0]) + 1);
			WRITE_ONCE(rw_writer, 0);
			fixture_lock_release(&lock_a[0]);
		}
	} else {
		fixture_read_acquire(&lock_a[0]);
		rw_native_context(worker, 1);
		if (READ_ONCE(rw_writer))
			worker->rw_errors++;
		WRITE_ONCE(rw_inside[role], true);
		smp_store_release(&rw_stage[role], 2);
		rw_wait_flag(worker, &rw_release[role]);
		worker->rw_effects++;
		WRITE_ONCE(rw_inside[role], false);
		fixture_read_release(&lock_a[0]);
	}
	rw_native_context(worker, 0);
	smp_store_release(&rw_stage[role], 3);
}

static void notrace fixture_rw_probe_reader(struct fixture_worker *worker)
{
	fixture_lock_t *lock = requested_mode == RW_NESTED_DOWNGRADE ? &lock_b[0] : &lock_a[0];

	if (!rw_wait_flag(worker, &rw_downgraded))
		return;
	/* One independent native reader attempts the physically retained writer. */
	smp_store_release(&rw_probe_attempted, true);
	fixture_read_acquire(lock);
	worker->rw_effects++;
	fixture_read_release(lock);
}

static int notrace start_rw_scene(unsigned int mode)
{
	unsigned int index;
	int result;

	if (!runtime || worker_count || mode > 2 || !fixture_locks_clear())
		return -EBUSY;
#ifndef KD_FIXTURE_RWSEM
	if (mode == 1)
		return -EINVAL;
#endif
	rw_scene_mode = mode;
	rw_scene_active = true;
	rw_writer = 0; rw_convert = false;
	requested_mode = 20 + mode; requested_iterations = 1;
	protected_a[0] = 0; protected_b[0] = 0;
	reinit_completion(&start_gate);
	atomic_set(&ready_count, 0);
	WRITE_ONCE(ready_goal, 3);
	WRITE_ONCE(abort_start, false);
	for (index = 0; index < 3; ++index) {
		init_completion(&rw_go[index]);
		rw_release[index] = false; rw_stage[index] = 0;
		rw_attempt[index] = false; rw_inside[index] = false;
	}
	for (index = 0; index < 3; ++index) {
		struct fixture_worker *worker = &workers[index];

		*worker = (struct fixture_worker) { .rw_scene = true, .role = index,
			.mode = 20 + mode, .iterations = 1 };
		worker->task = kthread_create(worker_main, worker, "kd-reader/%u", index);
		if (IS_ERR(worker->task)) {
			result = PTR_ERR(worker->task); worker->task = NULL;
			WRITE_ONCE(abort_start, true);
			for (index = 0; index < 3; ++index)
				complete_all(&rw_go[index]);
			stop_workers(); return result;
		}
		get_task_struct(worker->task); worker_count++;
		fixture_wake_worker(worker, index);
	}
	return 0;
}
