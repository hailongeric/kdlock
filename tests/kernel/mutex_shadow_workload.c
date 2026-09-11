// SPDX-License-Identifier: GPL-2.0
/* Join shadow-table exhaustion to the existing two real native frames.
 * These locks are acquired through hooks after test-controlled promotion;
 * cold filler sites do not execute JIT or acquire a delegated frame.
 */
#define KD_SHADOW_CAPACITY_LOCKS 1025
static struct mutex kd_shadow_capacity_locks[KD_SHADOW_CAPACITY_LOCKS];
static unsigned long kd_shadow_capacity_values[KD_SHADOW_CAPACITY_LOCKS];
static unsigned int kd_shadow_capacity_updates[KD_SHADOW_CAPACITY_LOCKS];
static struct task_struct *kd_shadow_capacity_tasks[2];
static atomic_t kd_shadow_capacity_claimed = ATOMIC_INIT(0);
static bool kd_shadow_capacity_filled, kd_shadow_capacity_ready;

static void kd_shadow_capacity_init(void)
{
	unsigned int i;

	if (!mutex_parallel_shadow)
		return;
	for (i = 0; i < KD_SHADOW_CAPACITY_LOCKS; i++) {
		mutex_init(&kd_shadow_capacity_locks[i]);
		kd_shadow_capacity_values[i] = i + 7;
	}
	pr_info("kd_parallel shadow layout: base=%lx stride=%zu count=%u\n",
		(unsigned long)kd_shadow_capacity_locks, sizeof(struct mutex),
		KD_SHADOW_CAPACITY_LOCKS);
}

static bool kd_shadow_capacity_wait(struct mutex *lock)
{
	unsigned long deadline = jiffies + 5 * HZ;

	for (;;) {
		unsigned long flags;
		struct mutex_waiter *waiter;
		unsigned int count = 0, matched = 0;

		if (!lock && smp_load_acquire(&kd_shadow_capacity_ready))
			return true;
		if (lock) {
			/* Two actual Linux waiters, not flags set before mutex_lock.
			 * Their tasks remain alive here because this caller owns L. */
			raw_spin_lock_irqsave(&lock->wait_lock, flags);
			list_for_each_entry(waiter, &lock->wait_list, list) {
				count++;
				if (waiter->task ==
				    READ_ONCE(kd_shadow_capacity_tasks[0]))
					matched |= 1;
				if (waiter->task ==
				    READ_ONCE(kd_shadow_capacity_tasks[1]))
					matched |= 2;
			}
			raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
			if (count == 2 && matched == 3) {
				pr_info("kd_parallel shadow queued: task=%d owner=%lx lock=%lx count=%u matched=%u\n",
					current->pid, (unsigned long)current,
					(unsigned long)lock, count, matched);
				return true;
			}
		}
		if (time_after_eq(jiffies, deadline))
			return kd_parallel_check(false, 2,
						 "shadow-capacity-timeout");
		usleep_range(100, 200);
	}
}

static __attribute__((noipa)) noinline void
kd_shadow_capacity_acquire(unsigned int index, unsigned int role)
{
	struct mutex *lock = &kd_shadow_capacity_locks[index];
	unsigned long value, owner;
	unsigned int updates;
	int present;
	bool valid;

	mutex_lock(lock);
	owner = kd_test_mutex_owner(lock);
	present = kd_mutex_debug_waiter_count(lock);
	valid = owner == (unsigned long)current && !preempt_count() &&
		!irqs_disabled() && (present == 0 || present == -ENOENT);
	if (role) {
		valid &= present == -ENOENT;
		if (role == 1) {
			smp_store_release(&kd_shadow_capacity_ready, true);
			valid &= kd_shadow_capacity_wait(lock);
		}
	}
	updates = ++kd_shadow_capacity_updates[index];
	value = kd_shadow_capacity_values[index] * 33 + index + 1;
	kd_shadow_capacity_values[index] = value;
	kd_parallel_check(valid, 2, "shadow-capacity-owner");
	mutex_unlock(lock);
	/* Capture protected values before unlock; another native caller may now
	 * update the same slot. No saved task pointer is dereferenced after exit. */
	pr_info("kd_parallel shadow record: role=%u index=%u task=%d waiter=%lx owner=%lx lock=%lx registered=%u updates=%u value=%lx valid=%u\n",
		role, index, current->pid, (unsigned long)current, owner,
		(unsigned long)lock, present == 0, updates, value, valid);
}

/* Selector 25 fills with real sequential acquisitions. 26 is a non-target
 * native holder; 27/28 are target callers whose shadows cannot be allocated.
 * All four roles finish before either of the original native frames resumes.
 */
static int kd_shadow_capacity_run(unsigned long loops, unsigned int role)
{
	unsigned int i;
	bool native = !strcmp(current->comm, "kd_native");

	if (!mutex_parallel_shadow || !mutex_parallel_armed || role > 3 ||
	    loops != 1 || !READ_ONCE(mutex_parallel_source_hold) ||
	    atomic_read_acquire(&parallel_arrived) != 3 ||
	    atomic_read(&parallel_done) || (role == 1) != native ||
	    (role && !smp_load_acquire(&kd_shadow_capacity_filled)))
		return -EINVAL;
	if (atomic_fetch_or(BIT(role), &kd_shadow_capacity_claimed) & BIT(role))
		return -EALREADY;
	if (!role) {
		for (i = 0; i < KD_SHADOW_CAPACITY_LOCKS; i++)
			kd_shadow_capacity_acquire(i, role);
		smp_store_release(&kd_shadow_capacity_filled, true);
	} else {
		if (role >= 2) {
			WRITE_ONCE(kd_shadow_capacity_tasks[role - 2], current);
			if (!kd_shadow_capacity_wait(NULL))
				return -EINVAL;
		}
		kd_shadow_capacity_acquire(KD_SHADOW_CAPACITY_LOCKS - 1, role);
	}
	return atomic_read(&parallel_failures) ? -EINVAL : 0;
}
