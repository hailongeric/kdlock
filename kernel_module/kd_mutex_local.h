/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_LOCAL_H
#define KD_MUTEX_LOCAL_H
#include <linux/osq_lock.h>
#include <linux/percpu.h>
#include "kd_mutex.h"

#define KD_MUTEX_TAIL_IDX_OFFSET 2
#define KD_MUTEX_TAIL_IDX_BITS 2
#define KD_MUTEX_TAIL_IDX_MASK ((1U << KD_MUTEX_TAIL_IDX_BITS) - 1)
#define KD_MUTEX_TAIL_CPU_OFFSET \
	(KD_MUTEX_TAIL_IDX_OFFSET + KD_MUTEX_TAIL_IDX_BITS)
#define KD_MUTEX_OSQ_WAITING 0
#define KD_MUTEX_OSQ_GRANTED 1
#define KD_MUTEX_OSQ_IDLE 2

DECLARE_PER_CPU_SHARED_ALIGNED(struct kd_mutex_node,
			      kd_mutex_nodes[KD_MUTEX_MAX_NODES]);
struct kd_mutex_osq_node *kd_mutex_osq_node_get(struct kd_mutex *lock);
void kd_mutex_osq_node_put(struct kd_mutex_osq_node *node);
bool kd_mutex_osq_lock(struct optimistic_spin_queue *lock,
		       struct kd_mutex_osq_node *node);
void kd_mutex_osq_unlock(struct optimistic_spin_queue *lock,
			 struct kd_mutex_osq_node *node);
/* Only an explicit delegation head may lend its already reserved slot. */
void kd_mutex_local_lock_node(struct kd_mutex *lock, struct kd_mutex_node *node);
#endif
