// SPDX-License-Identifier: GPL-2.0-only
/* External current-task anchors for canonical and borrowed source state. */
#include <linux/atomic.h>
#include <linux/errno.h>
#include <linux/hash.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/spinlock.h>

#include "state.h"
#include "task_state.h"

/* Internal mapping choice, not an anchor capacity or a scaling result. */
#define KD_TASK_REGISTRY_BITS 6
#define KD_TASK_REGISTRY_BUCKETS (1U << KD_TASK_REGISTRY_BITS)

struct kd_task_bucket {
	raw_spinlock_t guard;
	struct hlist_head anchors;
};

static struct kd_task_bucket kd_task_registry[KD_TASK_REGISTRY_BUCKETS] = {
	[0 ... KD_TASK_REGISTRY_BUCKETS - 1] = {
		.guard = __RAW_SPIN_LOCK_UNLOCKED(kd_task_registry),
		.anchors = HLIST_HEAD_INIT,
	},
};

static struct kd_task_bucket *current_bucket(void)
{
	return &kd_task_registry[hash_ptr(current, KD_TASK_REGISTRY_BITS)];
}

/* Only the bucket-guarded current-task key is exposed, never another task. */
static struct kd_task_anchor *find_current(struct kd_task_bucket *bucket)
{
	struct kd_task_anchor *anchor;

	hlist_for_each_entry(anchor, &bucket->anchors, registry_link)
		if (anchor->task == current)
			return anchor;
	return NULL;
}

void kd_task_anchor_init(struct kd_task_anchor *anchor)
{
	/* Constructor only: reinitializing registered/retained storage is invalid. */
	INIT_HLIST_NODE(&anchor->registry_link);
	anchor->task = NULL;
	anchor->own = NULL;
	anchor->borrowed = NULL;
}

struct kd_thread_state *kd_task_state_own(void)
{
	struct kd_task_bucket *bucket = current_bucket();
	struct kd_task_anchor *anchor;
	struct kd_thread_state *state;
	unsigned long flags;

	raw_spin_lock_irqsave(&bucket->guard, flags);
	anchor = find_current(bucket);
	state = anchor ? anchor->own : NULL;
	raw_spin_unlock_irqrestore(&bucket->guard, flags);
	/* Registration/current-task serialization retains the returned storage. */
	return state;
}

struct kd_thread_state *kd_task_state_active(void)
{
	struct kd_task_bucket *bucket = current_bucket();
	struct kd_task_anchor *anchor;
	struct kd_thread_state *state;
	unsigned long flags;

	raw_spin_lock_irqsave(&bucket->guard, flags);
	anchor = find_current(bucket);
	state = anchor ? (anchor->borrowed ? anchor->borrowed : anchor->own) : NULL;
	raw_spin_unlock_irqrestore(&bucket->guard, flags);
	/* Selecting a pointer never reads the possibly borrowed task's own packet. */
	return state;
}

int kd_task_state_attach(struct kd_task_anchor *anchor,
			 struct kd_thread_state *state, unsigned long origin_gs,
			 struct kd_execution_binding *native_binding)
{
	struct kd_task_bucket *bucket = current_bucket();
	unsigned long flags;
	int result;

	if (!anchor || !state || !native_binding)
		return -EINVAL;
	raw_spin_lock_irqsave(&bucket->guard, flags);
	if (find_current(bucket)) {
		result = -EEXIST;
		goto out;
	}
	/* The caller owns this private anchor; no concurrent reuse is permitted. */
	if (anchor->task || anchor->own || anchor->borrowed ||
	    !hlist_unhashed(&anchor->registry_link)) {
		result = -EBUSY;
		goto out;
	}
	result = kd_state_init(state, current, origin_gs, native_binding);
	if (result)
		goto out;
	get_task_struct(current);
	anchor->task = current;
	anchor->own = state;
	anchor->borrowed = NULL;
	hlist_add_head(&anchor->registry_link, &bucket->anchors);
	/* Bucket unlock publishes state initialization and the retained task key. */
out:
	raw_spin_unlock_irqrestore(&bucket->guard, flags);
	return result;
}

int kd_task_state_detach(struct kd_thread_state *state,
			 struct kd_execution_binding *native_binding)
{
	struct kd_task_bucket *bucket = current_bucket();
	struct kd_task_anchor *anchor;
	struct task_struct *task = NULL;
	unsigned long flags;
	int result;

	if (!state || !native_binding)
		return -EINVAL;
	raw_spin_lock_irqsave(&bucket->guard, flags);
	anchor = find_current(bucket);
	if (!anchor || anchor->own != state) {
		result = -ESTALE;
		goto out;
	}
	/* Do not inspect own mutable source state while a borrowed scope runs. */
	if (anchor->borrowed) {
		result = -EBUSY;
		goto out;
	}
	if (state->origin != current) {
		result = -EPERM;
		goto out;
	}
	/* Acquire and compare the retained endpoint before reading its fields. */
	if (kd_state_current_binding(state) != native_binding) {
		result = -ESTALE;
		goto out;
	}
	if (native_binding->state != state || native_binding->task != current ||
	    native_binding->kind != KD_EXECUTION_NATIVE) {
		result = -EPERM;
		goto out;
	}
	if (state->exit_image || !list_empty(&state->grants) ||
	    (state->operation.phase != KD_OPERATION_IDLE &&
	     state->operation.phase != KD_OPERATION_RESUMABLE)) {
		result = -EBUSY;
		goto out;
	}
	/* Admission is closed and all escaped users/scopes have already drained. */
	if (cmpxchg_release(&state->binding, native_binding, NULL) != native_binding) {
		result = -ESTALE;
		goto out;
	}
	task = anchor->task;
	hlist_del_init(&anchor->registry_link);
	anchor->task = NULL;
	anchor->own = NULL;
	anchor->borrowed = NULL;
	result = 0;
out:
	raw_spin_unlock_irqrestore(&bucket->guard, flags);
	/* No anchor/state access follows the final retained task-key release. */
	if (task)
		put_task_struct(task);
	return result;
}

void kd_task_borrow_scope_init(struct kd_task_borrow_scope *scope)
{
	scope->task = NULL;
	scope->anchor = NULL;
	scope->previous = NULL;
	scope->entered = NULL;
	scope->active = false;
}

int kd_task_borrow_enter(struct kd_task_borrow_scope *scope,
			 struct kd_thread_state *state,
			 struct kd_execution_binding *binding)
{
	struct kd_task_bucket *bucket = current_bucket();
	struct kd_task_anchor *anchor;
	unsigned long flags;
	int result = 0;

	if (!scope || !state || !binding)
		return -EINVAL;
	if (scope->active)
		return -EBUSY;
	if (!kd_state_is_jit_current(state, binding))
		return -EPERM;
	raw_spin_lock_irqsave(&bucket->guard, flags);
	anchor = find_current(bucket);
	if (!anchor) {
		result = -ENOENT;
		goto out;
	}
	if (state == anchor->own || state->origin == current) {
		result = -EINVAL;
		goto out;
	}
	scope->task = current;
	scope->anchor = anchor;
	scope->previous = anchor->borrowed;
	scope->entered = state;
	scope->active = true;
	anchor->borrowed = state;
out:
	raw_spin_unlock_irqrestore(&bucket->guard, flags);
	return result;
}

int kd_task_borrow_leave(struct kd_task_borrow_scope *scope)
{
	struct kd_task_bucket *bucket = current_bucket();
	struct kd_task_anchor *anchor;
	unsigned long flags;
	int result = 0;

	if (!scope || !scope->active)
		return -EINVAL;
	if (scope->task != current)
		return -EPERM;
	raw_spin_lock_irqsave(&bucket->guard, flags);
	anchor = find_current(bucket);
	if (!anchor || anchor != scope->anchor || anchor->borrowed != scope->entered) {
		result = -ESTALE;
		goto out;
	}
	/* Restore a pointer only, never an old packet or earlier execution right. */
	anchor->borrowed = scope->previous;
	scope->active = false;
	scope->task = NULL;
	scope->anchor = NULL;
	scope->previous = NULL;
	scope->entered = NULL;
out:
	raw_spin_unlock_irqrestore(&bucket->guard, flags);
	return result;
}
