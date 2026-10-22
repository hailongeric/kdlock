/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MMAP_PHASE_OBSERVER_API_H
#define KD_MMAP_PHASE_OBSERVER_API_H
#include <linux/types.h>
#include <linux/ioctl.h>
enum phase_count {
#define PHASE_COUNT(name) PH_##name,
#include "counts.def"
#undef PHASE_COUNT
	PH_COUNT
};
struct phase_result {
	__u64 abi, records, active, errors, missed;
	__u64 count[PH_COUNT];
};
struct phase_row {
	__u64 index, task, tid, mm, last_sem, sequence, active, first_entry_ns, last_epilogue_ns;
	__u64 count[PH_COUNT];
};
#define PHASE_ARM _IOW('p', 1, __u64)
#define PHASE_STOP _IO('p', 2)
#define PHASE_RESULT _IOR('p', 3, struct phase_result)
#define PHASE_ROW _IOWR('p', 4, struct phase_row)
#ifdef __KERNEL__
struct mm_struct;
int kd_phase_begin(struct mm_struct *first, struct mm_struct *second);
int kd_phase_snapshot(struct phase_result *result);
int kd_phase_end(struct phase_result *result);
#endif
#endif
