// SPDX-License-Identifier: GPL-2.0
/* Map each Linux spinlock L to a separate private scheduling word S.
 * S selects combiners; only L excludes native peers. A hold records the real
 * owner and ownership interval, not the containing lock allocation's lifetime.
 * The fixed map is append-only until controlled provider teardown. */
#include <linux/errno.h>
#include <linux/hash.h>
#include <linux/limits.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "kd_lock.h"
#include "kd_spin_gate.h"

#define KD_SPIN_GATE_BITS 10
#define KD_SPIN_GATE_SLOTS (1U << KD_SPIN_GATE_BITS)

static struct kd_spin_gate kd_spin_gates[KD_SPIN_GATE_SLOTS];
static DEFINE_RAW_SPINLOCK(kd_spin_gate_map_lock);

static struct kd_spin_gate *kd_spin_gate_lookup(raw_spinlock_t *origin,
						bool create)
{
	struct kd_spin_gate *gate = NULL;
	unsigned long flags;
	unsigned int start, step;

	if (!origin)
		return NULL;
	start = hash_long((unsigned long)origin, KD_SPIN_GATE_BITS);
	raw_spin_lock_irqsave(&kd_spin_gate_map_lock, flags);
	for (step = 0; step < KD_SPIN_GATE_SLOTS; step++) {
		struct kd_spin_gate *entry =
			&kd_spin_gates[(start + step) &
				       (KD_SPIN_GATE_SLOTS - 1)];

		if (entry->origin == origin) {
			gate = entry;
			break;
		}
		if (!entry->origin) {
			if (create) {
				entry->owner_cpu = -1;
				entry->origin = origin;
				gate = entry;
			}
			break;
		}
	}
	raw_spin_unlock_irqrestore(&kd_spin_gate_map_lock, flags);
	/* No reclamation or allocation in the lock path. The caller must select
	 * the original native protocol if this bounded map is exhausted.
	 */
	return gate;
}

struct kd_spin_gate *kd_spin_gate_get(raw_spinlock_t *origin)
{
	struct kd_spin_gate *gate = kd_spin_gate_lookup(origin, true);

#ifdef KDLOCK_SELFTEST
	/* Identify real allocation refusal without changing the bounded map or
	 * manufacturing a ticket. Native participants do not call this lookup. */
	if (origin && !gate)
		pr_info("kd_gate refusal: task=%d cpu=%u lock=%lx\n",
			current->pid, raw_smp_processor_id(),
			(unsigned long)origin);
#endif
	return gate;
}

struct kd_spin_gate *kd_spin_gate_find(raw_spinlock_t *origin)
{
	return kd_spin_gate_lookup(origin, false);
}

int kd_spin_gate_claim(struct kd_spin_gate *gate, struct kd_spin_hold *hold)
{
	if (!gate || !gate->origin || !hold || !in_task() || irqs_disabled() ||
	    !(preempt_count() & PREEMPT_MASK) || !READ_ONCE(gate->word.locked))
		return -EINVAL;
	if (hold->gate || cmpxchg(&gate->owner, NULL, current))
		return -EBUSY;
	if (gate->generation == ULONG_MAX) {
		WRITE_ONCE(gate->owner, NULL);
		return -EOVERFLOW;
	}

	gate->owner_cpu = raw_smp_processor_id();
	/* This is the Linux protocol on the original word, without hook reentry
	 * or a second preempt_disable. Native participants never inspect word.
	 */
	kd_preempt_disable_raw_spin_lock(gate->origin);
	gate->generation++;
	WRITE_ONCE(gate->held, true);
	*hold = (struct kd_spin_hold){
		.gate = gate,
		.owner = current,
		.generation = gate->generation,
		.cpu = gate->owner_cpu,
	};
	return 0;
}

int kd_spin_gate_release(struct kd_spin_hold *hold)
{
	struct kd_spin_gate *gate;

	if (!hold || !hold->gate)
		return -EINVAL;
	gate = hold->gate;
	if (!in_task() || !(preempt_count() & PREEMPT_MASK) ||
	    hold->owner != current || hold->cpu != raw_smp_processor_id())
		return -EPERM;
	if (READ_ONCE(gate->owner) != current || !READ_ONCE(gate->held) ||
	    gate->owner_cpu != hold->cpu ||
	    gate->generation != hold->generation)
		return -ESTALE;

	/* Release origin before the caller hands over the scheduling word.
	 * A stale token, another CPU or a logical waiter cannot release it.
	 */
	spin_release(&gate->origin->dep_map, _RET_IP_);
	do_raw_spin_unlock(gate->origin);
	WRITE_ONCE(gate->held, false);
	gate->owner_cpu = -1;
	WRITE_ONCE(gate->owner, NULL);
	*hold = (struct kd_spin_hold){ 0 };
	return 0;
}

/* Only call after all users have drained. Do not dereference origin: the lock
 * object may already have been freed after its last completed acquisition.
 */
int kd_spin_gates_check_idle(void)
{
	unsigned int i;

	for (i = 0; i < KD_SPIN_GATE_SLOTS; i++) {
		struct kd_spin_gate *gate = &kd_spin_gates[i];

		if (READ_ONCE(gate->owner) || READ_ONCE(gate->held) ||
		    atomic_read(&gate->word.val))
			return -EBUSY;
	}
	return 0;
}

#ifdef KDLOCK_SELFTEST
#include "../tests/kernel/spin_gate_selftest.c"
#endif
