/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_STATS_H
#define KD_MUTEX_STATS_H
#include <linux/percpu.h>
#include <linux/types.h>

/* Observations only: never use these values for owner, ACK or drain decisions.
 * x86 this_cpu_inc is one local operation, including in interruptible callers.
 * Live sums are snapshots; a stopped, drained cohort has a stable total. */
#define KD_MUTEX_STAT(name) static DEFINE_PER_CPU(u64, name)
#define KD_MUTEX_STAT_READ(name) ({ \
	u64 kd_stat_total = 0; int kd_stat_cpu; \
	for_each_possible_cpu(kd_stat_cpu) \
		kd_stat_total += READ_ONCE(per_cpu(name, kd_stat_cpu)); \
	kd_stat_total; \
})
#endif
