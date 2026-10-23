/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MM_UNMAP_TEST_API_H
#define KD_MM_UNMAP_TEST_API_H
#include <linux/types.h>
#include <linux/ioctl.h>
#define UB_WORKERS 16
struct ub_config { __u64 start, end, base, stride; };
struct ub_counts {
	__u64 calls, removed, delegated, native, post_ban;
	__u64 handbacks, acks, cancelled, refused, failed, native_only;
};
struct ub_status {
	struct ub_counts counts;
	__u64 mm, gate, pending, idle, held, ready, readers, pgdir_size, task_size;
	__s64 admission;
	__u64 checks, errors, reader_peak, pending_peak;
	__u64 cancel_tid[2], cancel_mapped[2];
	__s64 cancel_result[2];
};
#define UB_ENABLE _IOW('U', 0x61, struct ub_config)
#define UB_STATUS _IOR('U', 0x62, struct ub_status)
#define UB_HOLD _IO('U', 0x63)
#define UB_CANCEL _IO('U', 0x64)
#define UB_RELEASE _IO('U', 0x65)
/* Read one exact VMA and explicit-mm accounting under local read ownership.
 * Existing control structures/ioctl encodings remain binary-compatible. */
struct ub_layout {
	__u64 address, start, end, pgoff, flags;
	__u64 map_count, total_vm, data_vm, stack_vm, exec_vm, pgtables;
};
#define UB_LAYOUT _IOWR('U', 0x66, struct ub_layout)
#define UB_CANCEL_PARTIAL _IO('U', 0x67)
#endif
