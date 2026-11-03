/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_IRQ_PROBE_H
#define KD_IRQ_PROBE_H
#include <linux/kd_mmap_lock.h>

void kd_irq_init_lock(struct kd_mmap_lock *lock, bool kd);
extern struct kd_mmap_rwsem *kd_irq_inject;
extern unsigned int kd_irq_injections;
#endif
