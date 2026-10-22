/* SPDX-License-Identifier: GPL-2.0 */
/* Whole isolated anonymous VMA removal. Caller preparation and the original
 * native teardown remain shared. The old opt-in still requires absent PGDs.
 * A separate opt-in admits one resident anonymous base page only when neighbor
 * VMAs retain the PTE table, excluding current-dependent table-batch allocation. */

static struct page *kd_mmap_unmap_hold_page(struct mm_struct *mm,
	struct vm_area_struct *vma, struct vm_area_struct *prev,
	struct vm_area_struct *next, pmd_t **held_pmd)
{
	unsigned long address = vma->vm_start;
	pgd_t *pgd = pgd_offset(mm, address);
	p4d_t *p4d;
	pud_t *pud;
	pmd_t *pmd;
	pte_t *pte;
	spinlock_t *ptl;
	struct page *page = NULL;

	/* free_pgd_range rounds addr/ceiling to PMD boundaries. Neighbors
	 * strictly inside this same span make that range empty; the normal
	 * helper still runs, but cannot allocate a table-free batch. One data
	 * page fits the native eight-page local gather without allocation. */
	if (!mm->mmap_lock.unmap.allow_populated || IS_ENABLED(CONFIG_LRU_GEN) ||
	    vma->vm_end - address != PAGE_SIZE || !vma->anon_vma ||
	    (vma->vm_flags & VM_MERGEABLE) ||
	    !list_is_singular(&vma->anon_vma_chain) || !prev || !next ||
	    prev->vm_end <= (address & PMD_MASK) ||
	    next->vm_start >= (address & PMD_MASK) + PMD_SIZE ||
	    pgd_none(*pgd) || pgd_bad(*pgd))
		return NULL;
	p4d = p4d_offset(pgd, address);
	if (p4d_none(*p4d) || p4d_bad(*p4d)) return NULL;
	pud = pud_offset(p4d, address);
	if (pud_none(*pud) || pud_trans_huge(*pud) || pud_devmap(*pud) || pud_bad(*pud)) return NULL;
	pmd = pmd_offset(pud, address);
	if (pmd_none(*pmd) || pmd_trans_huge(*pmd) || pmd_devmap(*pmd) || pmd_bad(*pmd)) return NULL;
	pte = pte_offset_map_lock(mm, pmd, address, &ptl);
	if (!pte_present(*pte) || !pte_write(*pte) || pte_special(*pte) || pte_devmap(*pte)) goto out;
	page = vm_normal_page(vma, address, *pte);
	if (!page) goto out;
	get_page(page);
	/* Never wait for a page while holding its PTE lock. A busy, swapped,
	 * shared, huge, poisoned or externally pinned page refuses before
	 * effects. Page lock plus reference exclude reclaim/migration through
	 * the real unmap and keep the final state check's object alive. */
	if (!trylock_page(page)) goto put;
	if (PageCompound(page) || !PageAnon(page) || !PageAnonExclusive(page) ||
	    PageSwapCache(page) || PageHWPoison(page) || PageReserved(page) ||
	    page_mapcount(page) != 1 || page_maybe_dma_pinned(page)) {
		unlock_page(page);
		goto put;
	}
	*held_pmd = pmd;
	goto out;
put:
	put_page(page);
	page = NULL;
out:
	pte_unmap_unlock(pte, ptl);
	return page;
}

bool kd_mmap_unmap_try(struct mm_struct *mm, unsigned long start,
	unsigned long end, struct task_struct *origin, struct ma_state *live,
	struct ma_state *reserve, u64 request_id, int *result)
{
	struct vm_area_struct *vma, *prev, *next;
	struct page *page = NULL;
	pmd_t *held_pmd = NULL;
	unsigned long address, pages, table_bytes = 0, pfn = 0;
	unsigned int before;
	bool pristine;

	mmap_assert_write_locked(mm);
	if (origin->mm != mm || !live || !reserve || end <= start ||
	    end - start > 16 * PAGE_SIZE || start < mm->mmap_lock.unmap.start ||
	    end > mm->mmap_lock.unmap.end || live->tree != &mm->mm_mt ||
	    !live->alloc || ((unsigned long)live->alloc & 1) ||
	    live->alloc->total < 1 + mt_height(&mm->mm_mt) * 3 ||
	    !reserve->alloc || ((unsigned long)reserve->alloc & 1) ||
	    reserve->alloc->total < 1 || mm_has_notifiers(mm))
		return false;
	vma = find_vma_prev(mm, start, &prev);
	if (!vma || start != vma->vm_start || end != vma->vm_end ||
	    vma->vm_file || vma->vm_ops || anon_vma_name(vma) ||
	    userfaultfd_armed(vma) || vma_policy(vma) ||
	    !(vma->vm_flags & VM_NOHUGEPAGE) ||
	    (vma->vm_flags & (VM_SPECIAL | VM_HUGETLB | VM_SHARED | VM_ACCOUNT |
			     VM_GROWSDOWN | VM_GROWSUP | VM_LOCKED)))
		return false;
	next = find_vma(mm, end);
	if ((prev && prev->vm_end == start) || (next && next->vm_start == end))
		return false;
	pristine = !vma->anon_vma && list_empty(&vma->anon_vma_chain);
	for (address = start; address < end; address = pgd_addr_end(address, end))
		if (!pgd_none(READ_ONCE(*pgd_offset(mm, address))))
			pristine = false;
	if (!pristine) {
		page = kd_mmap_unmap_hold_page(mm, vma, prev, next, &held_pmd);
		if (!page) return false;
		pfn = page_to_pfn(page);
		table_bytes = mm_pgtables_bytes(mm);
	}
	/* The origin already checked TASK_SIZE/alignment with its own thread mode.
	 * x86-64 arch_unmap is empty in this captured source. No stale VMA or maple
	 * traversal pointer crosses publication; prepare only read a height hint. */
	arch_unmap(mm, start, end);
	mas_set(live, start);
	BUG_ON(mas_find(live, end - 1) != vma);
	before = mm->map_count;
	pages = mm->total_vm;
	*result = do_mas_align_munmap_prepared(live, vma, mm, start, end, NULL,
					     false, reserve);
	if (!*result) {
		BUG_ON(mm->map_count != before - 1 || mm->total_vm != pages - ((end - start) >> PAGE_SHIFT));
		BUG_ON(vma_lookup(mm, start) || vma_lookup(mm, end - 1));
	}
	if (page) {
		/* Neighbor VMAs keep this page-table directory under our writer.
		 * Native teardown has dropped the mapping reference and completed
		 * its TLB flush. Release our temporary reference on this executor;
		 * page/memcg ownership, never current's cgroup, governs final free. */
		if (!*result) {
			spinlock_t *ptl;
			pte_t *pte;

			BUG_ON(mm_pgtables_bytes(mm) != table_bytes);
			pte = pte_offset_map_lock(mm, held_pmd, start, &ptl);
			BUG_ON(!pte_none(*pte) || page_mapped(page));
			pte_unmap_unlock(pte, ptl);
		}
		unlock_page(page);
		put_page(page);
		if (!*result) {
			struct kd_mmap_unmap_state *u = &mm->mmap_lock.unmap;

			atomic64_inc(&u->populated);
			if (origin != current && atomic64_inc_return(&u->populated_remote) <= 16)
				pr_info("KD_MM_POPULATED done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx pfn=%lx pte_none=1 mapcount=0 tables_retained=1\n",
					mm, request_id, origin->pid, current->pid, start, end, pfn);
		}
	}
	return true;
}

static noinline bool kd_mmap_munmap(struct mm_struct *mm, unsigned long start,
				 size_t len, int *result)
{
	struct maple_tree scratch;
	MA_STATE(live, &mm->mm_mt, start, start);
	MA_STATE(reserve, &scratch, 0, 0);
	unsigned long end = 0;
	bool prepared = false, handled;

	/* All caller-sensitive address-limit checks and GFP_KERNEL allocation run
	 * here, on the original syscall/vm_munmap caller, before publication. No
	 * mmap read acquisition is retained or needed for allocation-only prepare. */
	mt_init_flags(&scratch, MT_FLAGS_LOCK_EXTERN);
	mt_set_external_lock(&scratch, &mm->mmap_lock);
	if (mm->mmap_lock.unmap.allow_populated &&
	    !READ_ONCE(mm->mmap_lock.unmap.native_only)) {
		/* Native unmap synchronizes caller-local RSS and LRU additions.
		 * Do that on the real origin before it becomes a pinned waiter. */
		sync_mm_rss(mm);
		lru_add_drain();
	}
	if (!READ_ONCE(mm->mmap_lock.unmap.native_only) && !offset_in_page(start) &&
	    start <= TASK_SIZE && len <= TASK_SIZE - start) {
		end = start + PAGE_ALIGN(len);
		if (end > start && end - start <= 16 * PAGE_SIZE &&
		    !kd_mmap_mas_preallocate(&live, GFP_KERNEL) &&
		    !mas_preallocate(&reserve, NULL, GFP_KERNEL))
			prepared = true;
	}
	handled = kd_mmap_unmap_submit(mm, start, end,
		prepared ? &live : NULL, prepared ? &reserve : NULL, result);
	/* A successful store consumes its reserve, including unused nodes. On
	 * refusal/cancellation, the origin frees every still-owned allocation only
	 * after its exact queue node has retired. No whole state/packet is copied. */
	mas_destroy(&live);
	mas_destroy(&reserve);
	BUG_ON(live.alloc || reserve.alloc);
	return handled;
}
