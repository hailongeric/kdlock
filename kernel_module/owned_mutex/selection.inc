/* Only the physical combiner inspects its private list. Unselected nodes stay
 * linked in their original order; their bypass counts survive queue rejoin. */
#define KD_OWNED_MUTEX_WINDOW 8U
#define KD_OWNED_MUTEX_MAX_BYPASSES 4U

static const struct kd_jit_image *
kd_owned_mutex_candidate(struct kd_owned_mutex_node *node, struct kd_exe_info **exe)
{
	const struct kd_jit_image *image;

	*exe = kd_exe_find_ready(0, node->saved_ret_addr);
	image = kd_image_current(*exe);
	if (!image || image->entry_abi != node->entry_abi)
		return NULL;
	if (image->requirements & KD_IMAGE_ORIGIN_SPIN) {
		if (!owned_mutex_origin_spin || node->origin_cpu == raw_smp_processor_id() ||
		    smp_load_acquire(&node->readiness) != KD_ORIGIN_READY)
			return NULL;
	}
	return image;
}

static struct kd_owned_mutex_node *kd_owned_mutex_select(struct kd_owned_mutex_batch *batch)
{
	struct kd_owned_mutex_waiter *waiter;
	struct kd_owned_mutex_node *best = NULL;
	unsigned int inspected = 0;
	bool best_local = false;

	list_for_each_entry(waiter, &batch->pending, list) {
		struct kd_owned_mutex_node *node;
		struct kd_exe_info *exe;
		const struct kd_jit_image *image;
		bool local;

		if (inspected++ == (owned_mutex_numa ? KD_OWNED_MUTEX_WINDOW : 1U) ||
		    waiter->kind != KD_OWNED_MUTEX_DELEGATE)
			break;
		node = container_of(waiter, struct kd_owned_mutex_node, waiter);
		image = kd_owned_mutex_candidate(node, &exe);
		local = node->numa_node == numa_node_id();
		/* A saturated request cannot be passed again. Earlier requests may
		 * still run; if it is the head and ineligible, the caller rejoins and
		 * releases to that head through KD's ordinary local-owner protocol. */
		if (image && (!best || (!best_local && local))) {
			best = node;
			best_local = local;
			batch->exe = exe;
			batch->image = image;
		}
		if (node->bypasses >= KD_OWNED_MUTEX_MAX_BYPASSES)
			break;
	}
	return best;
}

static void kd_owned_mutex_note_dispatch(struct kd_owned_mutex_batch *batch,
					struct kd_owned_mutex_node *selected)
{
	struct kd_owned_mutex_waiter *waiter;

	list_for_each_entry(waiter, &batch->pending, list) {
		struct kd_owned_mutex_node *node;

		if (waiter == &selected->waiter)
			break;
		BUG_ON(waiter->kind != KD_OWNED_MUTEX_DELEGATE);
		node = container_of(waiter, struct kd_owned_mutex_node, waiter);
		BUG_ON(node->bypasses >= KD_OWNED_MUTEX_MAX_BYPASSES);
		node->bypasses++;
		this_cpu_inc(kd_owned_mutex_bypasses);
	}
}

static void kd_owned_mutex_prepare_successor(struct kd_owned_mutex_batch *batch,
					    struct kd_owned_mutex_node *selected)
{
	struct kd_owned_mutex_waiter *waiter;
	unsigned int inspected = 0;

	if (!owned_mutex_origin_spin)
		return;
	list_for_each_entry(waiter, &batch->pending, list) {
		struct kd_owned_mutex_node *node;
		const struct kd_jit_image *image;

		if (inspected++ == KD_OWNED_MUTEX_WINDOW || waiter->kind != KD_OWNED_MUTEX_DELEGATE)
			break;
		node = container_of(waiter, struct kd_owned_mutex_node, waiter);
		if (node == selected)
			continue;
		image = kd_image_current(kd_exe_find_ready(0, node->saved_ret_addr));
		if (image && (image->requirements & KD_IMAGE_ORIGIN_SPIN) &&
		    node->origin_cpu != raw_smp_processor_id()) {
			kd_owned_mutex_request_ready(node);
			break;
		}
		if (node->bypasses >= KD_OWNED_MUTEX_MAX_BYPASSES)
			break;
	}
}
