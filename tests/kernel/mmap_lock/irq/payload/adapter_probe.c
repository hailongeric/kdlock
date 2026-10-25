// SPDX-License-Identifier: GPL-2.0
#undef MODULE
#include "probe.h"
/* Select builtin header declarations before any includes, so boot declarations
 * stay inert sections in this standalone module.
 * Only initialization policy is selected here; every operation is the actual
 * generated adapter. These standalone objects are not installed in mm_struct. */
#include "adapter.c"

void kd_irq_init_lock(struct kd_mmap_lock *lock, bool kd)
{
	kd_mmap_enabled = kd;
	kd_mmap_init(lock);
}
