// SPDX-License-Identifier: GPL-2.0
/* Included by the parallel workload: exhaust the real code pool through lock
 * hooks, never by writing registry entries or changing the production limit.
 * The daemon is stopped; these cold sites are deliberately NOT JIT positives. */
static DEFINE_MUTEX(kd_pool_lock);
static atomic_t kd_pool_claimed = ATOMIC_INIT(0);
static atomic_t kd_pool_ready = ATOMIC_INIT(0);
static unsigned long kd_pool_updates;
static unsigned int kd_pool_warm, kd_pool_filled;

struct kd_pool_record {
	unsigned long value, waiter, owner;
	unsigned int updates;
	pid_t task;
};

/* Keep independent lexical mutex CALL sites even under compiler ICF/IPA.
 * Their loaded ELF relocations, not these ordinal numbers, identify registry
 * keys. Sixty-four new sites exhaust a pool already used by the two images. */
/* clang-format off */
#define KD_POOL_SITES(X)                                                  \
	X(0) X(1) X(2) X(3) X(4) X(5) X(6) X(7)                          \
	X(8) X(9) X(10) X(11) X(12) X(13) X(14) X(15)                     \
	X(16) X(17) X(18) X(19) X(20) X(21) X(22) X(23)                   \
	X(24) X(25) X(26) X(27) X(28) X(29) X(30) X(31)                   \
	X(32) X(33) X(34) X(35) X(36) X(37) X(38) X(39)                   \
	X(40) X(41) X(42) X(43) X(44) X(45) X(46) X(47)                   \
	X(48) X(49) X(50) X(51) X(52) X(53) X(54) X(55)                   \
	X(56) X(57) X(58) X(59) X(60) X(61) X(62) X(63)
/* clang-format on */

static void kd_pool_observe(struct kd_pool_record *record)
{
	record->owner = kd_test_mutex_owner(&kd_pool_lock);
	kd_parallel_check(record->owner == record->waiter &&
				  record->waiter == (unsigned long)current &&
				  !preempt_count() && !irqs_disabled(),
			  2, "code-pool-owner");
	kd_pool_updates++;
}

#define KD_POOL_SITE(number)                                               \
	static __attribute__((noipa)) noinline void kd_pool_site_##number( \
		struct kd_pool_record *record)                             \
	{                                                                  \
		mutex_lock(&kd_pool_lock);                                 \
		record->updates++;                                         \
		record->value = record->value * 33 + (number) + 1;         \
		kd_pool_observe(record);                                   \
		mutex_unlock(&kd_pool_lock);                               \
	}
KD_POOL_SITES(KD_POOL_SITE)
#undef KD_POOL_SITE

#define KD_POOL_ADDRESS(number) kd_pool_site_##number,
static void (*const kd_pool_sites[])(struct kd_pool_record *) = {
	KD_POOL_SITES(KD_POOL_ADDRESS)
};
#undef KD_POOL_ADDRESS
#undef KD_POOL_SITES

static bool kd_pool_wait(unsigned int queued)
{
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		bool ready = queued ? kd_mutex_debug_waiter_count(
					      &kd_pool_lock) >= queued :
				      atomic_read_acquire(&kd_pool_ready);

		if (ready)
			return true;
		if (time_after_eq(jiffies, deadline))
			return kd_parallel_check(false, 2,
						 "code-pool-wait-timeout");
		usleep_range(100, 200);
	}
}

/* Selector 16 warms this independent lock after daemon shutdown; 17 fills
 * through the actual hooks while both earlier native frames remain paused.
 * 18..21 are a real holder and three ordered queue clients of the last site. */
static int kd_pool_run(unsigned long loops, unsigned int role)
{
	unsigned int count, i;

	if (mutex_parallel_shared_cpu || mutex_parallel_retired || role > 5 ||
	    !loops || loops > 20000 ||
	    (role == 0) == READ_ONCE(mutex_parallel_armed) ||
	    (role != 0 && loops != 1))
		return -EINVAL;
	if (atomic_fetch_or(BIT(role), &kd_pool_claimed) & BIT(role))
		return -EALREADY;
	if (role && (!READ_ONCE(mutex_parallel_source_hold) ||
		     atomic_read(&parallel_arrived) != 3 ||
		     atomic_read(&parallel_done)))
		return -EINVAL;
	if (role >= 2 && !smp_load_acquire(&kd_pool_filled))
		return -EINVAL;
	if (role == 2) {
		mutex_lock(&kd_pool_lock);
		atomic_set_release(&kd_pool_ready, 1);
		if (kd_pool_wait(3))
			pr_info("kd_parallel code queued: lock=%lx task=%d waiters=%d\n",
				(unsigned long)&kd_pool_lock, current->pid,
				kd_mutex_debug_waiter_count(&kd_pool_lock));
		mutex_unlock(&kd_pool_lock);
		return atomic_read(&parallel_failures) ? -EINVAL : 0;
	}
	if (role >= 3 &&
	    (!kd_pool_wait(0) || (role > 3 && !kd_pool_wait(role - 3))))
		return -EINVAL;
	count = role == 0 ? loops : role == 1 ? ARRAY_SIZE(kd_pool_sites) : 1;
	for (i = 0; i < count; i++) {
		unsigned int site = role == 0 ? 0 : role == 1 ? i : 63;
		unsigned long input = (role >= 3 ? role : site) + 7;
		struct kd_pool_record record = {
			.value = input,
			.waiter = (unsigned long)current,
			.task = current->pid,
		};
		bool valid;

		kd_pool_sites[site](&record);
		valid = record.updates == 1 && record.owner == record.waiter &&
			record.value == input * 33 + site + 1;
		kd_parallel_check(valid, 2, "code-pool-record");
		if (role)
			pr_info("kd_parallel code record: role=%u site=%u fn=%lx task=%d waiter=%lx owner=%lx lock=%lx updates=%u value=%lx valid=%u\n",
				role, site, (unsigned long)kd_pool_sites[site],
				record.task, record.waiter, record.owner,
				(unsigned long)&kd_pool_lock, record.updates,
				record.value, valid);
	}
	if (!role)
		WRITE_ONCE(kd_pool_warm, count);
	else if (role == 1)
		smp_store_release(&kd_pool_filled, count);
	return atomic_read(&parallel_failures) ? -EINVAL : 0;
}

static void kd_pool_report(void)
{
	if (!kd_pool_warm)
		return;
	pr_info("kd_parallel code stats: warm=%u filled=%u claimed=%u updates=%lu lock=%lx\n",
		kd_pool_warm, kd_pool_filled, atomic_read(&kd_pool_claimed),
		kd_pool_updates, kd_test_mutex_owner(&kd_pool_lock));
}
