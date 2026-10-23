/* SPDX-License-Identifier: GPL-2.0 */
#ifndef TC_RWSEM_COMPAT_H
#define TC_RWSEM_COMPAT_H
#include <linux/percpu.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/spinlock.h>
#include "include/rwsem/komb_rwsem.h"
#include "include/lib/combiner.h"

#define LOCK_DEFINE_TIMING_VAR(var)
#define LOCK_START_TIMING_PER_CPU(var)
#define LOCK_END_TIMING_PER_CPU(var)
#define LOCK_START_TIMING(var_t, var)
#define LOCK_END_TIMING(var_t, var)
#define PREFETCHING 1
#define WWJUMP 1
#define LOCK_START_TIMING_PER_CPU_DISABLE(name)
#define LOCK_END_TIMING_PER_CPU_DISABLE(name)

/* Replacement for upstream's custom task_struct fields. Fixed-affinity workers
 * register before measurement; all storage and task references survive until
 * the client has joined the entire cohort and drained the lock. */
struct tc_rwsem_context {
	struct task_struct *task;
	void *stack_allocation;
	unsigned long komb_stack_base_ptr, komb_stack_curr_ptr;
	struct komb_mutex_node *komb_mutex_node;
	struct komb_mutex_node *komb_local_queue_head, *komb_local_queue_tail;
	struct task_struct *komb_curr_waiter_task, *komb_prev_waiter_task;
	struct task_struct *komb_next_waiter_task;
	u64 counter_val;
	struct komb_rwsem *komb_lock_addr[8];
	u64 delegated, batches, parks;
	struct komb_mutex_node node;
};
DECLARE_PER_CPU(struct tc_rwsem_context *, tc_rwsem_contexts);

static __always_inline struct tc_rwsem_context *tc_rwsem_current(void)
{
	return raw_cpu_read(tc_rwsem_contexts);
}
static __always_inline struct tc_rwsem_context *
tc_rwsem_task(struct task_struct *task)
{
	return per_cpu(tc_rwsem_contexts, task_cpu(task));
}

extern long komb_batch_size;
void komb_context_switch(void *, void *);

int tc_rwsem_worker_register(void);
int tc_rwsem_workers_drain(void);
#endif
