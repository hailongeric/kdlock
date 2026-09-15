/*
 * Optional inclusive boundary timing; disabled runs take no clock samples.
 * Private implementation included only by exe.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* Optional inclusive C-boundary timings, not instruction or CPU time.
 * Load-time selection keeps every invocation in one session under the same
 * policy. Disabled invocations take no extra clock samples or atomic updates.
 * Nested dispatch/control intervals may overlap; never sum them as wall time.
 * Measurement failure cannot change an execution, replay or owner decision. */
enum kd_jit_timing_phase {
	KD_JIT_TIME_DISPATCH,
	KD_JIT_TIME_WRAPPER,
	KD_JIT_TIME_HOSTCALL,
	KD_JIT_TIME_CONTROL,
	KD_JIT_TIME_NATIVE_SPIN_WAIT,
	KD_JIT_TIME_NATIVE_MUTEX_WAIT,
	KD_JIT_TIME_SPIN_QUEUE,
	KD_JIT_TIME_MUTEX_QUEUE,
	KD_JIT_TIME_NATIVE_SPIN_HANDOFF,
	KD_JIT_TIME_NATIVE_MUTEX_HANDOFF,
	KD_JIT_TIME_COUNT,
};
static bool kd_jit_timing;
module_param_named(jit_timing, kd_jit_timing, bool, 0444);
MODULE_PARM_DESC(jit_timing, "Collect inclusive JIT boundary timings at unload");

static struct kd_jit_timing_stat {
	atomic64_t samples;
	atomic64_t ns;
	atomic_t invalid;
} kd_jit_times[KD_JIT_TIME_COUNT];

static inline u64 kd_jit_timing_start(void)
{
	return unlikely(kd_jit_timing) ? ktime_get_ns() : 0;
}

/* Keep overflow visible without wrapping signed counters or failing a CS. */
static inline void kd_jit_timing_add(struct kd_jit_timing_stat *stat,
				     atomic64_t *counter, u64 amount)
{
	s64 old = atomic64_read(counter);

	for (;;) {
		if (old < 0 || amount > (u64)(S64_MAX - old)) {
			atomic_set(&stat->invalid, 1);
			return;
		}
		if (atomic64_try_cmpxchg(counter, &old, old + (s64)amount))
			return;
	}
}

/* Queue service is confirmed only after dispatch returns. Accept the saved
 * pre-dispatch endpoint so the generated body is not charged as queue wait. */
static inline void kd_jit_timing_record(enum kd_jit_timing_phase phase,
				       u64 start, u64 end)
{
	struct kd_jit_timing_stat *stat = &kd_jit_times[phase];

	kd_jit_timing_add(stat, &stat->samples, 1);
	if (end < start) {
		atomic_set(&stat->invalid, 1);
		return;
	}
	kd_jit_timing_add(stat, &stat->ns, end - start);
}

static inline void kd_jit_timing_end(enum kd_jit_timing_phase phase, u64 start)
{
	if (likely(!kd_jit_timing))
		return;
	kd_jit_timing_record(phase, start, ktime_get_ns());
}

static inline void kd_jit_timing_reset(void)
{
	int i;

	for (i = 0; i < KD_JIT_TIME_COUNT; i++) {
		atomic64_set(&kd_jit_times[i].samples, 0);
		atomic64_set(&kd_jit_times[i].ns, 0);
		atomic_set(&kd_jit_times[i].invalid, 0);
	}
}

/* Teardown follows drain: paired readers require exactly one row per phase,
 * including zero rows for a native-only session with measurement enabled. */
static inline void kd_jit_timing_report(void)
{
	/* Bind log labels to their counters explicitly: declaration order must
	 * not silently relabel an interval consumed by the evidence observer. */
	static const char * const names[KD_JIT_TIME_COUNT] = {
		[KD_JIT_TIME_DISPATCH] = "dispatch",
		[KD_JIT_TIME_WRAPPER] = "wrapper",
		[KD_JIT_TIME_HOSTCALL] = "hostcall",
		[KD_JIT_TIME_CONTROL] = "control",
		[KD_JIT_TIME_NATIVE_SPIN_WAIT] = "native_spin_wait",
		[KD_JIT_TIME_NATIVE_MUTEX_WAIT] = "native_mutex_wait",
		[KD_JIT_TIME_SPIN_QUEUE] = "spin_queue",
		[KD_JIT_TIME_MUTEX_QUEUE] = "mutex_queue",
		[KD_JIT_TIME_NATIVE_SPIN_HANDOFF] = "native_spin_handoff",
		[KD_JIT_TIME_NATIVE_MUTEX_HANDOFF] = "native_mutex_handoff",
	};
	int i;

	if (!kd_jit_timing)
		return;
	for (i = 0; i < KD_JIT_TIME_COUNT; i++)
		KD_PR_INFO("kd_jit timing: phase=%s samples=%lld ns=%lld invalid=%d\n",
			   names[i],
			   (long long)atomic64_read(&kd_jit_times[i].samples),
			   (long long)atomic64_read(&kd_jit_times[i].ns),
			   atomic_read(&kd_jit_times[i].invalid));
}

/* Keep metrics private to the executor. The shared owner wait uses only a
 * local timestamp/backend, never waiter storage that the final ACK releases. */
u64 kd_exe_native_timing_start(void)
{
	return kd_jit_timing_start();
}

void kd_exe_native_timing_end(bool mutex, u64 start)
{
	kd_jit_timing_end(mutex ? KD_JIT_TIME_NATIVE_MUTEX_WAIT :
				 KD_JIT_TIME_NATIVE_SPIN_WAIT, start);
}

/* This contains, rather than adds to, the owner-wait interval. The caller
 * captures start before either remote or local waiter publication and supplies
 * no waiter/node pointer after ACK. Nested remote envelopes may overlap. */
void kd_exe_native_handoff_timing_end(bool mutex, u64 start)
{
	kd_jit_timing_end(mutex ? KD_JIT_TIME_NATIVE_MUTEX_HANDOFF :
				 KD_JIT_TIME_NATIVE_SPIN_HANDOFF, start);
}

u64 kd_exe_queue_timing_start(void)
{
	return kd_jit_timing_start();
}

/* The queue owner and waiter consume this field in protocol order, not
 * concurrently: dispatch finishes before wake; acquisition precedes node reuse.
 * Zero means disabled, not queued or already accounted. Module-loaded clocks
 * use nonzero monotonic uptime. Measurements never decide ownership or replay. */
void kd_exe_queue_timing_end(bool mutex, u64 *queued_at, u64 end)
{
	u64 start;

	if (likely(!kd_jit_timing) || !*queued_at)
		return;
	start = *queued_at;
	*queued_at = 0;
	kd_jit_timing_record(mutex ? KD_JIT_TIME_MUTEX_QUEUE :
				    KD_JIT_TIME_SPIN_QUEUE, start, end);
}
