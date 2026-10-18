// SPDX-License-Identifier: GPL-2.0
/*
 * Read-only pool drain and diagnostic owner scans. These observations
 * do not grant ownership or replace stable ticket references.
 */

/* After callers drain, verify that no fast hold or live ticket remains. */
int kd_spin_entries_check_idle(void)
{
	int cpu;
	unsigned int i;

	if (!kd_spin_fast_idle())
		return -EBUSY;
	if (!kd_spin_entries)
		return 0;
	for_each_possible_cpu(cpu) {
		struct kd_spin_entry_pool *pool =
			per_cpu_ptr(kd_spin_entries, cpu);

		for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++) {
			struct kd_spin_entry *entry = &pool->entries[i];
			unsigned long control = atomic64_read(&entry->control);

			if (kd_entry_state(control) != KD_ENTRY_FREE ||
			    kd_entry_refs(control) || READ_ONCE(entry->task))
				return -EBUSY;
		}
	}
	return 0;
}

/*
 * Diagnostic snapshot only; ownership decisions use the caller's stable ref.
 * Pool storage survives all observers until provider drain.
 */
unsigned long kd_spin_entry_owner(raw_spinlock_t *origin)
{
	int cpu;
	unsigned int i;

	if (!kd_spin_entries)
		return 0;
	for_each_possible_cpu(cpu) {
		struct kd_spin_fast_cpu *fast =
			per_cpu_ptr(&kd_spin_fast_cpu, cpu);
		struct kd_spin_entry_pool *pool =
			per_cpu_ptr(kd_spin_entries, cpu);

		if (READ_ONCE(fast->held) == (kd_spinlock_t *)origin)
			return (unsigned long)READ_ONCE(fast->owner);
		for (i = 0; i < KD_SPIN_ENTRY_SLOTS; i++) {
			struct kd_spin_entry *entry = &pool->entries[i];

			if (READ_ONCE(entry->origin) == origin &&
			    kd_entry_state(atomic64_read(&entry->control)) ==
				    KD_ENTRY_OWNED)
				return (unsigned long)READ_ONCE(entry->task);
		}
	}
	return 0;
}
