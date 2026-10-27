// SPDX-License-Identifier: GPL-2.0
/* One ioctl per worker; all three backends share payload, mix and timing. */
#include <linux/fs.h>
#include <linux/ktime.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include "api.h"
#include "direct.h"
#include "payload.h"

/* -1 reserves configuration/snapshot; otherwise count admitted ioctls. */
static atomic_t rb_control __aligned(64) = ATOMIC_INIT(0);
struct rb_progress_slot { u64 completed; unsigned int claimed; } __aligned(128);
static struct rb_progress_slot rb_progress[RB_MAX_WORKERS];
static struct rw_bench_config rb_config;

static long rb_run(void __user *user)
{
	struct rw_bench_run run;
	struct rb_progress_slot *slot;
#ifdef RB_HASH
	struct sc_hash_stats stats = { 0 };
	u64 random;
#endif
	u64 state = 1, limit;
	unsigned int i, mix, before_preempt;
	bool before_irqs;
	int error = 0;

	if (copy_from_user(&run, user, sizeof(run)))
		return -EFAULT;
	if (run.reserved || run.reserved2 || run.iterations > 100000000 ||
	    (!run.deadline_ns && !run.iterations) || (run.deadline_ns && run.iterations))
		return -EINVAL;
	if (!atomic_add_unless(&rb_control, 1, -1))
		return -EBUSY;
	if (!run.started_ns || run.started_ns != rb_config.started_ns ||
	    run.deadline_ns != rb_config.deadline_ns || run.worker >= rb_config.workers) {
		error = -EINVAL;
		goto out;
	}
	slot = &rb_progress[run.worker];
	if (cmpxchg(&slot->claimed, 0, 1)) {
		error = -EBUSY;
		goto out;
	}
#if defined(RB_TCLOCK) && defined(RB_RWSEM)
	/* Register once per fixed-affinity client, before entering any lock body. */
	error = tc_rwsem_worker_register();
	if (error)
		goto out;
#elif defined(RB_TCLOCK) && defined(RB_MUTEX)
	error = tc_mutex_worker_register();
	if (error)
		goto out;
#endif
	before_preempt = preempt_count();
	before_irqs = irqs_disabled();
	run.cpu = raw_smp_processor_id();
#ifdef RB_HASH
	random = (run.cpu + 1ULL) * 0x9e3779b97f4a7c15ULL;
#endif
	mix = (run.worker * 17) % 100;
	run.completed = run.reads = run.writes = run.read_errors = run.read_hits = 0;
	run.active_started_ns = ktime_get_ns();
	if (run.deadline_ns && run.active_started_ns >= run.deadline_ns) {
		error = -ETIMEDOUT;
		goto out;
	}
	do {
		limit = run.deadline_ns ? RB_BATCH : min_t(u64, RB_BATCH, run.iterations - run.completed);
		for (i = 0; i < limit; i++) {
#ifdef RB_HASH
			u32 src = sc_hash_random(&random) % SC_HASH_KEY_RANGE;
			u32 dst = sc_hash_random(&random) % SC_HASH_KEY_RANGE;
#endif
			/* Evenly spaced writes with different worker phases, deterministic
			 * across backends. Selection stays outside both lock bodies. */
			mix += rb_config.write_percent;
			if (mix >= 100) {
				mix -= 100;
#ifdef RB_HASH
				rb_write(src, dst, &stats);
#else
				rb_write();
#endif
				run.writes++;
			} else {
#ifdef RB_HASH
				run.read_hits += rb_read(src);
#else
				run.read_errors += rb_read();
#endif
				run.reads++;
			}
			state = rb_post_work(state);
		}
		run.completed += limit;
		WRITE_ONCE(slot->completed, run.completed);
		run.finished_ns = ktime_get_ns();
	} while (run.deadline_ns ? run.finished_ns < run.deadline_ns : run.completed < run.iterations);
	run.checksum = state;
#ifdef RB_HASH
	atomic64_add(stats.moves, &sc_hash_moves);
	atomic64_add(stats.dests, &sc_hash_dests);
	atomic64_add(stats.misses, &sc_hash_misses);
#endif
	if (WARN_ON_ONCE(before_preempt != preempt_count() || before_irqs != irqs_disabled() ||
			 run.cpu != raw_smp_processor_id()))
		error = -EUCLEAN;
out:
	(void)atomic_dec_return_release(&rb_control);
	if (error)
		return error;
	return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
}

static long rb_read_progress(void __user *user)
{
	struct rw_bench_progress p = { 0 };
	unsigned int i;
	p.started_ns = READ_ONCE(rb_config.started_ns);
	p.deadline_ns = READ_ONCE(rb_config.deadline_ns);
	p.workers = READ_ONCE(rb_config.workers);
	if (!p.started_ns || !p.workers || p.workers > RB_MAX_WORKERS)
		return -EINVAL;
	p.read_started_ns = ktime_get_ns();
	for (i = 0; i < p.workers; i++)
		p.completed[i] = READ_ONCE(rb_progress[i].completed);
	p.read_finished_ns = ktime_get_ns();
	if (p.started_ns != READ_ONCE(rb_config.started_ns))
		return -EAGAIN;
	return copy_to_user(user, &p, sizeof(p)) ? -EFAULT : 0;
}

static long rb_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct rw_bench_config config;
	struct rw_bench_snapshot snap = {
		.version = RB_VERSION, .backend = RB_BACKEND, .lines = RB_LINES,
		.post_work_rounds = RB_POST_WORK_ROUNDS,
#ifdef RB_HASH
		.workload = 1,
#elif defined(RB_TASKNAME)
		.workload = 2,
#elif defined(RB_SNAPSHOT_PAYLOAD)
		.workload = 3,
#elif defined(RB_NANO)
		.workload = RB_WORKLOAD_NANO,
#endif
	};
	unsigned int i;
	int error = 0;

	if (cmd == RB_RUN)
		return rb_run(user);
	if (cmd == RB_PROGRESS)
		return rb_read_progress(user);
	if (cmd != RB_CONFIG && cmd != RB_SNAPSHOT && cmd != RB_PREPARE && cmd != RB_DRAIN)
		return -ENOTTY;
	if (atomic_cmpxchg_acquire(&rb_control, 0, -1))
		return -EBUSY;
	switch (cmd) {
	case RB_CONFIG:
		if (copy_from_user(&config, user, sizeof(config))) {
			error = -EFAULT;
			break;
		}
		if (!config.workers || config.workers > RB_MAX_WORKERS || config.write_percent > 100 ||
#ifdef RB_MUTEX
		    config.write_percent != 100 ||
#endif
		    !config.started_ns || config.started_ns > ktime_get_ns() ||
		    (config.deadline_ns && (config.deadline_ns <= ktime_get_ns() ||
		     config.deadline_ns <= config.started_ns ||
		     config.deadline_ns - config.started_ns > 10000000000ULL))) {
			error = -EINVAL;
			break;
		}
		WRITE_ONCE(rb_config.started_ns, 0);
		for (i = 0; i < RB_MAX_WORKERS; i++) {
			WRITE_ONCE(rb_progress[i].completed, 0);
			WRITE_ONCE(rb_progress[i].claimed, 0);
		}
		rb_config.deadline_ns = config.deadline_ns;
		rb_config.workers = config.workers;
		rb_config.write_percent = config.write_percent;
		WRITE_ONCE(rb_config.started_ns, config.started_ns);
		break;
	case RB_PREPARE:
		error = rb_prepare();
		break;
	case RB_DRAIN:
#if defined(RB_MUTEX) && defined(RB_TCLOCK)
		/* No worker can enter while the gate is reserved. The provider still
		 * requires exact task exit and queue/stack quiescence before releasing
		 * registrations; an EBUSY response never authorizes teardown. */
		error = tc_mutex_workers_drain();
#endif
		break;
	case RB_SNAPSHOT:
		rb_lock_snapshot(&snap);
#ifdef RB_HASH
		error = sc_hash_snapshot(&snap);
#elif defined(RB_NANO)
		error = rb_nano_snapshot(snap.values);
#else
		for (i = 0; i < RB_SLOTS; i++)
			snap.values[i] = READ_ONCE(rb_values[i].value);
#endif
		if (!error && copy_to_user(user, &snap, sizeof(snap)))
			error = -EFAULT;
		break;
	}
	atomic_set_release(&rb_control, 0);
	return error;
}

static const struct file_operations rb_fops = {
	.owner = THIS_MODULE, .unlocked_ioctl = rb_ioctl,
};
static struct miscdevice rb_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_rwlock_bench", .fops = &rb_fops, .mode = 0600,
};
static int __init rb_init(void)
{
	BUILD_BUG_ON(sizeof(struct rw_bench_config) != 24);
	BUILD_BUG_ON(sizeof(struct rw_bench_run) != 104);
	BUILD_BUG_ON(sizeof(struct rw_bench_snapshot) != 184);
	BUILD_BUG_ON(sizeof(struct rw_bench_progress) != 552);
	BUILD_BUG_ON(sizeof(struct rb_progress_slot) != 128);
#ifdef RB_NANO
	BUILD_BUG_ON(sizeof(struct rb_nano_record) != 64);
	BUILD_BUG_ON(offsetof(struct rb_nano_record, copy) != sizeof(u64));
#endif
#ifdef RB_HASH
	sc_hash_init();
#endif
	return misc_register(&rb_device);
}
static void __exit rb_exit(void)
{
	WARN_ON_ONCE(atomic_read(&rb_control));
	misc_deregister(&rb_device);
}
module_init(rb_init);
module_exit(rb_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Native/TCLock/KD lock workloads and minimal record nano");
