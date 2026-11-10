// SPDX-License-Identifier: GPL-2.0-only
/* Retained actual-owner duties, independent of a returned source episode. */
#include <linux/compiler.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "mutex.h"
#include "owner_progress.h"

void kd_owner_progress_init(struct kd_owner_progress *progress,
			    struct task_struct *task)
{
	INIT_LIST_HEAD(&progress->batches);
	progress->task = task;
}

void kd_owner_batch_init(struct kd_owner_batch *item)
{
	INIT_LIST_HEAD(&item->link);
	item->progress = NULL;
	item->batch = NULL;
	item->control_stopped = false;
	item->terminal_foreign = false;
}

static bool owner_context(struct kd_owner_progress *progress)
{
	return progress && progress->task == current && in_task() &&
	       !in_atomic() && !irqs_disabled();
}

int kd_owner_progress_track(struct kd_owner_progress *progress,
			   struct kd_owner_batch *item,
			   struct kd_mutex_batch *batch)
{
	struct kd_mutex_release_owner *owner;
	struct kd_owner_batch *tracked;
	int result = 0;

	if (!owner_context(progress))
		return -EPERM;
	if (!item || !batch || !batch->initialized || !batch->head)
		return -EINVAL;
	if (item->progress || item->batch || !list_empty(&item->link) ||
	    item->control_stopped || item->terminal_foreign)
		return -EALREADY;
	list_for_each_entry(tracked, &progress->batches, link)
		if (tracked->batch == batch)
			return -EALREADY;
	owner = &batch->release_owner;
	raw_spin_lock(&owner->guard);
	if (owner->task != current || owner->phase != KD_MUTEX_OWNER_OPEN)
		result = -EPERM;
	raw_spin_unlock(&owner->guard);
	if (result)
		return result;
	item->progress = progress;
	item->batch = batch;
	list_add_tail(&item->link, &progress->batches);
	return 0;
}

int kd_owner_progress_control_stopped(struct kd_owner_batch *item,
				     bool terminal_foreign)
{
	if (!item || !owner_context(item->progress))
		return -EPERM;
	if (!item->batch || list_empty(&item->link) ||
	    !item->batch->initialized ||
	    item->batch->release_owner.task != current)
		return -ESTALE;
	if (item->control_stopped)
		return -EALREADY;
	if (item->batch->serving || !item->batch->head ||
	    !READ_ONCE(item->batch->head->source_granted))
		return -EBUSY;
	item->terminal_foreign = terminal_foreign;
	item->control_stopped = true;
	return 0;
}

static bool handle_ready(const struct kd_mutex_release *release)
{
	return (release->phase == KD_MUTEX_UNLOCK_REQUESTED &&
		release->route == KD_MUTEX_UNLOCK_ROUTE_OWNER) ||
	       (release->phase == KD_MUTEX_UNLOCK_UNWIND_READY &&
		release->route == KD_MUTEX_UNLOCK_ROUTE_DEFERRED_OUTER);
}

/* Only this task can retire owner obligations. List membership retains each
 * returned control across the unlocked owner_handle call; no source is read.
 */
static struct kd_mutex_release *next_ready(struct kd_mutex_batch *batch)
{
	struct kd_mutex_release_owner *owner = &batch->release_owner;
	struct kd_mutex_release *release, *ready = NULL;

	raw_spin_lock(&owner->guard);
	if (owner->phase == KD_MUTEX_OWNER_OPEN)
		list_for_each_entry(release, &owner->obligations, owner_link)
			if (handle_ready(release)) {
				ready = release;
				break;
			}
	raw_spin_unlock(&owner->guard);
	return ready;
}

static bool finish_ready_locked(struct kd_owner_batch *item)
{
	struct kd_mutex_batch *batch = item->batch;
	struct kd_mutex_release *release;

	if (!item->control_stopped ||
	    batch->release_owner.phase != KD_MUTEX_OWNER_OPEN || batch->serving ||
	    !batch->head || !READ_ONCE(batch->head->source_granted))
		return false;
	list_for_each_entry(release, &batch->release_owner.obligations, owner_link)
		if (release->phase != KD_MUTEX_UNLOCK_OWNER_HANDLED)
			return false;
	return true;
}

static bool reap_ready_locked(struct kd_owner_batch *item)
{
	struct kd_mutex_release_owner *owner = &item->batch->release_owner;
	struct kd_mutex_release *release;

	if (!item->control_stopped ||
	    owner->phase != KD_MUTEX_OWNER_PHYSICALLY_RELEASED)
		return false;
	if (list_empty(&owner->obligations))
		return true;
	list_for_each_entry(release, &owner->obligations, owner_link) {
		struct kd_mutex_node *node =
			container_of(release, struct kd_mutex_node, release);

		if (smp_load_acquire(&node->queue_done) &&
		    !smp_load_acquire(&node->result_user) && !release->source_user &&
		    !release->return_user && !release->notifier)
			return true;
	}
	return false;
}

static enum kd_mutex_owner_phase phase_locked(struct kd_mutex_batch *batch)
{
	struct kd_mutex_release_owner *owner = &batch->release_owner;
	enum kd_mutex_owner_phase phase;

	raw_spin_lock(&owner->guard);
	phase = owner->phase;
	raw_spin_unlock(&owner->guard);
	return phase;
}

int kd_owner_progress_run(struct kd_owner_progress *progress, bool *blocked)
{
	struct list_head *position, *next;
	struct kd_owner_batch *item;

	if (!blocked)
		return -EINVAL;
	*blocked = false;
	if (!owner_context(progress))
		return -EPERM;
	position = progress->batches.next;
	while (position != &progress->batches) {
		struct kd_mutex_batch *batch;
		struct kd_mutex_release_owner *owner;
		struct kd_mutex_release *release;
		bool finish, reap;
		int result;

		item = list_entry(position, struct kd_owner_batch, link);
		next = position->next;
		batch = item->batch;
		if (item->progress != progress || !batch || !batch->initialized ||
		    batch->release_owner.task != current)
			return -ESTALE;
		owner = &batch->release_owner;
		while ((release = next_ready(batch))) {
			result = kd_mutex_release_owner_handle(release);
			if (result)
				return result;
		}
		raw_spin_lock(&owner->guard);
		finish = finish_ready_locked(item);
		raw_spin_unlock(&owner->guard);
		if (finish) {
			result = kd_mutex_finish_batch(batch);
			if (result && result != -EBUSY)
				return result;
		}
		raw_spin_lock(&owner->guard);
		reap = reap_ready_locked(item);
		raw_spin_unlock(&owner->guard);
		if (reap) {
			/* Successful reap may end the head containing this exact item.
			 * Cache only independently retained list/slot neighbors first.
			 */
			list_del_init(&item->link);
			item->progress = NULL;
			item->batch = NULL;
			result = kd_mutex_reap_batch(batch);
			if (result) {
				/* Head is not retirable on failure. Restore the original
				 * position, not the tail, so this walk stays finite.
				 */
				item->progress = progress;
				item->batch = batch;
				list_add_tail(&item->link, next);
				if (result != -EBUSY)
					return result;
			}
			/* No item/batch access follows a successful reap. */
		}
		position = next;
	}
	list_for_each_entry(item, &progress->batches, link) {
		enum kd_mutex_owner_phase phase;

		if (!item->control_stopped || !item->terminal_foreign)
			continue;
		phase = phase_locked(item->batch);
		if (phase != KD_MUTEX_OWNER_PHYSICALLY_RELEASED &&
		    phase != KD_MUTEX_OWNER_RETIRED)
			*blocked = true;
	}
	return 0;
}

bool kd_owner_progress_ready(struct kd_owner_progress *progress)
{
	struct kd_owner_batch *item;

	if (!owner_context(progress))
		return false;
	list_for_each_entry(item, &progress->batches, link) {
		struct kd_mutex_release_owner *owner = &item->batch->release_owner;
		struct kd_mutex_release *release;
		bool ready;

		raw_spin_lock(&owner->guard);
		ready = finish_ready_locked(item) || reap_ready_locked(item);
		if (!ready && owner->phase == KD_MUTEX_OWNER_OPEN)
			list_for_each_entry(release, &owner->obligations, owner_link)
				if (handle_ready(release)) {
					ready = true;
					break;
				}
		raw_spin_unlock(&owner->guard);
		if (ready)
			return true;
	}
	return false;
}
