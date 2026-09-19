// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Per-lock diagnostic counters, waiter observations and JIT-disable latch.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static struct kd_spin_diag_slot *kd_spin_diag_find(unsigned long addr)
{
	unsigned int start;
	unsigned int i;

	if (!addr)
		return NULL;

	start = (unsigned int)(((addr >> 6) ^ (addr >> 17)) %
			       KD_SPIN_DIAG_SLOTS);
	for (i = 0; i < KD_SPIN_DIAG_SLOTS; i++) {
		struct kd_spin_diag_slot *slot =
			&kd_spin_diag_slots[(start + i) % KD_SPIN_DIAG_SLOTS];
		long observed = atomic_long_read(&slot->addr);

		if ((unsigned long)observed == addr)
			return slot;
		if (observed == 0) {
			observed =
				atomic_long_cmpxchg(&slot->addr, 0, (long)addr);
			if (observed == 0 || (unsigned long)observed == addr)
				return slot;
		}
	}

	this_cpu_inc(kd_spin_diag_cpu->overflow);
	return NULL;
}

static void kd_spin_diag_record_slot(struct kd_spin_diag_slot *slot,
				     enum kd_spin_diag_event event,
				     unsigned int depth)
{
	unsigned int index;
	int old_depth;

	if (event >= KD_SPIN_DIAG_EVENT_COUNT)
		return;

	if (!slot)
		return;

	index = slot - kd_spin_diag_slots;
	/* x86 this_cpu operations also tolerate an IRQ interrupting a recorder.
	 * The local cmpxchg prevents a shallower interrupted update from losing
	 * a deeper maximum; it needs no cross-CPU LOCK prefix. */
	this_cpu_inc(kd_spin_diag_cpu->slot[index].event[event]);
	old_depth = this_cpu_read(kd_spin_diag_cpu->slot[index].max_depth);
	while (old_depth < (int)depth) {
		int previous =
			this_cpu_cmpxchg(kd_spin_diag_cpu->slot[index].max_depth,
					 old_depth, depth);

		if (previous == old_depth)
			break;
		old_depth = previous;
	}
}

/* Resolve once when a caller has no retained request/batch identity. */
static void kd_spin_diag_record_addr(unsigned long addr,
				     enum kd_spin_diag_event event,
				     unsigned int depth)
{
	if (event < KD_SPIN_DIAG_EVENT_COUNT)
		kd_spin_diag_record_slot(kd_spin_diag_find(addr), event, depth);
}

/* Shutdown only, after callers/frames drain. Include CPUs which went offline
 * after recording; this is intentionally not a live statistical snapshot. */
static void kd_spin_diag_sum(unsigned int index, struct kd_spin_diag_counts *sum)
{
	int cpu, event;

	memset(sum, 0, sizeof(*sum));
	for_each_possible_cpu(cpu) {
		const struct kd_spin_diag_counts *counts =
			&per_cpu_ptr(kd_spin_diag_cpu, cpu)->slot[index];

		for (event = 0; event < KD_SPIN_DIAG_EVENT_COUNT; event++)
			sum->event[event] += counts->event[event];
		if (counts->max_depth > sum->max_depth)
			sum->max_depth = counts->max_depth;
	}
}

static void kd_spin_diag_record(struct qspinlock *lock,
				enum kd_spin_diag_event event,
				unsigned int depth)
{
	kd_spin_diag_record_addr((unsigned long)lock, event, depth);
}

static bool kd_spin_jit_is_disabled(const struct kd_spin_diag_slot *slot)
{
	return slot && atomic_read_acquire(&slot->jit_disabled);
}

static void kd_spin_jit_disable(struct qspinlock *lock)
{
	struct kd_spin_diag_slot *slot = kd_spin_diag_find((unsigned long)lock);

	if (!slot)
		return;
	if (atomic_cmpxchg(&slot->jit_disabled, 0, 1) == 0)
		kd_spin_diag_record(lock, KD_SPIN_DIAG_NATIVE_FALLBACK,
				    kd_spin_lock_stack_depth(
					    this_cpu_ptr(&local_shadow_stack)));
}

static struct kd_spin_diag_slot *kd_spin_diag_waiter_enter(struct qspinlock *lock)
{
	struct kd_spin_diag_slot *slot = kd_spin_diag_find((unsigned long)lock);

	if (slot)
		atomic_inc(&slot->waiter_count);
	return slot;
}

static void kd_spin_diag_waiter_exit(struct kd_spin_diag_slot *slot)
{
	if (!slot)
		return;
	if (unlikely(atomic_dec_return(&slot->waiter_count) < 0)) {
		atomic_set(&slot->waiter_count, 0);
		kd_spin_diag_invariant_failure();
	}
}

int kd_spin_debug_waiter_count(raw_spinlock_t *lock)
{
	struct kd_spin_diag_slot *slot;

	if (!lock)
		return -EINVAL;
	slot = kd_spin_diag_find((unsigned long)lock);
	return slot ? atomic_read(&slot->waiter_count) : -ENOSPC;
}
EXPORT_SYMBOL_GPL(kd_spin_debug_waiter_count);

/* Test observers must not interpret the Linux lock word as our private queue. */
unsigned int kd_spin_debug_word(raw_spinlock_t *lock)
{
	struct kd_spin_gate *gate = kd_spin_gate_find(lock);

	return gate ? atomic_read(&gate->word.val) : 0;
}
EXPORT_SYMBOL_GPL(kd_spin_debug_word);

/* Only a physically held proxy gate has an owner; native Linux users do not. */
unsigned long kd_spin_debug_owner(raw_spinlock_t *lock)
{
	struct kd_spin_gate *gate = kd_spin_gate_find(lock);

	return gate && READ_ONCE(gate->held) ?
		       (unsigned long)READ_ONCE(gate->owner) :
		       0;
}
EXPORT_SYMBOL_GPL(kd_spin_debug_owner);

static void kd_spin_diag_record_nested(raw_spinlock_t *lock,
				       enum kd_spin_diag_event event,
				       bool native_fallback)
{
	struct shadow_stack *ptr = this_cpu_ptr(&local_shadow_stack);
	unsigned int depth = kd_spin_lock_stack_depth(ptr);

	kd_spin_diag_record_addr((unsigned long)lock, event, depth);
	if (native_fallback)
		kd_spin_diag_record_addr((unsigned long)lock,
					 KD_SPIN_DIAG_NATIVE_FALLBACK, depth);
}

static void kd_spin_debug_combiner(struct kd_spin_diag_slot *slot, unsigned int depth)
{
	kd_spin_diag_record_slot(slot, KD_SPIN_DIAG_COMBINER, depth);
}

static void kd_spin_debug_jit_success(struct kd_spin_diag_slot *slot,
				      unsigned int depth)
{
	kd_spin_diag_record_slot(slot, KD_SPIN_DIAG_JIT_SUCCESS, depth);
}

static void kd_spin_debug_jit_not_ready(struct kd_spin_diag_slot *slot,
					unsigned int depth)
{
	kd_spin_diag_record_slot(slot, KD_SPIN_DIAG_JIT_NOT_READY, depth);
}

void kd_spin_debug_nested_lock(raw_spinlock_t *lock, bool native_fallback)
{
	kd_spin_diag_record_nested(lock, KD_SPIN_DIAG_NESTED_LOCK,
				   native_fallback);
}

void kd_spin_debug_nested_unlock(raw_spinlock_t *lock)
{
	kd_spin_diag_record_nested(lock, KD_SPIN_DIAG_NESTED_UNLOCK, false);
}

void kd_spin_debug_nested_remote(raw_spinlock_t *lock)
{
	kd_spin_diag_record_nested(lock, KD_SPIN_DIAG_NESTED_REMOTE, false);
}

static void kd_spin_debug_ooo_unlock(struct qspinlock *lock, unsigned int depth)
{
	kd_spin_diag_record(lock, KD_SPIN_DIAG_OOO_UNLOCK, depth);
}
