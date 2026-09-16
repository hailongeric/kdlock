/*
 * GS/current oracle for native and delegated bodies, with origin CPU storage.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

#define KD_GS_PROBE_MAGIC 0x4b44475300000000UL
#define KD_GS_PROBE_DELTA 0x101UL
#define KD_GS_PROBE_RMW_MAGIC 0x524d570000000000UL

struct kd_gs_probe_state {
	int cpu;
	unsigned long expected_value;
	unsigned long expected_rmw;
	unsigned long seen_value;
	unsigned long seen_task;
	struct task_struct *expected_task;
};

static noinline void kd_gs_probe_prepare(struct kd_gs_probe_state *state)
{
	int cpu = raw_smp_processor_id();
	unsigned long task_value = (unsigned long)current;

	memset(state, 0, sizeof(*state));
	state->cpu = cpu;
	state->expected_task = current;
	state->expected_value = KD_GS_PROBE_MAGIC ^ task_value ^
				((unsigned long)(cpu + 1) << 32);
	state->expected_rmw = KD_GS_PROBE_RMW_MAGIC ^ task_value ^
			      (unsigned long)(cpu + 1);
	WRITE_ONCE(per_cpu(kd_gs_probe_value, cpu), state->expected_value);
	WRITE_ONCE(per_cpu(kd_gs_probe_rmw, cpu), state->expected_rmw);
}

static __always_inline void kd_gs_probe_in_cs(struct kd_gs_probe_state *state)
{
	unsigned long value = raw_cpu_read(kd_gs_probe_value);

	raw_cpu_write(kd_gs_probe_value, value + KD_GS_PROBE_DELTA);
	raw_cpu_inc(kd_gs_probe_rmw);
	WRITE_ONCE(state->seen_value, value);
	WRITE_ONCE(state->seen_task, (unsigned long)current);
}

static noinline void kd_gs_probe_finish(struct kd_gs_probe_state *state,
					bool mutex_mode)
{
	atomic64_t *attempts = mutex_mode ? &gs_mutex_attempts :
					    &gs_spin_attempts;
	atomic64_t *successes = mutex_mode ? &gs_mutex_successes :
					     &gs_spin_successes;
	atomic64_t *failures = mutex_mode ? &gs_mutex_failures :
					    &gs_spin_failures;
	unsigned long written_value;
	unsigned long written_rmw;

	written_value = READ_ONCE(per_cpu(kd_gs_probe_value, state->cpu));
	written_rmw = READ_ONCE(per_cpu(kd_gs_probe_rmw, state->cpu));
	atomic64_inc(attempts);
	if (state->seen_value == state->expected_value &&
	    state->seen_task == (unsigned long)state->expected_task &&
	    written_value == state->expected_value + KD_GS_PROBE_DELTA &&
	    written_rmw == state->expected_rmw + 1) {
		atomic64_inc(successes);
		return;
	}

	atomic64_inc(failures);
	pr_err_ratelimited(
		"kd_gs probe mismatch: kind=%s cpu=%d value=%lx/%lx write=%lx rmw=%lx/%lx task=%lx/%px\n",
		mutex_mode ? "mutex" : "spin", state->cpu, state->seen_value,
		state->expected_value, written_value, written_rmw,
		state->expected_rmw + 1, state->seen_task,
		state->expected_task);
}
