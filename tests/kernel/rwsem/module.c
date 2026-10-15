// SPDX-License-Identifier: GPL-2.0
/* Ordinary sleeping API probe. Real JIT acceptance is a separate benchmark. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/sched/task.h>
#include <linux/uaccess.h>
#include "kd_rwsem.h"

static DEFINE_KD_RWSEM(sem);
static DEFINE_MUTEX(control);
static atomic_t reading = ATOMIC_INIT(0), writing = ATOMIC_INIT(0), errors = ATOMIC_INIT(0);
struct worker {
	struct task_struct *task;
	struct completion entered, release, done;
	bool writer;
	u64 switches;
};
static struct worker workers[4];
struct result { u64 errors, api_checks, readers_slept, writer_slept, late_reader_slept, idle; };
#define RUN _IOR('S', 1, struct result)

static void check_at(bool condition, unsigned int line)
{
	if (!condition) {
		atomic_inc(&errors);
		pr_info("rwsem probe check failed at line %u\n", line);
	}
}
#define check(condition) check_at(!!(condition), __LINE__)

static int worker_main(void *data)
{
	struct worker *w = data;
	unsigned long before = current->nvcsw;
	if (w->writer) {
		kd_down_write(&sem);
		check(!atomic_read(&reading));
		check(atomic_inc_return(&writing) == 1);
	} else {
		kd_down_read(&sem);
		atomic_inc(&reading);
		check(!atomic_read(&writing));
	}
	complete(&w->entered);
	wait_for_completion(&w->release);
	if (w->writer) {
		atomic_dec(&writing);
		kd_up_write(&sem);
	} else {
		check(!atomic_read(&writing));
		atomic_dec(&reading);
		kd_up_read(&sem);
	}
	w->switches = current->nvcsw - before;
	complete(&w->done);
	return 0;
}

static int start(unsigned int i, bool writer)
{
	struct worker *w = &workers[i];
	w->writer = writer;
	w->task = kthread_create(worker_main, w, "kd_rwsem_probe");
	if (IS_ERR(w->task)) {
		int ret = PTR_ERR(w->task);
		w->task = NULL;
		return ret;
	}
	get_task_struct(w->task);
	kthread_bind(w->task, i);
	wake_up_process(w->task);
	return 0;
}

static bool entered(unsigned int i)
{
	return wait_for_completion_timeout(&workers[i].entered, 5 * HZ) != 0;
}

static bool parked(struct task_struct *task)
{
	unsigned long deadline = jiffies + 5 * HZ;
	do {
		if (READ_ONCE(task->__state) & TASK_UNINTERRUPTIBLE)
			return true;
		msleep(1);
	} while (time_before(jiffies, deadline));
	return false;
}

static long run(void __user *user)
{
	struct result r = { 0 };
	unsigned int i;
	int ret = 0;
	if (!mutex_trylock(&control))
		return -EBUSY;
	for (i = 0; i < 4; i++) {
		if (!cpu_online(i)) {
			ret = -EINVAL;
			goto unlock;
		}
	}
	atomic_set(&errors, 0);
	check(kd_rwsem_is_idle(&sem));
	kd_rwsem_init(&sem);
	/* Trylocks and downgrade: no intervening writer is possible. */
	if (!kd_down_read_trylock(&sem)) {
		check(false);
		goto result;
	}
	if (!kd_down_read_trylock(&sem)) {
		check(false);
		kd_up_read(&sem);
		goto result;
	}
	check(!kd_down_write_trylock(&sem));
	kd_up_read(&sem);
	kd_up_read(&sem);
	if (!kd_down_write_trylock(&sem)) {
		check(false);
		goto result;
	}
	check(!kd_down_read_trylock(&sem));
	check(!kd_down_write_trylock(&sem));
	kd_downgrade_write(&sem);
	if (!kd_down_read_trylock(&sem)) {
		check(false);
		kd_up_read(&sem);
		goto result;
	}
	check(!kd_down_write_trylock(&sem));
	kd_up_read(&sem);
	kd_up_read(&sem);
	check(kd_rwsem_is_idle(&sem));
	r.api_checks = 8;
	if (atomic_read(&errors))
		goto result;
	for (i = 0; i < 4; i++) {
		workers[i].task = NULL;
		workers[i].switches = 0;
		init_completion(&workers[i].entered);
		init_completion(&workers[i].release);
		init_completion(&workers[i].done);
	}
	for (i = 0; i < 2; i++) {
		ret = start(i, false);
		if (ret || !entered(i))
			goto join;
	}
	check(atomic_read(&reading) == 2);
	r.readers_slept = parked(workers[0].task) + parked(workers[1].task);
	ret = start(2, true);
	if (ret)
		goto join;
	r.writer_slept = parked(workers[2].task);
	check(waitqueue_active(&sem.drain));
	check(!completion_done(&workers[2].entered));
	ret = start(3, false);
	if (ret)
		goto join;
	r.late_reader_slept = parked(workers[3].task);
	check(!completion_done(&workers[3].entered));
	complete(&workers[0].release);
	check(wait_for_completion_timeout(&workers[0].done, 5 * HZ));
	check(!completion_done(&workers[2].entered));
	complete(&workers[1].release);
	check(entered(2));
	check(parked(workers[2].task)); /* real writer body can sleep too */
	check(!completion_done(&workers[3].entered));
	complete(&workers[2].release);
	check(entered(3));
join:
	/* On failure retain the module until every worker really exits. A hung
	 * acquisition intentionally leaves the ioctl blocked for diagnosis. */
	for (i = 0; i < 4; i++)
		complete_all(&workers[i].release);
	for (i = 0; i < 4; i++) {
		if (!workers[i].task)
			continue;
		/* done may already have been consumed by the staged assertion. */
		check(!kthread_stop(workers[i].task));
		check(workers[i].switches > 0);
		put_task_struct(workers[i].task);
		workers[i].task = NULL;
	}
	check(r.readers_slept == 2 && r.writer_slept && r.late_reader_slept);
result:
	r.idle = kd_rwsem_is_idle(&sem) && !atomic_read(&reading) && !atomic_read(&writing);
	check(r.idle);
	r.errors = atomic_read(&errors);
	if (!ret && copy_to_user(user, &r, sizeof(r)))
		ret = -EFAULT;
unlock:
	mutex_unlock(&control);
	return ret;
}

static long probe_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	return cmd == RUN ? run((void __user *)arg) : -ENOTTY;
}
static const struct file_operations ops = {
	.owner = THIS_MODULE, .unlocked_ioctl = probe_ioctl, .llseek = no_llseek,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_rwsem_probe", .fops = &ops, .mode = 0600,
};
static int __init probe_init(void) { return misc_register(&device); }
static void __exit probe_exit(void) { misc_deregister(&device); }
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KD rwsem ordinary sleeping API and admission probe");
