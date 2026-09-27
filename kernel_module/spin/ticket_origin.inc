// SPDX-License-Identifier: GPL-2.0
/* Origin-local lookup, reservation, physical ownership and final release.
 * A caller-owned preemption pin protects pool membership throughout. */

/* The existing request pin protects membership and identity. Remote peers
 * update only the packed count, never recycle a slot or migrate its owner. */
static bool kd_entry_lookup(raw_spinlock_t *origin, bool native,
			    struct kd_spin_ref *ref)
{
	struct kd_spin_entry_pool *pool;
	unsigned long occupied;

	if (!kd_entry_pinned() || !kd_spin_entries)
		return false;
	pool = this_cpu_ptr(kd_spin_entries);
	for (occupied = pool->occupied; occupied; occupied &= occupied - 1) {
		struct kd_spin_entry *entry =
			&pool->entries[__builtin_ctzl(occupied)];
		unsigned long control = atomic64_read(&entry->control);

		if (kd_entry_state(control) == KD_ENTRY_FREE ||
		    entry->task != current ||
		    (origin && entry->origin != origin) ||
		    (native && kd_entry_state(control) != KD_ENTRY_NATIVE))
			continue;
		if (ref)
			*ref = (struct kd_spin_ref){
				entry, control >> KD_ENTRY_SEQUENCE_SHIFT
			};
		return true;
	}
	return false;
}

bool kd_spin_entry_find(raw_spinlock_t *origin, struct kd_spin_ref *ref)
{
	return origin && ref && kd_entry_lookup(origin, false, ref);
}

bool kd_spin_entry_task_active(void)
{
	return kd_spin_fast_active() || kd_entry_lookup(NULL, false, NULL);
}

bool kd_spin_entry_native_active(void)
{
	/* A lightweight KD root owns the physical lock but is not a native
	 * continuation. Its nested hooks still need their own tickets. */
	return kd_entry_lookup(NULL, true, NULL);
}

/* Reserve under a caller-owned pin. No peer may mutate a FREE generation;
 * the next tag is published only after its owner-local metadata is ready. */
static int kd_spin_entry_reserve(raw_spinlock_t *origin,
				enum kd_spin_entry_kind kind,
				struct kd_spin_ref *ref)
{
	struct kd_spin_entry_pool *pool;
	struct kd_spin_entry *entry;
	unsigned long occupied, available, control;
	unsigned int index;

	if (!kd_spin_entries)
		return -ENODEV;
	if (!origin || !ref || ref->entry || !in_task() ||
	    (kind != KD_SPIN_ENTRY_HOOK && kind != KD_SPIN_ENTRY_VIRTUAL))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	pool = this_cpu_ptr(kd_spin_entries);
	for (occupied = pool->occupied; occupied; occupied &= occupied - 1) {
		struct kd_spin_entry *candidate = &pool->entries[__builtin_ctzl(occupied)];

		if (candidate->task == current && candidate->origin == origin)
			return -EDEADLK;
	}
	available = ~pool->occupied & ((1UL << KD_SPIN_ENTRY_SLOTS) - 1);
	if (!available)
		return -E2BIG;
	if (pool->sequence >= KD_ENTRY_SEQUENCE_MAX)
		return -EOVERFLOW;
	index = __builtin_ctzl(available);
	entry = &pool->entries[index];
	entry->task = current;
	entry->origin = origin;
	entry->cpu = raw_smp_processor_id();
	control = (++pool->sequence << KD_ENTRY_SEQUENCE_SHIFT) | KD_ENTRY_WAITING;
	if (kind == KD_SPIN_ENTRY_VIRTUAL)
		control |= KD_ENTRY_VIRTUAL_BIT;
	pool->occupied |= 1UL << index;
	atomic64_set_release(&entry->control, control);
	*ref = (struct kd_spin_ref){ entry, pool->sequence };
	return 0;
}

int kd_spin_entry_begin(raw_spinlock_t *origin, enum kd_spin_entry_kind kind,
			struct kd_spin_ref *ref)
{
	int ret;

	preempt_disable();
	ret = kd_spin_entry_reserve(origin, kind, ref);
	if (ret)
		preempt_enable();
	return ret;
}

int kd_spin_entry_begin_pinned(raw_spinlock_t *origin,
			       struct kd_spin_ref *ref)
{
	return kd_spin_entry_reserve(origin, KD_SPIN_ENTRY_HOOK, ref);
}

kd_spinlock_t *kd_spin_entry_word(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;

	if (!kd_entry_ref_present(ref) || !kd_entry_pinned())
		return NULL;
	entry = ref->entry;
	/* A local request pin excludes identity reuse; remote native borrowers
	 * do not change these fields. Reject other CPUs before following origin. */
	if (READ_ONCE(entry->cpu) != raw_smp_processor_id() ||
	    entry->task != current || kd_entry_valid(ref, atomic64_read(&entry->control)))
		return NULL;
	return (kd_spinlock_t *)entry->origin;
}

static int kd_spin_entry_claim_from(const struct kd_spin_ref *ref,
				    enum kd_spin_entry_state from)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	ret = kd_entry_local(ref, control);
	if (ret)
		return ret;
	for (;;) {
		if (kd_entry_state(control) == KD_ENTRY_OWNED && from == KD_ENTRY_WAITING)
			return 0;
		if (kd_entry_state(control) != from || kd_entry_refs(control))
			return -EBUSY;
		/* Physical acquisition precedes this metadata transition. The CAS
		 * excludes a racing native borrow without a separate guard word. */
		if (!READ_ONCE(((kd_spinlock_t *)entry->origin)->locked))
			return -EINVAL;
		if (kd_entry_update(entry, &control,
				    kd_entry_with_state(control, KD_ENTRY_OWNED)))
			return 0;
	}
}

int kd_spin_entry_claim(const struct kd_spin_ref *ref)
{
	return kd_spin_entry_claim_from(ref, KD_ENTRY_WAITING);
}

int kd_spin_entry_reclaim(const struct kd_spin_ref *ref)
{
	return kd_spin_entry_claim_from(ref, KD_ENTRY_RELEASED);
}

int kd_spin_entry_release_origin(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	ret = kd_entry_local(ref, control);
	if (ret)
		return ret;
	for (;;) {
		if (kd_entry_state(control) != KD_ENTRY_OWNED)
			return -EBUSY;
		/* Metadata retirement is separate from the scheduler's physical
		 * release store and wake publication. Keep the request pin. */
		if (kd_entry_update(entry, &control,
				    kd_entry_with_state(control, KD_ENTRY_RELEASED)))
			return 0;
	}
}

int kd_spin_entry_end_pinned(struct kd_spin_ref *ref)
{
	struct kd_spin_entry_pool *pool;
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	if (!kd_entry_pinned())
		return -EPERM;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	ret = kd_entry_local(ref, control);
	if (ret)
		return ret;
	for (;;) {
		enum kd_spin_entry_state state = kd_entry_state(control);

		if (kd_entry_refs(control) ||
		    (state != KD_ENTRY_WAITING && state != KD_ENTRY_RELEASED &&
		     state != KD_ENTRY_NATIVE))
			return -EBUSY;
		/* FREE retains the generation, rejecting any delayed old CAS.
		 * Only this pinned owner can reserve the slot after this point. */
		if (kd_entry_update(entry, &control, control & ~KD_ENTRY_LOW_MASK))
			break;
	}
	pool = this_cpu_ptr(kd_spin_entries);
	pool->occupied &= ~(1UL << (entry - pool->entries));
	entry->task = NULL;
	entry->origin = NULL;
	entry->cpu = -1;
	*ref = (struct kd_spin_ref){ 0 };
	/* The caller retains its pin until its remaining per-CPU reads finish. */
	return 0;
}

/* Ordinary C exits consume the pin here. Nonlocal packet restoration uses
 * end_pinned(), retires its record after the last load, then unpins. */
int kd_spin_entry_end(struct kd_spin_ref *ref)
{
	int ret = kd_spin_entry_end_pinned(ref);

	if (!ret)
		preempt_enable();
	return ret;
}
