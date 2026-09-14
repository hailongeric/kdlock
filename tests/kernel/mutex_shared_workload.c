// SPDX-License-Identifier: GPL-2.0
/* Mode 4's second session: one borrowed native suffix retains B while another
 * A combiner and a non-target task sleep on that same Linux mutex. No test
 * frame, owner handoff or task reference is used to arrange their progress. */
static bool mutex_shared;
static bool mutex_shared_armed;
module_param(mutex_shared, bool, 0444);
module_param(mutex_shared_armed, bool, 0644);
MODULE_PARM_DESC(mutex_shared,
		 "Mode 4: two A queues and a native peer share B");
MODULE_PARM_DESC(mutex_shared_armed,
		 "Arm shared-B contention after both JIT entries are published");

static struct {
	struct mutex lock;
	bool ready;
	unsigned long visits, before, held, after, value, sequence;
} shared_a[2];
static DEFINE_MUTEX(shared_b);
static unsigned long shared_tasks[11];
static atomic_t shared_claimed = ATOMIC_INIT(0);
static atomic_t shared_failures = ATOMIC_INIT(0);
static bool shared_native_ready;
static unsigned int shared_observed;
static unsigned long shared_peer_sequence;

static bool kd_shared_check(bool valid, const char *phase)
{
	if (!valid) {
		atomic_inc(&shared_failures);
		pr_err("kd_shared error: phase=%s task=%d\n", phase,
		       current->pid);
	}
	return valid;
}

/* Only fixture-owned gates are bounded here. A failed observation still lets
 * each real owner release its own mutex; it never cancels a kdlock request. */
static bool kd_shared_wait(unsigned int lane, unsigned int queued,
			   bool native)
{
	unsigned long deadline = jiffies + 15 * HZ;

	for (;;) {
		if (native ? smp_load_acquire(&shared_native_ready) :
			     (smp_load_acquire(&shared_a[lane].ready) &&
			      kd_mutex_debug_waiter_count(&shared_a[lane].lock) >=
				      (int)queued))
			return true;
		if (time_after_eq(jiffies, deadline))
			return kd_shared_check(false, "gate-timeout");
		usleep_range(100, 200);
	}
}

/* Deliberately unlearned ordinary CALL: current/IRQ/wait-list observations run
 * on the original waiter, never in its translated prefix. The second A owner
 * is released only after this point; both its real B wait and the native peer
 * must be visible before the borrowed waiter can request B's owner-side ACK. */
static __attribute__((noipa)) noinline void kd_shared_native(void)
{
	unsigned long deadline = jiffies + 15 * HZ;
	unsigned int phase;

	if (!READ_ONCE(mutex_shared_armed))
		return;
	smp_store_release(&shared_native_ready, true);
	for (phase = 0; phase < 2; phase++) {
		struct mutex_waiter *waiter;
		unsigned long flags, a0, a1, b;
		pid_t executor = 0, peer = 0;
		unsigned int queued = 0;
		bool valid;

		/* Read task identity only while Linux protects the wait-list node.
		 * Stored role addresses are comparison tokens, not pinned tasks. */
		for (;;) {
			queued = 0;
			executor = peer = 0;
			raw_spin_lock_irqsave(&shared_b.wait_lock, flags);
			list_for_each_entry(waiter, &shared_b.wait_list, list) {
				unsigned long task = (unsigned long)waiter->task;

				queued++;
				if (task == READ_ONCE(shared_tasks[5]))
					executor = waiter->task->pid;
				if (task == READ_ONCE(shared_tasks[10]))
					peer = waiter->task->pid;
			}
			raw_spin_unlock_irqrestore(&shared_b.wait_lock, flags);
			if (executor && peer)
				break;
			if (time_after_eq(jiffies, deadline)) {
				kd_shared_check(false, "native-wait-list-timeout");
				return;
			}
			usleep_range(100, 200);
		}
		a0 = kd_test_mutex_owner(&shared_a[0].lock);
		a1 = kd_test_mutex_owner(&shared_a[1].lock);
		b = kd_test_mutex_owner(&shared_b);
		valid = (unsigned long)current == READ_ONCE(shared_tasks[2]) &&
			a0 == READ_ONCE(shared_tasks[1]) &&
			a1 == READ_ONCE(shared_tasks[5]) && a0 && a1 &&
			a0 != a1 && b == a0 && queued == 2 &&
			!preempt_count() && !irqs_disabled() &&
			READ_ONCE(shared_a[1].before) == 12002 &&
			READ_ONCE(shared_a[1].held) == 12001 &&
			READ_ONCE(shared_a[1].after) == 12001 &&
			READ_ONCE(kd_cs_states[KD_CS_MUTEX_B].sequence) == 24003;
		kd_shared_check(valid, "retained-owner");
		pr_info("kd_shared retained: phase=%u task=%d self=%lx cpu=%u a0=%lx a1=%lx b=%lx outer0=%lx outer1=%lx inner=%lx executor=%d peer=%d queued=%u before=%lu held=%lu after=%lu sequence=%lu preempt=%u irq=%u valid=%u\n",
			phase, current->pid, (unsigned long)current,
			raw_smp_processor_id(), a0, a1, b,
			(unsigned long)&shared_a[0].lock,
			(unsigned long)&shared_a[1].lock,
			(unsigned long)&shared_b, executor, peer, queued,
			READ_ONCE(shared_a[1].before),
			READ_ONCE(shared_a[1].held),
			READ_ONCE(shared_a[1].after),
			READ_ONCE(kd_cs_states[KD_CS_MUTEX_B].sequence),
			preempt_count(), irqs_disabled(), valid);
		if (!phase)
			usleep_range(10000, 12000);
	}
	shared_observed++;
}

/* Distinct constant-lane wrappers create two real entry registrations. Keep
 * the complex B transition in both images; only lane 0 leaves at a CALL miss.
 * Its committed prefix must not be replayed when the waiter finishes natively. */
static __always_inline void kd_shared_body(unsigned int lane)
{
	unsigned long token = 0x12340001UL + lane * 0x101UL;

	mutex_lock(&shared_a[lane].lock);
	shared_a[lane].visits++;
	shared_a[lane].before++;
	shared_a[lane].value += token;
	mutex_lock(&shared_b);
	kd_cs_step(KD_CS_MUTEX_B);
	shared_a[lane].held++;
	shared_a[lane].sequence = kd_cs_states[KD_CS_MUTEX_B].sequence;
	if (!lane)
		kd_shared_native();
	shared_a[lane].value ^= token << 1;
	shared_a[lane].after++;
	mutex_unlock(&shared_b);
	mutex_unlock(&shared_a[lane].lock);
}

static __attribute__((noipa)) noinline void kd_shared_cs0(void)
{
	kd_shared_body(0);
}

static __attribute__((noipa)) noinline void kd_shared_cs1(void)
{
	kd_shared_body(1);
}

/* Every caller has one role. Holders arrange private A queues; the peer is
 * non-target before taking B and remains so through its native unlock. */
static int kd_shared_run(unsigned long loops, unsigned int selector)
{
	unsigned int lane = selector / 4, role = selector % 4;
	bool armed = READ_ONCE(mutex_shared_armed);
	unsigned long i;

	if ((!armed && (selector < 8 || selector > 9)) ||
	    (armed && (loops != 1 || (selector >= 8 && selector != 10))))
		return -EINVAL;
	if (!armed) {
		lane = selector - 8;
		for (i = 0; i < loops; i++) {
			if (lane)
				kd_shared_cs1();
			else
				kd_shared_cs0();
		}
		return 0;
	}
	if (atomic_fetch_or(BIT(selector), &shared_claimed) & BIT(selector))
		return -EBUSY;
	if (selector == 10)
		kd_test_rename("kd_native");
	WRITE_ONCE(shared_tasks[selector], (unsigned long)current);
	pr_info("kd_shared role: role=%u task=%d self=%lx cpu=%u preempt=%u irq=%u comm=%s\n",
		selector, current->pid, (unsigned long)current,
		raw_smp_processor_id(), preempt_count(), irqs_disabled(),
		current->comm);
	if (selector == 10) {
		if (!kd_shared_wait(0, 0, true))
			goto done;
		mutex_lock(&shared_b);
		kd_cs_step(KD_CS_MUTEX_B);
		shared_peer_sequence = kd_cs_states[KD_CS_MUTEX_B].sequence;
		pr_info("kd_shared peer: task=%d self=%lx owner=%lx lock=%lx sequence=%lu comm=%s\n",
			current->pid, (unsigned long)current,
			kd_test_mutex_owner(&shared_b), (unsigned long)&shared_b,
			shared_peer_sequence, current->comm);
		mutex_unlock(&shared_b);
	} else if (!role) {
		mutex_lock(&shared_a[lane].lock);
		shared_a[lane].visits++;
		smp_store_release(&shared_a[lane].ready, true);
		kd_shared_wait(lane, 3, false);
		if (lane)
			kd_shared_wait(lane, 0, true);
		mutex_unlock(&shared_a[lane].lock);
	} else {
		if (!kd_shared_wait(lane, role - 1, false))
			goto done;
		if (role == 2) {
			if (lane)
				kd_shared_cs1();
			else
				kd_shared_cs0();
		} else {
			mutex_lock(&shared_a[lane].lock);
			shared_a[lane].visits++;
			mutex_unlock(&shared_a[lane].lock);
		}
	}
done:
	kd_shared_check(!preempt_count() && !irqs_disabled(), "final-context");
	pr_info("kd_shared done: role=%u task=%d self=%lx cpu=%u preempt=%u irq=%u comm=%s\n",
		selector, current->pid, (unsigned long)current,
		raw_smp_processor_id(), preempt_count(), irqs_disabled(),
		current->comm);
	return atomic_read(&shared_failures) ? -EINVAL : 0;
}

static void kd_shared_init(void)
{
	unsigned int lane;

	for (lane = 0; lane < ARRAY_SIZE(shared_a); lane++)
		mutex_init(&shared_a[lane].lock);
}

/* Read only after all nine callers and their owner acknowledgements drain.
 * The userspace oracle independently recomputes both complete root records. */
static void kd_shared_report(void)
{
	unsigned int lane;

	if (!mutex_shared)
		return;
	for (lane = 0; lane < ARRAY_SIZE(shared_a); lane++)
		pr_info("kd_shared record: lane=%u lock=%lx owner=%lx visits=%lu before=%lu held=%lu after=%lu value=%lx sequence=%lu\n",
			lane, (unsigned long)&shared_a[lane].lock,
			kd_test_mutex_owner(&shared_a[lane].lock),
			shared_a[lane].visits, shared_a[lane].before,
			shared_a[lane].held, shared_a[lane].after,
			shared_a[lane].value, shared_a[lane].sequence);
	pr_info("kd_shared stats: claimed=%x observed=%u peer_sequence=%lu owner=%lx failures=%u\n",
		atomic_read(&shared_claimed), shared_observed,
		shared_peer_sequence, kd_test_mutex_owner(&shared_b),
		atomic_read(&shared_failures));
}
