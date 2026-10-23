/* SPDX-License-Identifier: GPL-2.0 */
/* Native move_vma invokes ->mremap with the real writer, after copying the
 * destination VMA and before do_munmap retires the source. The destination is
 * farther away, so the old source is still the nearest neighbor at publication.
 * This callback only gates scheduling: native mremap performs every VMA edit. */
static const struct vm_operations_struct neighbor_ops;

static u64 neighbor_owner(struct session *s)
{
	unsigned long owner = atomic_long_read(&s->mm->mmap_lock.kd.gate.owner);

	return !(owner & 4UL) ? owner & ~7UL : 0;
}

static int neighbor_leaf(struct session *s, unsigned long address, u64 *table)
{
	pte_t entry;
	int error = change_entry(s, address, &entry, table, true);

	return error ? error : pte_none(entry) ? 0 : -EINVAL;
}

static bool neighbor_nearest(struct session *s, struct vm_area_struct *vma)
{
	struct ub_neighbor_config *n = &s->neighbor.config;
	struct vm_area_struct *next;

	if (n->side) return find_vma(s->mm, n->target_end) == vma;
	next = find_vma(s->mm, vma->vm_end);
	return next && next->vm_start == n->target_start && next->vm_end == n->target_end;
}

static void neighbor_open(struct vm_area_struct *vma)
{
	struct session *s = vma->vm_private_data;

	atomic_inc(&s->neighbor_vmas);
}

static void neighbor_close(struct vm_area_struct *vma)
{
	struct session *s = vma->vm_private_data;
	struct ub_neighbor *r = &s->neighbor;
	struct vm_area_struct *replacement;

	atomic_dec(&s->neighbor_vmas);
	if (!r->armed || (unsigned long)vma != r->old_vma || vma->vm_start != r->config.old_address)
		return;
	/* Native source retirement follows the queued gate and still owns the
	 * writer. The typed body has not executed; no borrowed owner is released. */
	r->close_owner = neighbor_owner(s);
	r->close_pending = kd_mmap_unmap_pending(s->mm);
	r->tables_closed = mm_pgtables_bytes(s->mm);
	r->maps_closed = s->mm->map_count;
	r->pages_closed = s->mm->total_vm;
	replacement = vma_lookup(s->mm, r->config.new_address);
	check(s, r->queued && r->released && !r->retired && r->actor == current->pid &&
		kd_mmap_is_write_owner(&s->mm->mmap_lock) && r->close_owner == (unsigned long)current &&
		!atomic_long_read(&s->mm->mmap_lock.kd.readers) && r->close_pending == r->config.count &&
		replacement && (unsigned long)replacement == r->new_vma && neighbor_nearest(s, replacement) &&
		!vma_lookup(s->mm, r->config.old_address) &&
		!atomic64_read(&s->mm->mmap_lock.unmap.removed) && !atomic64_read(&s->mm->mmap_lock.unmap.handbacks));
	r->retired = 1;
	pr_info("KD_MM_NEIGHBOR retired mm=%px actor=%d owner=%llx old=%lx new=%llx pending=%llu readers=0 effects=0 tables=%llu maps=%llu pages=%llu\n",
		s->mm, current->pid, r->close_owner, (unsigned long)vma, r->new_vma,
		r->close_pending, r->tables_closed, r->maps_closed, r->pages_closed);
}

static int neighbor_mremap(struct vm_area_struct *vma)
{
	struct session *s = vma->vm_private_data;
	struct ub_neighbor *r = &s->neighbor;
	struct vm_area_struct *old;
	unsigned long until;
	unsigned int i;
	int error = -EINVAL;

	if (current->mm != s->mm || !r->armed || r->queued ||
	    vma->vm_start != r->config.new_address || vma->vm_end != vma->vm_start + PAGE_SIZE ||
	    atomic_cmpxchg(&s->controlling, 0, 1)) return -EINVAL;
	old = vma_lookup(s->mm, r->config.old_address);
	if (!old || (unsigned long)old != r->old_vma || !neighbor_nearest(s, old) ||
	    !kd_mmap_is_write_owner(&s->mm->mmap_lock) || neighbor_owner(s) != (unsigned long)current ||
	    atomic_long_read(&s->mm->mmap_lock.kd.readers) ||
	    atomic_long_read(&s->mm->mmap_lock.kd.admission) != -1 ||
	    s->mm->map_count != r->maps_before + 1 || s->mm->total_vm != r->pages_before)
		goto out;
	r->actor = current->pid; r->owner = neighbor_owner(s);
	r->new_vma = (unsigned long)vma; r->new_flags = vma->vm_flags;
	if (r->old_vma == r->new_vma || r->old_flags != r->new_flags || r->pgoff != vma->vm_pgoff) goto out;
	atomic_set(&s->held, 1);
	if (r->config.cancel) {
		struct control *c = kzalloc(sizeof(*c), GFP_KERNEL);

		if (!c) { error = -ENOMEM; goto out; }
		c->session = s; s->neighbor_cancel = c;
		s->partial_cancel = r->config.offset + 1;
		for (i = 0; i < 2; i++) {
			error = start(c, &c->writers[i], i, false);
			if (error) goto out;
			s->result.cancel_tid[i] = c->writers[i].task->pid;
			if (!wait_pending(s, i + 1)) { error = -ETIMEDOUT; goto out; }
		}
		check(s, !send_sig(SIGUSR1, c->writers[1].task, 1));
		msleep(20); check(s, !completion_done(&c->writers[1].done));
		check(s, !send_sig(SIGKILL, c->writers[1].task, 1));
		msleep(20); check(s, !completion_done(&c->writers[1].done));
	} else if (r->config.count && !wait_pending(s, r->config.count)) {
		error = -ETIMEDOUT; goto out;
	}
	r->pending = kd_mmap_unmap_pending(s->mm);
	r->readers = atomic_long_read(&s->mm->mmap_lock.kd.readers);
	r->admission = atomic_long_read(&s->mm->mmap_lock.kd.admission);
	r->tables_queued = mm_pgtables_bytes(s->mm); r->maps_queued = s->mm->map_count;
	check(s, r->pending == r->config.count && !r->readers && r->admission == -1 &&
		neighbor_owner(s) == r->owner && neighbor_nearest(s, old) &&
		!atomic64_read(&s->mm->mmap_lock.unmap.removed) && !atomic64_read(&s->mm->mmap_lock.unmap.handbacks));
	r->queued = 1;
	pr_info("KD_MM_NEIGHBOR queued mm=%px actor=%llu owner=%llx old=%llx new=%llx old_start=%llx new_start=%llx side=%llu loss=%llu pending=%llu readers=%llu admission=%lld tables=%llu\n",
		s->mm, r->actor, r->owner, r->old_vma, r->new_vma, r->config.old_address,
		r->config.new_address, r->config.side, r->config.loss, r->pending, r->readers, r->admission, r->tables_queued);
	atomic_set(&s->ready, 1);
	until = jiffies + 20 * HZ;
	while (!atomic_read(&s->release) && time_before(jiffies, until)) msleep(1);
	error = atomic_read(&s->release) ? 0 : -ETIMEDOUT;
	if (!error) r->released = 1;
out:
	r->result = error;
	atomic_set(&s->ready, 0); atomic_set(&s->held, 0);
	/* Native mremap still owns the writer here. Its successful continuation
	 * retires old, then unlocks; an error uses its normal relocation rollback. */
	return error;
}

static vm_fault_t neighbor_fault(struct vm_fault *vmf)
{
	struct session *s = vmf->vma->vm_private_data;

	if ((vmf->flags & FAULT_FLAG_WRITE) || !s->neighbor_page) return VM_FAULT_SIGBUS;
	atomic_inc(&s->neighbor_faults);
	return vmf_insert_page(vmf->vma, vmf->address, s->neighbor_page);
}

static const struct vm_operations_struct neighbor_ops = {
	.open = neighbor_open, .close = neighbor_close, .mremap = neighbor_mremap, .fault = neighbor_fault,
};

static int neighbor_mmap(struct file *file, struct vm_area_struct *vma)
{
	struct session *s = file->private_data;

	if (current->mm != s->mm || vma->vm_end - vma->vm_start != PAGE_SIZE ||
	    (vma->vm_flags & (VM_WRITE | VM_SHARED)) || s->groups || atomic_read(&s->controlling)) return -EINVAL;
	if (!s->neighbor_page) {
		s->neighbor_page = alloc_page(GFP_KERNEL | __GFP_ZERO);
		if (!s->neighbor_page) return -ENOMEM;
	}
	vma->vm_flags |= VM_MIXEDMAP | VM_DONTEXPAND | VM_DONTDUMP | VM_NOHUGEPAGE;
	vma->vm_flags &= ~VM_MAYWRITE;
	vma->vm_ops = &neighbor_ops; vma->vm_private_data = s;
	neighbor_open(vma);
	return 0;
}

static int neighbor_operation(struct session *s, unsigned int cmd, unsigned long arg)
{
	struct ub_neighbor *r = &s->neighbor;
	int error = 0;

	if (cmd == UB_NEIGHBOR_ARM) {
		struct ub_neighbor_config config;
		struct vm_area_struct *old;
		unsigned int group = s->mm->mmap_lock.unmap.enabled ? 1 : 0;

		if (copy_from_user(&config, (void __user *)arg, sizeof(config))) return -EFAULT;
		if (r->armed || s->change_armed || atomic_read(&s->controlling) || config.side > 1 || config.loss > 1 ||
		    config.cancel > 1 || (config.offset != 0 && config.offset != 2) ||
		    (config.cancel && (config.loss || !s->mm->mmap_lock.unmap.enabled)) ||
		    config.target_start != target(s, group * 3) || config.target_end != config.target_start + 3 * PAGE_SIZE ||
		    config.old_address != config.target_start + (config.side ? 4 * PAGE_SIZE : -2 * PAGE_SIZE) ||
		    config.new_address != config.old_address + (config.side ? 1 : -1) * (config.loss ? PMD_SIZE : PAGE_SIZE) ||
		    config.count != (s->mm->mmap_lock.unmap.enabled ? config.cancel || config.loss || s->mm->mmap_lock.unmap.test_fail_after ? 2 : 3 : 0)) return -EINVAL;
		mmap_read_lock(s->mm);
		old = vma_lookup(s->mm, config.old_address);
		if (!old || old->vm_start != config.old_address || old->vm_end != config.old_address + PAGE_SIZE ||
		    old->vm_ops != &neighbor_ops || vma_lookup(s->mm, config.new_address)) error = -EINVAL;
		else {
			r->config = config; r->old_vma = (unsigned long)old;
			r->old_flags = old->vm_flags; r->pgoff = old->vm_pgoff;
			r->tables_before = mm_pgtables_bytes(s->mm); r->maps_before = s->mm->map_count; r->pages_before = s->mm->total_vm;
			error = neighbor_leaf(s, config.old_address, &r->old_table);
			if (!error) error = neighbor_leaf(s, config.new_address, &r->destination_table);
			if (!error && !neighbor_nearest(s, old)) error = -EINVAL;
			if (!error) r->armed = 1;
		}
		mmap_read_unlock(s->mm);
	} else if (cmd == UB_NEIGHBOR_PROBE) {
		bool read, write;

		if (!atomic_read(&s->held) || r->probe_actor) return -EINVAL;
		read = mmap_read_trylock(s->mm);
		if (read) mmap_read_unlock(s->mm);
		write = mmap_write_trylock(s->mm);
		if (write) mmap_write_unlock(s->mm);
		r->probe_actor = current->pid; r->reader_blocked = !read; r->writer_blocked = !write;
		check(s, !read && !write && neighbor_owner(s) == r->owner && r->owner != (unsigned long)current);
	} else if (cmd == UB_NEIGHBOR_FINISH) {
		unsigned int i;

		if (!r->released || !r->retired || r->result) return -EINVAL;
		if (s->neighbor_cancel) {
			struct control *c = s->neighbor_cancel;

			for (i = 0; i < 2; i++) if (!join(&c->writers[i])) return -EBUSY;
			mmap_read_lock(s->mm);
			for (i = 0; i < 2; i++) {
				s->result.cancel_result[i] = c->writers[i].result;
				s->result.cancel_mapped[i] = !!vma_lookup(s->mm, target(s, i * 3 + r->config.offset));
				check(s, c->writers[i].result == (i ? -EINTR : 0) && s->result.cancel_mapped[i] == !!i);
			}
			mmap_read_unlock(s->mm); kfree(c); s->neighbor_cancel = NULL; s->partial_cancel = 0;
		}
		atomic_set(&s->controlling, 0);
	} else {
		struct ub_neighbor snapshot = *r;

		snapshot.vmas = atomic_read(&s->neighbor_vmas); snapshot.faults = atomic_read(&s->neighbor_faults);
		snapshot.page_refs = s->neighbor_page ? page_count(s->neighbor_page) : 0;
		snapshot.page_maps = s->neighbor_page ? page_mapcount(s->neighbor_page) : 0;
		if (copy_to_user((void __user *)arg, &snapshot, sizeof(snapshot))) error = -EFAULT;
	}
	return error;
}
