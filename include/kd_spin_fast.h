/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_FAST_H
#define KD_SPIN_FAST_H

#include <linux/percpu.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "exe.h"
#include "kd_source.h"
#include "kd_spin_gate.h"

/* A monomorphic lookup cache, never an alternative ownership word. Source pins
 * and gate storage survive until controlled provider retirement. Only a root
 * caller may use this path: the native L pin then protects this CPU's record
 * through unlock, including a comm change or source admission closing.
 */
struct kd_spin_fast_cpu {
	raw_spinlock_t *origin;
	unsigned long rip;
	struct kd_spin_gate *gate;
	raw_spinlock_t *held;
	struct task_struct *owner;
};

DECLARE_PER_CPU(struct kd_spin_fast_cpu, kd_spin_fast_cpu);

static __always_inline bool kd_spin_fast_native_active(void)
{
	struct kd_spin_fast_cpu *fast;

	if (!in_task() || !(preempt_count() & PREEMPT_MASK))
		return false;
	fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	return fast->held && fast->owner == current;
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

	if (unlikely(preempt_count() || current->migration_disabled))
		return KD_SPIN_FAST_CONTEXT;
	preempt_disable();
	fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	if (likely(fast->origin == lock && fast->rip == rip) &&
	    !atomic_read(&fast->gate->word.val) && kd_source_is_open()) {
		spin_acquire(&lock->dep_map, 0, 0, _RET_IP_);
		if (likely(do_raw_spin_trylock(lock))) {
			fast->owner = current;
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

static __always_inline bool kd_spin_fast_unlock(raw_spinlock_t *lock)
{
	struct kd_spin_fast_cpu *fast;

	if (!in_task() || !(preempt_count() & PREEMPT_MASK))
		return false;
	fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	if (fast->held != lock || fast->owner != current)
		return false;
	spin_release(&lock->dep_map, _RET_IP_);
	do_raw_spin_unlock(lock);
	/* Retirement must see ownership until L is released. Clear the record
	 * before the final preempt_enable, which may schedule a different task. */
	WRITE_ONCE(fast->held, NULL);
	fast->owner = NULL;
	preempt_enable();
	return true;
}

/* Cold miss only, after the normal registration/pinning path. Requiring an
 * already published spin entry keeps discovery, admission and translation
 * preparation unchanged; cache hits execute native code and cannot dispatch
 * an obsolete JIT image. No cache is shared with a nested/borrowed caller.
 */
static inline void kd_spin_fast_remember(raw_spinlock_t *lock, unsigned long rip,
					 struct kd_spin_gate *gate)
{
	struct kd_spin_fast_cpu *fast;
	struct kd_exe_info *exe;

	/* Called only by kd_spin_lock after admission, with a non-NULL gate and
	 * the new ticket's pin. No scheduling point intervenes, so task/
	 * migration checks need not be repeated. Keep the depth test: a nested
	 * caller must not replace a root cache record. */
	if (preempt_count() != 1)
		return;
	exe = kd_get_exe(0, rip);
	if (!exe || exe->pid || exe->RIP != rip ||
	    exe->lock_kind != KD_EXE_LOCK_SPIN ||
	    READ_ONCE(exe->status_code) != KD_EXE_NORMAL || !kd_source_is_open())
		return;
	fast = raw_cpu_ptr(&kd_spin_fast_cpu);
	fast->origin = lock;
	fast->rip = rip;
	fast->gate = gate;
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
