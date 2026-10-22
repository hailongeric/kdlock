/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MM_FAULT_TEST_API_H
#define KD_MM_FAULT_TEST_API_H
#include <linux/types.h>
#include <linux/ioctl.h>
#define FB_WORKERS 16
struct fb_region { __u64 start, end; };
struct fb_counts {
	__u64 calls, supported, delegated, native, post_ban;
	__u64 handbacks, acks, cancelled, refused, native_only;
};
struct fb_status {
	struct fb_counts counts;
	__u64 mm, gate, pending, idle, held;
	__u64 checks, errors, reader_peak, delegated_with_readers;
	__u64 cancel_tid[2], cancel_present[2];
	__s64 cancel_result[2];
};
#define FB_ENABLE _IOW('F', 0x61, struct fb_region)
#define FB_STATUS _IOR('F', 0x62, struct fb_status)
#define FB_HOLD _IO('F', 0x63)
#define FB_CANCEL _IO('F', 0x64)
#endif
