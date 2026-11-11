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
	/* Context/polling only; the batch owns its separate service policy. */
	bool atomic_spin;
};

/*
 * Embed in its actual physical batch head's persistent containing allocation,
 * or independent storage held through successful reap. Never embed it in a
 * proxy node that this batch can retire before its head. A spin proxy is the
 * physical head of its own batch. Track that bound batch on the actual owner.
 *
 * control_stopped records that the driver exported or stopped its source.
 * For a mutex batch this enables physical finish after owner handling of its
 * releases. A spin batch can release its sole grant before control stops.
 * A writer cohort can close synchronously during a nested source callback.
 * Its separate cohort_active actor prevents reaping until the whole cohort
 * driver stops, independent of any individual callback's exported marker.
 * The backend retains its callback separately until it returns, and reaping
 * waits for both actors. terminal_foreign keeps
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
 * Ordinary task context, TASK_RUNNING, IRQs enabled, serial and nonreentrant.
 * Spin controllers allow atomic polling and later native retirement.
 * Handle ready release controls, finish eligible physical batches, then try reap
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
