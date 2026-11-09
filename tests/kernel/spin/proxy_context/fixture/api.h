/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_PROXY_CONTEXT_API_H
#define KD_SPIN_PROXY_CONTEXT_API_H
#include <linux/ioctl.h>
#include <linux/types.h>
struct proxy_run {
	__u32 iterations, worker, reserved[2];
	__u64 completed, errors;
};
struct proxy_snapshot {
	__u64 prefix, suffix, hot_taken, lock_address, entry, marker;
	__u64 failures, active, hot, idle;
};
enum proxy_mode {
	PROXY_IF_ON, PROXY_IF_OFF, PROXY_BH, PROXY_RCU,
	PROXY_PREEMPT, PROXY_MIGRATION, PROXY_MIXED_IF, PROXY_MODE_COUNT,
};
#define PROXY_RUN _IOWR('E', 1, struct proxy_run)
#define PROXY_SNAPSHOT _IOR('E', 2, struct proxy_snapshot)
#define PROXY_PREPARE _IO('E', 3)
#define PROXY_MODE _IOW('E', 4, __u32)
#define PROXY_BIND _IOW('E', 5, __u64)
#endif
