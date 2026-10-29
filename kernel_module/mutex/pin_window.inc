// SPDX-License-Identifier: GPL-2.0
/* One exact current descriptor under the enclosing proxy epoch. COMBINER
 * protects READY during ordinary execution; CLAIMED retains a current across
 * cold epoch closure. Queue reservation protects node storage; the batch lease
 * separately protects executable text until final retirement.
 * No descriptor is carried across queue handoff or a completed-node wake. */
static __always_inline void kd_mutex_batch_pin_check(struct kd_mutex_batch *batch)
{
	struct kd_mutex_node *node = batch->pin.node;

	BUG_ON(batch->nr_pins != 1 || !node ||
	       READ_ONCE(node->counted_lock) != batch->lock ||
	       READ_ONCE(node->count_seq) != batch->pin.generation);
}

/* Shared only within a fresh READY proof. This private predicate is not a
 * cached capability: each use reads current's actual physical owner and phase. */
static __always_inline bool kd_mutex_batch_ready_owned(struct kd_mutex_batch *batch)
{
	return batch->proxy_epoch && !batch->outer.released &&
		kd_mutex_delegation_owned(batch->lock, current) &&
		kd_mutex_gate_read(batch->lock) == KD_MUTEX_GATE_COMBINER;
}

/* A later owner's COMBINER phase cannot authorize this old frame. READY needs
 * this private epoch and its actual physical owner; CLAIMED already carries
 * an independent pin through cold services, early release and owner transfer. */
static __always_inline void
kd_mutex_batch_pin_assert(struct kd_mutex_batch *batch, struct kd_mutex_node *node)
{
	u8 state;

	BUG_ON(batch->pin.node != node);
	kd_mutex_batch_pin_check(batch);
	state = smp_load_acquire(&node->locked);
	if (state == KD_MUTEX_PROXY_READY) {
		BUG_ON(!kd_mutex_batch_ready_owned(batch));
	} else {
		BUG_ON(state != KD_MUTEX_PROXY_CLAIMED);
	}
}

/* Cold callers must not let the dual READY proof conceal a missed epoch close.
 * Physical ownership may legitimately have moved after this retained pin was
 * established; exact descriptor identity and CLAIMED remain mandatory. */
static __always_inline void
kd_mutex_batch_pin_assert_retained(struct kd_mutex_batch *batch,
				   struct kd_mutex_node *node)
{
	BUG_ON(batch->proxy_epoch || batch->pin.node != node);
	kd_mutex_batch_pin_check(batch);
	kd_mutex_proxy_assert_claimed(node);
}

/* A native outer callback can arrive after result0 already removed the node
 * descriptor. Check saved batch state only in that case, never its old node. */
static __always_inline void kd_mutex_batch_assert_cold(struct kd_mutex_batch *batch)
{
	BUG_ON(batch->proxy_epoch);
	if (batch->nr_pins)
		kd_mutex_batch_pin_assert_retained(batch, batch->pin.node);
	else
		BUG_ON(batch->pin.node);
}

static __always_inline bool kd_mutex_batch_pin_add(struct kd_mutex_batch *batch,
				   struct kd_mutex_node *node)
{
	u64 generation = READ_ONCE(node->count_seq);

	BUG_ON(batch->nr_pins || batch->pin.node || (generation & 1) ||
	       READ_ONCE(node->counted_lock) != batch->lock || !batch->proxy_epoch ||
	       batch->outer.released);
	if (!kd_mutex_proxy_request(batch->lock, node))
		return false;
	batch->pin.node = node;
	batch->pin.generation = generation;
	batch->nr_pins = 1;
	/* Capture alone is not stable identity. Re-read the exact counted key and
	 * generation after READY, before any borrowed origin state is prepared. */
	kd_mutex_batch_pin_check(batch);
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
	if (keep) {
		/* Promotion precedes the gate's release of withdrawal exclusion. A
		 * later expiry CAS then sees CLAIMED and cannot abandon this pin. */
		if (smp_load_acquire(&node->locked) == KD_MUTEX_PROXY_READY)
			smp_store_release(&node->locked, KD_MUTEX_PROXY_CLAIMED);
		return;
	}
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
	kd_mutex_batch_pin_assert(batch, node);
	batch->pin.node = NULL;
	batch->nr_pins = 0;
	KD_MUTEX_PIN_INC(batch, retired_claims);
}

static __always_inline void
kd_mutex_batch_pin_complete_retained(struct kd_mutex_batch *batch,
				     struct kd_mutex_node *node)
{
	kd_mutex_batch_pin_assert_retained(batch, node);
	kd_mutex_batch_pin_complete(batch, node);
}

/* This uninterrupted inline chain supplies the complete admission proof once:
 * private epoch/unreleased outer, exact owner excluding PICKUP, COMBINER,
 * different CPU, acquire READY, and a stable counted key/generation. Only
 * private diagnostic bookkeeping follows before the caller's first origin use.
 * Execution and every cold boundary still require their own fresh proof. */
static __always_inline bool kd_mutex_batch_pin_select(struct kd_mutex_batch *batch,
				      struct kd_mutex_node *node)
{
	KD_MUTEX_PIN_BEGIN(batch);
	if (!kd_mutex_batch_pin_add(batch, node)) {
		/* Preserve the refusal reason without a duplicate CPU check on the
		 * successful path. No descriptor or origin access was admitted. */
		if ((node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1 == raw_smp_processor_id())
			KD_MUTEX_PIN_STOP(batch, KD_MUTEX_PIN_SELF_CURRENT);
		else
			KD_MUTEX_PIN_STOP(batch, KD_MUTEX_PIN_CURRENT_NOT_READY);
		KD_MUTEX_PIN_END(batch);
		return false;
	}
	BUG_ON(batch->pin.node != node);
	KD_MUTEX_PIN_STOP(batch, KD_MUTEX_PIN_CLAIMED);
	KD_MUTEX_PIN_END(batch);
	return true;
}
