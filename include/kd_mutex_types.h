/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_TYPES_H
#define KD_MUTEX_TYPES_H

#include "kd_config.h"
#include <linux/atomic.h>
#include <linux/spinlock.h>
#include <linux/osq_lock.h>

struct kd_wait_node;

/* One guarded circular queue holds local and captured acquisitions. Physical
 * ownership and execution remain separate from membership. Equal geometry
 * never permits mixed protocols. */
struct kd_mutex {
	atomic_long_t owner;
	raw_spinlock_t wait_lock;
	struct optimistic_spin_queue osq;
	struct kd_wait_node *wait_head;
	atomic_t delegation_state;
	u32 delegation_tail; /* reserved; no independent tail publication */
};

#define KD_MUTEX_INITIALIZER(name) { \
 .owner = ATOMIC_LONG_INIT(0), .osq = OSQ_LOCK_UNLOCKED, \
 .wait_lock = __RAW_SPIN_LOCK_UNLOCKED(name.wait_lock), \
 .wait_head = NULL, .delegation_state = ATOMIC_INIT(0), .delegation_tail = 0 }
#define DEFINE_KD_MUTEX(name) struct kd_mutex name = KD_MUTEX_INITIALIZER(name)

#endif
