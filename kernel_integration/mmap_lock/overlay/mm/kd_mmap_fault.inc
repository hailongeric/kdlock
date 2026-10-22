/* SPDX-License-Identifier: GPL-2.0 */
/* Shared real do_anonymous_page installation body, entered with its PTE lock.
 * Page allocation, charging, throttling and task fault accounting stay on the
 * origin. Remote RSS accounting targets the explicit mm rather than another
 * task's deferred RSS cache. The page transfers to the PTE exactly once. */
static noinline void do_anonymous_page_install(struct vm_fault *vmf,
		struct page *page, pte_t entry, struct task_struct *origin)
{
	struct vm_area_struct *vma = vmf->vma;

	if (origin == current)
		inc_mm_counter_fast(vma->vm_mm, MM_ANONPAGES);
	else
		inc_mm_counter(vma->vm_mm, MM_ANONPAGES);
	page_add_new_anon_rmap(page, vma, vmf->address);
	lru_cache_add_inactive_or_unevictable(page, vma);
	set_pte_at(vma->vm_mm, vmf->address, vmf->pte, entry);
	update_mmu_cache(vma, vmf->address, vmf->pte);
}

bool kd_mmap_fault_try(struct vm_fault *vmf, struct page *page,
		       unsigned long value, struct task_struct *origin)
{
	struct vm_area_struct *vma = vmf->vma;
	struct mm_struct *mm = vma->vm_mm;
	bool installed = false;

	/* x86-64's update_mmu_cache is local-task independent. Multi-generation
	 * LRU uses current->in_lru_fault/PF_MEMALLOC, so refuse that configuration
	 * rather than impersonating the caller. The validated kernel disables it. */
	if (IS_ENABLED(CONFIG_LRU_GEN) || origin->mm != mm ||
	    !(vmf->flags & FAULT_FLAG_WRITE) || (vmf->flags & FAULT_FLAG_REMOTE) ||
	    vma->vm_file || vma->vm_ops || userfaultfd_armed(vma) || vma_policy(vma) ||
	    !(vma->vm_flags & VM_NOHUGEPAGE) ||
	    (vma->vm_flags & (VM_SPECIAL | VM_HUGETLB | VM_SHARED | VM_LOCKED |
			     VM_GROWSDOWN | VM_GROWSUP)) ||
	    PageCompound(page) || !PageUptodate(page) || pmd_trans_unstable(vmf->pmd))
		return false;
	/* Another mmap reader may have installed or discarded this PTE while the
	 * request waited. Check under the real PTE lock before any body effects.
	 * A refused request retains its page and native continuation on the origin. */
	vmf->pte = pte_offset_map_lock(mm, vmf->pmd, vmf->address, &vmf->ptl);
	if (pte_none(*vmf->pte) && !check_stable_address_space(mm)) {
		do_anonymous_page_install(vmf, page, __pte(value), origin);
		installed = true;
	}
	pte_unmap_unlock(vmf->pte, vmf->ptl);
	vmf->pte = NULL;
	vmf->ptl = NULL;
	return installed;
}
