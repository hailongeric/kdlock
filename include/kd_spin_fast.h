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
	raw_spinlock_t *cached_origin;
	unsigned long cached_rip;
	struct kd_spin_gate *cached_gate;
};

DECLARE_PER_CPU(struct kd_spin_fast_cpu, kd_spin_fast_cpu);
/* Read-only bint parameter: bool parsing with integer storage. This avoids
 * a UBSAN bool-load call site (and caller spills) at each hot-path read. */
extern int kd_spin_native_cache;
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

/* Use the original Linux trylock, not a load of L followed by an unconditional
 * store. Seeing S idle is an optimization hint: a racing combiner still takes
 * L, so both paths exclude each other. A nonzero S (including a queued tail)
 * gives the existing delegation path priority. No ticket/frame is published
 * by a successful native try, and nested calls remain native while it is held.
 */
enum kd_spin_fast_result {
	KD_SPIN_FAST_CONTEXT,
	KD_SPIN_FAST_MISS_PINNED,
	KD_SPIN_FAST_OWNED,
};

/* A miss returns its temporary CPU pin to the caller. The combined dispatch
 * drops it in a cold helper, keeping scheduling calls and their argument-save
 * prologue out of a successful native acquisition. OWNED retains the normal
 * lock pin through unlock; CONTEXT never acquired a pin. */
static __always_inline enum kd_spin_fast_result
kd_spin_fast_acquire(raw_spinlock_t *lock, unsigned long rip)
{
	struct kd_spin_fast_cpu *fast;

	if (unlikely(!READ_ONCE(kd_spin_native_cache) || preempt_count() ||
		     current->migration_disabled))
		return KD_SPIN_FAST_CONTEXT;
	preempt_disable();
	fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	if (likely(fast->cached_origin == lock && fast->cached_rip == rip) &&
	    !atomic_read(&fast->cached_gate->word.val) && kd_source_is_open()) {
		spin_acquire(&lock->dep_map, 0, 0, _RET_IP_);
		if (likely(do_raw_spin_trylock(lock))) {
			fast->hold.owner = current;
			WRITE_ONCE(fast->held, lock);
			return KD_SPIN_FAST_OWNED;
		}
		spin_release(&lock->dep_map, _RET_IP_);
	}
	return KD_SPIN_FAST_MISS_PINNED;
}

/* Preserve the legacy boolean helper's balanced-miss contract. */
static __always_inline bool
kd_spin_fast_trylock(raw_spinlock_t *lock, unsigned long rip)
{
	enum kd_spin_fast_result result = kd_spin_fast_acquire(lock, rip);

	if (result == KD_SPIN_FAST_MISS_PINNED)
		preempt_enable();
	return result == KD_SPIN_FAST_OWNED;
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

/* Root admission already has a stable gate/pin. A matching cache needs no
 * repeated registry lookup: it never grants JIT admission, its source/gate
 * storage survives the session, and acquire() still checks OPEN and idle S.
 * Only a new key needs the original published-NORMAL eligibility check. */
static inline void kd_spin_fast_remember(raw_spinlock_t *lock, unsigned long rip,
					 struct kd_spin_gate *gate)
{
	struct kd_spin_fast_cpu *fast;
	struct kd_exe_info *exe;

	if (!READ_ONCE(kd_spin_native_cache) || preempt_count() != 1)
		return;
	fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	if (fast->cached_origin == lock && fast->cached_rip == rip &&
	    fast->cached_gate == gate)
		return;
	exe = kd_get_exe(0, rip);
	if (!exe || exe->pid || exe->RIP != rip ||
	    exe->lock_kind != KD_EXE_LOCK_SPIN ||
	    READ_ONCE(exe->status_code) != KD_EXE_NORMAL || !kd_source_is_open())
		return;
	fast->cached_origin = lock;
	fast->cached_rip = rip;
	fast->cached_gate = gate;
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
