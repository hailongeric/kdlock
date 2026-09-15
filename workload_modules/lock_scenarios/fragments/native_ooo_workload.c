// SPDX-License-Identifier: GPL-2.0
/* Included by the workload module only. Arm after stage-3 JIT publication. */
static unsigned int native_resume_ooo;
module_param(native_resume_ooo, uint, 0644);
MODULE_PARM_DESC(
	native_resume_ooo,
	"Stage 3 mode 1/4: 1=miss before A unlock, 2=ordinary miss after A, 3=capacity after A");
static bool jit_mutex_ooo;
module_param(jit_mutex_ooo, bool, 0644);
MODULE_PARM_DESC(jit_mutex_ooo, "Mode 4: fully translated A-before-B unlock");

/* A, B and six children fill the ledger. A stays recorded after OOO unlock,
 * so the seventh child's lock CALL hits real capacity without acquiring it. */
#define KD_OOO_CHILDREN 7
static spinlock_t ooo_spin_locks[KD_OOO_CHILDREN];
static struct mutex ooo_mutex_locks[KD_OOO_CHILDREN];
static unsigned int mutex_ooo_dependency;
module_param(mutex_ooo_dependency, uint, 0644);
MODULE_PARM_DESC(
	mutex_ooo_dependency,
	"Mode 4 OOO=3: independent C owner waits on A, 1=target, 2=native");
static bool ooo_dependency_ready;
static struct kd_resume_record *ooo_dependency_record;

static unsigned int spin_ooo_dependency;
module_param(spin_ooo_dependency, uint, 0644);
MODULE_PARM_DESC(
	spin_ooo_dependency,
	"Mode 1 OOO=3: independent C owner waits on A, 1=target, 2=native");
static atomic_t spin_dep_holder = ATOMIC_INIT(0);
static atomic_t spin_dep_direct = ATOMIC_INIT(0);
static atomic_t spin_dep_nested = ATOMIC_INIT(0);
static atomic_t spin_dep_trailing = ATOMIC_INIT(0);
static bool spin_dep_ready;
static struct kd_resume_record *spin_dep_record;

/* Executed after real spin_lock(C), spin_lock(A), with C still excluding B's
 * waiter. Linux qspinlock has no task owner field; only B's proxy gate does. */
static void kd_ooo_spin_observe(void)
{
	struct kd_resume_record *record = smp_load_acquire(&spin_dep_record);
	u32 a = atomic_read(&nested_lock_a.rlock.raw_lock.val);
	u32 b = atomic_read(&nested_lock_b.rlock.raw_lock.val);
	u32 c = atomic_read(&ooo_spin_locks[6].rlock.raw_lock.val);
	unsigned long a_owner = kd_spin_debug_owner(&nested_lock_a.rlock);
	unsigned long b_owner = kd_spin_debug_owner(&nested_lock_b.rlock);
	unsigned int prefix = record ? READ_ONCE(record->ooo_seen) : 0;
	bool valid = record && prefix == 1 && record->task != current &&
		     b_owner && b_owner != (unsigned long)current &&
		     b_owner != (unsigned long)record->task &&
		     kd_test_spin_origin_locked(a) &&
		     kd_test_spin_origin_locked(b) &&
		     kd_test_spin_origin_locked(c) && preempt_count() == 2 &&
		     !irqs_disabled();

	if (spin_ooo_dependency == 1)
		valid &= a_owner == (unsigned long)current;
	if (!valid)
		atomic_inc(&resume_failures);
	pr_info("kd_ooo spin dependency: kind=%u task=%d owner_task=%lx waiter=%lx waiter_pid=%d outer=%lx inner=%lx child=%lx a_word=%x b_word=%x c_word=%x a_owner=%lx b_owner=%lx preempt=%u irq=%u prefix=%u valid=%u comm=%s\n",
		spin_ooo_dependency, current->pid, (unsigned long)current,
		record ? (unsigned long)record->task : 0,
		record ? record->task->pid : 0, (unsigned long)&nested_lock_a,
		(unsigned long)&nested_lock_b,
		(unsigned long)&ooo_spin_locks[6], a, b, c, a_owner, b_owner,
		preempt_count(), irqs_disabled(), prefix, valid, current->comm);
}

static void kd_ooo_spin_prepare(struct kd_resume_record *record)
{
	if (!READ_ONCE(spin_ooo_dependency))
		return;
	smp_store_release(&spin_dep_record, record);
	if (spin_ooo_dependency == 2)
		while (!smp_load_acquire(&spin_dep_ready))
			cpu_relax();
	while (!atomic_read(&spin_dep_holder) ||
	       atomic_read(&spin_dep_direct) < 2 ||
	       kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 1)
		cpu_relax();
	atomic_set(&spin_dep_nested, 1);
}

static noinline void kd_ooo_spin_role(unsigned int role)
{
	struct kd_resume_record *record;
	unsigned long deadline = jiffies + 10 * HZ;

	if (role == 5) {
		if (spin_ooo_dependency != 2)
			return;
		spin_lock(&ooo_spin_locks[6]);
		smp_store_release(&spin_dep_ready, true);
		for (;;) {
			record = smp_load_acquire(&spin_dep_record);
			if (record && READ_ONCE(record->ooo_seen))
				break;
			if (time_after_eq(jiffies, deadline)) {
				atomic_inc(&resume_failures);
				pr_err("kd_ooo spin dependency: JIT prefix timed out\n");
				spin_unlock(&ooo_spin_locks[6]);
				return;
			}
			cpu_relax();
		}
		spin_lock(&nested_lock_a);
		kd_ooo_spin_observe();
		kd_cs_step(KD_CS_SPIN_A);
		spin_unlock(&nested_lock_a);
		spin_unlock(&ooo_spin_locks[6]);
		return;
	}
	if (role == 1) {
		spin_lock(&nested_lock_a);
		atomic_set(&spin_dep_holder, 1);
		while (atomic_read(&spin_dep_direct) < 2 ||
		       !atomic_read(&spin_dep_nested) ||
		       !atomic_read(&spin_dep_trailing) ||
		       kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 3)
			cpu_relax();
	} else if (role == 2 || role == 3) {
		while (!atomic_read(&spin_dep_holder))
			cpu_relax();
		atomic_inc(&spin_dep_direct);
		spin_lock(&nested_lock_a);
	} else if (role == 4) {
		while (!atomic_read(&spin_dep_nested) ||
		       kd_spin_debug_waiter_count(&nested_lock_a.rlock) < 2)
			cpu_relax();
		if (spin_ooo_dependency == 1)
			spin_lock(&ooo_spin_locks[6]);
		atomic_set(&spin_dep_trailing, 1);
		spin_lock(&nested_lock_a);
		if (spin_ooo_dependency == 1)
			kd_ooo_spin_observe();
	} else {
		atomic_inc(&resume_failures);
		return;
	}
	kd_cs_step(KD_CS_SPIN_A);
	spin_unlock(&nested_lock_a);
	if (role == 4 && spin_ooo_dependency == 1)
		spin_unlock(&ooo_spin_locks[6]);
}

/* This observer runs on C's original owner, never on the translated waiter. */
static void kd_ooo_dependency_observe(void)
{
	struct kd_resume_record *record =
		smp_load_acquire(&ooo_dependency_record);
	unsigned long a = kd_test_mutex_owner(&nested_mutex_a);
	unsigned long b = kd_test_mutex_owner(&nested_mutex_b);
	unsigned long c = kd_test_mutex_owner(&ooo_mutex_locks[6]);
	unsigned int prefix = record ? READ_ONCE(record->ooo_seen) : 0;
	bool valid =
		record && prefix == 1 && a == (unsigned long)current &&
		c == a && b && b != a && b != (unsigned long)record->task &&
		record->task != current && !preempt_count() && !irqs_disabled();

	if (!valid)
		atomic_inc(&resume_failures);
	pr_info("kd_ooo dependency: kind=%u task=%d owner_task=%lx waiter=%lx waiter_pid=%d outer=%lx inner=%lx child=%lx a=%lx b=%lx c=%lx prefix=%u valid=%u comm=%s\n",
		mutex_ooo_dependency, current->pid, (unsigned long)current,
		record ? (unsigned long)record->task : 0,
		record ? record->task->pid : 0, (unsigned long)&nested_mutex_a,
		(unsigned long)&nested_mutex_b,
		(unsigned long)&ooo_mutex_locks[6], a, b, c, prefix, valid,
		current->comm);
}

static void kd_ooo_dependency_prepare(struct kd_resume_record *record)
{
	if (!READ_ONCE(mutex_ooo_dependency))
		return;
	smp_store_release(&ooo_dependency_record, record);
	if (mutex_ooo_dependency == 2)
		while (!smp_load_acquire(&ooo_dependency_ready))
			cpu_relax();
}

static void kd_ooo_dependency_hold(void)
{
	mutex_lock(&ooo_mutex_locks[6]);
	smp_store_release(&ooo_dependency_ready, true);
}

/* The native-only participant waits for an actual JIT prefix before joining
 * A. Keeping C until it owns A exposes the A/B/C cycle without an injected error. */
static noinline void run_mutex_native_dependency_role(void)
{
	struct kd_resume_record *record;
	unsigned long deadline = jiffies + 10 * HZ;

	if (READ_ONCE(mutex_ooo_dependency) != 2)
		return;
	kd_ooo_dependency_hold();
	for (;;) {
		record = smp_load_acquire(&ooo_dependency_record);
		if (record && READ_ONCE(record->ooo_seen))
			break;
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&resume_failures);
			pr_err("kd_ooo dependency: JIT prefix timed out\n");
			mutex_unlock(&ooo_mutex_locks[6]);
			return;
		}
		cpu_relax();
	}
	mutex_lock(&nested_mutex_a);
	kd_ooo_dependency_observe();
	kd_cs_step(KD_CS_MUTEX_A);
	mutex_unlock(&nested_mutex_a);
	mutex_unlock(&ooo_mutex_locks[6]);
}

static void kd_ooo_init(void)
{
	unsigned int i;

	for (i = 0; i < KD_OOO_CHILDREN; i++) {
		spin_lock_init(&ooo_spin_locks[i]);
		mutex_init(&ooo_mutex_locks[i]);
	}
}

/* Inline phase zero must execute before A unlock, without a CALL miss or a
 * logical-current/per-CPU access that would reject this test at admission. */
static __always_inline void kd_ooo_jit_prefix(struct kd_resume_record *record)
{
	record->ooo_value = record->value * 17 ^ record->value;
	record->ooo_seen++;
}

/* Runs only on the original waiter after the final child's native lock CALL.
 * The B-protected fixture serializes all accesses to these child locks. */
static __attribute__((noipa)) noinline void
kd_ooo_pending_observe(struct kd_resume_record *record, bool mutex)
{
	unsigned long id = record - resume_records;
	unsigned long b_owner = mutex ? kd_test_mutex_owner(&nested_mutex_b) :
					0;
	unsigned int i;
	bool valid = id < KD_RESUME_RECORDS && record->task == current &&
		     record->ooo_seen == 1 && !irqs_disabled();

	for (i = 0; i < KD_OOO_CHILDREN; i++) {
		unsigned long addr, owner = 0;
		u32 word = 0;
		bool owned;

		if (mutex) {
			addr = (unsigned long)&ooo_mutex_locks[i];
			owner = kd_test_mutex_owner(&ooo_mutex_locks[i]);
			owned = owner &&
				owner == (i == KD_OOO_CHILDREN - 1 ?
						  (unsigned long)current :
						  b_owner);
		} else {
			addr = (unsigned long)&ooo_spin_locks[i];
			word = atomic_read(
				&ooo_spin_locks[i].rlock.raw_lock.val);
			owned = kd_test_spin_origin_locked(word);
		}
		valid &= owned;
		pr_info("kd_ooo pending lock: record=%lu task=%d mutex=%u index=%u lock=%lx owner=%lx word=%x preempt=%u valid=%u\n",
			id, current->pid, mutex, i, addr, owner, word,
			preempt_count(), valid);
	}
	if (!valid)
		atomic_inc(&resume_failures);
}

/* Explicit calls keep every lexical path balanced for the admission walk. */
static __always_inline void
kd_ooo_pending_spin_enter(struct kd_resume_record *record)
{
	spin_lock(&ooo_spin_locks[0]);
	spin_lock(&ooo_spin_locks[1]);
	spin_lock(&ooo_spin_locks[2]);
	spin_lock(&ooo_spin_locks[3]);
	spin_lock(&ooo_spin_locks[4]);
	spin_lock(&ooo_spin_locks[5]);
	kd_ooo_jit_prefix(record);
	spin_unlock(&nested_lock_a);
	spin_lock(&ooo_spin_locks[6]);
	kd_ooo_pending_observe(record, false);
}

static __always_inline void kd_ooo_pending_spin_leave(void)
{
	spin_unlock(&ooo_spin_locks[6]);
	spin_unlock(&ooo_spin_locks[5]);
	spin_unlock(&ooo_spin_locks[4]);
	spin_unlock(&ooo_spin_locks[3]);
	spin_unlock(&ooo_spin_locks[2]);
	spin_unlock(&ooo_spin_locks[1]);
	spin_unlock(&ooo_spin_locks[0]);
}

static __always_inline void
kd_ooo_pending_mutex_enter(struct kd_resume_record *record)
{
	mutex_lock(&ooo_mutex_locks[0]);
	mutex_lock(&ooo_mutex_locks[1]);
	mutex_lock(&ooo_mutex_locks[2]);
	mutex_lock(&ooo_mutex_locks[3]);
	mutex_lock(&ooo_mutex_locks[4]);
	mutex_lock(&ooo_mutex_locks[5]);
	kd_ooo_jit_prefix(record);
	mutex_unlock(&nested_mutex_a);
	mutex_lock(&ooo_mutex_locks[6]);
	kd_ooo_pending_observe(record, true);
}

static __always_inline void kd_ooo_pending_mutex_leave(void)
{
	mutex_unlock(&ooo_mutex_locks[6]);
	mutex_unlock(&ooo_mutex_locks[5]);
	mutex_unlock(&ooo_mutex_locks[4]);
	mutex_unlock(&ooo_mutex_locks[3]);
	mutex_unlock(&ooo_mutex_locks[2]);
	mutex_unlock(&ooo_mutex_locks[1]);
	mutex_unlock(&ooo_mutex_locks[0]);
}

/* This callee stays untranslated: the earlier probe must already have caused
 * a CALL miss. Check the original task and pin on both sides of each unlock. */
static __attribute__((noipa)) noinline void
kd_ooo_checkpoint(struct kd_resume_record *record, bool mutex,
		  unsigned int phase)
{
	unsigned long a = 0, b = 0;
	unsigned long a_owner = 0, b_owner = 0;
	unsigned int a_private = 0, b_private = 0;
	unsigned int count = preempt_count();
	unsigned long id = record ? record - resume_records : KD_RESUME_RECORDS;
	bool valid = record && id < KD_RESUME_RECORDS && phase <= 2 &&
		     native_resume_stage == 3 && record->task == current &&
		     record->before == 1 && record->called == 1 &&
		     record->after == 1 && record->ooo_seen == phase &&
		     !irqs_disabled();

	if (mutex) {
		valid &= count == 0;
		if (phase < 2) {
			a = kd_test_mutex_owner(&nested_mutex_a);
			b = kd_test_mutex_owner(&nested_mutex_b);
			valid &= b != 0;
			if (!phase)
				valid &= a != 0;
		}
	} else {
		valid &= phase == 2 ? count == 0 : count != 0;
		if (phase < 2) {
			a = atomic_read(&nested_lock_a.rlock.raw_lock.val);
			b = atomic_read(&nested_lock_b.rlock.raw_lock.val);
			a_private = kd_spin_debug_word(&nested_lock_a.rlock);
			b_private = kd_spin_debug_word(&nested_lock_b.rlock);
			a_owner = kd_spin_debug_owner(&nested_lock_a.rlock);
			b_owner = kd_spin_debug_owner(&nested_lock_b.rlock);
			valid &= kd_test_spin_origin_locked(b);
			if (!phase)
				valid &= kd_test_spin_origin_locked(a);
		}
	}
	if (record) {
		if (!phase)
			record->ooo_value = id + 1;
		record->ooo_value = record->ooo_value * 17 ^ (id + phase + 1);
		record->ooo_seen++;
	}
	if (!valid)
		atomic_inc(&resume_failures);
	pr_info("kd_ooo checkpoint: record=%lu task=%d waiter=%lx phase=%u mutex=%u cpu=%u preempt=%u irq=%u a=%lx b=%lx a_private=%x b_private=%x a_owner=%lx b_owner=%lx value=%lx valid=%u\n",
		id, current->pid, record ? (unsigned long)record->task : 0,
		phase, mutex, raw_smp_processor_id(), count, irqs_disabled(), a,
		b, a_private, b_private, a_owner, b_owner,
		record ? record->ooo_value : 0, valid);
}

static void kd_ooo_report(void)
{
	unsigned int checked = 0, failures = 0;
	int id, count = min(atomic_read(&resume_requests), KD_RESUME_RECORDS);

	if (!native_resume_ooo)
		return;
	for (id = 0; id < count; id++) {
		const struct kd_resume_record *record = &resume_records[id];
		unsigned long value = id + 1;
		unsigned int phase;

		if (!record->ooo_seen)
			continue;
		for (phase = 0; phase < 3; phase++)
			value = value * 17 ^ (id + phase + 1);
		checked++;
		if (record->ooo_seen != 3 || record->ooo_value != value)
			failures++;
	}
	if (failures)
		atomic_add(failures, &resume_failures);
	pr_info("kd_ooo stats: checked=%u failures=%u\n", checked, failures);
}
