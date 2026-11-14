// SPDX-License-Identifier: GPL-2.0-only
/* Temporary physical-worker counters; no shared counter writes or event log. */
#include <linux/interrupt.h>
#include <linux/sched.h>
#include "rw_wait_diag.h"
#include "rw.h"
#include "task_state.h"
#include "episode.h"

int kd_rw_wait_diag_attach(struct kd_rw *target, struct kd_rw_wait_diag_row *row)
{
	struct kd_task_root_context *root = kd_task_root_context_current();

	/* Cold opt-in, before workload calls. Root teardown removes task lookup;
	 * no diagnostic pointer escapes into a persistent or canceled MCS node.
	 */
	if (!target || !target->atomic_admission || !row || !in_task() ||
	    in_atomic() || irqs_disabled() || !root || !root->attached ||
	    root->task != current || root->aux_entry || root->source_closing ||
	    !root->mutex_resources || root->mutex_resources->config.proxy_limit ||
	    root->mutex_resources->config.family != KD_LOCK_FAMILY_RWSEM)
		return -EINVAL;
	if (root->rw_wait_diag || row->task || !list_empty(&root->native_grants) ||
	    !list_empty(&root->core.grants) || !list_empty(&root->owners.batches))
		return -EBUSY;
	row->task = current;
	row->target = target;
	root->rw_wait_diag = row;
	return 0;
}

struct kd_rw_wait_diag_row *kd_rw_wait_diag_current(struct kd_rw *target)
{
	struct kd_task_root_context *root;
	struct kd_rw_wait_diag_row *row;

	/* A wake may hold the family guard with preemption disabled. Reject IRQ
	 * and NMI actors, but keep ordinary task actors in that guarded interval.
	 * Read only the physical task header, never its potentially borrowed S_W.
	 */
	if (!target || !in_task())
		return NULL;
	root = kd_task_root_context_current();
	if (!root || !root->attached || root->task != current)
		return NULL;
	row = root->rw_wait_diag;
	return row && row->task == current && row->target == target ? row : NULL;
}

struct kd_rw_wait_diag_wake_batch {
	unsigned long read_visits, read_accept, write_visits, write_accept;
};

static int diag_wake(wait_queue_entry_t *wait, unsigned int mode, int flags,
		void *key, bool writer)
{
	struct kd_rw_wait_diag_wake_batch *batch = key;
	int result;

	/* key is the synchronous broadcast caller's stack, never waiter storage.
	 * Uninstrumented wake sites supply NULL and retain ordinary semantics.
	 */
	if (batch) {
		if (writer)
			batch->write_visits++;
		else
			batch->read_visits++;
	}
	result = autoremove_wake_function(wait, mode, flags, NULL);
	/* Removal may already permit waiter stack reuse. Only batch and scalars
	 * may be touched after the call; batch lasts through __wake_up return.
	 */
	if (batch && result) {
		if (writer)
			batch->write_accept++;
		else
			batch->read_accept++;
	}
	return result;
}

static int diag_read_wake(wait_queue_entry_t *wait, unsigned int mode, int flags, void *key)
{
	return diag_wake(wait, mode, flags, key, false);
}

static int diag_write_wake(wait_queue_entry_t *wait, unsigned int mode, int flags, void *key)
{
	return diag_wake(wait, mode, flags, key, true);
}

void kd_rw_wait_diag_prepare(struct kd_rw_wait_diag_row *row, bool writer,
		bool *registered, wait_queue_head_t *queue, wait_queue_entry_t *wait, int state)
{
	unsigned long flags;
	unsigned int base = writer ? KD_RW_DIAG_WRITE_PREPARE : KD_RW_DIAG_READ_PREPARE;

	if (!row) {
		prepare_to_wait(queue, wait, state);
		return;
	}
	/* Install before the first publication only. Later callbacks can race a
	 * returning waiter; never rewrite func on an already published lifetime.
	 */
	if (!*registered)
		wait->func = writer ? diag_write_wake : diag_read_wake;
	/* Exact Ubuntu 7.0.0-38.38 prepare_to_wait ordering: classify and insert
	 * under the existing queue lock, then set state with its full barrier.
	 */
	wait->flags &= ~WQ_FLAG_EXCLUSIVE;
	spin_lock_irqsave(&queue->lock, flags);
	row->counts.value[base]++;
	if (list_empty(&wait->entry)) {
		__add_wait_queue(queue, wait);
		row->counts.value[base + (*registered ? 2 : 1)]++;
		*registered = true;
	} else {
		row->counts.value[base + 3]++;
	}
	set_current_state(state);
	spin_unlock_irqrestore(&queue->lock, flags);
}

void kd_rw_wait_diag_wake(struct kd_rw_wait_diag_row *row,
		wait_queue_head_t *queue, enum kd_rw_wait_diag_counter reason)
{
	struct kd_rw_wait_diag_wake_batch batch = { 0 };

	if (!row) {
		wake_up_all(queue);
		return;
	}
	row->counts.value[reason]++;
	__wake_up(queue, TASK_NORMAL, 0, &batch);
	row->counts.value[KD_RW_DIAG_READ_VISITS] += batch.read_visits;
	row->counts.value[KD_RW_DIAG_READ_ACCEPT] += batch.read_accept;
	row->counts.value[KD_RW_DIAG_WRITE_VISITS] += batch.write_visits;
	row->counts.value[KD_RW_DIAG_WRITE_ACCEPT] += batch.write_accept;
}
