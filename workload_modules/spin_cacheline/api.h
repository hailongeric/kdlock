/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SPIN_CACHELINE_API_H
#define SPIN_CACHELINE_API_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define SC_VERSION 1
#define SC_LINE_BYTES 64
#define SC_SLOTS 16
#define SC_MAX_ITERATIONS 100000000ULL
#define SC_DEVICE "/dev/spin_cacheline"
#define SC_COMM "sc_worker"

/* Fixed x86-64 ioctl ABI; no kdlock dependency or per-operation syscall. */
struct sc_layout {
	__u32 version, line_bytes, slots, lock_bytes;
	__u64 lock_addr, control_addr, data_addr;
	__u64 slot_addr[SC_SLOTS];
};

struct sc_run {
	__u32 cachelines, reserved;
	__u64 iterations, completed;
};

struct sc_counts {
	__u64 values[SC_SLOTS];
	__u32 active, reserved;
};

#define SC_LAYOUT _IOR(0xB7, 0, struct sc_layout)
#define SC_RUN _IOWR(0xB7, 1, struct sc_run)
#define SC_COUNTS _IOR(0xB7, 2, struct sc_counts)

#endif
