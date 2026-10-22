/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MM_UNMAP_TEST_API_H
#define KD_MM_UNMAP_TEST_API_H
#include <linux/types.h>
#include <linux/ioctl.h>
#define UB_WORKERS 16
#define UB_PAGES 48
struct ub_config { __u64 start, end, base, stride, groups; };
struct ub_counts {
	__u64 calls, removed, delegated, native, post_ban;
	__u64 handbacks, acks, cancelled, refused, failed, native_only;
	__u64 populated, populated_remote;
};
struct ub_status {
	struct ub_counts counts;
	__u64 mm, gate, pending, idle, held, ready, readers, pgdir_size, task_size;
	__s64 admission;
	__u64 checks, errors, reader_peak, pending_peak;
	__u64 cancel_tid[2], cancel_mapped[2];
	__s64 cancel_result[2];
	__u64 pins_owned, pins_released;
};
struct ub_page { __u64 address, pfn, hash, mapcount, refs, charged_same, value; };
struct ub_pages { __u64 count; struct ub_page page[UB_PAGES]; };
#define UB_ENABLE _IOW('U', 0x61, struct ub_config)
#define UB_STATUS _IOR('U', 0x62, struct ub_status)
#define UB_HOLD _IO('U', 0x63)
#define UB_CANCEL _IO('U', 0x64)
#define UB_RELEASE _IO('U', 0x65)
#define UB_PIN _IO('U', 0x66)
#define UB_PAGESTATE _IOR('U', 0x67, struct ub_pages)
#define UB_DROP _IO('U', 0x68)
#define UB_UNPIN_MAPPED _IO('U', 0x69)
#endif
