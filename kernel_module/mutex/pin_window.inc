// SPDX-License-Identifier: GPL-2.0
/* A bounded immediate execution window, not queue-wide pinning. The queue
 * reservation keeps each node live until result wake; the batch source lease
 * separately keeps executable text live through final retirement.
 * Every selected origin must ACK even when preparation/refusal closes the window.
 * Only the current request may survive a dispatcher or ownership boundary. */
static void kd_mutex_batch_pin_check(struct kd_mutex_batch *batch,
				     unsigned int index)
{
	struct kd_mutex_node *node = batch->pins[index].node;

	BUG_ON(!node || READ_ONCE(node->counted_lock) != batch->lock ||
	       READ_ONCE(node->count_seq) != batch->pins[index].generation);
}

static bool kd_mutex_batch_pin_add(struct kd_mutex_batch *batch,
				   struct kd_mutex_node *node)
{
	unsigned int i = batch->nr_pins;
	u64 generation = READ_ONCE(node->count_seq);

	BUG_ON(i >= KD_MUTEX_PIN_WINDOW || (generation & 1) ||
	       READ_ONCE(node->counted_lock) != batch->lock);
	if (!kd_mutex_proxy_request(node))
		return false;
	batch->pins[i].node = node;
	batch->pins[i].generation = generation;
	batch->nr_pins = i + 1;
	return true;
}

/* Dropping a REQUEST without its ACK could race a late origin store and revive
 * a cancelled selection. Wait for PINNED, remove our exact descriptor, then
 * publish WAIT. No descriptor/node access follows a wake or slot reuse. */
static void kd_mutex_batch_unpin(struct kd_mutex_batch *batch, bool keep_current)
{
	unsigned int keep = keep_current && batch->nr_pins ? 1 : 0;

	while (batch->nr_pins > keep) {
		unsigned int i = batch->nr_pins - 1;
		struct kd_mutex_node *node = batch->pins[i].node;

		kd_mutex_batch_pin_check(batch, i);
		kd_mutex_proxy_wait_pinned(node);
		batch->pins[i].node = NULL;
		batch->nr_pins = i;
		smp_store_release(&node->locked, KD_MUTEX_WAIT);
	}
}

/* Forget the completed/native current before result publication. Its pin ends
 * through that existing result protocol; every remaining descriptor is queued. */
static void kd_mutex_batch_pin_complete(struct kd_mutex_batch *batch,
					struct kd_mutex_node *node)
{
	unsigned int i;

	BUG_ON(!batch->nr_pins || batch->pins[0].node != node ||
	       smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_PINNED);
	kd_mutex_batch_pin_check(batch, 0);
	for (i = 1; i < batch->nr_pins; i++)
		batch->pins[i - 1] = batch->pins[i];
	batch->nr_pins--;
	batch->pins[batch->nr_pins].node = NULL;
}

/* The caller has already incremented counter for current. A deferred prefix
 * may first appear after the locality boundary: clamp to current instead of
 * unsigned underflow, then let the original next-iteration boundary decide. */
static void kd_mutex_batch_pin_budget(struct kd_mutex_batch *batch, int counter)
{
	unsigned int left = counter >= kd_mutex_batch_size ?
		1 : kd_mutex_batch_size - counter + 1;

	if (batch->deferred_head) {
		unsigned int local_left = counter >= KDLOCK_MUTEX_NUMA_BOUNDARY ?
			1 : KDLOCK_MUTEX_NUMA_BOUNDARY - counter + 1;

		if (left > local_left)
			left = local_left;
	}
	batch->pin_budget = left;
}

/* Do not run NUMA selection ahead of the existing combiner loop. Only a fully
 * linked, same-entry/local FIFO prefix is immediately selected. With a deferred
 * prefix, stop before its terminal or count boundary; never select that prefix
 * or change its links. Distinct origin CPUs keep one pin from blocking an ACK. */
static bool kd_mutex_batch_pin_select(struct kd_mutex_batch *batch,
				      struct kd_mutex_node *node, bool ahead)
{
	struct kd_mutex_node *next;
	unsigned int i, limit = batch->pin_budget;

	if (batch->nr_pins) {
		BUG_ON(batch->pins[0].node != node);
		kd_mutex_batch_pin_check(batch, 0);
	} else if (!kd_mutex_batch_pin_add(batch, node)) {
		return false;
	}
	if (!ahead)
		return true;
	if (limit > KD_MUTEX_PIN_WINDOW)
		limit = KD_MUTEX_PIN_WINDOW;
	while (batch->nr_pins < limit) {
		struct kd_mutex_node *last = batch->pins[batch->nr_pins - 1].node;
		int cpu;

		next = smp_load_acquire(&last->next);
		if (!next || next->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
		    next->packet_state != KD_PACKET_MINIMAL ||
		    READ_ONCE(next->regs.ip) != READ_ONCE(node->regs.ip) ||
		    (batch->numa_node >= 0 && next->numa_node != batch->numa_node) ||
		    (batch->deferred_head && !smp_load_acquire(&next->next)))
			break;
		cpu = next->tail >> KD_MUTEX_TAIL_CPU_OFFSET;
		for (i = 0; i < batch->nr_pins; i++)
			if ((batch->pins[i].node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) == cpu)
				return true;
		if (!kd_mutex_batch_pin_add(batch, next))
			break;
	}
	return true;
}
