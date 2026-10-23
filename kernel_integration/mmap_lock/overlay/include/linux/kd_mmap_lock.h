/* SPDX-License-Identifier: GPL-2.0 */
#ifndef LINUX_KD_MMAP_LOCK_H
#define LINUX_KD_MMAP_LOCK_H

#include <linux/kd_mmap_lock_types.h>

void kd_mmap_init(struct kd_mmap_lock *lock);
void kd_mmap_destroy(struct kd_mmap_lock *lock);
void kd_mmap_write_lock(struct kd_mmap_lock *lock);
void kd_mmap_write_lock_nested(struct kd_mmap_lock *lock, int subclass);
int kd_mmap_write_lock_killable(struct kd_mmap_lock *lock);
int kd_mmap_write_trylock(struct kd_mmap_lock *lock);
void kd_mmap_write_unlock(struct kd_mmap_lock *lock);
void kd_mmap_write_downgrade(struct kd_mmap_lock *lock);
void kd_mmap_read_lock(struct kd_mmap_lock *lock);
int kd_mmap_read_lock_killable(struct kd_mmap_lock *lock);
int kd_mmap_read_trylock(struct kd_mmap_lock *lock);
void kd_mmap_read_unlock(struct kd_mmap_lock *lock);
void kd_mmap_read_unlock_non_owner(struct kd_mmap_lock *lock);
bool kd_mmap_is_locked(struct kd_mmap_lock *lock);
bool kd_mmap_is_write_owner(struct kd_mmap_lock *lock);
bool kd_mmap_is_contended(struct kd_mmap_lock *lock);
bool kd_mmap_is_idle(struct kd_mmap_lock *lock);

struct mm_struct;
/* Explicit experiment opt-in under this mm's physical write ownership. */
int kd_mmap_body_enable(struct mm_struct *mm);
bool kd_mmap_body_write_owned(struct kd_mmap_lock *lock);
unsigned int kd_mmap_body_pending(struct mm_struct *mm);
int kd_mmap_madvise(struct mm_struct *mm, unsigned long start,
		   unsigned long end, int behavior);
/* Fixed in-tree implementations, never supplied by a module or user pointer.
 * try performs no effects before refusal; native runs only on the origin. */
bool kd_mmap_madvise_try(struct mm_struct *mm, unsigned long start,
			unsigned long end, int behavior, int *result);
int kd_mmap_madvise_native(struct mm_struct *mm, unsigned long start,
			  unsigned long end, int behavior);

struct vm_fault;
struct page;
struct task_struct;
enum kd_mmap_fault_result {
	KD_MMAP_FAULT_INSTALLED,
	KD_MMAP_FAULT_LOCAL,
	KD_MMAP_FAULT_CANCELLED,
};
void kd_mmap_fault_init(struct kd_mmap_lock *lock);
int kd_mmap_fault_enable(struct mm_struct *mm, unsigned long start, unsigned long end);
unsigned int kd_mmap_fault_pending(struct mm_struct *mm);
bool kd_mmap_fault_idle(struct kd_mmap_lock *lock);
/* Called only by the real anonymous fault after origin allocation/charging.
 * INSTALLED transfers the page to its PTE; all other results leave the page
 * with the origin. No mmap read share is transferred or released remotely. */
enum kd_mmap_fault_result kd_mmap_fault_submit(struct vm_fault *vmf,
					      struct page *page, unsigned long entry);
bool kd_mmap_fault_try(struct vm_fault *vmf, struct page *page,
		       unsigned long entry, struct task_struct *origin);

struct ma_state;
void kd_mmap_unmap_init(struct kd_mmap_lock *lock);
int kd_mmap_unmap_enable(struct mm_struct *mm, unsigned long start, unsigned long end);
int kd_mmap_unmap_populated_enable(struct mm_struct *mm, unsigned long start, unsigned long end);
int kd_mmap_unmap_resident_partial_enable(struct mm_struct *mm, unsigned long start, unsigned long end);
unsigned int kd_mmap_unmap_pending(struct mm_struct *mm);
/* Allocation-only preparation reads a height hint; actual capacity and VMA
 * eligibility are rechecked under exact physical mmap write ownership. */
int kd_mmap_mas_preallocate(struct ma_state *mas, gfp_t gfp);
struct anon_vma_chain;
struct vm_area_struct;
struct anon_vma_chain *kd_anon_vma_chain_alloc(void);
void kd_anon_vma_chain_free(struct anon_vma_chain *chain);
int kd_anon_vma_clone_prepared(struct vm_area_struct *dst,
	struct vm_area_struct *src, struct anon_vma_chain **prepared);
bool kd_mmap_unmap_submit(struct mm_struct *mm, unsigned long start,
	unsigned long end, struct ma_state *live, struct ma_state *reserve, int *result);
bool kd_mmap_unmap_try(struct mm_struct *mm, unsigned long start,
	unsigned long end, struct task_struct *origin, struct ma_state *live,
	struct ma_state *reserve, u64 request_id, int *result);

#endif
