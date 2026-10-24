/* SPDX-License-Identifier: GPL-2.0 */
/* Test-only state transition through native GUP (get_user_pages). No production
 * delegation hook or synthetic unmap callback: the body is still real munmap. */
static int change_entry(struct session *s, unsigned long address, pte_t *entry, u64 *table, bool allow_missing)
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
	if (allow_missing) {
		ptl = pmd_lock(s->mm, pmd);
		if (pmd_none(*pmd)) {
			*table = 0; *entry = __pte(0);
			spin_unlock(ptl); return 0;
		}
		spin_unlock(ptl);
	}
	if (pmd_none(*pmd) || pmd_bad(*pmd) || pmd_trans_huge(*pmd) || pmd_devmap(*pmd)) return -EINVAL;
	pte = pte_offset_map_lock(s->mm, pmd, address, &ptl);
	*entry = ptep_get(pte);
	*table = pmd_pfn(READ_ONCE(*pmd));
	pte_unmap_unlock(pte, ptl);
	return 0;
}

static int change_target(struct session *s)
{
	struct ub_change_more *more = &s->change;
	struct ub_change *r = &more->state;
	unsigned int i = r->index, b;
	bool missing = (more->mode >= 3 && more->mode <= 6) || more->mode >= 16;
	unsigned long address = target(s, i);
	struct page *page = NULL;
	struct vm_area_struct *vma;
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
	if (!s->change_armed || r->done ||
	    (more->mode == 10 ? !s->pages[i] || s->busy_page : !!s->pages[i]) || current->mm != s->mm ||
	    (s->mm->mmap_lock.unmap.enabled ?
	     r->pending != (more->mode >= 6 && more->mode != 11 && more->mode != 13 && more->mode != 14 && !(more->mode >= 16 && more->mode <= 18) ? 2 : 3) || r->readers != 2 || r->admission != -1 :
	     r->pending != 0 || r->readers != 1)) goto out;
	vma = vma_lookup(s->mm, address);
	if (!vma) goto out;
	more->anon_before = (unsigned long)vma->anon_vma;
	error = change_entry(s, address, &entry, &more->table_before, missing);
	if (error) goto out;
	if (more->mode == 10) {
		pte_t after;

		/* Change eligibility after publication using an already held local
		 * read share. Retain the original probe reference; do not fault,
		 * replace the PTE or fabricate a delegation body. Native handback
		 * may unmap this locked page; the probe unlocks before dropping it. */
		page = s->pages[i];
		if (!pte_present(entry) || !pte_write(entry) || pte_special(entry) ||
		    pte_devmap(entry) || pte_pfn(entry) != page_to_pfn(page) ||
		    !PageAnon(page) || !PageAnonExclusive(page) || PageCompound(page) ||
		    page_mapcount(page) != 1 || page_count(page) != 2 || !trylock_page(page)) {
			error = -EINVAL; goto out;
		}
		s->busy_page = page;
		error = change_entry(s, address, &after, &more->table_after, false);
		if (error) goto out;
		if (!pte_same(pte_mkold(entry), pte_mkold(after))) { error = -EINVAL; goto out; }
		bytes = kmap_local_page(page);
		for (b = 0; b < PAGE_SIZE; b++) {
			check(s, bytes[b] == value); hash = (hash ^ bytes[b]) * 1099511628211ULL;
		}
		kunmap_local(bytes);
		r->after_private = 1;
		r->page = (struct ub_page) { address, page_to_pfn(page), hash, page_mapcount(page),
			page_count(page), READ_ONCE(page->memcg_data) == s->charges[i], value, PageLocked(page) };
		goto completed;
	}
	if (missing) {
		/* No target leaf exists. Keep before_none=0 to avoid claiming a
		 * real empty PTE; the table-change receipt names this distinction. */
		if (more->table_before) { error = -EINVAL; goto out; }
	} else if (more->mode && more->mode != 9 && more->mode != 11 && more->mode != 12) {
		if (!pte_none(entry)) { error = -EINVAL; goto out; }
		more->before_none = 1;
	} else {
		if (!pte_present(entry) || !pte_special(entry) || pte_write(entry) ||
		    pte_protnone(entry) || pte_devmap(entry) || !is_zero_pfn(pte_pfn(entry))) {
			error = -EINVAL; goto out;
		}
		r->before_zero = 1; r->zero_pfn = pte_pfn(entry);
	}
	if (more->mode == 1 || more->mode == 3 || more->mode == 4 || more->mode == 6 || more->mode == 7 || more->mode == 13 || more->mode == 16 || more->mode == 17) {
		/* No pages[] and no FOLL_GET: a real native read fault, with no
		 * reference or ownership acquired on the permanent shared zero page. */
		got = get_user_pages(more->mode == 3 ? address - 3 * PAGE_SIZE : address, 1, 0, NULL, NULL);
		if (got != 1) { error = got < 0 ? got : -EFAULT; goto out; }
		error = change_entry(s, address, &entry, &more->table_after, false);
		if (error) goto out;
		if (more->mode == 3) {
			/* Fault the existing left-neighbor VMA, not any target-VMA slot. */
			if (!pte_none(entry)) { error = -EINVAL; goto out; }
			goto completed;
		}
		if (!pte_present(entry) || !pte_special(entry) || pte_write(entry) ||
		    pte_protnone(entry) || pte_devmap(entry) || !is_zero_pfn(pte_pfn(entry))) {
			error = -EINVAL; goto out;
		}
		more->after_zero = 1; r->zero_pfn = pte_pfn(entry);
		goto completed;
	}
	got = get_user_pages(address, 1, FOLL_WRITE, &page, NULL);
	if (got != 1) { error = got < 0 ? got : -EFAULT; goto out; }
	/* Own only the NEW private page. Even on a later observation failure,
	 * the session retains and retires this exact GUP reference. */
	s->pages[i] = page; s->pin_mask |= 1U << i;
	s->charges[i] = READ_ONCE(page->memcg_data);
	get_page(page); pagevec_init(&drain); pagevec_add(&drain, page); pagevec_release(&drain);
	error = change_entry(s, address, &entry, &more->table_after, false);
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
	/* Modes 12/15/19 retain exactly the new GUP reference and change only page-lock
	 * eligibility. Native handback may unmap it; the probe unlocks before put. */
	if (more->mode == 12 || more->mode == 15 || more->mode == 19) {
		if (s->busy_page || !trylock_page(page)) { error = -EINVAL; goto out; }
		s->busy_page = page;
	}
	r->after_private = 1;
	r->page = (struct ub_page) { address, page_to_pfn(page), hash, page_mapcount(page),
		page_count(page), 1, value, PageLocked(page) };
completed:
	more->anon_after = (unsigned long)vma->anon_vma;
	error = more->table_after && (missing ? !more->table_before :
		more->table_before == more->table_after) ? 0 : -EINVAL;
out:
	r->result = error; r->done = 1;
	if (more->mode == 10)
		pr_info("KD_MM_TEST edge_private_busy mm=%px index=%u actor=%llu pending=%llu readers=%llu admission=%lld mode=10 before_locked=0 after_locked=%llu table_before=%llx table_after=%llx anon_before=%llx anon_after=%llx private_pfn=%llx refs=%llu mapcount=%llu result=%d\n",
			s->mm, i, r->actor, r->pending, r->readers, r->admission, r->page.locked,
			more->table_before, more->table_after, more->anon_before, more->anon_after,
			r->page.pfn, r->page.refs, r->page.mapcount, error);
	else if (more->mode >= 16)
		pr_info("KD_MM_TEST shared_table_change mm=%px index=%u actor=%llu pending=%llu readers=%llu admission=%lld mode=%llu before_table_none=1 after_zero=%llu after_private=%llu table_before=%llx table_after=%llx anon_before=%llx anon_after=%llx zero_pfn=%llx private_pfn=%llx refs=%llu mapcount=%llu locked=%llu result=%d\n",
			s->mm, i, r->actor, r->pending, r->readers, r->admission, more->mode,
			more->after_zero, r->after_private, more->table_before, more->table_after,
			more->anon_before, more->anon_after, r->zero_pfn, r->page.pfn,
			r->page.refs, r->page.mapcount, r->page.locked, error);
	else if (missing)
		pr_info("KD_MM_TEST table_change mm=%px index=%u actor=%llu pending=%llu readers=%llu admission=%lld mode=%llu before_table_none=1 after_zero=%llu after_private=%llu table_before=%llx table_after=%llx anon_before=%llx anon_after=%llx zero_pfn=%llx private_pfn=%llx result=%d\n",
			s->mm, i, r->actor, r->pending, r->readers, r->admission, more->mode,
			more->after_zero, r->after_private, more->table_before, more->table_after,
			more->anon_before, more->anon_after, r->zero_pfn, r->page.pfn, error);
	else if (more->mode == 13 || more->mode == 14 || more->mode == 15)
		pr_info("KD_MM_TEST shared_empty_change mm=%px index=%u actor=%llu pending=%llu readers=%llu admission=%lld mode=%llu before_none=%llu before_zero=0 after_zero=%llu after_private=%llu table_before=%llx table_after=%llx anon_before=%llx anon_after=%llx zero_pfn=%llx private_pfn=%llx refs=%llu mapcount=%llu locked=%llu result=%d\n",
			s->mm, i, r->actor, r->pending, r->readers, r->admission, more->mode,
			more->before_none, more->after_zero, r->after_private,
			more->table_before, more->table_after, more->anon_before, more->anon_after,
			r->zero_pfn, r->page.pfn, r->page.refs, r->page.mapcount, r->page.locked, error);
	else if (more->mode == 11 || more->mode == 12)
		pr_info("KD_MM_TEST shared_zero_change mm=%px index=%u actor=%llu pending=%llu readers=%llu admission=%lld mode=%llu before_zero=%llu after_private=%llu table_before=%llx table_after=%llx anon_before=%llx anon_after=%llx zero_pfn=%llx private_pfn=%llx refs=%llu mapcount=%llu locked=%llu result=%d\n",
			s->mm, i, r->actor, r->pending, r->readers, r->admission, more->mode,
			r->before_zero, r->after_private, more->table_before, more->table_after,
			more->anon_before, more->anon_after, r->zero_pfn, r->page.pfn,
			r->page.refs, r->page.mapcount, r->page.locked, error);
	else if (more->mode == 9)
		pr_info("KD_MM_TEST edge_zero_change mm=%px index=%u actor=%llu pending=%llu readers=%llu admission=%lld mode=9 before_none=0 before_zero=%llu after_zero=0 after_private=%llu table_before=%llx table_after=%llx anon_before=%llx anon_after=%llx zero_pfn=%llx private_pfn=%llx result=%d\n",
			s->mm, i, r->actor, r->pending, r->readers, r->admission, r->before_zero,
			r->after_private, more->table_before, more->table_after,
			more->anon_before, more->anon_after, r->zero_pfn, r->page.pfn, error);
	else if (more->mode)
		pr_info("KD_MM_TEST %s mm=%px index=%u actor=%llu pending=%llu readers=%llu admission=%lld mode=%llu before_none=%llu after_zero=%llu after_private=%llu table_before=%llx table_after=%llx anon_before=%llx anon_after=%llx zero_pfn=%llx private_pfn=%llx result=%d\n",
			more->mode >= 7 ? "edge_empty_change" : "absent_change", s->mm, i, r->actor, r->pending, r->readers, r->admission, more->mode,
			more->before_none, more->after_zero, r->after_private, more->table_before,
			more->table_after, more->anon_before, more->anon_after, r->zero_pfn, r->page.pfn, error);
	else
		pr_info("KD_MM_TEST target_change mm=%px index=%u actor=%llu pending=%llu readers=%llu admission=%lld zero_pfn=%llx private_pfn=%llx before_zero=%llu after_private=%llu result=%d\n",
			s->mm, i, r->actor, r->pending, r->readers, r->admission, r->zero_pfn,
			r->page.pfn, r->before_zero, r->after_private, error);
	mutex_unlock(&s->pins_lock);
	return error;
}

static int change_operation(struct session *s, unsigned int cmd, unsigned long arg)
{
	int error = 0;
	struct ub_change *r = &s->change.state;
	bool interior = cmd == UB_CHANGE_INTERIOR_TABLE_ARM;
	bool busy = cmd == UB_CHANGE_EDGE_PRIVATE_BUSY_ARM;
	bool near = cmd == UB_CHANGE_SHARED_MISSING_NEAR_ARM;
	bool edge = interior || cmd == UB_CHANGE_EDGE_TABLE_ARM || cmd == UB_CHANGE_EDGE_EMPTY_ZERO_ARM ||
		cmd == UB_CHANGE_EDGE_EMPTY_PRIVATE_ARM || cmd == UB_CHANGE_EDGE_ZERO_PRIVATE_ARM || busy ||
		cmd == UB_CHANGE_SHARED_ZERO_PRIVATE_ARM || cmd == UB_CHANGE_SHARED_ZERO_BUSY_ARM ||
		cmd == UB_CHANGE_SHARED_EMPTY_ZERO_ARM || cmd == UB_CHANGE_SHARED_EMPTY_PRIVATE_ARM ||
		cmd == UB_CHANGE_SHARED_EMPTY_BUSY_ARM || near ||
		cmd == UB_CHANGE_SHARED_MISSING_ZERO_ARM || cmd == UB_CHANGE_SHARED_MISSING_PRIVATE_ARM ||
		cmd == UB_CHANGE_SHARED_MISSING_BUSY_ARM;

	if (atomic_read(&s->controlling)) return -EBUSY;
	if (cmd == UB_CHANGE_ARM || cmd == UB_CHANGE_EMPTY_ZERO_ARM || cmd == UB_CHANGE_EMPTY_PRIVATE_ARM ||
	    cmd == UB_CHANGE_TABLE_EMPTY_ARM || cmd == UB_CHANGE_TABLE_ZERO_ARM || cmd == UB_CHANGE_TABLE_PRIVATE_ARM ||
	    edge) {
		mutex_lock(&s->pins_lock);
		if (!s->groups || arg >= s->groups * 3 || (busy ? !s->pages[arg] || s->busy_page : !!s->pages[arg]) || s->change_armed ||
		    (s->mm->mmap_lock.unmap.enabled ? s->groups != 3 ||
		     (edge && !near && !interior ? arg != 3 && arg != 5 : arg != 4) : s->groups != 1 ||
		     (edge && !near && !interior ? arg != 0 && arg != 2 : arg != 1)))
			error = -EINVAL;
		else {
			r->index = arg; s->change_armed = true;
			s->change.mode = near ? 16 : cmd == UB_CHANGE_SHARED_MISSING_ZERO_ARM ? 17 : cmd == UB_CHANGE_SHARED_MISSING_PRIVATE_ARM ? 18 : cmd == UB_CHANGE_SHARED_MISSING_BUSY_ARM ? 19 : cmd == UB_CHANGE_SHARED_EMPTY_ZERO_ARM ? 13 : cmd == UB_CHANGE_SHARED_EMPTY_PRIVATE_ARM ? 14 : cmd == UB_CHANGE_SHARED_EMPTY_BUSY_ARM ? 15 : cmd == UB_CHANGE_SHARED_ZERO_PRIVATE_ARM ? 11 : cmd == UB_CHANGE_SHARED_ZERO_BUSY_ARM ? 12 : busy ? 10 : cmd == UB_CHANGE_EDGE_ZERO_PRIVATE_ARM ? 9 :
				cmd == UB_CHANGE_EDGE_EMPTY_ZERO_ARM ? 7 : cmd == UB_CHANGE_EDGE_EMPTY_PRIVATE_ARM ? 8 :
				(interior || cmd == UB_CHANGE_EDGE_TABLE_ARM) ? 6 : cmd == UB_CHANGE_EMPTY_ZERO_ARM ? 1 : cmd == UB_CHANGE_EMPTY_PRIVATE_ARM ? 2 :
				cmd == UB_CHANGE_TABLE_EMPTY_ARM ? 3 : cmd == UB_CHANGE_TABLE_ZERO_ARM ? 4 : cmd == UB_CHANGE_TABLE_PRIVATE_ARM ? 5 : 0;
		}
		mutex_unlock(&s->pins_lock);
	} else if (cmd == UB_CHANGE_NOW) {
		if (s->mm->mmap_lock.unmap.enabled) return -EINVAL;
		mmap_read_lock(s->mm); error = change_target(s); mmap_read_unlock(s->mm);
	} else {
		if (!r->done) return -EAGAIN;
		if (copy_to_user((void __user *)arg, &s->change,
				 cmd == UB_CHANGE_RESULT_MORE ? sizeof(s->change) : sizeof(*r))) error = -EFAULT;
	}
	return error;
}
