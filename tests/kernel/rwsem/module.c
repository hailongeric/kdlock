// SPDX-License-Identifier: GPL-2.0
/* Sleeping admission and outer-writer ordering. JIT acceptance is separate. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/sched/task.h>
#include <linux/sched/signal.h>
#include <linux/uaccess.h>
#include "kd_lock.h"
#include "kd_rwsem_api.h"

static DEFINE_KD_RWSEM(sem);
extern char rwsem_probe_entry[];
int kd_rwsem_compat_checks(void);
static DEFINE_KD_MUTEX(control);
static atomic_t reading = ATOMIC_INIT(0), writing = ATOMIC_INIT(0), errors = ATOMIC_INIT(0);
struct worker {
	struct task_struct *task;
	struct completion entered, release, done;
	enum { READER, WRITER, OUTER_WRITER } kind;
	u64 switches;
};
static struct worker workers[4];
struct result {
	u64 errors, api_checks, readers_slept, writer_slept, late_reader_slept;
	u64 cancellation_checks, colocated, idle;
	u64 outer_readers_slept, outer_writer_slept, downgrade_checks, publication_checks;
};
#define RUN _IOR('S', 1, struct result)

static void check_at(bool condition, unsigned int line)
{
	if (!condition) {
		atomic_inc(&errors);
		pr_info("rwsem probe check failed at line %u\n", line);
	}
}
#define check(condition) check_at(!!(condition), __LINE__)

/* No image is registered for this body. Its blocking assertions intentionally
 * test the outer wrapper's local return path; workload completion witnesses
 * separately prove that translated writers returned through the same pair.
 */
static __attribute__((noipa)) void outer_body(struct worker *w)
{

	kd_down_write(&sem);
	asm volatile(".globl rwsem_probe_entry\n.set rwsem_probe_entry, 1b\n\t"
	             ".pushsection .discard.noendbr\n\t"
	             _ASM_PTR " rwsem_probe_entry\n\t.popsection\n\t" : : : "memory");
	check(!atomic_read(&reading));
	check(atomic_inc_return(&writing) == 1);
	complete(&w->entered);
	wait_for_completion(&w->release);
	atomic_dec(&writing);
	kd_up_write(&sem);
}

static int worker_main(void *data)
{
	struct worker *w = data;
	unsigned long before = current->nvcsw;
	if (w->kind == OUTER_WRITER) {
		outer_body(w);
		goto done;
	}
	if (w->kind == WRITER) {
		(kd_down_write)(&sem);
		check(!atomic_read(&reading));
		check(atomic_inc_return(&writing) == 1);
	} else {
		kd_down_read(&sem);
		atomic_inc(&reading);
		check(!atomic_read(&writing));
	}
	complete(&w->entered);
	wait_for_completion(&w->release);
	if (w->kind == WRITER) {
		atomic_dec(&writing);
		kd_up_write(&sem);
	} else {
		check(!atomic_read(&writing));
		atomic_dec(&reading);
		kd_up_read(&sem);
	}
done:
	w->switches = current->nvcsw - before;
	complete(&w->done);
	return 0;
}

/* All four workers share one CPU. Sleeping holders must resume while later
 * contenders wait; pinned delegation polling would invalidate this scenario. */
static int start(unsigned int i, unsigned int kind)
{
	struct worker *w = &workers[i];
	w->kind = kind;
	w->task = kthread_create(worker_main, w, "kd_rwsem_probe");
	if (IS_ERR(w->task)) {
		int ret = PTR_ERR(w->task);
		w->task = NULL;
		return ret;
	}
	get_task_struct(w->task);
	kthread_bind(w->task, 0);
	wake_up_process(w->task);
	return 0;
}

static bool entered(unsigned int i)
{
	bool done = wait_for_completion_timeout(&workers[i].entered, 5 * HZ) != 0;

	check(done);
	return done;
}

static bool parked(struct task_struct *task)
{
	unsigned long deadline = jiffies + 5 * HZ;
	do {
		/* prepare_to_wait sets state before the final condition check. Require
		 * an actual switch-out, not that transient state on a running task.
		 */
		if ((READ_ONCE(task->__state) & TASK_UNINTERRUPTIBLE)
#ifdef CONFIG_SMP
		    && !READ_ONCE(task->on_cpu)
#endif
		   )
			return true;
		msleep(1);
	} while (time_before(jiffies, deadline));
	return false;
}

struct cancellation {
	struct completion ready, done;
	bool writer;
	int signal, result;
};

static int cancel_worker(void *data)
{
	struct cancellation *c = data;

	allow_signal(SIGUSR1);
	allow_signal(SIGKILL);
	complete(&c->ready);
	if (c->writer)
		c->result = c->signal == SIGKILL ?
			kd_down_write_killable(&sem) : kd_down_write_interruptible(&sem);
	else
		c->result = c->signal == SIGKILL ?
			kd_down_read_killable(&sem) : kd_down_read_interruptible(&sem);
	if (!c->result) {
		if (c->writer)
			kd_up_write(&sem);
		else
			kd_up_read(&sem);
	}
	complete(&c->done);
	return 0;
}

/* Cover cancellation during phase admission and reader drainage after an
 * ordinary writer owns its phase and gate. Retain all holders until
 * cancellation is observed, so successful acquisition cannot masquerade as it.
 */
static int cancel_case(bool writer, bool drain, int signal, bool outer)
{
	struct cancellation c = { .writer = writer, .signal = signal, .result = 1 };
	struct task_struct *task;
	unsigned long deadline;
	bool queued = false;
	bool gate_wait = writer && !drain && !READ_ONCE(sem.prepared_writes);

	init_completion(&c.ready);
	init_completion(&c.done);
	if (drain)
		kd_down_read(&sem);
	else if (outer)
		kd_down_write(&sem);
	else
		(kd_down_write)(&sem);
	task = kthread_create(cancel_worker, &c, "kd_rwsem_cancel");
	if (IS_ERR(task)) {
		if (drain)
			kd_up_read(&sem);
		else if (outer)
			kd_up_write(&sem);
		else
			kd_up_write(&sem);
		return PTR_ERR(task);
	}
	get_task_struct(task);
	kthread_bind(task, 0);
	wake_up_process(task);
	check(wait_for_completion_timeout(&c.ready, 5 * HZ));
	deadline = jiffies + 5 * HZ;
	do {
		queued = gate_wait ? !!READ_ONCE(sem.gate.wait_head) :
			kd_rwsem_condition_active(drain ? &sem.reader_drain : &sem.phase_wait);
		if (queued)
			break;
		msleep(1);
	} while (time_before(jiffies, deadline));
	check(queued);
	check(!kd_rwsem_condition_active(drain ? &sem.phase_wait : &sem.reader_drain));
	if (gate_wait)
		check(!kd_rwsem_condition_active(&sem.phase_wait));
	if (signal == SIGKILL) {
		check(!send_sig(SIGUSR1, task, 1));
		msleep(20);
		check(!completion_done(&c.done));
	}
	check(!send_sig(signal, task, 1));
	check(wait_for_completion_timeout(&c.done, 5 * HZ));
	check(c.result == -EINTR);
	if (drain) {
		/* A cancelled writer must have released its phase and gate even though
		 * this reader remains live. Another reader can immediately enter.
		 */
		if (kd_down_read_trylock(&sem))
			kd_up_read(&sem);
		else
			check(false);
		kd_up_read(&sem);
	} else if (outer) {
		kd_up_write(&sem);
	} else {
		kd_up_write(&sem);
	}
	check(!kthread_stop(task));
	put_task_struct(task);
	check(kd_rwsem_is_idle(&sem));
	return 0;
}

static void init_workers(void)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		workers[i].task = NULL;
		workers[i].switches = 0;
		init_completion(&workers[i].entered);
		init_completion(&workers[i].release);
		init_completion(&workers[i].done);
	}
}

static void join_workers(void)
{
	unsigned int i;

	/* A timeout is not drain. Keep the ioctl/module live until every worker
	 * really exits, preserving failed ownership and publication for diagnosis.
	 */
	for (i = 0; i < ARRAY_SIZE(workers); i++)
		complete_all(&workers[i].release);
	for (i = 0; i < ARRAY_SIZE(workers); i++) {
		if (!workers[i].task)
			continue;
		check(!kthread_stop(workers[i].task));
		check(workers[i].switches > 0);
		put_task_struct(workers[i].task);
		workers[i].task = NULL;
	}
	check(kd_rwsem_is_idle(&sem));
}

static void unpublished(struct result *r)
{
	/* This controlled probe has no registered JIT body or other delegation
	 * callers. Empty embedded state proves that this gate has not reserved
	 * delegation; phase/drain waiters cannot publish a delegation tail.
	 * Keep the independent exact waiter count through its safe accessor.
	 */
	check(!atomic_read(&sem.gate.delegation_state));
	check(!READ_ONCE(sem.gate.delegation_tail));
	check(!kd_mutex_debug_waiter_count(&sem.gate));
	r->publication_checks++;
}

static bool phase_is(long expected)
{
	unsigned long deadline = jiffies + 5 * HZ;

	do {
		if (atomic_long_read(&sem.admission) == expected)
			return true;
		msleep(1);
	} while (time_before(jiffies, deadline));
	return false;
}

static int sleeping_case(struct result *r, bool outer)
{
	unsigned int i;
	u64 readers_slept, writer_slept, late_reader_slept;
	int ret = 0;

	init_workers();
	for (i = 0; i < 2; i++) {
		ret = start(i, READER);
		if (ret || !entered(i))
			goto join;
	}
	check(atomic_read(&reading) == 2);
	readers_slept = parked(workers[0].task) + parked(workers[1].task);
	ret = start(2, outer ? OUTER_WRITER : WRITER);
	if (ret)
		goto join;
	writer_slept = parked(workers[2].task);
	check(kd_rwsem_condition_active(&sem.reader_drain));
	check(!kd_rwsem_condition_active(&sem.phase_wait));
	check(!completion_done(&workers[2].entered));
	if (outer) {
		check(atomic_long_read(&sem.admission) == 1);
		unpublished(r);
	}
	ret = start(3, READER);
	if (ret)
		goto join;
	late_reader_slept = parked(workers[3].task);
	check(kd_rwsem_condition_active(&sem.phase_wait));
	check(!completion_done(&workers[3].entered));
	complete(&workers[0].release);
	check(wait_for_completion_timeout(&workers[0].done, 5 * HZ));
	check(!completion_done(&workers[2].entered));
	complete(&workers[1].release);
	check(entered(2));
	check(parked(workers[2].task));
	check(!kd_rwsem_condition_active(&sem.reader_drain));
	check(kd_rwsem_condition_active(&sem.phase_wait));
	check(!completion_done(&workers[3].entered));
	complete(&workers[2].release);
	check(entered(3));
	check(readers_slept == 2 && writer_slept && late_reader_slept);
	if (outer) {
		r->outer_readers_slept = readers_slept;
		r->outer_writer_slept = writer_slept;
	} else {
		r->readers_slept = readers_slept;
		r->writer_slept = writer_slept;
		r->late_reader_slept = late_reader_slept;
	}
join:
	join_workers();
	return ret;
}

static int downgrade_case(struct result *r)
{
	int ret;

	init_workers();
	(kd_down_write)(&sem);
	ret = start(0, OUTER_WRITER);
	if (ret) {
		kd_up_write(&sem);
		return ret;
	}
	check(parked(workers[0].task));
	check(atomic_long_read(&sem.admission) == -1);
	check(kd_rwsem_condition_active(&sem.phase_wait));
	check(!kd_rwsem_condition_active(&sem.reader_drain));
	check(!completion_done(&workers[0].entered));
	unpublished(r);
	/* Conversion creates an admitted reader before reopening the phase. The
	 * waiting outer caller can reserve, but must still sleep before pinning.
	 */
	atomic_inc(&reading);
	kd_downgrade_write(&sem);
	check(phase_is(1));
	check(parked(workers[0].task));
	check(!kd_rwsem_condition_active(&sem.phase_wait));
	check(kd_rwsem_condition_active(&sem.reader_drain));
	check(atomic_long_read(&sem.admission) == 1);
	check(!completion_done(&workers[0].entered));
	unpublished(r);
	atomic_dec(&reading);
	kd_up_read(&sem);
	check(entered(0));
	join_workers();
	r->downgrade_checks++;
	return 0;
}

static DECLARE_COMPLETION(non_owner_done);

static int non_owner_release(void *unused)
{
	(void)unused;
	kd_up_read_non_owner(&sem);
	complete(&non_owner_done);
	return 0;
}

static int public_api_checks(void)
{
	struct task_struct *task;
	struct lock_class_key key;
	int annotations = 0, ret;
	void (*local_write)(struct kd_rwsem *) = kd_down_write;
	void (*routed_unlock)(struct kd_rwsem *) = kd_up_write;

	__kd_init_rwsem(&sem, "rwsem_probe", &key);
	check(!kd_rwsem_is_locked(&sem) && !kd_rwsem_is_contended(&sem));
	kd_down_write_nested(&sem, annotations++);
	check(!annotations && atomic_long_read(&sem.admission) == -1);
	kd_rwsem_assert_held(&sem);
	kd_rwsem_assert_held_write(&sem);
	check(kd_rwsem_prepare(&sem, (unsigned long)rwsem_probe_entry,
		KD_ENTRY_ABI_MUTEX_CLOBBER_V1) == -EBUSY);
	check(!READ_ONCE(sem.prepared_writes));
	kd_downgrade_write(&sem);
	kd_up_read(&sem);
	kd_down_read_non_owner(&sem);
	reinit_completion(&non_owner_done);
	task = kthread_create(non_owner_release, NULL, "kd_rwsem_nonown");
	if (IS_ERR(task)) {
		kd_up_read_non_owner(&sem);
		return PTR_ERR(task);
	}
	/* Retain the task through its explicit non-owner release and join. */
	get_task_struct(task);
	wake_up_process(task);
	check(wait_for_completion_timeout(&non_owner_done, 5 * HZ));
	check(!kthread_stop(task));
	put_task_struct(task);
	check(kd_rwsem_is_idle(&sem));
	{ guard(kd_rwsem_read)(&sem); check(kd_rwsem_is_locked(&sem)); }
	{ guard(kd_rwsem_write)(&sem); check(atomic_long_read(&sem.admission) == -1); }
	check(kd_rwsem_is_idle(&sem));
	ret = kd_rwsem_prepare(&sem, (unsigned long)rwsem_probe_entry,
		KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	if (ret)
		return ret;
	check(READ_ONCE(sem.prepared_writes) == 1);
	local_write(&sem);
	check(atomic_long_read(&sem.admission) == -1);
	kd_downgrade_write(&sem);
	kd_up_read(&sem);
	{ guard(kd_rwsem_write)(&sem); check(atomic_long_read(&sem.admission) == -1); }
	kd_down_write(&sem);
	check(atomic_long_read(&sem.admission) == 1);
	routed_unlock(&sem);
	check(kd_rwsem_is_idle(&sem) && READ_ONCE(sem.prepared_writes) == 1);
	check(!kd_rwsem_compat_checks());
	return 0;
}

static long run(void __user *user)
{
	struct result r = { 0 };
	unsigned int i;
	int ret = 0;
	if (!kd_mutex_trylock(&control))
		return -EBUSY;
	if (!cpu_online(0)) {
		ret = -EINVAL;
		goto unlock;
	}
	atomic_set(&errors, 0);
	if (!kd_rwsem_is_idle(&sem)) {
		/* Preserve a failed acquisition/queue for diagnosis. Reinitializing
		 * it would erase its ownership and waiter evidence on the next ioctl.
		 */
		check(false);
		goto result;
	}
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
	for (i = 0; i < 6; i++) {
		ret = cancel_case(i / 2 != 0, i / 2 == 2,
				  i % 2 ? SIGKILL : SIGUSR1, false);
		if (ret || atomic_read(&errors))
			goto result;
		r.cancellation_checks++;
	}
	ret = public_api_checks();
	if (ret || atomic_read(&errors))
		goto result;
	r.api_checks += 9;
	for (i = 0; i < 4; i++) {
		ret = cancel_case(i / 2, false, i % 2 ? SIGKILL : SIGUSR1, true);
		if (ret || atomic_read(&errors))
			goto result;
		r.cancellation_checks++;
	}
	ret = sleeping_case(&r, false);
	if (ret || atomic_read(&errors))
		goto result;
	ret = sleeping_case(&r, true);
	if (ret || atomic_read(&errors))
		goto result;
	ret = downgrade_case(&r);
	if (ret || atomic_read(&errors))
		goto result;
	r.colocated = 1;
result:
	r.idle = kd_rwsem_is_idle(&sem) && !atomic_read(&reading) && !atomic_read(&writing);
	check(r.idle);
	r.errors = atomic_read(&errors);
	if (!ret && copy_to_user(user, &r, sizeof(r)))
		ret = -EFAULT;
unlock:
	kd_mutex_local_unlock(&control);
	return ret;
}

#include "payload/gate_signal.inc"

static long probe_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	if (cmd == RUN_GATE_SIGNAL)
		return run_gate_signal((void __user *)arg);
	return cmd == RUN ? run((void __user *)arg) : -ENOTTY;
}
static const struct file_operations ops = {
	.owner = THIS_MODULE, .unlocked_ioctl = probe_ioctl,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_rwsem_probe", .fops = &ops, .mode = 0600,
};
static int __init probe_init(void) { return misc_register(&device); }
static void __exit probe_exit(void) { misc_deregister(&device); }
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KD rwsem sleeping API, outer admission and downgrade probe");
