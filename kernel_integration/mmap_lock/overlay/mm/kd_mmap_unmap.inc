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

static unsigned int kd_mmap_unmap_hold_pages(struct mm_struct *mm,
	struct vm_area_struct *vma, struct vm_area_struct *prev,
	struct vm_area_struct *next, unsigned long start, unsigned long end,
	bool partial, pmd_t **held_pmd, struct page **pages,
	unsigned int *present, unsigned int *zero, pte_t *zero_ptes,
	unsigned int *checked)
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
	*present = 0;
	*zero = 0;
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
	for (i = 0; i < count; i++) {
		struct page *page;
		unsigned long slot = address + i * PAGE_SIZE;
		pte_t entry = ptep_get(pte + i);

		/* Only retained slots may be absent. A partial target or survivor
		 * may map the permanent zero page, with no owned anonymous reference:
		 * do not get, lock, put or modify its page. Keep all slot identities
		 * separate. The writer excludes read/write faults during the body;
		 * already mapped readers may still set the hardware accessed bit. */
		if (partial) {
			if (pte_none(entry) && (slot < start || slot >= end)) continue;
			if (pte_present(entry) && !pte_protnone(entry) &&
			    pte_special(entry) && !pte_write(entry) &&
			    !pte_devmap(entry) && is_zero_pfn(pte_pfn(entry))) {
				*zero |= 1U << i;
				zero_ptes[i] = pte_mkold(entry);
				continue;
			}
		}
		/* All remaining present slots must be writable private resident pages.
		 * Unsupported special, swap and absent targets refuse before splitting. */
		if (!pte_present(entry) || !pte_write(entry) || pte_special(entry) || pte_devmap(entry)) break;
		page = vm_normal_page(vma, slot, entry);
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
		pages[i] = page;
		*present |= 1U << i;
		held++;
	}
	pte_unmap_unlock(pte, ptl);
	if (i != count) {
		*checked = held;
		kd_mmap_unmap_release_pages(pages, i);
		return 0;
	}
	*held_pmd = pmd;
	/* Keep at least one ordinary resident page and the existing single-link
	 * ancestry contract. With a zero target, that page must be a survivor. */
	return held;
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
	unsigned long address, pages, table_bytes = 0;
	unsigned long old_start, old_end, old_flags, old_pgoff;
	unsigned int before, nr = 0, i, checked, splits = 0, present = 0, zero = 0, slots;
	struct kd_mmap_unmap_preparation *prep;
	bool pristine, partial, zero_target = false;

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
			/* One private resident or shared-zero target in a three-page VMA.
			 * Retained slots may be private, zero or absent. The page walk still
			 * requires a private resident slot. Refuse unsupported ancestry or
			 * missing allocation before any split occurs. */
			if (!mm->mmap_lock.unmap.allow_partial || pristine ||
			    old_end - old_start != 3 * PAGE_SIZE || end - start != PAGE_SIZE ||
			    !vma->anon_vma || !list_is_singular(&vma->anon_vma_chain) ||
			    list_first_entry(&vma->anon_vma_chain, struct anon_vma_chain,
					     same_vma)->anon_vma != vma->anon_vma ||
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
		nr = kd_mmap_unmap_hold_pages(mm, vma, prev, next, start, end,
			partial, &held_pmd, held, &present, &zero, zero_ptes, &checked);
		if (!nr) {
			if (checked)
				pr_info("KD_MM_POPULATED_RANGE rollback mm=%px id=%llu origin=%d executor=%d start=%lx end=%lx held=%u released=%u effects=0\n",
					mm, request_id, origin->pid, current->pid, start, end, checked, checked);
			return false;
		}
		for (i = 0; i < slots; i++)
			if (present & (1U << i)) pfns[i] = page_to_pfn(held[i]);
		zero_target = partial && (zero & (1U << ((start - old_start) >> PAGE_SHIFT)));
		table_bytes = mm_pgtables_bytes(mm);
	}
	/* The origin already checked TASK_SIZE/alignment with its own thread mode.
	 * x86-64 arch_unmap is empty in this captured source. No stale VMA or maple
	 * traversal pointer crosses publication; prepare only read a height hint. */
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
	if (nr) {
		/* Neighbor VMAs keep this page-table directory under our writer.
		 * Native teardown has completed its TLB flush; a removed private page
		 * also lost its mapping reference. Zero pages own no such reference.
		 * Release our temporary private-page references on this executor;
		 * page/memcg ownership, never current's cgroup, governs final free. */
		if (!*result || zero) {
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
				} else if (*result) {
					continue;
				} else if (!(present & (1U << i))) {
					BUG_ON(!pte_none(ptep_get(pte + i)) || held[i]);
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
				if (zero_target) {
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
	if (*result && zero_target)
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
