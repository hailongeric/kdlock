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
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/swap.h>
#include <linux/uaccess.h>
#include "api.h"

struct session {
	struct mm_struct *mm;
	struct ub_config region;
	struct ub_status result;
	atomic_t controlling, held, readers, ready, release;
	struct mutex pins_lock;
	struct page *pages[UB_PAGES];
	unsigned long charges[UB_PAGES];
	struct ub_pages snapshot;
	struct page *busy_page;
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
		/* Exercise the real vm_munmap entry, including caller preparation,
		 * killable ownership and cancellation before actual VMA removal. */
		w->result = vm_munmap(s->region.base + w->index * s->region.stride, s->region.width * PAGE_SIZE);
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
	w->task = kthread_create(work, w, "pu_%c%u", reader ? 'r' : 'w', index);
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
	if (!cancel) {
		atomic_set(&s->ready, 1);
		until = jiffies + 20 * HZ;
		while (!atomic_read(&s->release) && time_before(jiffies, until)) msleep(1);
		if (!atomic_read(&s->release)) error = -ETIMEDOUT;
	}
out:
	atomic_set(&s->ready, 0);
	atomic_set(&s->held, 0);
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
			s->result.cancel_mapped[i] = !!vma_lookup(s->mm, s->region.base + i * s->region.stride);
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

static unsigned long target(struct session *s, unsigned int index)
{
	unsigned int group, page;
	ub_pin_location(&s->region, index, &group, &page);
	return s->region.base + group * s->region.stride + page * PAGE_SIZE;
}

static unsigned int pins_owned(struct session *s)
{
	unsigned int i, count = 0;
	for (i = 0; i < UB_PAGES; i++) count += !!READ_ONCE(s->pages[i]);
	return count;
}

static void drop_pins(struct session *s)
{
	unsigned int i;
	if (s->busy_page) { unlock_page(s->busy_page); s->busy_page = NULL; }
	for (i = 0; i < UB_PAGES; i++) {
		struct page *page = s->pages[i];
		if (!page) continue;
		s->pages[i] = NULL;
		put_page(page);
		s->result.pins_released++;
	}
}

static void settle_page_references(struct session *s)
{
	struct pagevec scratch;
	unsigned int i;

	/* The client populated and acquired these pages on its pinned setup CPU.
	 * Release exact scratch references through the exported page-vector API:
	 * it drains this CPU's deferred LRU references before our ownership oracle.
	 * lru_add_drain itself is internal and cannot be called from a module. */
	pagevec_init(&scratch);
	for (i = 0; i < ub_pin_total(&s->region); i++) {
		if (!s->pages[i]) continue;
		get_page(s->pages[i]);
		if (!pagevec_add(&scratch, s->pages[i])) pagevec_release(&scratch);
	}
	pagevec_release(&scratch);
}

static long page_operation(struct session *s, unsigned int cmd, unsigned long arg)
{
	unsigned int i;
	int error = 0;

	mutex_lock(&s->pins_lock);
	if (atomic_read(&s->controlling) || !s->region.groups) { error = -EBUSY; goto out; }
	if (cmd == UB_PIN) {
		if (pins_owned(s)) { error = -EBUSY; goto out; }
		mmap_read_lock(s->mm);
		for (i = 0; i < ub_pin_total(&s->region); i++) {
			long n = get_user_pages(target(s, i), 1, FOLL_WRITE, &s->pages[i], NULL);
			if (n != 1) { s->pages[i] = NULL; error = n < 0 ? n : -EFAULT; break; }
			s->charges[i] = READ_ONCE(s->pages[i]->memcg_data);
		}
		mmap_read_unlock(s->mm);
		settle_page_references(s);
		if (error) drop_pins(s);
	} else if (cmd == UB_PAGESTATE) {
		if (pins_owned(s) != ub_pin_total(&s->region)) { error = -EINVAL; goto out; }
		s->snapshot.count = ub_pin_total(&s->region);
		for (i = 0; i < ub_pin_total(&s->region); i++) {
			struct page *page = s->pages[i];
			unsigned char *bytes = kmap_local_page(page);
			u64 hash = 1469598103934665603ULL;
			unsigned int byte, group, offset;
			unsigned char value;

			ub_pin_location(&s->region, i, &group, &offset);
			value = 1 + group * 3 + offset;

			for (byte = 0; byte < PAGE_SIZE; byte++) {
				check(s, bytes[byte] == value);
				hash = (hash ^ bytes[byte]) * 1099511628211ULL;
			}
			kunmap_local(bytes);
			s->snapshot.page[i] = (struct ub_page) {
				target(s, i), page_to_pfn(page), hash, page_mapcount(page),
				page_count(page), READ_ONCE(page->memcg_data) == s->charges[i], value, PageLocked(page),
			};
			check(s, s->snapshot.page[i].charged_same);
		}
		if (copy_to_user((void __user *)arg, &s->snapshot, sizeof(s->snapshot))) error = -EFAULT;
	} else if (cmd == UB_BUSY_LOCK) {
		unsigned int last = ub_group_pins(&s->region, 0) + ub_group_pins(&s->region, 1) - 1;
		if (s->busy_page || s->region.groups != 3 || !s->pages[last] ||
		    !trylock_page(s->pages[last])) { error = -EBUSY; goto out; }
		s->busy_page = s->pages[last];
	} else if (cmd == UB_BUSY_UNLOCK) {
		if (!s->busy_page) { error = -EINVAL; goto out; }
		unlock_page(s->busy_page); s->busy_page = NULL;
	} else if (cmd == UB_UNPIN_MAPPED) {
		for (i = 0; i < ub_pin_total(&s->region); i++)
			if (!s->pages[i] || page_mapcount(s->pages[i]) != 1 || page_count(s->pages[i]) != 2) {
				error = -EBUSY; goto out;
			}
		drop_pins(s);
	} else {
		if (!kd_mmap_is_idle(&s->mm->mmap_lock)) { error = -EBUSY; goto out; }
		for (i = 0; i < ub_pin_total(&s->region); i++)
			if ((s->pages[i] && page_mapped(s->pages[i])) ||
			    (!s->pages[i] && s->result.pins_released != ub_pin_total(&s->region))) { error = -EBUSY; goto out; }
		/* The unsupported no-neighbor case uses native deferred table free.
		 * Drain those kernel callbacks after every requester has joined. */
		rcu_barrier();
		drop_pins(s);
	}
out:
	mutex_unlock(&s->pins_lock);
	return error;
}

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
	case UB_ENABLE:
		if (copy_from_user(&region, (void __user *)arg, sizeof(region))) return -EFAULT;
		if ((region.groups != 2 && region.groups != 3 && region.groups != UB_GROUPS) ||
		    !region.width || region.width > 4 || region.wide > 1 ||
		    (region.wide && (region.width != 4 || region.groups != 3)) ||
		    region.stride < 16 * PAGE_SIZE || region.base < region.start ||
		    region.base >= region.end ||
		    region.groups > (region.end - region.base) / region.stride + 1) return -EINVAL;
		mmap_write_lock(s->mm);
		error = kd_mmap_unmap_populated_enable(s->mm, region.start, region.end);
		if (!error) s->region = region;
		mmap_write_unlock(s->mm);
		return error;
	case UB_HOLD:
		return hold(s, arg, false);
	case UB_CANCEL:
		return hold(s, 2, true);
	case UB_RELEASE:
		atomic_set(&s->release, 1);
		return 0;
	case UB_PIN:
	case UB_PAGESTATE:
	case UB_DROP:
	case UB_UNPIN_MAPPED:
	case UB_BUSY_LOCK:
	case UB_BUSY_UNLOCK:
		return page_operation(s, cmd, arg);
	case UB_STATUS:
		result = s->result;
		result.counts = (struct ub_counts) {
			atomic64_read(&f->calls), atomic64_read(&f->removed),
			atomic64_read(&f->delegated), atomic64_read(&f->native),
			atomic64_read(&f->post_ban), atomic64_read(&f->handbacks),
			atomic64_read(&f->acks), atomic64_read(&f->cancelled),
			atomic64_read(&f->refused), atomic64_read(&f->failed), READ_ONCE(f->native_only),
			atomic64_read(&f->populated), atomic64_read(&f->populated_remote),
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
		result.pins_owned = pins_owned(s);
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
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mm_populated_test", .fops = &operations, .mode = 0600,
};
static int __init init(void) { return misc_register(&device); }
static void __exit fini(void) { misc_deregister(&device); }
module_init(init);
module_exit(fini);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Actual munmap queue, caller handback and shared-reader correctness");
