// SPDX-License-Identifier: GPL-2.0
/* One exact current claim under the enclosing proxy epoch. COMBINER prevents
 * every READY origin from withdrawing, so future claims are unnecessary for
 * pin safety. Queue reservation protects node storage; the batch source lease
 * separately protects executable text until final retirement.
 * No descriptor is carried across queue handoff or a completed-node wake. */
static __always_inline void kd_mutex_batch_pin_check(struct kd_mutex_batch *batch)
{
	struct kd_mutex_node *node = batch->pin.node;

	BUG_ON(batch->nr_pins != 1 || !node ||
	       READ_ONCE(node->counted_lock) != batch->lock ||
	       READ_ONCE(node->count_seq) != batch->pin.generation);
}

static __always_inline bool kd_mutex_batch_pin_add(struct kd_mutex_batch *batch,
				   struct kd_mutex_node *node)
{
	u64 generation = READ_ONCE(node->count_seq);

	BUG_ON(batch->nr_pins || batch->pin.node || (generation & 1) ||
	       READ_ONCE(node->counted_lock) != batch->lock || !batch->proxy_epoch);
	if (!kd_mutex_proxy_request(batch->lock, node))
		return false;
	batch->pin.node = node;
	batch->pin.generation = generation;
	batch->nr_pins = 1;
	KD_MUTEX_PIN_INC(batch, claims);
	return true;
}

/* Release only an unexecuted current that no frame still uses. A real current
 * frame or completed-tail continuation retains its exact CLAIMED pin while
 * epoch closure separately allows every unselected READY origin to withdraw. */
static void kd_mutex_batch_unpin(struct kd_mutex_batch *batch, bool keep_current)
{
	struct kd_mutex_node *node;
	unsigned int keep = keep_current && batch->nr_pins ? 1 : 0;

	BUG_ON(batch->nr_pins > 1 || (!batch->nr_pins && batch->pin.node));
	KD_MUTEX_PIN_DRAIN(batch, keep);
	if (!batch->nr_pins)
		return;
	node = batch->pin.node;
	kd_mutex_batch_pin_check(batch);
	KD_MUTEX_PIN_ASSERT(batch, node);
	if (keep)
		return;
	batch->pin.node = NULL;
	batch->nr_pins = 0;
	KD_MUTEX_PIN_INC(batch, cancelled_claims);
	/* Last access: the origin may unpin after observing this publication. */
	smp_store_release(&node->locked, KD_MUTEX_WAIT);
}

/* Clear the exact descriptor before result publication can release/reuse its
 * node. Neither completion nor native/role handoff leaves a future claim. */
static __always_inline void kd_mutex_batch_pin_complete(struct kd_mutex_batch *batch,
					struct kd_mutex_node *node)
{
	BUG_ON(batch->nr_pins != 1 || batch->pin.node != node ||
	       smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_CLAIMED);
	kd_mutex_batch_pin_check(batch);
	batch->pin.node = NULL;
	batch->nr_pins = 0;
	KD_MUTEX_PIN_INC(batch, retired_claims);
}

/* Each ordinary iteration claims its own current anew. Same-CPU refusal and
 * exact lock/generation checks remain; no future-node walk, response wait or
 * queue reordering is needed to establish this current's readiness. */
static __always_inline bool kd_mutex_batch_pin_select(struct kd_mutex_batch *batch,
				      struct kd_mutex_node *node)
{
	BUG_ON(batch->nr_pins || batch->pin.node);
	KD_MUTEX_PIN_BEGIN(batch);
	if ((node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1 == raw_smp_processor_id()) {
		KD_MUTEX_PIN_STOP(batch, KD_MUTEX_PIN_SELF_CURRENT);
		KD_MUTEX_PIN_END(batch);
		return false;
	}
	if (!kd_mutex_batch_pin_add(batch, node)) {
		KD_MUTEX_PIN_STOP(batch, KD_MUTEX_PIN_CURRENT_NOT_READY);
		KD_MUTEX_PIN_END(batch);
		return false;
	}
	KD_MUTEX_PIN_STOP(batch, KD_MUTEX_PIN_CLAIMED);
	KD_MUTEX_PIN_END(batch);
	return true;
}
