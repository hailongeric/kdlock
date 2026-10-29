// SPDX-License-Identifier: GPL-2.0
/* A bounded immediate execution window, not queue-wide pinning. The queue
 * reservation keeps each node live until result wake; the batch source lease
 * separately keeps executable text live through final retirement.
 * Every selected origin must ACK even when preparation/refusal closes the window.
 * Only the current request may survive a dispatcher or ownership boundary. */
/* Slots hold exact invocation identities. Advancing a private cursor avoids
 * copying overlapping descriptors through a library memmove on every body.
 * Empty windows may retain any valid head; all inactive node slots are NULL. */
static __always_inline unsigned int
kd_mutex_batch_pin_slot(struct kd_mutex_batch *batch, unsigned int offset)
{
	BUG_ON(batch->pin_head >= KD_MUTEX_PIN_WINDOW ||
	       offset >= KD_MUTEX_PIN_WINDOW);
	return (batch->pin_head + offset) % KD_MUTEX_PIN_WINDOW;
}

/* index is a physical slot returned by kd_mutex_batch_pin_slot(). */
static __always_inline void kd_mutex_batch_pin_check(struct kd_mutex_batch *batch,
				     unsigned int index)
{
	struct kd_mutex_node *node = batch->pins[index].node;

	BUG_ON(!node || READ_ONCE(node->counted_lock) != batch->lock ||
	       READ_ONCE(node->count_seq) != batch->pins[index].generation);
}

static __always_inline bool kd_mutex_batch_pin_add(struct kd_mutex_batch *batch,
				   struct kd_mutex_node *node)
{
	unsigned int count = batch->nr_pins, index;
	u64 generation = READ_ONCE(node->count_seq);

	BUG_ON(count >= KD_MUTEX_PIN_WINDOW || (generation & 1) ||
	       READ_ONCE(node->counted_lock) != batch->lock);
	index = kd_mutex_batch_pin_slot(batch, count);
	BUG_ON(batch->pins[index].node);
	if (!kd_mutex_proxy_request(node))
		return false;
	batch->pins[index].node = node;
	batch->pins[index].generation = generation;
	batch->nr_pins = count + 1;
	return true;
}

/* Dropping a REQUEST without its ACK could race a late origin store and revive
 * a cancelled selection. Wait for PINNED, remove our exact descriptor, then
 * publish WAIT. No descriptor/node access follows a wake or slot reuse. */
static void kd_mutex_batch_unpin(struct kd_mutex_batch *batch, bool keep_current)
{
	unsigned int keep = keep_current && batch->nr_pins ? 1 : 0;

	while (batch->nr_pins > keep) {
		unsigned int count = batch->nr_pins - 1;
		unsigned int index = kd_mutex_batch_pin_slot(batch, count);
		struct kd_mutex_node *node = batch->pins[index].node;

		kd_mutex_batch_pin_check(batch, index);
		kd_mutex_proxy_wait_pinned(node);
		batch->pins[index].node = NULL;
		batch->nr_pins = count;
		smp_store_release(&node->locked, KD_MUTEX_WAIT);
	}
}

/* Forget the completed/native current before result publication. Its pin ends
 * through that existing result protocol; every remaining descriptor is queued. */
static __always_inline void kd_mutex_batch_pin_complete(struct kd_mutex_batch *batch,
					struct kd_mutex_node *node)
{
	unsigned int index = kd_mutex_batch_pin_slot(batch, 0);

	BUG_ON(!batch->nr_pins || batch->pins[index].node != node ||
	       smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_PINNED);
	kd_mutex_batch_pin_check(batch, index);
	batch->pins[index].node = NULL;
	batch->nr_pins--;
	batch->pin_head = (index + 1) % KD_MUTEX_PIN_WINDOW;
}

/* The caller has already incremented counter for current. A deferred prefix
 * may first appear after the locality boundary: clamp to current instead of
 * unsigned underflow, then let the original next-iteration boundary decide. */
static __always_inline void kd_mutex_batch_pin_budget(struct kd_mutex_batch *batch, int counter)
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
static __always_inline bool kd_mutex_batch_pin_select(struct kd_mutex_batch *batch,
				      struct kd_mutex_node *node, bool ahead)
{
	struct kd_mutex_node *next;
	unsigned int i, limit = batch->pin_budget;

	if (batch->nr_pins) {
		unsigned int index = kd_mutex_batch_pin_slot(batch, 0);

		BUG_ON(batch->pins[index].node != node);
		kd_mutex_batch_pin_check(batch, index);
	} else if (!kd_mutex_batch_pin_add(batch, node)) {
		return false;
	}
	if (!ahead)
		return true;
	if (limit > KD_MUTEX_PIN_WINDOW)
		limit = KD_MUTEX_PIN_WINDOW;
	while (batch->nr_pins < limit) {
		unsigned int count = batch->nr_pins;
		struct kd_mutex_node *last;
		int cpu;

		/* Successful current selection established a nonempty window.
		 * Keep the index bound explicit at this dereference, including
		 * compile-time one-body policy configurations. */
		BUG_ON(!count || count > KD_MUTEX_PIN_WINDOW);
		last = batch->pins[kd_mutex_batch_pin_slot(batch, count - 1)].node;
		next = smp_load_acquire(&last->next);
		if (!next || next->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
		    next->packet_state != KD_PACKET_MINIMAL ||
		    READ_ONCE(next->regs.ip) != READ_ONCE(node->regs.ip) ||
		    (batch->numa_node >= 0 && next->numa_node != batch->numa_node) ||
		    (batch->deferred_head && !smp_load_acquire(&next->next)))
			break;
		cpu = next->tail >> KD_MUTEX_TAIL_CPU_OFFSET;
		for (i = 0; i < batch->nr_pins; i++) {
			unsigned int index = kd_mutex_batch_pin_slot(batch, i);

			if ((batch->pins[index].node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) == cpu)
				return true;
		}
		if (!kd_mutex_batch_pin_add(batch, next))
			break;
	}
	/* The next refill is three requests beyond the ordinary successor hint.
	 * While this owner retains the queue, a published forward link cannot
	 * retire before our wake. Hint only that one node's metadata lines; do
	 * not read its fields/stack, select it, or retain it across body execution.
	 * Every admission, identity and WAIT check still runs on the next refill. */
	if (batch->nr_pins == KD_MUTEX_PIN_WINDOW) {
		struct kd_mutex_node *last = batch->pins[
			kd_mutex_batch_pin_slot(batch, KD_MUTEX_PIN_WINDOW - 1)].node;

		next = smp_load_acquire(&last->next);
		if (next) {
			prefetch(next);
			prefetch(&next->entry_abi);
			prefetch(&next->regs);
			prefetch(&next->locked);
		}
	}
	return true;
}
