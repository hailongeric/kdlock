// SPDX-License-Identifier: GPL-2.0
/* Hold genuine hook acquisitions across A's combiner work. Each candidate
 * uses different locks, so these 31 tickets cannot serialize the A queue.
 * Promotion is controlled by the recovery script; pool state is never set.
 */
#define KD_TICKET_HELD 31
static bool native_ticket_pressure;
module_param(native_ticket_pressure, bool, 0444);
MODULE_PARM_DESC(native_ticket_pressure,
		 "Mode 8 stage 4: retain 31 physical locks on each A candidate");
static spinlock_t kd_ticket_locks[2][KD_TICKET_HELD];
static struct lock_class_key kd_ticket_keys[2][KD_TICKET_HELD];
static unsigned int kd_ticket_baseline[2];
static unsigned int kd_ticket_completed[2];

static int kd_ticket_init(void)
{
	unsigned int side, i;

	if (!native_ticket_pressure)
		return 0;
	if (native_resume_stage != 4 || !native_pending_contended ||
	    native_resume_registers || native_waiter_signal ||
	    native_stack_change)
		return -EINVAL;
	for (side = 0; side < 2; side++) {
		for (i = 0; i < KD_TICKET_HELD; i++) {
			spin_lock_init(&kd_ticket_locks[side][i]);
			lockdep_set_class(&kd_ticket_locks[side][i],
					  &kd_ticket_keys[side][i]);
			pr_info("kd_ticket lock: cpu=%u index=%u lock=%lx\n",
				4 + side * 2, i,
				(unsigned long)&kd_ticket_locks[side][i]);
		}
	}
	return 0;
}

static noinline void kd_ticket_hold(bool synchronized, bool acquire)
{
	unsigned int cpu, side, i, owned = 0;
	bool valid;

	if (!native_ticket_pressure || !synchronized)
		return;
	cpu = raw_smp_processor_id();
	if (cpu != 4 && cpu != 6) {
		atomic_inc(&resume_failures);
		return;
	}
	side = (cpu - 4) / 2;
	if (acquire) {
		kd_ticket_baseline[side] = preempt_count();
		for (i = 0; i < KD_TICKET_HELD; i++)
			spin_lock(&kd_ticket_locks[side][i]);
	}
	/* Observe real gate owners and public/private words, not only a loop
	 * counter. A has not been acquired yet, or has already been released.
	 */
	for (i = 0; i < KD_TICKET_HELD; i++) {
		raw_spinlock_t *lock = &kd_ticket_locks[side][i].rlock;

		if (kd_spin_debug_owner(lock) == (unsigned long)current &&
		    kd_spin_debug_word(lock) == 1 &&
		    atomic_read(&lock->raw_lock.val) == _Q_LOCKED_VAL)
			owned++;
	}
	valid = owned == KD_TICKET_HELD && !irqs_disabled() &&
		preempt_count() == kd_ticket_baseline[side] + KD_TICKET_HELD;
	if (!valid)
		atomic_inc(&resume_failures);
	pr_info("kd_ticket held: task=%d cpu=%u acquire=%u owned=%u pins=%u valid=%u\n",
		current->pid, cpu, acquire, owned,
		preempt_count() - kd_ticket_baseline[side], valid);
	if (acquire)
		return;
	/* Release only these fixture locks, after A's complete queue/native ACK
	 * lifecycle. This does not release A or change its physical owner.
	 */
	for (i = KD_TICKET_HELD; i > 0; i--)
		spin_unlock(&kd_ticket_locks[side][i - 1]);
	valid = preempt_count() == kd_ticket_baseline[side];
	for (i = 0; i < KD_TICKET_HELD; i++) {
		raw_spinlock_t *lock = &kd_ticket_locks[side][i].rlock;

		valid &= !kd_spin_debug_owner(lock) &&
			 !kd_spin_debug_word(lock) &&
			 !atomic_read(&lock->raw_lock.val);
	}
	if (!valid || kd_ticket_completed[side]++)
		atomic_inc(&resume_failures);
	pr_info("kd_ticket released: task=%d cpu=%u locks=%u pins=%u valid=%u\n",
		current->pid, cpu, KD_TICKET_HELD,
		preempt_count() - kd_ticket_baseline[side], valid);
}

static void kd_ticket_report(void)
{
	if (!native_ticket_pressure)
		return;
	if (kd_ticket_completed[0] != 1 || kd_ticket_completed[1] != 1)
		atomic_inc(&resume_failures);
	pr_info("kd_ticket stats: completed=%u,%u locks=%u\n",
		kd_ticket_completed[0], kd_ticket_completed[1], KD_TICKET_HELD);
}
