/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MMAP_COMPLETED_API_H
#define KD_MMAP_COMPLETED_API_H
#include <linux/ioctl.h>
#include <linux/types.h>
struct completed_range { __u64 start, end; };
struct completed_result {
	__u64 mm, lock, tid, use_kd, entries, returns, completed, retries, errors, missed;
	__u64 write_reacquired;
};
#define COMPLETED_START _IOW('M', 0x72, struct completed_range)
#define COMPLETED_END _IOR('M', 0x73, struct completed_result)
#endif
