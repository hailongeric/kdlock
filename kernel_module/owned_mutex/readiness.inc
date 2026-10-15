/* READY is published only by the migration/preemption-pinned origin. The
 * competing CAS is the exclusive scheduling/body boundary; neither a wake nor
 * elapsed polling budget grants permission to run or revoke a claim. */
static bool kd_owned_mutex_withdraw(struct kd_owned_mutex_node *node)
{
	u32 state = smp_load_acquire(&node->readiness);

	for (;;) {
		if (state == KD_ORIGIN_CLAIMED)
			return false;
		if (state != KD_ORIGIN_READY && state != KD_ORIGIN_REQUESTED)
			return true;
		if (try_cmpxchg(&node->readiness, &state, KD_ORIGIN_PARKABLE))
			return true;
	}
}

static void kd_owned_mutex_acknowledge(struct kd_owned_mutex_node *node)
{
	/* Caller has both pins, and checks its budget and reschedule request. */
	BUG_ON(!preempt_count() || node->origin_cpu != raw_smp_processor_id());
	cmpxchg_release(&node->readiness, KD_ORIGIN_REQUESTED, KD_ORIGIN_READY);
}

static bool kd_owned_mutex_claim(struct kd_owned_mutex_node *node,
				const struct kd_jit_image *image)
{
	if (!(image->requirements & KD_IMAGE_ORIGIN_SPIN))
		return true;
	if (!owned_mutex_origin_spin || node->origin_cpu == raw_smp_processor_id() ||
	    cmpxchg_acquire(&node->readiness, KD_ORIGIN_READY, KD_ORIGIN_CLAIMED) != KD_ORIGIN_READY) {
		this_cpu_inc(kd_owned_mutex_claim_failures);
		return false;
	}
	this_cpu_inc(kd_owned_mutex_claims);
	return true;
}

static void kd_owned_mutex_finish_claim(struct kd_owned_mutex_node *node, bool executed)
{
	if (READ_ONCE(node->readiness) == KD_ORIGIN_CLAIMED)
		smp_store_release(&node->readiness,
			executed ? KD_ORIGIN_FINISHED : KD_ORIGIN_PARKABLE);
}

static void kd_owned_mutex_request_ready(struct kd_owned_mutex_node *node)
{
	if (node->origin_cpu == raw_smp_processor_id() || !owned_mutex_origin_spin)
		return;
	if (cmpxchg(&node->readiness, KD_ORIGIN_PARKABLE, KD_ORIGIN_REQUESTED) == KD_ORIGIN_PARKABLE) {
		this_cpu_inc(kd_owned_mutex_preparations);
		/* Task and wait storage remain reserved until the outcome. Paired
		 * with the waiter's state barrier even when this precedes sleeping. */
		smp_mb();
		rcuwait_wake_up(node->wait);
	}
}
