/*
 * Shared original locks and per-request native-resume oracle/probe state.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

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
static unsigned long mode5_api_calls;
/* Each counter pair belongs to the same physical lock as its mode's CS. */
static unsigned long mode2_scalar_calls, mode2_scalar_failures;
static unsigned long mode5_scalar_calls, mode5_scalar_failures;
/* Switch only between joined workload phases: keep normal hostcall-return
 * coverage, then exceed the per-invocation quota without changing its value. */
static bool mode5_call_quota;
module_param(mode5_call_quota, bool, 0644);
MODULE_PARM_DESC(mode5_call_quota,
		 "Mode 5: use 17 clock calls per critical section (normal: 1)");

/* Each request has a distinct record: entry replay cannot hide behind an
 * aggregate counter. The ordinary noinline call deliberately starts missing. */
#define KD_RESUME_RECORDS 65536
static unsigned int native_resume_stage;
module_param(native_resume_stage, uint, 0444);
static bool native_resume_rename;
static bool native_pending_contended;
static bool mutex_nested_schedule;
module_param(mutex_nested_schedule, bool, 0444);
MODULE_PARM_DESC(mutex_nested_schedule,
		 "Mode 4: observe the A executor blocked on B on its holder's CPU");
static bool native_acquired_queue;
module_param(native_acquired_queue, bool, 0444);
MODULE_PARM_DESC(
	native_acquired_queue,
	"Stage 3: acquire virtual B from a real private queue before native continuation");
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
/* Arm only after promotion so task_lock traffic and rename observations stay
 * outside the mutex's frequency sample; unrelated locks no longer tune it. */
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

#include "../fragments/native_register_workload.c"

static void kd_signal_hold(struct kd_resume_record *record);
static bool mutex_signal_race;
static noinline void kd_signal_owner_unlock(bool done);

/* Match the non-RT mutex owner encoding used by the production hook. */
static unsigned long kd_test_mutex_owner(struct mutex *lock)
{
	return atomic_long_read(&lock->owner) & ~0x7UL;
}

#include "../fragments/native_waiter_signal_workload.c"
#include "../fragments/mutex_stack_workload.c"

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
		pr_info("kd_pending mutex acquired: task=%d waiter=%lx a_owner=%lx b_owner=%lx preserved=%u cpu=%u preempt=%u irq=%u\n",
			current->pid, (unsigned long)current, a_owner, b_owner,
			preserved, raw_smp_processor_id(), preempt_count(),
			irqs_disabled());
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
