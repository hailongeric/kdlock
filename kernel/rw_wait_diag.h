/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_RW_WAIT_DIAG_H
#define KDLOCK_RW_WAIT_DIAG_H
#include <linux/errno.h>
#include <linux/wait.h>
#include "../include/kd_rw_wait_diag.h"

struct kd_rw;
struct task_struct;
/* Only this physical task writes its row. The provider preallocates separate
 * rows and retains them through all calls/queue actors, including cancellation.
 * task is an identity, not a reference. No record/node retains this pointer.
 */
struct kd_rw_wait_diag_row {
	struct task_struct *task;
	struct kd_rw *target;
	struct kd_rw_wait_diag_counts counts;
} __aligned(128);

#ifdef CONFIG_KDLOCK_RW_WAIT_DIAG
int kd_rw_wait_diag_attach(struct kd_rw *target, struct kd_rw_wait_diag_row *row);
struct kd_rw_wait_diag_row *kd_rw_wait_diag_current(struct kd_rw *target);
void kd_rw_wait_diag_prepare(struct kd_rw_wait_diag_row *row, bool writer,
		bool *registered, wait_queue_head_t *queue, wait_queue_entry_t *wait, int state);
void kd_rw_wait_diag_wake(struct kd_rw_wait_diag_row *row,
		wait_queue_head_t *queue, enum kd_rw_wait_diag_counter reason);
static inline void kd_rw_wait_diag_add(struct kd_rw_wait_diag_row *row,
		enum kd_rw_wait_diag_counter counter, unsigned long value)
{
	if (row)
		row->counts.value[counter] += value;
}
#else
static inline int kd_rw_wait_diag_attach(struct kd_rw *target, struct kd_rw_wait_diag_row *row)
{
	return -EOPNOTSUPP;
}
#endif
#endif
