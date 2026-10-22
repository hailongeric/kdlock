/* SPDX-License-Identifier: GPL-2.0 */
/* Whole isolated anonymous VMA removal. The caller prepares maple allocations;
 * the real native removal helper retains its full page-table/TLB teardown.
 * Initial admission excludes even a top-level table for this range, so no
 * page/table batch allocation or caller-dependent page release can occur. */
bool kd_mmap_unmap_try(struct mm_struct *mm, unsigned long start,
	unsigned long end, struct task_struct *origin, struct ma_state *live,
	struct ma_state *reserve, int *result)
{
	struct vm_area_struct *vma, *prev, *next;
	unsigned long address, pages;
	unsigned int before;

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
	    vma->vm_file || vma->vm_ops || vma->anon_vma ||
	    !list_empty(&vma->anon_vma_chain) || anon_vma_name(vma) ||
	    userfaultfd_armed(vma) || vma_policy(vma) ||
	    !(vma->vm_flags & VM_NOHUGEPAGE) ||
	    (vma->vm_flags & (VM_SPECIAL | VM_HUGETLB | VM_SHARED | VM_ACCOUNT |
			     VM_GROWSDOWN | VM_GROWSUP | VM_LOCKED)))
		return false;
	next = find_vma(mm, end);
	if ((prev && prev->vm_end == start) || (next && next->vm_start == end))
		return false;
	for (address = start; address < end; address = pgd_addr_end(address, end))
		if (!pgd_none(READ_ONCE(*pgd_offset(mm, address))))
			return false;
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
