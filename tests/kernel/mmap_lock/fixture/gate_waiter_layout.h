/* SPDX-License-Identifier: GPL-2.0 */
/* Test-only view checked against the captured local-gate source by run.py. */
#ifndef KD_MMAP_PROBE_GATE_WAITER_LAYOUT_H
#define KD_MMAP_PROBE_GATE_WAITER_LAYOUT_H
#include <linux/list.h>

#define KD_MMAP_WAITERS 1UL
#define KD_MMAP_HANDOFF 2UL
#define KD_MMAP_PICKUP 4UL
#define KD_MMAP_FLAGS 7UL

struct kd_mmap_local_waiter {
	struct list_head list;
	struct task_struct *task;
};

#endif
