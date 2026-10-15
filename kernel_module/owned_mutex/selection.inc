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

/* FIFO dispatch already binds the exact image before attempting a claim. */
static struct kd_owned_mutex_node *kd_owned_mutex_select(struct kd_owned_mutex_batch *batch)
{
	struct kd_owned_mutex_waiter *waiter = list_first_entry(
		&batch->pending, struct kd_owned_mutex_waiter, list);
	struct kd_owned_mutex_node *node;

	if (waiter->kind != KD_OWNED_MUTEX_DELEGATE)
		return NULL;
	node = container_of(waiter, struct kd_owned_mutex_node, waiter);
	batch->image = kd_owned_mutex_candidate(node, &batch->exe);
	return batch->image ? node : NULL;
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
