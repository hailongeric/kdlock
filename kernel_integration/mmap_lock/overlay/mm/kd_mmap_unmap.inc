/* SPDX-License-Identifier: GPL-2.0 */
/* Whole isolated anonymous VMA removal. Caller preparation and the original
 * native teardown remain shared. The old opt-in still requires absent PGDs.
 * A separate opt-in admits up to four resident anonymous base pages when neighbor
 * VMAs retain the PTE table, excluding current-dependent table-batch allocation. */

#define KD_MMAP_RESIDENT_MAX 4

static void kd_mmap_unmap_release_pages(struct page **pages, unsigned int nr)
{
	while (nr) {
		struct page *page = pages[--nr];

		unlock_page(page);
		put_page(page);
	}
}

static unsigned int kd_mmap_unmap_hold_pages(struct mm_struct *mm,
	struct vm_area_struct *vma, struct vm_area_struct *prev,
	struct vm_area_struct *next, pmd_t **held_pmd, struct page **pages, unsigned int *checked)
{
	unsigned long address = vma->vm_start;
	unsigned long count = (vma->vm_end - address) >> PAGE_SHIFT;
	pgd_t *pgd = pgd_offset(mm, address);
	p4d_t *p4d;
	pud_t *pud;
	pmd_t *pmd;
	pte_t *pte;
	spinlock_t *ptl;
	unsigned int held = 0;

	/* Filling the native local gather can allocate its next batch immediately,
	 * so remain strictly below its capacity. Same-PMD neighbors retain every
	 * table: neither data-page nor table teardown allocates on the executor. */
	BUILD_BUG_ON(KD_MMAP_RESIDENT_MAX >= MMU_GATHER_BUNDLE);
	*checked = 0;
	if (!mm->mmap_lock.unmap.allow_populated || IS_ENABLED(CONFIG_LRU_GEN) ||
	    !count || count > KD_MMAP_RESIDENT_MAX || !vma->anon_vma ||
	    (vma->vm_flags & VM_MERGEABLE) ||
	    !list_is_singular(&vma->anon_vma_chain) || !prev || !next ||
	    ((vma->vm_end - 1) & PMD_MASK) != (address & PMD_MASK) ||
	    prev->vm_end <= (address & PMD_MASK) ||
	    next->vm_start >= (address & PMD_MASK) + PMD_SIZE ||
	    pgd_none(*pgd) || pgd_bad(*pgd))
		return 0;
	p4d = p4d_offset(pgd, address);
	if (p4d_none(*p4d) || p4d_bad(*p4d)) return 0;
	pud = pud_offset(p4d, address);
	if (pud_none(*pud) || pud_trans_huge(*pud) || pud_devmap(*pud) || pud_bad(*pud)) return 0;
	pmd = pmd_offset(pud, address);
	if (pmd_none(*pmd) || pmd_trans_huge(*pmd) || pmd_devmap(*pmd) || pmd_bad(*pmd)) return 0;
	pte = pte_offset_map_lock(mm, pmd, address, &ptl);
	while (held < count) {
		struct page *page;
		pte_t entry = ptep_get(pte + held);

		if (!pte_present(entry) || !pte_write(entry) || pte_special(entry) || pte_devmap(entry)) break;
		page = vm_normal_page(vma, address + held * PAGE_SIZE, entry);
		if (!page) break;
		get_page(page);
		/* All pages are checked before any removal. Try, never wait, under
		 * the PTE lock. A late refusal releases this reference and every
		 * earlier page lock/reference before handing the request back. */
		if (!trylock_page(page)) {
			put_page(page);
			break;
		}
		if (PageCompound(page) || !PageAnon(page) || !PageAnonExclusive(page) ||
		    PageSwapCache(page) || PageHWPoison(page) || PageReserved(page) ||
		    page_mapcount(page) != 1 || page_maybe_dma_pinned(page)) {
			unlock_page(page);
			put_page(page);
			break;
		}
		pages[held++] = page;
	}
	pte_unmap_unlock(pte, ptl);
	if (held != count) {
		*checked = held;
		kd_mmap_unmap_release_pages(pages, held);
		return 0;
	}
	*held_pmd = pmd;
	return held;
}

bool kd_mmap_unmap_try(struct mm_struct *mm, unsigned long start,
	unsigned long end, struct task_struct *origin, struct ma_state *live,
	struct ma_state *reserve, u64 request_id, int *result)
{
	struct vm_area_struct *vma, *prev, *next;
	struct page *held[KD_MMAP_RESIDENT_MAX];
	unsigned long pfns[KD_MMAP_RESIDENT_MAX];
	pmd_t *held_pmd = NULL;
	unsigned long address, pages, table_bytes = 0;
	unsigned int before, nr = 0, i, checked;
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
		nr = kd_mmap_unmap_hold_pages(mm, vma, prev, next, &held_pmd, held, &checked);
		if (!nr) {
			if (checked)
				pr_info("KD_MM_POPULATED_RANGE rollback mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx held=%u released=%u effects=0\n",
					mm, request_id, origin->pid, current->pid, start, end, checked, checked);
			return false;
		}
		for (i = 0; i < nr; i++) pfns[i] = page_to_pfn(held[i]);
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
	if (nr) {
		/* Neighbor VMAs keep this page-table directory under our writer.
		 * Native teardown has dropped the mapping reference and completed
		 * its TLB flush. Release our temporary reference on this executor;
		 * page/memcg ownership, never current's cgroup, governs final free. */
		if (!*result) {
			spinlock_t *ptl;
			pte_t *pte;

			BUG_ON(mm_pgtables_bytes(mm) != table_bytes);
			pte = pte_offset_map_lock(mm, held_pmd, start, &ptl);
			for (i = 0; i < nr; i++)
				BUG_ON(!pte_none(ptep_get(pte + i)) || page_mapped(held[i]));
			pte_unmap_unlock(pte, ptl);
		}
		kd_mmap_unmap_release_pages(held, nr);
		if (!*result) {
			struct kd_mmap_unmap_state *u = &mm->mmap_lock.unmap;

			atomic64_inc(&u->populated);
			if (origin != current && atomic64_inc_return(&u->populated_remote) <= 16) {
				if (nr == 1)
					pr_info("KD_MM_POPULATED done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx pfn=%lx pte_none=1 mapcount=0 tables_retained=1\n",
						mm, request_id, origin->pid, current->pid, start, end, pfns[0]);
				else
					for (i = 0; i < nr; i++)
						pr_info("KD_MM_POPULATED_RANGE done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx index=%u pages=%u pfn=%lx pte_none=1 mapcount=0 tables_retained=1\n",
							mm, request_id, origin->pid, current->pid, start, end, i, nr, pfns[i]);
			}
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
