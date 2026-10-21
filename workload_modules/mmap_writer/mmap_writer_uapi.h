/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MMAP_WRITER_UAPI_H
#define KD_MMAP_WRITER_UAPI_H
#include <linux/ioctl.h>
#include <linux/types.h>
#define MW_ABI 1
#define MW_MAX_PAGES 64
struct mw_identity { __u64 abi, object, mm, mmap_lock, tgid, tid; };
struct mw_stats {
	__u64 object, maps, clones, closes, vmas, faults, context_errors;
	__u64 foreign_rejects, contended_mmaps, observe;
};
#define MW_ID _IOR('W', 1, struct mw_identity)
#define MW_STATS _IOR('W', 2, struct mw_stats)
#endif
