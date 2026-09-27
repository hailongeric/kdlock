// SPDX-License-Identifier: GPL-2.0
/* Remote native borrowing, native-wake transition and final drain wait.
 * Every remote CAS checks the generation; borrows never recycle pool slots. */

int kd_spin_entry_borrow_get(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref))
		return -EINVAL;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	for (;;) {
		ret = kd_entry_valid(ref, control);
		if (ret)
			return ret;
		if ((control & KD_ENTRY_VIRTUAL_BIT) ||
		    kd_entry_state(control) != KD_ENTRY_WAITING)
			return -EINVAL;
		if (kd_entry_refs(control) == KD_ENTRY_REF_MAX)
			return -EOVERFLOW;
		if (kd_entry_update(entry, &control, control + KD_ENTRY_REF_ONE))
			return 0;
	}
}

int kd_spin_entry_mark_native(const struct kd_spin_ref *ref)
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
		if (kd_entry_state(control) != KD_ENTRY_WAITING ||
		    (control & KD_ENTRY_VIRTUAL_BIT))
			return -EINVAL;
		/* Preserve borrows admitted before the native wake. New gets
		 * fail once this phase is published; existing puts can continue. */
		if (kd_entry_update(entry, &control,
				    kd_entry_with_state(control, KD_ENTRY_NATIVE)))
			return 0;
	}
}

int kd_spin_entry_borrow_put(const struct kd_spin_ref *ref, bool *last)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref) || !last)
		return -EINVAL;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	for (;;) {
		ret = kd_entry_valid(ref, control);
		if (ret)
			return ret;
		if (!kd_entry_refs(control) ||
		    (kd_entry_state(control) != KD_ENTRY_WAITING &&
		     kd_entry_state(control) != KD_ENTRY_NATIVE))
			return -EINVAL;
		/* The ordered CAS publishes frame retirement before the waiter
		 * observes zero. Do not touch the entry after dropping the last ref. */
		if (kd_entry_update(entry, &control, control - KD_ENTRY_REF_ONE)) {
			*last = kd_entry_refs(control) == 1;
			return 0;
		}
	}
}

/* Native ACK is distinct from frame retirement. The owner retains its pin,
 * so only borrows can change while it polls; no locked RMW is needed here. */
int kd_spin_entry_borrow_wait(const struct kd_spin_ref *ref)
{
	struct kd_spin_entry *entry;
	unsigned long control;
	int ret;

	if (!kd_entry_ref_present(ref) || !kd_entry_pinned())
		return -EINVAL;
	entry = ref->entry;
	control = atomic64_read_acquire(&entry->control);
	ret = kd_entry_local(ref, control);
	if (ret)
		return ret;
	while (kd_entry_refs(control)) {
		cpu_relax();
		control = atomic64_read_acquire(&entry->control);
	}
	return 0;
}
