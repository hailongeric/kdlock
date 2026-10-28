// SPDX-License-Identifier: GPL-2.0
/* A native owner retains its old queue slot through the logical outer unlock.
 * Its FULL packet has already been copied to the original stack. No field here
 * points into the previous executor's frame after the pickup ACK. */

static struct kd_mutex_node *kd_mutex_custody_current(void)
{
	struct kd_mutex_node *node = kd_mutex_task_custody(current);

	if (!node)
		return NULL;
	BUG_ON(node->task_struct_ptr != current || !node->lock ||
	       READ_ONCE(node->counted_lock) ||
	       (READ_ONCE(node->count_seq) & 1) ||
	       READ_ONCE(node->count_seq) != node->custody.generation ||
	       !(this_cpu_read(kd_mutex_shadows.node_slots) & BIT(node->slot)) ||
	       !(this_cpu_read(kd_mutex_custody_slots) & BIT(node->slot)));
	return node;
}

/* Called pinned, after the trampoline copied every FULL field. The node's
 * union changes purpose only here, and W's generation is after waiter_exit. */
static void kd_mutex_custody_pickup(struct kd_mutex_node *node,
				    struct kd_exec_frame *frame)
{
	struct kd_mutex_node *head;
	u64 generation;

	BUG_ON(!frame->mutex_mixed.queue_transfer ||
	       !frame->mutex_mixed.transferred ||
	       frame->mutex_mixed.picked_up ||
	       frame->mutex_mixed.queue.owner != node ||
	       frame->logical_task != current || node->task_struct_ptr != current ||
	       (unsigned long)node->lock != frame->outer_lock_addr ||
	       kd_mutex_task_custody(current) != node);
	head = frame->mutex_mixed.queue.head;
	generation = frame->mutex_mixed.queue.generation;
	BUG_ON(!head || READ_ONCE(node->count_seq) != generation ||
	       (generation & 1) || READ_ONCE(node->counted_lock));
	BUG_ON(kd_mutex_transfer_pickup(node->lock));
	node->custody.head = head;
	node->custody.generation = generation;
	node->custody.phase = KD_MUTEX_CUSTODY_WAIT_READY;
	node->custody.ready = false;
	node->custody.source_lease = true;
	node->custody.native_count = 0;
	node->custody.native_overflow = false;
	node->native_transfer = NULL;
	this_cpu_or(kd_mutex_custody_slots, BIT(node->slot));
	/* Last frame access. The former executor can now retire its per-CPU
	 * frame, release its own lease, and make C's queued continuation runnable. */
	smp_store_release(&frame->mutex_mixed.picked_up, true);
	while (!smp_load_acquire(&node->custody.ready))
		cpu_relax();
	WRITE_ONCE(node->custody.phase, KD_MUTEX_CUSTODY_NATIVE);
}

void kd_mutex_custody_native_acquire(struct kd_mutex *lock)
{
	struct kd_mutex_node *node = kd_mutex_task_custody(current);
	struct kd_mutex_custody *custody;
	unsigned int i;

	if (!node)
		return;
	node = kd_mutex_custody_current();
	custody = &node->custody;
	if (custody->phase != KD_MUTEX_CUSTODY_NATIVE || lock == node->lock)
		return;
	for (i = 0; i < custody->native_count; i++)
		BUG_ON(custody->native_locks[i] == lock);
	if (custody->native_count == KD_MUTEX_CUSTODY_LOCKS) {
		custody->native_overflow = true;
		return;
	}
	custody->native_locks[custody->native_count++] = lock;
}
EXPORT_SYMBOL_GPL(kd_mutex_custody_native_acquire);

void kd_mutex_custody_native_release(struct kd_mutex *lock)
{
	struct kd_mutex_node *node = kd_mutex_task_custody(current);
	struct kd_mutex_custody *custody;
	unsigned int i;

	if (!node)
		return;
	node = kd_mutex_custody_current();
	custody = &node->custody;
	if (custody->phase != KD_MUTEX_CUSTODY_NATIVE || lock == node->lock)
		return;
	for (i = 0; i < custody->native_count; i++) {
		if (custody->native_locks[i] != lock)
			continue;
		custody->native_locks[i] = custody->native_locks[--custody->native_count];
		return;
	}
	/* Locks acquired outside this native suffix have no entry. Their use
	 * remains outside the root-only contract; never infer an ownership count. */
}

bool kd_mutex_custody_unlock(struct kd_mutex *lock)
{
	struct kd_mutex_node *node = kd_mutex_task_custody(current), *head;
	bool combine;

	if (!node || node->lock != lock)
		return false;
	node = kd_mutex_custody_current();
	BUG_ON(node->custody.phase != KD_MUTEX_CUSTODY_NATIVE ||
	       !node->custody.source_lease ||
	       !kd_mutex_delegation_owned(lock, current));
	/* A may be unlocked while native B remains held. Running another body's
	 * lock requests under B could create a dependency absent from the source.
	 * Keep that case local. Exact KD mutex entries supplement IRQ/spin state. */
	combine = !preempt_count() && !irqs_disabled() &&
		!node->custody.native_count && !node->custody.native_overflow;
	preempt_disable();
	combine = combine && !kd_exec_context_occupied();
	head = node->custody.head;
	node->custody.head = NULL;
	node->custody.phase = KD_MUTEX_CUSTODY_COMBINING;
	if (combine) {
		/* W's source body has already reached its unlock. The new batch may
		 * execute arbitrary supported C images and existing native exits,
		 * but it never reacquires A for a second W body. */
		BUG_ON(kd_mutex_run_combiner(lock, head, NULL, true) !=
		       KD_MUTEX_BATCH_RELEASED);
	} else {
		BUG_ON(_kd_mutex_unlock_checked(lock));
		if (head)
			smp_store_release(&head->locked, 0);
	}
	/* The exact node/task/source references outlive the final physical release
	 * and every C native ACK. No route or frame can still name this storage. */
	node->custody.phase = KD_MUTEX_CUSTODY_RETIRED;
	kd_mutex_task_custody_clear(current, node);
	this_cpu_and(kd_mutex_custody_slots, ~BIT(node->slot));
	node->custody.source_lease = false;
	kd_source_frame_put();
	kd_mutex_release_node(node);
	kd_mutex_task_put(current);
	preempt_enable();
	migrate_enable();
	return true;
}
