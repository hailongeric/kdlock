// SPDX-License-Identifier: GPL-2.0
/* Mode 8: two independent logical roots share one real B queue. The workload
 * never constructs frames/nodes or transfers ownership. Prepare/observe on
 * original stacks; translated bodies contain only protected data operations. */
static bool spin_multi_roots;
static bool spin_multi_quota;
module_param(spin_multi_roots, bool, 0444);
module_param(spin_multi_quota, bool, 0444);
MODULE_PARM_DESC(spin_multi_roots,
		 "Mode 8: two A queues feed one B combiner, arm with role high bit");
MODULE_PARM_DESC(spin_multi_quota,
		 "Multi-root variant: first B child uses the existing CALL quota exit");

#define KD_MULTI_ROLE_SYNC 0x80000000U
#define KD_MULTI_ROLES 14
static spinlock_t multi_locks[3];
static bool multi_holder[3], multi_abort;
static atomic_t multi_direct[3];
static atomic_t multi_started = ATOMIC_INIT(0);
static atomic_t multi_finished = ATOMIC_INIT(0);
static atomic_t multi_failures = ATOMIC_INIT(0);
static struct task_struct *multi_tasks[KD_MULTI_ROLES];
static unsigned long multi_clock_calls;
static unsigned int multi_quota_observed;
static struct {
	unsigned long before, after, value, shared_sequence;
} multi_records[2];

static __always_inline enum kd_cs_state_id kd_multi_state(unsigned int index)
{
	return index == 0 ? KD_CS_SPIN_A :
	       index == 1 ? KD_CS_SPIN_C : KD_CS_SPIN_B;
}

/* Timeouts open only workload gates. Published lock queues must still drain;
 * never report a native fallback or timeout as successful remote execution. */
static bool kd_multi_wait(unsigned int index, unsigned int queued)
{
	unsigned long deadline = jiffies + 15 * HZ;

	while (!READ_ONCE(multi_abort)) {
		if (smp_load_acquire(&multi_holder[index]) &&
		    (!queued ||
		     (atomic_read(&multi_direct[index]) >= 2 &&
		      kd_spin_debug_waiter_count(&multi_locks[index].rlock) >=
			      (int)queued)))
			return true;
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&multi_failures);
			pr_err("kd_multi timeout: index=%u queued=%u cpu=%u\n",
			       index, queued, raw_smp_processor_id());
			WRITE_ONCE(multi_abort, true);
			break;
		}
		cpu_relax();
	}
	return false;
}

static noinline bool kd_multi_root_prepare(unsigned int lane, bool armed)
{
	return !armed || (kd_multi_wait(2, 1) && kd_multi_wait(lane, 1));
}

/* This ordinary callee is reached only after the 17th service has returned on
 * the original waiter. Keep current/owner probes out of the translated body.
 * During this bounded interval B must retain ownership and pause the second
 * root; do not acquire a test lock or add task references to enforce that.
 * Two borrowed frames share one root origin pin on this waiter, not two
 * lexical lock-acquisition pins; only the final owner ACK consumes that pin. */
static __attribute__((noipa)) noinline void kd_multi_quota_observe(void)
{
	unsigned long deadline = jiffies + max(1, HZ / 100);
	unsigned int phase;

	for (phase = 0; phase < 2; phase++) {
		unsigned long a0 = kd_spin_debug_owner(&multi_locks[0].rlock);
		unsigned long a1 = kd_spin_debug_owner(&multi_locks[1].rlock);
		unsigned long b = kd_spin_debug_owner(&multi_locks[2].rlock);
		bool valid = current == READ_ONCE(multi_tasks[0]) &&
			a0 && a1 && b && a0 != a1 && a0 != b && a1 != b &&
			a0 != (unsigned long)current && b != (unsigned long)current &&
			preempt_count() == 1 && !irqs_disabled() &&
			READ_ONCE(multi_records[1].before) == 2 &&
			READ_ONCE(multi_records[1].after) == 1 &&
			READ_ONCE(multi_records[1].shared_sequence) == 12003 &&
			READ_ONCE(kd_cs_states[KD_CS_SPIN_B].sequence) == 12006 &&
			READ_ONCE(multi_clock_calls) == 34;

		if (!valid)
			atomic_inc(&multi_failures);
		pr_info("kd_multi quota: phase=%u task=%d self=%lx cpu=%u a0=%lx a1=%lx b=%lx other_before=%lu other_after=%lu other_shared=%lu sequence=%lu calls=%lu preempt=%u irq=%u valid=%u\n",
			phase, current->pid, (unsigned long)current,
			raw_smp_processor_id(), a0, a1, b,
			READ_ONCE(multi_records[1].before),
			READ_ONCE(multi_records[1].after),
			READ_ONCE(multi_records[1].shared_sequence),
			READ_ONCE(kd_cs_states[KD_CS_SPIN_B].sequence),
			READ_ONCE(multi_clock_calls), preempt_count(),
			irqs_disabled(), valid);
		while (!phase && time_before(jiffies, deadline))
			cpu_relax();
	}
	multi_quota_observed++;
}

static noinline void kd_multi_root(unsigned int lane, bool armed)
{
	spinlock_t *outer = &multi_locks[lane];
	unsigned long token = 0x12340001UL + lane * 0x101UL;
	unsigned int call;

	if (!kd_multi_root_prepare(lane, armed))
		return;
	spin_lock(outer);
	kd_cs_step(kd_multi_state(lane));
	multi_records[lane].before++;
	multi_records[lane].value += token;
	spin_lock(&multi_locks[2]);
	kd_cs_step(KD_CS_SPIN_B);
	multi_records[lane].shared_sequence = kd_cs_states[KD_CS_SPIN_B].sequence;
	/* The quota exit retains NORMAL publication. A CALL miss would instead
	 * request learning and prevent the second child using this shared image. */
	if (READ_ONCE(spin_multi_quota) && !lane) {
		for (call = 0; call < 17; call++)
			if (ktime_get_ns())
				multi_clock_calls++;
		if (armed)
			kd_multi_quota_observe();
	}
	spin_unlock(&multi_locks[2]);
	multi_records[lane].value ^= token << 1;
	multi_records[lane].after++;
	spin_unlock(outer);
}

static noinline bool kd_multi_direct_prepare(unsigned int index, bool armed,
					    bool trailing)
{
	/* The two A followers queue after their logical root; B's follower waits
	 * for both virtual requests. Pending-bit holders are not MCS waiters. */
	if (!armed)
		return true;
	if (trailing)
		return kd_multi_wait(index, index == 2 ? 3 : 2);
	if (!kd_multi_wait(index, 0))
		return false;
	atomic_inc(&multi_direct[index]);
	return true;
}

static noinline void kd_multi_direct(unsigned int index, bool armed,
				    bool trailing)
{
	spinlock_t *lock = &multi_locks[index];

	if (!kd_multi_direct_prepare(index, armed, trailing))
		return;
	spin_lock(lock);
	kd_cs_step(kd_multi_state(index));
	spin_unlock(lock);
}

static noinline void kd_multi_holder(unsigned int index)
{
	spinlock_t *lock = &multi_locks[index];

	spin_lock(lock);
	smp_store_release(&multi_holder[index], true);
	if (kd_multi_wait(index, index == 2 ? 4 : 3) && index == 2) {
		/* Both original callers are blocked in their root requests here,
		 * so their task objects remain live without extra test references. */
		struct task_struct *first = READ_ONCE(multi_tasks[0]);
		struct task_struct *second = READ_ONCE(multi_tasks[5]);
		unsigned long a0 = kd_spin_debug_owner(&multi_locks[0].rlock);
		unsigned long a1 = kd_spin_debug_owner(&multi_locks[1].rlock);
		bool valid = first && second && first != second && a0 && a1 &&
			     a0 != a1 && a0 != (unsigned long)first &&
			     a1 != (unsigned long)second &&
			     READ_ONCE(multi_records[0].before) == 2 &&
			     READ_ONCE(multi_records[1].before) == 2 &&
			     READ_ONCE(multi_records[0].after) == 1 &&
			     READ_ONCE(multi_records[1].after) == 1;

		if (!valid)
			atomic_inc(&multi_failures);
		pr_info("kd_multi queued: a0=%lx a1=%lx b=%lx first=%d second=%d owner0=%lx owner1=%lx b_owner=%lx count=%d valid=%u\n",
			(unsigned long)&multi_locks[0],
			(unsigned long)&multi_locks[1], (unsigned long)lock,
			first ? first->pid : 0, second ? second->pid : 0,
			a0, a1, kd_spin_debug_owner(&lock->rlock),
			kd_spin_debug_waiter_count(&lock->rlock), valid);
	}
	/* Force the quota root ahead of the JIT-only root at B using real queue
	 * admission, not an artificial child/frame or a change of physical owner. */
	if (index == 1 && READ_ONCE(spin_multi_quota))
		kd_multi_wait(2, 2);
	kd_cs_step(kd_multi_state(index));
	spin_unlock(lock);
}

static int kd_multi_run(unsigned long loops, unsigned int input)
{
	unsigned int role = input & ~KD_MULTI_ROLE_SYNC;
	bool armed = input & KD_MULTI_ROLE_SYNC;
	unsigned int index, local, before = preempt_count();
	unsigned long i;
	bool irq = irqs_disabled();

	if (role >= KD_MULTI_ROLES || !loops || (armed && loops != 1) ||
	    (armed && (before || irq)))
		return -EINVAL;
	index = role < 5 ? 0 : role < 10 ? 1 : 2;
	local = index == 2 ? role - 9 : role - 5 * index;
	if (!armed && local != 0 && local != 2 && local != 3)
		return -EINVAL;
	if (armed) {
		if (atomic_fetch_or(BIT(role), &multi_started) & BIT(role))
			return -EALREADY;
		WRITE_ONCE(multi_tasks[role], current);
		pr_info("kd_multi start: role=%u task=%d self=%lx cpu=%u preempt=%u irq=%u\n",
			role, current->pid, (unsigned long)current,
			raw_smp_processor_id(), before, irq);
	}
	for (i = 0; i < loops; i++) {
		if (!local)
			kd_multi_root(index, armed);
		else if (local == 1)
			kd_multi_holder(index);
		else
			kd_multi_direct(index, armed, local == 4);
	}
	if (armed) {
		if (preempt_count() != before || irqs_disabled() != irq)
			atomic_inc(&multi_failures);
		pr_info("kd_multi done: role=%u task=%d self=%lx cpu=%u preempt=%u irq=%u\n",
			role, current->pid, (unsigned long)current,
			raw_smp_processor_id(), preempt_count(), irqs_disabled());
		atomic_or(BIT(role), &multi_finished);
	}
	return READ_ONCE(multi_abort) ? -ETIMEDOUT : 0;
}

static void kd_multi_init(void)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(multi_locks); i++) {
		spin_lock_init(&multi_locks[i]);
		atomic_set(&multi_direct[i], 0);
	}
}

static void kd_multi_report(void)
{
	unsigned int lane;

	if (!spin_multi_roots)
		return;
	if (multi_clock_calls != (spin_multi_quota ? 34 : 0) ||
	    multi_quota_observed != (spin_multi_quota ? 1 : 0))
		atomic_inc(&multi_failures);
	for (lane = 0; lane < 2; lane++) {
		unsigned long token = 0x12340001UL + lane * 0x101UL;
		unsigned long expected = 0;
		unsigned int i;

		for (i = 0; i < 2; i++)
			expected = (expected + token) ^ (token << 1);
		if (multi_records[lane].before != 2 ||
		    multi_records[lane].after != 2 ||
		    multi_records[lane].value != expected)
			atomic_inc(&multi_failures);
		pr_info("kd_multi record: lane=%u before=%lu after=%lu value=%lx expected=%lx shared=%lu\n",
			lane, multi_records[lane].before, multi_records[lane].after,
			multi_records[lane].value, expected,
			multi_records[lane].shared_sequence);
	}
	pr_info("kd_multi stats: started=%x finished=%x failures=%d aborted=%u\n",
		atomic_read(&multi_started), atomic_read(&multi_finished),
		atomic_read(&multi_failures), multi_abort);
	pr_info("kd_multi services: quota=%u calls=%lu observed=%u\n",
		spin_multi_quota, multi_clock_calls, multi_quota_observed);
}
