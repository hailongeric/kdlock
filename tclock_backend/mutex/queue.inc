/* SPDX-License-Identifier: GPL-2.0 */
/* NUMA deferred queue selection and caller-stack hints; successor storage must remain live. */
#ifdef NUMA_AWARE
__always_inline static void add_to_local_queue(struct komb_mutex_node *node)
{
	struct komb_mutex_node **head, **tail;

	head = (struct komb_mutex_node **)(&tc_mutex_current()->komb_local_queue_head);
	tail = (struct komb_mutex_node **)(&tc_mutex_current()->komb_local_queue_tail);

	if (*head == NULL) {
		*head = node;
		*tail = node;
	} else {
		(*tail)->next = node;
		*tail = node;
	}
}
#endif

__always_inline static struct komb_mutex_node *
get_next_node(struct komb_mutex_node *my_node)
{
#ifdef NUMA_AWARE
	struct komb_mutex_node *curr_node, *next_node;

	curr_node = my_node;
	next_node = curr_node->next;

	while (true) {
		if (next_node == NULL || next_node->next == NULL)
			goto next_node_null;

		if (next_node->socket_id == numa_node_id()) {
			void *rsp_ptr = (void *)next_node->rsp;
			prefetchw(rsp_ptr);
			prefetchw(rsp_ptr + 64);
			prefetchw(rsp_ptr + 128);
			prefetchw(rsp_ptr + 192);
			prefetchw(rsp_ptr + 256);
			prefetchw(rsp_ptr + 320);

			prefetch(next_node->next);

			return next_node;
		}

		add_to_local_queue(next_node);
		curr_node = next_node;
		next_node = curr_node->next;
	}

next_node_null:
	return next_node;
#else
	return my_node->next;
#endif
}
