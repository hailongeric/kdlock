/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_RW_ADMISSION_H
#define KDLOCK_RW_ADMISSION_H

#include "rw.h"

/* x86_64 sleepable rwsems only. Readers, the physical writer, published
 * writer queue users and registered reader waits share this atomic word.
 * The supported workload has at most 2^30-1 admitted reads and 65535 of each
 * registered wait kind per object. Checked increments enforce these bounds
 * before publication; exceeding them is a violated admission contract.
 */
#define KD_RW_ADMIT_WRITE       (1UL << 0)
#define KD_RW_ADMIT_WAKE        (1UL << 1)
#define KD_RW_ADMIT_READ        (1UL << 2)
#define KD_RW_ADMIT_READ_MASK   (0x3fffffffUL << 2)
#define KD_RW_ADMIT_QUEUE       (1UL << 32)
#define KD_RW_ADMIT_QUEUE_MASK  (0xffffUL << 32)
#define KD_RW_ADMIT_WAIT        (1UL << 48)
#define KD_RW_ADMIT_WAIT_MASK   (0xffffUL << 48)
#define KD_RW_ADMIT_MAX_READERS (KD_RW_ADMIT_READ_MASK / KD_RW_ADMIT_READ)

bool kd_rw_admission_read_try(struct kd_rw *lock);
int kd_rw_admission_read(struct kd_rw *lock, unsigned int wait_state,
		const struct kd_rw_wait_ops *ops, void *context);
void kd_rw_admission_read_put(struct kd_rw *lock);
bool kd_rw_admission_write_try(struct kd_rw *lock, bool queued);
void kd_rw_admission_write_put(struct kd_rw *lock, bool downgrade);
void kd_rw_admission_queue_get(struct kd_rw *lock);
void kd_rw_admission_queue_put(struct kd_rw *lock);
bool kd_rw_admission_waking(struct kd_rw *lock);
unsigned long kd_rw_admission_readers(struct kd_rw *lock);

#endif
