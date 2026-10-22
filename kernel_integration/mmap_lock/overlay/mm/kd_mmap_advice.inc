/* SPDX-License-Identifier: GPL-2.0 */
/* Included after the original madvise walkers. Admission must finish before
 * any mutation: this permits exact origin handback without replay or a saved
 * VMA across an unlock. The supported path calls the original in-tree body. */
bool kd_mmap_madvise_try(struct mm_struct *mm, unsigned long start,
			unsigned long end, int behavior, int *result)
{
	struct vm_area_struct *vma, *prev, *next;

	mmap_assert_write_locked(mm);
	if (behavior != MADV_DONTDUMP && behavior != MADV_DODUMP)
		return false;
	vma = find_vma_prev(mm, start, &prev);
	if (!vma || start != vma->vm_start || end != vma->vm_end ||
	    vma->vm_file || vma->vm_ops || anon_vma_name(vma) ||
	    userfaultfd_armed(vma) || vma_policy(vma) ||
	    (vma->vm_flags & (VM_SPECIAL | VM_HUGETLB | VM_SHARED |
			     VM_GROWSDOWN | VM_GROWSUP | VM_LOCKED)))
		return false;
	next = find_vma(mm, end);
	if ((prev && prev->vm_end == start) || (next && next->vm_start == end))
		return false;
	/* Exact boundaries prohibit splitting; unmapped gaps prohibit merging.
	 * No file/device callback, user access, allocation, page-table operation,
	 * per-task block plug or implicit current->mm participates in this branch.
	 * All lookups and the existing flag store run under the actual mmap_lock. */
	*result = madvise_vma_behavior(vma, &prev, start, end, behavior);
	return true;
}

int kd_mmap_madvise_native(struct mm_struct *mm, unsigned long start,
			  unsigned long end, int behavior)
{
	struct blk_plug plug;
	int error;

	mmap_assert_write_locked(mm);
	blk_start_plug(&plug);
	error = madvise_walk_vmas(mm, start, end, behavior, madvise_vma_behavior);
	blk_finish_plug(&plug);
	return error;
}
