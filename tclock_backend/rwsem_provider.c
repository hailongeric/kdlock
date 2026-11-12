// SPDX-License-Identifier: GPL-2.0
/* Benchmark-only port of upstream original TCLock rwsem operations. */
#include <linux/module.h>
#include <linux/vmalloc.h>
#include <linux/slab.h>
#include <linux/topology.h>
#include <linux/mutex.h>
#include "rwsem_compat.h"

DEFINE_PER_CPU(struct tc_rwsem_context *, tc_rwsem_contexts);
static DEFINE_MUTEX(registration_lock);
static unsigned long target_lock;
long komb_batch_size = 1024;
module_param(komb_batch_size, long, 0444);
#ifdef NUMA_AWARE
MODULE_INFO(rwsem_numa, "1");
#else
MODULE_INFO(rwsem_numa, "0");
#endif

static bool contexts_idle(void)
{
	struct komb_rwsem *lock = (void *)READ_ONCE(target_lock);
	int cpu, i;

	if (lock && (READ_ONCE(lock->writer_tail) || atomic_long_read(&lock->cnts) ||
		     atomic_read(&lock->reader_wait_lock.val)))
		return false;
	for_each_possible_cpu(cpu) {
		struct tc_rwsem_context *ctx = per_cpu(tc_rwsem_contexts, cpu);
		if (!ctx)
			continue;
		if (ctx->komb_curr_waiter_task || ctx->komb_prev_waiter_task ||
		    ctx->komb_next_waiter_task || ctx->komb_local_queue_head ||
		    ctx->komb_local_queue_tail ||
		    ctx->komb_stack_curr_ptr != ctx->komb_stack_base_ptr - 8)
			return false;
		for (i = 0; i < ARRAY_SIZE(ctx->komb_lock_addr); i++)
			if (ctx->komb_lock_addr[i])
				return false;
	}
	return true;
}

static bool registrations_idle(void)
{
	int cpu;
	for_each_possible_cpu(cpu) {
		struct tc_rwsem_context *ctx = per_cpu(tc_rwsem_contexts, cpu);
		if (ctx && READ_ONCE(ctx->task))
			return false;
	}
	return true;
}

int tc_rwsem_worker_register(void)
{
	struct tc_rwsem_context *ctx;
	int cpu, ret = 0;

	/* API is deliberately restricted to one registered task per fixed CPU.
	 * Registration and drain are never inside the operation loop. */
	if (current->nr_cpus_allowed != 1)
		return -EINVAL;
	cpu = cpumask_first(current->cpus_ptr);
	(mutex_lock)(&registration_lock);
	ctx = per_cpu(tc_rwsem_contexts, cpu);
	if (!ctx || ctx->task)
		ret = -EBUSY;
	else {
		get_task_struct(current);
		WRITE_ONCE(ctx->task, current);
	}
	(mutex_unlock)(&registration_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(tc_rwsem_worker_register);

int tc_rwsem_workers_drain(void)
{
	int cpu, ret = 0;

	(mutex_lock)(&registration_lock);
	if (!contexts_idle()) {
		ret = -EBUSY;
		goto out;
	}
	/* Caller joins all registered workers first. A quiescent queue alone
	 * would not authorize releasing a still-running worker's registration. */
	for_each_possible_cpu(cpu) {
		struct tc_rwsem_context *ctx = per_cpu(tc_rwsem_contexts, cpu);
		if (ctx && ctx->task && pid_alive(ctx->task)) {
			ret = -EBUSY;
			goto out;
		}
	}
	for_each_possible_cpu(cpu) {
		struct tc_rwsem_context *ctx = per_cpu(tc_rwsem_contexts, cpu);
		if (ctx && ctx->task) {
			put_task_struct(ctx->task);
			WRITE_ONCE(ctx->task, NULL);
		}
	}
out:
	(mutex_unlock)(&registration_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(tc_rwsem_workers_drain);

/* The supervisor calls this only after the client cohort has exited. */
static int drain_set(const char *value, const struct kernel_param *param)
{
	bool requested;
	int ret = kstrtobool(value, &requested);
	if (ret || !requested)
		return ret ? ret : -EINVAL;
	return tc_rwsem_workers_drain();
}
static const struct kernel_param_ops drain_ops = { .set = drain_set };
module_param_cb(drain, &drain_ops, NULL, 0200);

static int target_set(const char *value, const struct kernel_param *param)
{
	unsigned long address;
	int ret = kstrtoul(value, 0, &address);
	if (ret)
		return ret;
	if (address % __alignof__(struct komb_rwsem))
		return -EINVAL;
	if (!contexts_idle() || !registrations_idle())
		return -EBUSY;
	WRITE_ONCE(*(unsigned long *)param->arg, address);
	return 0;
}
static const struct kernel_param_ops target_ops = {
	.set = target_set, .get = param_get_ulong,
};
module_param_cb(target_lock, &target_ops, &target_lock, 0644);

static int observation_get(char *buffer, const struct kernel_param *param)
{
	u64 value = 0;
	int cpu;
	if (!param->arg)
		return scnprintf(buffer, PAGE_SIZE, "%d\n",
				 contexts_idle() && registrations_idle());
	for_each_possible_cpu(cpu) {
		struct tc_rwsem_context *ctx = per_cpu(tc_rwsem_contexts, cpu);
		if (ctx)
			value += READ_ONCE(*(u64 *)((char *)ctx + (unsigned long)param->arg));
	}
	return scnprintf(buffer, PAGE_SIZE, "%llu\n", value);
}
static const struct kernel_param_ops observation_ops = { .get = observation_get };
module_param_cb(quiescent, &observation_ops, NULL, 0444);

static void free_contexts(void)
{
	int cpu;
	for_each_possible_cpu(cpu) {
		struct tc_rwsem_context *ctx = per_cpu(tc_rwsem_contexts, cpu);
		if (!ctx)
			continue;
		WARN_ON_ONCE(ctx->task);
		vfree(ctx->stack_allocation);
		kfree(ctx);
		per_cpu(tc_rwsem_contexts, cpu) = NULL;
	}
}
static int __init tc_rwsem_init(void)
{
	int cpu;
	if (komb_batch_size != 1024)
		return -EINVAL;
	for_each_possible_cpu(cpu) {
		struct tc_rwsem_context *ctx = kzalloc_node(sizeof(*ctx), GFP_KERNEL,
							 cpu_to_node(cpu));
		if (!ctx)
			goto fail;
		per_cpu(tc_rwsem_contexts, cpu) = ctx;
		ctx->stack_allocation = vzalloc_node(SIZE_OF_SHADOW_STACK, cpu_to_node(cpu));
		if (!ctx->stack_allocation)
			goto fail;
		ctx->komb_stack_base_ptr = (unsigned long)ctx->stack_allocation +
					  SIZE_OF_SHADOW_STACK;
		ctx->komb_stack_curr_ptr = ctx->komb_stack_base_ptr - 8;
		ctx->komb_mutex_node = &ctx->node;
	}
	return 0;
fail:
	free_contexts();
	return -ENOMEM;
}
static void __exit tc_rwsem_exit(void)
{
	WARN_ON_ONCE(!contexts_idle());
	free_contexts();
}
module_init(tc_rwsem_init);
module_exit(tc_rwsem_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Upstream TCLock rwsem for registered fixed-affinity benchmark workers");
