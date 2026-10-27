// SPDX-License-Identifier: GPL-2.0
/* Real mm objects and Linux 7 mmap APIs; private adapter try-write is tested
 * explicitly by backend_trylock.h, not presented as a public Linux API. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/irq_work.h>
#include <linux/kallsyms.h>
#include <linux/kprobes.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/uaccess.h>
#include "api.h"
#include "backend_trylock.h"

#ifndef CONFIG_KDLOCK_MMAP
#error "This probe requires the actual mmap-lock integration kernel"
#endif

static DEFINE_MUTEX(control);
static struct mm_struct *probe_mm;
static struct mm_struct *(*allocate_probe_mm)(void);
static atomic_t errors = ATOMIC_INIT(0), checks = ATOMIC_INIT(0);
static atomic_t reading = ATOMIC_INIT(0), writing = ATOMIC_INIT(0);
static bool expected_kd;
module_param(expected_kd, bool, 0444);

static void check_at(bool good, unsigned int line)
{
	atomic_inc(&checks);
	if (!good) {
		atomic_inc(&errors);
		pr_err("kd_mmap_probe: check failed at line %u\n", line);
	}
}
#define check(c) check_at(!!(c), __LINE__)

static bool idle(struct mm_struct *mm)
{
	if (mmap_lock_is_contended(mm) || kd_mmap_is_locked(&mm->mmap_lock))
		return false;
	if (mm->mmap_lock.use_kd) {
		struct kd_mmap_rwsem *s = &mm->mmap_lock.kd;
		return !atomic_long_read(&s->readers) && !atomic_long_read(&s->admission) &&
			!atomic_long_read(&s->gate.owner) && !atomic_read(&s->gate.osq.tail) &&
			!READ_ONCE(s->gate.wait_head) && !atomic_read(&s->gate.delegation_state) &&
			!READ_ONCE(s->gate.delegation_tail);
	}
	return true;
}

struct worker {
	struct task_struct *task;
	struct completion entered, release, done;
	bool writer, killable;
	int result;
	u64 switches;
};
static struct worker workers[4];

static bool parked(struct task_struct *task)
{
	unsigned long end = jiffies + 5 * HZ;

	do {
		if ((READ_ONCE(task->__state) & TASK_UNINTERRUPTIBLE) && !READ_ONCE(task->on_cpu))
			return true;
		msleep(1);
	} while (time_before(jiffies, end));
	return false;
}

static int worker_main(void *data)
{
	struct worker *w = data;
	struct mm_struct *mm = probe_mm;
	u64 before = current->nvcsw;

	check(!current->mm); /* This participant uses another task's real mm object. */
	check(raw_smp_processor_id() == 0);
	if (w->killable) {
		allow_signal(SIGUSR1);
		allow_signal(SIGKILL);
		w->result = w->writer ? mmap_write_lock_killable(mm) : mmap_read_lock_killable(mm);
		if (w->result)
			goto done;
	} else if (w->writer) {
		mmap_write_lock(mm);
	} else {
		mmap_read_lock(mm);
	}
	if (w->writer) {
		check(kd_mmap_is_write_owner(&mm->mmap_lock));
		check(!atomic_read(&reading));
		check(atomic_inc_return(&writing) == 1);
	} else {
		atomic_inc(&reading);
		check(!atomic_read(&writing));
	}
	complete(&w->entered);
	wait_for_completion(&w->release);
	if (w->writer) {
		check(!atomic_read(&reading));
		atomic_dec(&writing);
		mmap_write_unlock(mm);
	} else {
		unsigned long flags;
		int count = preempt_count();

		check(!atomic_read(&writing));
		atomic_dec(&reading);
		/* Exercise the actual adapter's atomic final-reader release while
		 * a writer drains. Native retains its ordinary release context. */
		if (expected_kd) {
			local_irq_save(flags);
			mmap_read_unlock(mm);
			check(irqs_disabled() && preempt_count() == count);
			local_irq_restore(flags);
		} else {
			mmap_read_unlock(mm);
		}
	}
done:
	w->switches = current->nvcsw - before;
	mmdrop(mm);
	complete(&w->done);
	return 0;
}

static int start(unsigned int n, bool writer, bool killable)
{
	struct worker *w = &workers[n];

	check(!w->task);
	init_completion(&w->entered);
	init_completion(&w->release);
	init_completion(&w->done);
	w->writer = writer;
	w->killable = killable;
	w->result = 0;
	w->switches = 0;
	mmgrab(probe_mm);
	w->task = kthread_create(worker_main, w, "kd_mm_probe");
	if (IS_ERR(w->task)) {
		int ret = PTR_ERR(w->task);
		w->task = NULL;
		mmdrop(probe_mm);
		return ret;
	}
	get_task_struct(w->task);
	kthread_bind(w->task, 0);
	wake_up_process(w->task);
	return 0;
}

static bool entered(unsigned int n)
{
	bool ready = wait_for_completion_timeout(&workers[n].entered, 5 * HZ);
	check(ready);
	return ready;
}

static void join_all(void)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(workers); i++)
		if (workers[i].task)
			complete_all(&workers[i].release);
	/* A timeout is not drain. Keep the ioctl and its module reference until
	 * every real worker exits; never erase a stranded ownership record. */
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		if (!workers[i].task)
			continue;
		check(!kthread_stop(workers[i].task));
		put_task_struct(workers[i].task);
		workers[i].task = NULL;
	}
	check(atomic_read(&probe_mm->mm_count) == 1);
	check(idle(probe_mm));
}

static void queue_check(bool drain)
{
	check(mmap_lock_is_contended(probe_mm));
	if (probe_mm->mmap_lock.use_kd) {
		struct kd_mmap_rwsem *s = &probe_mm->mmap_lock.kd;
		check(waitqueue_active(drain ? &s->reader_drain : &s->phase_wait));
		check(!waitqueue_active(drain ? &s->phase_wait : &s->reader_drain));
		check(!atomic_read(&s->gate.delegation_state) && !READ_ONCE(s->gate.delegation_tail));
	}
}

static int cancellation(bool writer, bool drain)
{
	int ret;
	bool done;

	if (drain)
		mmap_read_lock(probe_mm);
	else
		mmap_write_lock(probe_mm);
	ret = start(0, writer, true);
	if (ret)
		goto release;
	check(parked(workers[0].task));
	queue_check(drain);
	check(!send_sig(SIGUSR1, workers[0].task, 1));
	msleep(20);
	check(!completion_done(&workers[0].done) && !completion_done(&workers[0].entered));
	check(!send_sig(SIGKILL, workers[0].task, 1));
	done = wait_for_completion_timeout(&workers[0].done, 5 * HZ);
	check(done);
	check(workers[0].result == -EINTR);
	if (drain) {
		bool acquired = mmap_read_trylock(probe_mm);
		check(acquired);
		if (acquired)
			mmap_read_unlock(probe_mm);
	}
release:
	if (drain)
		mmap_read_unlock(probe_mm);
	else
		mmap_write_unlock(probe_mm);
	join_all();
	return ret;
}

static int sleeping(struct kd_mmap_probe_result *r)
{
	int ret;
	unsigned int i;

	for (i = 0; i < 2; i++) {
		ret = start(i, false, false);
		if (ret || !entered(i))
			goto join;
	}
	check(atomic_read(&reading) == 2);
	r->readers_slept = parked(workers[0].task) + parked(workers[1].task);
	ret = start(2, true, false);
	if (ret)
		goto join;
	r->writer_slept = parked(workers[2].task);
	queue_check(true);
	check(!completion_done(&workers[2].entered));
	ret = start(3, false, false);
	if (ret)
		goto join;
	r->late_reader_slept = parked(workers[3].task);
	check(!completion_done(&workers[3].entered));
	complete(&workers[0].release);
	check(wait_for_completion_timeout(&workers[0].done, 5 * HZ));
	check(!completion_done(&workers[2].entered));
	complete(&workers[1].release);
	if (!entered(2))
		goto join;
	check(parked(workers[2].task));
	check(!completion_done(&workers[3].entered));
	complete(&workers[2].release);
	check(entered(3));
	check(r->readers_slept == 2 && r->writer_slept == 1 && r->late_reader_slept == 1);
join:
	join_all();
	return ret;
}

static int downgrade(void)
{
	int ret;

	mmap_write_lock(probe_mm);
	ret = start(0, true, false);
	if (ret) {
		mmap_write_unlock(probe_mm);
		return ret;
	}
	check(parked(workers[0].task));
	queue_check(false);
	atomic_inc(&reading);
	mmap_write_downgrade(probe_mm);
	msleep(20);
	check(parked(workers[0].task));
	queue_check(true);
	check(!completion_done(&workers[0].entered));
	atomic_dec(&reading);
	mmap_read_unlock(probe_mm);
	check(entered(0));
	join_all();
	return 0;
}

struct transfer {
	struct irq_work work;
	struct mmap_read_token token;
};

static void transfer_complete(struct irq_work *work)
{
	struct transfer *t = container_of(work, struct transfer, work);
	mmap_read_unlock_complete(&t->token);
}

/* A unique mm identity, consumed before destruction, is the observation key.
 * This diagnostic never authorizes an acquisition or a reference release. */
static struct mm_struct *destroy_watch;
static bool destroy_seen, destroy_on_worker, destroy_empty;
static DECLARE_COMPLETION(destroy_done);
static int destroy_entry(struct kretprobe_instance *ri, struct pt_regs *regs)
{
	struct mm_struct *mm = (void *)regs->di;

	if (!mm || cmpxchg(&destroy_watch, mm, NULL) != mm)
		return 1;
	destroy_seen = true;
	destroy_on_worker = !!(current->flags & PF_WQ_WORKER) && !in_interrupt();
	destroy_empty = atomic_read(&mm->mm_count) == 0 && idle(mm);
	return 0;
}

static int destroy_return(struct kretprobe_instance *ri, struct pt_regs *regs)
{
	/* The exact watched __mmdrop has returned, including its final free. */
	complete(&destroy_done);
	return 0;
}

static int transfer_cases(struct kd_mmap_probe_result *r)
{
	struct transfer t = { .token = { NULL } };
	struct kretprobe kp = { .kp.symbol_name = "__mmdrop", .entry_handler = destroy_entry,
		.handler = destroy_return, .maxactive = 64 };
	struct mm_struct *mm;
	unsigned long flags;
	int ret, context;
	bool acquired;

	init_irq_work(&t.work, transfer_complete);
	/* Match the originating IRQ/preemption state on success and failure.
	 * Native release remains outside atomic context or uses its exact token. */
	for (context = 0; context < 3; context++) {
		int count;
		bool irq;

		flags = 0;
		if (context == 1)
			local_irq_save(flags);
		else if (context == 2)
			preempt_disable();
		count = preempt_count();
		irq = irqs_disabled();
		acquired = mmap_read_trylock(probe_mm);
		check(acquired && irqs_disabled() == irq && preempt_count() == count);
		if (acquired && expected_kd) {
			mmap_read_unlock(probe_mm);
			check(irqs_disabled() == irq && preempt_count() == count);
		}
		if (context == 1)
			local_irq_restore(flags);
		else if (context == 2)
			preempt_enable();
		if (acquired && !expected_kd)
			mmap_read_unlock(probe_mm);
		check(idle(probe_mm));
		mmap_write_lock(probe_mm);
		if (context == 1)
			local_irq_save(flags);
		else if (context == 2)
			preempt_disable();
		count = preempt_count();
		irq = irqs_disabled();
		check(!mmap_read_trylock(probe_mm));
		check(irqs_disabled() == irq && preempt_count() == count);
		if (context == 1)
			local_irq_restore(flags);
		else if (context == 2)
			preempt_enable();
		check(kd_mmap_is_write_owner(&probe_mm->mmap_lock));
		mmap_write_unlock(probe_mm);
		check(idle(probe_mm) && !irqs_disabled() && !preempt_count());
	}
	r->irq_checks++;

	mmap_read_lock(probe_mm);
	mmap_read_unlock_prepare(&t.token, probe_mm);
	check(t.token.mm == probe_mm && atomic_read(&probe_mm->mm_count) == 2);
	irq_work_queue(&t.work);
	irq_work_sync(&t.work);
	check(!t.token.mm && atomic_read(&probe_mm->mm_count) == 1 && idle(probe_mm));
	r->transfer_checks++;

	ret = register_kretprobe(&kp);
	if (ret)
		return ret;
	mm = allocate_probe_mm();
	if (!mm) {
		unregister_kretprobe(&kp);
		return -ENOMEM;
	}
	/* Finish mm_users teardown while retaining the allocation. Then transfer
	 * the last allocation reference; completion must defer __mmdrop from IRQ. */
	mmgrab(mm);
	mmput(mm);
	check(atomic_read(&mm->mm_users) == 0 && atomic_read(&mm->mm_count) == 1);
	mmap_read_lock(mm);
	mmap_read_unlock_prepare(&t.token, mm);
	check(t.token.mm == mm && atomic_read(&mm->mm_count) == 2);
	destroy_seen = destroy_on_worker = destroy_empty = false;
	reinit_completion(&destroy_done);
	WRITE_ONCE(destroy_watch, mm);
	mmdrop(mm);
	irq_work_queue(&t.work);
	irq_work_sync(&t.work);
	if (!wait_for_completion_timeout(&destroy_done, 5 * HZ)) {
		check(false);
		/* Keep this ioctl/module alive until the exact destruction returns. */
		wait_for_completion(&destroy_done);
	}
	check(!t.token.mm && destroy_seen && destroy_on_worker && destroy_empty && !destroy_watch);
	check(!kp.nmissed);
	unregister_kretprobe(&kp);
	r->destroy_checks++;
	return 0;
}

static long run(void __user *user)
{
	struct kd_mmap_probe_result r = { .abi = 1 };
	struct mm_struct *nested = NULL;
	int ret = 0;
	unsigned int i;
	bool ok;

	if (!mutex_trylock(&control))
		return -EBUSY;
	if (probe_mm || !cpu_online(0)) {
		ret = -EBUSY;
		goto unlock;
	}
	probe_mm = allocate_probe_mm();
	if (!probe_mm) {
		ret = -ENOMEM;
		goto unlock;
	}
	atomic_set(&errors, 0);
	atomic_set(&checks, 0);
	r.mm = (unsigned long)probe_mm;
	r.lock = (unsigned long)&probe_mm->mmap_lock;
	r.use_kd = probe_mm->mmap_lock.use_kd;
	check(r.use_kd == expected_kd && idle(probe_mm));
	check(current->mm && current->mm->mmap_lock.use_kd == expected_kd);
	check(!atomic_read(&reading) && !atomic_read(&writing));
	for (i = 0; i < 2; i++) {
		ok = mmap_read_trylock(probe_mm);
		check(ok);
		if (!ok) {
			while (i--)
				mmap_read_unlock(probe_mm);
			goto result;
		}
	}
	check(!probe_backend_write_trylock(probe_mm));
	mmap_read_unlock(probe_mm);
	mmap_read_unlock(probe_mm);
	ok = probe_backend_write_trylock(probe_mm);
	check(ok);
	if (!ok)
		goto result;
	check(kd_mmap_is_write_owner(&probe_mm->mmap_lock));
	check(!mmap_read_trylock(probe_mm) && !probe_backend_write_trylock(probe_mm));
	mmap_write_downgrade(probe_mm);
	check(!probe_backend_write_trylock(probe_mm));
	mmap_read_unlock(probe_mm);
	check(idle(probe_mm));
	r.api_checks = 8;
	nested = allocate_probe_mm();
	if (!nested) {
		ret = -ENOMEM;
		goto result;
	}
	mmap_write_lock(probe_mm);
	mmap_write_lock_nested(nested, SINGLE_DEPTH_NESTING);
	check(kd_mmap_is_write_owner(&probe_mm->mmap_lock) && kd_mmap_is_write_owner(&nested->mmap_lock));
	mmap_write_unlock(nested);
	mmap_write_unlock(probe_mm);
	check(idle(nested) && idle(probe_mm));
	mmput(nested);
	r.nested_checks++;
	for (i = 0; i < 3 && !atomic_read(&errors); i++) {
		ret = cancellation(i != 0, i == 2);
		if (ret)
			goto result;
		r.cancellation_checks++;
	}
	if (atomic_read(&errors))
		goto result;
	ret = sleeping(&r);
	if (ret || atomic_read(&errors))
		goto result;
	ret = downgrade();
	if (ret || atomic_read(&errors))
		goto result;
	r.downgrade_checks++;
	ret = transfer_cases(&r);
result:
	r.idle = idle(probe_mm) && atomic_read(&probe_mm->mm_count) == 1 &&
		!atomic_read(&reading) && !atomic_read(&writing);
	check(r.idle);
	r.errors = atomic_read(&errors);
	r.checks = atomic_read(&checks);
	if (r.idle) {
		mmput(probe_mm);
		probe_mm = NULL;
	} else {
		/* Retain failed state and prevent unload; it is never reinitialized. */
		__module_get(THIS_MODULE);
	}
	if (!ret && copy_to_user(user, &r, sizeof(r)))
		ret = -EFAULT;
unlock:
	(mutex_unlock)(&control);
	return ret;
}

static long probe_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	return cmd == KD_MMAP_PROBE_RUN ? run((void __user *)arg) : -ENOTTY;
}
static const struct file_operations ops = {
	.owner = THIS_MODULE, .unlocked_ioctl = probe_ioctl,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mmap_probe", .fops = &ops, .mode = 0600,
};
static int __init probe_init(void)
{
	/* The captured guest exports symbol lookup, but mm_alloc itself is an
	 * internal kernel API. Resolve once before publishing this test device. */
	allocate_probe_mm = (void *)kallsyms_lookup_name("mm_alloc");
	if (!allocate_probe_mm)
		return -ENOENT;
	return misc_register(&device);
}
static void __exit probe_exit(void) { misc_deregister(&device); }
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Actual mmap-lock local API, mode, cancellation and reference-transfer probe");
