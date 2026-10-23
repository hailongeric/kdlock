// SPDX-License-Identifier: GPL-2.0
/* Queue/read-admission controls for actual munmap calls. No body callback is
 * supplied by this module; userspace calls munmap and cancellation uses vm_munmap. */
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/highmem.h>
#include <linux/kd_mmap_lock.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/pagevec.h>
#include <linux/rmap.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include "api.h"

struct session {
	struct mm_struct *mm;
	struct ub_config region;
	struct ub_status result;
	atomic_t controlling, held, readers, ready, release;
	bool partial_cancel;
	unsigned int groups;
	unsigned int pin_mask;
	struct mutex pins_lock;
	struct page *pages[UB_EXT_PAGES], *busy_page;
	unsigned long charges[UB_EXT_PAGES];
	u64 pins_released;
	struct ub_pages snapshot;
	bool change_armed;
	struct ub_change_more change;
};
struct control;
struct worker {
	struct control *control;
	struct task_struct *task;
	struct completion entered, done;
	unsigned int index;
	bool reader;
	int result;
};
struct control {
	struct session *session;
	struct completion release_readers;
	struct completion change_go, change_done;
	bool change_run;
	int change_error;
	struct worker readers[2], writers[2];
};

static void check(struct session *s, bool good)
{
	s->result.checks++;
	if (!good)
		s->result.errors++;
}

static int change_target(struct session *s);

static int work(void *argument)
{
	struct worker *w = argument;
	struct control *c = w->control;
	struct session *s = c->session;

	kthread_use_mm(s->mm);
	if (w->reader) {
		mmap_read_lock(s->mm);
		atomic_inc(&s->readers);
		complete(&w->entered);
		if (s->change_armed && !w->index) {
			wait_for_completion(&c->change_go);
			if (c->change_run) c->change_error = change_target(s);
			complete(&c->change_done);
		}
		wait_for_completion(&c->release_readers);
		atomic_dec(&s->readers);
		mmap_read_unlock(s->mm);
	} else {
		allow_signal(SIGUSR1);
		allow_signal(SIGKILL);
		/* Exercise the real vm_munmap entry, including caller preparation,
		 * killable ownership and cancellation before actual VMA removal. */
		w->result = vm_munmap(s->region.base + w->index * s->region.stride +
			(s->partial_cancel ? PAGE_SIZE : 0), (s->partial_cancel ? 1 : 3) * PAGE_SIZE);
	}
	kthread_unuse_mm(s->mm);
	complete(&w->done);
	return 0;
}

static int start(struct control *c, struct worker *w, unsigned int index, bool reader)
{
	w->control = c;
	w->index = index;
	w->reader = reader;
	init_completion(&w->entered);
	init_completion(&w->done);
	w->task = kthread_create(work, w, "ub_%c%u", reader ? 'r' : 'w', index);
	if (IS_ERR(w->task)) {
		int error = PTR_ERR(w->task);
		w->task = NULL;
		return error;
	}
	get_task_struct(w->task);
	kthread_bind(w->task, reader ? 60 + index : index);
	wake_up_process(w->task);
	return 0;
}

static bool join(struct worker *w)
{
	if (!w->task)
		return true;
	if (!wait_for_completion_timeout(&w->done, 30 * HZ))
		return false;
	kthread_stop(w->task);
	put_task_struct(w->task);
	w->task = NULL;
	return true;
}

static bool wait_pending(struct session *s, unsigned int count)
{
	unsigned long until = jiffies + 10 * HZ;

	do {
		if (kd_mmap_unmap_pending(s->mm) == count)
			return true;
		msleep(1);
	} while (time_before(jiffies, until));
	return false;
}

static int hold(struct session *s, unsigned int count, bool cancel)
{
	struct control *c;
	unsigned int i;
	unsigned long until;
	int error = 0;
	bool drained = true;

	if (!count || count > UB_WORKERS || !READ_ONCE(s->mm->mmap_lock.unmap.enabled))
		return -EINVAL;
	if (atomic_cmpxchg(&s->controlling, 0, 1)) return -EBUSY;
	c = kzalloc(sizeof(*c), GFP_KERNEL);
	if (!c) { atomic_set(&s->controlling, 0); return -ENOMEM; }
	c->session = s;
	init_completion(&c->release_readers);
	init_completion(&c->change_go);
	init_completion(&c->change_done);
	atomic_set(&s->ready, 0);
	atomic_set(&s->release, 0);
	for (i = 0; i < 2; i++) {
		error = start(c, &c->readers[i], i, true);
		if (error) goto out;
		if (!wait_for_completion_timeout(&c->readers[i].entered, 5 * HZ)) {
			error = -ETIMEDOUT; goto out;
		}
	}
	check(s, atomic_read(&s->readers) == 2);
	s->result.reader_peak = max_t(u64, s->result.reader_peak, atomic_read(&s->readers));
	atomic_set(&s->held, 1);
	if (cancel) {
		for (i = 0; i < 2; i++) {
			error = start(c, &c->writers[i], i, false);
			if (error) goto out;
			s->result.cancel_tid[i] = c->writers[i].task->pid;
			if (!wait_pending(s, i + 1)) { error = -ETIMEDOUT; goto out; }
		}
		check(s, !send_sig(SIGUSR1, c->writers[1].task, 1));
		msleep(20);
		check(s, !completion_done(&c->writers[1].done));
		check(s, !send_sig(SIGKILL, c->writers[1].task, 1));
		msleep(20);
		check(s, !completion_done(&c->writers[1].done));
	} else if (!wait_pending(s, count)) {
		error = -ETIMEDOUT; goto out;
	}
	check(s, kd_mmap_unmap_pending(s->mm) == count);
	s->result.pending_peak = max_t(u64, s->result.pending_peak, count);
	until = jiffies + 5 * HZ;
	while (atomic_long_read(&s->mm->mmap_lock.kd.admission) != -1 && time_before(jiffies, until))
		msleep(1);
	check(s, atomic_long_read(&s->mm->mmap_lock.kd.admission) == -1);
	check(s, atomic_long_read(&s->mm->mmap_lock.kd.readers) == 2);
	if (s->change_armed) {
		/* Both local read shares already exist. A normal write fault using
		 * one of them can finish while queued writers await their release.
		 * No reader bypass, PTE poke or body callback is introduced. */
		if (cancel || count != 3 || kd_mmap_unmap_pending(s->mm) != count ||
		    atomic_long_read(&s->mm->mmap_lock.kd.admission) != -1 ||
		    atomic_long_read(&s->mm->mmap_lock.kd.readers) != 2) {
			error = -EINVAL; goto out;
		}
		c->change_run = true;
		complete(&c->change_go);
		if (!wait_for_completion_timeout(&c->change_done, 10 * HZ)) {
			error = -ETIMEDOUT; goto out;
		}
		if (c->change_error) { error = c->change_error; goto out; }
	}
	if (!cancel) {
		atomic_set(&s->ready, 1);
		until = jiffies + 20 * HZ;
		while (!atomic_read(&s->release) && time_before(jiffies, until)) msleep(1);
		if (!atomic_read(&s->release)) error = -ETIMEDOUT;
	}
out:
	atomic_set(&s->ready, 0);
	atomic_set(&s->held, 0);
	complete_all(&c->change_go);
	complete_all(&c->release_readers);
	for (i = 0; i < 2; i++) {
		if (!join(&c->readers[i])) drained = false;
		if (!join(&c->writers[i])) drained = false;
	}
	if (!drained) {
		mmget(s->mm);
		__module_get(THIS_MODULE);
		return -EBUSY;
	}
	if (cancel && !error) {
		mmap_read_lock(s->mm);
		for (i = 0; i < 2; i++) {
			s->result.cancel_result[i] = c->writers[i].result;
			s->result.cancel_mapped[i] = !!vma_lookup(s->mm, s->region.base + i * s->region.stride +
				(s->partial_cancel ? PAGE_SIZE : 0));
			check(s, c->writers[i].result == (i ? -EINTR : 0));
			check(s, s->result.cancel_mapped[i] == !!i);
		}
		mmap_read_unlock(s->mm);
	}
	until = jiffies + 20 * HZ;
	while (!kd_mmap_is_idle(&s->mm->mmap_lock) && time_before(jiffies, until)) msleep(1);
	if (!kd_mmap_is_idle(&s->mm->mmap_lock)) error = -ETIMEDOUT;
	kfree(c);
	atomic_set(&s->controlling, 0);
	return error;
}

#include "resident.inc"
#include "target_change.inc"

static long operation(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct session *s = file->private_data;
	struct kd_mmap_unmap_state *f = &s->mm->mmap_lock.unmap;
	struct ub_status result;
	struct ub_config region;
	int error;

	if (current->mm != s->mm)
		return -EXDEV;
	switch (cmd) {
	case UB_CHANGE_ARM:
	case UB_CHANGE_NOW:
	case UB_CHANGE_RESULT:
	case UB_CHANGE_EMPTY_ZERO_ARM:
	case UB_CHANGE_EMPTY_PRIVATE_ARM:
	case UB_CHANGE_RESULT_MORE:
		return change_operation(s, cmd, arg);
	case UB_EXPERIMENT:
		return experiment(s, arg);
	case UB_RMAP:
		return rmap_state(s, arg);
	case UB_PIN:
	case UB_PIN_MASK:
	case UB_PAGESTATE:
	case UB_DROP:
	case UB_BUSY_LOCK:
	case UB_BUSY_UNLOCK:
	case UB_UNPIN_MAPPED:
		return page_operation(s, cmd, arg);
	case UB_PTES:
	case UB_PTE_TABLES:
		return pte_state(s, arg, cmd == UB_PTE_TABLES);
	case UB_EXTRA: {
		struct ub_extra extra;

		mmap_read_lock(s->mm);
		extra = (struct ub_extra) { f->test_fail_after, f->test_fail_seen,
			pins_owned(s), s->pins_released };
		mmap_read_unlock(s->mm);
		return copy_to_user((void __user *)arg, &extra, sizeof(extra)) ? -EFAULT : 0;
	}
	case UB_ENABLE:
		if (copy_from_user(&region, (void __user *)arg, sizeof(region))) return -EFAULT;
		mmap_write_lock(s->mm);
		error = kd_mmap_unmap_enable(s->mm, region.start, region.end);
		if (!error) s->region = region;
		mmap_write_unlock(s->mm);
		return error;
	case UB_HOLD:
		return hold(s, arg, false);
	case UB_CANCEL:
		return hold(s, 2, true);
	case UB_CANCEL_PARTIAL:
		s->partial_cancel = true;
		error = hold(s, 2, true);
		s->partial_cancel = false;
		return error;
	case UB_LAYOUT: {
		struct ub_layout layout;
		struct vm_area_struct *vma;

		if (copy_from_user(&layout, (void __user *)arg, sizeof(layout))) return -EFAULT;
		mmap_read_lock(s->mm);
		vma = vma_lookup(s->mm, layout.address);
		layout.start = vma ? vma->vm_start : 0;
		layout.end = vma ? vma->vm_end : 0;
		layout.pgoff = vma ? vma->vm_pgoff : 0;
		layout.flags = vma ? vma->vm_flags : 0;
		layout.map_count = s->mm->map_count;
		layout.total_vm = s->mm->total_vm;
		layout.data_vm = s->mm->data_vm;
		layout.stack_vm = s->mm->stack_vm;
		layout.exec_vm = s->mm->exec_vm;
		layout.pgtables = mm_pgtables_bytes(s->mm);
		mmap_read_unlock(s->mm);
		return copy_to_user((void __user *)arg, &layout, sizeof(layout)) ? -EFAULT : 0;
	}
	case UB_RELEASE:
		atomic_set(&s->release, 1);
		return 0;
	case UB_STATUS:
		result = s->result;
		result.counts = (struct ub_counts) {
			atomic64_read(&f->calls), atomic64_read(&f->removed),
			atomic64_read(&f->delegated), atomic64_read(&f->native),
			atomic64_read(&f->post_ban), atomic64_read(&f->handbacks),
			atomic64_read(&f->acks), atomic64_read(&f->cancelled),
			atomic64_read(&f->refused), atomic64_read(&f->failed), READ_ONCE(f->native_only),
		};
		result.mm = (unsigned long)s->mm;
		result.gate = (unsigned long)&s->mm->mmap_lock.kd.gate;
		result.pending = kd_mmap_unmap_pending(s->mm);
		result.idle = kd_mmap_is_idle(&s->mm->mmap_lock);
		result.held = atomic_read(&s->held);
		result.ready = atomic_read(&s->ready);
		result.readers = atomic_long_read(&s->mm->mmap_lock.kd.readers);
		result.admission = atomic_long_read(&s->mm->mmap_lock.kd.admission);
		result.pgdir_size = PGDIR_SIZE;
		result.task_size = TASK_SIZE;
		return copy_to_user((void __user *)arg, &result, sizeof(result)) ? -EFAULT : 0;
	default:
		return -EINVAL;
	}
}

static int opened(struct inode *inode, struct file *file)
{
	struct session *s;

	if (!current->mm || !current->mm->mmap_lock.use_kd)
		return -EOPNOTSUPP;
	s = kzalloc(sizeof(*s), GFP_KERNEL);
	if (!s) return -ENOMEM;
	s->mm = current->mm;
	mutex_init(&s->pins_lock);
	mmget(s->mm);
	file->private_data = s;
	return 0;
}

static int released(struct inode *inode, struct file *file)
{
	struct session *s = file->private_data;

	if (atomic_read(&s->controlling)) {
		__module_get(THIS_MODULE);
		return 0;
	}
	WARN_ON(!kd_mmap_is_idle(&s->mm->mmap_lock));
	drop_pins(s);
	mmput(s->mm);
	kfree(s);
	return 0;
}

static const struct file_operations operations = {
	.owner = THIS_MODULE, .open = opened, .release = released,
	.unlocked_ioctl = operation, .llseek = no_llseek,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mm_unmap_test", .fops = &operations, .mode = 0600,
};
static int __init init(void) { return misc_register(&device); }
static void __exit fini(void) { misc_deregister(&device); }
module_init(init);
module_exit(fini);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Actual munmap queue, caller handback and shared-reader correctness");
