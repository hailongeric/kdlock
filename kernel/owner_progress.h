/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_OWNER_PROGRESS_H
#define KDLOCK_OWNER_PROGRESS_H

#include <linux/list.h>
#include <linux/types.h>

struct task_struct;
struct kd_mutex_batch;

/* Physical-task control only. This list neither selects nor reads source S_W. */
struct kd_owner_progress {
	struct list_head batches;
	struct task_struct *task;
};

/*
 * Embed in its actual physical batch head's persistent containing allocation,
 * or independent storage held through successful reap. Never embed it in a
 * proxy node that this batch can retire before its head. Track only a local
 * physical winner, not an unused possible_batch in a proxy-selected request.
 *
 * control_stopped is explicit: the local batch's source/control C scope has
 * ended, no callback is running or may reenter it, and normal physical finish
 * can proceed after every logical release is owner-handled. It is neither a
 * source unlock nor physical completion. terminal_foreign additionally keeps
 * this task's own source pending until that physical duty completes. Later
 * source/result/return/notifier retirement alone does not impose that wait.
 */
struct kd_owner_batch {
	struct list_head link;
	struct kd_owner_progress *progress;
	struct kd_mutex_batch *batch;
	bool control_stopped;
	bool terminal_foreign;
};

/* Private constructors; task may be NULL until the owning root is attached. */
void kd_owner_progress_init(struct kd_owner_progress *progress,
			    struct task_struct *task);
void kd_owner_batch_init(struct kd_owner_batch *item);
/* Current owner only, after actual batch initialization and before combining. */
int kd_owner_progress_track(struct kd_owner_progress *progress,
			   struct kd_owner_batch *item,
			   struct kd_mutex_batch *batch);
/* Current owner closes that batch's C-control role once, never its source state. */
int kd_owner_progress_control_stopped(struct kd_owner_batch *item,
				     bool terminal_foreign);

/*
 * Ordinary sleepable task context, TASK_RUNNING, serial and nonreentrant.
 * Handle ready release controls, finish stopped physical batches, then try reap
 * without waiting for source/core/result/return/notifier users. No source code,
 * S_W access, allocation, image selection or new worker is involved.
 *
 * blocked reports only stopped terminal-foreign physical duties that remain;
 * PHYSICALLY_RELEASED metadata by itself cannot block this task's own source.
 * Controller/task/item/batch backing survives every API and escaped observer.
 * Slot capacity includes all unreaped records, not merely active call depth.
 *
 * Before possible successful reap, the item is unlinked and progress/batch are
 * cleared. Head retirable publication may permit immediate containing-storage
 * reuse: no item/batch access follows success. On failure head is still retained
 * and the original list position is restored. External callers must not reap a
 * tracked batch or mutate this list while the controller owns its membership.
 */
int kd_owner_progress_run(struct kd_owner_progress *progress, bool *blocked);
/*
 * Nonblocking metadata-only recheck AFTER publishing a sleep state. Existing
 * exact release/result/core/return/notifier notifications wake the owner task.
 * A true result requires another TASK_RUNNING run, never source execution.
 */
bool kd_owner_progress_ready(struct kd_owner_progress *progress);

/* After node.retirable and all API/observer users end, a reusable item has
 * progress == NULL, batch == NULL and an empty link. Historical flags may still
 * be true until its next private constructor; no source packet is reset here.
 */
#endif
