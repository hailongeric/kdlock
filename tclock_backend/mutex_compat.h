/* SPDX-License-Identifier: GPL-2.0 */
#ifndef TC_MUTEX_COMPAT_H
#define TC_MUTEX_COMPAT_H
#include <linux/percpu.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/spinlock.h>
#include "include/mutex/komb_mutex.h"

#define PREFETCHING 1
#define WWJUMP 1
#define LOCK_START_TIMING_PER_CPU_DISABLE(name)
#define LOCK_END_TIMING_PER_CPU_DISABLE(name)

/* Replacement for upstream's custom task_struct fields. Fixed-affinity workers
 * register before measurement; all storage and task references survive until
 * the client has joined the entire cohort and drained the lock. */
struct tc_mutex_context {
	struct task_struct *task;
	void *stack_allocation;
	unsigned long komb_stack_base_ptr, komb_stack_curr_ptr;
	struct komb_mutex_node *komb_mutex_node;
	struct komb_mutex_node *komb_local_queue_head, *komb_local_queue_tail;
	struct task_struct *komb_curr_waiter_task, *komb_prev_waiter_task;
	struct task_struct *komb_next_waiter_task;
	u64 counter_val;
	struct komb_mutex *komb_lock_addr[8];
	u64 delegated, batches, parks;
	struct komb_mutex_node node;
};
DECLARE_PER_CPU(struct tc_mutex_context *, tc_mutex_contexts);

static __always_inline struct tc_mutex_context *tc_mutex_current(void)
{
	return raw_cpu_read(tc_mutex_contexts);
}
static __always_inline struct tc_mutex_context *
tc_mutex_task(struct task_struct *task)
{
	return per_cpu(tc_mutex_contexts, task_cpu(task));
}

extern long komb_batch_size;
void komb_context_switch(void *, void *);
void __komb_mutex_lock(struct komb_mutex *);
int tc_mutex_worker_register(void);
int tc_mutex_workers_drain(void);
#endif
