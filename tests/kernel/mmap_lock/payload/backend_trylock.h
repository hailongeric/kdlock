/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MMAP_PROBE_BACKEND_TRYLOCK_H
#define KD_MMAP_PROBE_BACKEND_TRYLOCK_H

#include <linux/mmap_lock.h>

/* Linux 7 has no public mmap_write_trylock(). This test-only operation checks
 * the private adapter's try-write API without adding a kernel-wide wrapper.
 * A successful writer still begins the native sequence and emits the native
 * trace events before the ordinary mmap_write_unlock/downgrade can end it. */
static inline bool probe_backend_write_trylock(struct mm_struct *mm)
{
	bool acquired;

	__mmap_lock_trace_start_locking(mm, true);
	acquired = kd_mmap_write_trylock(&mm->mmap_lock);
	if (acquired)
		mm_lock_seqcount_begin(mm);
	__mmap_lock_trace_acquire_returned(mm, true, acquired);
	return acquired;
}

#endif
