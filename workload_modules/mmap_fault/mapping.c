// SPDX-License-Identifier: GPL-2.0
/* Opt-in module-owned mappings, not an mm_struct::mmap_lock replacement.
 * The native mmap lock protects VMAs. One immutable per-file backend protects
 * backing metadata. Allocation, user copies and page-table work stay outside
 * that private lock. Faults and mode transitions execute on the origin task.
 */
#include <linux/fs.h>
#include <linux/highmem.h>
#include <linux/list.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/rwsem.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/wait.h>
#include "kd_rwsem.h"
#include "kd_rwsem_direct.h"
#include "rwlock/komb_rwlock.h"
#include "mmap_fault_uapi.h"

#define MF_MAX_PAGES 64
#define MF_FEATURES (MF_PRIVATE | MF_WRITABLE | MF_INHERIT | MF_DOWNGRADE | MF_ALLOW_FALLBACK | MF_LOOKUP_WRITE | MF_DELEGATE)

struct mf_scope {
	struct task_struct *task;
	struct mm_struct *mm;
	struct mf_probe *result;
	bool held;
};
struct mf_mapping {
	union {
		struct kd_rwsem kd;
		struct rw_semaphore native;
		struct komb_rwlock tc;
	} lock;
	void *allocation;
	unsigned int backend, features, pages, fallback;
	struct page *page[MF_MAX_PAGES];
	u64 epoch, complement;
	/* The lookup sequence is backing metadata protected by writer ownership.
	 * Page slots and their base references are immutable until final release. */
	u64 lookup_sequence;
	/* scope is published and removed under the private writer lock. Only
	 * its exact origin task may use the stack record outside that lock. */
	struct mf_scope *scope;
	atomic_t probe_busy, vmas, dropped, proceed;
	wait_queue_head_t events;
	atomic64_t faults, reads, read_ends, writes, write_ends, downgrades;
	atomic64_t context_errors, data_errors, scopes, scope_ends;
	atomic64_t lookup_begins, lookup_ends, lookup_fallbacks, lookup_candidates, fault_lookups;
};
struct mf_file {
	atomic_t configuring;
	struct mf_mapping *mapping;
};
static atomic_t files = ATOMIC_INIT(0);
static atomic64_t destroyed = ATOMIC64_INIT(0);
static atomic64_t release_errors = ATOMIC64_INIT(0);

static void mf_read(struct mf_mapping *m)
{
	if (!MF_TC_BUILD && m->backend == MF_KD)
		kd_down_read(&m->lock.kd);
	else if (MF_TC_BUILD && m->backend == MF_TC) {
		preempt_disable();
		komb_read_lock(&m->lock.tc);
	} else
		down_read(&m->lock.native);
	atomic64_inc(&m->reads);
}
static void mf_read_end(struct mf_mapping *m)
{
	atomic64_inc(&m->read_ends);
	if (!MF_TC_BUILD && m->backend == MF_KD)
		kd_up_read(&m->lock.kd);
	else if (MF_TC_BUILD && m->backend == MF_TC) {
		komb_read_unlock(&m->lock.tc);
		preempt_enable();
	} else
		up_read(&m->lock.native);
}
static void mf_write(struct mf_mapping *m)
{
	if (!MF_TC_BUILD && m->backend == MF_KD)
		kd_down_write(&m->lock.kd);
	else if (MF_TC_BUILD && m->backend == MF_TC) {
		preempt_disable();
		komb_write_lock(&m->lock.tc);
	} else
		down_write(&m->lock.native);
	atomic64_inc(&m->writes);
}
static void mf_write_end(struct mf_mapping *m)
{
	atomic64_inc(&m->write_ends);
	if (!MF_TC_BUILD && m->backend == MF_KD)
		kd_up_write(&m->lock.kd);
	else if (MF_TC_BUILD && m->backend == MF_TC) {
		komb_write_unlock(&m->lock.tc);
		preempt_enable();
	} else
		up_write(&m->lock.native);
}
static bool mf_idle(struct mf_mapping *m)
{
	if (!MF_TC_BUILD && m->backend == MF_KD)
		return kd_rwsem_is_idle(&m->lock.kd);
	if (MF_TC_BUILD && m->backend == MF_TC)
		return !atomic_read(&m->lock.tc.cnts) && !atomic_read(&m->lock.tc.lock.val);
	return !rwsem_is_locked(&m->lock.native);
}

#include "lookup.inc"

static int mf_open(struct inode *inode, struct file *file)
{
	struct mf_file *f = kzalloc(sizeof(*f), GFP_KERNEL);
	if (!f)
		return -ENOMEM;
	file->private_data = f;
	atomic_inc(&files);
	return 0;
}
static void mf_free(struct mf_mapping *m)
{
	unsigned int i;
	if (!m)
		return;
	for (i = 0; i < m->pages; i++)
		if (m->page[i])
			put_page(m->page[i]);
	kfree(m->allocation);
}
static int mf_release(struct inode *inode, struct file *file)
{
	struct mf_file *f = file->private_data;
	struct mf_mapping *m = f->mapping;
	/* VFS file references cover every VMA and ioctl. Only this final release
	 * can inspect idle and destroy the object; counters never permit unload. */
	if (m) {
		if (atomic_read(&m->vmas) || atomic_read(&m->probe_busy) || m->scope ||
		    !mf_idle(m) || atomic64_read(&m->reads) != atomic64_read(&m->read_ends) ||
		    atomic64_read(&m->writes) != atomic64_read(&m->write_ends) ||
		    atomic64_read(&m->lookup_begins) != atomic64_read(&m->lookup_ends) ||
		    atomic64_read(&m->lookup_ends) != m->lookup_sequence ||
		    atomic64_read(&m->context_errors) || atomic64_read(&m->data_errors)) {
			atomic64_inc(&release_errors);
			WARN_ON_ONCE(1);
			/* An invariant failure retains storage and the module for
			 * diagnosis; a final file put is not a substitute for drain. */
			__module_get(THIS_MODULE);
			return 0;
		}
		mf_free(m);
		atomic64_inc(&destroyed);
	}
	kfree(f);
	atomic_dec(&files);
	return 0;
}

static int mf_create(struct mf_file *f, struct mf_create *c)
{
	struct mf_mapping *m;
	void *allocation;
	unsigned int i, selected = c->backend;
	bool unsupported;
	if (c->abi != MF_ABI || c->backend > MF_TC || !c->pages || c->pages > MF_MAX_PAGES ||
	    c->features & ~MF_FEATURES || c->reserved[0] || c->reserved[1])
		return -EINVAL;
	if (c->backend == (MF_TC_BUILD ? MF_KD : MF_TC))
		return -EOPNOTSUPP;
	if ((c->features & MF_DELEGATE) &&
	    (!(c->features & MF_LOOKUP_WRITE) || c->backend != MF_KD))
		return -EOPNOTSUPP;
	if ((c->features & MF_LOOKUP_WRITE) &&
	    (c->features & (MF_PRIVATE | MF_WRITABLE | MF_INHERIT)))
		return -EOPNOTSUPP;
	/* Shared writeback/page_mkwrite is not this driver's callback contract. */
	if ((c->features & MF_WRITABLE) && !(c->features & MF_PRIVATE))
		return -EOPNOTSUPP;
	unsupported = selected != MF_NATIVE &&
		(c->features & (MF_PRIVATE | MF_WRITABLE | MF_INHERIT));
	unsupported |= selected == MF_TC && (c->features & MF_DOWNGRADE);
	if (unsupported) {
		if (!(c->features & MF_ALLOW_FALLBACK))
			return -EOPNOTSUPP;
		selected = MF_NATIVE;
	}
	if (atomic_cmpxchg(&f->configuring, 0, 1))
		return -EBUSY;
	allocation = kzalloc(sizeof(*m) + __alignof__(*m) - 1, GFP_KERNEL);
	if (!allocation)
		goto oom;
	m = PTR_ALIGN(allocation, __alignof__(*m));
	m->allocation = allocation;
	m->backend = selected;
	m->features = c->features;
	m->fallback = unsupported;
	m->pages = c->pages;
	m->complement = ~m->epoch;
	init_waitqueue_head(&m->events);
	if (!MF_TC_BUILD && selected == MF_KD)
		kd_rwsem_init(&m->lock.kd);
	else if (selected == MF_NATIVE)
		init_rwsem(&m->lock.native);
	/* TCLock's zero initializer is its unlocked state; no live type switch. */
	for (i = 0; i < m->pages; i++) {
		m->page[i] = alloc_page(GFP_KERNEL | __GFP_ZERO);
		if (!m->page[i]) {
			mf_free(m);
			goto oom;
		}
		*(u64 *)page_address(m->page[i]) = MF_WORD + i;
	}
	c->selected_backend = selected;
	c->fallback = unsupported;
	/* Publication happens once, after every page and the chosen lock exist. */
	smp_store_release(&f->mapping, m);
	return 0;
oom:
	atomic_set(&f->configuring, 0);
	return -ENOMEM;
}

static void mf_mm_release(struct mf_scope *scope)
{
	/* Authority is this origin's exact acquisition, never rwsem_is_locked(). */
	if (WARN_ON_ONCE(!scope->held || current != scope->task))
		return;
	scope->held = false;
	scope->result->releases++;
	mmap_read_unlock(scope->mm);
}

static vm_fault_t mf_fault(struct vm_fault *vmf)
{
	struct task_struct *origin = current;
	struct mf_mapping *m = vmf->vma->vm_private_data;
	struct mf_scope *scope = NULL;
	struct page *page = NULL;
	vm_fault_t result;
	unsigned int action = MF_NORMAL;

	atomic64_inc(&m->faults);
	if (origin->mm != vmf->vma->vm_mm || !origin->mm) {
		atomic64_inc(&m->context_errors);
		return VM_FAULT_SIGBUS;
	}
	mf_read(m);
	if (m->complement != ~m->epoch)
		atomic64_inc(&m->data_errors);
	if (m->scope && m->scope->task == origin) {
		scope = m->scope;
		scope->result->callbacks++;
		action = scope->result->action;
	}
	if (!(m->features & MF_LOOKUP_WRITE) && vmf->pgoff < m->pages) {
		page = m->page[vmf->pgoff];
		get_page(page);
	}
	mf_read_end(m);
	if (m->features & MF_LOOKUP_WRITE) {
		/* Read scope/task state only on the origin. The delegated helper
		 * sees immutable slot identity and resident backing metadata only. */
		atomic64_inc(&m->fault_lookups);
		page = mf_lookup_page(m, vmf->pgoff,
			vmf->flags & (FAULT_FLAG_RETRY_NOWAIT | FAULT_FLAG_TRIED |
				      FAULT_FLAG_WRITE | FAULT_FLAG_REMOTE), NULL);
	}
	if (!page)
		return VM_FAULT_SIGBUS;
	/* Only an active ioctl scope may release mmap ownership. Its VFS file
	 * reference and mmget survive the release; ordinary CPU faults never
	 * inherit a scope from another task. No VMA is used after a drop. */
	if (scope && (action == MF_RETRY || action == MF_REVALIDATE || action == MF_NOWAIT) &&
	    !(vmf->flags & FAULT_FLAG_TRIED) && (vmf->flags & FAULT_FLAG_ALLOW_RETRY)) {
		put_page(page);
		if (vmf->flags & FAULT_FLAG_RETRY_NOWAIT) {
			scope->result->nowait++;
			return VM_FAULT_RETRY;
		}
		scope->result->retries++;
		mf_mm_release(scope);
		if (action == MF_REVALIDATE) {
			atomic_set(&m->dropped, 1);
			wake_up_all(&m->events);
			if (!wait_event_timeout(m->events, atomic_read(&m->proceed), 5 * HZ))
				scope->result->pause_timeout++;
		}
		return VM_FAULT_RETRY;
	}
	if (scope && action == MF_COMPLETED) {
		/* Shared read-only VM_MIXEDMAP is checked by the ioctl before entry.
		 * NOPAGE tells __do_fault no vmf->page is returned. COMPLETED records
		 * the separately completed native mmap release, exactly once. */
		result = vmf_insert_page(vmf->vma, vmf->address, page);
		put_page(page);
		if (result & VM_FAULT_ERROR)
			return result;
		scope->result->completed++;
		mf_mm_release(scope);
		return result | VM_FAULT_COMPLETED;
	}
	vmf->page = page; /* Core fault handling consumes this acquired reference. */
	return 0;
}

static void mf_vma_open(struct vm_area_struct *vma)
{
	struct mf_mapping *m = vma->vm_private_data;
	atomic_inc(&m->vmas);
}
static void mf_vma_close(struct vm_area_struct *vma)
{
	struct mf_mapping *m = vma->vm_private_data;
	atomic_dec(&m->vmas);
}
static const struct vm_operations_struct mf_vm_ops = {
	.open = mf_vma_open, .close = mf_vma_close, .fault = mf_fault,
};
static int mf_mmap(struct file *file, struct vm_area_struct *vma)
{
	struct mf_file *f = file->private_data;
	struct mf_mapping *m = smp_load_acquire(&f->mapping);
	if (!m)
		return -EINVAL;
	if (command == MF_PREPARE) {
#if !MF_TC_BUILD
		if (m->backend == MF_KD && (m->features & MF_DELEGATE))
			return kd_mutex_prepare(&m->lock.kd.gate, (unsigned long)mf_lookup_entry,
					       KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#endif
		return -EOPNOTSUPP;
	}
	if (command == MF_LOOKUPS || command == MF_LOCAL_LOOKUPS) {
		struct mf_work work;
		u64 i;
		if (!(m->features & MF_LOOKUP_WRITE) || !current->mm)
			return -EOPNOTSUPP;
		if (copy_from_user(&work, user, sizeof(work)))
			return -EFAULT;
		if (!work.iterations || work.iterations > 10000000 || work.completed || work.errors || work.last_sequence)
			return -EINVAL;
		for (i = 0; i < work.iterations; i++) {
			struct page *page = mf_lookup_page(m, i % m->pages,
				command == MF_LOCAL_LOOKUPS, &work.last_sequence);
			if (!page || *(u64 *)page_address(page) != MF_WORD + i % m->pages)
				work.errors++;
			if (page)
				put_page(page);
			work.completed++;
			if (!(i & 255))
				cond_resched();
		}
		return copy_to_user(user, &work, sizeof(work)) ? -EFAULT : 0;
	}
	if (!!(vma->vm_flags & VM_SHARED) == !!(m->features & MF_PRIVATE) ||
	    !!(vma->vm_flags & VM_WRITE) != !!(m->features & MF_WRITABLE) ||
	    !(vma->vm_flags & VM_READ) || vma->vm_flags & VM_EXEC)
		return -EOPNOTSUPP;
	if (vma->vm_pgoff > m->pages || vma_pages(vma) > m->pages - vma->vm_pgoff)
		return -EINVAL;
	vma->vm_flags |= VM_DONTEXPAND | VM_DONTDUMP;
	if (!(m->features & MF_INHERIT))
		vma->vm_flags |= VM_DONTCOPY;
	if (!(m->features & MF_WRITABLE))
		vma->vm_flags &= ~VM_MAYWRITE;
	vma->vm_flags &= ~VM_MAYEXEC;
	if (vma->vm_flags & VM_SHARED)
		vma->vm_flags |= VM_MIXEDMAP;
	vma->vm_ops = &mf_vm_ops;
	vma->vm_private_data = m;
	mf_vma_open(vma);
	return 0;
}

static __attribute__((noipa)) void mf_scope_set(struct mf_mapping *m, struct mf_scope *scope)
{
	mf_write(m);
	m->scope = scope;
	mf_write_end(m);
}
static int mf_probe(struct file *file, struct mf_mapping *m, struct mf_probe *p)
{
	struct mf_scope scope = { .task = current, .mm = current->mm, .result = p };
	struct vm_area_struct *vma;
	unsigned int flags = FAULT_FLAG_ALLOW_RETRY | FAULT_FLAG_KILLABLE;
	vm_fault_t ret;
	int error = 0;
	if (!scope.mm || p->reserved || p->action > MF_REVALIDATE ||
	    !PAGE_ALIGNED(p->address) || p->address >= TASK_SIZE ||
	    m->features & (MF_PRIVATE | MF_WRITABLE))
		return -EOPNOTSUPP;
	if (atomic_cmpxchg(&m->probe_busy, 0, 1))
		return -EBUSY;
	if (p->action == MF_NOWAIT)
		flags |= FAULT_FLAG_RETRY_NOWAIT;
	mmget(scope.mm);
	atomic_set(&m->dropped, 0);
	atomic_set(&m->proceed, 0);
	atomic64_inc(&m->scopes);
	mf_scope_set(m, &scope);
	for (;;) {
		if (mmap_read_lock_killable(scope.mm)) {
			error = -EINTR;
			break;
		}
		scope.held = true;
		p->acquisitions++;
		/* Re-find and validate after every drop. Never reuse a VMA pointer,
		 * including when a new mapping now occupies the same user address. */
		vma = find_vma(scope.mm, p->address);
		if (!vma || p->address < vma->vm_start || vma->vm_file != file ||
		    vma->vm_ops != &mf_vm_ops || vma->vm_private_data != m ||
		    !(vma->vm_flags & VM_SHARED) || !(vma->vm_flags & VM_READ) ||
		    vma->vm_flags & (VM_WRITE | VM_EXEC)) {
			p->stale++;
			error = -ESTALE;
			break;
		}
		if (p->attempts)
			p->revalidated++;
		p->attempts++;
		ret = handle_mm_fault(vma, p->address, flags, NULL);
		vma = NULL;
		/* Flags verify the scope's explicit ownership transitions. They do
		 * not grant release authority or overwrite the exact held record. */
		if (ret & VM_FAULT_COMPLETED) {
			if (scope.held || !p->completed)
				error = -EUCLEAN;
			break;
		}
		if (ret & VM_FAULT_RETRY) {
			if (flags & FAULT_FLAG_RETRY_NOWAIT) {
				error = scope.held ? -EAGAIN : -EUCLEAN;
				break;
			}
			if (scope.held || p->attempts != 1 || p->pause_timeout) {
				error = -EUCLEAN;
				break;
			}
			flags |= FAULT_FLAG_TRIED;
			continue;
		}
		if (!scope.held)
			error = -EUCLEAN;
		else if (ret & VM_FAULT_ERROR)
			error = -EFAULT;
		break;
	}
	if (scope.held)
		mf_mm_release(&scope);
	p->final_held = scope.held;
	p->result = error;
	mf_scope_set(m, NULL);
	atomic64_inc(&m->scope_ends);
	mmput(scope.mm);
	atomic_set(&m->probe_busy, 0);
	return 0;
}

static __attribute__((noipa)) void mf_mutate(struct mf_mapping *m)
{
	mf_write(m);
	m->epoch++;
	m->complement = ~m->epoch;
	mf_write_end(m);
}
static int mf_downgrade(struct mf_mapping *m)
{
	if (!(m->features & MF_DOWNGRADE) || m->backend == MF_TC)
		return -EOPNOTSUPP;
	mf_write(m);
	m->epoch++;
	m->complement = ~m->epoch;
	atomic64_inc(&m->write_ends);
	if (!MF_TC_BUILD && m->backend == MF_KD)
		kd_downgrade_write(&m->lock.kd);
	else
		downgrade_write(&m->lock.native);
	atomic64_inc(&m->reads);
	atomic64_inc(&m->downgrades);
	if (m->complement != ~m->epoch)
		atomic64_inc(&m->data_errors);
	mf_read_end(m);
	return 0;
}
static long mf_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
	struct mf_file *f = file->private_data;
	struct mf_mapping *m = smp_load_acquire(&f->mapping);
	void __user *user = (void __user *)arg;
	int error;
	if (command == MF_CREATE) {
		struct mf_create c;
		if (copy_from_user(&c, user, sizeof(c)))
			return -EFAULT;
		error = mf_create(f, &c);
		return error ?: (copy_to_user(user, &c, sizeof(c)) ? -EFAULT : 0);
	}
	if (!m)
		return -EINVAL;
	if (command == MF_PROBE) {
		struct mf_probe p;
		if (copy_from_user(&p, user, sizeof(p)))
			return -EFAULT;
		/* Caller inputs are only address/action; zero observation fields. */
		if (p.result || p.attempts || p.acquisitions || p.releases || p.retries ||
		    p.nowait || p.completed || p.callbacks || p.revalidated || p.stale ||
		    p.pause_timeout || p.final_held)
			return -EINVAL;
		error = mf_probe(file, m, &p);
		return error ?: (copy_to_user(user, &p, sizeof(p)) ? -EFAULT : 0);
	}
	if (command == MF_MUTATE) {
		mf_mutate(m);
		return 0;
	}
	if (command == MF_DOWNGRADE_ONCE)
		return mf_downgrade(m);
	if (command == MF_WAIT_DROP)
		return wait_event_timeout(m->events, atomic_read(&m->dropped), 5 * HZ) ? 0 : -ETIMEDOUT;
	if (command == MF_RELEASE_DROP) {
		atomic_set(&m->proceed, 1);
		wake_up_all(&m->events);
		return 0;
	}
	if (command == MF_STATS) {
		struct mf_stats s = {
			.backend = m->backend, .features = m->features, .vmas = atomic_read(&m->vmas),
			.active_probe = atomic_read(&m->probe_busy), .epoch = READ_ONCE(m->epoch),
			.faults = atomic64_read(&m->faults), .reads = atomic64_read(&m->reads),
			.read_ends = atomic64_read(&m->read_ends), .writes = atomic64_read(&m->writes),
			.write_ends = atomic64_read(&m->write_ends), .downgrades = atomic64_read(&m->downgrades),
			.context_errors = atomic64_read(&m->context_errors), .data_errors = atomic64_read(&m->data_errors),
			.fallback = m->fallback, .scopes = atomic64_read(&m->scopes),
			.scope_ends = atomic64_read(&m->scope_ends),
			.lookup_sequence = READ_ONCE(m->lookup_sequence),
			.lookup_begins = atomic64_read(&m->lookup_begins),
			.lookup_ends = atomic64_read(&m->lookup_ends),
			.lookup_fallbacks = atomic64_read(&m->lookup_fallbacks),
			.lookup_candidates = atomic64_read(&m->lookup_candidates),
			.fault_lookups = atomic64_read(&m->fault_lookups),
		};
#if !MF_TC_BUILD
		if (m->backend == MF_KD) {
			s.entry = (unsigned long)mf_lookup_entry;
			s.gate = (unsigned long)&m->lock.kd.gate;
		}
#endif
		return copy_to_user(user, &s, sizeof(s)) ? -EFAULT : 0;
	}
	return -ENOTTY;
}

static const struct file_operations mf_fops = {
	.owner = THIS_MODULE, .open = mf_open, .release = mf_release,
	.mmap = mf_mmap, .unlocked_ioctl = mf_ioctl, .llseek = no_llseek,
};
static struct miscdevice mf_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mmap_fault", .fops = &mf_fops, .mode = 0600,
};
static int health_get(char *buffer, const struct kernel_param *parameter)
{
	return scnprintf(buffer, PAGE_SIZE, "files=%d destroyed=%lld release_errors=%lld\n",
		atomic_read(&files), atomic64_read(&destroyed), atomic64_read(&release_errors));
}
static const struct kernel_param_ops health_ops = { .get = health_get };
module_param_cb(health, &health_ops, NULL, 0400);
static int __init mf_init(void) { return misc_register(&mf_device); }
static void __exit mf_exit(void)
{
	WARN_ON_ONCE(atomic_read(&files) || atomic64_read(&release_errors));
	misc_deregister(&mf_device);
}
module_init(mf_init);
module_exit(mf_exit);
#if MF_TC_BUILD
MODULE_INFO(mmap_provider, "tclock");
#else
MODULE_INFO(mmap_provider, "kdlock");
#endif
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Opt-in local KD backing-state locks and origin-task mmap/fault transactions");
