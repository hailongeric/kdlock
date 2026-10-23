/* SPDX-License-Identifier: GPL-2.0 */
/* Test-only state transition through native GUP (get_user_pages). No production
 * delegation hook or synthetic unmap callback: the body is still real munmap. */
static int change_entry(struct session *s, unsigned long address, pte_t *entry)
{
	pgd_t *pgd = pgd_offset(s->mm, address);
	p4d_t *p4d; pud_t *pud; pmd_t *pmd; pte_t *pte;
	spinlock_t *ptl;

	mmap_assert_locked(s->mm);
	if (pgd_none(*pgd) || pgd_bad(*pgd)) return -EINVAL;
	p4d = p4d_offset(pgd, address);
	if (p4d_none(*p4d) || p4d_bad(*p4d)) return -EINVAL;
	pud = pud_offset(p4d, address);
	if (pud_none(*pud) || pud_bad(*pud) || pud_trans_huge(*pud) || pud_devmap(*pud)) return -EINVAL;
	pmd = pmd_offset(pud, address);
	if (pmd_none(*pmd) || pmd_bad(*pmd) || pmd_trans_huge(*pmd) || pmd_devmap(*pmd)) return -EINVAL;
	pte = pte_offset_map_lock(s->mm, pmd, address, &ptl);
	*entry = ptep_get(pte);
	pte_unmap_unlock(pte, ptl);
	return 0;
}

static int change_target(struct session *s)
{
	struct ub_change *r = &s->change;
	unsigned int i = r->index, b;
	unsigned long address = target(s, i);
	struct page *page = NULL;
	struct pagevec drain;
	unsigned char *bytes, value = 1 + i;
	u64 hash = 1469598103934665603ULL;
	pte_t entry;
	long got;
	int error;

	/* The existing share remains held throughout. The native get_user_pages
	 * wrapper passes locked=NULL, so it cannot drop/reacquire mmap_lock on a
	 * retry. Unlike the unlocked wrapper, it makes no new reader admission. */
	mmap_assert_locked(s->mm);
	mutex_lock(&s->pins_lock);
	r->actor = current->pid;
	r->pending = kd_mmap_unmap_pending(s->mm);
	r->readers = atomic_long_read(&s->mm->mmap_lock.kd.readers);
	r->admission = atomic_long_read(&s->mm->mmap_lock.kd.admission);
	error = -EINVAL;
	if (!s->change_armed || r->done || s->pages[i] || current->mm != s->mm ||
	    (s->mm->mmap_lock.unmap.enabled ?
	     r->pending != 3 || r->readers != 2 || r->admission != -1 :
	     r->pending != 0 || r->readers != 1)) goto out;
	error = change_entry(s, address, &entry);
	if (error) goto out;
	if (!pte_present(entry) || !pte_special(entry) || pte_write(entry) ||
	    pte_protnone(entry) || pte_devmap(entry) || !is_zero_pfn(pte_pfn(entry))) {
		error = -EINVAL; goto out;
	}
	r->before_zero = 1; r->zero_pfn = pte_pfn(entry);
	got = get_user_pages(address, 1, FOLL_WRITE, &page, NULL);
	if (got != 1) { error = got < 0 ? got : -EFAULT; goto out; }
	/* Own only the NEW private page. Even on a later observation failure,
	 * the session retains and retires this exact GUP reference. */
	s->pages[i] = page; s->pin_mask |= 1U << i;
	s->charges[i] = READ_ONCE(page->memcg_data);
	get_page(page); pagevec_init(&drain); pagevec_add(&drain, page); pagevec_release(&drain);
	error = change_entry(s, address, &entry);
	if (error) goto out;
	if (!pte_present(entry) || !pte_write(entry) || pte_special(entry) ||
	    pte_devmap(entry) || pte_pfn(entry) != page_to_pfn(page) ||
	    is_zero_pfn(pte_pfn(entry)) || !PageAnon(page) || !PageAnonExclusive(page) ||
	    page_mapcount(page) != 1 || page_count(page) != 2) { error = -EINVAL; goto out; }
	bytes = kmap_local_page(page);
	for (b = 0; b < PAGE_SIZE; b++) {
		check(s, !bytes[b]); bytes[b] = value;
		hash = (hash ^ bytes[b]) * 1099511628211ULL;
	}
	kunmap_local(bytes);
	r->after_private = 1;
	r->page = (struct ub_page) { address, page_to_pfn(page), hash, page_mapcount(page),
		page_count(page), 1, value, PageLocked(page) };
	error = 0;
out:
	r->result = error; r->done = 1;
	pr_info("KD_MM_TEST target_change mm=%px index=%u actor=%llu pending=%llu readers=%llu admission=%lld zero_pfn=%llx private_pfn=%llx before_zero=%llu after_private=%llu result=%d\n",
		s->mm, i, r->actor, r->pending, r->readers, r->admission, r->zero_pfn,
		r->page.pfn, r->before_zero, r->after_private, error);
	mutex_unlock(&s->pins_lock);
	return error;
}

static int change_operation(struct session *s, unsigned int cmd, unsigned long arg)
{
	int error = 0;

	if (atomic_read(&s->controlling)) return -EBUSY;
	if (cmd == UB_CHANGE_ARM) {
		mutex_lock(&s->pins_lock);
		if (!s->groups || arg >= s->groups * 3 || s->pages[arg] || s->change_armed ||
		    (s->mm->mmap_lock.unmap.enabled ? s->groups != 3 || arg != 4 : s->groups != 1 || arg != 1))
			error = -EINVAL;
		else { s->change.index = arg; s->change_armed = true; }
		mutex_unlock(&s->pins_lock);
	} else if (cmd == UB_CHANGE_NOW) {
		if (s->mm->mmap_lock.unmap.enabled) return -EINVAL;
		mmap_read_lock(s->mm); error = change_target(s); mmap_read_unlock(s->mm);
	} else {
		if (!s->change.done) return -EAGAIN;
		if (copy_to_user((void __user *)arg, &s->change, sizeof(s->change))) error = -EFAULT;
	}
	return error;
}
