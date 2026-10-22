/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MM_BODY_API_H
#define KD_MM_BODY_API_H
#include <linux/types.h>
#include <linux/ioctl.h>
#define MB_WORKERS 16
struct mb_counts {
	__u64 calls, supported, delegated, handbacks, native, post_ban, cancelled, acks;
	__u64 native_only;
};
struct mb_result {
	__u64 address[MB_WORKERS];
	__u64 mm, lock, checks, errors, completed, reader_peak, pending_peak, idle;
	__u64 tids[3][MB_WORKERS];
	struct mb_counts counts[3];
};
#define MB_RUN _IOWR('B', 0x51, struct mb_result)
#define MB_CANCEL _IOWR('B', 0x52, struct mb_result)
#endif
