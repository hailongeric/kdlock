// SPDX-License-Identifier: GPL-2.0
/* Mode 8 only. Arm after promotion; all observers execute on original stacks. */
static unsigned int remote_spin_ooo;
module_param(remote_spin_ooo, uint, 0644);
MODULE_PARM_DESC(
	remote_spin_ooo,
	"Mode 8: 1=JIT, 2=native before ancestors, 3=after ancestors, 4=between deep ancestors");
static bool remote_spin_native_owner;
module_param(remote_spin_native_owner, bool, 0644);
static bool remote_spin_deep, remote_spin_reverse;
module_param(remote_spin_deep, bool, 0644);
module_param(remote_spin_reverse, bool, 0644);
static DEFINE_SPINLOCK(remote_lock_d);
static struct task_struct *remote_ooo_waiter;
static unsigned int remote_ooo_origin_cpu;
static unsigned int remote_ooo_prefix, remote_ooo_suffix, remote_ooo_observed;
static bool remote_ooo_c_ready;
static atomic_t remote_c_holder = ATOMIC_INIT(0);
static atomic_t remote_c_direct = ATOMIC_INIT(0);
static atomic_t remote_c_nested = ATOMIC_INIT(0);
static atomic_t remote_c_trailing = ATOMIC_INIT(0);

static void kd_remote_chain_observe(void)
{
	struct task_struct *waiter = READ_ONCE(remote_ooo_waiter);
	u32 a = atomic_read(&nested_lock_a.rlock.raw_lock.val);
	u32 b = atomic_read(&nested_lock_b.rlock.raw_lock.val);
	u32 c = atomic_read(&nested_lock_c.rlock.raw_lock.val);
	u32 d = atomic_read(&remote_lock_d.rlock.raw_lock.val);
	unsigned long a_owner = kd_spin_debug_owner(&nested_lock_a.rlock);
	unsigned long b_owner = kd_spin_debug_owner(&nested_lock_b.rlock);
	unsigned long c_owner = kd_spin_debug_owner(&nested_lock_c.rlock);
	bool valid = waiter && waiter != current && c_owner &&
		     c_owner != (unsigned long)waiter &&
		     c_owner != (unsigned long)current &&
		     kd_test_spin_origin_locked(a) &&
		     kd_test_spin_origin_locked(b) &&
		     kd_test_spin_origin_locked(c) &&
		     kd_test_spin_origin_locked(d) && preempt_count() == 3 &&
		     !irqs_disabled() && READ_ONCE(remote_ooo_prefix) == 1 &&
		     !READ_ONCE(remote_ooo_suffix) && !remote_ooo_observed;

	if (!remote_spin_native_owner)
		valid &= a_owner == (unsigned long)current &&
			 b_owner == (unsigned long)current;
	if (!valid)
		atomic_inc(&resume_failures);
	pr_info("kd_chain observe: task=%d cpu=%u origin_cpu=%u owner_task=%lx waiter=%lx waiter_pid=%d a=%lx b=%lx c=%lx d=%lx a_word=%x b_word=%x c_word=%x d_word=%x a_owner=%lx b_owner=%lx c_owner=%lx preempt=%u irq=%u prefix=%u suffix=%u valid=%u comm=%s\n",
		current->pid, raw_smp_processor_id(),
		READ_ONCE(remote_ooo_origin_cpu), (unsigned long)current,
		(unsigned long)waiter, waiter ? waiter->pid : 0,
		(unsigned long)&nested_lock_a, (unsigned long)&nested_lock_b,
		(unsigned long)&nested_lock_c, (unsigned long)&remote_lock_d, a,
		b, c, d, a_owner, b_owner, c_owner, preempt_count(),
		irqs_disabled(), READ_ONCE(remote_ooo_prefix),
		READ_ONCE(remote_ooo_suffix), valid, current->comm);
	remote_ooo_observed++;
}

static noinline void kd_remote_c_prepare(void)
{
	while (!atomic_read(&remote_c_holder) ||
	       atomic_read(&remote_c_direct) < 2)
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_c.rlock) < 1)
		cpu_relax();
}

/* C gets its own real pending/head/virtual/trailing queue, not a third
 * locally held lock in B's frame. Warmup uses the same direct CALL site. */
static noinline void kd_remote_c_direct_prepare(bool synchronized)
{
	if (!synchronized)
		return;
	while (!atomic_read(&remote_c_holder))
		cpu_relax();
	atomic_inc(&remote_c_direct);
	smp_mb__after_atomic();
}

static noinline void kd_remote_c_direct_role(unsigned long work_load,
					     bool synchronized)
{
	volatile int dummy = 0;
	unsigned long j;

	kd_remote_c_direct_prepare(synchronized);
	spin_lock(&nested_lock_c);
	kd_cs_step(KD_CS_SPIN_C);
	for (j = 0; j < work_load; j++)
		dummy++;
	spin_unlock(&nested_lock_c);
}

static noinline void kd_remote_c_holder_role(void)
{
	atomic_set(&remote_c_holder, 0);
	atomic_set(&remote_c_direct, 0);
	atomic_set(&remote_c_nested, 0);
	atomic_set(&remote_c_trailing, 0);
	spin_lock(&nested_lock_c);
	atomic_set(&remote_c_holder, 1);
	smp_mb__after_atomic();
	while (atomic_read(&remote_c_direct) < 2 ||
	       !atomic_read(&remote_c_nested) ||
	       !atomic_read(&remote_c_trailing))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_c.rlock) < 3)
		cpu_relax();
	kd_cs_step(KD_CS_SPIN_C);
	spin_unlock(&nested_lock_c);
}

static noinline void kd_remote_c_trailing_role(void)
{
	while (!atomic_read(&remote_c_nested))
		cpu_relax();
	while (kd_spin_debug_waiter_count(&nested_lock_c.rlock) < 2)
		cpu_relax();
	atomic_set(&remote_c_trailing, 1);
	smp_mb__after_atomic();
	spin_lock(&nested_lock_c);
	kd_cs_step(KD_CS_SPIN_C);
	spin_unlock(&nested_lock_c);
}

static void kd_remote_ooo_observe(void)
{
	struct task_struct *waiter = READ_ONCE(remote_ooo_waiter);
	u32 a = atomic_read(&nested_lock_a.rlock.raw_lock.val);
	u32 b = atomic_read(&nested_lock_b.rlock.raw_lock.val);
	u32 c = atomic_read(&nested_lock_c.rlock.raw_lock.val);
	unsigned long a_owner = kd_spin_debug_owner(&nested_lock_a.rlock);
	unsigned long b_owner = kd_spin_debug_owner(&nested_lock_b.rlock);
	bool valid = waiter && waiter != current && b_owner &&
		     b_owner != (unsigned long)waiter &&
		     b_owner != (unsigned long)current &&
		     kd_test_spin_origin_locked(a) &&
		     kd_test_spin_origin_locked(b) &&
		     kd_test_spin_origin_locked(c) && preempt_count() == 2 &&
		     !irqs_disabled() && READ_ONCE(remote_ooo_prefix) == 1 &&
		     !READ_ONCE(remote_ooo_suffix) && !remote_ooo_observed;

	if (!remote_spin_native_owner)
		valid &= a_owner == (unsigned long)current;
	if (!valid)
		atomic_inc(&resume_failures);
	pr_info("kd_remote observe: task=%d cpu=%u origin_cpu=%u waiter=%lx waiter_pid=%d outer=%lx inner=%lx child=%lx a_word=%x b_word=%x c_word=%x a_owner=%lx b_owner=%lx preempt=%u irq=%u prefix=%u suffix=%u valid=%u comm=%s\n",
		current->pid, raw_smp_processor_id(),
		READ_ONCE(remote_ooo_origin_cpu), (unsigned long)waiter,
		waiter ? waiter->pid : 0, (unsigned long)&nested_lock_a,
		(unsigned long)&nested_lock_b, (unsigned long)&nested_lock_c, a,
		b, c, a_owner, b_owner, preempt_count(), irqs_disabled(),
		READ_ONCE(remote_ooo_prefix), READ_ONCE(remote_ooo_suffix),
		valid, current->comm);
	remote_ooo_observed++;
}

static noinline void kd_remote_ooo_native_owner(void)
{
	unsigned long deadline = jiffies + 10 * HZ;
	spinlock_t *dependency = remote_spin_deep ? &remote_lock_d :
						    &nested_lock_c;

	if (!remote_spin_ooo || !remote_spin_native_owner)
		return;
	spin_lock(dependency);
	smp_store_release(&remote_ooo_c_ready, true);
	while (!READ_ONCE(remote_ooo_prefix)) {
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&resume_failures);
			pr_err("kd_remote C owner: prefix timed out\n");
			spin_unlock(dependency);
			return;
		}
		cpu_relax();
	}
	spin_lock(&nested_lock_a);
	if (remote_spin_deep) {
		spin_lock(&nested_lock_b);
		kd_remote_chain_observe();
		kd_cs_step(KD_CS_SPIN_B);
		spin_unlock(&nested_lock_b);
	} else {
		kd_remote_ooo_observe();
	}
	kd_cs_step(KD_CS_SPIN_A);
	spin_unlock(&nested_lock_a);
	spin_unlock(dependency);
}

static void kd_remote_ooo_report(void)
{
	if (!remote_spin_ooo)
		return;
	if (remote_ooo_prefix != 1 || remote_ooo_suffix != 1 ||
	    remote_ooo_observed != 1)
		atomic_inc(&resume_failures);
	if (remote_spin_deep) {
		pr_info("kd_chain workload: stage=%u native_owner=%u reverse=%u depth=3 prefix=%u suffix=%u observed=%u\n",
			remote_spin_ooo, remote_spin_native_owner,
			remote_spin_reverse, remote_ooo_prefix,
			remote_ooo_suffix, remote_ooo_observed);
		return;
	}
	pr_info("kd_remote workload: stage=%u native_owner=%u prefix=%u suffix=%u observed=%u\n",
		remote_spin_ooo, remote_spin_native_owner, remote_ooo_prefix,
		remote_ooo_suffix, remote_ooo_observed);
}
