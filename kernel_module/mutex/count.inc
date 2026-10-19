// SPDX-License-Identifier: GPL-2.0
/* Cold exact observations of origin-owned waiter records. Private to
 * kd_mutex.c; no allocation or scan occurs in queue entry/exit or gate changes. */

#define KD_MUTEX_COUNT_SCAN_RETRIES 8

/* The caller has stopped and joined every user of this object. Other mutexes
 * may still be active; their keys do not prevent this object's checked reuse.
 * This is not an admission barrier and never dereferences the recorded key. */
bool kd_mutex_waiters_idle(struct kd_mutex *lock)
{
	int cpu, idx;

	if (!lock)
		return false;
	for_each_possible_cpu(cpu) {
		for (idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
			struct kd_mutex_node *node =
				per_cpu_ptr(&kd_mutex_nodes[idx], cpu);

			if (READ_ONCE(node->counted_lock) == lock)
				return false;
		}
	}
	return true;
}

/* Global controlled drain also rejects an interrupted record transition,
 * independently of the CPU balance and reservation checks. */
static bool kd_mutex_count_records_idle(void)
{
	int cpu, idx;

	for_each_possible_cpu(cpu) {
		for (idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
			struct kd_mutex_node *node =
				per_cpu_ptr(&kd_mutex_nodes[idx], cpu);

			if ((READ_ONCE(node->count_seq) & 1) ||
			    READ_ONCE(node->counted_lock))
				return false;
		}
	}
	return true;
}

/* A single sum across changing nodes would not describe one instant. First
 * collect each stable record and its version, then validate every version
 * again. Nonwrapping versions prove a common cut between the two passes.
 * Bound retries: an interrupt observer can encounter its own paused writer.
 * Allocation/refusal is confined to this diagnostic API, never acquisition. */
int kd_mutex_waiter_count(struct kd_mutex *lock)
{
	u64 *versions;
	int attempt, cpu, idx, count = -EAGAIN;

	if (!lock)
		return -EINVAL;
	versions = kmalloc_array((size_t)nr_cpu_ids * KD_MUTEX_MAX_NODES,
				 sizeof(*versions), GFP_ATOMIC);
	if (!versions)
		return -ENOMEM;
	for (attempt = 0; attempt < KD_MUTEX_COUNT_SCAN_RETRIES; attempt++) {
		count = 0;
		for_each_possible_cpu(cpu) {
			for (idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
				struct kd_mutex_node *node =
					per_cpu_ptr(&kd_mutex_nodes[idx], cpu);
				struct kd_mutex *key;
				u64 seq = smp_load_acquire(&node->count_seq);

				if (seq & 1)
					goto retry;
				key = READ_ONCE(node->counted_lock);
				smp_rmb();
				if (seq != READ_ONCE(node->count_seq))
					goto retry;
				versions[(size_t)cpu * KD_MUTEX_MAX_NODES + idx] = seq;
				count += key == lock;
			}
		}
		/* Complete every first-pass read before validating any record. */
		smp_rmb();
		for_each_possible_cpu(cpu) {
			for (idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
				struct kd_mutex_node *node =
					per_cpu_ptr(&kd_mutex_nodes[idx], cpu);

				if (READ_ONCE(node->count_seq) !=
				    versions[(size_t)cpu * KD_MUTEX_MAX_NODES + idx])
					goto retry;
			}
		}
		kfree(versions);
		return count;
retry:
		count = -EAGAIN;
		cpu_relax();
	}
	kfree(versions);
	return count;
}
