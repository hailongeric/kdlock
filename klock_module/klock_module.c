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
#include <linux/jiffies.h>
#include <kernel/locking/mutex.h>

#define DRIVER_NAME "lock_dev"

extern int kd_spin_debug_waiter_count(raw_spinlock_t *lock);
extern unsigned int kd_spin_debug_word(raw_spinlock_t *lock);
extern unsigned long kd_spin_debug_owner(raw_spinlock_t *lock);
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
/* A plus eight child locks crosses the production eight-lock frame limit. */
#define KD_RESUME_DEPTH_LOCKS 8
static struct mutex resume_depth_locks[KD_RESUME_DEPTH_LOCKS];
static DEFINE_PER_CPU(unsigned long, kd_gs_probe_value);
static DEFINE_PER_CPU(unsigned long, kd_gs_probe_rmw);

static unsigned long mode2_api_observations;
static unsigned long mode5_api_observations;

/* Each request has a distinct record: entry replay cannot hide behind an
 * aggregate counter. The ordinary noinline call deliberately starts missing. */
#define KD_RESUME_RECORDS 65536
static unsigned int native_resume_stage;
module_param(native_resume_stage, uint, 0444);
static bool native_resume_rename;
static bool native_pending_contended;
module_param(native_pending_contended, bool, 0444);
MODULE_PARM_DESC(native_pending_contended,
		 "Stage 4 oracle: hold B until the original waiter queues");
static bool native_depth_armed;
module_param(native_depth_armed, bool, 0644);
MODULE_PARM_DESC(native_depth_armed,
		 "Stage 5: arm the deep callee only after outer-A promotion");
static unsigned int mixed_lock_probe;
module_param(mixed_lock_probe, uint, 0644);
MODULE_PARM_DESC(
	mixed_lock_probe,
	"Mode 3 admission probe: 0=off, 1=outer-only warmup, 2=mixed locks");
/* Arm only after promotion so task_lock traffic cannot change the hot-lock
 * sampling window of the mutex under test. */
module_param(native_resume_rename, bool, 0644);
static atomic_t mutex_inside = ATOMIC_INIT(0);
static atomic_t mutex_overlaps = ATOMIC_INIT(0);
struct kd_resume_record {
	struct task_struct *task;
	unsigned long value;
	unsigned int before, called, after;
	unsigned long ooo_value;
	unsigned int ooo_seen;
};
static struct kd_resume_record *resume_records;
static atomic_t resume_requests = ATOMIC_INIT(0);
static atomic_t resume_failures = ATOMIC_INIT(0);
static struct kd_resume_record *pending_mutex_record;
static unsigned long pending_mutex_a_owner;
static unsigned int pending_mutex_observed;
static unsigned int pending_mutex_acquired;
static struct kd_resume_record *pending_spin_record;
static unsigned int pending_spin_observed;
static unsigned int pending_spin_acquired;
static atomic_t depth_capacity_resumes = ATOMIC_INIT(0);
static atomic_t depth_callee_resumes = ATOMIC_INIT(0);
static atomic_t depth_native_runs = ATOMIC_INIT(0);

#include "../tests/kernel/native_register_workload.c"

static void kd_signal_hold(struct kd_resume_record *record);
static bool mutex_signal_race;
static noinline void kd_signal_owner_unlock(bool done);

/* Match the non-RT mutex owner encoding used by the production hook. */
static unsigned long kd_test_mutex_owner(struct mutex *lock)
{
	return atomic_long_read(&lock->owner) & ~0x7UL;
}

#include "../tests/kernel/native_waiter_signal_workload.c"

static bool kd_test_spin_origin_locked(u32 word)
{
	u32 locked = word & _Q_LOCKED_MASK;

	/* Linux PV waiters may mark L as _Q_SLOW_VAL while its owner holds it.
	 * The pending-spin script checks this private constant in matching KDIR. */
	return locked == _Q_LOCKED_VAL ||
	       (IS_ENABLED(CONFIG_PARAVIRT_SPINLOCKS) &&
		locked == (3U << _Q_LOCKED_OFFSET));
}

static void kd_resume_check_depth(struct kd_resume_record *record)
{
	unsigned long owner = kd_test_mutex_owner(&nested_mutex_a);
	unsigned int retained = 0, i;
	bool valid = owner != 0;

	for (i = 0; i < KD_RESUME_DEPTH_LOCKS; i++) {
		unsigned long child =
			kd_test_mutex_owner(&resume_depth_locks[i]);

		if (owner != (unsigned long)current && child == owner) {
			retained++;
			if (i == KD_RESUME_DEPTH_LOCKS - 1)
				valid = false;
		} else if (child != (unsigned long)current) {
			valid = false;
		}
	}
	if (retained && retained != KD_RESUME_DEPTH_LOCKS - 1)
		valid = false;
	if (!valid)
		atomic_inc(&resume_failures);
	if (owner == (unsigned long)current) {
		atomic_inc(&depth_native_runs);
		return;
	}
	if (retained)
		atomic_inc(&depth_capacity_resumes);
	else
		atomic_inc(&depth_callee_resumes);
	pr_info("kd_depth mutex: task=%d retained=%u children=%u valid=%u record=%lu\n",
		record->task->pid, retained, KD_RESUME_DEPTH_LOCKS, valid,
		(unsigned long)(record - resume_records));
}

/* Test-only comm changes exercise routing without requiring the unexported
 * __set_task_comm API or another guest kernel patch. */
static void kd_test_rename(const char *name)
{
	char previous[TASK_COMM_LEN];
	unsigned int before = preempt_count();
	bool irq = irqs_disabled();
	bool valid;

	task_lock(current);
	strscpy(previous, current->comm, sizeof(previous));
	strscpy(current->comm, name, TASK_COMM_LEN);
	task_unlock(current);
	valid = preempt_count() == before && irqs_disabled() == irq;
	if (!valid)
		atomic_inc(&resume_failures);
	pr_info("kd_resume rename: task=%d old=%s new=%s cpu=%d preempt_before=%u preempt_after=%u irq_before=%u irq_after=%u valid=%u\n",
		current->pid, previous, name, raw_smp_processor_id(), before,
		preempt_count(), irq, irqs_disabled(), valid);
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
	kd_register_begin(id);
	return record;
}

static __attribute__((noipa)) noinline void
kd_resume_native_probe(struct kd_resume_record *record)
{
	if (record->task != current || record->before != 1 || record->called ||
	    record->after)
		atomic_inc(&resume_failures);
	kd_signal_hold(record);
	if (native_resume_stage == 5 && READ_ONCE(native_depth_armed))
		kd_resume_check_depth(record);
	if (native_pending_contended &&
	    smp_load_acquire(&pending_spin_observed) &&
	    record == READ_ONCE(pending_spin_record)) {
		u32 a = atomic_read(&nested_lock_a.rlock.raw_lock.val);
		u32 b = atomic_read(&nested_lock_b.rlock.raw_lock.val);
		u32 a_private = kd_spin_debug_word(&nested_lock_a.rlock);
		bool valid = kd_test_spin_origin_locked(a) &&
			     (a_private & _Q_LOCKED_MASK) == 3 &&
			     b == _Q_LOCKED_VAL && record->task == current &&
			     kd_spin_debug_waiter_count(&nested_lock_b.rlock) ==
				     0;

		if (!valid || pending_spin_acquired)
			atomic_inc(&resume_failures);
		pending_spin_acquired++;
		pr_info("kd_pending spin acquired: task=%d cpu=%d outer=%lx lock=%lx a_val=%x b_val=%x a_private=%x valid=%u\n",
			current->pid, raw_smp_processor_id(),
			(unsigned long)&nested_lock_a,
			(unsigned long)&nested_lock_b, a, b, a_private, valid);
	}
	if (native_pending_contended && READ_ONCE(pending_mutex_observed) &&
	    record == READ_ONCE(pending_mutex_record)) {
		unsigned long a_owner = kd_test_mutex_owner(&nested_mutex_a);
		unsigned long b_owner = kd_test_mutex_owner(&nested_mutex_b);
		bool preserved = a_owner == pending_mutex_a_owner &&
				 b_owner == (unsigned long)current;

		if (!preserved || pending_mutex_acquired)
			atomic_inc(&resume_failures);
		pending_mutex_acquired++;
		pr_info("kd_pending mutex acquired: task=%d waiter=%lx a_owner=%lx b_owner=%lx preserved=%u\n",
			current->pid, (unsigned long)current, a_owner, b_owner,
			preserved);
		kd_waiter_signal_acquired(record);
	}
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
	kd_register_invoke(record);
	kd_resume_native_probe(record);
	record->after++;
	record->value ^= 0x5a5a;
}

/* Stage 4 spans the lock CALL: replaying A or skipping B cannot satisfy the
 * per-request before/called/after oracle after a pending acquisition exit. */
static __always_inline void
kd_resume_before_pending_lock(struct kd_resume_record *record)
{
	if (!record || native_resume_stage != 4)
		return;
	record->before++;
	record->value *= 3;
}

static __always_inline void
kd_resume_after_pending_lock(struct kd_resume_record *record)
{
	if (!record || native_resume_stage != 4)
		return;
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
/* A and B can execute concurrently. Each completion counter uses its own lock,
 * just like the state it checks; aggregate only after all workers have exited. */
static unsigned long kd_cs_completed[KD_CS_STATE_COUNT];
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
	kd_cs_completed[id]++;
}

#include "../tests/kernel/native_ooo_workload.c"
#include "../tests/kernel/remote_outer_workload.c"
#include "../tests/kernel/spin_chain_workload.c"
#include "../tests/kernel/remote_depth_workload.c"

/* A normal missing CALL is learned first. With its caller's A still held,
 * seven acquisitions fill the frame; the eighth must fail before acquisition
 * and continue natively with the prior seven children still owned by A's owner.
 * Keep the calls explicit so the fixture does not depend on loop inference. */
static __attribute__((noipa)) noinline void
kd_resume_depth_mutex(struct kd_resume_record *record)
{
	if (!record)
		return;
	mutex_lock(&resume_depth_locks[0]);
	mutex_lock(&resume_depth_locks[1]);
	mutex_lock(&resume_depth_locks[2]);
	mutex_lock(&resume_depth_locks[3]);
	mutex_lock(&resume_depth_locks[4]);
	mutex_lock(&resume_depth_locks[5]);
	mutex_lock(&resume_depth_locks[6]);
	record->before++;
	record->value *= 3;
	mutex_lock(&resume_depth_locks[7]);
	kd_resume_native_probe(record);
	record->after++;
	record->value ^= 0x5a5a;
	kd_cs_step(KD_CS_MUTEX_B);
	mutex_unlock(&resume_depth_locks[7]);
	mutex_unlock(&resume_depth_locks[6]);
	mutex_unlock(&resume_depth_locks[5]);
	mutex_unlock(&resume_depth_locks[4]);
	mutex_unlock(&resume_depth_locks[3]);
	mutex_unlock(&resume_depth_locks[2]);
	mutex_unlock(&resume_depth_locks[1]);
	mutex_unlock(&resume_depth_locks[0]);
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

#include "../tests/kernel/spin_native_workload.c"

static void run_contention_test(unsigned long loop_count,
				unsigned long work_load)
{
	unsigned long i, j;
	unsigned int count = preempt_count();
	bool irq = irqs_disabled();
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		struct kd_resume_record *record = kd_resume_begin();

		spin_lock(&global_lock);
		kd_spin_oracle_enter();
		kd_cs_step(KD_CS_SPIN_GLOBAL);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		kd_resume_probe(record, 1);
		atomic_dec(&spin_inside);
		spin_unlock(&global_lock);
		kd_spin_check_context(count, irq);
		if (native_resume_rename)
			kd_test_rename("klock_test");
	}
}

static void run_nested_spinlock_test(unsigned long loop_count,
				     unsigned long work_load, unsigned int role)
{
	unsigned long i, j;
	unsigned int count = preempt_count();
	bool irq = irqs_disabled();
	volatile int dummy_computation = 0;

	if (READ_ONCE(spin_ooo_dependency) && (role & MODE_ROLE_SYNCHRONIZED) &&
	    (role & ~MODE_ROLE_SYNCHRONIZED)) {
		kd_ooo_spin_role(role & ~MODE_ROLE_SYNCHRONIZED);
		return;
	}

	for (i = 0; i < loop_count; i++) {
		struct kd_resume_record *record = kd_resume_begin();

		kd_ooo_spin_prepare(record);
		spin_lock(&nested_lock_a);
		kd_resume_before_pending_lock(record);
		spin_lock(&nested_lock_b);
		kd_resume_after_pending_lock(record);

		kd_cs_step(KD_CS_SPIN_B);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		if (READ_ONCE(native_resume_ooo) == 3 && record) {
			kd_ooo_pending_spin_enter(record);
			kd_resume_probe(record, 3);
			kd_ooo_checkpoint(record, false, 1);
			kd_cs_step(KD_CS_SPIN_B);
			kd_ooo_pending_spin_leave();
			spin_unlock(&nested_lock_b);
			kd_ooo_checkpoint(record, false, 2);
			goto nested_spin_done;
		}
		if (READ_ONCE(native_resume_ooo) == 2 && record) {
			kd_ooo_jit_prefix(record);
			spin_unlock(&nested_lock_a);
			kd_resume_probe(record, 3);
			goto spin_ooo_after_a;
		}
		kd_resume_probe(record, 3);
		if (READ_ONCE(native_resume_ooo) == 1) {
			kd_ooo_checkpoint(record, false, 0);
			spin_unlock(&nested_lock_a);
spin_ooo_after_a:
			kd_ooo_checkpoint(record, false, 1);
			kd_cs_step(KD_CS_SPIN_B);
			spin_unlock(&nested_lock_b);
			kd_ooo_checkpoint(record, false, 2);
			goto nested_spin_done;
		}
		spin_unlock(&nested_lock_b);
		kd_resume_probe(record, 2);
		spin_unlock(&nested_lock_a);
nested_spin_done:
		kd_spin_check_context(count, irq);
		if (native_resume_rename)
			kd_test_rename("klock_test");
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

static noinline void prepare_inner_nested_role(bool synchronized,
					       struct kd_resume_record *record)
{
	int direct = native_pending_contended ? 1 : 2;

	/* Keep arming branches out of the caller's A acquisition site. */
	if (READ_ONCE(remote_spin_ooo)) {
		WRITE_ONCE(remote_ooo_waiter, current);
		WRITE_ONCE(remote_ooo_origin_cpu, raw_smp_processor_id());
		if (remote_spin_native_owner)
			while (!smp_load_acquire(&remote_ooo_c_ready))
				cpu_relax();
	}
	if (!synchronized)
		return;
	if (READ_ONCE(remote_spin_deep))
		kd_remote_c_prepare();
	/* Keep this branch outside the caller so warmup and contention share A's
	 * acquisition site, rather than registering only one compiler-split entry. */
	if (native_pending_contended && record)
		smp_store_release(&pending_spin_record, record);
	while (!atomic_read(&inner_holder_ready) ||
	       atomic_read(&inner_direct_waiting) < direct ||
	       !atomic_read(&outer_holder_ready) ||
	       atomic_read(&outer_direct_waiting) < 2)
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 1)
		cpu_relax();
	if (native_pending_contended) {
		/* One independent B contender owns the pending bit, not a node. */
		while (!(atomic_read(&nested_lock_b.rlock.raw_lock.val) &
			 _Q_PENDING_MASK))
			cpu_relax();
	} else {
		while (kd_spin_debug_waiter_count(&nested_lock_b.rlock) < 1)
			cpu_relax();
	}
}

static noinline void run_inner_nested_role(unsigned long work_load,
					   bool synchronized, bool outer_only)
{
	unsigned long j;
	unsigned int count = preempt_count();
	bool irq = irqs_disabled();
	volatile int dummy_computation = 0;
	struct kd_resume_record *record = outer_only ? NULL : kd_resume_begin();

	prepare_inner_nested_role(synchronized, record);
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
	kd_resume_before_pending_lock(record);
	spin_lock(&nested_lock_b);
	kd_resume_after_pending_lock(record);
	kd_cs_step(KD_CS_SPIN_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	if (READ_ONCE(remote_spin_ooo) && READ_ONCE(remote_spin_deep)) {
		atomic_set(&remote_c_nested, 1);
		smp_mb__after_atomic();
		spin_lock(&nested_lock_c);
		kd_cs_step(KD_CS_SPIN_C);
		remote_ooo_prefix++;
		if (READ_ONCE(remote_spin_ooo) == 2)
			kd_resume_probe(record, 3);
		if (READ_ONCE(remote_spin_reverse))
			spin_unlock(&nested_lock_b);
		else
			spin_unlock(&nested_lock_a);
		if (READ_ONCE(remote_spin_ooo) == 4)
			kd_resume_probe(record, 3);
		if (READ_ONCE(remote_spin_reverse))
			spin_unlock(&nested_lock_a);
		else
			spin_unlock(&nested_lock_b);
		if (READ_ONCE(remote_spin_ooo) == 3)
			kd_resume_probe(record, 3);
		spin_lock(&remote_lock_d);
		remote_ooo_suffix++;
		kd_cs_step(KD_CS_SPIN_C);
		spin_unlock(&remote_lock_d);
		spin_unlock(&nested_lock_c);
		goto inner_done;
	}
	if (READ_ONCE(remote_spin_ooo)) {
		remote_ooo_prefix++;
		if (READ_ONCE(remote_spin_ooo) == 2)
			kd_resume_probe(record, 3);
		spin_unlock(&nested_lock_a);
		if (READ_ONCE(remote_spin_ooo) == 3)
			kd_resume_probe(record, 3);
		spin_lock(&nested_lock_c);
		remote_ooo_suffix++;
		kd_cs_step(KD_CS_SPIN_B);
		spin_unlock(&nested_lock_c);
		spin_unlock(&nested_lock_b);
		goto inner_done;
	}
	kd_resume_probe(record, 3);
	spin_unlock(&nested_lock_b);
	kd_resume_probe(record, 2);
	spin_unlock(&nested_lock_a);
inner_done:
	kd_spin_check_context(count, irq);
	if (native_resume_rename)
		kd_test_rename("klock_test");
}

static noinline void run_gs_spin_nested_role(unsigned long work_load,
					     bool synchronized)
{
	struct kd_gs_probe_state probe;
	unsigned long j;
	volatile int dummy_computation = 0;

	prepare_inner_nested_role(synchronized, NULL);
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
	/* Stage 4 needs a Linux pending-bit holder, not another private request.
	 * Keep registration on the ordinary call site during unsynchronized warmup. */
	if (native_pending_contended && synchronized) {
		__raw_spin_lock(&nested_lock_b.rlock);
		kd_cs_step(KD_CS_SPIN_B);
		for (j = 0; j < work_load; j++)
			dummy_computation++;
		__raw_spin_unlock(&nested_lock_b.rlock);
		return;
	}
	spin_lock(&nested_lock_b);
	kd_cs_step(KD_CS_SPIN_B);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	spin_unlock(&nested_lock_b);
}

/* This fixture has one B pending-bit holder and one queued, CPU-pinned waiter.
 * While B is owned, its tail cannot drain or be replaced by another contender.
 * Observe the published tail, not merely a flag set before the lock CALL. */
static noinline void wait_for_pending_spin_waiter(void)
{
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		struct kd_resume_record *record =
			smp_load_acquire(&pending_spin_record);
		u32 b = atomic_read_acquire(&nested_lock_b.rlock.raw_lock.val);
		int cpu = (b >> _Q_TAIL_CPU_OFFSET) - 1;
		int queued = kd_spin_debug_waiter_count(&nested_lock_b.rlock);

		if (record && (b & _Q_TAIL_MASK) && queued == 0 &&
		    cpu == task_cpu(record->task)) {
			u32 a = atomic_read(&nested_lock_a.rlock.raw_lock.val);
			u32 a_private =
				kd_spin_debug_word(&nested_lock_a.rlock);
			bool valid = kd_test_spin_origin_locked(a) &&
				     (a_private & _Q_LOCKED_MASK) == 3 &&
				     kd_test_spin_origin_locked(b) &&
				     (b & _Q_PENDING_MASK) == _Q_PENDING_VAL &&
				     !(b & _Q_TAIL_IDX_MASK) &&
				     record->task != current &&
				     READ_ONCE(record->before) == 1 &&
				     !READ_ONCE(record->called) &&
				     !READ_ONCE(record->after);

			if (!valid || pending_spin_observed)
				atomic_inc(&resume_failures);
			smp_store_release(&pending_spin_observed, 1);
			pr_info("kd_pending spin blocked: task=%d cpu=%d holder_cpu=%d outer=%lx lock=%lx a_val=%x b_val=%x a_private=%x queued=%d valid=%u holder_comm=%s\n",
				record->task->pid, cpu, raw_smp_processor_id(),
				(unsigned long)&nested_lock_a,
				(unsigned long)&nested_lock_b, a, b, a_private,
				queued, valid, current->comm);
			return;
		}
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&resume_failures);
			pr_err("kd_pending spin: original waiter did not queue on B\n");
			return;
		}
		cpu_relax();
	}
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
	if (native_pending_contended) {
		wait_for_pending_spin_waiter();
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

#include "../tests/kernel/context_lock_workload.c"

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
	mutex_lock(&nested_mutex_b);
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

/* B's owner observes the original waiter in the real kernel wait_list,
 * rather than mistaking a pre-lock flag or the combiner for that waiter.
 * On timeout release B and fail the oracle instead of stranding the test. */
static noinline void wait_for_pending_mutex_waiter(void)
{
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		struct kd_resume_record *record =
			smp_load_acquire(&pending_mutex_record);
		struct mutex_waiter *waiter;
		unsigned long flags;
		bool found = false;

		raw_spin_lock_irqsave(&nested_mutex_b.wait_lock, flags);
		list_for_each_entry(waiter, &nested_mutex_b.wait_list, list) {
			if (record && waiter->task == record->task) {
				found = true;
				break;
			}
		}
		raw_spin_unlock_irqrestore(&nested_mutex_b.wait_lock, flags);
		if (found) {
			unsigned long a_owner =
				kd_test_mutex_owner(&nested_mutex_a);
			unsigned long b_owner =
				kd_test_mutex_owner(&nested_mutex_b);
			bool valid = a_owner &&
				     a_owner != (unsigned long)record->task &&
				     a_owner != (unsigned long)current &&
				     b_owner == (unsigned long)current &&
				     READ_ONCE(record->before) == 1 &&
				     !READ_ONCE(record->called) &&
				     !READ_ONCE(record->after);

			if (!valid || pending_mutex_observed)
				atomic_inc(&resume_failures);
			pending_mutex_observed++;
			pending_mutex_a_owner = a_owner;
			pr_info("kd_pending mutex blocked: task=%d waiter=%lx a_owner=%lx b_owner=%lx queued=1 valid=%u holder_comm=%s\n",
				record->task->pid, (unsigned long)record->task,
				a_owner, b_owner, valid, current->comm);
			kd_waiter_signal_send(record);
			return;
		}
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&resume_failures);
			pr_err("kd_pending mutex: original waiter did not queue on B\n");
			return;
		}
		cond_resched();
	}
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
	if (native_pending_contended) {
		wait_for_pending_mutex_waiter();
	} else {
		/* The ordinary nested JIT case waits for the A executor, not
		 * for the original waiter used by pending-CALL continuation. */
		while (!kd_mutex_debug_nested_waiters())
			cpu_relax();
	}
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
	if (READ_ONCE(mutex_ooo_dependency) == 1)
		kd_ooo_dependency_hold();
	atomic_set(&mutex_outer_trailing_waiting, 1);
	smp_mb__after_atomic();
	mutex_lock(&nested_mutex_a);
	if (READ_ONCE(mutex_ooo_dependency) == 1)
		kd_ooo_dependency_observe();
	kd_cs_step(KD_CS_MUTEX_A);
	for (j = 0; j < work_load; j++)
		dummy_computation++;
	mutex_unlock(&nested_mutex_a);
	if (READ_ONCE(mutex_ooo_dependency) == 1)
		mutex_unlock(&ooo_mutex_locks[6]);
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
		else if (sync_role == 7 && !gs_context)
			run_mutex_native_dependency_role();
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

#include "../tests/kernel/spin_routing_workload.c"
#include "../tests/kernel/mutex_signal_workload.c"

static long my_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct test_args k_args;

	switch (cmd) {
	case IOC_RUN_TEST:
		if (copy_from_user(&k_args, (void __user *)arg, sizeof(k_args)))
			return -EFAULT;
		if (mutex_signal_probe) {
			if (k_args.mode != MODE_MUTEX_CONTENTION)
				return -EINVAL;
			if (k_args.role & KD_SIGNAL_ROLE)
				return k_args.loop_count == 1 ?
					       kd_signal_run(k_args.role &
							     ~KD_SIGNAL_ROLE) :
					       -EINVAL;
		}
		if (spin_route_probe)
			return k_args.mode == MODE_SPIN_CONTENTION &&
					       k_args.loop_count == 1 ?
				       kd_route_run(k_args.role) :
				       -EINVAL;
		if (context_lock_probe && k_args.mode != MODE_MUTEX_CONTENTION)
			return -EINVAL;
		if (spin_chain_depth)
			return k_args.mode == MODE_SPIN_INNER_CONTENTION ?
				       kd_chain_run(k_args.loop_count,
						    k_args.role) :
				       -EINVAL;
		if (remote_chain_depth)
			return k_args.mode == MODE_SPIN_INNER_CONTENTION ?
				       kd_deep_run(k_args.loop_count,
						   k_args.role) :
				       -EINVAL;
		if (k_args.mode == MODE_SPIN_CONTENTION) {
			unsigned int api = k_args.role & 0x20000000U ?
						   k_args.role & 3U :
						   0;

			if (api)
				run_native_spin_contention_test(
					k_args.loop_count, k_args.work_load,
					api);
			else
				run_contention_test(k_args.loop_count,
						    k_args.work_load);
		} else if (k_args.mode == MODE_SPIN_NESTED)
			run_nested_spinlock_test(k_args.loop_count,
						 k_args.work_load, k_args.role);
		else if (k_args.mode == MODE_SPIN_API_IN_LOCK)
			run_api_in_lock_test(k_args.loop_count,
					     k_args.work_load);
		else if (k_args.mode == MODE_MUTEX_CONTENTION)
			return run_mutex_contention_test(k_args.loop_count,
							 k_args.work_load,
							 k_args.role);
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
				   unsigned long *completed,
				   unsigned int *active_states)
{
	unsigned int failures = 0;
	unsigned int id;

	*operations = 0;
	*completed = 0;
	*active_states = 0;
	for (id = 0; id < KD_CS_STATE_COUNT; id++) {
		struct kd_cs_state expected = {};
		struct kd_cs_state *state = &kd_cs_states[id];
		unsigned long count = READ_ONCE(state->sequence);
		unsigned long done = READ_ONCE(kd_cs_completed[id]);
		unsigned long i;

		*operations += count;
		*completed += done;
		if (count != done) {
			failures++;
			pr_err("kd_cs operation mismatch: state=%s operations=%lu completed=%lu\n",
			       kd_cs_state_names[id], count, done);
		}
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

	return failures;
}

static int __init my_module_init(void)
{
	int cpu;
	int ret;

	ret = kd_signal_init();
	if (ret)
		return ret;
	ret = kd_route_init();
	if (ret)
		return ret;
	if (native_resume_stage > 5)
		return -EINVAL;
	if (native_pending_contended && native_resume_stage != 4)
		return -EINVAL;
	if (native_waiter_signal &&
	    ((native_waiter_signal != SIGUSR1 && native_waiter_signal != SIGKILL) ||
	     !native_pending_contended || native_resume_stage != 4))
		return -EINVAL;
	if (native_resume_ooo || jit_mutex_ooo || mutex_ooo_dependency ||
	    spin_ooo_dependency)
		return -EINVAL;
	kd_ooo_init();
	if (context_lock_probe > 9 ||
	    (context_lock_probe && (mixed_lock_probe != 1 ||
				    native_resume_stage || spin_chain_depth)))
		return -EINVAL;
	ret = kd_chain_init();
	if (ret)
		return ret;
	ret = kd_deep_init();
	if (ret)
		return ret;
	for (cpu = 0; cpu < KD_RESUME_DEPTH_LOCKS; cpu++)
		mutex_init(&resume_depth_locks[cpu]);
	if (native_resume_stage) {
		resume_records = kvcalloc(KD_RESUME_RECORDS,
					  sizeof(*resume_records), GFP_KERNEL);
		if (!resume_records)
			return -ENOMEM;
	}
	ret = kd_register_init();
	if (ret) {
		kvfree(resume_records);
		return ret;
	}
	mode2_api_observations = 0;
	mode5_api_observations = 0;
	memset(kd_cs_states, 0, sizeof(kd_cs_states));
	memset(kd_cs_completed, 0, sizeof(kd_cs_completed));
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
		kvfree(register_samples);
		kvfree(resume_records);
		return ret;
	}
	pr_info("module loaded\n");
	return 0;
}

static void __exit my_module_exit(void)
{
	unsigned long cs_operations;
	unsigned long cs_completed;
	unsigned int cs_active_states;
	unsigned int cs_failures;
	int id, requests = atomic_read(&resume_requests);

	misc_deregister(&my_misc_device);
	kd_chain_report();
	kd_deep_report();
	kd_context_report();
	kd_route_report();
	kd_signal_report();
	kd_waiter_signal_report();
	kd_ooo_report();
	kd_remote_ooo_report();
	kd_spin_oracle_report();
	for (id = 0; id < min(requests, KD_RESUME_RECORDS); id++) {
		struct kd_resume_record *record = &resume_records[id];
		unsigned long expected = (((unsigned long)id + 1) * 3 + 17) ^
					 0x5a5a;

		if (record->before != 1 || record->called != 1 ||
		    record->after != 1 || record->value != expected)
			atomic_inc(&resume_failures);
	}
	pr_info("kd_resume records: requests=%d failures=%d\n", requests,
		atomic_read(&resume_failures));
	kd_register_report(requests);
	if (native_pending_contended)
		pr_info("kd_pending mutex: observed=%u acquired=%u\n",
			pending_mutex_observed, pending_mutex_acquired);
	if (native_pending_contended)
		pr_info("kd_pending spin: observed=%u acquired=%u\n",
			pending_spin_observed, pending_spin_acquired);
	if (native_resume_stage == 5)
		pr_info("kd_depth mutex stats: capacity=%d callee=%d native=%d\n",
			atomic_read(&depth_capacity_resumes),
			atomic_read(&depth_callee_resumes),
			atomic_read(&depth_native_runs));
	pr_info("kd_mutex oracle: inside=%d overlaps=%d\n",
		atomic_read(&mutex_inside), atomic_read(&mutex_overlaps));
	kvfree(resume_records);
	kvfree(register_samples);
	cs_failures = kd_cs_validate(&cs_operations, &cs_completed,
				     &cs_active_states);
	pr_info("module unloaded, final counter: %lu\n", cs_completed);
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
