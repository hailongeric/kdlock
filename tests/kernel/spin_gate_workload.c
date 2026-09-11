// SPDX-License-Identifier: GPL-2.0
/* Extend the existing real ticket refusal while its native waiter retains A.
 * Independent hook acquisitions fill the gate map; a fresh native L still
 * excludes target callers whose gate allocation fails. No owner is handed off.
 */
#define KD_GATE_CAPACITY_LOCKS 1025
static bool native_gate_pressure, native_gate_release;
static unsigned int native_gate_phase;
module_param(native_gate_pressure, bool, 0444);
module_param(native_gate_release, bool, 0600);
module_param(native_gate_phase, uint, 0444);
MODULE_PARM_DESC(
	native_gate_pressure,
	"Mode 8 ticket pressure: hold B across independent gate-map pressure");
MODULE_PARM_DESC(
	native_gate_release,
	"Release the observed B holder after gate-pressure callers drain");
MODULE_PARM_DESC(
	native_gate_phase,
	"Read-only gate-pressure phase: 0 initial, 1 B held, 2 B resuming");
static spinlock_t kd_gate_capacity_locks[KD_GATE_CAPACITY_LOCKS];
static unsigned long kd_gate_capacity_values[KD_GATE_CAPACITY_LOCKS];
static unsigned int kd_gate_capacity_updates[KD_GATE_CAPACITY_LOCKS];
static atomic_t kd_gate_capacity_claimed = ATOMIC_INIT(0);
static bool kd_gate_capacity_filled, kd_gate_capacity_ready;

static bool kd_gate_capacity_check(bool valid)
{
	if (!valid)
		atomic_inc(&resume_failures);
	return valid;
}

static int kd_gate_capacity_init(void)
{
	unsigned int i;

	if (native_gate_phase || native_gate_release ||
	    (native_gate_pressure && !native_ticket_pressure))
		return -EINVAL;
	if (!native_gate_pressure)
		return 0;
	for (i = 0; i < KD_GATE_CAPACITY_LOCKS; i++) {
		spin_lock_init(&kd_gate_capacity_locks[i]);
		kd_gate_capacity_values[i] = i + 7;
	}
	pr_info("kd_gate layout: base=%lx stride=%zu count=%u\n",
		(unsigned long)kd_gate_capacity_locks, sizeof(spinlock_t),
		KD_GATE_CAPACITY_LOCKS);
	return 0;
}

static noinline void kd_gate_capacity_hold(void)
{
	unsigned long deadline, a, b;
	bool valid;

	if (!native_gate_pressure)
		return;
	a = kd_spin_debug_owner(&nested_lock_a.rlock);
	b = kd_spin_debug_owner(&nested_lock_b.rlock);
	valid = a && a != b && b == (unsigned long)current &&
		smp_load_acquire(&pending_spin_observed) &&
		!READ_ONCE(pending_spin_acquired);
	kd_gate_capacity_check(valid);
	pr_info("kd_gate hold: task=%d cpu=%u a=%lx b=%lx valid=%u\n",
		current->pid, raw_smp_processor_id(), a, b, valid);
	smp_store_release(&native_gate_phase, 1);
	deadline = jiffies + 20 * HZ;
	while (!smp_load_acquire(&native_gate_release)) {
		if (time_after_eq(jiffies, deadline)) {
			kd_gate_capacity_check(false);
			pr_err("kd_gate timeout: pressure callers did not drain\n");
			break;
		}
		cpu_relax();
	}
	valid &= a == kd_spin_debug_owner(&nested_lock_a.rlock) &&
		 b == kd_spin_debug_owner(&nested_lock_b.rlock) &&
		 !READ_ONCE(pending_spin_acquired);
	kd_gate_capacity_check(valid);
	pr_info("kd_gate resume: task=%d cpu=%u a=%lx b=%lx valid=%u\n",
		current->pid, raw_smp_processor_id(), a, b, valid);
	smp_store_release(&native_gate_phase, 2);
}

static bool kd_gate_capacity_wait(spinlock_t *lock)
{
	unsigned long deadline = jiffies + 5 * HZ;

	for (;;) {
		if (!lock && smp_load_acquire(&kd_gate_capacity_ready))
			return true;
		if (lock) {
			u32 value =
				atomic_read_acquire(&lock->rlock.raw_lock.val);

			/* Only one other caller can touch this fresh lock. Observe its
			 * Linux pending/tail publication, not a pre-CALL arrival flag. */
			if (value & (_Q_PENDING_MASK | _Q_TAIL_MASK)) {
				pr_info("kd_gate queued: task=%d cpu=%u lock=%lx value=%x\n",
					current->pid, raw_smp_processor_id(),
					(unsigned long)lock, value);
				return true;
			}
		}
		if (time_after_eq(jiffies, deadline)) {
			pr_err("kd_gate timeout: native queue did not progress\n");
			return kd_gate_capacity_check(false);
		}
		cpu_relax();
	}
}

static __attribute__((noipa)) noinline void
kd_gate_capacity_acquire(unsigned int index, unsigned int role)
{
	spinlock_t *lock = &kd_gate_capacity_locks[index];
	unsigned long owner, value;
	unsigned int updates, pins = preempt_count();
	bool present, valid;

	spin_lock(lock);
	owner = kd_spin_debug_owner(&lock->rlock);
	present = owner == (unsigned long)current;
	valid = (present || !owner) && preempt_count() == pins + 1 &&
		!irqs_disabled() &&
		kd_spin_debug_word(&lock->rlock) == (present ? 1 : 0) &&
		kd_test_spin_origin_locked(
			atomic_read(&lock->rlock.raw_lock.val));
	if (role) {
		valid &= !present;
		if (role == 1) {
			smp_store_release(&kd_gate_capacity_ready, true);
			valid &= kd_gate_capacity_wait(lock);
		}
	}
	updates = ++kd_gate_capacity_updates[index];
	value = kd_gate_capacity_values[index] * 33 + index + 1;
	kd_gate_capacity_values[index] = value;
	kd_gate_capacity_check(valid);
	spin_unlock(lock);
	valid &= preempt_count() == pins;
	kd_gate_capacity_check(valid);
	/* Values belong to this completed critical section, not a reread after
	 * another caller can update them. Never retain/dereference an exited task. */
	pr_info("kd_gate record: role=%u index=%u task=%d cpu=%u lock=%lx registered=%u updates=%u value=%lx pins=%u valid=%u\n",
		role, index, current->pid, raw_smp_processor_id(),
		(unsigned long)lock, present, updates, value, preempt_count(),
		valid);
}

static int kd_gate_capacity_run(unsigned long loops, unsigned int role)
{
	unsigned int i;
	bool native = !strcmp(current->comm, "kd_native");

	if (!native_gate_pressure || role > 2 || loops != 1 ||
	    smp_load_acquire(&native_gate_phase) != 1 ||
	    READ_ONCE(native_gate_release) || (role == 1) != native ||
	    (role && !smp_load_acquire(&kd_gate_capacity_filled)))
		return -EINVAL;
	if (atomic_fetch_or(BIT(role), &kd_gate_capacity_claimed) & BIT(role))
		return -EALREADY;
	if (!role) {
		for (i = 0; i < KD_GATE_CAPACITY_LOCKS; i++)
			kd_gate_capacity_acquire(i, 0);
		smp_store_release(&kd_gate_capacity_filled, true);
	} else {
		if (role == 2 && !kd_gate_capacity_wait(NULL))
			return -EINVAL;
		kd_gate_capacity_acquire(KD_GATE_CAPACITY_LOCKS - 1, role);
	}
	return atomic_read(&resume_failures) ? -EINVAL : 0;
}

static void kd_gate_capacity_report(void)
{
	unsigned int i;
	bool valid;

	if (!native_gate_pressure)
		return;
	valid = atomic_read(&kd_gate_capacity_claimed) == 7 &&
		native_gate_phase == 2;
	for (i = 0; i < KD_GATE_CAPACITY_LOCKS; i++) {
		unsigned int n,
			expected = i == KD_GATE_CAPACITY_LOCKS - 1 ? 3 : 1;
		unsigned long value = i + 7;

		for (n = 0; n < expected; n++)
			value = value * 33 + i + 1;
		valid &= kd_gate_capacity_updates[i] == expected &&
			 kd_gate_capacity_values[i] == value &&
			 !atomic_read(
				 &kd_gate_capacity_locks[i].rlock.raw_lock.val);
	}
	kd_gate_capacity_check(valid);
	pr_info("kd_gate stats: locks=%u roles=%x phase=%u valid=%u\n",
		KD_GATE_CAPACITY_LOCKS, atomic_read(&kd_gate_capacity_claimed),
		native_gate_phase, valid);
}
