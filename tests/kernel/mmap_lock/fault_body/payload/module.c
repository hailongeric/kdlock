// SPDX-License-Identifier: GPL-2.0
/* Controls only queue admission and observation. Actual user/kernel memory
 * writes enter the hardware page-fault path; this module supplies no body. */
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/kd_mmap_lock.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include "api.h"

/* Existing physical provider APIs, used only to hold the real fault gate until
 * all test origins have published. They do not implement a synthetic fault. */
extern void kd_mmap_mutex_local_lock(struct kd_mmap_mutex *lock);
extern void kd_mmap_mutex_local_unlock(struct kd_mmap_mutex *lock);

struct session {
	struct mm_struct *mm;
	struct fb_region region;
	struct fb_status result;
	atomic_t controlling, held, readers;
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
	struct worker readers[2], writers[2];
};

static void check(struct session *s, bool good)
{
	s->result.checks++;
	if (!good)
		s->result.errors++;
}

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
		wait_for_completion(&c->release_readers);
		atomic_dec(&s->readers);
		mmap_read_unlock(s->mm);
	} else {
		allow_signal(SIGUSR1);
		allow_signal(SIGKILL);
		/* put_user causes a genuine kernel-mode CPU write fault in this mm.
		 * SIGKILL exercises the normal x86 exception-table retry/fixup edge. */
		w->result = put_user((u8)(0x61 + w->index),
			(u8 __user *)(unsigned long)(s->region.start + w->index * PAGE_SIZE));
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
	w->task = kthread_create(work, w, "fb_%c%u", reader ? 'r' : 'w', index);
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
		if (kd_mmap_fault_pending(s->mm) == count)
			return true;
		msleep(1);
	} while (time_before(jiffies, until));
	return false;
}

static bool present(struct mm_struct *mm, unsigned long address)
{
	pgd_t *pgd = pgd_offset(mm, address);
	p4d_t *p4d;
	pud_t *pud;
	pmd_t *pmd;
	pte_t *pte;
	spinlock_t *ptl;
	bool found;

	if (pgd_none(*pgd) || pgd_bad(*pgd)) return false;
	p4d = p4d_offset(pgd, address);
	if (p4d_none(*p4d) || p4d_bad(*p4d)) return false;
	pud = pud_offset(p4d, address);
	if (pud_none(*pud) || pud_bad(*pud)) return false;
	pmd = pmd_offset(pud, address);
	if (pmd_none(*pmd) || pmd_trans_unstable(pmd)) return false;
	pte = pte_offset_map_lock(mm, pmd, address, &ptl);
	found = pte_present(*pte);
	pte_unmap_unlock(pte, ptl);
	return found;
}

static int hold(struct session *s, unsigned int count, bool cancel)
{
	struct kd_mmap_fault_state *f = &s->mm->mmap_lock.fault;
	struct control *c;
	u64 before;
	unsigned int i;
	unsigned long until;
	int error = 0;
	bool gate = false, drained = true;

	if (!count || count > FB_WORKERS || !READ_ONCE(f->enabled))
		return -EINVAL;
	if (atomic_cmpxchg(&s->controlling, 0, 1))
		return -EBUSY;
	c = kzalloc(sizeof(*c), GFP_KERNEL);
	if (!c) { atomic_set(&s->controlling, 0); return -ENOMEM; }
	c->session = s;
	init_completion(&c->release_readers);
	before = atomic64_read(&f->delegated);
	for (i = 0; i < 2; i++) {
		error = start(c, &c->readers[i], i, true);
		if (error) goto out;
		if (!wait_for_completion_timeout(&c->readers[i].entered, 5 * HZ)) {
			error = -ETIMEDOUT; goto out;
		}
	}
	check(s, atomic_read(&s->readers) == 2);
	s->result.reader_peak = max_t(u64, s->result.reader_peak, atomic_read(&s->readers));
	kd_mmap_mutex_local_lock(&f->gate);
	gate = true;
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
		error = -ETIMEDOUT;
		goto out;
	}
	check(s, kd_mmap_fault_pending(s->mm) == count);
	kd_mmap_mutex_local_unlock(&f->gate);
	gate = false;
	atomic_set(&s->held, 0);
	until = jiffies + 20 * HZ;
	while (!kd_mmap_fault_idle(&s->mm->mmap_lock) && time_before(jiffies, until))
		msleep(1);
	if (!kd_mmap_fault_idle(&s->mm->mmap_lock)) { error = -ETIMEDOUT; goto out; }
	check(s, atomic_read(&s->readers) == 2);
	/* These two real readers remained admitted through remote installation. */
	s->result.delegated_with_readers += atomic64_read(&f->delegated) - before;
out:
	if (gate)
		kd_mmap_mutex_local_unlock(&f->gate);
	atomic_set(&s->held, 0);
	complete_all(&c->release_readers);
	for (i = 0; i < 2; i++) {
		if (!join(&c->readers[i])) drained = false;
		if (!join(&c->writers[i])) drained = false;
	}
	if (!drained) {
		/* Keep the context, mm and module reachable for diagnosis. */
		mmget(s->mm);
		__module_get(THIS_MODULE);
		return -EBUSY;
	}
	if (cancel && !error) {
		mmap_read_lock(s->mm);
		for (i = 0; i < 2; i++) {
			s->result.cancel_result[i] = c->writers[i].result;
			s->result.cancel_present[i] = present(s->mm, s->region.start + i * PAGE_SIZE);
			check(s, c->writers[i].result == (i ? -EFAULT : 0));
			check(s, s->result.cancel_present[i] == !i);
		}
		mmap_read_unlock(s->mm);
	}
	kfree(c);
	atomic_set(&s->controlling, 0);
	return error;
}

static long operation(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct session *s = file->private_data;
	struct kd_mmap_fault_state *f = &s->mm->mmap_lock.fault;
	struct fb_status result;
	struct fb_region region;
	int error;

	if (current->mm != s->mm)
		return -EXDEV;
	switch (cmd) {
	case FB_ENABLE:
		if (copy_from_user(&region, (void __user *)arg, sizeof(region))) return -EFAULT;
		mmap_write_lock(s->mm);
		error = kd_mmap_fault_enable(s->mm, region.start, region.end);
		if (!error) s->region = region;
		mmap_write_unlock(s->mm);
		return error;
	case FB_HOLD:
		return hold(s, arg, false);
	case FB_CANCEL:
		return hold(s, 2, true);
	case FB_STATUS:
		result = s->result;
		result.counts = (struct fb_counts) {
			atomic64_read(&f->calls), atomic64_read(&f->supported),
			atomic64_read(&f->delegated), atomic64_read(&f->native),
			atomic64_read(&f->post_ban), atomic64_read(&f->handbacks),
			atomic64_read(&f->acks), atomic64_read(&f->cancelled),
			atomic64_read(&f->refused), READ_ONCE(f->native_only),
		};
		result.mm = (unsigned long)s->mm;
		result.gate = (unsigned long)&f->gate;
		result.pending = kd_mmap_fault_pending(s->mm);
		result.idle = kd_mmap_fault_idle(&s->mm->mmap_lock);
		result.held = atomic_read(&s->held);
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
	WARN_ON(!kd_mmap_fault_idle(&s->mm->mmap_lock));
	mmput(s->mm);
	kfree(s);
	return 0;
}

static const struct file_operations operations = {
	.owner = THIS_MODULE, .open = opened, .release = released,
	.unlocked_ioctl = operation, .llseek = no_llseek,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mm_fault_test", .fops = &operations, .mode = 0600,
};
static int __init init(void) { return misc_register(&device); }
static void __exit fini(void) { misc_deregister(&device); }
module_init(init);
module_exit(fini);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Actual page-fault body queue, caller handback and shared-reader correctness");
