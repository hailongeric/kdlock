// SPDX-License-Identifier: GPL-2.0
/* Two independent queues must retain different waiters/owners across their
 * JIT images' ordinary CALL misses. This is a workload, not a fabricated frame.
 * Stop the daemon before arming: concurrent code replacement is not tested. */
static bool mutex_parallel;
static bool mutex_parallel_armed;
static bool mutex_parallel_shared_cpu;
static bool mutex_parallel_pressure;
static bool mutex_parallel_pressure_release;
static bool mutex_parallel_source_hold;
static bool mutex_parallel_exit_hold;
static bool mutex_parallel_retired;
static bool mutex_parallel_peers;
static bool mutex_parallel_shadow;
static unsigned int mutex_parallel_first;
module_param(mutex_parallel, bool, 0444);
module_param(mutex_parallel_armed, bool, 0644);
module_param(mutex_parallel_shared_cpu, bool, 0444);
module_param(mutex_parallel_pressure, bool, 0444);
module_param(mutex_parallel_pressure_release, bool, 0644);
module_param(mutex_parallel_source_hold, bool, 0644);
module_param(mutex_parallel_exit_hold, bool, 0644);
module_param(mutex_parallel_retired, bool, 0444);
module_param(mutex_parallel_peers, bool, 0444);
module_param(mutex_parallel_shadow, bool, 0444);
module_param(mutex_parallel_first, uint, 0444);
MODULE_PARM_DESC(mutex_parallel, "Mode 3: two independent nested mutex queues");
MODULE_PARM_DESC(mutex_parallel_armed,
		 "Arm after serial promotion/publication");
MODULE_PARM_DESC(mutex_parallel_first,
		 "First native waiter to drain: lane 0/1");
MODULE_PARM_DESC(mutex_parallel_shared_cpu,
		 "Reject lane 1 JIT while lane 0 owns their shared CPU frame");
MODULE_PARM_DESC(mutex_parallel_pressure,
		 "Combine four real CPU 1 nodes with node/task refusal waiters");
MODULE_PARM_DESC(mutex_parallel_pressure_release,
		 "Release lane 1 holder after observing both resource refusals");
MODULE_PARM_DESC(mutex_parallel_source_hold,
		 "Pause both real native frames for busy source retirement");
MODULE_PARM_DESC(mutex_parallel_exit_hold,
		 "Keep the second native frame until the first waiter exits");
MODULE_PARM_DESC(
	mutex_parallel_peers,
	"Queue native B peers across the two retained JIT/native frames");
MODULE_PARM_DESC(
	mutex_parallel_shadow,
	"Fill real mutex shadows while two old native frames stay live");
MODULE_PARM_DESC(
	mutex_parallel_retired,
	"Reloaded source: observe native contention with JIT admission retired");

enum {
	KD_PAR_HOLDER,
	KD_PAR_OWNER,
	KD_PAR_WAITER,
	KD_PAR_TRAILER,
	KD_PAR_WARM,
	KD_PAR_PRESSURE,
	KD_PAR_TASK_REFUSAL
};
struct kd_parallel_record {
	struct task_struct *task;
	unsigned long value, owner;
	unsigned int before, held, called, after, lane, role;
	pid_t pid;
};
static struct kd_parallel_lane {
	struct mutex a, b, native;
	struct kd_parallel_record records[KD_PAR_TASK_REFUSAL + 1];
	unsigned long sequence, digest;
	unsigned int native_acquired, native_released;
	atomic_t ready, claimed, warming;
} parallel_lanes[2];
static atomic_t parallel_arrived = ATOMIC_INIT(0);
static atomic_t parallel_done = ATOMIC_INIT(0);
static atomic_t parallel_pressure_done = ATOMIC_INIT(0);
static atomic_t parallel_peer_done = ATOMIC_INIT(0);
static atomic_t parallel_failures = ATOMIC_INIT(0);

#include "mutex_parallel/native.inc"

static int kd_parallel_run(unsigned long loops, unsigned int selector)
{
	unsigned int index = selector / 8, role = selector % 8;
	struct kd_parallel_record *record;
	struct kd_parallel_lane *lane;
	unsigned long i;
	bool valid;

	if (selector >= 25 && selector <= 28)
		return kd_shadow_capacity_run(loops, selector - 25);
	if (selector >= 22 && selector <= 24)
		return kd_parallel_peer_run(loops, selector - 22);
	if (selector >= 16)
		return kd_pool_run(loops, selector - 16);
	if (index >= ARRAY_SIZE(parallel_lanes) || role > KD_PAR_TASK_REFUSAL ||
	    (role >= KD_PAR_PRESSURE && (!mutex_parallel_pressure || !index)) ||
	    !loops || loops > 20000 ||
	    (role == KD_PAR_WARM) == READ_ONCE(mutex_parallel_armed) ||
	    (role != KD_PAR_WARM && loops != 1))
		return -EINVAL;
	lane = &parallel_lanes[index];
	if (role == KD_PAR_WARM) {
		if (atomic_cmpxchg(&lane->warming, 0, 1))
			return -EBUSY;
	} else if (atomic_fetch_or(BIT(role), &lane->claimed) & BIT(role)) {
		return -EALREADY;
	}
	if (role == KD_PAR_HOLDER) {
		mutex_lock(&lane->a);
		atomic_set_release(&lane->ready, 1);
		kd_parallel_wait(lane, NULL, 3);
		/* Lane 1 must not acquire A until lane 0 really reached native
		 * continuation. Lane 0 in turn waits for lane 1's final unlock,
		 * keeping the foreign CPU frame live throughout the refusal. */
		if (mutex_parallel_shared_cpu && index)
			kd_parallel_wait(lane, &parallel_arrived, 1);
		if (mutex_parallel_pressure && index) {
			unsigned long deadline = jiffies + 10 * HZ;

			/* The controller observes actual node exhaustion, then arms
			 * the existing one-shot task allocation failure for another
			 * caller. Only after both refusals may native A1 open. No
			 * production frame, capacity, node or context is fabricated. */
			while (!READ_ONCE(mutex_parallel_pressure_release)) {
				if (time_after_eq(jiffies, deadline)) {
					kd_parallel_check(false, index,
							  "release-timeout");
					break;
				}
				usleep_range(100, 200);
			}
		}
		mutex_unlock(&lane->a);
		return 0;
	}
	if (role != KD_PAR_WARM) {
		kd_parallel_wait(lane, &lane->ready, 1);
		if (role != KD_PAR_OWNER)
			kd_parallel_wait(lane, NULL,
					 role >= KD_PAR_PRESSURE ? 3 :
								   role - 1);
		if (role >= KD_PAR_PRESSURE)
			kd_parallel_wait(lane, &parallel_arrived, 1);
	}
	record = &lane->records[role];
	for (i = 0; i < loops; i++) {
		/* Capture identity before entry, and never dereference a saved task
		 * after it exits. The fixture adds no task/frame lifetime reference. */
		*record = (struct kd_parallel_record){
			.task = current,
			.pid = current->pid,
			.lane = index,
			.role = role,
			.value = index * 8UL + role + 1,
		};
		if (index)
			kd_parallel_cs1(record);
		else
			kd_parallel_cs0(record);
		valid = record->before == 1 && record->held == 1 &&
			record->called == 1 && record->after == 1 &&
			record->value ==
				(((index * 8UL + role + 1) * 3 + 17) ^ 0x5a5a);
		kd_parallel_check(valid, index, "post-unlock-record");
	}
	if (role == KD_PAR_WAITER) {
		if (native_resume_rename)
			valid &= kd_parallel_check(!strcmp(current->comm,
							   "kd_renamed"),
						   index, "renamed-owner-acks");
		pr_info("kd_parallel done: lane=%u task=%d waiter=%lx owner=%lx record=%lx before=%u held=%u called=%u after=%u value=%lx comm=%s valid=%u\n",
			index, current->pid, (unsigned long)current,
			record->owner, (unsigned long)record, record->before,
			record->held, record->called, record->after,
			record->value, current->comm, valid);
		/* Do not restore target eligibility before the borrowed B/A ACKs;
		 * that would let comm matching hide broken active-task routing. */
		if (native_resume_rename)
			kd_test_rename("klock_test");
		/* Publish only after both real owner ACKs and the final record log. */
		atomic_fetch_or(BIT(index), &parallel_done);
	}
	if (role >= KD_PAR_PRESSURE) {
		pr_info("kd_parallel pressure done: role=%u task=%d waiter=%lx owner=%lx outer=%lx inner=%lx record=%lx before=%u held=%u called=%u after=%u value=%lx cpu=%u valid=%u\n",
			role, current->pid, (unsigned long)current,
			record->owner, (unsigned long)&lane->a,
			(unsigned long)&lane->b, (unsigned long)record,
			record->before, record->held, record->called,
			record->after, record->value, raw_smp_processor_id(),
			valid);
		/* Full-order RMW publishes each post-unlock record independently.
		 * These are own-owner unlocks, never synthetic native ACKs. */
		atomic_fetch_or(BIT(role - KD_PAR_PRESSURE),
				&parallel_pressure_done);
	}
	if (role == KD_PAR_WARM)
		atomic_set(&lane->warming, 0);
	return atomic_read(&parallel_failures) ? -EINVAL : 0;
}

static int kd_parallel_init(void)
{
	unsigned int i;

	if (mutex_parallel_armed || mutex_parallel_pressure_release ||
	    mutex_parallel_source_hold || mutex_parallel_exit_hold ||
	    mutex_parallel_first > 1 ||
	    (!mutex_parallel &&
	     (mutex_parallel_first || mutex_parallel_shared_cpu ||
	      mutex_parallel_pressure)) ||
	    (mutex_parallel_shared_cpu && mutex_parallel_first != 1) ||
	    (mutex_parallel_pressure && !mutex_parallel_shared_cpu))
		return -EINVAL;
	if (mutex_parallel_retired &&
	    (!mutex_parallel || mutex_parallel_shared_cpu))
		return -EINVAL;
	if (mutex_parallel_peers &&
	    (!mutex_parallel || mutex_parallel_shared_cpu ||
	     mutex_parallel_retired))
		return -EINVAL;
	if (mutex_parallel_shadow &&
	    (!mutex_parallel || mutex_parallel_shared_cpu ||
	     mutex_parallel_retired))
		return -EINVAL;
	if (!mutex_parallel)
		return 0;
	if (native_resume_rename && !mutex_parallel_peers)
		return -EINVAL;
	if (native_resume_stage || mixed_lock_probe || mutex_signal_probe ||
	    spin_route_probe || spin_chain_depth || remote_chain_depth)
		return -EINVAL;
	for (i = 0; i < ARRAY_SIZE(parallel_lanes); i++) {
		mutex_init(&parallel_lanes[i].a);
		mutex_init(&parallel_lanes[i].b);
		mutex_init(&parallel_lanes[i].native);
	}
	kd_shadow_capacity_init();
	return 0;
}

static void kd_parallel_report(void)
{
	unsigned int i;

	if (!mutex_parallel)
		return;
	kd_pool_report();
	kd_parallel_peer_report();
	for (i = 0; i < ARRAY_SIZE(parallel_lanes); i++)
		pr_info("kd_parallel lane: lane=%u sequence=%lu digest=%lx claimed=%u a=%lx b=%lx\n",
			i, parallel_lanes[i].sequence, parallel_lanes[i].digest,
			atomic_read(&parallel_lanes[i].claimed),
			kd_test_mutex_owner(&parallel_lanes[i].a),
			kd_test_mutex_owner(&parallel_lanes[i].b));
	pr_info("kd_parallel stats: first=%u shared_cpu=%u pressure=%u pressure_done=%u arrived=%u done=%u failures=%u\n",
		mutex_parallel_first, mutex_parallel_shared_cpu,
		mutex_parallel_pressure, atomic_read(&parallel_pressure_done),
		atomic_read(&parallel_arrived), atomic_read(&parallel_done),
		atomic_read(&parallel_failures));
	if (mutex_parallel_retired) {
		unsigned int role;

		/* Only captured scalar identities are printed after callers exit;
		 * never dereference their retired task pointers for this oracle. */
		for (i = 0; i < ARRAY_SIZE(parallel_lanes); i++)
			for (role = KD_PAR_OWNER; role <= KD_PAR_TRAILER;
			     role++) {
				struct kd_parallel_record *r =
					&parallel_lanes[i].records[role];

				pr_info("kd_parallel retired record: lane=%u role=%u task=%d waiter=%lx owner=%lx before=%u held=%u called=%u after=%u value=%lx\n",
					i, role, r->pid, (unsigned long)r->task,
					r->owner, r->before, r->held, r->called,
					r->after, r->value);
			}
	}
}
