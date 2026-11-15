// SPDX-License-Identifier: GPL-2.0-only
/* Kernel16 7338197a only. No image publisher, hooks or replacement symbols. */
#include <linux/module.h>
#include <linux/kthread.h>
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/build_bug.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/jiffies.h>
#include <asm/msr.h>
#include <asm/msr-index.h>
#include "include/kd_spin_api.h"
#include "kernel/runtime.h"
#include "kernel/task_state.h"

#define WORKERS 2
#define ITERATIONS 64
#define BYTES(s) { .data = (s), .length = sizeof(s) - 1 }

/* Explicit prerequisites, not proof supplied by setting a boolean. */
static bool immutable_text, auxiliary_contract, gs_verified;
static unsigned long gs_offset;
static unsigned int cpu_a, cpu_b = 1;
module_param(immutable_text, bool, 0400);
module_param(auxiliary_contract, bool, 0400);
module_param(gs_verified, bool, 0400);
module_param(gs_offset, ulong, 0400);
module_param(cpu_a, uint, 0400);
module_param(cpu_b, uint, 0400);

static struct kd_spinlock lock;
static struct kd_jit_source_provider *provider;
static struct kd_jit_runtime *runtime;
static struct completion gate;
static atomic_t inside = ATOMIC_INIT(0);
static atomic_t overlaps = ATOMIC_INIT(0);
static unsigned long total;
static bool abort_run;
static const char version[] = "7338197a587fd84110fe710be63abafde270c02b-spin-simple";
static unsigned int config_identity, load_identity;
static struct module *source_modules[] = { THIS_MODULE };

struct worker {
	struct task_struct *task;
	struct completion ready, done;
	struct kd_task_storage *storage;
	unsigned int cpu, increments;
	int error;
};
static struct worker workers[WORKERS];

/* Unexpected cleanup errors retain this task, its stack and module init.
 * Returning and freeing live KD storage would turn a failure into corruption.
 */
static void notrace retain_failure(const char *stage, int error)
{
	pr_err("kd_spin_simple: retained at %s error=%d; no forced cleanup\n", stage, error);
	for (;;)
		msleep(1000);
}

static int notrace worker_main(void *arg)
{
	struct worker *w = arg;
	unsigned long gs;
	unsigned int i;
	int error;

	preempt_disable();
	rdmsrl(MSR_GS_BASE, gs);
	preempt_enable();
	error = kd_jit_runtime_enter_current(runtime, gs, &w->storage);
	w->error = error;
	if (error)
		WRITE_ONCE(abort_run, true);
	complete(&w->ready);
	wait_for_completion(&gate);
	if (!error && !READ_ONCE(abort_run)) {
		for (i = 0; i < ITERATIONS; ++i) {
			kd_spin_lock(&lock);
			/* This diagnostic does not provide exclusion for total. */
			if (atomic_inc_return(&inside) != 1)
				atomic_inc(&overlaps);
			WRITE_ONCE(total, READ_ONCE(total) + 1);
			w->increments++;
			if (atomic_dec_return(&inside) != 0)
				atomic_inc(&overlaps);
			kd_spin_unlock(&lock);
			cond_resched();
		}
	}
	while (w->storage) {
		struct kd_task_root_context *root = kd_task_storage_root(w->storage);
		struct kd_execution_binding *binding = smp_load_acquire(&root->core.binding);
		bool pending;

		error = kd_jit_runtime_leave_current(w->storage, binding, &pending);
		if (!error) {
			/* root and binding may already have been freed. */
			w->storage = NULL;
			break;
		}
		if (error != -EBUSY && error != -EAGAIN)
			retain_failure("task detach", error);
		cond_resched();
	}
	complete(&w->done);
	/* Keep the task alive until init joins it with kthread_stop(). */
	while (!kthread_should_stop())
		schedule_timeout_interruptible(HZ / 10);
	return w->error;
}

static void observe_completion(struct completion *done, const char *stage)
{
	if (!wait_for_completion_timeout(done, 5 * HZ)) {
		pr_err("kd_spin_simple: %s exceeded observer deadline; retaining state\n", stage);
		/* A wedged spin acquisition cannot be cancelled by a timer. */
		wait_for_completion(done);
	}
}

static void close_runtime(void)
{
	int error;

	while (runtime) {
		error = kd_jit_runtime_destroy(runtime);
		if (!error) {
			runtime = NULL;
			break;
		}
		if (error != -EBUSY && error != -EAGAIN)
			retain_failure("runtime destroy", error);
		msleep(20);
	}
	if (!provider)
		return;
	error = kd_jit_source_provider_close(provider);
	if (error && error != -EALREADY)
		retain_failure("provider close", error);
	error = kd_jit_source_provider_destroy(provider);
	if (error)
		retain_failure("provider destroy", error);
	provider = NULL;
}

static int __init simple_init(void)
{
	struct kd_jit_source_load_region region;
	struct kd_jit_source_provider_args source;
	struct kd_jit_runtime_config config;
	unsigned int i, created = 0;
	int error = 0;

	BUILD_BUG_ON(sizeof(struct kd_spinlock) != 2 * sizeof(void *));
	BUILD_BUG_ON(offsetof(struct kd_spinlock, queue) != 0);
	if (!IS_ENABLED(CONFIG_KDLOCK_REBUILD) || !IS_ENABLED(CONFIG_PREEMPT_COUNT) ||
	    IS_ENABLED(CONFIG_PREEMPT_RT) || IS_ENABLED(CONFIG_DEBUG_SPINLOCK) ||
	    IS_ENABLED(CONFIG_DEBUG_MUTEXES) || IS_ENABLED(CONFIG_DEBUG_LOCK_ALLOC) ||
	    IS_ENABLED(CONFIG_LOCKDEP))
		return -EOPNOTSUPP;
	if (!immutable_text || !auxiliary_contract || !gs_verified)
		return -EINVAL;
	cpus_read_lock();
	if (cpu_a == cpu_b || cpu_a >= nr_cpu_ids || cpu_b >= nr_cpu_ids ||
	    !cpu_online(cpu_a) || !cpu_online(cpu_b)) {
		error = -EINVAL;
		goto unlock_cpus;
	}
	region = (struct kd_jit_source_load_region) {
		.start = (unsigned long)THIS_MODULE->mem[MOD_TEXT].base,
		.length = THIS_MODULE->mem[MOD_TEXT].size,
	};
	source = (struct kd_jit_source_provider_args) {
		.contract = KD_JIT_SOURCE_IMMUTABLE_DEPENDENCIES,
		.version = (const unsigned char *)version, .version_length = sizeof(version) - 1,
		.regions = &region, .region_count = 1,
		.configuration_identity = &config_identity, .load_identity = &load_identity,
		.current_task_gs_offset = gs_offset,
		.modules = source_modules, .module_count = ARRAY_SIZE(source_modules),
	};
	error = kd_jit_source_provider_create(&source, &provider);
	if (error)
		goto unlock_cpus;
	config = (struct kd_jit_runtime_config) {
		.source = provider, .feedback_capacity = 4096, .cycle_capacity = 2,
		.image_capacity = 1, .claim_capacity = 4096,
		.compiled = { .code_capacity = 128 * 1024, .artifact_capacity = 512 * 1024,
			.flat_capacity = 256 * 1024, .entry_capacity = 64,
			.source_capacity = 4096, .observation_capacity = 4096 },
		.symbols = { .descriptor = BYTES("kd_spin_simple_image"),
			.source = BYTES("kd_spin_simple_epoch"),
			.producer = BYTES("kd_spin_simple_producer"),
			.entry = BYTES("kd_spin_simple_entry") },
		.channel_name = "kd_spin_simple", .owner = THIS_MODULE,
		.frame_capacity = 2 * 1024 * 1024, .request_capacity = 256,
		.auxiliary_bytes = 128 * 1024, .required_control_bytes = 32 * 1024,
		.atomic_spin = true, .family = KD_LOCK_FAMILY_SPIN, .proxy_limit = 1,
	};
	/* No controller opens this channel or publishes a translated image. */
	error = kd_jit_runtime_create(&config, &runtime);
	if (error)
		goto close;
	kd_spin_init(&lock);
	init_completion(&gate);
	workers[0].cpu = cpu_a;
	workers[1].cpu = cpu_b;
	for (i = 0; i < WORKERS; ++i) {
		struct worker *w = &workers[i];

		init_completion(&w->ready);
		init_completion(&w->done);
		w->task = kthread_create(worker_main, w, "kd_spin_simple/%u", i);
		if (IS_ERR(w->task)) {
			error = PTR_ERR(w->task);
			w->task = NULL;
			WRITE_ONCE(abort_run, true);
			break;
		}
		created++;
		kthread_bind(w->task, w->cpu);
		wake_up_process(w->task);
	}
	for (i = 0; i < created; ++i)
		observe_completion(&workers[i].ready, "task setup");
	complete_all(&gate);
	for (i = 0; i < created; ++i) {
		int joined;

		observe_completion(&workers[i].done, "worker completion/detach");
		joined = kthread_stop(workers[i].task);
		workers[i].task = NULL;
		if (joined && !error)
			error = joined;
		pr_info("kd_spin_simple: worker=%u cpu=%u increments=%u error=%d\n",
			i, workers[i].cpu, workers[i].increments, workers[i].error);
	}
	if (!error && (created != WORKERS || READ_ONCE(abort_run) ||
	    atomic_read(&inside) || atomic_read(&overlaps) || total != WORKERS * ITERATIONS))
		error = -EUCLEAN;
	for (i = 0; i < created; ++i)
		if (workers[i].increments != ITERATIONS && !error)
			error = -EUCLEAN;
close:
	close_runtime();
	pr_info("kd_spin_simple: result=%d total=%lu expected=%u overlaps=%d\n",
		error, total, WORKERS * ITERATIONS, atomic_read(&overlaps));
unlock_cpus:
	cpus_read_unlock();
	return error;
}

static void __exit simple_exit(void)
{
	/* Init returned only after every worker joined and KD storage retired. */
}
module_init(simple_init);
module_exit(simple_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Kernel16 two-worker KD spin API correctness fixture");
