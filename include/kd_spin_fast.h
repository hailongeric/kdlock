/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_FAST_H
#define KD_SPIN_FAST_H

#include <linux/percpu.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "exe.h"
#include "kd_source.h"
#include "kd_spin_gate.h"

/* Active ownership is independent of the optional acquisition lookup cache. The uncontended
 * private-S owner needs no ticket/frame but must retain its native-L pin and
 * unlock provenance across comm changes, nested acquisitions and closing.
 * Only that task/CPU writes the record; retirement reads held after drain.
 */
struct kd_spin_fast_cpu {
	struct kd_spin_hold hold;
	raw_spinlock_t *held;
};

DECLARE_PER_CPU(struct kd_spin_fast_cpu, kd_spin_fast_cpu);
/* Keep the S/L release call and its live pointers out of cached-native callers. */
void kd_spin_fast_release_gate(struct kd_spin_fast_cpu *fast);

static __always_inline bool kd_spin_fast_active(void)
{
	struct kd_spin_fast_cpu *fast;

	if (!in_task() || !(preempt_count() & PREEMPT_MASK))
		return false;
	fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	return fast->held && fast->hold.owner == current;
}

/* Cached native-L ownership keeps the former conservative nested-native
 * route. The S/L path below is ordinary ownership and admits nested tickets. */
static __always_inline bool kd_spin_fast_native_active(void)
{
	struct kd_spin_fast_cpu *fast;

	if (!kd_spin_fast_active())
		return false;
	fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	return !fast->hold.gate;
}

/* S is owned and CPU pinned. Keep the existing physical-owner token and
 * generation checks: queued peers and diagnostics must still see the real
 * owner, and a stale hold must never release a later acquisition. No ticket
 * is required until a root actually contends for S. */
static __always_inline int kd_spin_fast_claim(struct kd_spin_gate *gate)
{
	struct kd_spin_fast_cpu *fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	int ret = kd_spin_gate_claim(gate, &fast->hold);

	if (!ret)
		WRITE_ONCE(fast->held, gate->origin);
	return ret;
}

static __always_inline bool kd_spin_fast_unlock(raw_spinlock_t *lock)
{
	struct kd_spin_fast_cpu *fast;

	if (!in_task() || !(preempt_count() & PREEMPT_MASK))
		return false;
	fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	if (fast->held != lock || fast->hold.owner != current)
		return false;
	if (unlikely(fast->hold.gate)) {
		kd_spin_fast_release_gate(fast);
		return true;
	}
	spin_release(&lock->dep_map, _RET_IP_);
	do_raw_spin_unlock(lock);
	fast->hold.owner = NULL;
	/* Retirement must see ownership until L is released. Clear the record
	 * before the final preempt_enable, which may schedule a different task. */
	WRITE_ONCE(fast->held, NULL);
	preempt_enable();
	return true;
}

static inline bool kd_spin_fast_idle(void)
{
	int cpu;

	for_each_possible_cpu(cpu)
		if (READ_ONCE(per_cpu(kd_spin_fast_cpu, cpu).held))
			return false;
	return true;
}

#endif
