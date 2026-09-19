// SPDX-License-Identifier: GPL-2.0
/* Guest-only component benchmark. The build directory supplies an unchanged
 * production sampler and header; no provider hooks, JIT or application locks
 * are installed. Preparation uses real time and natural state transitions.
 * Time is read outside each worker's entire record loop, never per record. */
#include <linux/module.h>
#include <linux/kthread.h>
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/slab.h>
#include <linux/ktime.h>
#include <linux/cpu.h>
#include "kd_hotlock.c"

static unsigned int threads = 1;
static unsigned int phase;
static unsigned int iterations = 100000;
module_param(threads, uint, 0400);
module_param(phase, uint, 0400); /* 0 discovery, 1 sparse cold keys, 2 DELEGATE */
module_param(iterations, uint, 0400);

static unsigned long measured_key, warmup_key;
/* At most 4883 observations/key even at 20 * 1e6 calls; no hot key. */
static unsigned long cold_keys[4096];
static DECLARE_COMPLETION(start);
static DECLARE_COMPLETION(ready);
static atomic_t ready_count = ATOMIC_INIT(0);
struct record_worker {
	struct task_struct *task;
	struct completion done;
	u64 begin, end;
	unsigned int calls;
	bool balanced;
} ____cacheline_aligned;

#ifdef KD_HOTLOCK_CPU_WINDOW
/* Open this CPU through observations, never by editing sampler state. Keep
 * the per-CPU discovery cost outside the single-lock/terminal measurement. */
static void prepare_cpu_gate(void)
{
	unsigned int i;

#ifdef KD_HOTLOCK_LOCAL_DISCOVERY_V1
	for (i = 0; i < 2 * KD_HOTLOCK_CHECK_INTERVAL; i++)
#else
	for (i = 0; i < KD_HOTLOCK_CPU_TARGET + KD_HOTLOCK_BATCH; i++)
#endif
		kd_hotlock_record((unsigned long)&warmup_key);
}
#endif

static int worker_main(void *arg)
{
	struct record_worker *w = arg;
	unsigned int before, i;
	bool irq;

	if (atomic_inc_return(&ready_count) == threads)
		complete(&ready);
	wait_for_completion(&start);
#ifdef KD_HOTLOCK_CPU_WINDOW
	prepare_cpu_gate();
#endif
	/* Terminal timing starts only after this worker has naturally admitted
	 * the measured key on its own CPU. Never inherit a global-only hint. */
	if (phase == 2)
		for (i = 0; i < 24000; i++)
			kd_hotlock_record((unsigned long)&measured_key);
	before = preempt_count();
	irq = irqs_disabled();
	w->begin = ktime_get_ns();
	while (w->calls < iterations && !kthread_should_stop()) {
		unsigned long addr = phase == 1 ?
			(unsigned long)&cold_keys[w->calls % ARRAY_SIZE(cold_keys)] :
			(unsigned long)&measured_key;
		int promoted = kd_hotlock_record(addr);
		w->calls++;
		if (!phase && promoted)
			break;
	}
	w->end = ktime_get_ns();
	w->balanced = before == preempt_count() && irq == irqs_disabled();
	complete(&w->done);
	/* Keep the task alive for kthread_stop, even if initialization failed. */
	set_current_state(TASK_INTERRUPTIBLE);
	while (!kthread_should_stop()) {
		schedule();
		set_current_state(TASK_INTERRUPTIBLE);
	}
	__set_current_state(TASK_RUNNING);
	return 0;
}

#ifndef KD_HOTLOCK_CPU_WINDOW
/* Compatibility with frozen pre-CPU-gate baselines, outside all timings. */
static void wait_cycles(unsigned long cycles)
{
	unsigned long begin = rdtsc_ordered();
	while (rdtsc_ordered() - begin <= cycles)
		msleep(10);
}
#endif

static int __init record_bench_init(void)
{
	struct record_worker *workers;
	unsigned int i, created = 0;
	bool hot;
	u64 first = U64_MAX, last = 0, calls = 0, worker_ns = 0;
	int ret;

	if (!threads || threads > 20 || phase > 2 || !iterations || iterations > 1000000)
		return -EINVAL;
	for (i = 0; i < threads; i++)
		if (!cpu_online(i))
			return -ENODEV;
	ret = kd_hotlock_init();
	if (ret)
		return ret;
#ifndef KD_HOTLOCK_CPU_WINDOW
	kd_hotlock_record((unsigned long)&warmup_key);
	wait_cycles(KD_HOTLOCK_WARMUP_CYCLES);
#endif
	workers = kcalloc(threads, sizeof(*workers), GFP_KERNEL);
	if (!workers) { ret = -ENOMEM; goto out; }
	for (i = 0; i < threads; i++) {
		init_completion(&workers[i].done);
		workers[i].task = kthread_create(worker_main, &workers[i], "kd-record/%u", i);
		if (IS_ERR(workers[i].task)) {
			ret = PTR_ERR(workers[i].task);
			goto stop;
		}
		created++;
		kthread_bind(workers[i].task, i);
		wake_up_process(workers[i].task);
	}
	if (!wait_for_completion_timeout(&ready, 5 * HZ)) { ret = -ETIMEDOUT; goto stop; }
	complete_all(&start);
	for (i = 0; i < threads; i++) {
		if (!wait_for_completion_timeout(&workers[i].done, 15 * HZ)) {
			ret = -ETIMEDOUT;
			goto stop;
		}
		if (!workers[i].balanced || !workers[i].calls) { ret = -EUCLEAN; goto stop; }
		first = min(first, workers[i].begin);
		last = max(last, workers[i].end);
		calls += workers[i].calls;
		worker_ns += workers[i].end - workers[i].begin;
	}
	hot = kd_hotlock_is_promoted((unsigned long)&measured_key);
	if (phase == 1) {
		for (i = 0; i < ARRAY_SIZE(cold_keys); i++)
			if (kd_hotlock_is_promoted((unsigned long)&cold_keys[i])) {
				ret = -EUCLEAN;
				goto stop;
			}
	} else if (!hot) {
		ret = -EUCLEAN;
		goto stop;
	}
	pr_info("HOTLOCK_RECORD phase=%u threads=%u calls=%llu wall_ns=%llu worker_ns=%llu status=%u balanced=1\n",
		phase, threads, calls, last - first, worker_ns, phase == 1 ? 0 : 2);

stop:
	complete_all(&start);
	for (i = 0; i < created; i++)
		kthread_stop(workers[i].task);
	kfree(workers);
out:
	kd_hotlock_exit();
	return ret;
}
static void __exit record_bench_exit(void) { }
module_init(record_bench_init);
module_exit(record_bench_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Recovery-only unchanged hotlock sampler component benchmark");
