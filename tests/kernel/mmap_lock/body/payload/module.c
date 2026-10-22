// SPDX-License-Identifier: GPL-2.0
/* Correctness-only callers of the actual in-tree do_madvise body. */
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/kallsyms.h>
#include <linux/kd_mmap_lock.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mman.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include "api.h"

static int (*advice)(struct mm_struct *, unsigned long, size_t, int);
static atomic_t busy = ATOMIC_INIT(0);
struct test;
struct worker {
	struct test *test;
	struct task_struct *task;
	struct completion done, entered;
	unsigned int index, phase, iterations;
	bool reader, cancel;
	int returned;
	u64 completed, errors;
};
struct test {
	struct mm_struct *mm;
	struct completion go, release_readers;
	atomic_t readers, peak;
	struct worker workers[MB_WORKERS], readers_work[2];
	struct mb_result result;
};

static void check(struct test *t, bool good)
{
	t->result.checks++;
	if (!good)
		t->result.errors++;
}

static int work(void *argument)
{
	struct worker *w = argument;
	struct test *t = w->test;
	unsigned int i;

	kthread_use_mm(t->mm);
	if (w->cancel) {
		allow_signal(SIGUSR1);
		allow_signal(SIGKILL);
		w->returned = advice(t->mm, t->result.address[w->index], 3 * PAGE_SIZE, MADV_DONTDUMP);
		w->completed++;
		goto done;
	}
	if (w->reader) {
		int active;

		mmap_read_lock(t->mm);
		active = atomic_inc_return(&t->readers);
		if (active == 2)
			atomic_set(&t->peak, 2);
		complete(&w->entered);
		wait_for_completion(&t->release_readers);
		atomic_dec(&t->readers);
		mmap_read_unlock(t->mm);
	} else {
		wait_for_completion(&t->go);
		for (i = 0; i < w->iterations; i++) {
			unsigned long start = t->result.address[w->index];
			size_t len = (w->phase == 1 ? 1 : 3) * PAGE_SIZE;
			int behavior = (i & 1) ? MADV_DODUMP : MADV_DONTDUMP;
			struct vm_area_struct *vma;

			if (advice(t->mm, start, len, behavior))
				w->errors++;
			w->completed++;
			/* Readback uses the real concurrent reader API on this origin.
			 * Each worker owns a disjoint range, so later writers cannot
			 * erase this operation's expected result before observation. */
			mmap_read_lock(t->mm);
			vma = find_vma(t->mm, start);
			if (!vma || vma->vm_start > start ||
			    !!(vma->vm_flags & VM_DONTDUMP) != !(i & 1))
				w->errors++;
			mmap_read_unlock(t->mm);
		}
	}
done:
	kthread_unuse_mm(t->mm);
	complete(&w->done);
	return 0;
}

static int start(struct test *t, struct worker *w, unsigned int cpu,
		 unsigned int phase, bool reader)
{
	w->test = t;
	w->index = cpu;
	w->phase = phase;
	w->iterations = phase == 0 ? 128 : (phase == 1 ? 1 : 32);
	w->reader = reader;
	init_completion(&w->done);
	init_completion(&w->entered);
	w->task = kthread_create(work, w, "mb_%c%u", reader ? 'r' : 'w', cpu);
	if (IS_ERR(w->task))
		return PTR_ERR(w->task);
	get_task_struct(w->task);
	kthread_bind(w->task, cpu);
	wake_up_process(w->task);
	return 0;
}

static bool join(struct worker *w)
{
	if (!wait_for_completion_timeout(&w->done, 30 * HZ))
		return false;
	kthread_stop(w->task);
	put_task_struct(w->task);
	w->task = NULL;
	return true;
}

static int phase(struct test *t, unsigned int p)
{
	struct kd_mmap_lock *lock = &t->mm->mmap_lock;
	struct mb_counts *c = &t->result.counts[p];
	unsigned int i, pending = 0, spawned = 0, readers = 0;
	unsigned long deadline;
	int error = 0;

	init_completion(&t->go);
	init_completion(&t->release_readers);
	/* Force publication behind two simultaneously admitted local readers.
	 * This proves shared admission and guarantees a real waiting batch. */
	if (p < 2) {
		for (i = 0; i < 2; i++) {
			error = start(t, &t->readers_work[i], 60 + i, p, true);
			if (error)
				goto release;
			readers++;
			if (!wait_for_completion_timeout(&t->readers_work[i].entered, 5 * HZ)) {
				error = -ETIMEDOUT;
				goto release;
			}
		}
		check(t, atomic_read(&t->readers) == 2);
	}
	for (i = 0; i < MB_WORKERS; i++) {
		t->workers[i].completed = t->workers[i].errors = 0;
		error = start(t, &t->workers[i], i, p, false);
		if (error)
			goto release;
		t->result.tids[p][i] = t->workers[i].task->pid;
		spawned++;
	}
	complete_all(&t->go);
	if (p < 2) {
		deadline = jiffies + 5 * HZ;
		do {
			pending = kd_mmap_body_pending(t->mm);
			if (pending == MB_WORKERS)
				break;
			msleep(1);
		} while (time_before(jiffies, deadline));
		check(t, pending == MB_WORKERS);
		t->result.pending_peak = max_t(u64, t->result.pending_peak, pending);
	}
release:
	complete_all(&t->go);
	complete_all(&t->release_readers);
	for (i = 0; i < readers; i++)
		if (!join(&t->readers_work[i]))
			return -EBUSY;
	for (i = 0; i < spawned; i++) {
		if (!join(&t->workers[i]))
			return -EBUSY;
		check(t, t->workers[i].completed == t->workers[i].iterations && !t->workers[i].errors);
		t->result.completed += t->workers[i].completed;
	}
	if (error)
		return error;
	mmap_read_lock(t->mm);
	*c = (struct mb_counts) { lock->body_calls, lock->body_supported,
		lock->body_delegated, lock->body_handbacks, lock->body_native,
		lock->body_post_ban, lock->body_cancelled, lock->body_acks,
		lock->body_native_only };
	mmap_read_unlock(t->mm);
	check(t, kd_mmap_is_idle(lock));
	return 0;
}

/* Keep the healthy head behind a real reader while one published follower is
 * cancelled. The victim cannot retire its link early; after reader release it
 * returns EINTR with no VMA mutation and the exact queue/slot state is empty. */
static int cancellation(struct test *t)
{
	struct kd_mmap_lock *lock = &t->mm->mmap_lock;
	unsigned int i, spawned = 0, pending = 0;
	unsigned long deadline;
	int error = 0;

	mmap_read_lock(t->mm);
	for (i = 0; i < 2; i++) {
		t->workers[i].cancel = true;
		error = start(t, &t->workers[i], i, 0, false);
		if (error)
			goto release;
		spawned++;
		t->result.tids[0][i] = t->workers[i].task->pid;
		deadline = jiffies + 5 * HZ;
		do {
			pending = kd_mmap_body_pending(t->mm);
			if (pending == i + 1)
				break;
			msleep(1);
		} while (time_before(jiffies, deadline));
		check(t, pending == i + 1);
		if (pending != i + 1) { error = -ETIMEDOUT; goto release; }
	}
	t->result.pending_peak = pending;
	check(t, !send_sig(SIGUSR1, t->workers[1].task, 1));
	msleep(20);
	check(t, !completion_done(&t->workers[1].done));
	check(t, !send_sig(SIGKILL, t->workers[1].task, 1));
	msleep(20);
	check(t, !completion_done(&t->workers[1].done));
release:
	mmap_read_unlock(t->mm);
	for (i = 0; i < spawned; i++) {
		if (!join(&t->workers[i]))
			return -EBUSY;
		check(t, t->workers[i].returned == (i ? -EINTR : 0));
		t->result.completed += t->workers[i].completed;
	}
	if (error)
		return error;
	mmap_read_lock(t->mm);
	for (i = 0; i < 2; i++) {
		struct vm_area_struct *vma = find_vma(t->mm, t->result.address[i]);

		check(t, vma && vma->vm_start == t->result.address[i] &&
		      !!(vma->vm_flags & VM_DONTDUMP) == !i);
	}
	t->result.counts[0] = (struct mb_counts) { lock->body_calls, lock->body_supported,
		lock->body_delegated, lock->body_handbacks, lock->body_native,
		lock->body_post_ban, lock->body_cancelled, lock->body_acks,
		lock->body_native_only };
	mmap_read_unlock(t->mm);
	check(t, kd_mmap_is_idle(lock));
	return 0;
}

static long run(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct test *t;
	struct vm_area_struct *vma;
	unsigned int i;
	int error = 0;

	if ((cmd != MB_RUN && cmd != MB_CANCEL) || !current->mm || !current->mm->mmap_lock.use_kd)
		return -EOPNOTSUPP;
	if (atomic_cmpxchg(&busy, 0, 1))
		return -EBUSY;
	t = kzalloc(sizeof(*t), GFP_KERNEL);
	if (!t) { error = -ENOMEM; goto clear; }
	if (copy_from_user(&t->result, (void __user *)arg, sizeof(t->result))) {
		error = -EFAULT;
		goto free;
	}
	if (memchr_inv(&t->result.mm, 0, sizeof(t->result) - sizeof(t->result.address))) {
		error = -EINVAL;
		goto free;
	}
	t->mm = current->mm;
	mmget(t->mm);
	t->result.mm = (unsigned long)t->mm;
	t->result.lock = (unsigned long)&t->mm->mmap_lock;
	mmap_write_lock(t->mm);
	for (i = 0; i < MB_WORKERS; i++) {
		vma = find_vma(t->mm, t->result.address[i]);
		if (!vma || vma->vm_start != t->result.address[i] ||
		    vma->vm_end != vma->vm_start + 3 * PAGE_SIZE || vma->vm_file)
			error = -EINVAL;
	}
	if (!error)
		error = kd_mmap_body_enable(t->mm);
	mmap_write_unlock(t->mm);
	if (!error && cmd == MB_CANCEL)
		error = cancellation(t);
	else
		for (i = 0; !error && i < 3; i++)
			error = phase(t, i);
	if (error == -EBUSY) {
		/* Unjoined tasks retain this context, mm and module for diagnosis. */
		__module_get(THIS_MODULE);
		return error;
	}
	t->result.reader_peak = atomic_read(&t->peak);
	t->result.idle = kd_mmap_is_idle(&t->mm->mmap_lock);
	if (!error && copy_to_user((void __user *)arg, &t->result, sizeof(t->result)))
		error = -EFAULT;
	mmput(t->mm);
free:
	kfree(t);
clear:
	atomic_set(&busy, 0);
	return error;
}

static const struct file_operations operations = {
	.owner = THIS_MODULE, .unlocked_ioctl = run, .llseek = no_llseek,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mm_body_test", .fops = &operations, .mode = 0600,
};
static int __init init(void)
{
	advice = (void *)kallsyms_lookup_name("do_madvise");
	return advice ? misc_register(&device) : -ENOENT;
}
static void __exit fini(void)
{
	WARN_ON(atomic_read(&busy));
	misc_deregister(&device);
}
module_init(init);
module_exit(fini);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Actual mmap_lock typed-body execution, handback and shared-reader correctness");
