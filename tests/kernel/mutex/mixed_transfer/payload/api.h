/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_MIXED_TRANSFER_API_H
#define KD_MUTEX_MIXED_TRANSFER_API_H
#include <linux/ioctl.h>
#include <linux/types.h>

enum mixed_role { MIXED_GATE, MIXED_SPIN, MIXED_COMBINER, MIXED_WAITER,
		  MIXED_THIEF, MIXED_ROLES };
struct mixed_run {
	__u32 role, iterations;
	__u64 returned, errors;
};
struct mixed_snapshot {
	__u64 a, b, entry, spin_call;
	__u64 active, failures, started, ready, done, release_gate;
	__u64 owner, gate, tail, b_word;
	__u64 prefix, suffix, combiner_bodies;
	__u64 owner_before, owner_after, combiner_owner;
	__u64 samples, steal_attempts, steals, prefix_observed, thief_done;
	__u64 c_task, w_task, warm_ops, armed;
	__u64 warm_eligible, entry_checked, entry_eligible;
	__u64 preholder_release, preholder_done, g_task, t_task;
	__s64 waiters;
};
#define MIXED_RUN _IOWR('M', 1, struct mixed_run)
#define MIXED_SNAPSHOT _IOR('M', 2, struct mixed_snapshot)
#define MIXED_PREPARE _IO('M', 3)
#define MIXED_RELEASE _IO('M', 4)
#define MIXED_DRAIN _IO('M', 5)
#define MIXED_WARMUP _IOWR('M', 6, struct mixed_run)
#define MIXED_ARM _IO('M', 7)
#define MIXED_PREHOLDER_RELEASE _IO('M', 8)
#endif
