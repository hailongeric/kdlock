// SPDX-License-Identifier: GPL-2.0-only
/* Ordinary Linux rwsem APIs on one cold, private, selected KD gate. */
#include <linux/capability.h>
#include <linux/completion.h>
#include <linux/errno.h>
#include <linux/err.h>
#include <linux/fs.h>
#include <linux/ioctl.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/limits.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/rwsem.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/tracepoint.h>
#include <linux/uaccess.h>

#include "include/kd_linux_rwsem.h"
#include "kernel/observation.h"
#include "kernel/rw_native.h"

#ifndef CONFIG_KDLOCK_REBUILD
#error "The rebuilt Linux rwsem binding is required"
#endif

#define API_RUN _IO('Q', 1)
#define API_STOP _IO('Q', 2)
#define WORKERS 3
#define CASES 12

static unsigned int native_capacity;
module_param(native_capacity, uint, 0400);
MODULE_PARM_DESC(native_capacity, "Required cold record capacity, at least three");
static unsigned int wait_timeout_ms;
module_param(wait_timeout_ms, uint, 0400);
MODULE_PARM_DESC(wait_timeout_ms, "Required positive bound for each controlled wait");

enum action { API_READ, API_WRITE, API_READ_INTR, API_READ_KILL, API_WRITE_KILL, API_NON_OWNER, API_CONVERT };
enum run_state { COLD, RUNNING, PASS, FAILED_RETAINED, DRAINED_FAILED };
struct worker {
	struct task_struct *task;
	struct completion entered, go, acquired, convert, converted, release, done;
	enum action action;
	bool pending_start, joined;
	int result, stop_result;
	bool pending_seen, granted;
	atomic_t nonowner_open;
};
struct case_result {
	bool ran;
	unsigned int used_mask;
	int result, values[WORKERS];
	bool granted[WORKERS], pending[WORKERS];
};
struct fixture {
	struct rw_semaphore sem;
	struct kd_rwsem gate;
	struct kd_rw_native_pool pool;
	struct kd_rw_native_record *records;
	struct kd_linux_rwsem_binding binding;
	struct worker workers[WORKERS];
	struct case_result cases[CASES];
	atomic64_t counts[8];
	atomic_t count_overflow;
	enum run_state state;
	unsigned int case_index, created, joined;
	int error, try_values[4];
	bool run_hold, turn_wait_proved, turn_cleanup_proved;
};
static struct fixture fixture;
static DEFINE_MUTEX(control_mutex);

static unsigned long wait_ticks(void)
{
	return max_t(unsigned long, 1, msecs_to_jiffies(wait_timeout_ms));
}

static void observe(void *unused, const struct kd_observation *event)
{
	unsigned int index;

	if (event->object != (unsigned long)&fixture.gate.core.queue)
		return;
	if (event->kind == KD_OBS_ENQUEUE)
		index = 7;
	else if (event->kind >= KD_OBS_NATIVE_READ_ACQUIRE &&
		 event->kind <= KD_OBS_NATIVE_TRY_MISS)
		index = event->kind - KD_OBS_NATIVE_READ_ACQUIRE;
	else
		return;
	if (!atomic64_add_unless(&fixture.counts[index], 1, S64_MAX))
		atomic_set(&fixture.count_overflow, 1);
}

static int body(void *argument)
{
	struct worker *worker = argument;
	/* Parentheses/function pointers retain the actual callable C ABI. */
	void (*read_call)(struct rw_semaphore *) = down_read;
	void (*write_call)(struct rw_semaphore *) = down_write;

	if (worker->action == API_READ_INTR)
		allow_signal(SIGUSR1);
	if (worker->action == API_READ_KILL || worker->action == API_WRITE_KILL)
		allow_signal(SIGKILL);
	complete(&worker->entered);
	if (worker->pending_start)
		wait_for_completion(&worker->go);
	worker->pending_seen = signal_pending(current);
	switch (worker->action) {
	case API_READ: read_call(&fixture.sem); worker->result = 0; break;
	case API_WRITE: write_call(&fixture.sem); worker->result = 0; break;
	case API_READ_INTR: worker->result = (down_read_interruptible)(&fixture.sem); break;
	case API_READ_KILL: worker->result = (down_read_killable)(&fixture.sem); break;
	case API_WRITE_KILL: worker->result = (down_write_killable)(&fixture.sem); break;
	case API_NON_OWNER: (down_read_non_owner)(&fixture.sem); worker->result = 0; break;
	case API_CONVERT: down_write(&fixture.sem); worker->result = 0; break;
	}
	if (!worker->result) {
		worker->granted = true;
		if (worker->action == API_NON_OWNER)
			atomic_set(&worker->nonowner_open, 1);
		complete(&worker->acquired);
		if (worker->action == API_CONVERT) {
			wait_for_completion(&worker->convert);
			downgrade_write(&fixture.sem);
			complete(&worker->converted);
		}
		if (worker->action != API_NON_OWNER) {
			wait_for_completion(&worker->release);
			if (worker->action == API_WRITE || worker->action == API_WRITE_KILL)
				up_write(&fixture.sem);
			else
				up_read(&fixture.sem);
		}
	}
	/* The controller retains task/control storage through actual kthread join. */
	complete(&worker->done);
	return 0;
}

static int start(unsigned int index, enum action action, bool pending_start)
{
	struct worker *worker = &fixture.workers[index];

	init_completion(&worker->entered);
	init_completion(&worker->go);
	init_completion(&worker->acquired);
	init_completion(&worker->convert);
	init_completion(&worker->converted);
	init_completion(&worker->release);
	init_completion(&worker->done);
	worker->action = action;
	worker->pending_start = pending_start;
	worker->joined = false;
	worker->result = -EINPROGRESS;
	worker->stop_result = -EINPROGRESS;
	worker->pending_seen = false;
	worker->granted = false;
	atomic_set(&worker->nonowner_open, 0);
	worker->task = kthread_create(body, worker, "kd-rwapi/%u", index);
	if (IS_ERR(worker->task)) {
		int result = PTR_ERR(worker->task);

		worker->task = NULL;
		return result;
	}
	get_task_struct(worker->task);
	fixture.created++;
	fixture.cases[fixture.case_index].used_mask |= 1U << index;
	wake_up_process(worker->task);
	return wait_for_completion_timeout(&worker->entered, wait_ticks()) ? 0 : -ETIMEDOUT;
}

static int acquired(unsigned int index)
{
	return wait_for_completion_timeout(&fixture.workers[index].acquired,
		wait_ticks()) ? 0 : -ETIMEDOUT;
}

static int join_one(unsigned int index)
{
	struct worker *worker = &fixture.workers[index];

	if (!worker->task || worker->joined)
		return 0;
	if (!wait_for_completion_timeout(&worker->done, wait_ticks()))
		return -ETIMEDOUT;
	/* done is the last body operation. kthread_stop establishes actual exit,
	 * rather than interpreting the wait bound as a join.
	 */
	worker->stop_result = kthread_stop(worker->task);
	if (worker->stop_result)
		return worker->stop_result;
	put_task_struct(worker->task);
	worker->task = NULL;
	worker->joined = true;
	fixture.joined++;
	return 0;
}

static int drain(void)
{
	unsigned int index;
	int result;

	/* Each owner performs its own release. The controller owns no semaphore
	 * grant, so a later STOP caller need not impersonate a previous owner.
	 */
	for (index = 0; index < WORKERS; ++index) {
		struct worker *worker = &fixture.workers[index];

		if (!worker->task || worker->joined)
			continue;
		complete_all(&worker->go);
		complete_all(&worker->convert);
		complete_all(&worker->release);
	}
	for (index = 0; index < WORKERS; ++index) {
		result = join_one(index);
		if (result)
			return result;
		if (atomic_xchg(&fixture.workers[index].nonowner_open, 0))
			up_read_non_owner(&fixture.sem);
	}
	return kd_rw_native_pool_idle(&fixture.pool) ? 0 : -EBUSY;
}

static int contended(void)
{
	unsigned long end = jiffies + wait_ticks();

	for (;;) {
		if (rwsem_is_contended(&fixture.sem))
			return 0;
		if (time_after_eq(jiffies, end))
			return -ETIMEDOUT;
		schedule_timeout_uninterruptible(1);
	}
}

static int reader_overlap(void)
{
	int result;

	result = start(0, API_READ, false);
	if (result || (result = acquired(0))) return result;
	result = start(1, API_READ, false);
	if (result || (result = acquired(1))) return result;
	if (!rwsem_is_locked(&fixture.sem)) return -EUCLEAN;
	result = start(2, API_WRITE, false);
	if (result || (result = contended())) return result;
	if (completion_done(&fixture.workers[2].acquired)) return -EUCLEAN;
	complete(&fixture.workers[0].release);
	if ((result = join_one(0))) return result;
	if (completion_done(&fixture.workers[2].acquired)) return -EUCLEAN;
	complete(&fixture.workers[1].release);
	if ((result = acquired(2))) return result;
	rwsem_assert_held_write(&fixture.sem);
#if defined(CONFIG_DEBUG_RWSEMS) || defined(CONFIG_DETECT_HUNG_TASK_BLOCKER)
	if (rwsem_owner(&fixture.sem) != fixture.workers[2].task ||
	    is_rwsem_reader_owned(&fixture.sem)) return -EUCLEAN;
#endif
	return drain();
}

static int try_and_constructors(void)
{
	long long enqueues, reads, writes;
	int result;

	/* Macros, real symbols and cleanup constructors all use the selected gate. */
	down_read(&fixture.sem);
	if (!rwsem_is_locked(&fixture.sem)) { up_read(&fixture.sem); return -EUCLEAN; }
	rwsem_assert_held(&fixture.sem);
	(up_read)(&fixture.sem);
	{ guard(rwsem_read)(&fixture.sem);
	  if (!rwsem_is_locked(&fixture.sem)) return -EUCLEAN;
	  rwsem_assert_held(&fixture.sem); }
	{ guard(rwsem_write)(&fixture.sem);
	  if (!kd_linux_rwsem_is_write_locked(&fixture.binding)) return -EUCLEAN;
	  rwsem_assert_held_write(&fixture.sem); }
	fixture.try_values[0] = (down_read_trylock)(&fixture.sem);
	if (fixture.try_values[0] == 1)
		up_read(&fixture.sem);
	else
		return -EUCLEAN;
	fixture.try_values[1] = (down_write_trylock)(&fixture.sem);
	if (fixture.try_values[1] == 1)
		(up_write)(&fixture.sem);
	else
		return -EUCLEAN;
	result = start(0, API_WRITE, false);
	if (result || (result = acquired(0))) return result;
	enqueues = atomic64_read(&fixture.counts[7]);
	reads = atomic64_read(&fixture.counts[0]);
	writes = atomic64_read(&fixture.counts[2]);
	fixture.try_values[2] = (down_read_trylock)(&fixture.sem);
	if (fixture.try_values[2] == 1)
		up_read(&fixture.sem);
	if (fixture.try_values[2])
		return -EUCLEAN;
	fixture.try_values[3] = (down_write_trylock)(&fixture.sem);
	if (fixture.try_values[3] == 1)
		up_write(&fixture.sem);
	if (fixture.try_values[3])
		return -EUCLEAN;
	if (enqueues != atomic64_read(&fixture.counts[7]) ||
	    reads != atomic64_read(&fixture.counts[0]) ||
	    writes != atomic64_read(&fixture.counts[2])) return -EUCLEAN;
	return drain();
}

static int conversion(void)
{
	int result = start(0, API_CONVERT, false);

	if (result || (result = acquired(0))) return result;
	complete(&fixture.workers[0].convert);
	if (!wait_for_completion_timeout(&fixture.workers[0].converted, wait_ticks()))
		return -ETIMEDOUT;
	result = start(1, API_READ, false);
	if (result || (result = acquired(1))) return result;
	/* Both exact real read credits exist before the former writer's up_read. */
	if (!rwsem_is_locked(&fixture.sem) ||
	    completion_done(&fixture.workers[0].done)) return -EUCLEAN;
	result = start(2, API_WRITE, false);
	if (result || (result = contended())) return result;
	if (completion_done(&fixture.workers[2].acquired)) return -EUCLEAN;
	complete(&fixture.workers[0].release);
	if ((result = join_one(0))) return result;
	if (completion_done(&fixture.workers[2].acquired)) return -EUCLEAN;
	complete(&fixture.workers[1].release);
	if ((result = acquired(2))) return result;
	return drain();
}

static int nonowner_transfer(void)
{
	int result = start(0, API_NON_OWNER, false);

	if (result || (result = acquired(0)) || (result = join_one(0))) return result;
	/* The acquiring thread has exited. Its nonowner credit remains exact. */
	if (!rwsem_is_locked(&fixture.sem) || !atomic_read(&fixture.workers[0].nonowner_open))
		return -EUCLEAN;
	up_read_non_owner(&fixture.sem);
	atomic_set(&fixture.workers[0].nonowner_open, 0);
	return kd_rw_native_pool_idle(&fixture.pool) ? 0 : -EBUSY;
}

/* This is the queue-head branch, distinct from a canceled successor whose
 * predecessor still owns WRITE. Inspect only exact persistent control under
 * the same family->pool ordering as the native backend.
 */
static int draining_turn(struct worker *worker)
{
	unsigned long end = jiffies + wait_ticks();
	unsigned int index;
	bool found;

	for (;;) {
		found = false;
		raw_spin_lock(&fixture.gate.core.guard);
		raw_spin_lock(&fixture.pool.guard);
		for (index = 0; index < native_capacity; ++index) {
			struct kd_rw_native_record *record = &fixture.records[index];

			/* writer_pending publishes the completed private batch constructor
			 * before inspecting its initialized field under the family guard.
			 */
			if (fixture.gate.core.writer_pending && !fixture.gate.core.writer &&
			    fixture.gate.core.readers && record->task == worker->task &&
			    record->phase == KD_RW_NATIVE_WRITE_WAIT && record->turn_owned &&
			    record->batch.initialized && record->queue_user && !record->grant_user)
				found = true;
		}
		raw_spin_unlock(&fixture.pool.guard);
		raw_spin_unlock(&fixture.gate.core.guard);
		if (found) {
			fixture.turn_wait_proved = true;
			return 0;
		}
		if (time_after_eq(jiffies, end)) return -ETIMEDOUT;
		schedule_timeout_uninterruptible(1);
	}
}

static int cancelled(enum action action, int signal, bool read_blocker)
{
	unsigned int index;
	bool queued_cancel = false, turn_clean;
	long long write_grants;
	int result = start(0, read_blocker ? API_READ : API_WRITE, false);

	if (result || (result = acquired(0))) return result;
	write_grants = atomic64_read(&fixture.counts[2]);
	result = start(1, action, false);
	if (result || (result = contended())) return result;
	if (read_blocker && (result = draining_turn(&fixture.workers[1]))) return result;
	if ((result = send_sig(signal, fixture.workers[1].task, 1))) return result;
	if ((result = join_one(1))) return result;
	if (fixture.workers[1].result != -EINTR || fixture.workers[1].granted)
		return -EUCLEAN;
	if (read_blocker) {
		if (!rwsem_is_locked(&fixture.sem) || kd_linux_rwsem_is_write_locked(&fixture.binding) ||
		    write_grants != atomic64_read(&fixture.counts[2])) return -EUCLEAN;
		raw_spin_lock(&fixture.gate.core.guard);
		turn_clean = !fixture.gate.core.writer_pending && !fixture.gate.core.writer &&
			!READ_ONCE(fixture.gate.core.queue.tail) && fixture.gate.core.readers == 1;
		raw_spin_unlock(&fixture.gate.core.guard);
		if (!turn_clean) return -EUCLEAN;
		fixture.turn_cleanup_proved = true;
	} else {
		rwsem_assert_held_write(&fixture.sem);
	}
	if (completion_done(&fixture.workers[0].done)) return -EUCLEAN;
	if (action == API_WRITE_KILL && !read_blocker) {
		raw_spin_lock(&fixture.pool.guard);
		for (index = 0; index < native_capacity; ++index)
			if (fixture.records[index].phase == KD_RW_NATIVE_CANCELLED &&
			    fixture.records[index].queue_user &&
			    !fixture.records[index].caller_user && !fixture.records[index].grant_user)
				queued_cancel = true;
		raw_spin_unlock(&fixture.pool.guard);
		if (!queued_cancel) return -EUCLEAN;
	}
	return drain();
}

static int ready_pending(enum action action, int signal)
{
	int result = start(0, action, true);

	if (result) return result;
	if ((result = send_sig(signal, fixture.workers[0].task, 1))) return result;
	complete(&fixture.workers[0].go);
	if ((result = acquired(0))) return result;
	if (fixture.workers[0].result || !fixture.workers[0].pending_seen)
		return -EUCLEAN;
	return drain();
}

static int run_case(unsigned int index)
{
	switch (index) {
	case 0: return reader_overlap();
	case 1: return try_and_constructors();
	case 2: return conversion();
	case 3: return nonowner_transfer();
	case 4: return cancelled(API_READ_INTR, SIGUSR1, false);
	case 5: return cancelled(API_READ_KILL, SIGKILL, false);
	case 6: return cancelled(API_WRITE_KILL, SIGKILL, false);
	case 7: return ready_pending(API_READ_INTR, SIGUSR1);
	case 8: return ready_pending(API_READ_KILL, SIGKILL);
	case 9: return ready_pending(API_WRITE_KILL, SIGKILL);
	case 10: return cancelled(API_WRITE_KILL, SIGKILL, true);
	case 11:
		if (atomic_read(&fixture.count_overflow) ||
		    !kd_rw_native_pool_idle(&fixture.pool) || rwsem_is_locked(&fixture.sem))
			return -EUCLEAN;
		return 0;
	}
	return -EINVAL;
}

static long control(struct file *file, unsigned int command, unsigned long argument)
{
	unsigned int index, worker;
	int result = 0;

	if (!capable(CAP_SYS_ADMIN)) return -EPERM;
	if (argument || (command != API_RUN && command != API_STOP)) return -EINVAL;
	if (mutex_lock_interruptible(&control_mutex)) return -EINTR;
	if (command == API_STOP) {
		result = drain();
		if (!result && fixture.run_hold) {
			fixture.run_hold = false;
			fixture.state = DRAINED_FAILED;
			module_put(THIS_MODULE);
		}
		goto out;
	}
	if (fixture.state != COLD) { result = -EALREADY; goto out; }
	if (!try_module_get(THIS_MODULE)) { result = -ENODEV; goto out; }
	fixture.run_hold = true;
	fixture.state = RUNNING;
	for (index = 0; index < CASES; ++index) {
		fixture.case_index = index;
		fixture.cases[index].ran = true;
		for (worker = 0; worker < WORKERS; ++worker) {
			fixture.workers[worker].result = -EINPROGRESS;
			fixture.workers[worker].granted = false;
			fixture.workers[worker].pending_seen = false;
		}
		result = run_case(index);
		fixture.cases[index].result = result;
		for (worker = 0; worker < WORKERS; ++worker) {
			fixture.cases[index].values[worker] = READ_ONCE(fixture.workers[worker].result);
			fixture.cases[index].granted[worker] = READ_ONCE(fixture.workers[worker].granted);
			fixture.cases[index].pending[worker] = READ_ONCE(fixture.workers[worker].pending_seen);
		}
		if (result) break;
	}
	fixture.error = result;
	if (result) {
		fixture.state = FAILED_RETAINED;
	} else {
		fixture.state = PASS;
		fixture.run_hold = false;
		module_put(THIS_MODULE);
	}
out:
	mutex_unlock(&control_mutex);
	return result;
}

static ssize_t status_read(struct file *file, char __user *buffer, size_t length, loff_t *offset)
{
	char *text;
	size_t used;
	unsigned int index;
	ssize_t result;

	text = kmalloc(PAGE_SIZE, GFP_KERNEL);
	if (!text) return -ENOMEM;
	if (mutex_lock_interruptible(&control_mutex)) { kfree(text); return -EINTR; }
	used = scnprintf(text, PAGE_SIZE,
		"{\"state\":%u,\"error\":%d,\"case_index\":%u,\"created\":%u,\"joined\":%u,"
		"\"module_hold\":%u,\"pool_idle\":%u,\"count_overflow\":%u,"
		"\"turn_wait_proved\":%u,\"turn_cleanup_proved\":%u,\"native_counts\":[",
		fixture.state, fixture.error, fixture.case_index, fixture.created, fixture.joined,
		fixture.run_hold, kd_rw_native_pool_idle(&fixture.pool), atomic_read(&fixture.count_overflow),
		fixture.turn_wait_proved, fixture.turn_cleanup_proved);
	for (index = 0; index < ARRAY_SIZE(fixture.counts); ++index)
		used += scnprintf(text + used, PAGE_SIZE - used, "%s%lld", index ? "," : "",
			(long long)atomic64_read(&fixture.counts[index]));
	used += scnprintf(text + used, PAGE_SIZE - used,
		"],\"try_returns\":[%d,%d,%d,%d],\"cases\":[",
		fixture.try_values[0], fixture.try_values[1], fixture.try_values[2], fixture.try_values[3]);
	for (index = 0; index < CASES; ++index)
		used += scnprintf(text + used, PAGE_SIZE - used,
			"%s{\"ran\":%u,\"used_mask\":%u,\"result\":%d,\"returns\":[%d,%d,%d],\"granted\":[%u,%u,%u],\"pending\":[%u,%u,%u]}",
			index ? "," : "", fixture.cases[index].ran, fixture.cases[index].used_mask,
			fixture.cases[index].result,
			fixture.cases[index].values[0], fixture.cases[index].values[1], fixture.cases[index].values[2],
			fixture.cases[index].granted[0], fixture.cases[index].granted[1], fixture.cases[index].granted[2],
			fixture.cases[index].pending[0], fixture.cases[index].pending[1], fixture.cases[index].pending[2]);
	used += scnprintf(text + used, PAGE_SIZE - used, "],\"workers\":[");
	for (index = 0; index < WORKERS; ++index) {
		struct worker *worker = &fixture.workers[index];

		used += scnprintf(text + used, PAGE_SIZE - used,
			"%s{\"task\":%llu,\"joined\":%u,\"done\":%u,\"return\":%d,\"stop_return\":%d,\"nonowner_open\":%d}",
			index ? "," : "", (unsigned long long)(unsigned long)worker->task,
			worker->joined, worker->task ? completion_done(&worker->done) : 0,
			READ_ONCE(worker->result), worker->stop_result, atomic_read(&worker->nonowner_open));
	}
	used += scnprintf(text + used, PAGE_SIZE - used, "]}\n");
	result = simple_read_from_buffer(buffer, length, offset, text, used);
	mutex_unlock(&control_mutex);
	kfree(text);
	return result;
}

static const struct file_operations operations = {
	.owner = THIS_MODULE, .unlocked_ioctl = control, .read = status_read, .llseek = no_llseek,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_rwsem_api", .fops = &operations, .mode = 0600,
};

static int __init load(void)
{
	unsigned int index;
	int result;

	if (native_capacity < WORKERS || !wait_timeout_ms) return -EINVAL;
	for (index = 0; index < ARRAY_SIZE(fixture.try_values); ++index)
		fixture.try_values[index] = -EINPROGRESS;
	fixture.records = kvcalloc(native_capacity, sizeof(*fixture.records), GFP_KERNEL);
	if (!fixture.records) return -ENOMEM;
	init_rwsem(&fixture.sem);
	kd_rwsem_init(&fixture.gate);
	result = kd_rw_native_pool_init(&fixture.gate.core, &fixture.pool, fixture.records, native_capacity);
	if (result) goto free_private;
	result = kd_linux_rwsem_bind(&fixture.sem, &fixture.binding, &fixture.gate, false);
	if (result) goto free_private;
	for (index = 0; index < ARRAY_SIZE(fixture.counts); ++index)
		atomic64_set(&fixture.counts[index], 0);
	atomic_set(&fixture.count_overflow, 0);
	result = register_trace_kdlock_observe_tp(observe, NULL);
	if (result) goto unbind;
	result = misc_register(&device);
	if (!result) return 0;
	unregister_trace_kdlock_observe_tp(observe, NULL);
	tracepoint_synchronize_unregister();
unbind:
	(void)kd_linux_rwsem_unbind(&fixture.binding);
free_private:
	kvfree(fixture.records);
	return result;
}

static void __exit unload(void)
{
	/* Open fds and the explicit failed-run hold exclude active callbacks and
	 * workers. Only a cold or actually drained fixture can reach this point.
	 */
	misc_deregister(&device);
	unregister_trace_kdlock_observe_tp(observe, NULL);
	tracepoint_synchronize_unregister();
	(void)kd_linux_rwsem_unbind(&fixture.binding);
	kvfree(fixture.records);
}
module_init(load);
module_exit(unload);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Bounded ordinary Linux rwsem compatibility checks");
