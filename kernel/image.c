// SPDX-License-Identifier: GPL-2.0-only
/* RCU lookup plus exact image users that can outlive a read-side section. */
#include <linux/compiler.h>
#include <linux/errno.h>

#include "image.h"

static bool use_kind_valid(enum kd_jit_image_use_kind kind)
{
	return kind == KD_JIT_IMAGE_USE_EXECUTION ||
	       kind == KD_JIT_IMAGE_USE_RETURN || kind == KD_JIT_IMAGE_USE_SOURCE;
}

static const struct kd_jit_image *current_locked(struct kd_jit_image_slot *slot)
{
	return rcu_dereference_protected(slot->image, lockdep_is_held(&slot->guard));
}

void kd_jit_image_slot_init(struct kd_jit_image_slot *slot,
			    const struct kd_jit_image *initial)
{
	raw_spin_lock_init(&slot->guard);
	RCU_INIT_POINTER(slot->image, initial);
	INIT_LIST_HEAD(&slot->users);
	slot->update = NULL;
	slot->closing = false;
}

void kd_jit_image_use_init(struct kd_jit_image_use *use)
{
	INIT_LIST_HEAD(&use->slot_link);
	use->slot = NULL;
	use->image = NULL;
	use->state = NULL;
	use->holder = NULL;
	use->consumer = NULL;
	use->kind = KD_JIT_IMAGE_USE_UNUSED;
	use->linked = false;
}

void kd_jit_image_update_init(struct kd_jit_image_update *update)
{
	update->slot = NULL;
	update->expected_old = NULL;
	update->candidate = NULL;
	update->owner_identity = NULL;
	update->phase = KD_JIT_IMAGE_UPDATE_PRIVATE;
}

static int link_use_locked(struct kd_jit_image_slot *slot,
			    struct kd_jit_image_use *use,
			    const struct kd_jit_image *image,
			    struct kd_thread_state *state, const void *holder,
			    enum kd_jit_image_use_kind kind)
{
	if (use->slot || use->linked || !list_empty(&use->slot_link))
		return -EALREADY;
	use->slot = slot;
	use->image = image;
	use->state = state;
	use->holder = holder;
	use->consumer = NULL;
	use->kind = kind;
	use->linked = true;
	list_add_tail(&use->slot_link, &slot->users);
	return 0;
}

int kd_jit_image_lookup(struct kd_jit_image_slot *slot,
			struct kd_jit_image_use *use,
			struct kd_thread_state *state, const void *holder,
			enum kd_jit_image_use_kind kind)
{
	const struct kd_jit_image *image;
	int result;

	if (!slot || !use || !state || !holder || !use_kind_valid(kind))
		return -EINVAL;
	rcu_read_lock();
	image = rcu_dereference(slot->image);
	raw_spin_lock(&slot->guard);
	if (slot->closing || current_locked(slot) != image)
		result = -EAGAIN;
	else if (!image)
		result = -ENOENT;
	else
		result = link_use_locked(slot, use, image, state, holder, kind);
	raw_spin_unlock(&slot->guard);
	rcu_read_unlock();
	return result;
}

int kd_jit_image_use_extend(struct kd_jit_image_use *parent,
			    const void *parent_holder,
			    struct kd_jit_image_use *child,
			    const void *child_holder,
			    enum kd_jit_image_use_kind kind)
{
	struct kd_jit_image_slot *slot;
	int result;

	if (!parent || !parent_holder || !child || child == parent ||
	    !child_holder || !use_kind_valid(kind))
		return -EINVAL;
	slot = READ_ONCE(parent->slot);
	if (!slot)
		return -ESTALE;
	raw_spin_lock(&slot->guard);
	if (parent->slot != slot || !parent->linked ||
	    parent->holder != parent_holder || !parent->image || !parent->state ||
	    parent->image != current_locked(slot))
		result = -ESTALE;
	else
		/* Closing cannot strand an already-admitted descendant/return. */
		result = link_use_locked(slot, child, parent->image, parent->state,
					 child_holder, kind);
	raw_spin_unlock(&slot->guard);
	return result;
}

static void unlink_use_locked(struct kd_jit_image_use *use)
{
	list_del_init(&use->slot_link);
	use->linked = false;
	use->image = NULL;
	use->state = NULL;
	use->holder = NULL;
	use->consumer = NULL;
	use->kind = KD_JIT_IMAGE_USE_UNUSED;
	WRITE_ONCE(use->slot, NULL);
}

int kd_jit_image_use_prepare_exit(struct kd_jit_image_use *execution,
				   const void *execution_holder,
				   struct kd_thread_state *state,
				   struct kd_jit_image_use *exit_use,
				   const void *exit_holder,
				   const struct kd_jit_image **image)
{
	struct kd_jit_image_slot *slot;
	int result;

	if (!execution || !execution_holder || !state || !exit_use ||
	    exit_use == execution || !exit_holder || !image)
		return -EINVAL;
	*image = NULL;
	slot = READ_ONCE(execution->slot);
	if (!slot)
		return -ESTALE;
	raw_spin_lock(&slot->guard);
	if (execution->slot != slot || !execution->linked ||
	    execution->holder != execution_holder || execution->state != state ||
	    execution->kind != KD_JIT_IMAGE_USE_EXECUTION || execution->consumer ||
	    !execution->image || execution->image != current_locked(slot)) {
		result = -ESTALE;
	} else {
		result = link_use_locked(slot, exit_use, execution->image, state,
					 exit_holder, KD_JIT_IMAGE_USE_SOURCE);
		if (!result) {
			exit_use->consumer = state;
			*image = exit_use->image;
		}
	}
	raw_spin_unlock(&slot->guard);
	return result;
}

static bool exit_matches_locked(struct kd_jit_image_slot *slot,
				struct kd_jit_image_use *use,
				const void *holder, struct kd_thread_state *state)
{
	return use->slot == slot && use->linked && use->holder == holder &&
	       use->state == state && use->consumer == state &&
	       use->kind == KD_JIT_IMAGE_USE_SOURCE && use->image &&
	       use->image == current_locked(slot);
}

int kd_jit_image_use_check_exit(struct kd_jit_image_use *exit_use,
				 const void *exit_holder,
				 struct kd_thread_state *state,
				 const struct kd_jit_image **image)
{
	struct kd_jit_image_slot *slot;
	int result = 0;

	if (!exit_use || !exit_holder || !state || !image)
		return -EINVAL;
	*image = NULL;
	slot = READ_ONCE(exit_use->slot);
	if (!slot)
		return -ESTALE;
	raw_spin_lock(&slot->guard);
	if (!exit_matches_locked(slot, exit_use, exit_holder, state))
		result = -ESTALE;
	else
		*image = exit_use->image;
	raw_spin_unlock(&slot->guard);
	return result;
}

int kd_jit_image_use_finish_exit(struct kd_jit_image_use *exit_use,
				  const void *exit_holder,
				  struct kd_thread_state *state)
{
	struct kd_jit_image_slot *slot;
	int result = 0;

	if (!exit_use || !exit_holder || !state)
		return -EINVAL;
	slot = READ_ONCE(exit_use->slot);
	if (!slot)
		return -ESTALE;
	raw_spin_lock(&slot->guard);
	if (!exit_matches_locked(slot, exit_use, exit_holder, state))
		result = -ESTALE;
	else
		unlink_use_locked(exit_use);
	/* No exit_use/image access follows successful unlink. */
	raw_spin_unlock(&slot->guard);
	return result;
}

int kd_jit_image_use_put(struct kd_jit_image_use *use, const void *holder)
{
	struct kd_jit_image_slot *slot;
	int result = 0;

	if (!use || !holder)
		return -EINVAL;
	slot = READ_ONCE(use->slot);
	if (!slot)
		return -ESTALE;
	raw_spin_lock(&slot->guard);
	if (use->slot != slot || !use->linked || use->holder != holder) {
		result = -ESTALE;
	} else if (use->consumer) {
		result = -EBUSY;
	} else {
		unlink_use_locked(use);
		/* The last exact user may now permit publication/reclamation.
		 * Unlock uses the retained slot only, never the dropped use/image.
		 */
	}
	raw_spin_unlock(&slot->guard);
	return result;
}

int kd_jit_image_update_begin(struct kd_jit_image_slot *slot,
			      struct kd_jit_image_update *update,
			      const struct kd_jit_image *expected_old,
			      const struct kd_jit_image *candidate,
			      const void *owner_identity)
{
	int result = 0;

	if (!slot || !update || !candidate || !owner_identity ||
	    candidate == expected_old)
		return -EINVAL;
	/* Caller owns fresh private transaction storage until this publication. */
	if (update->slot || update->phase != KD_JIT_IMAGE_UPDATE_PRIVATE)
		return -EALREADY;
	raw_spin_lock(&slot->guard);
	if (slot->closing || slot->update)
		result = -EBUSY;
	else if (current_locked(slot) != expected_old)
		result = -ESTALE;
	else {
		update->expected_old = expected_old;
		update->candidate = candidate;
		update->owner_identity = owner_identity;
		update->phase = KD_JIT_IMAGE_UPDATE_CLOSING;
		WRITE_ONCE(update->slot, slot);
		slot->update = update;
		slot->closing = true;
	}
	raw_spin_unlock(&slot->guard);
	return result;
}

static bool update_matches_locked(struct kd_jit_image_slot *slot,
				   struct kd_jit_image_update *update,
				   const void *owner_identity)
{
	return slot->update == update && slot->closing &&
	       update->slot == slot && update->owner_identity == owner_identity;
}

int kd_jit_image_update_try_commit(struct kd_jit_image_update *update,
				   const void *owner_identity,
				   const struct kd_jit_image **retired)
{
	struct kd_jit_image_slot *slot;
	const struct kd_jit_image *old;
	int result = 0;

	if (!update || !owner_identity || !retired)
		return -EINVAL;
	*retired = NULL;
	slot = READ_ONCE(update->slot);
	if (!slot)
		return -ESTALE;
	raw_spin_lock(&slot->guard);
	if (!update_matches_locked(slot, update, owner_identity))
		result = -ESTALE;
	else if (update->phase != KD_JIT_IMAGE_UPDATE_CLOSING)
		result = -EALREADY;
	else if (current_locked(slot) != update->expected_old)
		result = -ESTALE;
	else if (!list_empty(&slot->users))
		result = -EBUSY;
	else {
		old = update->expected_old;
		rcu_assign_pointer(slot->image, update->candidate);
		update->phase = KD_JIT_IMAGE_UPDATE_GRACE;
	}
	raw_spin_unlock(&slot->guard);
	if (result)
		return result;

	/* Sleeping source/return users have drained by exact membership. RCU
	 * separately closes old lookup readers; it never substitutes for them.
	 */
	synchronize_rcu();
	raw_spin_lock(&slot->guard);
	if (!update_matches_locked(slot, update, owner_identity) ||
	    update->phase != KD_JIT_IMAGE_UPDATE_GRACE ||
	    current_locked(slot) != update->candidate) {
		result = -ESTALE;
	} else {
		update->phase = KD_JIT_IMAGE_UPDATE_COMMITTED;
		slot->update = NULL;
		slot->closing = false;
	}
	raw_spin_unlock(&slot->guard);
	if (result)
		return result;
	*retired = old;
	return 0;
}

int kd_jit_image_update_abort(struct kd_jit_image_update *update,
			      const void *owner_identity)
{
	struct kd_jit_image_slot *slot;
	int result = 0;

	if (!update || !owner_identity)
		return -EINVAL;
	slot = READ_ONCE(update->slot);
	if (!slot)
		return -ESTALE;
	raw_spin_lock(&slot->guard);
	if (!update_matches_locked(slot, update, owner_identity))
		result = -ESTALE;
	else if (update->phase != KD_JIT_IMAGE_UPDATE_CLOSING)
		result = -EBUSY;
	else if (current_locked(slot) != update->expected_old)
		result = -ESTALE;
	else {
		update->phase = KD_JIT_IMAGE_UPDATE_ABORTED;
		slot->update = NULL;
		slot->closing = false;
	}
	raw_spin_unlock(&slot->guard);
	return result;
}
