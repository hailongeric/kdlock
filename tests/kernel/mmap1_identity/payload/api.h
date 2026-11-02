/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MMAP1_IDENTITY_API_H
#define KD_MMAP1_IDENTITY_API_H
#include <linux/ioctl.h>
#include <linux/types.h>

#define KD_MMAP1_IDENTITY_CAPACITY 128
struct kd_mmap1_identity_record {
	__u64 tid, tgid, start_boottime_ns, mm, lock, backing, use_kd, cpu;
	__u64 provider, route;
};
struct kd_mmap1_identity_snapshot {
	__u64 abi, count, overflow, errors, stopped, refs_acquired, refs_released;
	struct kd_mmap1_identity_record records[KD_MMAP1_IDENTITY_CAPACITY];
};
#define KD_MMAP1_IDENTITY_STOP _IOR('M', 0x79, struct kd_mmap1_identity_snapshot)
#endif
