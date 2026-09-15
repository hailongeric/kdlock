// SPDX-License-Identifier: GPL-2.0
/*
 * Direct/holder/follower roles and observers for the remote chain.
 * Private implementation included only by remote_depth_workload.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

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
