/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MMAP_PROBE_API_H
#define KD_MMAP_PROBE_API_H
#include <linux/ioctl.h>
#include <linux/types.h>

struct kd_mmap_probe_result {
	__u64 abi, use_kd, mm, lock, checks, errors, api_checks, nested_checks;
	__u64 cancellation_checks, readers_slept, writer_slept, late_reader_slept;
	__u64 downgrade_checks, transfer_checks, irq_checks, destroy_checks, idle;
};
#define KD_MMAP_PROBE_RUN _IOR('M', 0x71, struct kd_mmap_probe_result)
#endif
