/*
 * klock_module — test device driver for kdlock benchmarking.
 *
 * Exposes /dev/lock_dev with an ioctl interface.  Each ioctl call executes
 * a synthetic critical section using either a spinlock or mutex (depending
 * on mode), optionally with a nested lock or a kernel API call inside the
 * critical section.  When kdlock_km is loaded with target_process="klock_test",
 * these lock operations trigger the kdlock hooks and exercise the delegation
 * path.
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/mutex.h>
#include <linux/percpu.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/ktime.h>
#include <linux/string.h>
#include <linux/sched.h>

#define DRIVER_NAME "lock_dev"

extern int kd_spin_debug_waiter_count(raw_spinlock_t *lock);
extern int kd_mutex_debug_waiter_count(struct mutex *lock);
extern int kd_mutex_debug_nested_waiters(void);

struct test_args {
	unsigned long loop_count;
	unsigned long work_load;
	unsigned int mode;
	unsigned int role;
};

#define IOC_MAGIC 'k'
#define IOC_RUN_TEST _IOW(IOC_MAGIC, 1, struct test_args)

static DEFINE_SPINLOCK(global_lock);
static DEFINE_SPINLOCK(nested_lock_a);
static DEFINE_SPINLOCK(nested_lock_b);
static DEFINE_SPINLOCK(nested_lock_c);
static DEFINE_MUTEX(global_mutex);
static DEFINE_MUTEX(nested_mutex_a);
static DEFINE_MUTEX(nested_mutex_b);
static DEFINE_PER_CPU(unsigned long, kd_gs_probe_value);
static DEFINE_PER_CPU(unsigned long, kd_gs_probe_rmw);

static unsigned long global_counter = 0;
static unsigned long mode2_api_observations;
static unsigned long mode5_api_observations;

/* Each request has a distinct record: entry replay cannot hide behind an
 * aggregate counter. The ordinary noinline call deliberately starts missing. */
#define KD_RESUME_RECORDS 65536
static unsigned int native_resume_stage;
module_param(native_resume_stage, uint, 0444);
static bool native_resume_rename;
/* Arm only after promotion so task_lock traffic cannot change the hot-lock
 * sampling window of the mutex under test. */
module_param(native_resume_rename, bool, 0644);
static atomic_t mutex_inside = ATOMIC_INIT(0);
static atomic_t mutex_overlaps = ATOMIC_INIT(0);
struct kd_resume_record {
	struct task_struct *task;
	unsigned long value;
	unsigned int before, called, after;
};
static struct kd_resume_record *resume_records;
static atomic_t resume_requests = ATOMIC_INIT(0);
static atomic_t resume_failures = ATOMIC_INIT(0);

/* Test-only comm changes exercise routing without requiring the unexported
 * __set_task_comm API or another guest kernel patch. */
static void kd_test_rename(const char *name)
{
	task_lock(current);
	strscpy(current->comm, name, TASK_COMM_LEN);
	task_unlock(current);
}

static struct kd_resume_record *kd_resume_begin(void)
{
	struct kd_resume_record *record;
	int id;

	if (!native_resume_stage)
		return NULL;
	id = atomic_inc_return(&resume_requests) - 1;
	if (id >= KD_RESUME_RECORDS) {
		atomic_inc(&resume_failures);
		return NULL;
	}
	record = &resume_records[id];
	record->task = current;
	record->value = (unsigned long)id + 1;
	return record;
}

static __attribute__((noipa)) noinline void
kd_resume_native_probe(struct kd_resume_record *record)
{
	if (record->task != current || record->before != 1 ||
	    record->called || record->after)
		atomic_inc(&resume_failures);
	record->called++;
	record->value += 17;
	if (native_resume_rename)
		kd_test_rename("kd_renamed");
}

static __always_inline void kd_resume_probe(struct kd_resume_record *record,
					    unsigned int stage)
{
	if (!record || native_resume_stage != stage)
		return;
	record->before++;
	record->value *= 3;
	kd_resume_native_probe(record);
	record->after++;
	record->value ^= 0x5a5a;
}

#define KD_CS_LANES 4
#define KD_CS_VERIFY_LIMIT 10000000UL
#define KD_CS_ODD_BIAS 0x9e3779b97f4a7c15UL
#define KD_CS_EVEN_BIAS 0xc2b2ae3d27d4eb4fUL
#define KD_CS_COMMIT_BIAS 0x165667b19e3779f9UL

enum kd_cs_state_id {
	KD_CS_SPIN_GLOBAL,
	KD_CS_SPIN_A,
	KD_CS_SPIN_B,
	KD_CS_SPIN_C,
	KD_CS_MUTEX_GLOBAL,
	KD_CS_MUTEX_A,
	KD_CS_MUTEX_B,
	KD_CS_STATE_COUNT,
};

struct kd_cs_state {
	unsigned long sequence;
	unsigned long sum;
	unsigned long branch_mix;
	unsigned long rolling;
	unsigned long lanes[KD_CS_LANES];
	unsigned long commit;
};

static struct kd_cs_state kd_cs_states[KD_CS_STATE_COUNT];
static const char *const kd_cs_state_names[KD_CS_STATE_COUNT] = {
	[KD_CS_SPIN_GLOBAL] = "spin-global",
	[KD_CS_SPIN_A] = "spin-a",
	[KD_CS_SPIN_B] = "spin-b",
	[KD_CS_SPIN_C] = "spin-c",
	[KD_CS_MUTEX_GLOBAL] = "mutex-global",
	[KD_CS_MUTEX_A] = "mutex-a",
	[KD_CS_MUTEX_B] = "mutex-b",
};

/* Keep this inline: every operation is part of the translated critical section. */
static __always_inline void kd_cs_transition(struct kd_cs_state *state)
{
	unsigned long next = state->sequence + 1;
	unsigned long sum = state->sum + next;
	unsigned long branch_mix = state->branch_mix;
	unsigned long rolling;
	unsigned long lane = next & (KD_CS_LANES - 1);

	state->sequence = next;
	state->sum = sum;
	if (next & 1)
		branch_mix += (next << 1) ^ KD_CS_ODD_BIAS;
	else
		branch_mix ^= (next << 2) + KD_CS_EVEN_BIAS;
	state->branch_mix = branch_mix;

	rolling = state->rolling ^ (sum + branch_mix);
	rolling = (rolling << 7) | (rolling >> 57);
	state->rolling = rolling;
	state->lanes[lane] += next + lane + (rolling & 0xffff);
	state->commit = (sum ^ branch_mix ^ rolling ^ state->lanes[0] ^
			 state->lanes[1] ^ state->lanes[2] ^ state->lanes[3]) +
			next * KD_CS_COMMIT_BIAS;
}

static __always_inline void kd_cs_step(enum kd_cs_state_id id)
{
	kd_cs_transition(&kd_cs_states[id]);
	global_counter++;
}

static atomic_t inner_holder_ready = ATOMIC_INIT(0);
static atomic_t inner_direct_waiting = ATOMIC_INIT(0);
static atomic_t inner_nested_waiting = ATOMIC_INIT(0);
static atomic_t inner_trailing_waiting = ATOMIC_INIT(0);
static atomic_t outer_holder_ready = ATOMIC_INIT(0);
static atomic_t outer_direct_waiting = ATOMIC_INIT(0);
static atomic_t outer_nested_waiting = ATOMIC_INIT(0);
static atomic_t outer_trailing_waiting = ATOMIC_INIT(0);
static atomic_t mutex_inner_holder_ready = ATOMIC_INIT(0);
static atomic_t mutex_inner_direct_waiting = ATOMIC_INIT(0);
static atomic_t mutex_inner_nested_waiting = ATOMIC_INIT(0);
static atomic_t mutex_inner_trailing_waiting = ATOMIC_INIT(0);
static atomic_t mutex_outer_holder_ready = ATOMIC_INIT(0);
static atomic_t mutex_outer_direct_waiting = ATOMIC_INIT(0);
static atomic_t mutex_outer_nested_waiting = ATOMIC_INIT(0);
static atomic_t mutex_outer_trailing_waiting = ATOMIC_INIT(0);
static atomic64_t gs_spin_attempts = ATOMIC64_INIT(0);
static atomic64_t gs_spin_successes = ATOMIC64_INIT(0);
static atomic64_t gs_spin_failures = ATOMIC64_INIT(0);
static atomic64_t gs_mutex_attempts = ATOMIC64_INIT(0);
static atomic64_t gs_mutex_successes = ATOMIC64_INIT(0);
static atomic64_t gs_mutex_failures = ATOMIC64_INIT(0);

#define MODE_ROLE_SYNCHRONIZED 0x80000000U
#define MODE_ROLE_OUTER_ONLY 0x40000000U

#define MODE_SPIN_CONTENTION 0
#define MODE_SPIN_NESTED 1
#define MODE_SPIN_API_IN_LOCK 2
#define MODE_MUTEX_CONTENTION 3
#define MODE_MUTEX_NESTED 4
#define MODE_MUTEX_API_IN_LOCK 5
#define MODE_SPIN_DEEP_NESTED 6
#define MODE_SPIN_OOO_NESTED 7
#define MODE_SPIN_INNER_CONTENTION 8
#define MODE_SPIN_ABORT_RECOVERY 9
#define MODE_SPIN_GS_CONTEXT 10
#define MODE_MUTEX_GS_CONTEXT 11

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

static void run_contention_test(unsigned long loop_count,
				unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		struct kd_resume_record *record = kd_resume_begin();

		spin_lock(&global_lock);

		kd_cs_step(KD_CS_SPIN_GLOBAL);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		kd_resume_probe(record, 1);
		spin_unlock(&global_lock);
	}
}

static void run_nested_spinlock_test(unsigned long loop_count,
				     unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		struct kd_resume_record *record = kd_resume_begin();

		spin_lock(&nested_lock_a);
		spin_lock(&nested_lock_b);

		kd_cs_step(KD_CS_SPIN_B);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		kd_resume_probe(record, 3);
		spin_unlock(&nested_lock_b);
		kd_resume_probe(record, 2);
		spin_unlock(&nested_lock_a);
	}
}

static void run_deep_nested_spinlock_test(unsigned long loop_count,
					  unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&nested_lock_a);
		spin_lock(&nested_lock_b);
		spin_lock(&nested_lock_c);

		kd_cs_step(KD_CS_SPIN_C);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&nested_lock_c);
		spin_unlock(&nested_lock_b);
		spin_unlock(&nested_lock_a);
	}
}

static void run_ooo_nested_spinlock_test(unsigned long loop_count,
					 unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&nested_lock_a);
		spin_lock(&nested_lock_b);

		kd_cs_step(KD_CS_SPIN_B);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&nested_lock_a);
		spin_unlock(&nested_lock_b);
	}
}

static noinline void prepare_inner_nested_role(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&inner_holder_ready) ||
	       atomic_read(&inner_direct_waiting) < 2 ||
	       !atomic_read(&outer_holder_ready) ||
	       atomic_read(&outer_direct_waiting) < 2)
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 1 ||
	       kd_spin_debug_waiter_count(&nested_lock_b.rlock) < 1)
		cpu_relax();
}

static noinline void run_inner_nested_role(unsigned long work_load,
					   bool synchronized, bool outer_only)
{
	unsigned long j;
	volatile int dummy_computation = 0;
	struct kd_resume_record *record = outer_only ? NULL : kd_resume_begin();

	prepare_inner_nested_role(synchronized);
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
	spin_lock(&nested_lock_b);
	kd_cs_step(KD_CS_SPIN_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	kd_resume_probe(record, 3);
	spin_unlock(&nested_lock_b);
	kd_resume_probe(record, 2);
	spin_unlock(&nested_lock_a);
}

static noinline void run_gs_spin_nested_role(unsigned long work_load,
					     bool synchronized)
{
	struct kd_gs_probe_state probe;
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_inner_nested_role(synchronized);
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
	spin_lock(&nested_lock_b);
	kd_cs_step(KD_CS_SPIN_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_b);
}

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
	while (atomic_read(&inner_direct_waiting) < 2 ||
	       !atomic_read(&inner_nested_waiting) ||
	       !atomic_read(&inner_trailing_waiting))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_b.rlock) < 3)
		cpu_relax();
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

	prepare_outer_direct_role(synchronized);
	spin_lock(&nested_lock_a);
	kd_cs_step(KD_CS_SPIN_A);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_a);
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

	prepare_outer_trailing_role(synchronized);
	spin_lock(&nested_lock_a);
	kd_cs_step(KD_CS_SPIN_A);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_a);
}

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
		else
			run_inner_direct_role(work_load, synchronized);
	}
}

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

		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&global_lock);
	}
}

static int run_mutex_contention_test(unsigned long loop_count,
				    unsigned long work_load, unsigned int role)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

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
		mutex_unlock(&global_mutex);
		if (native_resume_rename)
			kd_test_rename("klock_test");
	}
	return 0;
}

static noinline void prepare_nested_mutex_role(void)
{
	while (!atomic_read(&mutex_inner_holder_ready) ||
	       !atomic_read(&mutex_inner_direct_waiting) ||
	       !atomic_read(&mutex_outer_holder_ready) ||
	       !atomic_read(&mutex_outer_direct_waiting))
		cpu_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_a) < 1)
		cpu_relax();
}

static noinline void run_nested_mutex_cs(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;
	struct kd_resume_record *record = kd_resume_begin();

	atomic_set(&mutex_outer_nested_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	atomic_set(&mutex_inner_nested_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_b);

	kd_cs_step(KD_CS_MUTEX_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;

	kd_resume_probe(record, 3);
	mutex_unlock(&nested_mutex_b);
	kd_resume_probe(record, 2);
	mutex_unlock(&nested_mutex_a);
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

static noinline void run_inner_mutex_direct_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_inner_holder_ready))
		cpu_relax();
	atomic_set(&mutex_inner_direct_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_b);
	kd_cs_step(KD_CS_MUTEX_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_b);
}

static noinline void run_inner_mutex_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&mutex_inner_holder_ready, 0);
	atomic_set(&mutex_inner_direct_waiting, 0);
	atomic_set(&mutex_inner_nested_waiting, 0);
	atomic_set(&mutex_inner_trailing_waiting, 0);
	smp_mb__after_atomic();

	mutex_lock(&nested_mutex_b);
	atomic_set(&mutex_inner_holder_ready, 1);
	smp_mb__after_atomic();
	while (!atomic_read(&mutex_inner_direct_waiting) ||
	       !atomic_read(&mutex_inner_nested_waiting) ||
	       !atomic_read(&mutex_inner_trailing_waiting))
		cpu_relax();
	/* B stays native. Wait until the A executor has actually failed to
	 * acquire B before releasing it; no shadow-queue count is involved. */
	while (!kd_mutex_debug_nested_waiters())
		cpu_relax();
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	kd_cs_step(KD_CS_MUTEX_B);
	mutex_unlock(&nested_mutex_b);
}

static noinline void run_inner_mutex_trailing_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_inner_nested_waiting))
		cpu_relax();
	atomic_set(&mutex_inner_trailing_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_b);
	kd_cs_step(KD_CS_MUTEX_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_b);
}

static noinline void run_outer_mutex_direct_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_outer_holder_ready))
		cpu_relax();
	atomic_set(&mutex_outer_direct_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	kd_cs_step(KD_CS_MUTEX_A);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_a);
}

static noinline void run_outer_mutex_holder_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	atomic_set(&mutex_outer_holder_ready, 0);
	atomic_set(&mutex_outer_direct_waiting, 0);
	atomic_set(&mutex_outer_nested_waiting, 0);
	atomic_set(&mutex_outer_trailing_waiting, 0);
	smp_mb__after_atomic();

	mutex_lock(&nested_mutex_a);
	atomic_set(&mutex_outer_holder_ready, 1);
	smp_mb__after_atomic();
	while (!atomic_read(&mutex_outer_direct_waiting) ||
	       !atomic_read(&mutex_outer_nested_waiting) ||
	       !atomic_read(&mutex_outer_trailing_waiting))
		cpu_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_a) < 3)
		cpu_relax();
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	kd_cs_step(KD_CS_MUTEX_A);
	mutex_unlock(&nested_mutex_a);
}

static noinline void run_outer_mutex_trailing_role(unsigned long work_load)
{
	unsigned long j;
	volatile int dummy_computation = 0;

	while (!atomic_read(&mutex_outer_nested_waiting))
		cpu_relax();
	while (kd_mutex_debug_waiter_count(&nested_mutex_a) < 2)
		cpu_relax();
	atomic_set(&mutex_outer_trailing_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	kd_cs_step(KD_CS_MUTEX_A);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_a);
}

static void run_nested_mutex_test(unsigned long loop_count,
				  unsigned long work_load, unsigned int role,
				  bool gs_context)
{
	unsigned long i;
	unsigned int sync_role = role & ~MODE_ROLE_SYNCHRONIZED;
	bool synchronized = role & MODE_ROLE_SYNCHRONIZED;

	for (i = 0; i < loop_count; i++) {
		if (!synchronized || sync_role == 0)
			run_nested_mutex_role(work_load, synchronized,
					      gs_context);
		else if (sync_role == 1)
			run_inner_mutex_holder_role(work_load);
		else if (sync_role == 2)
			run_inner_mutex_direct_role(work_load);
		else if (sync_role == 3)
			run_outer_mutex_holder_role(work_load);
		else if (sync_role == 4)
			run_outer_mutex_direct_role(work_load);
		else if (sync_role == 5)
			run_inner_mutex_trailing_role(work_load);
		else if (sync_role == 6)
			run_outer_mutex_trailing_role(work_load);
	}
}

static void run_api_in_mutex_test(unsigned long loop_count,
				  unsigned long work_load)
{
	unsigned long i, j;
	unsigned long now;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		mutex_lock(&global_mutex);

		kd_cs_step(KD_CS_MUTEX_GLOBAL);
		now = (unsigned long)ktime_get_ns();
		dummy_computation ^= (int)(now & 0xffff);
		if (now)
			mode5_api_observations++;
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		mutex_unlock(&global_mutex);
	}
}

static long my_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct test_args k_args;

	switch (cmd) {
	case IOC_RUN_TEST:
		if (copy_from_user(&k_args, (void __user *)arg, sizeof(k_args)))
			return -EFAULT;
		if (k_args.mode == MODE_SPIN_CONTENTION)
			run_contention_test(k_args.loop_count,
					    k_args.work_load);
		else if (k_args.mode == MODE_SPIN_NESTED)
			run_nested_spinlock_test(k_args.loop_count,
						 k_args.work_load);
		else if (k_args.mode == MODE_SPIN_API_IN_LOCK)
			run_api_in_lock_test(k_args.loop_count,
					     k_args.work_load);
		else if (k_args.mode == MODE_MUTEX_CONTENTION)
			return run_mutex_contention_test(k_args.loop_count,
						 k_args.work_load, k_args.role);
		else if (k_args.mode == MODE_MUTEX_NESTED)
			run_nested_mutex_test(k_args.loop_count,
					      k_args.work_load, k_args.role,
					      false);
		else if (k_args.mode == MODE_MUTEX_API_IN_LOCK)
			run_api_in_mutex_test(k_args.loop_count,
					      k_args.work_load);
		else if (k_args.mode == MODE_SPIN_DEEP_NESTED)
			run_deep_nested_spinlock_test(k_args.loop_count,
						      k_args.work_load);
		else if (k_args.mode == MODE_SPIN_OOO_NESTED)
			run_ooo_nested_spinlock_test(k_args.loop_count,
						     k_args.work_load);
		else if (k_args.mode == MODE_SPIN_INNER_CONTENTION)
			run_inner_contention_spinlock_test(k_args.loop_count,
							   k_args.work_load,
							   k_args.role, false);
		else if (k_args.mode == MODE_SPIN_ABORT_RECOVERY)
			run_abort_recovery_spinlock_test(k_args.loop_count,
							 k_args.work_load,
							 k_args.role);
		else if (k_args.mode == MODE_SPIN_GS_CONTEXT)
			run_inner_contention_spinlock_test(k_args.loop_count,
							   k_args.work_load,
							   k_args.role, true);
		else if (k_args.mode == MODE_MUTEX_GS_CONTEXT)
			run_nested_mutex_test(k_args.loop_count,
					      k_args.work_load, k_args.role,
					      true);
		else
			return -EINVAL;
		break;
	default:
		return -EINVAL;
	}
	return 0;
}

static const struct file_operations my_fops = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = my_ioctl,
};

static struct miscdevice my_misc_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = DRIVER_NAME,
	.fops = &my_fops,
};

static unsigned int kd_cs_validate(unsigned long *operations,
				   unsigned int *active_states)
{
	unsigned int failures = 0;
	unsigned int id;

	*operations = 0;
	*active_states = 0;
	for (id = 0; id < KD_CS_STATE_COUNT; id++) {
		struct kd_cs_state expected = {};
		struct kd_cs_state *state = &kd_cs_states[id];
		unsigned long count = READ_ONCE(state->sequence);
		unsigned long i;

		*operations += count;
		if (!count)
			continue;
		(*active_states)++;
		if (count > KD_CS_VERIFY_LIMIT) {
			failures++;
			pr_err("kd_cs integrity limit: state=%s operations=%lu limit=%lu\n",
			       kd_cs_state_names[id], count,
			       KD_CS_VERIFY_LIMIT);
			continue;
		}

		for (i = 0; i < count; i++)
			kd_cs_transition(&expected);
		if (memcmp(state, &expected, sizeof(expected))) {
			failures++;
			pr_err("kd_cs integrity mismatch: state=%s operations=%lu commit=%lx/%lx\n",
			       kd_cs_state_names[id], count, state->commit,
			       expected.commit);
		}
	}

	if (*operations != READ_ONCE(global_counter)) {
		failures++;
		pr_err("kd_cs operation mismatch: states=%lu counter=%lu\n",
		       *operations, READ_ONCE(global_counter));
	}
	return failures;
}

static int __init my_module_init(void)
{
	int cpu;
	int ret;

	if (native_resume_stage > 3)
		return -EINVAL;
	if (native_resume_stage) {
		resume_records = kvcalloc(KD_RESUME_RECORDS,
					 sizeof(*resume_records), GFP_KERNEL);
		if (!resume_records)
			return -ENOMEM;
	}
	global_counter = 0;
	mode2_api_observations = 0;
	mode5_api_observations = 0;
	memset(kd_cs_states, 0, sizeof(kd_cs_states));
	atomic64_set(&gs_spin_attempts, 0);
	atomic64_set(&gs_spin_successes, 0);
	atomic64_set(&gs_spin_failures, 0);
	atomic64_set(&gs_mutex_attempts, 0);
	atomic64_set(&gs_mutex_successes, 0);
	atomic64_set(&gs_mutex_failures, 0);
	for_each_possible_cpu(cpu) {
		per_cpu(kd_gs_probe_value, cpu) = ~0UL;
		per_cpu(kd_gs_probe_rmw, cpu) = ~0UL;
	}
	ret = misc_register(&my_misc_device);
	if (ret) {
		pr_err("failed to register %s: %d\n", DRIVER_NAME, ret);
		kvfree(resume_records);
		return ret;
	}
	pr_info("module loaded\n");
	return 0;
}

static void __exit my_module_exit(void)
{
	unsigned long cs_operations;
	unsigned int cs_active_states;
	unsigned int cs_failures;
	int id, requests = atomic_read(&resume_requests);

	misc_deregister(&my_misc_device);
	for (id = 0; id < min(requests, KD_RESUME_RECORDS); id++) {
		struct kd_resume_record *record = &resume_records[id];
		unsigned long expected = (((unsigned long)id + 1) * 3 + 17) ^ 0x5a5a;

		if (record->before != 1 || record->called != 1 ||
		    record->after != 1 || record->value != expected)
			atomic_inc(&resume_failures);
	}
	pr_info("kd_resume records: requests=%d failures=%d\n",
		requests, atomic_read(&resume_failures));
	pr_info("kd_mutex oracle: inside=%d overlaps=%d\n",
		atomic_read(&mutex_inside), atomic_read(&mutex_overlaps));
	kvfree(resume_records);
	cs_failures = kd_cs_validate(&cs_operations, &cs_active_states);
	pr_info("module unloaded, final counter: %lu\n", global_counter);
	pr_info("kd_cs integrity: operations=%lu active_states=%u failures=%u\n",
		cs_operations, cs_active_states, cs_failures);
	pr_info("mode2 api observations: %lu\n", mode2_api_observations);
	pr_info("mode5 api observations: %lu\n", mode5_api_observations);
	pr_info("kd_gs spin stats: attempts=%lld successes=%lld failures=%lld\n",
		(long long)atomic64_read(&gs_spin_attempts),
		(long long)atomic64_read(&gs_spin_successes),
		(long long)atomic64_read(&gs_spin_failures));
	pr_info("kd_gs mutex stats: attempts=%lld successes=%lld failures=%lld\n",
		(long long)atomic64_read(&gs_mutex_attempts),
		(long long)atomic64_read(&gs_mutex_successes),
		(long long)atomic64_read(&gs_mutex_failures));
}

module_init(my_module_init);
module_exit(my_module_exit);

MODULE_LICENSE("GPL");
