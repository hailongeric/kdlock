/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_LOCAL_H
#define KD_MUTEX_LOCAL_H
#include <linux/osq_lock.h>
int kd_mutex_osq_init(void);
void kd_mutex_osq_exit(void);
bool kd_mutex_osq_lock(struct optimistic_spin_queue *lock);
void kd_mutex_osq_unlock(struct optimistic_spin_queue *lock);
#endif
