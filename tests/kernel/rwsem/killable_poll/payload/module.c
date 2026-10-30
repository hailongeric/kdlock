// SPDX-License-Identifier: GPL-2.0
/* Source-extracted admission only; no physical gate or protected body. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/fs.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/uaccess.h>
#include "kd_rwsem_types.h"
#include "api.h"

static unsigned int cpu;
module_param(cpu, uint, 0444);
static DEFINE_KD_RWSEM(sem);
static DEFINE_MUTEX(run_mutex);
static bool used;
static struct kd_poll_report report;
struct poll_worker {
	struct task_struct *task;
	struct completion done;
	struct kd_poll_case *row;
};
static struct poll_worker *active;

/* Both generated files retain exact production text; wrappers below alter
 * observation only. The plain reserve also establishes the controller's
 * private phase, without pretending that it has acquired the physical gate. */
#include "reserve-source.inc"

static bool observed_reserve(struct kd_rwsem *lock)
{
	bool won;
	struct kd_poll_case *row = active->row;

	row->reserve_calls++;
	won = kd_rwsem_reserve_local(lock);
	row->reserve_wins += won;
	return won;
}
static bool observed_need_resched(void)
{
	bool pending = need_resched();

	active->row->resched_calls++;
	active->row->resched_true += pending;
	return pending;
}
static bool observed_signal_pending(struct task_struct *task)
{
	bool pending = signal_pending(task);

	active->row->signal_calls++;
	active->row->signal_true += pending;
	return pending;
}
static void observed_cpu_relax(void)
{
	active->row->relax_calls++;
	cpu_relax();
}
#define kd_rwsem_reserve_local observed_reserve
#undef need_resched
#define need_resched observed_need_resched
#define signal_pending observed_signal_pending
#undef cpu_relax
#define cpu_relax observed_cpu_relax
#include "poll-source.inc"
#undef kd_rwsem_reserve_local
#undef need_resched
#undef signal_pending
#undef cpu_relax

static bool unpublished(void)
{
	return !waitqueue_active(&sem.phase_wait) &&
	       !waitqueue_active(&sem.reader_drain) &&
	       !atomic_read(&sem.reader_osq.tail) &&
	       !atomic_long_read(&sem.readers) &&
	       !atomic_long_read(&sem.gate.owner) &&
	       !atomic_read(&sem.gate.osq.tail) &&
	       !READ_ONCE(sem.gate.wait_head) &&
	       !atomic_read(&sem.gate.delegation_state) &&
	       !READ_ONCE(sem.gate.delegation_tail);
}

static int poll_main(void *data)
{
	struct poll_worker *worker = data;
	struct kd_poll_case *row = worker->row;
	int ret;

	allow_signal(SIGUSR1);
	allow_signal(SIGKILL);
	cond_resched();
	ret = send_sig(row->signal, current, 1);
	row->send_error = ret ? -ret : 0;
	row->pending_before = signal_pending(current);
	row->fatal_before = fatal_signal_pending(current);
	row->preempt_before = preempt_count();
	row->irq_before = irqs_disabled();
	if (!ret) {
		row->returned = kd_rwsem_poll_killable(&sem);
		row->admission_after = atomic_long_read(&sem.admission);
		row->preempt_after = preempt_count();
		row->irq_after = irqs_disabled();
		if (!row->busy && row->returned) {
			/* This worker alone owns the successful phase CAS. No gate,
			 * reader or waiter exists on this private diagnostic object. */
			row->cleanup_ok = atomic_long_cmpxchg(&sem.admission,
				KD_RWSEM_LOCAL_WRITER, 0) == KD_RWSEM_LOCAL_WRITER;
		}
	}
	row->errors += ret != 0 || !unpublished();
	/* Do not allow a pending test signal to affect kthread completion/join. */
	flush_signals(current);
	complete(&worker->done);
	return 0;
}

static void validate_case(struct kd_poll_case *row)
{
	row->errors += row->pending_before != 1 ||
		row->fatal_before != (row->signal == SIGKILL) ||
		row->preempt_before || row->preempt_after ||
		row->irq_before || row->irq_after ||
		row->admission_after != (u64)KD_RWSEM_LOCAL_WRITER ||
		row->cleanup_ok != 1;
	if (row->busy) {
		/* A real scheduler request is a legitimate helper exit, but it
		 * cannot establish that the signal predicate stopped the poll. */
		row->inconclusive = row->resched_true != 0;
		row->errors += row->returned || row->reserve_calls != 1 ||
			row->reserve_wins || row->relax_calls || row->resched_calls != 1;
		if (!row->inconclusive)
			row->errors += row->signal_calls != 1 || row->signal_true != 1;
	} else {
		row->errors += !row->returned || row->reserve_calls != 1 ||
			row->reserve_wins != 1 || row->resched_calls ||
			row->signal_calls || row->relax_calls;
	}
}

static long run_probe(void)
{
	unsigned int i;

	report.abi = 1;
	for (i = 0; i < KD_POLL_CASES; i++) {
		struct kd_poll_case *row = &report.rows[i];
		struct poll_worker worker;
		bool controller_owned = false;
		int ret;

		row->id = i;
		row->signal = i % 2 ? SIGKILL : SIGUSR1;
		row->busy = i < 2;
		worker.row = row;
		init_completion(&worker.done);
		if (row->busy) {
			controller_owned = kd_rwsem_reserve_local(&sem);
			if (!controller_owned) {
				report.errors++;
				break;
			}
		}
		active = &worker;
		worker.task = kthread_create(poll_main, &worker, "kd-rwpoll");
		if (IS_ERR(worker.task)) {
			row->errors++;
			if (controller_owned)
				row->cleanup_ok = atomic_long_cmpxchg(&sem.admission,
					KD_RWSEM_LOCAL_WRITER, 0) == KD_RWSEM_LOCAL_WRITER;
			report.errors++;
			active = NULL;
			break;
		}
		get_task_struct(worker.task);
		kthread_bind(worker.task, cpu);
		wake_up_process(worker.task);
		if (!wait_for_completion_timeout(&worker.done, 5 * HZ)) {
			report.timeouts++;
			/* Keep stack/module/phase lifetime until the actual worker
			 * finishes. Userspace timeout must leave this ioctl intact. */
			wait_for_completion(&worker.done);
		}
		ret = kthread_stop(worker.task);
		put_task_struct(worker.task);
		report.joined++;
		active = NULL;
		row->errors += ret != 0;
		if (controller_owned)
			row->cleanup_ok = atomic_long_cmpxchg(&sem.admission,
				KD_RWSEM_LOCAL_WRITER, 0) == KD_RWSEM_LOCAL_WRITER;
		validate_case(row);
		report.errors += row->errors;
		report.inconclusive += row->inconclusive;
		report.cases++;
		if (row->errors || row->inconclusive || report.timeouts)
			break;
	}
	report.phase_idle = !atomic_long_read(&sem.admission) && unpublished();
	report.complete = report.joined == report.cases && report.phase_idle;
	return 0;
}

static long probe_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
	long ret;

	(void)file;
	if (command != KD_POLL_RUN)
		return -ENOTTY;
	if (!mutex_trylock(&run_mutex))
		return -EBUSY;
	if (used) {
		ret = -EALREADY;
		goto out;
	}
	used = true;
	cpus_read_lock();
	if (cpu >= nr_cpu_ids || !cpu_online(cpu)) {
		ret = -EINVAL;
		goto cpu_out;
	}
	run_probe();
	ret = copy_to_user((void __user *)arg, &report, sizeof(report)) ? -EFAULT : 0;
cpu_out:
	cpus_read_unlock();
out:
	mutex_unlock(&run_mutex);
	return ret;
}
static const struct file_operations probe_fops = {
	.owner = THIS_MODULE, .unlocked_ioctl = probe_ioctl,
};
static struct miscdevice probe_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_rwsem_poll_probe", .fops = &probe_fops,
	.mode = 0600,
};
static int __init probe_init(void)
{
	BUILD_BUG_ON(sizeof(report) != 768);
	return misc_register(&probe_device);
}
static void __exit probe_exit(void)
{
	misc_deregister(&probe_device);
}
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Source-extracted killable phase polling with real pending signals");
