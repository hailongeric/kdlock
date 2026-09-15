// SPDX-License-Identifier: GPL-2.0
/* Shared L exclusion oracle; alternate APIs stay outside the JIT entry CFG. */
static atomic_t spin_inside = ATOMIC_INIT(0);
static atomic_t spin_overlaps = ATOMIC_INIT(0);
static atomic_t spin_origin_missing = ATOMIC_INIT(0);
static atomic_t spin_context_failures = ATOMIC_INIT(0);
static unsigned long spin_native_operations[4];

static __always_inline void kd_spin_oracle_enter(void)
{
	if (atomic_inc_return(&spin_inside) != 1)
		atomic_inc(&spin_overlaps);
	if (!raw_spin_is_locked(&global_lock.rlock))
		atomic_inc(&spin_origin_missing);
}

static __attribute__((noipa)) noinline void
kd_spin_check_context(unsigned int count, bool irq)
{
	if (preempt_count() != count || irqs_disabled() != irq)
		atomic_inc(&spin_context_failures);
}

static __attribute__((noipa)) noinline void
run_native_spin_contention_test(unsigned long loops, unsigned long work,
				unsigned int api)
{
	unsigned long i, j, flags = 0;
	unsigned int count = preempt_count();
	bool irq = irqs_disabled();
	volatile int dummy = 0;

	for (i = 0; i < loops; i++) {
		switch (api) {
		case 1:
			spin_lock_irqsave(&global_lock, flags);
			break;
		case 2:
			spin_lock_bh(&global_lock);
			break;
		default:
			while (!spin_trylock(&global_lock))
				cpu_relax();
		}
		kd_spin_oracle_enter();
		spin_native_operations[api]++;
		kd_cs_step(KD_CS_SPIN_GLOBAL);
		for (j = 0; j < work; j++)
			dummy++;
		atomic_dec(&spin_inside);
		switch (api) {
		case 1:
			spin_unlock_irqrestore(&global_lock, flags);
			break;
		case 2:
			spin_unlock_bh(&global_lock);
			break;
		default:
			spin_unlock(&global_lock);
		}
		kd_spin_check_context(count, irq);
	}
}

static void kd_spin_oracle_report(void)
{
	pr_info("kd_spin oracle: inside=%d overlaps=%d origin_missing=%d context_failures=%d irqsave=%lu bh=%lu trylock=%lu\n",
		atomic_read(&spin_inside), atomic_read(&spin_overlaps),
		atomic_read(&spin_origin_missing),
		atomic_read(&spin_context_failures), spin_native_operations[1],
		spin_native_operations[2], spin_native_operations[3]);
}
