/* SPDX-License-Identifier: GPL-2.0 */
/* Seven real hook callers put virtual B at its private queue's head, with a
 * follower. No node, gate word, capacity or production result is fabricated.
 * All scheduling barriers are outside JIT or after its checked native exit. */
static struct kd_resume_record *acquired_record;
static unsigned int acquired_prepared, acquired_suffix, acquired_completed;
static unsigned int acquired_queued, acquired_trailer;
static atomic_t acquired_failures = ATOMIC_INIT(0);

static void kd_acquired_check(bool valid)
{
	if (!valid) {
		atomic_inc(&acquired_failures);
		atomic_inc(&resume_failures);
	}
}

static void kd_acquired_wait(unsigned int stage)
{
	unsigned long deadline = jiffies + 5 * HZ;
	bool ready;

	/* A failed schedule must release its holders, not strand kernel callers
	 * behind an observation loop. It remains a failed test after draining. */
	do {
		switch (stage) {
		case 0:
			ready = atomic_read(&inner_holder_ready) &&
				atomic_read(&outer_holder_ready) &&
				atomic_read(&outer_direct_waiting) == 2 &&
				kd_spin_debug_waiter_count(
					&nested_lock_a.rlock) >= 1;
			break;
		case 1:
			ready = kd_spin_debug_waiter_count(
					&nested_lock_b.rlock) == 2;
			break;
		case 2:
			ready = READ_ONCE(acquired_record) &&
				kd_spin_debug_waiter_count(
					&nested_lock_b.rlock) == 1;
			break;
		case 3:
			ready = atomic_read(&outer_direct_waiting) == 2 &&
				atomic_read(&outer_nested_waiting) &&
				atomic_read(&outer_trailing_waiting) &&
				kd_spin_debug_waiter_count(
					&nested_lock_a.rlock) >= 3;
			break;
		case 4:
			ready = atomic_read(&outer_holder_ready);
			break;
		case 8:
			ready = atomic_read(&outer_nested_waiting) &&
				kd_spin_debug_waiter_count(
					&nested_lock_a.rlock) >= 2;
			break;
		default:
			ready = false;
		}
		if (ready)
			return;
		cpu_relax();
	} while (time_before(jiffies, deadline));
	kd_acquired_check(false);
	pr_err("kd_acquired timeout: task=%d stage=%u\n", current->pid, stage);
}

static noinline void kd_acquired_spin_prepare(struct kd_resume_record *record,
					      unsigned int role)
{
	if (!native_acquired_queue || !(role & MODE_ROLE_SYNCHRONIZED))
		return;
	kd_acquired_wait(0);
	kd_acquired_check(record && !acquired_prepared);
	WRITE_ONCE(acquired_prepared, acquired_prepared + 1);
	smp_store_release(&acquired_record, record);
	atomic_set(&outer_nested_waiting, 1);
	smp_mb__after_atomic();
}

static noinline void kd_acquired_spin_observe(struct kd_resume_record *record)
{
	unsigned long a = kd_spin_debug_owner(&nested_lock_a.rlock);
	unsigned long b = kd_spin_debug_owner(&nested_lock_b.rlock);
	bool valid = record && record == acquired_record &&
		     record->task == current &&
		     READ_ONCE(acquired_prefix) == 1 && !acquired_suffix &&
		     READ_ONCE(acquired_queued) == 1 && a && a == b &&
		     a != (unsigned long)current &&
		     kd_test_spin_origin_locked(
			     atomic_read(&nested_lock_a.rlock.raw_lock.val)) &&
		     kd_test_spin_origin_locked(
			     atomic_read(&nested_lock_b.rlock.raw_lock.val));

	WRITE_ONCE(acquired_suffix, acquired_suffix + 1);
	kd_acquired_check(valid);
	pr_info("kd_acquired resumed: task=%d cpu=%u waiter=%lx a_owner=%lx b_owner=%lx prefix=%u suffix=%u valid=%u\n",
		current->pid, raw_smp_processor_id(), (unsigned long)current, a,
		b, READ_ONCE(acquired_prefix), acquired_suffix, valid);
}

static noinline void kd_acquired_spin_finish(struct kd_resume_record *record)
{
	kd_acquired_check(record && record == acquired_record &&
			  record->task == current && acquired_prefix == 1 &&
			  acquired_suffix == 1 && !acquired_completed);
	WRITE_ONCE(acquired_completed, acquired_completed + 1);
	pr_info("kd_acquired finish: task=%d prefix=%u suffix=%u completed=%u\n",
		current->pid, acquired_prefix, acquired_suffix,
		acquired_completed);
}

static noinline void kd_acquired_spin_role(unsigned int role)
{
	unsigned int count = preempt_count();
	bool irq = irqs_disabled();

	if (role == 1) {
		struct kd_resume_record *record;
		unsigned long a, b;
		bool valid;

		spin_lock(&nested_lock_b);
		atomic_set(&inner_holder_ready, 1);
		smp_mb__after_atomic();
		kd_acquired_wait(1);
		record = smp_load_acquire(&acquired_record);
		a = kd_spin_debug_owner(&nested_lock_a.rlock);
		b = kd_spin_debug_owner(&nested_lock_b.rlock);
		valid = record && a && a != (unsigned long)current &&
			b == (unsigned long)current &&
			READ_ONCE(acquired_prefix) == 1 &&
			!READ_ONCE(acquired_suffix) &&
			!READ_ONCE(acquired_completed) &&
			(kd_spin_debug_word(&nested_lock_a.rlock) & 0xff) ==
				3 &&
			kd_spin_debug_waiter_count(&nested_lock_b.rlock) == 2;
		kd_acquired_check(valid);
		WRITE_ONCE(acquired_queued, acquired_queued + 1);
		pr_info("kd_acquired queued: task=%d holder=%d cpu=%u a_owner=%lx b_owner=%lx prefix=%u waiters=%d valid=%u\n",
			record ? record->task->pid : 0, current->pid,
			raw_smp_processor_id(), a, b,
			READ_ONCE(acquired_prefix),
			kd_spin_debug_waiter_count(&nested_lock_b.rlock),
			valid);
		kd_cs_step(KD_CS_SPIN_B);
		spin_unlock(&nested_lock_b);
	} else if (role == 2) {
		bool valid;

		kd_acquired_wait(2);
		spin_lock(&nested_lock_b);
		valid = READ_ONCE(acquired_queued) == 1 &&
			READ_ONCE(acquired_suffix) == 1 &&
			kd_spin_debug_owner(&nested_lock_b.rlock) ==
				(unsigned long)current;
		kd_acquired_check(valid);
		WRITE_ONCE(acquired_trailer, acquired_trailer + 1);
		pr_info("kd_acquired trailer: task=%d cpu=%u owner=%lx prefix=%u suffix=%u valid=%u\n",
			current->pid, raw_smp_processor_id(),
			(unsigned long)current, READ_ONCE(acquired_prefix),
			READ_ONCE(acquired_suffix), valid);
		kd_cs_step(KD_CS_SPIN_B);
		spin_unlock(&nested_lock_b);
	} else if (role == 3) {
		spin_lock(&nested_lock_a);
		atomic_set(&outer_holder_ready, 1);
		smp_mb__after_atomic();
		kd_acquired_wait(3);
		kd_cs_step(KD_CS_SPIN_A);
		spin_unlock(&nested_lock_a);
	} else if (role == 4 || role == 6 || role == 8) {
		kd_acquired_wait(role == 8 ? 8 : 4);
		if (role == 8)
			atomic_set(&outer_trailing_waiting, 1);
		else
			atomic_inc(&outer_direct_waiting);
		smp_mb__after_atomic();
		spin_lock(&nested_lock_a);
		kd_cs_step(KD_CS_SPIN_A);
		spin_unlock(&nested_lock_a);
	} else {
		kd_acquired_check(false);
	}
	kd_spin_check_context(count, irq);
	pr_info("kd_acquired role: role=%u task=%d cpu=%u\n", role,
		current->pid, raw_smp_processor_id());
}

static void kd_acquired_spin_report(void)
{
	if (!native_acquired_queue)
		return;
	pr_info("kd_acquired stats: prepared=%u prefix=%u suffix=%u completed=%u queued=%u trailer=%u failures=%d\n",
		acquired_prepared, acquired_prefix, acquired_suffix,
		acquired_completed, acquired_queued, acquired_trailer,
		atomic_read(&acquired_failures));
}
