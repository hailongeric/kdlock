/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MMAP_FAULT_UAPI_H
#define KD_MMAP_FAULT_UAPI_H
#include <linux/ioctl.h>
#include <linux/types.h>

#define MF_ABI 1
#define MF_NATIVE 0
#define MF_KD 1
#define MF_TC 2
#define MF_PRIVATE 1U
#define MF_WRITABLE 2U
#define MF_INHERIT 4U
#define MF_DOWNGRADE 8U
#define MF_ALLOW_FALLBACK 16U
#define MF_NORMAL 0
#define MF_RETRY 1
#define MF_NOWAIT 2
#define MF_COMPLETED 3
#define MF_REVALIDATE 4
#define MF_WORD 0x4b444d4d00000000ULL

struct mf_create {
	__u32 abi, backend, features, pages;
	__u32 selected_backend, fallback, reserved[2];
};
struct mf_probe {
	__u64 address;
	__u32 action, reserved;
	__s64 result;
	__u64 attempts, acquisitions, releases, retries, nowait, completed;
	__u64 callbacks, revalidated, stale, pause_timeout, final_held;
};
struct mf_stats {
	__u64 backend, features, vmas, active_probe, epoch, faults, reads, read_ends;
	__u64 writes, write_ends, downgrades, context_errors, data_errors, fallback;
	__u64 scopes, scope_ends;
};
#define MF_CREATE _IOWR('M', 1, struct mf_create)
#define MF_PROBE _IOWR('M', 2, struct mf_probe)
#define MF_STATS _IOR('M', 3, struct mf_stats)
#define MF_MUTATE _IO('M', 4)
#define MF_DOWNGRADE_ONCE _IO('M', 5)
#define MF_WAIT_DROP _IO('M', 6)
#define MF_RELEASE_DROP _IO('M', 7)
#endif
