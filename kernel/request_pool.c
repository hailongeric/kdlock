/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/errno.h>
#include <linux/sched.h>
#include "request_pool.h"

void kd_request_user_init(struct kd_request_user *user)
{
	INIT_LIST_HEAD(&user->link);
	user->slot = NULL;
	user->identity = NULL;
	user->kind = KD_REQUEST_USER_UNUSED;
	user->linked = false;
}

static bool user_idle(const struct kd_request_user *user)
{
	return !user->linked && !user->slot && !user->identity &&
	       user->kind == KD_REQUEST_USER_UNUSED && list_empty(&user->link);
}

static bool image_idle(const struct kd_jit_image_use *use)
{
	return !use->slot && !use->linked && !use->image && !use->state &&
	       !use->holder && !use->consumer &&
	       use->kind == KD_JIT_IMAGE_USE_UNUSED && list_empty(&use->slot_link);
}

/* Only after the exact users ended; their pool-guard releases order these
 * otherwise component-owned idle fields without nesting their component guards.
 */
static bool controls_idle(const struct kd_request_slot *slot)
{
	return list_empty(&slot->users) && !slot->parent &&
	       user_idle(&slot->parent_user) &&
	       image_idle(&slot->execution_use) && image_idle(&slot->exit_use) &&
	       image_idle(&slot->return_use) && image_idle(&slot->source_use) &&
	       (slot->entry.phase == KD_MUTEX_ENTRY_PRIVATE ||
		slot->entry.phase == KD_MUTEX_ENTRY_COMPLETE) &&
	       !slot->owner_batch.progress && !slot->owner_batch.batch &&
	       list_empty(&slot->owner_batch.link);
}

static bool is_slot_binding(const struct kd_request_slot *slot,
			    const struct kd_execution_binding *binding)
{
	/* Compare known addresses only; a sampled current binding is not a hold. */
	return binding == &slot->call.offer || binding == &slot->call.execution ||
	       binding == &slot->call.returned || binding == &slot->capture ||
	       binding == &slot->native_return;
}

static bool matches(const struct kd_request_slot *slot, const void *claim)
{
	return claim && slot->claim == claim && slot->phase != KD_REQUEST_SLOT_FREE;
}

/* For LIVE requests, actual retirement precedes every component-owned read and
 * the current-binding sample. A node result/detach alone is never sufficient.
 * ignored_native is allowed only during the fully drained atomic detach.
 */
static int reusable_locked(struct kd_request_slot *slot,
			   const struct kd_execution_binding *ignored_native)
{
	struct kd_execution_binding *binding;

	if (slot->phase != KD_REQUEST_SLOT_LIVE &&
	    slot->phase != KD_REQUEST_SLOT_RESERVED)
		return -EBUSY;
	if (!list_empty(&slot->users) || slot->parent ||
	    !user_idle(&slot->parent_user))
		return -EBUSY;
	if (slot->phase == KD_REQUEST_SLOT_LIVE) {
		if (!smp_load_acquire(&slot->call.node.retirable))
			return -EAGAIN;
		if (slot->call.grant.linked ||
		    !list_empty(&slot->call.grant.state_link) ||
		    slot->call.possible_batch.initialized)
			return -EBUSY;
	}
	if (!controls_idle(slot))
		return -EBUSY;
	binding = kd_state_current_binding(slot->pool->state);
	if (is_slot_binding(slot, binding) &&
	    !(binding == ignored_native && binding == &slot->native_return))
		return -EBUSY;
	return 0;
}

static void free_locked(struct kd_request_slot *slot)
{
	struct kd_request_pool *pool = slot->pool;

	slot->claim = NULL;
	slot->phase = KD_REQUEST_SLOT_FREE;
	list_move_tail(&slot->pool_link, &pool->free_slots);
	/* No referring actor or old publication may access this record now. */
}

static void private_records_init(struct kd_request_slot *slot)
{
	struct kd_thread_state *state = slot->pool->state;

	/* Only small fresh referring records are reset, never the canonical packet. */
	slot->call.node.state = state;
	slot->call.driver = NULL;
	slot->capture.state = state;
	slot->capture.task = current;
	slot->capture.control = &slot->call;
	slot->capture.kind = KD_EXECUTION_JIT;
	slot->native_return.state = state;
	slot->native_return.task = state->origin;
	slot->native_return.control = &slot->call;
	slot->native_return.kind = KD_EXECUTION_NATIVE;
	kd_jit_image_use_init(&slot->execution_use);
	kd_jit_image_use_init(&slot->exit_use);
	kd_jit_image_use_init(&slot->return_use);
	kd_jit_image_use_init(&slot->source_use);
	slot->entry = (struct kd_mutex_entry) { .phase = KD_MUTEX_ENTRY_PRIVATE };
	kd_owner_batch_init(&slot->owner_batch);
}

int kd_request_pool_init(struct kd_request_pool *pool,
			 struct kd_thread_state *state,
			 struct kd_request_slot *slots, unsigned int capacity)
{
	unsigned int index;

	if (!pool || !state || !state->origin || (capacity && !slots))
		return -EINVAL;
	raw_spin_lock_init(&pool->guard);
	pool->state = state;
	pool->slots = slots;
	pool->capacity = capacity;
	INIT_LIST_HEAD(&pool->free_slots);
	INIT_LIST_HEAD(&pool->live_slots);
	for (index = 0; index < capacity; ++index) {
		struct kd_request_slot *slot = &slots[index];

		INIT_LIST_HEAD(&slot->pool_link);
		INIT_LIST_HEAD(&slot->users);
		slot->pool = pool;
		slot->claim = NULL;
		slot->phase = KD_REQUEST_SLOT_FREE;
		slot->parent = NULL;
		kd_request_user_init(&slot->parent_user);
		private_records_init(slot);
		list_add_tail(&slot->pool_link, &pool->free_slots);
	}
	return 0;
}

bool kd_request_pool_empty(struct kd_request_pool *pool)
{
	unsigned long flags;
	bool empty;

	if (!pool)
		return false;
	raw_spin_lock_irqsave(&pool->guard, flags);
	empty = list_empty(&pool->live_slots);
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return empty;
}

unsigned int kd_request_pool_collect(struct kd_request_pool *pool)
{
	struct kd_request_slot *slot, *next;
	unsigned long flags;
	unsigned int collected = 0;

	if (!pool)
		return 0;
	raw_spin_lock_irqsave(&pool->guard, flags);
	list_for_each_entry_safe(slot, next, &pool->live_slots, pool_link) {
		if (slot->phase == KD_REQUEST_SLOT_LIVE &&
		    !reusable_locked(slot, NULL)) {
			free_locked(slot);
			++collected;
		}
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return collected;
}

static int reserve_slot(struct kd_request_pool *pool,
			    struct kd_execution_binding *binding, const void *claim,
			    struct kd_request_slot **result)
{
	struct kd_request_slot *slot;
	unsigned long flags;
	int error = 0;

	if (!pool || !result)
		return -EINVAL;
	*result = NULL;
	if (!kd_state_is_current(pool->state, binding))
		return -EPERM;
	raw_spin_lock_irqsave(&pool->guard, flags);
	if (kd_state_current_binding(pool->state) != binding) {
		error = -ESTALE;
	} else if (list_empty(&pool->free_slots)) {
		error = -ENOSPC;
	} else {
		slot = list_first_entry(&pool->free_slots,
					struct kd_request_slot, pool_link);
		slot->claim = claim ? claim : &slot->call.acquisition_identity;
		slot->phase = KD_REQUEST_SLOT_RESERVED;
		list_move_tail(&slot->pool_link, &pool->live_slots);
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	if (error)
		return error;
	/* RESERVED is private and not collectable; no subrecord observer exists. */
	private_records_init(slot);
	*result = slot;
	return 0;
}

int kd_request_slot_reserve(struct kd_request_pool *pool,
			    struct kd_execution_binding *binding, const void *claim,
			    struct kd_request_slot **slot)
{
	if (!claim)
		return -EINVAL;
	return reserve_slot(pool, binding, claim, slot);
}

int kd_request_slot_reserve_owned(struct kd_request_pool *pool,
				  struct kd_execution_binding *binding,
				  struct kd_request_slot **slot)
{
	return reserve_slot(pool, binding, NULL, slot);
}

int kd_request_slot_prepare(struct kd_request_slot *slot, const void *claim,
			    struct kd_execution_binding *binding,
			    const struct kd_jit_mutex_driver *driver, bool ready)
{
	struct kd_request_pool *pool;
	unsigned long flags;
	int result;

	if (!slot || !slot->pool || !driver)
		return -EINVAL;
	pool = slot->pool;
	if (!kd_state_is_current(pool->state, binding))
		return -EPERM;
	raw_spin_lock_irqsave(&pool->guard, flags);
	if (!matches(slot, claim))
		result = -ESTALE;
	else if (slot->phase != KD_REQUEST_SLOT_RESERVED)
		result = -EBUSY;
	else if (kd_state_current_binding(pool->state) != binding)
		result = -ESTALE;
	else {
		slot->phase = KD_REQUEST_SLOT_PREPARING;
		result = 0;
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	if (result)
		return result;

	/* No queue/source effects or task-reference acquisition on init failure. */
	slot->driver = *driver;
	result = kd_jit_mutex_call_init(&slot->call, pool->state,
					&slot->driver, ready);
	raw_spin_lock_irqsave(&pool->guard, flags);
	slot->phase = result ? KD_REQUEST_SLOT_RESERVED : KD_REQUEST_SLOT_LIVE;
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}

int kd_request_slot_cancel(struct kd_request_slot *slot, const void *claim)
{
	struct kd_request_pool *pool;
	unsigned long flags;
	int result;

	if (!slot || !slot->pool)
		return -EINVAL;
	pool = slot->pool;
	raw_spin_lock_irqsave(&pool->guard, flags);
	if (!matches(slot, claim))
		result = -ESTALE;
	else if (slot->phase != KD_REQUEST_SLOT_RESERVED)
		result = -EBUSY;
	else {
		result = reusable_locked(slot, NULL);
		if (!result)
			free_locked(slot);
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}

int kd_request_slot_discard(struct kd_request_slot *slot, const void *claim)
{
	struct kd_request_pool *pool;
	unsigned long flags;
	int result;

	if (!slot || !slot->pool)
		return -EINVAL;
	pool = slot->pool;
	raw_spin_lock_irqsave(&pool->guard, flags);
	if (!matches(slot, claim))
		result = -ESTALE;
	else if (slot->phase != KD_REQUEST_SLOT_LIVE)
		result = -EBUSY;
	else {
		slot->phase = KD_REQUEST_SLOT_DISCARDING;
		result = 0;
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	if (result)
		return result;

	/* Constructor's exact task reference is dropped by its own unwind API. */
	result = kd_mutex_node_discard(&slot->call.node);
	raw_spin_lock_irqsave(&pool->guard, flags);
	slot->phase = KD_REQUEST_SLOT_LIVE;
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}

int kd_request_slot_release(struct kd_request_slot *slot, const void *claim)
{
	struct kd_request_pool *pool;
	unsigned long flags;
	int result;

	if (!slot || !slot->pool)
		return -EINVAL;
	pool = slot->pool;
	raw_spin_lock_irqsave(&pool->guard, flags);
	if (!matches(slot, claim))
		result = -ESTALE;
	else if (slot->phase != KD_REQUEST_SLOT_LIVE)
		result = -EBUSY;
	else {
		result = reusable_locked(slot, NULL);
		if (!result)
			free_locked(slot);
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}

static void link_user_locked(struct kd_request_slot *slot,
			     struct kd_request_user *user, const void *identity,
			     enum kd_request_user_kind kind)
{
	user->slot = slot;
	user->identity = identity;
	user->kind = kind;
	user->linked = true;
	list_add_tail(&user->link, &slot->users);
}

static void unlink_user_locked(struct kd_request_user *user)
{
	list_del_init(&user->link);
	user->linked = false;
	user->identity = NULL;
	user->kind = KD_REQUEST_USER_UNUSED;
	WRITE_ONCE(user->slot, NULL);
}

int kd_request_user_hold(struct kd_request_slot *slot, const void *claim,
			 struct kd_request_user *user, const void *identity,
			 enum kd_request_user_kind kind)
{
	struct kd_request_pool *pool;
	unsigned long flags;
	int result = 0;

	if (!slot || !slot->pool || !user || !identity ||
	    kind < KD_REQUEST_USER_CONTROL || kind >= KD_REQUEST_USER_PARENT)
		return -EINVAL;
	pool = slot->pool;
	raw_spin_lock_irqsave(&pool->guard, flags);
	if (!matches(slot, claim))
		result = -ESTALE;
	else if (slot->phase != KD_REQUEST_SLOT_RESERVED &&
		 slot->phase != KD_REQUEST_SLOT_LIVE)
		result = -EBUSY;
	else if (!user_idle(user))
		result = -EALREADY;
	else
		link_user_locked(slot, user, identity, kind);
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}

static int drop_user(struct kd_request_user *user, const void *identity,
		     bool finish)
{
	struct kd_request_slot *slot;
	struct kd_request_pool *pool;
	unsigned long flags;
	int result = 0;

	if (!user || !identity)
		return -EINVAL;
	slot = READ_ONCE(user->slot);
	if (!slot)
		return -ESTALE;
	pool = slot->pool;
	raw_spin_lock_irqsave(&pool->guard, flags);
	if (user->slot != slot || !user->linked || user->identity != identity)
		result = -ESTALE;
	else if (user->kind == KD_REQUEST_USER_PARENT)
		result = -EPERM;
	else {
		unlink_user_locked(user);
		/* The current guard retains the array while this final user ends.
		 * No access to user/slot follows possible final free_locked.
		 */
		if (finish && slot->phase == KD_REQUEST_SLOT_LIVE &&
		    !reusable_locked(slot, NULL))
			free_locked(slot);
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}

int kd_request_user_put(struct kd_request_user *user, const void *identity)
{
	return drop_user(user, identity, false);
}

int kd_request_user_finish(struct kd_request_user *user, const void *identity)
{
	return drop_user(user, identity, true);
}

int kd_request_slot_set_parent(struct kd_request_slot *child,
			       const void *child_claim,
			       struct kd_request_slot *parent,
			       const void *parent_claim)
{
	struct kd_request_pool *pool;
	unsigned long flags;
	int result = 0;

	if (!child || !parent || child == parent || !child->pool ||
	    child->pool != parent->pool)
		return -EINVAL;
	pool = child->pool;
	raw_spin_lock_irqsave(&pool->guard, flags);
	if (!matches(child, child_claim) || !matches(parent, parent_claim))
		result = -ESTALE;
	else if (child->phase != KD_REQUEST_SLOT_RESERVED ||
		 parent->phase != KD_REQUEST_SLOT_LIVE)
		result = -EBUSY;
	else if (child->parent || !user_idle(&child->parent_user))
		result = -EALREADY;
	else {
		link_user_locked(parent, &child->parent_user, child_claim,
				 KD_REQUEST_USER_PARENT);
		child->parent = parent;
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}

int kd_request_slot_drop_parent(struct kd_request_slot *child,
				const void *child_claim)
{
	struct kd_request_pool *pool;
	unsigned long flags;
	int result = 0;

	if (!child || !child->pool)
		return -EINVAL;
	pool = child->pool;
	raw_spin_lock_irqsave(&pool->guard, flags);
	if (!matches(child, child_claim))
		result = -ESTALE;
	else if (child->phase != KD_REQUEST_SLOT_RESERVED &&
		 child->phase != KD_REQUEST_SLOT_LIVE)
		result = -EBUSY;
	else if (!child->parent || !child->parent_user.linked ||
		 child->parent_user.slot != child->parent ||
		 child->parent_user.identity != child_claim ||
		 child->parent_user.kind != KD_REQUEST_USER_PARENT)
		result = -ESTALE;
	else {
		/* Detach paired metadata before publishing the parent's last drop. */
		child->parent = NULL;
		unlink_user_locked(&child->parent_user);
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}

static int native_owner(struct kd_request_pool *pool,
			struct kd_execution_binding *binding)
{
	if (!pool || !binding)
		return -EINVAL;
	if (!kd_state_is_current(pool->state, binding) ||
	    binding->kind != KD_EXECUTION_NATIVE)
		return -EPERM;
	return 0;
}

static int can_detach_locked(struct kd_request_pool *pool,
			      struct kd_execution_binding *native)
{
	struct kd_request_slot *slot;
	int result;

	list_for_each_entry(slot, &pool->live_slots, pool_link) {
		if (native != &slot->native_return)
			return -EBUSY;
		result = reusable_locked(slot, native);
		if (result)
			return result;
	}
	return kd_state_current_binding(pool->state) == native ? 0 : -ESTALE;
}

int kd_request_pool_can_detach(struct kd_request_pool *pool,
			       struct kd_execution_binding *exact_native)
{
	unsigned long flags;
	int result;

	result = native_owner(pool, exact_native);
	if (result)
		return result;
	raw_spin_lock_irqsave(&pool->guard, flags);
	result = can_detach_locked(pool, exact_native);
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}

int kd_request_pool_detach(struct kd_request_pool *pool,
			   struct kd_execution_binding *exact_native)
{
	struct kd_request_slot *slot, *next;
	unsigned long flags;
	int result;

	result = native_owner(pool, exact_native);
	if (result)
		return result;
	raw_spin_lock_irqsave(&pool->guard, flags);
	result = can_detach_locked(pool, exact_native);
	if (!result && cmpxchg_release(&pool->state->binding,
				       exact_native, NULL) != exact_native)
		result = -ESTALE;
	if (!result) {
		/* Complete drain and all fallible checks preceded revocation. */
		list_for_each_entry_safe(slot, next, &pool->live_slots, pool_link)
			free_locked(slot);
	}
	raw_spin_unlock_irqrestore(&pool->guard, flags);
	return result;
}
