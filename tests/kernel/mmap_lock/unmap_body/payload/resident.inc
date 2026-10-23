/* SPDX-License-Identifier: GPL-2.0 */
/* Exact test references and read-only reverse-map observations. This code does
 * not supply a body: callers still enter the real munmap/vm_munmap functions. */
static int experiment(struct session *s, unsigned long arg)
{
	struct ub_experiment e;
	struct kd_mmap_unmap_state *u = &s->mm->mmap_lock.unmap;
	int error = 0;

	if (copy_from_user(&e, (void __user *)arg, sizeof(e))) return -EFAULT;
	if (e.mode > 2 || !e.groups || e.groups > 3 || e.fail_after > 2 ||
	    !e.region.start || e.region.end <= e.region.start ||
	    ((e.region.start | e.region.end | e.region.base | e.region.stride) & ~PAGE_MASK) ||
	    e.region.base < e.region.start || e.region.base >= e.region.end ||
	    e.region.stride < 16 * PAGE_SIZE ||
	    e.groups > (e.region.end - e.region.base) / e.region.stride + 1)
		return -EINVAL;
	mmap_write_lock(s->mm);
	if (u->enabled || u->test_fail_after || u->test_fail_seen || s->groups) error = -EBUSY;
	else if (e.mode == 2) error = kd_mmap_unmap_resident_partial_enable(s->mm, e.region.start, e.region.end);
	else if (e.mode == 1) error = kd_mmap_unmap_enable(s->mm, e.region.start, e.region.end);
	else { u->start = e.region.start; u->end = e.region.end; }
	if (!error) {
		s->region = e.region; s->groups = e.groups;
		u->test_fail_after = e.fail_after;
	}
	mmap_write_unlock(s->mm);
	return error;
}

static int rmap_state(struct session *s, unsigned long arg)
{
	struct ub_rmap r;
	struct vm_area_struct *vma;
	struct anon_vma_chain *avc;
	struct rb_node *node;

	if (copy_from_user(&r, (void __user *)arg, sizeof(r))) return -EFAULT;
	r.anon = r.root = r.link = r.links = r.active = r.refs = r.intervals = 0;
	mmap_read_lock(s->mm);
	vma = vma_lookup(s->mm, r.address);
	if (vma && vma->anon_vma) {
		struct anon_vma *anon = vma->anon_vma;

		anon_vma_lock_read(anon);
		r.anon = (unsigned long)anon; r.root = (unsigned long)anon->root;
		r.active = anon->num_active_vmas; r.refs = atomic_read(&anon->refcount);
		list_for_each_entry(avc, &vma->anon_vma_chain, same_vma) {
			r.link = (unsigned long)avc; r.links++;
			check(s, avc->vma == vma && avc->anon_vma == anon);
		}
		for (node = rb_first(&anon->rb_root.rb_root); node; node = rb_next(node)) {
			avc = rb_entry(node, struct anon_vma_chain, rb);
			check(s, avc->anon_vma == anon && avc->vma->vm_start < avc->vma->vm_end);
			r.intervals++;
		}
		anon_vma_unlock_read(anon);
	}
	mmap_read_unlock(s->mm);
	return copy_to_user((void __user *)arg, &r, sizeof(r)) ? -EFAULT : 0;
}

static unsigned long target(struct session *s, unsigned int i)
{
	return s->region.base + (i / 3) * s->region.stride + (i % 3) * PAGE_SIZE;
}

static unsigned int pins_owned(struct session *s)
{
	unsigned int i, n = 0;
	for (i = 0; i < UB_EXT_PAGES; i++) n += !!s->pages[i];
	return n;
}

static void drop_pins(struct session *s)
{
	unsigned int i;
	if (s->busy_page) { unlock_page(s->busy_page); s->busy_page = NULL; }
	for (i = 0; i < UB_EXT_PAGES; i++) {
		struct page *page = s->pages[i];
		if (!page) continue;
		s->pages[i] = NULL; put_page(page); s->pins_released++;
	}
}

static int page_operation(struct session *s, unsigned int cmd, unsigned long arg)
{
	unsigned int i, n = s->groups * 3;
	int error = 0;

	mutex_lock(&s->pins_lock);
	if (!n || atomic_read(&s->controlling)) { error = -EBUSY; goto out; }
	if (cmd == UB_PIN) {
		struct pagevec scratch;

		if (pins_owned(s)) { error = -EBUSY; goto out; }
		mmap_read_lock(s->mm);
		for (i = 0; i < n; i++) {
			long got = get_user_pages(target(s, i), 1, FOLL_WRITE, &s->pages[i], NULL);
			if (got != 1) { s->pages[i] = NULL; error = got < 0 ? got : -EFAULT; break; }
			s->charges[i] = READ_ONCE(s->pages[i]->memcg_data);
		}
		mmap_read_unlock(s->mm);
		/* Same exported drain as the preserved resident whole-VMA probe. */
		pagevec_init(&scratch);
		for (i = 0; i < n; i++) {
			if (!s->pages[i]) continue;
			get_page(s->pages[i]);
			if (!pagevec_add(&scratch, s->pages[i])) pagevec_release(&scratch);
		}
		pagevec_release(&scratch);
		if (error) drop_pins(s);
	} else if (cmd == UB_PAGESTATE) {
		if (pins_owned(s) != n) { error = -EINVAL; goto out; }
		s->snapshot.count = n;
		for (i = 0; i < n; i++) {
			struct page *page = s->pages[i];
			unsigned char *bytes = kmap_local_page(page), value = 1 + i;
			u64 hash = 1469598103934665603ULL;
			unsigned int b;

			for (b = 0; b < PAGE_SIZE; b++) {
				check(s, bytes[b] == value); hash = (hash ^ bytes[b]) * 1099511628211ULL;
			}
			kunmap_local(bytes);
			s->snapshot.page[i] = (struct ub_page) { target(s, i), page_to_pfn(page), hash,
				page_mapcount(page), page_count(page), READ_ONCE(page->memcg_data) == s->charges[i], value, PageLocked(page) };
			check(s, s->snapshot.page[i].charged_same);
		}
		if (copy_to_user((void __user *)arg, &s->snapshot, sizeof(s->snapshot))) error = -EFAULT;
	} else if (cmd == UB_BUSY_LOCK) {
		if (s->groups != 3 || s->busy_page || !s->pages[5] || !trylock_page(s->pages[5])) { error = -EBUSY; goto out; }
		s->busy_page = s->pages[5];
	} else if (cmd == UB_BUSY_UNLOCK) {
		if (!s->busy_page) { error = -EINVAL; goto out; }
		unlock_page(s->busy_page); s->busy_page = NULL;
	} else {
		if (!kd_mmap_is_idle(&s->mm->mmap_lock)) { error = -EBUSY; goto out; }
		for (i = 0; i < n; i++)
			if (s->pages[i] && (cmd == UB_UNPIN_MAPPED ?
			    page_mapcount(s->pages[i]) != 1 || page_count(s->pages[i]) != 2 :
			    page_mapped(s->pages[i]) || page_count(s->pages[i]) != 1)) { error = -EBUSY; goto out; }
		rcu_barrier(); drop_pins(s);
	}
out:
	mutex_unlock(&s->pins_lock);
	return error;
}
