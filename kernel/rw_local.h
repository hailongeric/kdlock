/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_RW_LOCAL_H
#define KDLOCK_RW_LOCAL_H

#include "rw_native.h"

/* Cold task storage, one record per explicit resource slot. Ordinary reads use
 * only the record's identity/link fields. Its MCS fields are prepared only on a
 * contended local writer; no source packet, image or execution frame is made.
 */
struct kd_rw_local {
	struct kd_rw_native_pool pool;
	struct kd_rw_native_record record;
};

void kd_rw_local_init(struct kd_rw_local *local, struct list_head *free);
struct kd_task_root_context *kd_rw_local_root(void);
bool kd_rw_local_read_lock(struct kd_rw *lock);
bool kd_rw_local_write_try(struct kd_rw *lock, struct kd_task_root_context *root);
int kd_rw_local_write_lock(struct kd_rw *lock, struct kd_task_root_context *root);
bool kd_rw_local_read_release(struct kd_rw *lock);
bool kd_rw_local_write_release(struct kd_rw *lock, bool downgrade);
bool kd_rw_local_native_writer(struct kd_rw *lock);
void kd_rw_local_done(struct kd_rw *lock, struct kd_rw_native_record *record);

#endif
