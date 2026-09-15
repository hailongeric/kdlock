// SPDX-License-Identifier: GPL-2.0
/*
 * Frame lock-vector mutations and completion predicates; this never acquires L.
 * Private implementation included only by kd_exec.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

int kd_exec_frame_set_lock_entries(struct kd_exec_frame *frame,
				   const unsigned long *lock_addr,
				   const enum kd_exec_lock_kind *lock_kind,
				   void *const *lock_node,
				   const bool *lock_released,
				   unsigned int depth)
{
	unsigned int i;
	unsigned int outer_index = KD_EXEC_MAX_LOCK_DEPTH;

	if (!frame || (depth && !lock_addr))
		return -EINVAL;
	if (depth > KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;
	for (i = 0; i < depth; i++) {
		unsigned int j;

		if (!lock_addr[i])
			return -EINVAL;
		if (lock_kind && (lock_kind[i] <= KD_EXEC_LOCK_NONE ||
				  lock_kind[i] > KD_EXEC_LOCK_NATIVE))
			return -EINVAL;
		for (j = 0; j < i; j++)
			if (lock_addr[j] == lock_addr[i])
				return -EDEADLK;
		if (lock_addr[i] == frame->outer_lock_addr)
			outer_index = i;
	}
	if (frame->outer_lock_addr && outer_index == KD_EXEC_MAX_LOCK_DEPTH)
		return -ENOENT;

	memset(frame->jit_lock_addr, 0, sizeof(frame->jit_lock_addr));
	memset(frame->jit_lock_kind, 0, sizeof(frame->jit_lock_kind));
	memset(frame->jit_lock_node, 0, sizeof(frame->jit_lock_node));
	memset(frame->jit_lock_released, 0, sizeof(frame->jit_lock_released));
	for (i = 0; i < depth; i++) {
		frame->jit_lock_addr[i] = lock_addr[i];
		frame->jit_lock_kind[i] = lock_kind ? lock_kind[i] :
						      KD_EXEC_LOCK_QUEUE_OWNER;
		frame->jit_lock_node[i] = lock_node ? lock_node[i] : NULL;
		frame->jit_lock_released[i] = lock_released ? lock_released[i] :
							      false;
	}
	frame->jit_lock_depth = depth;
	frame->outer_lock_index = outer_index;
	return kd_exec_frame_validate(frame) ? 0 : kd_exec_invariant_failure();
}

int kd_exec_frame_set_lock_stack(struct kd_exec_frame *frame,
				 const unsigned long *lock_addr,
				 unsigned int depth)
{
	return kd_exec_frame_set_lock_entries(frame, lock_addr, NULL, NULL,
					      NULL, depth);
}

int kd_exec_frame_lock_push(struct kd_exec_frame *frame,
			    unsigned long lock_addr,
			    enum kd_exec_lock_kind kind, void *lock_node)
{
	if (!frame || !lock_addr || kind <= KD_EXEC_LOCK_NONE ||
	    kind > KD_EXEC_LOCK_NATIVE || !kd_exec_frame_validate(frame))
		return -EINVAL;
	if (frame->jit_lock_depth >= KD_EXEC_MAX_LOCK_DEPTH)
		return -E2BIG;
	if (kd_exec_frame_lock_contains(frame, lock_addr))
		return -EDEADLK;

	frame->jit_lock_addr[frame->jit_lock_depth] = lock_addr;
	frame->jit_lock_kind[frame->jit_lock_depth] = kind;
	frame->jit_lock_node[frame->jit_lock_depth] = lock_node;
	frame->jit_lock_released[frame->jit_lock_depth] = false;
	frame->jit_lock_depth++;
	frame->held_lock_depth++;
	return 0;
}

unsigned int kd_exec_frame_lock_depth(const struct kd_exec_frame *frame)
{
	if (!frame)
		return 0;
	return frame->jit_lock_depth;
}

int kd_exec_frame_lock_pop(struct kd_exec_frame *frame, unsigned long lock_addr)
{
	unsigned int i, removed;
	bool removed_outer;

	if (!frame || !lock_addr || !frame->jit_lock_depth)
		return -EINVAL;

	for (i = frame->jit_lock_depth; i > 0; i--) {
		if (frame->jit_lock_addr[i - 1] != lock_addr)
			continue;
		removed = i - 1;
		removed_outer = removed == frame->outer_lock_index;

		for (; i < frame->jit_lock_depth; i++) {
			frame->jit_lock_addr[i - 1] = frame->jit_lock_addr[i];
			frame->jit_lock_kind[i - 1] = frame->jit_lock_kind[i];
			frame->jit_lock_node[i - 1] = frame->jit_lock_node[i];
			frame->jit_lock_released[i - 1] =
				frame->jit_lock_released[i];
		}
		frame->jit_lock_addr[frame->jit_lock_depth - 1] = 0;
		frame->jit_lock_kind[frame->jit_lock_depth - 1] =
			KD_EXEC_LOCK_NONE;
		frame->jit_lock_node[frame->jit_lock_depth - 1] = NULL;
		frame->jit_lock_released[frame->jit_lock_depth - 1] = false;
		frame->jit_lock_depth--;
		if (frame->held_lock_depth)
			frame->held_lock_depth--;
		if (removed_outer)
			frame->outer_lock_index = KD_EXEC_MAX_LOCK_DEPTH;
		else if (frame->outer_lock_index > removed &&
			 frame->outer_lock_index < KD_EXEC_MAX_LOCK_DEPTH)
			frame->outer_lock_index--;
		return kd_exec_frame_validate(frame) ?
			       0 :
			       kd_exec_invariant_failure();
	}

	return -ENOENT;
}

int kd_exec_frame_lock_mark_released(struct kd_exec_frame *frame,
				     unsigned long lock_addr)
{
	unsigned int i;

	if (!frame || !lock_addr || !kd_exec_frame_validate(frame))
		return -EINVAL;

	for (i = frame->jit_lock_depth; i > 0; i--) {
		if (frame->jit_lock_addr[i - 1] != lock_addr)
			continue;
		if (frame->jit_lock_released[i - 1])
			return -EALREADY;
		frame->jit_lock_released[i - 1] = true;
		return 0;
	}

	return -ENOENT;
}

enum kd_exec_lock_kind
kd_exec_frame_lock_kind(const struct kd_exec_frame *frame,
			unsigned long lock_addr)
{
	unsigned int i;

	if (!frame || !lock_addr)
		return KD_EXEC_LOCK_NONE;

	for (i = frame->jit_lock_depth; i > 0; i--)
		if (frame->jit_lock_addr[i - 1] == lock_addr)
			return frame->jit_lock_kind[i - 1];

	return KD_EXEC_LOCK_NONE;
}

void *kd_exec_frame_lock_node(const struct kd_exec_frame *frame,
			      unsigned long lock_addr)
{
	unsigned int i;

	if (!frame || !lock_addr)
		return NULL;

	for (i = frame->jit_lock_depth; i > 0; i--)
		if (frame->jit_lock_addr[i - 1] == lock_addr)
			return frame->jit_lock_node[i - 1];

	return NULL;
}

bool kd_exec_frame_lock_contains(const struct kd_exec_frame *frame,
				 unsigned long lock_addr)
{
	unsigned int i;

	if (!frame || !lock_addr)
		return false;

	for (i = 0; i < frame->jit_lock_depth; i++)
		if (frame->jit_lock_addr[i] == lock_addr)
			return true;
	return false;
}

bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)
{
	unsigned int i;

	if (!frame || frame->outer_lock_index >= frame->jit_lock_depth)
		return false;

	for (i = frame->outer_lock_index + 1; i < frame->jit_lock_depth; i++)
		if (!frame->jit_lock_released[i])
			return true;

	return false;
}

bool kd_exec_frame_locks_released(const struct kd_exec_frame *frame)
{
	unsigned int i;

	if (!frame || !frame->outer_unlock_seen ||
	    frame->outer_lock_index >= frame->jit_lock_depth)
		return false;

	for (i = frame->outer_lock_index; i < frame->jit_lock_depth; i++)
		if (!frame->jit_lock_released[i])
			return false;

	return true;
}

bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)
{
	return kd_exec_frame_locks_released(frame) &&
	       !kd_exec_frame_remote_pending(frame);
}
