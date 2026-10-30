/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MMAP_STRICT_HOLD_API_H
#define KD_MMAP_STRICT_HOLD_API_H
#include <linux/ioctl.h>
#include <linux/types.h>
#define SH_ABI 1
enum sh_state { SH_IDLE, SH_STARTING, SH_HELD, SH_FINISHED };
struct sh_report {
	__u64 abi, object, mm, mmap_lock, target_tgid, target_tid, holder_tid;
	__u64 use_kd, state, acquired, unlocked, timed_out, errors, joined;
};
struct sh_context { __u64 mm, tgid, tid; };
#define SH_REPORT _IOR('H', 1, struct sh_report)
#define SH_START _IO('H', 2)
#define SH_STATUS _IO('H', 3)
#define SH_RELEASE _IO('H', 4)
#define SH_JOIN _IO('H', 5)
#define SH_CONTEXT _IOR('H', 6, struct sh_context)
#endif
