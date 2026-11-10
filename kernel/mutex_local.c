// SPDX-License-Identifier: GPL-2.0-only
/* Temporary native waiters and stable object-owned heads in the common MCS queue. */
#include <linux/bug.h>
#include <linux/errno.h>
#include <linux/interrupt.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <linux/sched.h>

#include "mutex_local.h"
#include "owner_progress.h"
#include "task_state.h"

/* Caller already retains its known exact native endpoint. Do not sample and
 * dereference an arbitrary binding or read a borrowed canonical packet here.
 */
static bool local_context(struct kd_task_root_context *root)
{
	return root && kd_task_root_context_current() == root && root->attached &&
	       root->task == current && !root->aux_entry && in_task() &&
	       !in_atomic() && !irqs_disabled();
}

bool kd_mutex_local_held(struct kd_mutex *lock, struct kd_task_root_context *root)
{
	struct kd_mutex *held;

	if (!lock || !local_context(root) ||
	    READ_ONCE(lock->local_owner) != current)
		return false;
	list_for_each_entry(held, &root->held_local, local_link)
		if (held == lock)
			return true;
	return false;
}

static void wait_local(struct kd_mutex_link *waiter,
		       struct kd_owner_progress *owners)
{
	for (;;) {
		bool blocked;
		int result;

		__set_current_state(TASK_RUNNING);
		result = kd_owner_progress_run(owners, &blocked);
		BUG_ON(result);
		set_current_state(TASK_UNINTERRUPTIBLE);
		if (!blocked && smp_load_acquire(&waiter->turn))
			break;
		/* Exact release notifications before this sleep publication are
		 * visible to ready; later notifications wake this task normally.
		 */
		if (kd_owner_progress_ready(owners))
			continue;
		schedule();
	}
	__set_current_state(TASK_RUNNING);
}

int kd_mutex_local_lock(struct kd_mutex *lock, struct kd_task_root_context *root)
{
	struct kd_mutex_link waiter;

	if (!lock)
		return -EINVAL;
	if (!local_context(root))
		return -EPERM;
	might_sleep();
	kd_mutex_link_init(&waiter, NULL, KD_MUTEX_SELECTED_LOCAL);
	kd_mutex_link_enqueue(lock, &waiter);
	wait_local(&waiter, &root->owners);
	BUG_ON(READ_ONCE(lock->owner) || READ_ONCE(lock->local_owner));
	/* Prior local owner ended every stable-head access before its tail CAS
	 * or our turn publication. No other queue consumer can run on our turn.
	 */
	kd_mutex_link_init(&lock->local_head, NULL, KD_MUTEX_SELECTED_LOCAL);
	kd_mutex_link_replace_head(lock, &waiter, &lock->local_head);
	WRITE_ONCE(lock->local_owner, current);
	INIT_LIST_HEAD(&lock->local_link);
	list_add_tail(&lock->local_link, &root->held_local);
	/* No queue producer/predecessor can access waiter after head replacement. */
	return 0;
}

int kd_mutex_local_unlock(struct kd_mutex *lock, struct kd_task_root_context *root)
{
	struct kd_mutex_link *head;

	if (!lock)
		return -EINVAL;
	if (!local_context(root))
		return -EPERM;
	if (!kd_mutex_local_held(lock, root))
		return -ESTALE;
	BUG_ON(READ_ONCE(lock->owner));
	head = &lock->local_head;
	list_del_init(&lock->local_link);
	WRITE_ONCE(lock->local_owner, NULL);
	/* All old owner/index/task accesses precede actual MCS release. There is
	 * no object-owned long-lived grant/release control to finish afterward.
	 */
	kd_mutex_link_release(lock, head, NULL);
	return 0;
}
