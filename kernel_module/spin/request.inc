// SPDX-License-Identifier: GPL-2.0
/* One packet/frame per request. Only pinned task-context producers reserve
 * their CPU's slots; remote CPUs can release users but cannot allocate here.
 * Acquire of zero pairs with the final release before storage is overwritten. */
static struct kd_spin_exec_request *kd_spin_request_reserve(void)
{
	struct kd_spin_exec_request *pool = *this_cpu_ptr(&kd_spin_requests);
	unsigned int i;

	if (!pool)
		return NULL;
	for (i = 0; i < KD_SPIN_REQUEST_SLOTS; i++) {
		struct kd_spin_exec_request *request = &pool[i];

		if (atomic_read_acquire(&request->users))
			continue;
		atomic_set(&request->users, 1);
		request->packet_owner = NULL;
		return request;
	}
	return NULL;
}

static void kd_spin_request_put(struct kd_spin_exec_request *request)
{
	struct kd_spin_exec_request *owner = request->packet_owner;

	/* Cache the only dependency before publishing zero: another task may
	 * immediately reuse this slot. A remote child retains the logical root,
	 * not its parent's recyclable queue slot or stack. */
	if (atomic_dec_and_test(&request->users) && owner)
		atomic_dec(&owner->users);
}
