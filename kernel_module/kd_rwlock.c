// SPDX-License-Identifier: GPL-2.0
/* Reader admission derived from TCLocks komb_rwlock.c.
 * Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi */
/* Local contended readers. The inline entry retains the fast increment/test;
 * this provider boundary owns no additional pin and never delegates a reader. */
#include <linux/export.h>
#include "kd_rwlock.h"

noinline void kd_rwlock_read_lock_slowpath(kd_rwlock_t *lock)
{
	/* Match native queued rwlocks: an interrupt/BH reader may interrupt a
	 * reader that a queued writer is draining. Joining that writer's gate
	 * would deadlock the interrupted reader. Keep this count and wait only
	 * for actual writer ownership, never for WAITING or the gate. */
	if (unlikely(in_interrupt())) {
		atomic_cond_read_acquire(&lock->cnts, !(VAL & KD_RWLOCK_WRITER_LOCKED));
		return;
	}

	/* Do not wait in the admission queue while counted as an active reader:
	 * its writer head may already be waiting for that count to reach zero. */
	atomic_sub(KD_RWLOCK_READER_BIAS, &lock->cnts);
	kd_spin_direct_native_lock_inline(&lock->gate);
	/* The count prevents another ungated writer from entering. A fast writer
	 * which won before this increment can still be active: wait for its
	 * release while holding the gate, before allowing the reader body. */
	atomic_add(KD_RWLOCK_READER_BIAS, &lock->cnts);
	atomic_cond_read_acquire(&lock->cnts, !(VAL & KD_RWLOCK_WRITER_LOCKED));
	kd_spin_direct_native_release_inline(&lock->gate);
}
EXPORT_SYMBOL_GPL(kd_rwlock_read_lock_slowpath);
