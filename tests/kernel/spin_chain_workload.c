// SPDX-License-Identifier: GPL-2.0
/* A real queue chain: CPU 0 combines one request on each independently held lock. */
#define KD_CHAIN_DEPTH 8
#define KD_CHAIN_FOLLOWERS 3
static unsigned int spin_chain_depth;
module_param(spin_chain_depth, uint, 0444);
static bool spin_chain_armed;
module_param(spin_chain_armed, bool, 0644);
static unsigned int spin_chain_defer;
static unsigned int spin_chain_defer_count = 1;
static unsigned int spin_chain_defer_ready;
module_param(spin_chain_defer, uint, 0444);
module_param(spin_chain_defer_count, uint, 0444);
module_param(spin_chain_defer_ready, uint, 0644);
MODULE_PARM_DESC(spin_chain_defer, "Selected chain levels as a bitmask, 0=off");
MODULE_PARM_DESC(spin_chain_defer_count,
		 "Remote followers per selected level, 1..3");
MODULE_PARM_DESC(
	spin_chain_defer_ready,
	"Driver opens each level only after actual predecessor publication");
MODULE_PARM_DESC(spin_chain_depth,
		 "Mode 8 only: natural combiner chain depth, 0=off");
MODULE_PARM_DESC(spin_chain_armed,
		 "Arm only after all chain locks and JIT are ready");

static spinlock_t chain_locks[KD_CHAIN_DEPTH + 1];
static struct kd_cs_state chain_states[KD_CHAIN_DEPTH];
static unsigned long chain_completed[KD_CHAIN_DEPTH];
static atomic_t chain_inside[KD_CHAIN_DEPTH + 1];
static bool chain_owner_ready[KD_CHAIN_DEPTH];
static bool chain_abort;
static atomic_t chain_failures = ATOMIC_INIT(0);
static atomic_t chain_requests = ATOMIC_INIT(0);
static atomic_t chain_checked = ATOMIC_INIT(0);
static unsigned int chain_follower_acquired[KD_CHAIN_DEPTH][KD_CHAIN_FOLLOWERS];
static unsigned int chain_follower_returned[KD_CHAIN_DEPTH][KD_CHAIN_FOLLOWERS];

static unsigned int kd_chain_followers(unsigned int id)
{
	return spin_chain_defer & BIT(id) ? spin_chain_defer_count : 0;
}

struct kd_chain_record {
	struct task_struct *task;
	unsigned long id, value;
	unsigned int before, called, after;
};

static bool kd_chain_wait(unsigned int id, unsigned int queued, bool head)
{
	unsigned long deadline = jiffies + 10 * HZ;

	while (!READ_ONCE(chain_abort)) {
		unsigned int word = kd_spin_debug_word(&chain_locks[id].rlock);
		int count = kd_spin_debug_waiter_count(&chain_locks[id].rlock);

		if (smp_load_acquire(&chain_owner_ready[id]) && count >= 0 &&
		    (unsigned int)count >= queued &&
		    (!head ||
		     ((word & _Q_TAIL_MASK) == (1U << _Q_TAIL_CPU_OFFSET))))
			return true;
		if (time_after(jiffies, deadline)) {
			atomic_inc(&chain_failures);
			WRITE_ONCE(chain_abort, true);
			pr_err("kd_chain timeout: cpu=%d lock=%u queued=%d wanted=%u head=%u word=%x\n",
			       raw_smp_processor_id(), id, count, queued, head,
			       word);
			break;
		}
		cpu_relax();
	}
	return false;
}

static __attribute__((noipa)) noinline bool
kd_chain_prepare(unsigned int id, struct kd_chain_record *record)
{
	record->task = current;
	record->id = atomic_inc_return(&chain_requests);
	record->value = record->id;
	record->before = record->called = record->after = 0;
	return !READ_ONCE(spin_chain_armed) || kd_chain_wait(id, 1, true);
}

static __attribute__((noipa)) noinline void
kd_chain_finish(unsigned int id, const struct kd_chain_record *record)
{
	bool valid = record->task == current && record->before == 1 &&
		     record->called == 1 && record->after == 1 &&
		     record->value == (((record->id * 3) + 17) ^ 0x5a5a);

	if (!valid)
		atomic_inc(&chain_failures);
	atomic_inc(&chain_checked);
	if (READ_ONCE(spin_chain_armed))
		pr_info("kd_chain request: lock=%u task=%d cpu=%d before=%u called=%u after=%u valid=%u\n",
			id, current->pid, raw_smp_processor_id(),
			record->before, record->called, record->after, valid);
}

static __always_inline void kd_chain_enter(unsigned int id)
{
	if (atomic_inc_return(&chain_inside[id]) != 1)
		atomic_inc(&chain_failures);
}

static __always_inline void kd_chain_step(unsigned int id)
{
	kd_cs_transition(&chain_states[id]);
	chain_completed[id]++;
}

static __attribute__((noipa)) noinline void kd_chain_request(unsigned int id)
{
	struct kd_chain_record record;

	/* Keep warmup and armed execution at exactly the same two lock call sites. */
	if (!kd_chain_prepare(id, &record))
		return;
	spin_lock(&chain_locks[id]);
	kd_chain_enter(id);
	record.before++;
	record.value *= 3;
	spin_lock(&chain_locks[id + 1]);
	kd_chain_enter(id + 1);
	record.called++;
	record.value += 17;
	kd_chain_step(id);
	atomic_dec(&chain_inside[id + 1]);
	spin_unlock(&chain_locks[id + 1]);
	record.after++;
	record.value ^= 0x5a5a;
	atomic_dec(&chain_inside[id]);
	spin_unlock(&chain_locks[id]);
	kd_chain_finish(id, &record);
}

static noinline void kd_chain_direct(unsigned int id)
{
	spin_lock(&chain_locks[id]);
	kd_chain_enter(id);
	kd_chain_step(id);
	atomic_dec(&chain_inside[id]);
	spin_unlock(&chain_locks[id]);
}

static noinline void kd_chain_owner(unsigned int id)
{
	unsigned int followers = kd_chain_followers(id);
	unsigned long deadline = jiffies + 10 * HZ;

	spin_lock(&chain_locks[id]);
	kd_chain_enter(id);
	smp_store_release(&chain_owner_ready[id], true);
	kd_chain_wait(id, 3 + followers, false);
	/* Waiter counts precede prev->next publication; only the live link
	 * witness lets the controller release this independently held lock. */
	while (followers &&
	       !(smp_load_acquire(&spin_chain_defer_ready) & BIT(id)) &&
	       !READ_ONCE(chain_abort)) {
		if (time_after(jiffies, deadline)) {
			atomic_inc(&chain_failures);
			WRITE_ONCE(chain_abort, true);
			pr_err("kd_chain gate timeout: lock=%u cpu=%u\n", id,
			       raw_smp_processor_id());
		}
		cpu_relax();
	}
	kd_chain_step(id);
	atomic_dec(&chain_inside[id]);
	spin_unlock(&chain_locks[id]);
}

static noinline void kd_chain_follower_record(unsigned int id,
					      unsigned int extra,
					      struct task_struct *origin,
					      bool acquired)
{
	unsigned long owner = kd_spin_debug_owner(&chain_locks[id].rlock);
	u32 word = atomic_read(&chain_locks[id].rlock.raw_lock.val);
	bool valid = current == origin && !irqs_disabled() &&
		     preempt_count() == acquired;

	if (acquired) {
		valid &= atomic_read(&chain_inside[id]) == 1 &&
			 kd_test_spin_origin_locked(word) &&
			 owner == (unsigned long)origin;
		valid &= ++chain_follower_acquired[id][extra] == 1;
	} else {
		valid &= chain_follower_acquired[id][extra] == 1 &&
			 ++chain_follower_returned[id][extra] == 1;
	}
	if (!valid)
		atomic_inc(&chain_failures);
	pr_info("kd_chain follower: lock=%u extra=%u acquired=%u task=%d cpu=%u origin=%lx owner=%lx word=%x preempt=%u irq=%u valid=%u\n",
		id, extra, acquired, current->pid, raw_smp_processor_id(),
		(unsigned long)origin, owner, word, preempt_count(),
		irqs_disabled(), valid);
}

/* Never warm this lock call site. After daemon stop it must execute natively. */
static __attribute__((noipa)) noinline void
kd_chain_follower(unsigned int id, unsigned int extra)
{
	struct task_struct *origin = current;

	if (!kd_chain_wait(id, 2 + extra, false))
		return;
	spin_lock(&chain_locks[id]);
	kd_chain_enter(id);
	kd_chain_follower_record(id, extra, origin, true);
	kd_chain_step(id);
	atomic_dec(&chain_inside[id]);
	spin_unlock(&chain_locks[id]);
	kd_chain_follower_record(id, extra, origin, false);
}

static int kd_chain_run(unsigned long loops, unsigned int role)
{
	unsigned long i;

	if (role < spin_chain_depth) {
		for (i = 0; i < loops; i++)
			kd_chain_request(role);
		return READ_ONCE(chain_abort) ? -ETIMEDOUT : 0;
	}
	if (!READ_ONCE(spin_chain_armed) || loops != 1)
		return -EINVAL;
	if (role >= 20 && role < 20 + spin_chain_depth) {
		kd_chain_owner(role - 20);
	} else if (role >= 10 && role < 10 + spin_chain_depth) {
		if (kd_chain_wait(role - 10, 2 + kd_chain_followers(role - 10),
				  false))
			kd_chain_direct(role - 10);
	} else if (role >= 30 &&
		   role < 30 + KD_CHAIN_DEPTH * KD_CHAIN_FOLLOWERS) {
		unsigned int id = (role - 30) / KD_CHAIN_FOLLOWERS;
		unsigned int extra = (role - 30) % KD_CHAIN_FOLLOWERS;

		if (id >= spin_chain_depth || extra >= kd_chain_followers(id))
			return -EINVAL;
		kd_chain_follower(id, extra);
	} else if (role == 9) {
		if (kd_chain_wait(0, 0, false))
			kd_chain_direct(0);
	} else if (role == 8) {
		unsigned long deadline = jiffies + 10 * HZ;

		if (!kd_chain_wait(0, 0, false))
			return -ETIMEDOUT;
		while (!(kd_spin_debug_word(&chain_locks[0].rlock) &
			 _Q_PENDING_MASK)) {
			if (READ_ONCE(chain_abort) ||
			    time_after(jiffies, deadline)) {
				WRITE_ONCE(chain_abort, true);
				atomic_inc(&chain_failures);
				return -ETIMEDOUT;
			}
			cpu_relax();
		}
		pr_info("kd_chain root: task=%d cpu=%d\n", current->pid,
			raw_smp_processor_id());
		kd_chain_direct(0);
	} else {
		return -EINVAL;
	}
	return READ_ONCE(chain_abort) ? -ETIMEDOUT : 0;
}

static int kd_chain_init(void)
{
	unsigned int i;

	if (spin_chain_depth > KD_CHAIN_DEPTH || spin_chain_armed ||
	    spin_chain_defer_ready || !spin_chain_defer_count ||
	    spin_chain_defer_count > KD_CHAIN_FOLLOWERS ||
	    (spin_chain_defer >> spin_chain_depth) ||
	    (!spin_chain_defer && spin_chain_defer_count != 1) ||
	    (spin_chain_depth && (native_resume_stage || mixed_lock_probe)))
		return -EINVAL;
	for (i = 0; i <= spin_chain_depth; i++) {
		spin_lock_init(&chain_locks[i]);
		atomic_set(&chain_inside[i], 0);
		if (spin_chain_depth)
			pr_info("kd_chain lock: index=%u addr=%px\n", i,
				&chain_locks[i]);
	}
	return 0;
}

static void kd_chain_report(void)
{
	unsigned int i, active = 0;
	unsigned int acquired = 0, returned = 0;
	unsigned long total = 0;

	if (!spin_chain_depth)
		return;
	for (i = 0; i < spin_chain_depth; i++) {
		struct kd_cs_state expected = {};
		unsigned long j, count = chain_completed[i];
		bool valid = count <= KD_CS_VERIFY_LIMIT &&
			     chain_states[i].sequence == count;

		if (valid)
			for (j = 0; j < count; j++)
				kd_cs_transition(&expected);
		valid &= !memcmp(&chain_states[i], &expected, sizeof(expected));
		if (!valid)
			atomic_inc(&chain_failures);
		active += count != 0;
		total += count;
		pr_info("kd_chain state: lock=%u operations=%lu valid=%u\n", i,
			count, valid);
	}
	for (i = 0; i <= spin_chain_depth; i++)
		if (atomic_read(&chain_inside[i]))
			atomic_inc(&chain_failures);
	if (spin_chain_defer) {
		unsigned int extra;
		bool valid = spin_chain_defer_ready == spin_chain_defer;

		for (i = 0; i < spin_chain_depth; i++) {
			for (extra = 0; extra < KD_CHAIN_FOLLOWERS; extra++) {
				unsigned int expected = extra <
							kd_chain_followers(i);

				valid &= chain_follower_acquired[i][extra] ==
						 expected &&
					 chain_follower_returned[i][extra] ==
						 expected;
				acquired += chain_follower_acquired[i][extra];
				returned += chain_follower_returned[i][extra];
			}
		}
		if (!valid)
			atomic_inc(&chain_failures);
		pr_info("kd_chain deferred: mask=%u count=%u acquired=%u returned=%u valid=%u\n",
			spin_chain_defer, spin_chain_defer_count, acquired,
			returned, valid);
	}
	if (atomic_read(&chain_checked) != atomic_read(&chain_requests))
		atomic_inc(&chain_failures);
	pr_info("kd_chain summary: depth=%u operations=%lu states=%u requests=%d checked=%d failures=%d\n",
		spin_chain_depth, total, active, atomic_read(&chain_requests),
		atomic_read(&chain_checked), atomic_read(&chain_failures));
}
