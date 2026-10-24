/* SPDX-License-Identifier: GPL-2.0 */
/* Whole isolated anonymous VMA removal and bounded anonymous slicing. Caller
 * preparation and native teardown remain shared. The old opt-in requires absent PGDs.
 * A separate opt-in admits up to four resident anonymous base pages when neighbor
 * VMAs retain the PTE table, excluding current-dependent table-batch allocation. */

#define KD_MMAP_RESIDENT_MAX 4

/* The existing typed queue borrows &detach. Its enclosing caller-owned object
 * also retains the two possible split resources until exact node retirement.
 * No live VMA pointer or traversal is captured during caller preparation. */
struct kd_mmap_unmap_preparation {
	struct ma_state detach;
	struct ma_state *split_mas[2];
	struct vm_area_struct *split_vma[2];
	struct anon_vma_chain *split_avc[2];
};

static bool kd_mmap_unmap_capacity(struct ma_state *mas, unsigned int height)
{
	return mas && mas->alloc && !((unsigned long)mas->alloc & 1) &&
		mas->alloc->total >= 1 + height * 3;
}

static void kd_mmap_unmap_release_pages(struct page **pages, unsigned int nr)
{
	while (nr) {
		struct page *page = pages[--nr];

		if (!page) continue;
		unlock_page(page);
		put_page(page);
	}
}

/* Zero/read-only anonymous mappings can have no reverse-map ancestry at all.
 * Empty means BOTH the pointer and chain are absent. An inherited simple chain
 * still needs its caller-prepared clone links even when no private PTE remains. */
static bool kd_mmap_unmap_simple_anon(struct vm_area_struct *vma, bool allow_empty)
{
	if (!vma->anon_vma)
		return allow_empty && list_empty(&vma->anon_vma_chain);
	return list_is_singular(&vma->anon_vma_chain) &&
		list_first_entry(&vma->anon_vma_chain, struct anon_vma_chain,
				 same_vma)->anon_vma == vma->anon_vma;
}

/* Both PMD entries and their common parent remain live under the mmap writer.
 * A private target uses the same exact temporary hold as a same-table target;
 * missing/empty/zero targets never acquire private-page ownership. */
struct kd_mmap_unmap_edge {
	pmd_t *target, *survivor;
	pud_t *parent;
	unsigned long parent_pfn, target_pfn, survivor_pfn, boundary, floor, ceiling;
	unsigned long outer_floor, outer_ceiling;
	unsigned int target_mask, other_mask;
	pte_t target_entry;
	unsigned int target_refs_before, target_refs_after;
	bool target_missing, target_zero, target_private, survivor_missing, shared, interior;
};

static bool kd_mmap_unmap_zero_pte(pte_t entry)
{
	return pte_present(entry) && !pte_protnone(entry) && pte_special(entry) &&
		!pte_write(entry) && !pte_devmap(entry) && is_zero_pfn(pte_pfn(entry));
}

static bool kd_mmap_unmap_hold_slot(struct vm_area_struct *vma,
	unsigned long address, pte_t entry, bool partial, struct page **held,
	bool *zero, pte_t *zero_entry)
{
	struct page *page;

	*zero = false;
	if (partial && pte_none(entry)) return true;
	if (partial && kd_mmap_unmap_zero_pte(entry)) {
		*zero = true;
		*zero_entry = pte_mkold(entry);
		return true;
	}
	if (!vma->anon_vma || !pte_present(entry) || !pte_write(entry) ||
	    pte_special(entry) || pte_devmap(entry)) return false;
	page = vm_normal_page(vma, address, entry);
	if (!page) return false;
	get_page(page);
	if (!trylock_page(page)) { put_page(page); return false; }
	if (PageCompound(page) || !PageAnon(page) || !PageAnonExclusive(page) ||
	    PageSwapCache(page) || PageHWPoison(page) || PageReserved(page) ||
	    page_mapcount(page) != 1 || page_maybe_dma_pinned(page)) {
		unlock_page(page); put_page(page); return false;
	}
	*held = page;
	return true;
}

static bool kd_mmap_unmap_hold_edge(struct mm_struct *mm,
	struct vm_area_struct *vma, struct vm_area_struct *prev,
	struct vm_area_struct *next, unsigned long start, unsigned long end,
	struct kd_mmap_unmap_edge *edge, struct page **held, unsigned int *present,
	unsigned int *zero, pte_t *zero_ptes, unsigned int *checked, unsigned int *nr)
{
	unsigned long lo = vma->vm_start, hi = vma->vm_end;
	unsigned long first = lo & PMD_MASK, last = (hi - 1) & PMD_MASK;
	unsigned long addr, free_end = end, ceiling;
	unsigned int target = (start - lo) >> PAGE_SHIFT, i;
	pgd_t *pgd; p4d_t *p4d; pud_t *pud; pmd_t *left;
	spinlock_t *ptl;
	pte_t *pte;
	bool is_zero;

	*nr = *checked = *present = *zero = 0;
	if (!mm->mmap_lock.unmap.allow_partial || IS_ENABLED(CONFIG_LRU_GEN) ||
	    hi - lo != 3 * PAGE_SIZE || end - start != PAGE_SIZE ||
	    last != first + PMD_SIZE || (lo & PUD_MASK) != ((hi - 1) & PUD_MASK) ||
	    !(start == lo || end == hi || target == 1) ||
	    !kd_mmap_unmap_simple_anon(vma, true) || (vma->vm_flags & VM_MERGEABLE) ||
	    !prev || !next || prev->vm_end <= first || next->vm_start >= last + PMD_SIZE)
		return false;
	edge->interior = start > lo && end < hi;
	edge->shared = edge->interior || !((start == lo && end == last) || (end == hi && start == last));
	edge->outer_floor = prev->vm_end;
	edge->outer_ceiling = next->vm_start;
	/* Each cut creates a surviving adjacent VMA. For two interior cuts the
	 * actual post-split floor is start and ceiling is end; either boundary
	 * orientation returns before native free_pgd_range walks any table.
	 * Keep BOTH outer-neighbor guards too: this stage does not generalize
	 * lifetime or teardown beyond the established retained-table scope. */
	edge->floor = start > lo ? start : prev->vm_end;
	edge->ceiling = end < hi ? end : next->vm_start;
	for (i = 0; i < 3; i++)
		if (((lo + i * PAGE_SIZE) & PMD_MASK) == (start & PMD_MASK))
			edge->target_mask |= 1U << i;
	edge->other_mask = 7U ^ edge->target_mask;
	addr = start & PMD_MASK;
	if (addr < edge->floor) addr += PMD_SIZE;
	ceiling = edge->ceiling & PMD_MASK;
	if (!ceiling) return false;
	if (free_end - 1 > ceiling - 1) free_end -= PMD_SIZE;
	if (addr <= free_end - 1) return false;
	pgd = pgd_offset(mm, lo);
	if (pgd_none(*pgd) || pgd_bad(*pgd)) return false;
	p4d = p4d_offset(pgd, lo);
	if (p4d_none(*p4d) || p4d_bad(*p4d)) return false;
	pud = pud_offset(p4d, lo);
	if (pud_none(*pud) || pud_bad(*pud) || pud_trans_huge(*pud) || pud_devmap(*pud)) return false;
	left = pmd_offset(pud, lo);
	edge->target = left + ((start & PMD_MASK) == last);
	edge->survivor = left + ((start & PMD_MASK) != last);
	edge->parent = pud;
	edge->parent_pfn = pud_pfn(READ_ONCE(*pud));
	edge->boundary = last;
	ptl = pmd_lock(mm, edge->target);
	edge->target_missing = pmd_none(*edge->target);
	spin_unlock(ptl);
	if (!edge->target_missing) {
		pte_t entry;
		bool supported;

		/* Rewalk under the actual mmap writer, never a prepublication PTE
		 * pointer. The unchanged floor/ceiling proof retains this table.
		 * The shared classifier takes one nonblocking private-page hold,
		 * rejects COW/pinned/busy pages, and never owns a special zero page.
		 * Native zap and the bounded gather perform rmap/RSS/TLB teardown;
		 * the exact temporary hold survives until that teardown completes. */
		if (!pmd_present(*edge->target) || pmd_bad(*edge->target) ||
		    pmd_trans_huge(*edge->target) || pmd_devmap(*edge->target)) return false;
		pte = pte_offset_map_lock(mm, edge->target, start, &ptl);
		edge->target_pfn = pmd_pfn(READ_ONCE(*edge->target));
		entry = ptep_get(pte);
		/* The interior class admits empty or exact shared-zero PTEs under
		 * the current PTE lock and retained mmap writer. The zero classifier
		 * owns no page: native zap clears its PTE and invalidates translation,
		 * then skips RSS/rmap/page release as vm_normal_page() returns NULL.
		 * Private targets and all other special entries still hand back
		 * before holds or either split; edge support does not authorize them. */
		if (edge->interior && !pte_none(entry) && !kd_mmap_unmap_zero_pte(entry)) {
			pte_unmap_unlock(pte, ptl);
			return false;
		}
		supported = kd_mmap_unmap_hold_slot(vma, start, entry, true,
			&held[target], &is_zero, &zero_ptes[target]);
		edge->target_zero = is_zero;
		edge->target_private = !!held[target];
		edge->target_entry = pte_mkold(entry);
		if (held[target]) {
			*present |= 1U << target;
			(*nr)++;
			edge->target_refs_before = page_count(held[target]);
		}
		if (edge->target_zero) {
			*zero |= 1U << target;
			zero_ptes[target] = pte_mkold(entry);
		}
		pte_unmap_unlock(pte, ptl);
		if (!supported) return false;
	}
	/* A missing target PMD covers the near survivor too. Under this mmap
	 * writer it cannot acquire a leaf table; the near slot is necessarily
	 * untouched, with no PTE pointer, reverse map or private-page hold.
	 * The upper walk and BOTH outer-neighbor/native-retention checks above
	 * still apply. Never allocate a table merely to remove an absent range.
	 * Existing tables passed the exact empty/zero/private classifier. */
	ptl = pmd_lock(mm, edge->survivor);
	edge->survivor_missing = pmd_none(*edge->survivor);
	spin_unlock(ptl);
	if (!edge->survivor_missing) {
		if (!pmd_present(*edge->survivor) || pmd_bad(*edge->survivor) ||
		    pmd_trans_huge(*edge->survivor) || pmd_devmap(*edge->survivor)) goto rollback;
		edge->survivor_pfn = pmd_pfn(READ_ONCE(*edge->survivor));
	}
	for (i = 0; i < 3; i++) {
		pmd_t *slot;
		bool supported;

		if (i == target) continue;
		addr = lo + i * PAGE_SIZE;
		slot = (addr & PMD_MASK) == (start & PMD_MASK) ? edge->target : edge->survivor;
		if ((slot == edge->target && edge->target_missing) ||
		    (slot == edge->survivor && edge->survivor_missing)) continue;
		/* Each surviving slot is classified in its actual current table.
		 * The mmap writer retains both tables; never hold two PTE locks or
		 * carry a PTE pointer across the table boundary. */
		pte = pte_offset_map_lock(mm, slot, addr, &ptl);
		/* An empty or zero interior target may retain an exact shared-zero
		 * near PTE in this existing table. Target classification was captured
		 * under its PTE lock and remains stable under the mmap writer; never
		 * allocate a target page or table. The common classifier owns no zero
		 * page, and post-body/error checks preserve the surviving PTE.
		 * Private/special near entries refuse before either split, rolling
		 * back any earlier far hold exactly; native work must never replay. */
		if (edge->interior && slot == edge->target && !pte_none(ptep_get(pte)) &&
		    !(!edge->target_missing && (edge->target_zero || pte_none(edge->target_entry)) &&
		      kd_mmap_unmap_zero_pte(ptep_get(pte)))) {
			pte_unmap_unlock(pte, ptl);
			goto rollback;
		}
		supported = kd_mmap_unmap_hold_slot(vma, addr, ptep_get(pte),
			true, &held[i], &is_zero, &zero_ptes[i]);
		pte_unmap_unlock(pte, ptl);
		if (!supported) goto rollback;
		if (is_zero) *zero |= 1U << i;
		if (held[i]) { *present |= 1U << i; (*nr)++; }
	}
	return true;
rollback:
	/* A survivor refusal must also release a previously acquired target.
	 * No split or destructive native work has happened on this route. */
	*checked = *nr;
	kd_mmap_unmap_release_pages(held, 3);
	return false;
}

static bool kd_mmap_unmap_hold_pages(struct mm_struct *mm,
	struct vm_area_struct *vma, struct vm_area_struct *prev,
	struct vm_area_struct *next,
	bool partial, pmd_t **held_pmd, pud_t **held_pud,
	bool *missing_table, unsigned long *parent_pfn, struct page **pages,
	unsigned int *present, unsigned int *zero, pte_t *zero_ptes,
	unsigned int *checked, unsigned int *nr)
{
	unsigned long address = vma->vm_start;
	unsigned long count = (vma->vm_end - address) >> PAGE_SHIFT;
	pgd_t *pgd = pgd_offset(mm, address);
	p4d_t *p4d;
	pud_t *pud;
	pmd_t *pmd;
	pte_t *pte;
	spinlock_t *ptl;
	unsigned int held = 0, i;

	/* Filling the native local gather can allocate its next batch immediately,
	 * so remain strictly below its capacity. Same-PMD neighbors retain every
	 * table: neither data-page nor table teardown allocates on the executor. */
	BUILD_BUG_ON(KD_MMAP_RESIDENT_MAX >= MMU_GATHER_BUNDLE);
	*checked = 0;
	*nr = 0;
	*present = 0;
	*zero = 0;
	*missing_table = false;
	if (!mm->mmap_lock.unmap.allow_populated || IS_ENABLED(CONFIG_LRU_GEN) ||
	    !count || count > KD_MMAP_RESIDENT_MAX ||
	    !kd_mmap_unmap_simple_anon(vma, partial) ||
	    (vma->vm_flags & VM_MERGEABLE) ||
	    !prev || !next ||
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
	/* pmd_none() means this entire 2-MiB interval has no leaf table; all
	 * three same-PMD slots are necessarily untouched. Never allocate one.
	 * Serialize the observation with native pmd_install(), even though our
	 * mmap writer already excludes ordinary faults. Missing PGD/P4D/PUD and
	 * huge/special non-present entries never reach this admitted state. */
	if (partial) {
		ptl = pmd_lock(mm, pmd);
		if (pmd_none(*pmd)) {
			*held_pmd = pmd;
			*held_pud = pud;
			*parent_pfn = pud_pfn(READ_ONCE(*pud));
			*missing_table = true;
		}
		spin_unlock(ptl);
		if (*missing_table) return true;
	}
	if (pmd_none(*pmd) || pmd_trans_huge(*pmd) || pmd_devmap(*pmd) || pmd_bad(*pmd)) return 0;
	pte = pte_offset_map_lock(mm, pmd, address, &ptl);
	for (i = 0; i < count; i++) {
		bool is_zero;

		/* Preserve slot indices, zero-page non-ownership and exact rollback.
		 * The shared classifier never waits while holding the PTE lock. */
		if (!kd_mmap_unmap_hold_slot(vma, address + i * PAGE_SIZE,
			ptep_get(pte + i), partial, &pages[i], &is_zero, &zero_ptes[i])) break;
		if (is_zero) *zero |= 1U << i;
		if (pages[i]) { *present |= 1U << i; held++; }
	}
	pte_unmap_unlock(pte, ptl);
	if (i != count) {
		*checked = held;
		kd_mmap_unmap_release_pages(pages, i);
		return 0;
	}
	*held_pmd = pmd;
	*nr = held;
	/* Admission and ownership are separate: zero/empty targets may own no
	 * pages. Native removal still runs; the retained table needs post-body
	 * checks even when no populated target translation needs invalidation. */
	return true;
}

bool kd_mmap_unmap_try(struct mm_struct *mm, unsigned long start,
	unsigned long end, struct task_struct *origin, struct ma_state *live,
	struct ma_state *reserve, u64 request_id, int *result)
{
	struct vm_area_struct *vma, *prev, *next;
	struct page *held[KD_MMAP_RESIDENT_MAX] = { NULL };
	pte_t zero_ptes[KD_MMAP_RESIDENT_MAX];
	unsigned long pfns[KD_MMAP_RESIDENT_MAX];
	pmd_t *held_pmd = NULL;
	pud_t *held_pud = NULL;
	unsigned long parent_pfn = 0;
	bool missing_table = false, boundary_edge = false;
	struct kd_mmap_unmap_edge edge = { 0 };
	unsigned long address, pages, table_bytes = 0;
	unsigned long old_start, old_end, old_flags, old_pgoff;
	unsigned int before, nr = 0, i, checked, splits = 0, present = 0, zero = 0, slots;
	struct kd_mmap_unmap_preparation *prep;
	bool pristine, partial, zero_target = false, absent_target = false;

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
	if (!vma || start < vma->vm_start || end > vma->vm_end ||
	    vma->vm_file || vma->vm_ops || anon_vma_name(vma) ||
	    userfaultfd_armed(vma) || vma_policy(vma) ||
	    !(vma->vm_flags & VM_NOHUGEPAGE) ||
	    (vma->vm_flags & (VM_SPECIAL | VM_HUGETLB | VM_SHARED | VM_ACCOUNT |
			     VM_GROWSDOWN | VM_GROWSUP | VM_LOCKED)))
		return false;
	old_start = vma->vm_start;
	old_end = vma->vm_end;
	old_flags = vma->vm_flags;
	old_pgoff = vma->vm_pgoff;
	slots = (old_end - old_start) >> PAGE_SHIFT;
	partial = start != old_start || end != old_end;
	if (partial && (old_end - old_start > 16 * PAGE_SIZE ||
	    old_start < mm->mmap_lock.unmap.start || old_end > mm->mmap_lock.unmap.end))
		return false;
	next = find_vma(mm, old_end);
	if ((prev && prev->vm_end == old_start) || (next && next->vm_start == old_end))
		return false;
	pristine = !vma->anon_vma && list_empty(&vma->anon_vma_chain);
	for (address = partial ? old_start : start; address < (partial ? old_end : end);
	     address = pgd_addr_end(address, partial ? old_end : end))
		if (!pgd_none(READ_ONCE(*pgd_offset(mm, address))))
			pristine = false;
	prep = container_of(reserve, struct kd_mmap_unmap_preparation, detach);
	if (partial) {
		unsigned int height = mt_height(&mm->mm_mt) + 2;

		if (!kd_mmap_unmap_capacity(live, height))
			return false;
		if (mm->mmap_lock.unmap.allow_populated) {
			/* One private, shared-zero or empty-leaf target in a three-page VMA.
			 * Retained slots may be private, zero or absent. Empty ancestry is
			 * valid only with no private PTEs. Refuse unsupported ancestry or
			 * missing allocation before any split occurs. */
			if (!mm->mmap_lock.unmap.allow_partial || pristine ||
			    old_end - old_start != 3 * PAGE_SIZE || end - start != PAGE_SIZE ||
			    !kd_mmap_unmap_simple_anon(vma, true) ||
			    !prep->split_avc[0] || !prep->split_avc[1])
				return false;
		} else if (!pristine) {
			return false;
		}
		for (i = 0; i < 2; i++)
			if (!prep->split_vma[i] || prep->split_mas[i]->tree != &mm->mm_mt ||
			    !kd_mmap_unmap_capacity(prep->split_mas[i], height))
				return false;
		if (start > old_start && end < old_end && mm->map_count >= sysctl_max_map_count) {
			*result = -ENOMEM;
			return true;
		}
	}
	if (!pristine) {
		bool admitted;

		boundary_edge = partial && (old_start & PMD_MASK) != ((old_end - 1) & PMD_MASK);
		if (boundary_edge) {
			admitted = kd_mmap_unmap_hold_edge(mm, vma, prev, next, start, end,
				&edge, held, &present, &zero, zero_ptes, &checked, &nr);
			if (admitted) held_pmd = edge.target;
		} else {
			admitted = kd_mmap_unmap_hold_pages(mm, vma, prev, next,
				partial, &held_pmd, &held_pud, &missing_table, &parent_pfn,
				held, &present, &zero, zero_ptes, &checked, &nr);
		}
		if (!admitted) {
			if (checked)
				pr_info("KD_MM_POPULATED_RANGE rollback mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx held=%u released=%u effects=0\n",
					mm, request_id, origin->pid, current->pid, start, end, checked, checked);
			return false;
		}
		for (i = 0; i < slots; i++)
			if (present & (1U << i)) pfns[i] = page_to_pfn(held[i]);
		zero_target = partial && (zero & (1U << ((start - old_start) >> PAGE_SHIFT)));
		absent_target = partial && !boundary_edge && !missing_table && !((present | zero) &
				(1U << ((start - old_start) >> PAGE_SHIFT)));
		table_bytes = mm_pgtables_bytes(mm);
	}
	/* The origin already checked TASK_SIZE/alignment with its own thread mode.
	 * x86-64 arch_unmap is empty in this captured source. No stale VMA or maple
	 * traversal pointer crosses publication; prepare only read a height hint. */
	if (boundary_edge && edge.interior && origin != current)
		pr_info("KD_MM_INTERIOR preflight mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx old_start=%lx old_end=%lx outer_floor=%lx outer_ceiling=%lx floor=%lx ceiling=%lx required_splits=2 no_table_walk=1\n",
			mm, request_id, origin->pid, current->pid, start, end, old_start, old_end,
			edge.outer_floor, edge.outer_ceiling, edge.floor, edge.ceiling);
	arch_unmap(mm, start, end);
	before = mm->map_count;
	pages = mm->total_vm;
	if (partial) {
		table_bytes = mm_pgtables_bytes(mm);
		/* Admission is now complete. Once a split can change the maple tree,
		 * any error is an admitted return, NEVER a native replay/refusal. */
		if (start > old_start) {
			*result = split_vma_prepared(mm, vma, start, 0,
				&prep->split_vma[splits], prep->split_mas[splits], &prep->split_avc[splits]);
			if (*result) goto out_pages;
			splits++;
			vma = find_vma(mm, start);
			*result = kd_mmap_unmap_test_error(mm, start, end, splits, false);
			if (*result) goto out_pages;
		}
		if (end < old_end) {
			*result = split_vma_prepared(mm, vma, end, 0,
				&prep->split_vma[splits], prep->split_mas[splits], &prep->split_avc[splits]);
			if (*result) goto out_pages;
			splits++;
			vma = find_vma(mm, start);
			if (boundary_edge && edge.interior) {
				struct vm_area_struct *left, *right;

				BUG_ON(splits != 2 || find_vma_prev(mm, start, &left) != vma);
				right = find_vma(mm, end);
				BUG_ON(!left || left->vm_start != old_start || left->vm_end != edge.floor ||
				       !right || right->vm_start != edge.ceiling || right->vm_end != old_end ||
				       !vma || vma->vm_start != start || vma->vm_end != end ||
				       mm->map_count != before + 2 || mm->total_vm != pages ||
				       mm_pgtables_bytes(mm) != table_bytes);
				if (origin != current)
					pr_info("KD_MM_INTERIOR split_bounds mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx left_start=%lx left_end=%lx right_start=%lx right_end=%lx splits=2 tables_unchanged=1\n",
						mm, request_id, origin->pid, current->pid, start, end,
						left->vm_start, left->vm_end, right->vm_start, right->vm_end);
			}
			*result = kd_mmap_unmap_test_error(mm, start, end, splits, false);
			if (*result) goto out_pages;
		}
		BUG_ON(!vma || vma->vm_start != start || vma->vm_end != end);
	}
	mas_set(live, start);
	BUG_ON(mas_find(live, end - 1) != vma);
	*result = do_mas_align_munmap_prepared(live, vma, mm, start, end, NULL,
					     false, reserve);
	if (!*result) {
		BUG_ON(mm->map_count != before + splits - 1 || mm->total_vm != pages - ((end - start) >> PAGE_SHIFT));
		BUG_ON(vma_lookup(mm, start) || vma_lookup(mm, end - 1));
		if (partial) {
			struct vm_area_struct *kept;

			BUG_ON(mm_pgtables_bytes(mm) != table_bytes);
			if (start > old_start) {
				kept = vma_lookup(mm, old_start);
				BUG_ON(!kept || kept->vm_start != old_start || kept->vm_end != start ||
				       kept->vm_flags != old_flags || kept->vm_pgoff != old_pgoff);
			}
			if (end < old_end) {
				kept = vma_lookup(mm, end);
				BUG_ON(!kept || kept->vm_start != end || kept->vm_end != old_end ||
				       kept->vm_flags != old_flags ||
				       kept->vm_pgoff != old_pgoff + ((end - old_start) >> PAGE_SHIFT));
			}
			if (origin != current && atomic64_read(&mm->mmap_lock.unmap.delegated) < 16)
				pr_info("KD_MM_PARTIAL done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx old_start=%lx old_end=%lx splits=%u maps_before=%u maps_after=%u pages_before=%lu pages_after=%lu tables_unchanged=1\n",
					mm, request_id, origin->pid, current->pid, start, end, old_start, old_end,
					splits, before, mm->map_count, pages, mm->total_vm);
		}
	}
out_pages:
	if (held_pmd) {
		/* Neighbor VMAs keep this page-table directory under our writer.
		 * Native teardown has completed its TLB flush; a removed private page
		 * also lost its mapping reference. Zero pages own no such reference.
		 * Release our temporary private-page references on this executor;
		 * page/memcg ownership, never current's cgroup, governs final free. */
		if (boundary_edge) {
			unsigned int target = (start - old_start) >> PAGE_SHIFT;
			spinlock_t *ptl;
			pte_t *pte;

			BUG_ON(mm_pgtables_bytes(mm) != table_bytes ||
			       !!held[target] != edge.target_private ||
			       !!(present & (1U << target)) != edge.target_private ||
			       !!(zero & (1U << target)) != edge.target_zero ||
			       pud_none(*edge.parent) || pud_pfn(*edge.parent) != edge.parent_pfn);
			ptl = pmd_lock(mm, edge.target);
			BUG_ON(pmd_none(*edge.target) != edge.target_missing);
			spin_unlock(ptl);
			if (!edge.target_missing) {
				BUG_ON(!pmd_present(*edge.target) || pmd_bad(*edge.target) ||
				       pmd_trans_huge(*edge.target) || pmd_devmap(*edge.target) ||
				       pmd_pfn(*edge.target) != edge.target_pfn);
				pte = pte_offset_map_lock(mm, edge.target, start, &ptl);
				/* A post-split error preserves the original target. Success
				 * has completed native zap/TLB before any temporary put. */
				if (*result && (edge.target_zero || edge.target_private))
					BUG_ON(!pte_same(pte_mkold(ptep_get(pte)), edge.target_entry));
				else
					BUG_ON(!pte_none(ptep_get(pte)));
				if (edge.target_private) {
					BUG_ON(page_to_pfn(held[target]) != pfns[target] ||
					       page_mapcount(held[target]) != !!*result);
					edge.target_refs_after = page_count(held[target]);
				}
				pte_unmap_unlock(pte, ptl);
			}
			ptl = pmd_lock(mm, edge.survivor);
			BUG_ON(pmd_none(*edge.survivor) != edge.survivor_missing);
			spin_unlock(ptl);
			if (!edge.survivor_missing)
				BUG_ON(pmd_pfn(*edge.survivor) != edge.survivor_pfn);
			for (i = 0; i < 3; i++) {
				pmd_t *slot;
				pte_t entry;

				if (i == target) continue;
				address = old_start + i * PAGE_SIZE;
				slot = (address & PMD_MASK) == (start & PMD_MASK) ? edge.target : edge.survivor;
				if ((slot == edge.target && edge.target_missing) ||
				    (slot == edge.survivor && edge.survivor_missing)) {
					BUG_ON(held[i] || ((present | zero) & (1U << i)));
					continue;
				}
				pte = pte_offset_map_lock(mm, slot, address, &ptl);
				entry = ptep_get(pte);
				if (zero & (1U << i))
					BUG_ON(held[i] || !pte_same(pte_mkold(entry), zero_ptes[i]));
				else if (present & (1U << i))
					BUG_ON(!pte_present(entry) || pte_pfn(entry) != pfns[i] || page_mapcount(held[i]) != 1);
				else BUG_ON(held[i] || !pte_none(entry));
				pte_unmap_unlock(pte, ptl);
			}
		} else if (missing_table) {
			spinlock_t *ptl;

			/* Same-PMD floor/ceiling makes native free_pgd_range() return
			 * before walking. Check the retained PMD-table identity and its
			 * still-empty entry, including admitted split errors. There is
			 * no PTE pointer, data-page ownership or table-free obligation. */
			BUG_ON(nr || present || zero || !held_pud ||
			       pud_none(*held_pud) || pud_pfn(*held_pud) != parent_pfn ||
			       mm_pgtables_bytes(mm) != table_bytes);
			ptl = pmd_lock(mm, held_pmd);
			BUG_ON(!pmd_none(*held_pmd));
			spin_unlock(ptl);
		} else if (!*result || zero || absent_target) {
			spinlock_t *ptl;
			pte_t *pte;

			BUG_ON(mm_pgtables_bytes(mm) != table_bytes);
			pte = pte_offset_map_lock(mm, held_pmd, old_start, &ptl);
			for (i = 0; i < slots; i++)
				if (zero & (1U << i)) {
					/* Native zap clears a zero target and records its TLB
					 * invalidation, but vm_normal_page() returns NULL: there
					 * is no private RSS, rmap or page reference to release.
					 * On error every zero PTE, including the target, remains.
					 * Ignore only readers' hardware access-bit updates. */
					BUG_ON(held[i] || (present & (1U << i)));
					if (!*result && old_start + i * PAGE_SIZE >= start &&
					    old_start + i * PAGE_SIZE < end)
						BUG_ON(!pte_none(ptep_get(pte + i)));
					else
						BUG_ON(!pte_same(pte_mkold(ptep_get(pte + i)), zero_ptes[i]));
				} else if (!(present & (1U << i))) {
					/* Empty leaves stay empty on success and admitted error;
					 * the successful VMA removal above, not a PTE clear,
					 * makes later access to the target invalid. */
					BUG_ON(!pte_none(ptep_get(pte + i)) || held[i]);
				} else if (*result) {
					continue;
				} else if (old_start + i * PAGE_SIZE >= start && old_start + i * PAGE_SIZE < end) {
					BUG_ON(!pte_none(ptep_get(pte + i)) || page_mapped(held[i]));
				} else {
					pte_t entry = ptep_get(pte + i);

					BUG_ON(!pte_present(entry) || pte_pfn(entry) != pfns[i] ||
					       page_mapcount(held[i]) != 1);
				}
			pte_unmap_unlock(pte, ptl);
		}
		kd_mmap_unmap_release_pages(held, slots);
		if (!*result) {
			struct kd_mmap_unmap_state *u = &mm->mmap_lock.unmap;

			atomic64_inc(&u->populated);
			if (origin != current && atomic64_inc_return(&u->populated_remote) <= 16) {
				if (boundary_edge && edge.target_private) {
					pr_info("KD_MM_BOUNDARY%s_PRIVATE done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx boundary=%lx parent_pfn=%lx survivor_table_pfn=%lx survivor_missing=%u resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u floor=%lx ceiling=%lx target_pmd_none=0 target_owned=1 tables_unchanged=1 target_table_pfn=%lx target_pte_none=1 target_pfn=%lx refs_before=%u refs_after=%u mapcount=0 target_put=1 tlb_complete=1 shared_geometry=%u target_table_mask=%u other_table_mask=%u\n",
						edge.interior ? "_INTERIOR" : edge.shared ? "_SHARED" : "", mm, request_id, origin->pid, current->pid, start, end, edge.boundary,
						edge.parent_pfn, edge.survivor_pfn, edge.survivor_missing,
						present, zero, 7U ^ (present | zero), nr, nr, edge.floor, edge.ceiling,
						edge.target_pfn, pfns[(start - old_start) >> PAGE_SHIFT],
						edge.target_refs_before, edge.target_refs_after, edge.shared,
						edge.target_mask,
						edge.other_mask);
				} else if (boundary_edge) {
					pr_info("KD_MM_BOUNDARY%s%s done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx boundary=%lx parent_pfn=%lx survivor_table_pfn=%lx survivor_missing=%u resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u floor=%lx ceiling=%lx target_pmd_none=%u target_owned=0 tables_unchanged=1 target_table_pfn=%lx target_pte_none=%u target_zero=%u zero_pfn=%lx zero_owned=0 shared_geometry=%u target_table_mask=%u other_table_mask=%u zero_tlb_complete=%u\n",
						edge.interior ? "_INTERIOR" : edge.shared ? "_SHARED" : "", edge.target_missing ? (edge.shared ? "_MISSING" : "") : edge.target_zero ? "_ZERO" : "_EMPTY", mm, request_id, origin->pid, current->pid, start, end, edge.boundary,
						edge.parent_pfn, edge.survivor_pfn, edge.survivor_missing,
						present, zero, 7U ^ (present | zero), nr, nr, edge.floor, edge.ceiling,
						edge.target_missing, edge.target_pfn, !edge.target_missing, edge.target_zero,
						edge.target_zero ? pte_pfn(zero_ptes[(start - old_start) >> PAGE_SHIFT]) : 0UL, edge.shared,
						edge.target_mask,
						edge.other_mask, edge.target_zero);
				} else if (missing_table) {
					pr_info("KD_MM_MISSING_TABLE done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx pmd_table_pfn=%lx pmd_none=1 held=0 released=0 target_owned=0 upper_retained=1 tables_unchanged=1\n",
						mm, request_id, origin->pid, current->pid, start, end, parent_pfn);
				} else if (absent_target) {
					pr_info("KD_MM_ABSENT_TARGET done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u initial_pte_none=1 target_pte_none=1 target_owned=0 table_pfn=%lx tables_retained=1 zero_survivors_preserved=1\n",
						mm, request_id, origin->pid, current->pid, start, end,
						present, zero, 7U ^ (present | zero), nr, nr,
						pmd_pfn(READ_ONCE(*held_pmd)));
				} else if (zero_target) {
					pr_info("KD_MM_ZERO_TARGET done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx zero_pfn=%lx resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u target_pte_none=1 zero_owned=0 tables_retained=1 zero_survivors_preserved=1\n",
						mm, request_id, origin->pid, current->pid, start, end,
						pte_pfn(zero_ptes[(start - old_start) >> PAGE_SHIFT]),
						present, zero, 7U ^ (present | zero), nr, nr);
				} else if (partial) {
					pr_info("KD_MM_RESIDENT_PARTIAL done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx pfn=%lx held=%u released=%u pte_none=1 mapcount=0 tables_retained=1\n",
						mm, request_id, origin->pid, current->pid, start, end,
						pfns[(start - old_start) >> PAGE_SHIFT], nr, nr);
					if (zero)
						pr_info("KD_MM_ZERO_PARTIAL done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u zero_ptes_preserved=1\n",
							mm, request_id, origin->pid, current->pid, start, end,
							present, zero, 7U ^ (present | zero), nr, nr);
					else if (present != 7)
						pr_info("KD_MM_MIXED_PARTIAL done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx resident_mask=%u untouched_mask=%u held=%u released=%u\n",
							mm, request_id, origin->pid, current->pid, start, end,
							present, 7U ^ present, nr, nr);
				} else if (nr == 1)
					pr_info("KD_MM_POPULATED done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx pfn=%lx pte_none=1 mapcount=0 tables_retained=1\n",
						mm, request_id, origin->pid, current->pid, start, end, pfns[0]);
				else
					for (i = 0; i < nr; i++)
						pr_info("KD_MM_POPULATED_RANGE done mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx index=%u pages=%u pfn=%lx pte_none=1 mapcount=0 tables_retained=1\n",
							mm, request_id, origin->pid, current->pid, start, end, i, nr, pfns[i]);
			}
		}
	}
	if (*result && partial)
		pr_info("KD_MM_PARTIAL error mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx splits=%u held=%u released=%u result=%d\n",
			mm, request_id, origin->pid, current->pid, start, end, splits, nr, nr, *result);
	if (*result && boundary_edge && edge.target_private)
		pr_info("KD_MM_BOUNDARY%s_PRIVATE error mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx boundary=%lx parent_pfn=%lx survivor_table_pfn=%lx survivor_missing=%u resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u floor=%lx ceiling=%lx target_pmd_none=0 target_owned=1 tables_unchanged=1 result=%d target_table_pfn=%lx target_pte_none=0 target_pfn=%lx refs_before=%u refs_after=%u mapcount=1 target_put=1 target_preserved=1 shared_geometry=%u target_table_mask=%u other_table_mask=%u\n",
			edge.interior ? "_INTERIOR" : edge.shared ? "_SHARED" : "", mm, request_id, origin->pid, current->pid, start, end, edge.boundary,
			edge.parent_pfn, edge.survivor_pfn, edge.survivor_missing,
			present, zero, 7U ^ (present | zero), nr, nr, edge.floor, edge.ceiling,
			*result, edge.target_pfn, pfns[(start - old_start) >> PAGE_SHIFT],
			edge.target_refs_before, edge.target_refs_after, edge.shared,
			edge.target_mask,
			edge.other_mask);
	else if (*result && boundary_edge)
		pr_info("KD_MM_BOUNDARY%s%s error mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx boundary=%lx parent_pfn=%lx survivor_table_pfn=%lx survivor_missing=%u resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u floor=%lx ceiling=%lx target_pmd_none=%u target_owned=0 tables_unchanged=1 result=%d target_table_pfn=%lx target_pte_none=%u target_zero=%u zero_pfn=%lx zero_owned=0 zero_ptes_preserved=1 shared_geometry=%u target_table_mask=%u other_table_mask=%u\n",
			edge.interior ? "_INTERIOR" : edge.shared ? "_SHARED" : "", edge.target_missing ? (edge.shared ? "_MISSING" : "") : edge.target_zero ? "_ZERO" : "_EMPTY", mm, request_id, origin->pid, current->pid, start, end, edge.boundary,
			edge.parent_pfn, edge.survivor_pfn, edge.survivor_missing,
			present, zero, 7U ^ (present | zero), nr, nr, edge.floor, edge.ceiling,
			edge.target_missing, *result, edge.target_pfn, !edge.target_missing && !edge.target_zero,
			edge.target_zero, edge.target_zero ? pte_pfn(zero_ptes[(start - old_start) >> PAGE_SHIFT]) : 0UL, edge.shared,
			edge.target_mask,
			edge.other_mask);
	else if (*result && missing_table)
		pr_info("KD_MM_MISSING_TABLE error mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx pmd_table_pfn=%lx pmd_none=1 held=0 released=0 target_owned=0 upper_retained=1 tables_unchanged=1 result=%d\n",
			mm, request_id, origin->pid, current->pid, start, end, parent_pfn, *result);
	else if (*result && absent_target)
		pr_info("KD_MM_ABSENT_TARGET error mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u target_pte_none=1 target_owned=0 table_pfn=%lx zero_ptes_preserved=1 result=%d\n",
			mm, request_id, origin->pid, current->pid, start, end,
			present, zero, 7U ^ (present | zero), nr, nr,
			pmd_pfn(READ_ONCE(*held_pmd)), *result);
	else if (*result && zero_target)
		pr_info("KD_MM_ZERO_TARGET error mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u zero_ptes_preserved=1 zero_owned=0 result=%d\n",
			mm, request_id, origin->pid, current->pid, start, end,
			present, zero, 7U ^ (present | zero), nr, nr, *result);
	else if (*result && zero)
		pr_info("KD_MM_ZERO_PARTIAL error mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx resident_mask=%u zero_mask=%u untouched_mask=%u held=%u released=%u zero_ptes_preserved=1 result=%d\n",
			mm, request_id, origin->pid, current->pid, start, end,
			present, zero, 7U ^ (present | zero), nr, nr, *result);
	return true;
}

static noinline bool kd_mmap_munmap(struct mm_struct *mm, unsigned long start,
				 size_t len, int *result)
{
	struct maple_tree scratch;
	MA_STATE(live, &mm->mm_mt, start, start);
	MA_STATE(split0, &mm->mm_mt, 0, 0);
	MA_STATE(split1, &mm->mm_mt, 0, 0);
	struct kd_mmap_unmap_preparation prep = {
		.detach = { .tree = &scratch, .node = MAS_START },
		.split_mas = { &split0, &split1 },
	};
	struct ma_state *reserve = &prep.detach;
	unsigned long end = 0;
	unsigned long allocated[2] = { 0, 0 };
	unsigned long allocated_avc[2] = { 0, 0 };
	unsigned int i, consumed = 0, freed = 0;
	unsigned int avc_consumed = 0, avc_freed = 0;
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
		    !mas_preallocate(reserve, NULL, GFP_KERNEL))
			prepared = true;
		if (prepared && (!mm->mmap_lock.unmap.allow_populated || mm->mmap_lock.unmap.allow_partial)) {
			for (i = 0; i < 2; i++) {
				prep.split_vma[i] = vm_area_alloc(mm);
				allocated[i] = (unsigned long)prep.split_vma[i];
				if (!prep.split_vma[i] || kd_mmap_mas_preallocate(prep.split_mas[i], GFP_KERNEL)) {
					prepared = false;
					break;
				}
				if (mm->mmap_lock.unmap.allow_partial) {
					prep.split_avc[i] = kd_anon_vma_chain_alloc();
					allocated_avc[i] = (unsigned long)prep.split_avc[i];
					if (!prep.split_avc[i]) { prepared = false; break; }
				}
			}
		}
	}
	handled = kd_mmap_unmap_submit(mm, start, end,
		prepared ? &live : NULL, prepared ? reserve : NULL, result);
	/* A successful store consumes its reserve, including unused nodes. On
	 * refusal/cancellation, the origin frees every still-owned allocation only
	 * after its exact queue node has retired. No whole state/packet is copied. */
	mas_destroy(&live);
	mas_destroy(reserve);
	for (i = 0; i < 2; i++) {
		mas_destroy(prep.split_mas[i]);
		if (prep.split_vma[i]) {
			vm_area_free(prep.split_vma[i]);
			freed |= 1U << i;
		} else if (allocated[i]) {
			consumed |= 1U << i;
		}
		BUG_ON(prep.split_mas[i]->alloc);
		if (prep.split_avc[i]) {
			kd_anon_vma_chain_free(prep.split_avc[i]);
			avc_freed |= 1U << i;
		} else if (allocated_avc[i]) {
			avc_consumed |= 1U << i;
		}
	}
	BUG_ON(live.alloc || reserve->alloc || (freed & consumed));
	if (allocated[0] && atomic64_read(&mm->mmap_lock.unmap.calls) <= 64)
		pr_info("KD_MM_SPLIT retire mm=%px origin=%d start=%lx end=%lx vma0=%lx vma1=%lx consumed=%u freed=%u\n",
			mm, current->pid, start, end, allocated[0], allocated[1], consumed, freed);
	if (allocated_avc[0] && atomic64_read(&mm->mmap_lock.unmap.calls) <= 64)
		pr_info("KD_MM_RMAP retire mm=%px origin=%d start=%lx end=%lx avc0=%lx avc1=%lx consumed=%u freed=%u\n",
			mm, current->pid, start, end, allocated_avc[0], allocated_avc[1], avc_consumed, avc_freed);
	return handled;
}
