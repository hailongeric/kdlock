/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MMAP_BODY_INTERNAL_H
#define KD_MMAP_BODY_INTERNAL_H
#include <linux/atomic.h>
#include "kd_mmap_mutex_local.h"
struct kd_mmap_rwsem;

struct kd_mmap_mutex_node *kd_mmap_body_node_get(struct kd_mmap_mutex *lock);
int kd_mmap_mutex_lock_killable_node(struct kd_mmap_mutex *lock,
				   struct kd_mmap_mutex_node *node);
int kd_mmap_rwsem_body_lock(struct kd_mmap_rwsem *sem,
			   struct kd_mmap_mutex_node *node);
#endif
