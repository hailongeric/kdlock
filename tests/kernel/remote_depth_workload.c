// SPDX-License-Identifier: GPL-2.0
/* Mode 8 opt-in: one logical waiter, independent physical executors per lock. */
#define KD_DEEP_MAX 8
#define KD_DEEP_DEFER_MAX 8
static unsigned int remote_chain_depth, remote_chain_stage;
static bool remote_chain_reverse;
static unsigned int remote_chain_defer;
static unsigned int remote_chain_defer_count = 1;
static bool remote_chain_defer_ready;
static bool remote_chain_readmit, remote_chain_readmit_ready;
static unsigned int remote_chain_readmit_layer = 3;
module_param(remote_chain_depth, uint, 0444);
module_param(remote_chain_stage, uint, 0644);
module_param(remote_chain_reverse, bool, 0644);
module_param(remote_chain_defer, uint, 0444);
module_param(remote_chain_defer_count, uint, 0444);
module_param(remote_chain_defer_ready, bool, 0644);
module_param(remote_chain_readmit, bool, 0444);
module_param(remote_chain_readmit_ready, bool, 0644);
module_param(remote_chain_readmit_layer, uint, 0444);
MODULE_PARM_DESC(
	remote_chain_readmit_layer,
	"Readmission virtual layer: 1=B, 2=C, 3=D in the four-lock workload");
MODULE_PARM_DESC(
	remote_chain_readmit,
	"Four-lock JIT test: real local lead and remote prefix before virtual request");
MODULE_PARM_DESC(
	remote_chain_defer,
	"Extra successor at logical layer + 1, 0=off; requires selftest link tracing");
MODULE_PARM_DESC(
	remote_chain_defer_count,
	"Remote followers at the selected layer: 1..8, followed by one local successor");
MODULE_PARM_DESC(remote_chain_depth,
		 "Mode 8 logical remote depth: 0=off, 4..8");
MODULE_PARM_DESC(
	remote_chain_stage,
	"Arm after publication: 1=JIT, 2=before, 3=after, 4=between, 5=capacity at depth 8");

static spinlock_t deep_locks[KD_DEEP_MAX + 1];
static struct kd_cs_state deep_states[KD_DEEP_MAX];
static unsigned long deep_completed[KD_DEEP_MAX];
static atomic_t deep_inside[KD_DEEP_MAX + 1];
static atomic_t deep_direct[KD_DEEP_MAX];
static bool deep_holder[KD_DEEP_MAX], deep_published[KD_DEEP_MAX];
static bool deep_dependency_ready, deep_abort;
static atomic_t deep_failures = ATOMIC_INIT(0);
static unsigned int deep_prefix, deep_suffix, deep_observed, deep_origin_cpu;
static unsigned int deep_requests, deep_checked;
static struct task_struct *deep_waiter;
static unsigned int deep_follower_acquired[KD_DEEP_DEFER_MAX + 1];
static unsigned int deep_follower_returned[KD_DEEP_DEFER_MAX + 1];

struct kd_deep_record {
	struct task_struct *task;
	unsigned int id, before, called, after;
	unsigned long value;
};

static __always_inline void kd_deep_enter(unsigned int id)
{
	u32 word = atomic_read(&deep_locks[id].rlock.raw_lock.val) &
		   _Q_LOCKED_MASK;

	if (atomic_inc_return(&deep_inside[id]) != 1 ||
	    (word != _Q_LOCKED_VAL && word != (3U << _Q_LOCKED_OFFSET)))
		atomic_inc(&deep_failures);
}

static __always_inline void kd_deep_leave(unsigned int id)
{
	if (atomic_dec_return(&deep_inside[id]) != 0)
		atomic_inc(&deep_failures);
}

static __always_inline void kd_deep_step(unsigned int id)
{
	kd_cs_transition(&deep_states[id]);
	deep_completed[id]++;
}

static bool kd_deep_wait(unsigned int id, unsigned int queued)
{
	unsigned long deadline = jiffies + 15 * HZ;

	while (!READ_ONCE(deep_abort)) {
		int count = kd_spin_debug_waiter_count(&deep_locks[id].rlock);

		if (smp_load_acquire(&deep_holder[id]) &&
		    (!queued ||
		     (count >= 0 && (unsigned int)count >= queued &&
		      atomic_read(&deep_direct[id]) >= 2 &&
		      (queued < 2 || smp_load_acquire(&deep_published[id])))))
			return true;
		if (time_after_eq(jiffies, deadline)) {
			pr_err("kd_deep timeout: lock=%u queued=%u cpu=%u\n",
			       id, queued, raw_smp_processor_id());
			atomic_inc(&deep_failures);
			WRITE_ONCE(deep_abort, true);
			break;
		}
		cpu_relax();
	}
	return false;
}

/* Unlike kd_deep_wait(queued >= 2), this runs before the parent publishes
 * its nested request. Only actual predecessor admission opens this gate. */
static bool kd_deep_readmit_wait(unsigned int queued)
{
	unsigned long deadline = jiffies + 15 * HZ;
	unsigned int id = remote_chain_readmit_layer;

	while (!READ_ONCE(deep_abort)) {
		int count = kd_spin_debug_waiter_count(&deep_locks[id].rlock);

		if (smp_load_acquire(&deep_holder[id]) && count >= 0 &&
		    (unsigned int)count >= queued &&
		    atomic_read(&deep_direct[id]) >= (int)queued + 1)
			return true;
		if (time_after_eq(jiffies, deadline)) {
			pr_err("kd_deep readmit timeout: queued=%u cpu=%u\n",
			       queued, raw_smp_processor_id());
			atomic_inc(&deep_failures);
			WRITE_ONCE(deep_abort, true);
		}
		cpu_relax();
	}
	return false;
}

static __attribute__((noipa)) noinline bool
kd_deep_prepare(struct kd_deep_record *record)
{
	unsigned int i;
	unsigned int id = ++deep_requests;
	unsigned long deadline = jiffies + 15 * HZ;

	*record = (struct kd_deep_record){ .task = current,
					   .id = id,
					   .value = id };
	if (!READ_ONCE(remote_chain_stage))
		return true;
	WRITE_ONCE(deep_waiter, current);
	WRITE_ONCE(deep_origin_cpu, raw_smp_processor_id());
	while (!smp_load_acquire(&deep_dependency_ready)) {
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&deep_failures);
			WRITE_ONCE(deep_abort, true);
			return false;
		}
		cpu_relax();
	}
	for (i = 0; i < remote_chain_depth; i++)
		if (!kd_deep_wait(i, 1))
			return false;
	if (remote_chain_readmit && !kd_deep_readmit_wait(3))
		return false;
	return true;
}

static __attribute__((noipa)) noinline void
kd_deep_native_probe(struct kd_deep_record *record)
{
	bool valid = current == record->task && record->before == 1 &&
		     !record->called && !record->after;

	if (!valid)
		atomic_inc(&deep_failures);
	record->called++;
	record->value += 17;
	pr_info("kd_deep native probe: task=%d cpu=%u record=%u valid=%u\n",
		current->pid, raw_smp_processor_id(), record->id, valid);
	if (native_resume_rename)
		kd_test_rename("kd_renamed");
}

static __always_inline void kd_deep_probe(struct kd_deep_record *record)
{
	record->before++;
	record->value *= 3;
	kd_deep_native_probe(record);
	record->after++;
	record->value ^= 0x5a5a;
}

static __attribute__((noipa)) noinline void
kd_deep_finish(const struct kd_deep_record *record)
{
	bool native = READ_ONCE(remote_chain_stage) > 1;
	unsigned long expected = native ? (record->id * 3UL + 17) ^ 0x5a5a :
					  record->id;
	bool valid = current == record->task && record->before == native &&
		     record->called == native && record->after == native &&
		     record->value == expected && !preempt_count() &&
		     !irqs_disabled();

	if (!valid)
		atomic_inc(&deep_failures);
	deep_checked++;
	if (native && native_resume_rename)
		kd_test_rename("klock_test");
	pr_info("kd_deep request: task=%d cpu=%u record=%u before=%u called=%u after=%u valid=%u armed=%u\n",
		current->pid, raw_smp_processor_id(), record->id,
		record->before, record->called, record->after, valid,
		!!remote_chain_stage);
}

/* Each configured depth has a bounded source CFG. Repeated runtime tests of
 * depth around an acquisition loop would lose the lexical lock boundary. */
#define DEEP_ACQUIRE(i)                              \
	smp_store_release(&deep_published[i], true); \
	spin_lock(&deep_locks[i]);                   \
	kd_deep_enter(i);                            \
	kd_deep_step(i)
#define DEEP_RELEASE(i, first)                             \
	kd_deep_leave(i);                                  \
	spin_unlock(&deep_locks[i]);                       \
	if ((first) && READ_ONCE(remote_chain_stage) == 4) \
	kd_deep_probe(&record)
#define DEEP_ACQUIRE_4   \
	DEEP_ACQUIRE(0); \
	DEEP_ACQUIRE(1); \
	DEEP_ACQUIRE(2); \
	DEEP_ACQUIRE(3)
#define DEEP_ACQUIRE_5  \
	DEEP_ACQUIRE_4; \
	DEEP_ACQUIRE(4)
#define DEEP_ACQUIRE_6  \
	DEEP_ACQUIRE_5; \
	DEEP_ACQUIRE(5)
#define DEEP_ACQUIRE_7  \
	DEEP_ACQUIRE_6; \
	DEEP_ACQUIRE(6)
#define DEEP_ACQUIRE_8  \
	DEEP_ACQUIRE_7; \
	DEEP_ACQUIRE(7)
#define DEEP_FORWARD_4      \
	DEEP_RELEASE(0, 1); \
	DEEP_RELEASE(1, 0); \
	DEEP_RELEASE(2, 0)
#define DEEP_FORWARD_5  \
	DEEP_FORWARD_4; \
	DEEP_RELEASE(3, 0)
#define DEEP_FORWARD_6  \
	DEEP_FORWARD_5; \
	DEEP_RELEASE(4, 0)
#define DEEP_FORWARD_7  \
	DEEP_FORWARD_6; \
	DEEP_RELEASE(5, 0)
#define DEEP_FORWARD_8  \
	DEEP_FORWARD_7; \
	DEEP_RELEASE(6, 0)
#define DEEP_REST_4         \
	DEEP_RELEASE(1, 0); \
	DEEP_RELEASE(0, 0)
#define DEEP_REST_5         \
	DEEP_RELEASE(2, 0); \
	DEEP_REST_4
#define DEEP_REST_6         \
	DEEP_RELEASE(3, 0); \
	DEEP_REST_5
#define DEEP_REST_7         \
	DEEP_RELEASE(4, 0); \
	DEEP_REST_6
#define DEEP_REST_8         \
	DEEP_RELEASE(5, 0); \
	DEEP_REST_7
#define DEEP_REQUEST(n)                                                       \
	static __attribute__((noipa)) noinline void kd_deep_request_##n(void) \
	{                                                                     \
		struct kd_deep_record record;                                 \
		if (!kd_deep_prepare(&record))                                \
			return;                                               \
		DEEP_ACQUIRE_##n;                                             \
		if (READ_ONCE(remote_chain_stage))                            \
			deep_prefix++;                                        \
		if (READ_ONCE(remote_chain_stage) == 2)                       \
			kd_deep_probe(&record);                               \
		if (READ_ONCE(remote_chain_reverse)) {                        \
			DEEP_RELEASE(n - 2, 1);                               \
			DEEP_REST_##n;                                        \
		} else {                                                      \
			DEEP_FORWARD_##n;                                     \
		}                                                             \
		if (READ_ONCE(remote_chain_stage) == 3)                       \
			kd_deep_probe(&record);                               \
		spin_lock(&deep_locks[n]);                                    \
		kd_deep_enter(n);                                             \
		if (READ_ONCE(remote_chain_stage) == 5)                       \
			kd_deep_probe(&record);                               \
		if (READ_ONCE(remote_chain_stage))                            \
			deep_suffix++;                                        \
		kd_deep_step(n - 1);                                          \
		kd_deep_leave(n);                                             \
		spin_unlock(&deep_locks[n]);                                  \
		kd_deep_leave(n - 1);                                         \
		spin_unlock(&deep_locks[n - 1]);                              \
		kd_deep_finish(&record);                                      \
	}
DEEP_REQUEST(4)
DEEP_REQUEST(5)
DEEP_REQUEST(6)
DEEP_REQUEST(7)
DEEP_REQUEST(8)

static __attribute__((noipa)) noinline bool
kd_deep_direct_prepare(unsigned int id)
{
	if (!READ_ONCE(remote_chain_stage))
		return true;
	if (!kd_deep_wait(id, 0))
		return false;
	atomic_inc(&deep_direct[id]);
	smp_mb__after_atomic();
	return true;
}

static __attribute__((noipa)) noinline void kd_deep_direct(unsigned int id)
{
	if (!kd_deep_direct_prepare(id))
		return;
	spin_lock(&deep_locks[id]);
	kd_deep_enter(id);
	kd_deep_step(id);
	kd_deep_leave(id);
	spin_unlock(&deep_locks[id]);
}

static noinline void kd_deep_holder(unsigned int id)
{
	bool deferred = remote_chain_defer == id + 1;
	bool readmit = remote_chain_readmit && id == remote_chain_readmit_layer;
	unsigned long deadline = jiffies + 15 * HZ;

	WRITE_ONCE(deep_published[id], false);
	atomic_set(&deep_direct[id], 0);
	spin_lock(&deep_locks[id]);
	kd_deep_enter(id);
	smp_store_release(&deep_holder[id], true);
	kd_deep_wait(id, readmit  ? 5 :
			 deferred ? remote_chain_defer_count + 3 :
				    3);
	/* The driver opens this gate only after observing the actual tail link. */
	while (((deferred && !smp_load_acquire(&remote_chain_defer_ready)) ||
		(readmit && !smp_load_acquire(&remote_chain_readmit_ready))) &&
	       !READ_ONCE(deep_abort)) {
		if (time_after_eq(jiffies, deadline)) {
			pr_err("kd_deep deferred timeout: lock=%u cpu=%u\n", id,
			       raw_smp_processor_id());
			atomic_inc(&deep_failures);
			WRITE_ONCE(deep_abort, true);
		}
		cpu_relax();
	}
	kd_deep_step(id);
	kd_deep_leave(id);
	spin_unlock(&deep_locks[id]);
}

static __attribute__((noipa)) noinline void
kd_deep_follower_record(unsigned int id, unsigned int extra, bool acquired)
{
	unsigned long owner = kd_spin_debug_owner(&deep_locks[id].rlock);
	u32 word = atomic_read(&deep_locks[id].rlock.raw_lock.val);
	bool valid = !irqs_disabled() && preempt_count() == acquired;

	if (acquired) {
		valid &= atomic_read(&deep_inside[id]) == 1 &&
			 kd_test_spin_origin_locked(word) &&
			 owner == (unsigned long)current;
		valid &= ++deep_follower_acquired[extra] == 1;
	} else {
		valid &= deep_follower_acquired[extra] == 1 &&
			 ++deep_follower_returned[extra] == 1;
	}
	if (!valid)
		atomic_inc(&deep_failures);
	pr_info("kd_deep follower: index=%u extra=%u acquired=%u task=%d cpu=%u owner=%lx word=%x preempt=%u irq=%u valid=%u\n",
		id, extra, acquired, current->pid, raw_smp_processor_id(),
		owner, word, preempt_count(), irqs_disabled(), valid);
}

static noinline void kd_deep_trailing(unsigned int id, unsigned int extra)
{
	if (!kd_deep_wait(
		    id,
		    extra + 2 +
			    (remote_chain_readmit &&
					     id == remote_chain_readmit_layer ?
				     2 :
				     0)))
		return;
	spin_lock(&deep_locks[id]);
	kd_deep_enter(id);
	if (remote_chain_defer == id + 1)
		kd_deep_follower_record(id, extra, true);
	kd_deep_step(id);
	kd_deep_leave(id);
	spin_unlock(&deep_locks[id]);
	if (remote_chain_defer == id + 1)
		kd_deep_follower_record(id, extra, false);
}

static noinline void kd_deep_observer(void)
{
	unsigned int i, n = remote_chain_depth;
	unsigned long deadline = jiffies + 15 * HZ;
	struct task_struct *waiter;
	bool valid;

	spin_lock(&deep_locks[n]);
	kd_deep_enter(n);
	smp_store_release(&deep_dependency_ready, true);
	while (!READ_ONCE(deep_prefix) && !READ_ONCE(deep_abort)) {
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&deep_failures);
			WRITE_ONCE(deep_abort, true);
		}
		cpu_relax();
	}
	if (READ_ONCE(deep_abort))
		goto out;
	for (i = 0; i + 1 < n; i++) {
		spin_lock(&deep_locks[i]);
		kd_deep_enter(i);
		kd_deep_step(i);
	}
	waiter = READ_ONCE(deep_waiter);
	valid = waiter && waiter != current && deep_prefix == 1 &&
		!deep_suffix && !deep_observed && preempt_count() == n &&
		!irqs_disabled();
	for (i = 0; i <= n; i++) {
		unsigned long owner = kd_spin_debug_owner(&deep_locks[i].rlock);
		u32 word = atomic_read(&deep_locks[i].rlock.raw_lock.val);
		bool held = kd_test_spin_origin_locked(word) &&
			    atomic_read(&deep_inside[i]) == 1;

		if (i == n - 1)
			held &= owner && owner != (unsigned long)waiter &&
				owner != (unsigned long)current;
		if (i < n - 1 && !strcmp(current->comm, "klock_test"))
			held &= owner == (unsigned long)current;
		valid &= held;
		pr_info("kd_deep observe lock: index=%u addr=%lx word=%x owner=%lx valid=%u\n",
			i, (unsigned long)&deep_locks[i], word, owner, held);
	}
	if (!valid)
		atomic_inc(&deep_failures);
	deep_observed++;
	pr_info("kd_deep observe: task=%d cpu=%u owner=%lx waiter=%lx waiter_pid=%d origin_cpu=%u depth=%u prefix=%u suffix=%u preempt=%u irq=%u valid=%u comm=%s\n",
		current->pid, raw_smp_processor_id(), (unsigned long)current,
		(unsigned long)waiter, waiter ? waiter->pid : 0,
		deep_origin_cpu, n, deep_prefix, deep_suffix, preempt_count(),
		irqs_disabled(), valid, current->comm);
	for (i = n - 1; i > 0; i--) {
		kd_deep_leave(i - 1);
		spin_unlock(&deep_locks[i - 1]);
	}
out:
	kd_deep_leave(n);
	spin_unlock(&deep_locks[n]);
}

static int kd_deep_run(unsigned long loops, unsigned int role)
{
	unsigned long i;
	unsigned int id = role >= 2 ? (role - 2) / 4 : 0;
	unsigned int kind = role >= 2 ? (role - 2) % 4 : 0;
	unsigned int base = 2 + 4 * remote_chain_depth;
	bool extra = remote_chain_defer && role >= base;
	bool readmit = remote_chain_readmit && role >= base;

	if (remote_chain_stage > 5 ||
	    role >= base + (remote_chain_readmit ? 2 :
			    remote_chain_defer	 ? remote_chain_defer_count :
						   0) ||
	    (remote_chain_readmit && remote_chain_stage > 1) ||
	    (remote_chain_stage == 5 && remote_chain_depth != 8) ||
	    (remote_chain_stage == 1 && remote_chain_depth == 8) ||
	    (!remote_chain_stage && role &&
	     (extra || readmit || role == 1 || kind == 0 || kind == 3)) ||
	    (remote_chain_stage && loops != 1))
		return -EINVAL;
	for (i = 0; i < loops; i++) {
		if (!role) {
			switch (remote_chain_depth) {
			case 4:
				kd_deep_request_4();
				break;
			case 5:
				kd_deep_request_5();
				break;
			case 6:
				kd_deep_request_6();
				break;
			case 7:
				kd_deep_request_7();
				break;
			case 8:
				kd_deep_request_8();
				break;
			}
		} else if (role == 1)
			kd_deep_observer();
		else if (readmit) {
			if (kd_deep_readmit_wait(role - base + 1))
				kd_deep_direct(remote_chain_readmit_layer);
		} else if (extra)
			kd_deep_trailing(remote_chain_defer - 1,
					 role - base + 1);
		else if (kind == 0)
			kd_deep_holder(id);
		else if (kind == 3)
			kd_deep_trailing(id, 0);
		else
			kd_deep_direct(id);
	}
	return READ_ONCE(deep_abort) ? -ETIMEDOUT : 0;
}

static int kd_deep_init(void)
{
	unsigned int i;

	if (!remote_chain_defer_count ||
	    remote_chain_defer_count > KD_DEEP_DEFER_MAX ||
	    (!remote_chain_defer && remote_chain_defer_count != 1))
		return -EINVAL;
	if (remote_chain_readmit_layer < 1 || remote_chain_readmit_layer > 3 ||
	    (!remote_chain_readmit && remote_chain_readmit_layer != 3) ||
	    remote_chain_readmit_ready ||
	    (remote_chain_readmit &&
	     (remote_chain_depth != 4 || remote_chain_defer)))
		return -EINVAL;
	if (!remote_chain_depth)
		return remote_chain_stage || remote_chain_reverse ||
				       remote_chain_defer ||
				       remote_chain_defer_ready ?
			       -EINVAL :
			       0;
	if (remote_chain_depth < 4 || remote_chain_depth > KD_DEEP_MAX ||
	    remote_chain_stage || remote_chain_reverse || native_resume_stage ||
	    spin_chain_depth || mixed_lock_probe || remote_spin_ooo ||
	    remote_chain_defer > remote_chain_depth || remote_chain_defer_ready)
		return -EINVAL;
	for (i = 0; i <= remote_chain_depth; i++) {
		spin_lock_init(&deep_locks[i]);
		atomic_set(&deep_inside[i], 0);
		pr_info("kd_deep lock: index=%u addr=%lx\n", i,
			(unsigned long)&deep_locks[i]);
	}
	return 0;
}

static void kd_deep_report(void)
{
	unsigned int i, n = remote_chain_depth;

	if (!n)
		return;
	for (i = 0; i < n; i++) {
		struct kd_cs_state expected = {};
		unsigned long j, count = deep_completed[i];
		bool valid = count <= KD_CS_VERIFY_LIMIT &&
			     deep_states[i].sequence == count;

		if (valid)
			for (j = 0; j < count; j++)
				kd_cs_transition(&expected);
		valid &= !memcmp(&deep_states[i], &expected, sizeof(expected));
		if (!valid)
			atomic_inc(&deep_failures);
		pr_info("kd_deep state: index=%u operations=%lu valid=%u\n", i,
			count, valid);
	}
	for (i = 0; i <= n; i++) {
		int queued = kd_spin_debug_waiter_count(&deep_locks[i].rlock);
		unsigned int inside = atomic_read(&deep_inside[i]);
		u32 word = atomic_read(&deep_locks[i].rlock.raw_lock.val);
		unsigned long owner = kd_spin_debug_owner(&deep_locks[i].rlock);
		bool valid = !inside && !word && !owner &&
			     (!queued || (i == n && queued == -ENOSPC));

		if (!valid)
			atomic_inc(&deep_failures);
		pr_info("kd_deep drain: index=%u inside=%u word=%x owner=%lx queued=%d valid=%u\n",
			i, inside, word, owner, queued, valid);
	}
	if (deep_prefix != 1 || deep_suffix != 1 || deep_observed != 1 ||
	    deep_requests != 2 || deep_checked != deep_requests)
		atomic_inc(&deep_failures);
	if (remote_chain_readmit) {
		bool valid = remote_chain_readmit_ready;
		if (!valid)
			atomic_inc(&deep_failures);
		pr_info("kd_deep readmit: ready=%u valid=%u\n",
			remote_chain_readmit_ready, valid);
	}
	if (remote_chain_defer) {
		unsigned int acquired = 0, returned = 0;
		bool valid = remote_chain_defer_ready;

		for (i = 0; i <= remote_chain_defer_count; i++) {
			valid &= deep_follower_acquired[i] == 1 &&
				 deep_follower_returned[i] == 1;
			acquired += deep_follower_acquired[i];
			returned += deep_follower_returned[i];
		}
		if (!valid)
			atomic_inc(&deep_failures);
		pr_info("kd_deep deferred: layer=%u ready=%u followers=%u acquired=%u returned=%u valid=%u\n",
			remote_chain_defer - 1, remote_chain_defer_ready,
			remote_chain_defer_count + 1, acquired, returned,
			valid);
	}
	pr_info("kd_deep summary: depth=%u stage=%u reverse=%u requests=%u checked=%u prefix=%u suffix=%u observed=%u failures=%d abort=%u\n",
		n, remote_chain_stage, remote_chain_reverse, deep_requests,
		deep_checked, deep_prefix, deep_suffix, deep_observed,
		atomic_read(&deep_failures), deep_abort);
}
