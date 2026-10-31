/* SPDX-License-Identifier: GPL-2.0 */
/* A root's ordinary spin pin supplies count one on its original CPU. Saving
 * IF does not install that CPU's context on an executor: compare the actual
 * executor before lending it an unexecuted root. Zero is never compatible. */
#define KD_SPIN_CONTEXT_ROOT 1U
#define KD_SPIN_CONTEXT_IRQ_OFF 2U

static __always_inline u8 kd_spin_proxy_context(void)
{
	if (!in_task() || preempt_count() != 1 || softirq_count() ||
	    current->migration_disabled)
		return 0;
#ifdef CONFIG_PREEMPT_RCU
	/* A pre-existing read-side lifetime belongs to the origin task. It is
	 * not represented by the ordinary preempt count on PREEMPT_RCU. */
	if (READ_ONCE(current->rcu_read_lock_nesting))
		return 0;
#endif
	return KD_SPIN_CONTEXT_ROOT |
		(irqs_disabled() ? KD_SPIN_CONTEXT_IRQ_OFF : 0);
}

static __always_inline bool
kd_spin_proxy_context_matches(u8 origin, u8 executor)
{
	return origin && origin == executor;
}
